# 7. crew keeps its own Codex invocation; codex-plugin-cc is evaluated, not adopted

**Status:** accepted, 2026-10-19 (re-evaluate on the trigger below)
**Decided by:** the owner's approval of the L-0727 spec (2026-10-19), which records this as an evaluation, not an adoption

## Context

crew reaches Codex for QA review through `review_run.py` `command_for` (`codex exec --json --sandbox
read-only --skip-git-repo-check -C <root> [--model M] [-c model_reasoning_effort=E] <prompt>`,
`review_run.py:838-845`), and reads the verdict out of its JSON stream with
`review_verdict.codex_final_message` (`review_verdict.py:257`). L-0727 asked whether
`openai/codex-plugin-cc` could replace that call, so crew would maintain less Codex plumbing.

Evaluated: `openai/codex-plugin-cc` v1.0.6 (released 2026-07-08, Apache-2.0), from the researcher's
report of 2026-10-08. The facts below were not re-fetched on 2026-10-19; that date only re-read crew's own
side.

## Decision

Keep `command_for`. Do not adopt codex-plugin-cc. Each criterion, with its evidence:

| Criterion | crew needs | codex-plugin-cc v1.0.6 | Result |
|---|---|---|---|
| A custom prompt or rubric | the review prompt crew builds (`review_prompt.py`) | `review` takes `--base`, `--scope`, `--model`, `--json` and no prompt or rubric; `adversarial-review` takes focus text only | does not fit |
| A documented JSON verdict | CLEAN, FINDINGS or INCOMPLETE parsed by `review_verdict.py` | the JSON shape is unconfirmed | unknown, so not relied on |
| A read-only sandbox | `--sandbox read-only` on the command line | through `codex` itself, as crew's call already is | equal |
| The ledger-bound receipt | crew owns `review_ledger.py` rounds and the receipt hash | none; it would sit beside, not inside, crew's ledger | crew keeps it either way |
| Dependencies | `codex` only | Node >= 18.18 and `@openai/codex` | a new runtime dependency |

An unconfirmed JSON contract is "could not tell", not a pass: crew's reviewer path treats a verdict it
cannot parse as INCOMPLETE, so a plugin whose output it cannot parse would make every round incomplete.

## Rejected option

Replace `command_for` with a `/codex:review` call. It would drop a maintained line of plumbing but
needs a prompt entry point crew cannot pass, an unconfirmed output contract and Node.

## Trigger to re-evaluate

codex-plugin-cc exposes an entry point that takes a prompt file and documents its JSON verdict.
Re-check then: the prompt input, the verdict schema, the sandbox flag and the Node requirement, against
the table above.

## Consequences

No code changes. `review_run.py` and `review_verdict.py` are untouched by L-0727.
