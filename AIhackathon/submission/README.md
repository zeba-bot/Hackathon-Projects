# Hackmatrix 1.0 - FinTech: payment reconciliation

Files: solution.py (decide), feats.py (cleaning + features), model.json (trained weights).

Pipeline
1. Clean: unpack raw_feed (staged-operations-v1) if present (snapshot filtering, highest revision resolution, decimal-to-paise conversion, backfill payment hints); dedupe transactions by transaction_id and bank credits by bank_id, normalise currency spelling.
2. Candidates: same merchant/currency, invoice amount == captured total; fully reversed payments only on
   cancelled invoices; unreversed payments never on cancelled invoices.
3. Model: conditional logit over (candidate invoices + "no invoice") using reference/tax/name evidence from the
   payment, processor receipt (shared origin) and bank/ERP advice weighted by OCR/template/manual quality,
   plus competition between payments. Trained offline on public training data (weights in model.json).
4. Capacity rescaling so one invoice cannot be claimed by several payments.
5. Decision: match only when P>=0.8 (wrong match costs 5x value, suspense 1x); assignment via Hungarian algorithm.
6. Queries: up to 4, on the payments with the largest expected loss (re-planned after every answer).
7. Posting: full ledger row per invoice, suspense, bank_total; integrity sanitiser drops any unsafe link.
