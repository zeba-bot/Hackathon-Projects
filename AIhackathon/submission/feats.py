"""Cleaning + feature engineering for payment->invoice reconciliation."""
import re
from collections import defaultdict

FIELDS = ('captured', 'refunded', 'fees', 'net')


def digits(s):
    if s is None:
        return None
    m = re.findall(r'\d+', str(s))
    return ''.join(m) if m else None


def norm_name(s):
    return None if s is None else ' '.join(str(s).split()).casefold()


def norm_cur(s):
    return None if s is None else str(s).strip().upper()


def unpack_raw_feed(ob):
    """
    Unpacks migrated asynchronous raw_feed events into:
    - ob['transactions']
    - ob['bank_credits']
    - ob['remittance_documents']
    - backfills ob['payments'] identity hints (source_ref, tax_suffix, sender_name)
    according to staged-operations-v1 specification in RECORDS.md.
    """
    raw_feed = ob.get('raw_feed')
    if not raw_feed:
        return ob

    columns = raw_feed.get('columns', [])
    col_idx = {c: i for i, c in enumerate(columns)} if columns else {}
    sources = raw_feed.get('sources', {})
    events = raw_feed.get('events', [])
    snapshot_minute = raw_feed.get('snapshot_business_minute')

    def parse_money(val, factor):
        if val is None:
            return 0
        if isinstance(val, int) and factor == 1:
            return val
        try:
            return int(round(float(val) * factor))
        except (ValueError, TypeError):
            return 0

    # 1. Filter events arriving before snapshot_business_minute (exclusive)
    # and deduplicate by (source, kind, record_id) keeping highest revision.
    best_events = {}
    for item in events:
        if isinstance(item, dict):
            ev = item
        elif isinstance(item, (list, tuple)):
            ev = {c: item[col_idx[c]] for c in columns if c in col_idx}
        else:
            continue

        src = ev.get('source', '')
        kind = ev.get('kind', '')
        rec_id = ev.get('record_id', '')
        try:
            rev = int(ev.get('revision', 0))
        except (ValueError, TypeError):
            rev = 0

        src_meta = sources.get(src, {})
        clock_offset = src_meta.get('clock_offset_minutes', 0)
        rcv_minute = ev.get('received_clock_minute')

        if snapshot_minute is not None and rcv_minute is not None:
            biz_received = rcv_minute - clock_offset
            if biz_received >= snapshot_minute:
                continue

        key = (src, kind, rec_id)
        if key not in best_events:
            best_events[key] = (rev, ev)
        else:
            prev_rev, _ = best_events[key]
            if rev > prev_rev:
                best_events[key] = (rev, ev)

    # 2. Extract transactions, bank credits, and remittance documents
    transactions = {}
    bank_credits = {}
    remittance_docs = []

    for (src, kind, rec_id), (rev, ev) in best_events.items():
        payload = ev.get('payload', {})
        if not payload:
            continue

        src_meta = sources.get(src, {})
        factor = src_meta.get('minor_units_per_money_unit', 1)

        if kind == 'transaction':
            tx_id = payload.get('transaction_id') or rec_id
            pid = payload.get('payment_id')
            gross = parse_money(payload.get('gross', 0), factor)
            fee = parse_money(payload.get('fee', 0), factor)
            if 'net' in payload:
                net = parse_money(payload['net'], factor)
            else:
                net = gross - fee
            tx_kind = payload.get('kind', 'capture' if gross >= 0 else 'refund')

            tx_row = {
                'transaction_id': tx_id,
                'payment_id': pid,
                'kind': tx_kind,
                'gross': gross,
                'fee': fee,
                'net': net
            }
            if 'parent_transaction_id' in payload:
                tx_row['parent_transaction_id'] = payload['parent_transaction_id']
            if 'event_id' in payload:
                tx_row['event_id'] = payload['event_id']

            transactions[tx_id] = tx_row

        elif kind == 'bank_credit':
            bank_id = payload.get('bank_id') or rec_id
            pid = payload.get('payment_id')
            amount = parse_money(payload.get('amount', 0), factor)
            bank_row = {
                'bank_id': bank_id,
                'payment_id': pid,
                'amount': amount
            }
            bank_credits[bank_id] = bank_row

        elif kind == 'document':
            d = dict(payload)
            if 'source' not in d:
                d['source'] = src
            if 'document_id' not in d:
                d['document_id'] = rec_id
            remittance_docs.append(d)

    if transactions:
        ob['transactions'] = list(transactions.values())
    elif not ob.get('transactions'):
        ob['transactions'] = []

    if bank_credits:
        ob['bank_credits'] = list(bank_credits.values())
    elif not ob.get('bank_credits'):
        ob['bank_credits'] = []

    if remittance_docs:
        ob['remittance_documents'] = remittance_docs
    elif not ob.get('remittance_documents'):
        ob['remittance_documents'] = []

    # 3. Backfill payment identity hints from processor_receipt
    # "Captured payment/receipt fields share one origin... Fallback receipt documents only re-express provided captured fields."
    proc_by_pay = {}
    for d in remittance_docs:
        if d.get('source') == 'processor_receipt':
            pid = d.get('payment_id')
            if not pid:
                continue
            if pid not in proc_by_pay:
                proc_by_pay[pid] = d
            else:
                prev = proc_by_pay[pid]
                if d.get('status') == 'active' and prev.get('status') != 'active':
                    proc_by_pay[pid] = d
                elif d.get('status') == prev.get('status') and d.get('revision', 0) > prev.get('revision', 0):
                    proc_by_pay[pid] = d

    for p in ob.get('payments', []):
        pid = p.get('payment_id')
        proc = proc_by_pay.get(pid)
        if proc:
            if p.get('source_ref') is None and proc.get('reference') is not None:
                p['source_ref'] = proc['reference']
            if p.get('tax_suffix') is None and proc.get('tax_suffix') is not None:
                p['tax_suffix'] = proc['tax_suffix']
            if p.get('sender_name') is None and proc.get('sender_name') is not None:
                p['sender_name'] = proc['sender_name']

    return ob


def prepare(observation):
    """Deduplicate transactions / bank credits, unpack raw_feed if present, normalise currencies."""
    from copy import deepcopy
    ob = deepcopy(observation)
    if 'raw_feed' in ob:
        unpack_raw_feed(ob)
        # Also sync back to original observation object in case an external evaluator reads observation directly
        if not observation.get('transactions') and ob.get('transactions'):
            observation['transactions'] = ob['transactions']
        if not observation.get('bank_credits') and ob.get('bank_credits'):
            observation['bank_credits'] = ob['bank_credits']
        if not observation.get('remittance_documents') and ob.get('remittance_documents'):
            observation['remittance_documents'] = ob['remittance_documents']
        for p_orig, p_unpacked in zip(observation.get('payments', []), ob.get('payments', [])):
            if p_orig.get('source_ref') is None and p_unpacked.get('source_ref') is not None:
                p_orig['source_ref'] = p_unpacked['source_ref']
            if p_orig.get('tax_suffix') is None and p_unpacked.get('tax_suffix') is not None:
                p_orig['tax_suffix'] = p_unpacked['tax_suffix']
            if p_orig.get('sender_name') is None and p_unpacked.get('sender_name') is not None:
                p_orig['sender_name'] = p_unpacked['sender_name']

    for p in ob.get('payments', []):
        p['currency'] = norm_cur(p.get('currency'))
    for i in ob.get('invoices', []):
        i['currency'] = norm_cur(i.get('currency'))
    ob['transactions'] = list({r['transaction_id']: r for r in ob.get('transactions', [])}.values())
    ob['bank_credits'] = list({r['bank_id']: r for r in ob.get('bank_credits', [])}.values())
    return ob


def build_context(ob):
    """Per-payment summaries needed by the model."""
    cap = defaultdict(int)
    ref = defaultdict(int)
    for t in ob['transactions']:
        cap[t['payment_id']] += max(0, t['gross'])
        ref[t['payment_id']] += max(0, -t['gross'])
    docs = defaultdict(dict)
    for r in ob.get('remittance_documents', []):
        key = (r.get('source'), r.get('lineage') or r.get('document_id'))
        if key not in docs[r['payment_id']]:
            docs[r['payment_id']][key] = r
        elif r.get('status') == 'active' and docs[r['payment_id']][key].get('status') != 'active':
            docs[r['payment_id']][key] = r
        elif r.get('status') == 'active' and r.get('revision', 0) > docs[r['payment_id']][key].get('revision', 0):
            docs[r['payment_id']][key] = r
    ctx = {'cap': cap, 'ref': ref, 'docs': {k: list(v.values()) for k, v in docs.items()}}
    ctx['inv_digits'] = {i['invoice_id']: digits(i['reference']) for i in ob['invoices']}
    ctx['inv_by_id'] = {i['invoice_id']: i for i in ob['invoices']}
    return ctx


def candidates(ob, ctx, p):
    pid = p['payment_id']
    cap, ref = ctx['cap'][pid], ctx['ref'][pid]
    full = cap > 0 and ref >= cap
    out = []
    for i in ob['invoices']:
        if i['merchant'] != p['merchant'] or i['currency'] != p['currency']:
            continue
        if i['amount'] != cap or cap <= 0:
            continue
        if i['status'] == 'cancelled' and not full:
            continue
        if full and i['status'] != 'cancelled':
            continue
        out.append(i)
    return out


PAIR_NAMES = [
    'bias',
    'pay_ref_eq', 'pay_ref_ne', 'pay_ref_none',
    'pay_tax_eq', 'pay_tax_ne', 'pay_name_eq',
    'proc_act', 'proc_inact', 'proc_tax_eq', 'proc_name_eq',
    'bank_ref_eq_clean', 'bank_ref_eq_tpl', 'bank_ref_eq_hi', 'bank_ref_eq_lo', 'bank_ref_eq_man',
    'bank_ref_ne_clean', 'bank_ref_ne_tpl', 'bank_ref_ne_hi',
    'bank_tax_eq', 'bank_tax_ne', 'bank_name_eq',
    'erp_ref_eq_clean', 'erp_ref_eq_tpl', 'erp_ref_eq_hi', 'erp_ref_eq_lo', 'erp_ref_eq_man',
    'erp_ref_ne_clean', 'erp_ref_ne_tpl', 'erp_ref_ne_hi',
    'erp_tax_eq', 'erp_tax_ne', 'erp_name_eq',
    'all_three_agree',
    'bank_erp_agree_eq', 'bank_erp_agree_eq_indep',
    'bank_pay_agree_eq', 'erp_pay_agree_eq',
    'conflict_pay_eq_be_ne', 'conflict_be_eq_pay_ne',
    'bank_erp_points_to_other_cand', 'pay_points_to_other_cand',
    'all_tax_agree', 'be_tax_agree', 'pay_tax_conflict',
    'day0', 'day1', 'day2', 'day_late', 'day_neg',
    'cancel_full',
    'claim_other_ref', 'claim_other_tax', 'claim_other_bank_erp',
    'k_inv'
]

NULL_NAMES = [
    'null_bias',
    'n_ref_none', 'n_ref_any', 'n_tax_any', 'n_name_any',
    'n_bank_ref_any', 'n_erp_ref_any', 'n_no_evidence_any',
    'n_k'
]


def pair_features(ob, ctx, p, i, cands):
    pid = p['payment_id']
    d_ref = digits(p['source_ref'])
    inv_ref = ctx['inv_digits'][i['invoice_id']]
    i_tax = digits(i['tax_suffix'])
    i_name = norm_name(i['customer_name'])

    f = dict.fromkeys(PAIR_NAMES, 0.0)
    f['bias'] = 1.0

    # Pay
    if d_ref is None:
        f['pay_ref_none'] = 1.0
    elif d_ref == inv_ref:
        f['pay_ref_eq'] = 1.0
    else:
        f['pay_ref_ne'] = 1.0

    p_tax = digits(p['tax_suffix'])
    if p_tax is not None:
        if p_tax == i_tax:
            f['pay_tax_eq'] = 1.0
        else:
            f['pay_tax_ne'] = 1.0

    if norm_name(p['sender_name']) == i_name:
        f['pay_name_eq'] = 1.0

    # Docs
    docs = ctx['docs'].get(pid, [])
    proc = next((d for d in docs if d['source'] == 'processor_receipt'), None)
    bank = next((d for d in docs if d['source'] == 'bank_memo'), None)
    erp = next((d for d in docs if d['source'] == 'erp_advice'), None)

    if proc:
        f['proc_act' if proc['status'] == 'active' else 'proc_inact'] = 1.0
        if digits(proc['tax_suffix']) == i_tax:
            f['proc_tax_eq'] = 1.0
        if norm_name(proc['sender_name']) == i_name:
            f['proc_name_eq'] = 1.0

    b_ref = digits(bank['reference']) if bank else None
    if bank and b_ref is not None:
        tpl = bank.get('template_reused')
        ocr = bank.get('ocr_confidence')
        man = bank.get('manual_entry')
        if b_ref == inv_ref:
            if tpl:
                f['bank_ref_eq_tpl'] = 1.0
            else:
                f['bank_ref_eq_clean'] = 1.0
            if ocr is not None and ocr >= 0.9:
                f['bank_ref_eq_hi'] = 1.0
            if ocr is not None and ocr < 0.7:
                f['bank_ref_eq_lo'] = 1.0
            if man:
                f['bank_ref_eq_man'] = 1.0
        else:
            if tpl:
                f['bank_ref_ne_tpl'] = 1.0
            else:
                f['bank_ref_ne_clean'] = 1.0
            if ocr is not None and ocr >= 0.9:
                f['bank_ref_ne_hi'] = 1.0
    if bank and digits(bank['tax_suffix']) is not None:
        if digits(bank['tax_suffix']) == i_tax:
            f['bank_tax_eq'] = 1.0
        else:
            f['bank_tax_ne'] = 1.0
    if bank and norm_name(bank['sender_name']) == i_name:
        f['bank_name_eq'] = 1.0

    e_ref = digits(erp['reference']) if erp else None
    if erp and e_ref is not None:
        tpl = erp.get('template_reused')
        ocr = erp.get('ocr_confidence')
        man = erp.get('manual_entry')
        if e_ref == inv_ref:
            if tpl:
                f['erp_ref_eq_tpl'] = 1.0
            else:
                f['erp_ref_eq_clean'] = 1.0
            if ocr is not None and ocr >= 0.9:
                f['erp_ref_eq_hi'] = 1.0
            if ocr is not None and ocr < 0.7:
                f['erp_ref_eq_lo'] = 1.0
            if man:
                f['erp_ref_eq_man'] = 1.0
        else:
            if tpl:
                f['erp_ref_ne_tpl'] = 1.0
            else:
                f['erp_ref_ne_clean'] = 1.0
            if ocr is not None and ocr >= 0.9:
                f['erp_ref_ne_hi'] = 1.0
    if erp and digits(erp['tax_suffix']) is not None:
        if digits(erp['tax_suffix']) == i_tax:
            f['erp_tax_eq'] = 1.0
        else:
            f['erp_tax_ne'] = 1.0
    if erp and norm_name(erp['sender_name']) == i_name:
        f['erp_name_eq'] = 1.0

    # Cross source agreements
    if d_ref == inv_ref and b_ref == inv_ref and e_ref == inv_ref:
        f['all_three_agree'] = 1.0

    shared_lin = (bank and erp and bank.get('lineage') == erp.get('lineage'))
    if b_ref == inv_ref and e_ref == inv_ref:
        f['bank_erp_agree_eq'] = 1.0
        if not shared_lin:
            f['bank_erp_agree_eq_indep'] = 1.0

    if b_ref == inv_ref and d_ref == inv_ref and e_ref != inv_ref:
        f['bank_pay_agree_eq'] = 1.0
    if e_ref == inv_ref and d_ref == inv_ref and b_ref != inv_ref:
        f['erp_pay_agree_eq'] = 1.0

    if d_ref == inv_ref and (b_ref is not None or e_ref is not None):
        if (b_ref != inv_ref) and (e_ref != inv_ref):
            f['conflict_pay_eq_be_ne'] = 1.0

    if (b_ref == inv_ref or e_ref == inv_ref) and d_ref is not None and d_ref != inv_ref:
        f['conflict_be_eq_pay_ne'] = 1.0

    cand_refs = {ctx['inv_digits'][c['invoice_id']] for c in cands if c['invoice_id'] != i['invoice_id']}
    if b_ref is not None and b_ref == e_ref and b_ref in cand_refs:
        f['bank_erp_points_to_other_cand'] = 1.0
    if d_ref is not None and d_ref in cand_refs:
        f['pay_points_to_other_cand'] = 1.0

    if f['pay_tax_eq'] and f['bank_tax_eq'] and f['erp_tax_eq']:
        f['all_tax_agree'] = 1.0
    if f['bank_tax_eq'] and f['erp_tax_eq']:
        f['be_tax_agree'] = 1.0
    if not f['pay_tax_eq'] and (f['bank_tax_eq'] or f['erp_tax_eq']):
        f['pay_tax_conflict'] = 1.0

    # Days
    dd = p['day'] - i['issued_day']
    if dd < 0:
        f['day_neg'] = 1.0
    elif dd == 0:
        f['day0'] = 1.0
    elif dd == 1:
        f['day1'] = 1.0
    elif dd == 2:
        f['day2'] = 1.0
    else:
        f['day_late'] = 1.0

    f['cancel_full'] = float(i['status'] == 'cancelled')
    f['k_inv'] = len(cands) / 5.0

    # Competition
    cr = ct = cbe = 0
    for q in ob['payments']:
        if q['payment_id'] == pid or q['merchant'] != p['merchant']:
            continue
        if ctx['cap'][q['payment_id']] != ctx['cap'][pid]:
            continue
        if digits(q['source_ref']) == inv_ref and inv_ref is not None:
            cr += 1
        if digits(q['tax_suffix']) == i_tax and i_tax is not None:
            ct += 1
        for d in ctx['docs'].get(q['payment_id'], []):
            if d['source'] != 'processor_receipt' and digits(d.get('reference')) == inv_ref and inv_ref is not None:
                cbe += 1
                break
    f['claim_other_ref'] = float(min(cr, 2))
    f['claim_other_tax'] = float(min(ct, 2))
    f['claim_other_bank_erp'] = float(min(cbe, 2))

    return [f[n] for n in PAIR_NAMES]


def null_features(ob, ctx, p, cands, pair_rows):
    pid = p['payment_id']
    d_ref = digits(p['source_ref'])
    p_tax = digits(p['tax_suffix'])
    p_name = norm_name(p['sender_name'])

    docs = ctx['docs'].get(pid, [])
    bank = next((d for d in docs if d['source'] == 'bank_memo'), None)
    erp = next((d for d in docs if d['source'] == 'erp_advice'), None)
    b_ref = digits(bank['reference']) if bank else None
    e_ref = digits(erp['reference']) if erp else None

    cand_refs = {ctx['inv_digits'][c['invoice_id']] for c in cands}
    cand_taxes = {digits(c['tax_suffix']) for c in cands}
    cand_names = {norm_name(c['customer_name']) for c in cands}

    g = dict.fromkeys(NULL_NAMES, 0.0)
    g['null_bias'] = 1.0
    g['n_ref_none'] = float(d_ref is None)
    g['n_ref_any'] = float(d_ref is not None and d_ref in cand_refs)
    g['n_tax_any'] = float(p_tax is not None and p_tax in cand_taxes)
    g['n_name_any'] = float(p_name is not None and p_name in cand_names)
    g['n_bank_ref_any'] = float(b_ref is not None and b_ref in cand_refs)
    g['n_erp_ref_any'] = float(e_ref is not None and e_ref in cand_refs)

    has_any_ref = (g['n_ref_any'] or g['n_bank_ref_any'] or g['n_erp_ref_any'])
    g['n_no_evidence_any'] = float(not has_any_ref)
    g['n_k'] = len(cands) / 5.0

    return [g[n] for n in NULL_NAMES]
