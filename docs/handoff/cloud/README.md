# Cloud handoff (temporary)

## Cleanup (required)

- When a ticket's PR merges (or the ticket is closed or dropped), delete its `docs/handoff/cloud/T-NNNN.md` and its row below in that same PR.
- When the last ticket is done, delete `docs/handoff/cloud/` entirely, and remove any link to it, in the final PR.
- These notes are temporary scaffolding, not documentation: never extend them and never cite them from other docs.

## What this is

On 2026-09-30 the owner moved these tickets from the local orchestration session to a cloud session. `.work/` is gitignored,
so each ticket's direction, spec and plan are copied in full into its file here. Local lanes will not pick these tickets up.
Pick them up in the order below: tickets closest to landing first, then the rest.

| Order | Ticket | INDEX status | Phase | Branch | Draft PR |
|---|---|---|---|---|---|
| 1 | [T-0503](T-0503.md) - bitbucket skill: trailing-slash variables endpoints, access tokens are UI-only (and the ro | in-progress | Implement done; refresh-check waiver being applied when stopped | `T-0503-build` | #270 |
| 2 | [T-0504](T-0504.md) - crew stops asking the owner to run its own bookkeeping commands (crew_ticket.py activate a | in-progress | Implement done - Review round 1 was starting | `T-0504-build` | #271 |
| 3 | [T-0501](T-0501.md) - crew_instructions.py rules warns (or refuses) when generating .claude/rules from codemaps  | in-progress | Review round 1 complete (FINDINGS) - Fix next | `T-0501-build` | #272 |
| 4 | [T-0107](T-0107.md) - gizmoduck routine CLI: headless checkov/trivy/dependency-check/semgrep/zap/testssl/nmap/ni | in-progress | Fix after review round 1 (in progress) | `T-0107-build` | #273 |
| 5 | [T-0104](T-0104.md) - webtest scaffold for multi-module repos: detect modules, honour testDir, close the gaps it | approved | Implement (in progress when stopped) | `T-0104-build` | #274 |
| 6 | [T-0500](T-0500.md) - crew init after migrate re-offers phases whose definition changed since marked done, and a | approved | Implement (in progress) | `T-0500-build` | #275 |
| 7 | [T-0507](T-0507.md) - Refresh the 7 code maps (crew, install-scripts, localgpu, marketplace-registration, obsidi | direction | Direction (seed, not approved) | none | none - not started |
| 8 | [T-0502](T-0502.md) - crew-setup _verify diagrams case renders as root (puppeteer --no-sandbox when EUID=0) and  | direction | Direction (seed, not approved) | none | none - not started |
| 9 | [T-0505](T-0505.md) - PULLED BACK LOCAL 2026-09-30, cloud must not work it - promote-gate judges the main checkout | in-progress (local) | owned by the local lane | `T-0505-promote-gate-cwd` | local lane's PR |
| 10 | [T-0506](T-0506.md) - concurrent pwsh runs corrupt the shared ~/.cache/powershell startup profile; every later p | direction | Direction (seed, not approved) | none | none - not started |
| 11 | [T-0105](T-0105.md) - crew_migrate maps a 0.20 autopilot key to 1.0's top-level autopilot instead of unmapped.au | direction | Direction (seed, not approved) | none | none - not started |
| 12 | [T-0106](T-0106.md) - crew_autoclear_setup apply-migrate --scan-root finds every repo with autoClear.enabled for | direction | Direction (seed, not approved) | none | none - not started |

Version: bump crew one past whatever version main holds when this ticket lands (main moves; T-0501 #272 and T-0504 #271 both claim 1.0.70, which main now already holds).
