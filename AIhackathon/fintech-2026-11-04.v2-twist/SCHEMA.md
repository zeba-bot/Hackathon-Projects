# Contract

Every call receives the full current observation and your previous JSON state. All money is integer minor units. `invoices` contain invoice_id, merchant, currency, customer_name, tax_suffix, reference, issued_day, amount and status (open/cancelled). `payments` contain payment_id, merchant, currency, channel, sender_name, tax_suffix, source_ref (string/null) and day. Neither reference nor tax/name/date is guaranteed correct identity evidence. There is no fixed hard date cutoff; original remittance verification can resolve a surprising date/name/reference.

`transactions` contain event_id, transaction_id, payment_id, kind (capture/refund), gross, fee, net, parent_transaction_id. Net = gross - fee. Captures have positive gross; refunds negative gross. The same transaction_id may be delivered several times with different event_id; post each transaction once. Financial content on duplicates agrees. Refund parent IDs refer to original captures in the same payment. A payment's multiple captures share one intended invoice; no allocation of one payment across several invoices is required. An invoice accepts at most one payment group. Total captured cannot exceed invoice amount; total refunded cannot exceed captured. A cancelled invoice only accepts a fully reversed payment. Its remaining_due follows the same numerical formula; status controls collection, not arithmetic.

`bank_credits` contain stable bank_id, payment_id and signed amount; delivery retries can repeat a bank_id. Sum each bank_id once. Currency spelling may require trimming and case normalization. Payment membership is trusted. Their sum equals unique transaction net and may include negative refund settlement amounts. Credits may split; never treat them as additional captures. All invoices, all transactions and all bank credits are present at the start. `investigations` initially [], then contains only results you purchased. `queries_remaining` starts at 4. `rules` repeats scoring constants.

Actions:

```json
{"op":"query","payment_id":"pay_..."}
```

This returns a new observation with `{payment_id, verified_invoice_id}` appended to investigations. verified_invoice_id is a ledger ID or null. No other payment's truth is revealed. A maximum of four distinct valid queries is allowed. An unknown ID, repeated query, over-budget query, malformed object or unknown operation terminates with zero. There is no free query/peek/error recovery. At most five calls are needed: four queries, one submit.

```json
{"op":"submit","matches":[{"payment_id":"pay_...","invoice_id":"inv_..."}],"ledger":[{"invoice_id":"inv_...","captured":10000,"refunded":0,"fees":120,"net":9880,"remaining_due":0}],"suspense":{"captured":0,"refunded":0,"fees":0,"net":0},"bank_total":9880}
```

The example is schematic: supply one ledger row for **every** invoice, including all zero balances. Omit unresolved payments from matches, and put all their unique transactions in suspense. No payment or invoice may occur twice in matches. For each invoice sum the unique transactions of its assigned payment: captured=sum(max(gross,0)); refunded=sum(max(-gross,0)); fees=sum(fee); net=sum(net); remaining_due=invoice.amount-captured+refunded. Never change an invoice amount to make a match fit. Unmatched invoices have zero balances and remaining_due=amount. Suspense has exactly captured/refunded/fees/net with analogous sums for unassigned payments. bank_total=sum(bank credit amount)=sum(ledger.net)+suspense.net. All accounting values must be integers; booleans and floats are rejected. No extra action/row keys are accepted. Submission is final.

Diagnostic feedback consists only of aggregate correctly reconciled value, unresolved value, wrong-match loss, review cost/use, total eligible value and integrity failures. V is private until grading. Per-payment truth is withheld on hidden batches. Common lifecycle rules determine which stages contribute to ranking.
