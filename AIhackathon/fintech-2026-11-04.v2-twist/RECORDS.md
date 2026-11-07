Migrated reconciliation contract (staged-operations-v1)

Invoices, payment roster, INR currency, invoice capacity/cancellation rules and
submit/query schemas remain unchanged. Roster source_ref, tax_suffix and
sender_name are null because remittance evidence now travels only in raw_feed;
the nulls mean unavailable in that roster, not evidence of a missing identity.
transactions, bank_credits and remittance_documents are empty compatibility
containers, not clean alternative feeds. All current economic rows are present
in raw_feed; remittance documents may still be in transit.

raw_feed.events uses raw_feed.columns: source, kind, record_id, revision,
delivery_id, event_clock_minute, received_clock_minute, payload. kind is
transaction, bank_credit or document. Highest revision for the tuple
(source,kind,record_id) is a FULL replacement. Replayed deliveries of that version
must not add money or independent identity evidence. Event list order is not
revision order. delivery_id identifies transport, not a transaction. After
transport reconciliation, post each original transaction_id once and each
bank_id once. Payloads retain original IDs, refund parents and signed economics.
No eligible value, invoice assignment or gold is created or changed by transport.

raw_feed.sources specifies minor_units_per_money_unit and clock_offset_minutes.
For transaction gross/fee/net and bank_credit amount, multiply the exact decimal
payload by minor_units_per_money_unit to obtain integer paise. processor_ledger
uses decimal rupees (factor100); bank_clearing uses integer paise (factor1).
Do not round floating-point approximations into accounting entries. Submission
values must remain integer paise, including negative refunds and signed credits.

Clock minutes are integer minutes since scenario business-day0, not Unix time.
Subtract the source's fixed clock_offset_minutes to obtain business time.
snapshot_business_minute is exclusive. The source day fields in document
payloads retain their original business-day meaning. Feed event clocks encode
that day at midday; economic clocks use payment.day at midday. This is synthetic
transport metadata, not a claim about real bank settlement timing. All economic
batch deliveries arrive before the snapshot. Document delivery occurs at midday
on original received_day plus its source lag: processor_receipt0 days, bank_memo1
day, erp_advice5 days in routine cases or8 in demanding cases. Per-observation
source specs and availability are authoritative. A document whose delivery is
not before snapshot is absent; changing future documents cannot affect current
evidence. Missing or delayed advice means UNKNOWN, not no match.

Document payload document_id/revision/status/lineage describe the original
remittance evidence, separately from transport record_id/revision. Existing
frozen source documents are used unchanged when supplied. Only active source
versions are current evidence; void/superseded versions are history. A bank memo
may copy ERP advice; shared lineage is correlated, never an independent vote.
OCR confidence measures legibility, not correctness. Neither the newest
transport revision, an active document nor any unverified reference proves a
match. Captured payment/receipt fields share one origin. Existing noisy names,
references and tax suffixes remain noisy; source metadata does not make them
verified. Fallback receipt documents only re-express provided captured fields.

Query actions remain {op:'query',payment_id:...}, at most FOUR distinct valid
payments, each costing180 paise of utility. Only that purchased payment's
verified_invoice_id (or null) is added to investigations. Querying does not move
the snapshot, release delayed records or refresh other payments. A duplicate,
unknown or fifth query terminates with zero. Submit uses the unchanged exact
matches/ledger/suspense/bank_total schema. Unresolved payments belong in suspense;
there is at most one payment per invoice. All money must conserve against the
recovered complete economic feed. All-in-suspense is legal but earns no matching
credit. At most four queries and one submit are needed.

Utility is unchanged: max(0,100*(1-(unresolved eligible value +4*wrongly assigned
payment value +180*reviews_used)/total eligible value)); invalid submissions
score0. No arbitrary tie-breaker. Ledger reconciliation remains a hard integrity
requirement. Four reviews cannot verify all22 receipts; allocate them according
to value, ambiguity and assignment conflicts. Initial scoring is unchanged.
Historical excerpts are partial, unlabelled and not runnable complete cases;
omitted payments/rows/documents are unknown. No labelled post practice is given.
