# Observation guide — frozen v6 rehearsal

Submit solution.py with decide(observation, state), returning action and state.
Preparation, feature engineering and decisions belong in that runnable pipeline.
You may compare algorithms and use any causal strategy consistent with the action
schema. Source examples and local checks are development aids;
only portal submissions reveal validation performance. Final results stay private
to organizers. See EVENT_RULES.md for limits, schedule and 20/30/50 phase weights.

Reconcile invoices, payments, refunds, fees and bank postings with limited investigation calls.
remittance_documents add document_id, payment_id, source, lineage, event_day, received_day,
revision, status, reference, tax_suffix and sender_name, plus quality hints. Only as-of evidence
is present. A newer delivery is not necessarily a semantic revision. An active document may be
wrong. The raw payment, its processor receipt and copied lineage share an evidence origin;
their agreement is not independent support. Unknown quality hints are not correctness labels.
Normalize currency spelling. Deduplicate transactions by transaction_id and bank credits by
bank_id, never by amount. Preserve distinct transactions, refunds, splits and their economics.
Choose evidence, abstention and query strategies; submit matches and complete ledger/suspense
postings using the original action schema. Public examples include match labels for local
experiments. These are fictional events and scenario error rates, not measured banking failures.
