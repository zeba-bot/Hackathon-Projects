"""Runnable conservative starting point. Teams may replace every decision rule."""
import re

FIELDS=('captured','refunded','fees','net')


def payment_value(obs,payment_id):
    return sum(max(0,t['gross']) for t in {x['transaction_id']:x for x in obs['transactions']}.values() if t['payment_id']==payment_id)


def candidate_scores(obs,payment):
    value=payment_value(obs,payment['payment_id'])
    tx=[t for t in {x['transaction_id']:x for x in obs['transactions']}.values() if t['payment_id']==payment['payment_id']]
    refunded=sum(max(0,-t['gross']) for t in tx)
    tokens=lambda s:set(re.findall('[a-z0-9]+',s.lower()))
    rows=[]
    for inv in obs['invoices']:
        if (inv['merchant'],inv['currency'])!=(payment['merchant'],payment['currency']):continue
        if inv['amount']<value:continue
        if inv['status']=='cancelled' and refunded!=value:continue
        name=len(tokens(inv['customer_name']) & tokens(payment['sender_name']))
        if not name:continue
        score=2*(inv['amount']==value)+min(2,name)+3*(inv['reference']==payment['source_ref'])+2*(inv['tax_suffix']==payment['tax_suffix'])
        score+=max(0,1-abs(payment['day']-inv['issued_day']-1)/3)
        rows.append((score,inv['invoice_id']))
    return sorted(rows,reverse=True)


def accounting(obs,mapping):
    ledger={i['invoice_id']:dict.fromkeys(FIELDS,0) for i in obs['invoices']}
    suspense=dict.fromkeys(FIELDS,0)
    for t in {x['transaction_id']:x for x in obs['transactions']}.values():
        b=ledger[mapping[t['payment_id']]] if t['payment_id'] in mapping else suspense
        b['captured']+=max(0,t['gross']);b['refunded']+=max(0,-t['gross']);b['fees']+=t['fee'];b['net']+=t['net']
    rows=[]
    for i in obs['invoices']:
        b=ledger[i['invoice_id']]
        rows.append(dict(invoice_id=i['invoice_id'],**b,remaining_due=i['amount']-b['captured']+b['refunded']))
    return dict(op='submit',matches=[dict(payment_id=p,invoice_id=i) for p,i in mapping.items()],ledger=rows,
                suspense=suspense,bank_total=sum(b['amount'] for b in obs['bank_credits']))


def _decide(observation,state):
    mapping={x['payment_id']:x['verified_invoice_id'] for x in observation['investigations'] if x['verified_invoice_id'] is not None}
    used=set(mapping.values());verified={x['payment_id'] for x in observation['investigations']}
    for p in observation['payments']:
        if p['payment_id'] in verified:continue
        options=candidate_scores(observation,p)
        if options and options[0][0]>=6 and (len(options)<2 or options[0][0]-options[1][0]>=3) and options[0][1] not in used:
            mapping[p['payment_id']]=options[0][1];used.add(options[0][1])
    return dict(action=accounting(observation,mapping),state={})


def prepare(observation):
    from copy import deepcopy
    value = deepcopy(observation)
    for payment in value['payments']:
        payment['currency'] = payment['currency'].strip().upper()
    value['transactions'] = list({r['transaction_id']: r for r in value['transactions']}.values())
    value['bank_credits'] = list({r['bank_id']: r for r in value['bank_credits']}.values())
    return value

def decide(observation, state):
    return _decide(prepare(observation), state)
