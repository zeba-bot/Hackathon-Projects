"""Payment reconciliation assistant (Hackmatrix 1.0, FinTech).

Pipeline: clean raw observation -> candidate invoices per payment -> conditional-logit
match probabilities (weights in model.json) -> capacity-constrained rescaling so an
invoice is not over-claimed -> expected-utility assignment (match only when P>0.8,
because a wrong match costs 5x its value and suspense costs 1x) -> spend the
verified-remittance queries on the payments with the largest expected loss ->
balanced posting with ledger/suspense/bank totals.
"""
import json
import math
import os

import numpy as np

import sys
_D = os.path.dirname(os.path.abspath(__file__))
if _D not in sys.path:
    sys.path.insert(0, _D)
try:
    from feats import (FIELDS, PAIR_NAMES, NULL_NAMES, prepare, build_context,
                       candidates, pair_features, null_features)
except ImportError:  # imported as a package module
    from .feats import (FIELDS, PAIR_NAMES, NULL_NAMES, prepare, build_context,
                        candidates, pair_features, null_features)

QUERY_COST = 180
WRONG_MULT = 4

_HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = {'sinkhorn_iters': 30, 'match_threshold': 0.84, 'query_min_gain': 1.0, 'query_mode': 'greedy'}
_MODEL = None


def load_model(path=None):
    global _MODEL
    if _MODEL is None or path:
        with open(path or os.path.join(_HERE, 'model.json')) as fh:
            m = json.load(fh)
        _MODEL = (np.array([m['pair'][n] for n in PAIR_NAMES]), np.array([m['null'][n] for n in NULL_NAMES]))
    return _MODEL


def set_model(wp, wn):
    global _MODEL
    _MODEL = (np.asarray(wp, float), np.asarray(wn, float))


# ---------------------------------------------------------------- probabilities
def raw_scores(ob, ctx, skip):
    """Softmax over (candidate invoices + 'no invoice') for every payment not in skip."""
    wp, wn = load_model()
    cands, raw = {}, {}
    for p in ob['payments']:
        pid = p['payment_id']
        if pid in skip:
            continue
        cs = candidates(ob, ctx, p)
        rows = [pair_features(ob, ctx, p, i, cs) for i in cs]
        g = null_features(ob, ctx, p, cs, rows)
        s = np.array([float(np.dot(r, wp)) for r in rows] + [float(np.dot(g, wn))])
        s -= s.max()
        e = np.exp(s)
        raw[pid] = e / e.sum()
        cands[pid] = [i['invoice_id'] for i in cs]
    return raw, cands


def match_probabilities(ob, ctx, investigations, cache=None, forced=None):
    """Return (probs, nullp, cands): probs[pid]={inv_id: P(match)}, nullp[pid]=P(no invoice).

    investigations: purchased truths; forced: extra hypothetical truths {pid: inv_id|None}."""
    verified = {r['payment_id']: r['verified_invoice_id'] for r in investigations}
    if forced:
        verified = dict(verified, **forced)
    claimed = {v for v in verified.values() if v is not None}
    raw, cands = cache if cache is not None else raw_scores(ob, ctx, set())
    probs, nullp = {}, {}
    for pid in raw:
        if pid in verified:
            continue
        keep = [k for k, iid in enumerate(cands[pid]) if iid not in claimed]
        v = raw[pid]
        sub = np.array([v[k] for k in keep] + [v[-1]])
        sub = sub / sub.sum()
        probs[pid] = {cands[pid][k]: float(sub[a]) for a, k in enumerate(keep)}
        nullp[pid] = float(sub[-1])
    # capacity: an invoice can host only one payment -> scale over-subscribed columns, renormalise rows
    for _ in range(PARAMS['sinkhorn_iters']):
        col = {}
        for pid, d in probs.items():
            for iid, q in d.items():
                col[iid] = col.get(iid, 0.0) + q
        changed = False
        for pid, d in probs.items():
            for iid in d:
                if col[iid] > 1.0 + 1e-9:
                    d[iid] /= col[iid]; changed = True
            tot = sum(d.values()) + nullp[pid]
            for iid in d:
                d[iid] /= tot
            nullp[pid] /= tot
        if not changed:
            break
    return probs, nullp, cands


def gross_value(ctx, pid):
    return ctx['cap'][pid]


def choose_matches(ob, ctx, probs, nullp):
    """Expected-utility assignment: gain of matching p to i is v*(5q-4); each invoice/payment once."""
    from scipy.optimize import linear_sum_assignment
    pids = list(probs)
    inv_ids = sorted({i for d in probs.values() for i in d})
    if not pids or not inv_ids:
        return {}
    thr = PARAMS['match_threshold']
    gain = np.zeros((len(pids), len(inv_ids)))
    ix = {i: k for k, i in enumerate(inv_ids)}
    for a, pid in enumerate(pids):
        v = gross_value(ctx, pid)
        for iid, q in probs[pid].items():
            g = v * (5 * q - 4) + 1e-6 * q
            if q >= thr and g > 0:
                gain[a, ix[iid]] = g
    r, c = linear_sum_assignment(-gain)
    return {pids[a]: inv_ids[b] for a, b in zip(r, c) if gain[a, b] > 0}


def expected_costs(ctx, probs, nullp, chosen):
    """Expected monetary loss per unresolved payment under the current decision."""
    out = {}
    for pid, d in probs.items():
        v = gross_value(ctx, pid)
        n = nullp[pid]
        if pid in chosen:
            q = d.get(chosen[pid], 0.0)
            out[pid] = v * (5 * (1 - n - q) + 4 * n)
        else:
            out[pid] = v * (1 - n)
    return out


def total_cost(ob, ctx, probs, nullp):
    chosen = choose_matches(ob, ctx, probs, nullp)
    return sum(expected_costs(ctx, probs, nullp, chosen).values())


def pick_query(ob, ctx, inv, cache, probs, nullp, chosen):
    """One-step lookahead value of information; returns payment id or None if no query pays for itself."""
    if PARAMS.get('query_mode') == 'greedy':
        ec = expected_costs(ctx, probs, nullp, chosen)
        pid = max(ec, key=lambda k: (ec[k], k))
        return pid if ec[pid] > QUERY_COST * PARAMS['query_min_gain'] else None
    base = sum(expected_costs(ctx, probs, nullp, chosen).values())
    best, best_gain = None, QUERY_COST * PARAMS['query_min_gain']
    for pid in sorted(probs):
        exp_after = 0.0
        outcomes = list(probs[pid].items()) + [(None, nullp[pid])]
        for iid, pr in outcomes:
            if pr < 1e-6:
                continue
            p2, n2, _ = match_probabilities(ob, ctx, inv, cache, forced={pid: iid})
            exp_after += pr * total_cost(ob, ctx, p2, n2)
        gain = base - exp_after
        if gain > best_gain:
            best, best_gain = pid, gain
    return best


# ---------------------------------------------------------------- accounting
def accounting(ob, mapping):
    ledger = {i['invoice_id']: dict.fromkeys(FIELDS, 0) for i in ob['invoices']}
    suspense = dict.fromkeys(FIELDS, 0)
    for t in ob['transactions']:
        b = ledger[mapping[t['payment_id']]] if t['payment_id'] in mapping else suspense
        b['captured'] += max(0, t['gross']); b['refunded'] += max(0, -t['gross'])
        b['fees'] += t['fee']; b['net'] += t['net']
    rows = []
    for i in ob['invoices']:
        b = ledger[i['invoice_id']]
        rows.append(dict(invoice_id=i['invoice_id'], captured=int(b['captured']), refunded=int(b['refunded']),
                         fees=int(b['fees']), net=int(b['net']),
                         remaining_due=int(i['amount'] - b['captured'] + b['refunded'])))
    return dict(op='submit',
                matches=[dict(payment_id=p, invoice_id=i) for p, i in mapping.items()],
                ledger=rows,
                suspense={k: int(v) for k, v in suspense.items()},
                bank_total=int(sum(b['amount'] for b in ob['bank_credits'])))


def sanitize(ob, ctx, mapping):
    """Drop any link that could break an integrity rule (never lose a whole batch)."""
    inv = ctx['inv_by_id']
    pays = {p['payment_id']: p for p in ob['payments']}
    out, used = {}, set()
    for pid, iid in mapping.items():
        if pid not in pays or iid not in inv or iid in used:
            continue
        p, i = pays[pid], inv[iid]
        cap, ref = ctx['cap'][pid], ctx['ref'][pid]
        if p['merchant'] != i['merchant'] or p['currency'] != i['currency']:
            continue
        if cap > i['amount'] or ref > cap:
            continue
        if i['status'] == 'cancelled' and not (cap > 0 and ref == cap):
            continue
        out[pid] = iid; used.add(iid)
    return out


# ---------------------------------------------------------------- entry point
def _decide(observation):
    ob = prepare(observation)
    ctx = build_context(ob)
    inv = list(ob.get('investigations', []))
    cache = raw_scores(ob, ctx, set())
    probs, nullp, cands = match_probabilities(ob, ctx, inv, cache)
    chosen = choose_matches(ob, ctx, probs, nullp)
    if observation.get('queries_remaining', 0) > 0 and probs:
        pid = pick_query(ob, ctx, inv, cache, probs, nullp, chosen)
        if pid is not None:
            return dict(op='query', payment_id=pid)
    mapping = {r['payment_id']: r['verified_invoice_id'] for r in inv if r['verified_invoice_id'] is not None}
    mapping.update(chosen)
    return accounting(ob, sanitize(ob, ctx, mapping))


def decide(observation, state):
    try:
        action = _decide(observation)
    except Exception:  # last-resort safe posting: everything in suspense, no queries
        ob = prepare(observation)
        action = accounting(ob, {})
    return dict(action=action, state={})
