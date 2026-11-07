"""Test post-twist raw_feed ingestion and end-to-end decision performance."""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'submission'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import solution as S
from feats import prepare
from local_eval import validate, run_case


def convert_to_raw_feed(ob_orig):
    """Synthesize post-twist staged-operations-v1 raw_feed from pre-twist observation."""
    ob = copy.deepcopy(ob_orig)
    sources = {
        'processor_ledger': {'minor_units_per_money_unit': 100, 'clock_offset_minutes': 15},
        'bank_clearing': {'minor_units_per_money_unit': 1, 'clock_offset_minutes': 0},
        'bank_memo': {'minor_units_per_money_unit': 1, 'clock_offset_minutes': 0},
        'erp_advice': {'minor_units_per_money_unit': 1, 'clock_offset_minutes': 0},
        'processor_receipt': {'minor_units_per_money_unit': 100, 'clock_offset_minutes': 15}
    }
    columns = ['source', 'kind', 'record_id', 'revision', 'delivery_id', 'event_clock_minute', 'received_clock_minute', 'payload']
    events = []

    # 1. Transactions -> processor_ledger (decimal rupees: factor 100)
    for idx, t in enumerate(ob['transactions']):
        # convert integer paise to decimal rupees string
        payload = {
            'transaction_id': t['transaction_id'],
            'payment_id': t['payment_id'],
            'kind': t['kind'],
            'gross': t['gross'] / 100.0,
            'fee': t['fee'] / 100.0,
            'net': t['net'] / 100.0,
            'parent_transaction_id': t.get('parent_transaction_id')
        }
        # Add a revision 1 delivery
        events.append(['processor_ledger', 'transaction', t['transaction_id'], 1, f'del_tx_{idx}_v1', 720, 735, payload])
        # Add a replay delivery of revision 1 (transport retry)
        events.append(['processor_ledger', 'transaction', t['transaction_id'], 1, f'del_tx_{idx}_replay', 720, 740, payload])

    # 2. Bank credits -> bank_clearing (integer paise: factor 1)
    for idx, b in enumerate(ob['bank_credits']):
        payload = {
            'bank_id': b['bank_id'],
            'payment_id': b['payment_id'],
            'amount': b['amount']
        }
        events.append(['bank_clearing', 'bank_credit', b['bank_id'], 1, f'del_bk_{idx}', 800, 800, payload])

    # 3. Documents
    for idx, d in enumerate(ob['remittance_documents']):
        src = d['source']
        payload = copy.deepcopy(d)
        events.append([src, 'document', d['document_id'], d.get('revision', 1), f'del_doc_{idx}', 720, 720, payload])

    # 4. Add a dummy future event that arrives past snapshot
    snapshot_business_minute = 5000
    events.append(['bank_clearing', 'bank_credit', 'future_bank_credit', 1, 'del_future', 6000, 6000, {'bank_id': 'future_bank', 'amount': 999999}])

    # Strip legacy containers
    ob['raw_feed'] = {
        'columns': columns,
        'sources': sources,
        'snapshot_business_minute': snapshot_business_minute,
        'events': events
    }
    ob['transactions'] = []
    ob['bank_credits'] = []
    ob['remittance_documents'] = []
    for p in ob['payments']:
        p['source_ref'] = None
        p['tax_suffix'] = None
        p['sender_name'] = None

    return ob


def test_twist():
    cases = json.load(open(os.path.join(ROOT, 'data', 'smoke.json')))
    for i, c in enumerate(cases):
        orig_ob = copy.deepcopy(c['observation'])
        twisted_ob = convert_to_raw_feed(orig_ob)

        # Test preparation
        prep = prepare(twisted_ob)
        assert len(prep['transactions']) == len(set(t['transaction_id'] for t in orig_ob['transactions'])), f"Transaction count mismatch: {len(prep['transactions'])} vs {len(orig_ob['transactions'])}"
        assert len(prep['bank_credits']) == len(set(b['bank_id'] for b in orig_ob['bank_credits'])), f"Bank credits count mismatch: {len(prep['bank_credits'])} vs {len(orig_ob['bank_credits'])}"
        
        # Verify integer paise conservation
        sum_net = sum(t['net'] for t in prep['transactions'])
        sum_bank = sum(b['amount'] for b in prep['bank_credits'])
        assert sum_net == sum_bank, f"Money conservation failed: net {sum_net} != bank {sum_bank}"

        # Test end-to-end run
        twisted_case = {'observation': twisted_ob, 'matches': c['matches']}
        score, err, used = run_case(twisted_case)
        print(f"Case {i}: score={score:.2f}, error={err}, queries={used}")
        assert err is None, f"Encountered integrity error: {err}"
        assert score > 90.0, f"Score too low: {score}"

    print("\nALL TWIST TESTS PASSED SUCCESSFULLY!")


if __name__ == '__main__':
    test_twist()

