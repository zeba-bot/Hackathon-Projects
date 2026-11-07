"""Score the solution on training cases: python tools/local_eval.py
(Mimics the portal formula + SCHEMA.md integrity checks. Not the official checker.)"""
import copy, collections, json, os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'submission'))
import solution as S
from feats import *


def validate(case_ob, act):
    ob = prepare(case_ob)
    inv = {i['invoice_id']: i for i in ob['invoices']}
    pays = {p['payment_id']: p for p in ob['payments']}
    tx = collections.defaultdict(list)
    for t in ob['transactions']: tx[t['payment_id']].append(t)
    if set(act) != {'op', 'matches', 'ledger', 'suspense', 'bank_total'}: return 'keys'
    mp = {}; ui = set()
    for m in act['matches']:
        if m['payment_id'] in mp or m['invoice_id'] in ui: return 'duplicate'
        mp[m['payment_id']] = m['invoice_id']; ui.add(m['invoice_id'])
        p, i = pays[m['payment_id']], inv[m['invoice_id']]
        if (p['merchant'], p['currency']) != (i['merchant'], i['currency']): return 'cross merchant/currency'
        cap = sum(max(0, t['gross']) for t in tx[p['payment_id']]); ref = sum(max(0, -t['gross']) for t in tx[p['payment_id']])
        if cap > i['amount'] or ref > cap: return 'over-capture'
        if i['status'] == 'cancelled' and ref != cap: return 'cancelled invoice'
    exp = {i['invoice_id']: dict.fromkeys(FIELDS, 0) for i in ob['invoices']}; sus = dict.fromkeys(FIELDS, 0)
    for t in ob['transactions']:
        b = exp[mp[t['payment_id']]] if t['payment_id'] in mp else sus
        b['captured'] += max(0, t['gross']); b['refunded'] += max(0, -t['gross']); b['fees'] += t['fee']; b['net'] += t['net']
    if len(act['ledger']) != len(inv): return 'ledger rows'
    for r in act['ledger']:
        e = exp[r['invoice_id']]
        for k in FIELDS:
            if r[k] != e[k] or type(r[k]) is not int: return 'ledger ' + k
        if r['remaining_due'] != inv[r['invoice_id']]['amount'] - e['captured'] + e['refunded']: return 'remaining_due'
    if act['suspense'] != sus: return 'suspense'
    bt = sum(b['amount'] for b in ob['bank_credits'])
    if act['bank_total'] != bt or bt != sum(r['net'] for r in act['ledger']) + sus['net']: return 'bank total'
    return None


def run_case(case):
    ob0, truth = case['observation'], case['matches']
    ob = copy.deepcopy(ob0); used = 0
    for _ in range(6):
        out = S.decide(ob, {})['action']
        if out['op'] != 'query': break
        pid = out['payment_id']
        assert all(r['payment_id'] != pid for r in ob['investigations']), 'repeated query'
        ob['investigations'] = ob['investigations'] + [dict(payment_id=pid, verified_invoice_id=truth[pid])]
        ob['queries_remaining'] -= 1; used += 1
        assert used <= 4
    err = validate(ob0, out)
    if err: return 0.0, err, used
    P = prepare(ob0); cap = collections.Counter()
    for t in P['transactions']: cap[t['payment_id']] += max(0, t['gross'])
    mp = {m['payment_id']: m['invoice_id'] for m in out['matches']}
    V = sum(cap[p] for p, i in truth.items() if i); C = sum(cap[p] for p, i in mp.items() if truth[p] == i)
    W = 4 * sum(cap[p] for p, i in mp.items() if truth[p] != i)
    return max(0, 100 * (1 - ((V - C) + W + 180 * used) / V)), None, used


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data', 'training.json')
    cases = json.load(open(path))
    res = [run_case(c) for c in cases]
    print('cases:', len(cases), '| mean score: %.2f' % np.mean([r[0] for r in res]),
          '| integrity failures:', sum(1 for r in res if r[1]), '| avg queries: %.1f' % np.mean([r[2] for r in res]))
