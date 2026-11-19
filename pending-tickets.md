# Pending tickets

The fresh queue, created 2026-11-18 from the approved crew revamp plan
(`docs/plans/crew-revamp-2026-11-18.md`, revision 3). One file per ticket in `docs/tickets/pending/`,
named by ticket id. The previous backlog was cleared the same day (`docs/tickets/CLEARED-2026-11-18.md`);
it remains in git history at parent commit `5558cac9cbe67525d26db3733d9695efa5126c29`.

Status values: `READY` (no open dependency), `blocked: <ids>`, `in progress`, `in review (PR #n)`,
`done (PR #n)`. Dependencies on the owner decisions O1 to O6 count as met: all six were approved on
2026-11-18. A ticket may start when every ticket in its Depends column has landed; phases are delivery
groups, not barriers (plan section 6, "Order"). **H** marks a harness ticket: its PR lands alone.

Ticket count: 102. Re-measure with `ls docs/tickets/pending | wc -l`.

## Ready now

Start order, foundations first: the measurements and the two tickets everything else leans on
(R-01, R-04, R-06, R-07), the configuration-guide registry (R-C1), then the independent harness
repairs and the rest.

| # | Ticket | Title | Size | Model | Harness | Phase |
|---|---|---|---|---|---|---|
| 1 | [R-04](docs/tickets/pending/R-04.md) | `crew_paths.py`: machine-owned roots and the deletion helper | M | Opus 5.5 |  | 0 |
| 2 | [R-06](docs/tickets/pending/R-06.md) | Measure what a crew-launched headless run reports as the answering model and whether a fallback shows; exercise the direct API path and its response metadata too | S | Fable 5.2 |  | 0 |
| 3 | [R-07](docs/tickets/pending/R-07.md) | Measure the two attestation forms: an owner-presence signing key on Windows and Linux, and a forge review by the owner while agents use a separate account | S | Fable 5.2 |  | 0 |
| 4 | [R-02](docs/tickets/pending/R-02.md) | Reproduce the host damage in a disposable VM with write auditing | M | Opus 5.5 |  | 0 |
| 5 | [R-05](docs/tickets/pending/R-05.md) | Machine-owned tier map, report-only | S | Opus 5.5 |  | 0 |
| 6 | [R-10](docs/tickets/pending/R-10.md) | Provider registry; one probe per attempt | M | Opus 5.5 | H | 1 |
| 7 | [R-20](docs/tickets/pending/R-20.md) | Store tripwire stops refusing everyday commands | S | Opus 5.5 | H | 2 |
| 8 | [R-21](docs/tickets/pending/R-21.md) | ADR and measurement: is a blocked prompt's hook text shown; does a plain reply arrive unchanged | S | Fable 5.2 |  | 2 |
| 9 | [R-03](docs/tickets/pending/R-03.md) | Capture one refused IAM write and one refused dispatch | S | Haiku 5.5 |  | 0 |
| 10 | [R-3B](docs/tickets/pending/R-3B.md) | CLAUDE.md wording for O1 | S | Sonnet 5.5 |  | 4 |
| 11 | [R-42](docs/tickets/pending/R-42.md) | Backup evidence, first provider (AWS RDS snapshots) | M | Opus 5.5 |  | 7 |
| 12 | [R-54](docs/tickets/pending/R-54.md) | Scope guard allowance for the active ticket's handoff file | S | Opus 5.5 | H | 8 |
| 13 | [R-70](docs/tickets/pending/R-70.md) | `crew_triage.py` | S | Sonnet 5.5 |  | 10 |
| 14 | [R-72](docs/tickets/pending/R-72.md) | Status maps and event ids for all four trackers | M | Opus 5.5 |  | 10 |

## All tickets by phase

### Phase 0 — Find out, lay foundations (no behaviour change)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-01](docs/tickets/pending/R-01.md) | `crew_policy.py` decision table, report-only, with `explain` | M | Opus 5.5 |  | — | done (PR #794) |
| [R-02](docs/tickets/pending/R-02.md) | Reproduce the host damage in a disposable VM with write auditing | M | Opus 5.5 |  | — | READY |
| [R-03](docs/tickets/pending/R-03.md) | Capture one refused IAM write and one refused dispatch | S | Haiku 5.5 |  | — | READY |
| [R-04](docs/tickets/pending/R-04.md) | `crew_paths.py`: machine-owned roots and the deletion helper | M | Opus 5.5 |  | — | READY |
| [R-05](docs/tickets/pending/R-05.md) | Machine-owned tier map, report-only | S | Opus 5.5 |  | — | READY |
| [R-06](docs/tickets/pending/R-06.md) | Measure what a crew-launched headless run reports as the answering model and whether a fallback shows; exercise the direct API path and its response metadata too | S | Fable 5.2 |  | — | READY |
| [R-07](docs/tickets/pending/R-07.md) | Measure the two attestation forms: an owner-presence signing key on Windows and Linux, and a forge review by the owner while agents use a separate account | S | Fable 5.2 |  | — | READY |

### Phase 1 — Reviewer-family neutrality

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-10](docs/tickets/pending/R-10.md) | Provider registry; one probe per attempt | M | Opus 5.5 | H | — | READY |
| [R-11](docs/tickets/pending/R-11.md) | Neutral labels and notes; old spellings read | S | Sonnet 5.5 | H | R-10 | blocked: R-10 |
| [R-12](docs/tickets/pending/R-12.md) | `review.md` and `reviewer.md` in neutral words | S | Sonnet 5.5 | H | R-10 | blocked: R-10 |
| [R-13](docs/tickets/pending/R-13.md) | Neutral wording elsewhere, string check, `reasoningEffort` validation | S | Sonnet 5.5 |  | R-11 | blocked: R-11 |
| [R-14](docs/tickets/pending/R-14.md) | Five severities and the money rule, old severities read | M | Opus 5.5 | H | R-10 | blocked: R-10 |

### Phase 2 — Approval by conversation

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-20](docs/tickets/pending/R-20.md) | Store tripwire stops refusing everyday commands | S | Opus 5.5 | H | — | READY |
| [R-21](docs/tickets/pending/R-21.md) | ADR and measurement: is a blocked prompt's hook text shown; does a plain reply arrive unchanged | S | Fable 5.2 |  | — | READY |
| [R-22](docs/tickets/pending/R-22.md) | Request classes and bindings; session checked at spend | M | Opus 5.5 | H | R-20, R-21 | blocked: R-20, R-21 |
| [R-23](docs/tickets/pending/R-23.md) | Whole-prompt grammar, frozen repeat-back, atomic claim | M | Opus 5.5 | H | R-22 | blocked: R-22 |
| [R-24](docs/tickets/pending/R-24.md) | Cloud guard records requests and spends receipts, behind a switch; no marker for new classes | M | Opus 5.5 |  | R-23 | blocked: R-23 |
| [R-25](docs/tickets/pending/R-25.md) | Unattended requests: inbox in `/crew:status`, resume, cancel, re-validate. Holds only one-way and plan-of-record items once Phase 3 is on | M | Opus 5.5 |  | R-24 | blocked: R-24 |
| [R-26](docs/tickets/pending/R-26.md) | Verify trust: hash stays default; owner allowance is a separate bounded decision | S | Sonnet 5.5 |  | R-23 | blocked: R-23 |

### Phase 3 — Modes and the decider (new in revision 3)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-M1](docs/tickets/pending/R-M1.md) | `mode` key: machine-owned, protected; repo, ticket and run may only set `guided`; unknown is `guided` | S | Opus 5.5 |  | R-32 | blocked: R-32 |
| [R-D1](docs/tickets/pending/R-D1.md) | `crew_decider.py`: launch with a pinned model, catalog of exact owner-confirmed ids, decision record with requested and reported model id; report-only | M | Opus 5.5 |  | R-06, R-01 | blocked: R-06, R-01 |
| [R-D2](docs/tickets/pending/R-D2.md) | Decision classes in `crew_policy.py`: which asks are routine, closed outcomes per class, sticky denials, per-ticket cap | M | Opus 5.5 |  | R-01, R-D1 | blocked: R-01, R-D1 |
| [R-D3](docs/tickets/pending/R-D3.md) | Advisors: Codex or Kimi output attached as input, never a decision | S | Sonnet 5.5 |  | R-D1, R-10 | blocked: R-D1, R-10 |
| [R-D5](docs/tickets/pending/R-D5.md) | Routine records in the approval store and the `decider` approval value in `crew_ticket.py`: one-step reply bound to the one request that was shown, letter required when several are pending, class fixed at request time | M | Opus 5.5 | H | R-23, R-D2 | blocked: R-23, R-D2 |
| [R-D4](docs/tickets/pending/R-D4.md) | Switch on: routine asks go to the person (`guided`) or the decider (`directive`) | S | Opus 5.5 |  | R-D5, R-24, R-M1, R-P6, R-M4 | blocked: R-D5, R-24, R-M1, R-P6, R-M4 |
| [R-M2](docs/tickets/pending/R-M2.md) | `guided` messaging: ask before each stage, explain template, glossary, "you decide" | M | Sonnet 5.5 |  | R-M1, R-73 | blocked: R-M1, R-73 |
| [R-M3](docs/tickets/pending/R-M3.md) | `directive` behaviour: self-answered questions with decision, rationale and alternatives on the evidence trail; exceptions-only status | M | Opus 5.5 |  | R-D4, R-72 | blocked: R-D4, R-72 |
| [R-M4](docs/tickets/pending/R-M4.md) | Parity suite: one table run under both modes, ask rows followed through to the final grant and execution | M | Opus 5.5 |  | R-M1, R-D2 | blocked: R-M1, R-D2 |

### Phase 4 — Lanes and planned actions (inert first)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-30](docs/tickets/pending/R-30.md) | Actions schema per kind, validation | M | Opus 5.5 |  | R-01 | done (PR #797) |
| [R-31](docs/tickets/pending/R-31.md) | Planned-action matcher for exact actions, report-only | M | Opus 5.5 |  | R-30 | blocked: R-30 |
| [R-32](docs/tickets/pending/R-32.md) | Protected policy: effective-policy comparison | M | Opus 5.5 |  | R-01 | blocked: R-01 |
| [R-33](docs/tickets/pending/R-33.md) | Never lane: hook-skipping flags, redaction, secret tripwire | M | Opus 5.5 |  | R-01 | blocked: R-01 |
| [R-34](docs/tickets/pending/R-34.md) | Human-only findings: terraform state edits, deleting another's branch | S | Sonnet 5.5 |  | R-01 | blocked: R-01 |
| [R-35](docs/tickets/pending/R-35.md) | `balanced` profile for dev and QA | M | Opus 5.5 |  | R-05, R-32, R-33 | blocked: R-05, R-32, R-33 |
| [R-36](docs/tickets/pending/R-36.md) | Read-only database identity setup and check; becomes the database row of account verification (4.14) | S | Sonnet 5.5 |  | R-05, R-A1 | blocked: R-05, R-A1 |
| [R-37](docs/tickets/pending/R-37.md) | Temporary grants, AWS | M | Opus 5.5 |  | R-30, R-32 | blocked: R-30, R-32 |
| [R-38](docs/tickets/pending/R-38.md) | Temporary grants, Azure | M | Opus 5.5 |  | R-37 | blocked: R-37 |
| [R-39](docs/tickets/pending/R-39.md) | Switch on planned actions, one kind at a time: a kind is enabled only when its own control ticket has landed (permission grants after R-37 or R-38 and R-A8; account and admin kinds after R-A8b; envelopes after R-P4) | S | Opus 5.5 |  | R-31, R-32, R-24, R-P2, R-P3, R-P8 | blocked: R-31, R-32, R-24, R-P2, R-P3, R-P8 |
| [R-3A](docs/tickets/pending/R-3A.md) | Session-start line content: guards off, live grants and temporary accounts, open admin need, `directive` mode, same-user broker residual. Written to the status file that R-C6 reads; touches no harness path | S | Haiku 5.5 |  | R-35, R-37, R-M1, R-AA, R-A8, R-B1, R-C6 | blocked: R-35, R-37, R-M1, R-AA, R-A8, R-B1, R-C6 |
| [R-3B](docs/tickets/pending/R-3B.md) | CLAUDE.md wording for O1 | S | Sonnet 5.5 |  | O1 | READY |

### Phase 5 — Plan of record (new in revision 3)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-P6](docs/tickets/pending/R-P6.md) | Serious classifier: the closed list; could not place is serious; cost threshold | S | Opus 5.5 |  | R-01 | blocked: R-01 |
| [R-P1](docs/tickets/pending/R-P1.md) | Plan-of-record template and validator (`crew_planrecord.py`): sections, research labels, typed operations (`payment`, `account-create`, `admin-identity-op`), per-kind envelope fields, exact-only kinds, generated Accounts, Permissions and Money views, expiry | M | Opus 5.5 |  | R-30, R-P6 | blocked: R-30, R-P6 |
| [R-P2](docs/tickets/pending/R-P2.md) | The collaboration flow as states with a state record: planner run records (requested and reported model) and the owner's prompt ids, each bound to the draft digest | M | Opus 5.5 |  | R-P1, R-73, R-D1, R-D3 | blocked: R-P1, R-73, R-D1, R-D3 |
| [R-P3](docs/tickets/pending/R-P3.md) | Approval of a plan of record in the prompt hook: refuses unless the R-P2 state is complete; structured repeat-back; receipt stored outside the plan, naming the plan digest | M | Opus 5.5 | H | R-23, R-P1, R-P2 | blocked: R-23, R-P1, R-P2 |
| [R-P7](docs/tickets/pending/R-P7.md) | Attestation issued at `confirm` over the plan digest (presence key), or recorded from the owner's forge review | M | Opus 5.5 | H | R-07, R-P3 | blocked: R-07, R-P3 |
| [R-P8](docs/tickets/pending/R-P8.md) | Attestation verification library used by both executors | S | Opus 5.5 |  | R-P7 | blocked: R-P7 |
| [R-P4](docs/tickets/pending/R-P4.md) | Envelope matcher: decider binds values, script checks the bounds from the real artifact (plan JSON attribute paths, workflow file and pinned dependencies) | M | Opus 5.5 |  | R-31, R-D1, R-41 | blocked: R-31, R-D1, R-41 |
| [R-P4b](docs/tickets/pending/R-P4b.md) | Money ledger and reservations: atomic reserve before dispatch, release only by reconciliation | M | Opus 5.5 |  | R-P1 | blocked: R-P1 |
| [R-P5](docs/tickets/pending/R-P5.md) | Standing plans: expiry, use cap, void on tier, account or workflow drift | S | Opus 5.5 |  | R-P4, R-P4b, R-A1 | blocked: R-P4, R-P4b, R-A1 |

### Phase 6 — Service accounts and admin use (new in revision 3)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-A1](docs/tickets/pending/R-A1.md) | Account registry, naming convention, workspace enrolment (checkout or authenticated CI workload), tier map references; existing `unattendedCloud` rows migrated | M | Opus 5.5 |  | R-05, R-32 | blocked: R-05, R-32 |
| [R-B1](docs/tickets/pending/R-B1.md) | `crew-broker`: local service under its own OS account, closed request protocol (one action of a plan, one operation of a need), no request that returns a credential; same-user fallback marked weak | M | Opus 5.5 |  | R-A1, R-P8, R-43 | blocked: R-A1, R-P8, R-43 |
| [R-B2](docs/tickets/pending/R-B2.md) | Broker install and enrolment as a planned step, both install scripts untouched; removal path | S | Sonnet 5.5 |  | R-B1 | blocked: R-B1 |
| [R-A2](docs/tickets/pending/R-A2.md) | Permission profiles and `crew_accounts.py verify`, AWS: effective permissions including inherited ones equal the profile; checked at issuance | M | Opus 5.5 |  | R-A1 | blocked: R-A1 |
| [R-A4](docs/tickets/pending/R-A4.md) | Profiles and verify, GitHub tokens and App installations | S | Sonnet 5.5 |  | R-A1 | blocked: R-A1 |
| [R-A5](docs/tickets/pending/R-A5.md) | Verify, Azure | M | Opus 5.5 |  | R-A2 | blocked: R-A2 |
| [R-A6](docs/tickets/pending/R-A6.md) | Issuing read and dev and QA write credentials to a child: references, environment or `credential_process`, redactor on everything published | M | Opus 5.5 |  | R-A1, R-A2, R-33 | blocked: R-A1, R-A2, R-33 |
| [R-A7](docs/tickets/pending/R-A7.md) | Admin need record and checks per reason code on provider evidence, exact operations with payload digests; report-only | M | Opus 5.5 |  | R-A1, R-A2, R-P6 | blocked: R-A1, R-A2, R-P6 |
| [R-A8](docs/tickets/pending/R-A8.md) | Admin operations through the broker, AWS: each mechanism verified against the provider first; time box, source identity, session policy, permissions boundary; one operation per request with its payload digest | M | Opus 5.5 |  | R-A7, R-B1, R-P8 | blocked: R-A7, R-B1, R-P8 |
| [R-A8b](docs/tickets/pending/R-A8b.md) | Admin close: provider audit pull, comparison with the need's operations and payloads, quarantine, evidence post, automatic close | M | Opus 5.5 |  | R-A8 | blocked: R-A8 |
| [R-A9](docs/tickets/pending/R-A9.md) | Onboarding plan template: enrol the workspace and the admin account, create the read and write accounts per tier from profiles, list grantable profiles, set the owner alert | M | Opus 5.5 |  | R-P1, R-A8b | blocked: R-P1, R-A8b |
| [R-AA](docs/tickets/pending/R-AA.md) | Temporary accounts: provider-enforced expiry, or broker-held credential refused after the deadline; sweep as clean-up from `/crew:status`, the pipeline and the broker timer | M | Opus 5.5 |  | R-37, R-A1, R-A8b | blocked: R-37, R-A1, R-A8b |
| [R-AC](docs/tickets/pending/R-AC.md) | Admin operations on providers without session scoping, through the broker, marked weak | M | Opus 5.5 |  | R-A7, R-B1 | blocked: R-A7, R-B1 |
| [R-AB](docs/tickets/pending/R-AB.md) | Switch on: verified scoped accounts authorised; production read always | S | Opus 5.5 |  | R-A2, R-A6, R-35 | blocked: R-A2, R-A6, R-35 |

### Phase 7 — Production

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-40](docs/tickets/pending/R-40.md) | `crew_prodwindow.py` | S | Opus 5.5 |  | R-32 | blocked: R-32 |
| [R-41](docs/tickets/pending/R-41.md) | Terraform action manifest from the saved plan | M | Opus 5.5 |  | R-30 | blocked: R-30 |
| [R-42](docs/tickets/pending/R-42.md) | Backup evidence, first provider (AWS RDS snapshots) | M | Opus 5.5 |  | — | READY |
| [R-43](docs/tickets/pending/R-43.md) | `crew_prodcheck.py` receipt per operation, prior state, attempt | M | Opus 5.5 |  | R-41, R-42 | blocked: R-41, R-42 |
| [R-44](docs/tickets/pending/R-44.md) | Pipeline executor template: the protected Environment holds the write account; the privileged workflow, check script and manifest reader come from a protected ref; the job verifies the attestation | M | Opus 5.5 |  | R-43, R-P8 | blocked: R-43, R-P8 |
| [R-45](docs/tickets/pending/R-45.md) | Production queue with durable states and atomic reservation of the action, the plan use and the money amount, held until reconciliation | M | Opus 5.5 |  | R-40, R-P4b | blocked: R-40, R-P4b |
| [R-46](docs/tickets/pending/R-46.md) | Switch on unattended production, by pipeline or broker; eligibility is machine timing and the plan's window and `unattended: yes` | S | Opus 5.5 |  | R-39, R-43, R-44, R-45, R-AB, R-B1, R-P5, R-P8, R-48 | blocked: R-39, R-43, R-44, R-45, R-AB, R-B1, R-P5, R-P8, R-48 |
| [R-47](docs/tickets/pending/R-47.md) | Owner-declared, scoped emergency | S | Opus 5.5 |  | R-23, R-43 | blocked: R-23, R-43 |
| [R-48](docs/tickets/pending/R-48.md) | Irreversible actions: listed exactly in the plan, cap and preflight, one use | S | Opus 5.5 |  | R-43, R-P1 | blocked: R-43, R-P1 |

### Phase 8 — Locations, clean-up, handoff

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-50](docs/tickets/pending/R-50.md) | Init registers the owner-local worktree hook; both lane roots covered | S | Sonnet 5.5 |  | R-04 | blocked: R-04 |
| [R-51](docs/tickets/pending/R-51.md) | Reviewer snapshot: read-only input, separate output | M | Opus 5.5 | H | R-04, R-10 | blocked: R-04, R-10 |
| [R-52](docs/tickets/pending/R-52.md) | Coordinator clean-up with checkout lock | M | Sonnet 5.5 |  | R-04, R-72 | blocked: R-04, R-72 |
| [R-53](docs/tickets/pending/R-53.md) | Verify gate: candidate-sha clean tree, explicit NOT VERIFIED, both shells | M | Opus 5.5 | H | R-04 | blocked: R-04 |
| [R-54](docs/tickets/pending/R-54.md) | Scope guard allowance for the active ticket's handoff file | S | Opus 5.5 | H | — | READY |
| [R-55](docs/tickets/pending/R-55.md) | Handoff format and `/crew:handoff` commit | S | Sonnet 5.5 |  | R-54 | blocked: R-54 |

### Phase 9 — Sandbox

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-60](docs/tickets/pending/R-60.md) | `crew_sandbox.py run` | M | Opus 5.5 |  | R-04, R-02 | blocked: R-04, R-02 |
| [R-61](docs/tickets/pending/R-61.md) | Disposable-VM host-change test and suite hygiene | M | Sonnet 5.5 |  | R-60 | blocked: R-60 |
| [R-62](docs/tickets/pending/R-62.md) | Both eval builders and a Compose template use the launcher | S | Sonnet 5.5 |  | R-60 | blocked: R-60 |
| [R-63](docs/tickets/pending/R-63.md) | Raw `docker run` tripwire in the cloud guard | S | Sonnet 5.5 |  | R-60 | blocked: R-60 |
| [R-64](docs/tickets/pending/R-64.md) | Worker-in-container mode for unattended lanes | M | Opus 5.5 |  | R-60 | blocked: R-60 |

### Phase 10 — Orchestrator and workflow

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-70](docs/tickets/pending/R-70.md) | `crew_triage.py` | S | Sonnet 5.5 |  | — | READY |
| [R-71](docs/tickets/pending/R-71.md) | Role defaults, escalation by round, re-route and restart counters | S | Sonnet 5.5 |  | R-70 | blocked: R-70 |
| [R-72](docs/tickets/pending/R-72.md) | Status maps and event ids for all four trackers | M | Opus 5.5 |  | — | READY |
| [R-73](docs/tickets/pending/R-73.md) | Phase state machine; documentation allowlist | M | Opus 5.5 |  | R-70, R-72 | blocked: R-70, R-72 |
| [R-74](docs/tickets/pending/R-74.md) | Wave: lanes run Implement to Fix; coordinator does the rest | M | Sonnet 5.5 |  | R-73, R-50 | blocked: R-73, R-50 |
| [R-75](docs/tickets/pending/R-75.md) | Advisor review of the spec before approval (the owner's for serious work, the person's or the decider's otherwise) | S | Sonnet 5.5 |  | R-73 | blocked: R-73 |

### Phase 11 — Checks

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-80](docs/tickets/pending/R-80.md) | Tiers and slices in `gate-runner.py` | M | Sonnet 5.5 |  | — | done (PR #799) |
| [R-81](docs/tickets/pending/R-81.md) | Verify gate: fast per round, heavy at Gate, shard completeness | M | Opus 5.5 | H | R-80, R-53 | blocked: R-80, R-53 |
| [R-82](docs/tickets/pending/R-82.md) | Web test and doc slices; smoke template | S | Sonnet 5.5 |  | R-80 | blocked: R-80 |

### Phase 12 — Plain language

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-90](docs/tickets/pending/R-90.md) | Refusal template applied to guard reasons | S | Sonnet 5.5 |  | R-35 | blocked: R-35 |
| [R-91](docs/tickets/pending/R-91.md) | `/crew:help` and `/crew:status` for owners | S | Sonnet 5.5 |  | R-25 | blocked: R-25 |

### Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)

| Ticket | Title | Size | Model | H | Depends | Status |
|---|---|---|---|---|---|---|
| [R-C1](docs/tickets/pending/R-C1.md) | Registry completeness: every key has a plain-language line, allowed values, a layer class and its arrival version | S | Sonnet 5.5 |  | — | done (PR #795) |
| [R-C2](docs/tickets/pending/R-C2.md) | Generator writes `config.blank.json`, `global.blank.json`, `keys.json` and `template.annotated.md` into `plugin/crew/docs/configuration/`; `--check` covers them | M | Opus 5.5 |  | R-C1 | blocked: R-C1 |
| [R-C3](docs/tickets/pending/R-C3.md) | `guide.md`: layers, owner set-up, the AI procedure, worked examples as files validated in CI | M | Sonnet 5.5 |  | R-C2 | blocked: R-C2 |
| [R-C4](docs/tickets/pending/R-C4.md) | `CONFIG.md` becomes a generated index under its cap; prose and family tables move to the guide; budgets read and set | S | Sonnet 5.5 |  | R-C2 | blocked: R-C2 |
| [R-C5](docs/tickets/pending/R-C5.md) | Pointers from crew-setup, `/crew:init`, `/crew:help`, `/crew:config`; `crew_config.py --guide` | S | Sonnet 5.5 |  | R-C3 | blocked: R-C3 |
| [R-C6](docs/tickets/pending/R-C6.md) | Session-start line in `crew_hook.py` that prints a status file other tickets write to, plus the line for a missing or invalid config naming the guide | S | Opus 5.5 | H | R-C5 | blocked: R-C5 |
| [R-C7](docs/tickets/pending/R-C7.md) | Built HTML, DOCX and PDF from the same source | S | Sonnet 5.5 |  | R-C3 | blocked: R-C3 |
| [R-C7b](docs/tickets/pending/R-C7b.md) | Publish the Claude Docs "Configuration Guide" from the same source and bring the existing "Crew Config Reference" artifact into line; state who may publish and how it is checked | S | Sonnet 5.5 |  | R-C7 | blocked: R-C7 |
