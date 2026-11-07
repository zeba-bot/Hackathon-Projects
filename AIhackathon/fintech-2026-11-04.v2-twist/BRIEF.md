# Historical initial brief

For the revised phase, TWIST.md, RECORDS.md and EVALUATION.md take precedence.

# Payment reconciliation under uncertainty

Build a reconciliation assistant in six working hours. Each batch has 30 invoices, 22 incoming payment groups, noisy processor remittance fields, duplicate transaction deliveries, split captures, occasional refunds/cancellations, and split bank credits. All records are synthetic INR operations. Invoice references in payment feeds can be stale or absent. Two receipts typically have no invoice in this ledger. A matching reference is evidence, never a guaranteed answer.

Choose which payments warrant verified remittance investigation, which payment-to-invoice links to accept, and which to leave unresolved. You may use rules, assignment optimization, statistical models, or another method. Four queries per batch are available; each costs 180 minor units. Queries return a verified invoice ID or null if no invoice exists. They consume a step and cannot be repeated. Then submit one final posting with complete accounting.

The objective is monetary utility, not a prescribed algorithm. Let V be the total gross captured value of payments that truly belong to ledger invoices; C the correctly reconciled gross value; U=V-C; W=4 times the gross value of incorrectly assigned payments (including unrelated receipts); R=180 times queries used. Your batch score is max(0, 100 * (1 - (U+W+R)/V)). Thus a wrong assigned eligible payment contributes both its unresolved value and four times its value as wrong-match loss. Correctly leaving an unrelated payment in suspense adds no U. Refunded payments still require correct original invoice linkage, so gross captured value is the reconciliation value even for full reversals. Batch scores are averaged equally. A truth-informed, zero-query posting reaches 100; no student policy is promised 100 under ambiguous evidence.

Posting integrity is mandatory. Duplicate assignment, exceeding review capacity, wrong balances, cross-merchant/currency posting, invoice over-capture, posting an unreversed payment to a cancelled invoice, malformed action, or failure to conserve all bank/transaction money yields zero for that batch. Correct accounting cannot offset wrong links. Financial fields and schema semantics are reliable; identity hints are uncertain. See SCHEMA.md for exact requirements.

Practice and training contain observations and true payment links, including null. They include realistic uncertainty: some exact references are wrong, hints can conflict, payer families share multiple same-amount invoices, and errors can affect several payments from one sender. These simulations disclose scenario examples, not empirical probabilities. Hidden batches use fresh identities from the same operational setting. No transaction IDs, invoice IDs, input order, or event IDs encode correct links. Query results are the only authoritative identity evidence. Public training and practice need no service or model account.

Run `python3 local_check.py solution.py` before submission. This checks the contract and public practice accounting/outcomes; the organizer alone runs hidden grading. Implement `solution.py:decide(observation,state)` returning `{action: {...}, state: {...}}`. Student state starts empty for every batch. Submit a source solution under the common event rules. All reasoning, library choices, and review-allocation policies are yours.


## Current data version

Use OBSERVATIONS.md for the v6 data layout and interpretation rules. The action schema and domain outcome score remain unchanged. Implement your own runnable preparation and decisions.

## Expanded training and practice (public-expanded-1)

`training.json` contains 60 ordinary development examples; `practice.json` contains 20 different ordinary examples. See DEVELOPMENT.md for source-group counts, commands, smoke tests and baseline results. Use training for fitting/tuning and practice for comparison after tuning. Practice is public; repeatedly tuning on it makes it development data. Portal practice uses these same practice worlds. Official scoring and private cohorts are unchanged.
