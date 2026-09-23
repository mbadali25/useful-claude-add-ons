---
title: Daily workflow - scope and approval
guide: crew 1.0, guide 2 (section; linked from daily-workflow.md)
date: 2026-09-23
---

# Scope and approval

Every crew 1.0 ticket has a contract: the spec says which files it may touch, the plan says which
of those each step changes, and you approve both. Two hooks then hold the session to that
contract. This section explains what they do, what they print, and how to change scope while you
work.

## The contract

A ticket lives in `.work/tickets/<id>/`:

- `spec.md` has six sections: `## Intent`, `## Exclusions`, `## Evidence`, `## Unknowns`,
  `## Touch` and `## Acceptance checks`. `## Touch` lists one repo-relative glob or path per
  bullet:

  ```markdown
  ## Touch
  - `src/export/**`
  - `tests/test_export.py`
  - `docs/export.md`
  ```

- `plan.md` is a list of steps. Each step has a `Files:` line, a `Test:` line and a `Risk:` line.
  Every `Files:` entry must fall inside Touch. A plan cannot add a path the spec does not list.

Check the contract at any time:

```bash
python3 <crew>/hooks/scripts/crew_ticket.py validate --ticket T-0042
```

A plan path outside Touch is reported as `INVALID: plan Files entry '...' is outside spec
## Touch`. To fix it, add the path to Touch. crew never widens Touch for you.

## Approval

When the plan is ready, the session asks you to approve it. Type this yourself:

```
/crew:approve T-0042
```

crew's UserPromptSubmit hook sees the prompt you typed, validates the contract, then records the
sha256 of `spec.md` and `plan.md` in `<git-common-dir>/crew/tickets/T-0042/approval.json`, marked
`approved_via: "user-prompt"`. If the contract does not validate, the hook blocks the prompt and
says why. That file is outside the worktree, and the scope guard refuses any Write or Edit to it
and any shell command that runs `crew_ticket.py approve`, so the session cannot approve its own
plan. The approval is a step you take, not a lock.

`crew_ticket.py status --ticket T-0042` prints one of three states:

- `approved`: both files match the receipt.
- `stale`: `spec.md` or `plan.md` changed since approval.
- `none`: the ticket has never been approved.

## While you implement: the scope guard

Before every Write, Edit, MultiEdit or NotebookEdit, the guard checks the target file:

- The ticket's own `.work/tickets/<id>/` files are always allowed, so you can amend the spec and
  plan.
- Any other file needs a current approval and a path inside Touch.
- Nothing else is exempt, including `.crew/`, `TODO.md`, `.claude/` and crew's own policy files.
  If the ticket changes one of them, list it in Touch.
- Approval receipts, the review ledger and the scope base are always refused.

The guard checks the real file a symlink points to and the path as written, so a link cannot
move a write into or out of scope. `..` is resolved the way the operating system resolves it.
Refusals look like this:

```
SCOPE GUARD: refused Edit on other/keep.py.
  Reason: other/keep.py is outside T-0042's spec ## Touch.
  To widen scope: amend .work/tickets/T-0042/spec.md ## Touch (and plan.md), then ask the user to type
  `/crew:approve T-0042`. (scope.mode is block)
```

## At the end of a turn: the completion audit

The guard only sees the editing tools. A `sed -i`, a shell redirect or a formatter can still
change files. So when the session stops, the completion audit compares the whole tree with the
commit the ticket started from. It covers committed, staged, unstaged and untracked changes, and
both ends of a rename. If any changed path is outside Touch, the audit blocks the stop and lists
the paths in six lines or fewer. It never blocks the continuation it caused. `/crew:done` runs
the same check:

```bash
python3 <crew>/hooks/scripts/completion_audit.py --check --ticket T-0042
```

The audit sees what git sees. Gitignored files, including everything under `.crew/`, and `.work/`
are outside it.

## Amending scope

1. Edit `spec.md` `## Touch` to add the path. Update `plan.md` if a step now changes it.
2. Run `crew_ticket.py validate --ticket <id>`.
3. Type `/crew:approve <id>` yourself.

Between steps 1 and 3 the approval is stale. The guard refuses edits outside the ticket directory
until you approve again.

## After two review rounds: a successor plan

If a ticket uses both review rounds without an accepted receipt, it moves to `NEEDS_REPLAN`.
Write a different plan and approve it. `approve` reports `review may continue`, and the ledger
gives the new plan two fresh rounds. Approving the same plan again is refused and exits with
status 3.

## Modes

Set `scope.mode` in `.crew/config.json`:

| Value | What happens |
|---|---|
| `off` | Default. Neither hook does anything. |
| `report` | Everything is allowed. Would-be refusals go to `.crew/guard.log` and appear as a system message. |
| `block` | Refusals block. |
| `auto` | `report` for the first ten tickets approved in the repository, then `block`. |

If the config file does not parse, or `scope.mode` has an unknown value, crew treats it as
`block` and says so.

## Which ticket is active

`crew_ticket.py activate --ticket <id>` sets the active ticket for the current worktree.
`deactivate` clears it, and `active` prints it. Without a setting, crew uses the open ticket in
`.work/INDEX.md` if `.work/tickets/<id>/` exists. With no active ticket, the edit guard only
protects approval and ledger state, and the completion audit does nothing.
