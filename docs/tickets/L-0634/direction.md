# The wave refuses a ticket whose built-against contract hash no longer matches

Split from T-0031 (2026-10-04 size check). Filed as L-0634.

Status: direction inherited. The owner approved the parent direction on 2026-09-25; the independent review recorded there says a hash mismatch "refuses the wave, mechanically ... not only a prose stop".

## Scope
T-0031 records, per ticket, which contract version and hash this side built against. This slice adds the check: `crew_contract.py verify --ticket <id>` compares each local binding with the channel, and the wave calls the same check before it treats a ticket as eligible. A mismatch refuses the ticket. A channel or record that cannot be read is `unknown` and also refuses it.

## Why it is a separate ticket
It is the one guard in the parent scope, and it needs both T-0031's record and T-0029's wave. Keeping it apart leaves T-0031 with a single parser and lets the record land before the wave does.

## Options
- A (recommended, taken). One function, `check_bindings(root, ticket)`, in `crew_contract.py`; the `verify` command and `crew_wave._judge` both call it.
- B. Check only inside the wave. Rejected: a session working one ticket without a wave would have no way to ask.
- C. Compare against the channel's `built_by` only. Rejected: a peer that rewrites the body can rewrite `built_by` too; the local binding is the independent copy.

## Questions answered with the recommended option (owner not available 2026-10-04)
1. Does a ticket with no bindings file get checked? Taken: no, and no fetch is made for it.
2. Is a newer version existing on the channel a refusal? Taken: no. Only a change to the version this ticket is bound to refuses; a newer draft is reported as information.
