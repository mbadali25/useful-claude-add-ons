# L-0634 plan: the wave refuses a ticket whose built-against contract moved          spec: docs/tickets/L-0634/spec.md

Written by the implementing session (rush lane g3c-contracts, 2026-10-05) on top of T-0031 and
L-0633 from this lane, over T-0029/T-0030 as ported by rush g0. The record and binding formats are
read from the landed `crew_contract.py` (`parse_record`, `read_bindings`, `scan`/`versions`), not
from the spec's quotes; `_judge` in `crew_wave.py` is re-found by content (it now takes L-0633's
`channels` cache).

### Step 1: `check_bindings` and `verify` in crew_contract.py
Files: plugin/crew/hooks/scripts/crew_contract.py, plugin/crew/tests/test_crew_contract_verify.py
Test: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_contract_verify.py plugin/crew/tests/test_crew_contract.py plugin/crew/tests/test_crew_wave.py -q`
Risk: high. A binding read as current when it cannot be told would start a lane on a moved interface.
- [ ] `check_bindings(top, ticket, read=None, remote=None)`: no `contracts.json` is ok with no fetch;
  an unreadable one is unknown. Per binding, on its fetched channel: the version's files and a
  parseable record (else unknown), then the record's hash equals the binding's, the body's sha256
  equals the record's hash, status `built-against`, and `(repo, ticket, hash)` in `built_by`
  (else mismatch). A newer version is an information suffix. Mismatch outranks unknown.
- [ ] `read` is a `channel_reader` (`coord.remote`, default origin, each channel fetched once) or
  the wave's own cache; `verify --ticket <id>` prints one `[peer-written]` line per binding and
  exits 0 / 1 / 3. Usage is checked before any git call.

### Step 2: the wave
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_contract_verify.py
Test: as Step 1
Risk: high.
- [ ] `_judge` calls `_contract_refusal` after `_dep_refusal`, through the plan's channel cache; its
  reason is the check's first refusal, so `plan_text` prints `refused: contract <n> v<N> changed
  since <id> built against it (...)` or `refused: contract <n> v<N> unknown (...)`, and `start`
  launches no lane for it. Other tickets are judged as before.

### Step 3: docs, verify rules
Files: plugin/crew/README.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/crew-troubleshooting.html, docs/guides/crew/crew-troubleshooting.docx, docs/guides/crew/crew-troubleshooting.pdf, .crew/verify.json, .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: `python3 scripts/check-tooling-pr.py`; `python3 scripts/check-marketplace.py` after the commit
Risk: low.
- [ ] README: `verify` and the wave refusal; troubleshooting: the refusal lines and the owner's way
  out; rebuilt with `python3 docs/guides/crew/src/build.py --guide troubleshooting`.
- [ ] The new test file joins the contract rule and the wave rule in `.crew/verify.json`.
