"""Public practice runner: no hidden evaluator or generator dependency."""
import importlib.util
import json
from pathlib import Path
import sys


def expected_posting(obs,mapping):
    fields=('captured','refunded','fees','net')
    balances={i['invoice_id']:dict.fromkeys(fields,0) for i in obs['invoices']}
    suspense=dict.fromkeys(fields,0)
    for t in {x['transaction_id']:x for x in obs['transactions']}.values():
        row=balances[mapping[t['payment_id']]] if t['payment_id'] in mapping else suspense
        row['captured']+=max(0,t['gross']);row['refunded']+=max(0,-t['gross']);row['fees']+=t['fee'];row['net']+=t['net']
    return dict(op='submit',matches=[dict(payment_id=p,invoice_id=i) for p,i in mapping.items()],
                ledger=[dict(invoice_id=i['invoice_id'],**balances[i['invoice_id']],remaining_due=i['amount']-balances[i['invoice_id']]['captured']+balances[i['invoice_id']]['refunded']) for i in obs['invoices']],
                suspense=suspense,bank_total=sum(b['amount'] for b in {r['bank_id']: r for r in obs['bank_credits']}.values()))


def main():
    path=Path(sys.argv[1] if len(sys.argv)>1 else 'solution.py')
    spec=importlib.util.spec_from_file_location('participant_solution',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    examples=json.loads((Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).with_name('practice.json')).read_text())
    for index,item in enumerate(examples):
        obs=item['observation'];student={};queries=[]
        for _ in range(6):
            response=module.decide(obs,student)
            assert set(response)=={'action','state'}, 'response must contain action and state'
            action=response['action'];student=response['state']
            if action['op']=='query':
                assert set(action)=={'op','payment_id'}, 'query schema'
                pid=action['payment_id'];assert pid in item['matches'] and pid not in queries and len(queries)<4
                queries.append(pid);obs['queries_remaining']-=1
                obs['investigations'].append(dict(payment_id=pid,verified_invoice_id=item['matches'][pid]))
                continue
            assert action['op']=='submit'
            mapping={m['payment_id']:m['invoice_id'] for m in action['matches']}
            assert len(mapping)==len(action['matches']) and len(set(mapping.values()))==len(mapping)
            expected=expected_posting(obs,mapping)
            assert set(action)==set(expected),'Submission keys differ from contract'
            # Ledger order is unrestricted; all other content is exact.
            assert sorted(action['ledger'],key=lambda r:r['invoice_id'])==sorted(expected['ledger'],key=lambda r:r['invoice_id']),'Ledger differs from unique source totals'
            assert all(action[k]==expected[k] for k in ('op','matches','suspense','bank_total')),'Accounting differs from unique source totals'
            for row in action['ledger']:
                assert all(isinstance(v,int) and not isinstance(v,bool) for k,v in row.items() if k!='invoice_id'),'Integer money required'
            assert all(isinstance(v,int) and not isinstance(v,bool) for v in action['suspense'].values())
            assert isinstance(action['bank_total'],int) and not isinstance(action['bank_total'],bool)
            inv={i['invoice_id']:i for i in obs['invoices']}
            pay={p['payment_id']:p for p in obs['payments']}
            for m in action['matches']:
                assert pay[m['payment_id']]['merchant']==inv[m['invoice_id']]['merchant']
                assert pay[m['payment_id']]['currency'].strip().upper()==inv[m['invoice_id']]['currency']
            for r in action['ledger']:
                i=inv[r['invoice_id']]
                assert r['captured']<=i['amount'] and r['refunded']<=r['captured']
                assert i['status']!='cancelled' or r['captured']==r['refunded']
            assert action['bank_total']==sum(r['net'] for r in action['ledger'])+action['suspense']['net']
            unique={t['transaction_id']:t for t in obs['transactions']}
            values={p:sum(max(0,t['gross']) for t in unique.values() if t['payment_id']==p) for p in item['matches']}
            total=sum(values[p] for p,i in item['matches'].items() if i is not None)
            correct=sum(values[p] for p,i in item['matches'].items() if i is not None and mapping.get(p)==i)
            wrong=4*sum(values[p] for p,i in mapping.items() if item['matches'][p]!=i)
            score=max(0,100*(1-(total-correct+wrong+180*len(queries))/total))
            print(json.dumps(dict(practice=index,score=round(score,4),reviews=len(queries),correct_value=correct,unresolved_value=total-correct,wrong_loss=wrong)))
            break
        else:raise AssertionError('No final submission')

if __name__=='__main__':main()
