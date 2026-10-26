# Functional QA checklist

How to exercise a change that has no screen: an API, a CLI, a job or worker, a webhook. Browser
changes use `/crew:webtest`. This checklist is adapted from gstack's functional QA section (see
`NOTICE.md`), restated for crew's evidence rules. Read it when a ticket's acceptance checks name a
non-browser surface, or when a QA report claims "works" for one.

## Before the first probe

- **Pick the surface from the change**, not from whether a URL exists: browser, functional, or a
  mix. A URL may be an API; no URL does not mean no server. Include the changed behaviour and its
  neighbours.
- **Own the fixtures.** Use synthetic data and credentials in an isolated store. Resolve paths,
  symlinks, queues and downstream destinations first: localhost can forward to production. If you
  cannot tell who owns a target, that probe is blocked, not skipped quietly. Touching production
  or an external system needs an explicit instruction naming the target, the operation and the
  effect.
- **State the target, the surfaces, the writes you may make and the depth** before you start.

## What to exercise

For each contract the change touches, run one probe per row that applies. A probe is one command
or request, run on its own.

| Contract | What to exercise | Pass looks like |
|---|---|---|
| Success | the documented happy path | right output AND the right durable effect, not only "accepted" |
| Invalid input | one probe per input rule, breaking only that rule | the declared rejection, the right status, no state change |
| Auth | valid, missing, invalid identity; wrong owner or role | allowed only for the right identity; no effect on a refusal |
| CLI | the command with its flags | exact exit code; stdout and stderr read separately; files changed as documented |
| State | start, middle and end or failed states | only permitted transitions |
| Timeout, cancel | deadline hit, work cancelled midway | owned work stops, partial state is as documented, recovery works |
| Retry | a failing dependency | the promised attempts and backoff, a terminal state, no unbounded loop |
| Duplicates | the same request or event twice | the number of durable effects the guarantee promises |
| Concurrency | two competing operations, in both finishing orders | the invariant holds either way |
| Partial failure | interrupt after an effect, then restart or replay | completes or dead-letters, with no duplicate effect |

Do not demand exactly-once delivery unless the repo promises it. Keep acceptance, enqueue,
processing, retry or dead-letter, and final effect separate: a 2xx is acceptance, not completion.

## Evidence to keep, per probe

The exact command or method, path, headers and body; the setup and reset; the contract and where it
is written (doc, test or the user); exit code or status, stdout and stderr; the durable state before
and after; the revision and runtime; where the evidence is saved. Secrets appear by environment
variable name only. Save the evidence before you clean up, clean up only what you started, and name
anything left behind.

## Pass, fail and everything else

Record each contract as one of: pass, fail, blocked, not run, inconclusive, not applicable (with a
reason).

- **Pass** needs every required contract to pass on the current input, with nothing required left
  over. A missing prerequisite, a missing expectation, a missing observation, a timeout and a
  refusal are never a pass.
- **Fail** needs the intended contract and its source. A bug is not "the code does X"; it is "the
  contract says Y and the code does X".
- **Blocked** is a missing service or permission that stops the probe. It is reported, and it
  never reads as pass.
- An expected rejection or an injected failure that behaves as documented is a pass.
- Replay a failing probe from the same starting state before any fix, and again after it. A
  different input or a new test is not a replay.
- Never fix product code to hide a missing prerequisite, and never freeze buggy output into a test.
- List the contracts you did not test. A report with no such list claims full coverage.
