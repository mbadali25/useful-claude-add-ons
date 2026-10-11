# L-0789 self-check
<!-- stamp: bundle=f7367b2a5e2020e5f9760b512d9aa01799bd36ece8be55ab597d6c1b3c876f81 standards=baeb336870ce3b4e1123df93ba56574e6ffb64c7132c2b446d4314b0610bd993 base=987ea4fb89087bfe35fcc5f2883ba37fd69d26ba -->

standards: 15 in sets GEN, REPO; overlay: present (.crew/standards.md); digest baeb3368

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | n/a | no code path is added; the diagrams' own unknowns stay in their notes (the WHAT CREW 1.0 CHANGED block is marked history, not re-measured) |
| GEN-02 | n/a | no shared runtime file is written; generated pages were written by diagram_doc.py and crew_diagrams.py embed, unchanged tools |
| GEN-03 | n/a | no irreversible action is added |
| GEN-04 | n/a | no behaviour changes; text and generated docs only |
| GEN-05 | n/a | no parser or allowlist changes |
| GEN-06 | n/a | no sink changes |
| GEN-07 | addressed | the .mmd is the one source; docs/diagrams/README.md, index.html and plugin/crew/README.md regenerated from it; crew_diagrams.py check --root . reads fresh |
| GEN-08 | addressed | both .mmd written with newline=LF (file(1) shows no CRLF); no script changes |
| GEN-09 | addressed | every count and line number in the ratchet part's Note lines re-taken at 987ea4fb by import (ALL_GUARD_NAMES 12, RATCHETED_KEYS 15, _RATCHETED 16) and grep -n (crew_guards.py:551-578, :593, :478, :504, :518; crew_config.py:1006, :1050, :1095, :3182-3315; role_write_guard.py:761-768) |
| GEN-10 | addressed | counts measured by importing crew_guards and crew_config in this worktree, not read from prose; render.sh 74 ok and diagram_check.py PASS for both diagrams |
| GEN-11 | addressed | both diagrams' headers name 987ea4fb; crew_refresh_check.py --ticket L-0789 no longer lists either diagram |
| GEN-12 | addressed | checks re-run on the committed HEAD; verify-gate.sh --all run on the same sha through heavy-run |
| REPO-01 | n/a | no identity, id or key handling changes |
| REPO-02 | n/a | no change detector changes |
| REPO-03 | addressed | crew 1.2.31 in plugin.json, marketplace.json and plugin/PLUGINS.md; CHANGELOG entry; sync-updates.py --check current; check-marketplace.py all checks passed after the commit |
