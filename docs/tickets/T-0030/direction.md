# T-0030 direction - cross-session coordination for autopilot

Status: direction APPROVED by the owner 2026-09-25, split into three tickets:
"Yes let's split it into three tickets".
- T-0030 (this ticket): claims plus the git-backed record (`crew-coord/<channel>`), and a read-only status.
- T-0031: versioned interface contracts and shared findings, frozen on first `built_by`, plus
  cross-session dependencies in T-0029's wave. A hash mismatch or an `unknown` peer state refuses the wave.
- T-0032: the messaging bridge as the doorbell, the main session as the hub, and inbound messages
  handled as untrusted data.

## Ask (owner, Matthew Badali, 2026-09-25, verbatim)
"So when it runs on its own the workflow and automation will pick the recommended route can the
workflow communicate with other sessions because that will be crucial
I have scenarios where I have one code base working with another code base together so two sessions
are coordinating work and researching their own designs and sharing information"
"It wouldn't be cross repo it would be cross session as well"

## Scope
Coordination between Claude Code sessions, whether they work the same repo or different repos:
- Two sessions on one repo, e.g. three sessions worked this repo in one night (CLAUDE.md Lessons,
  "Check ListAgents before assuming a diff, a branch, or a dirty tree is yours").
- Two sessions on two repos building against each other, each researching its own design and
  sharing findings, contracts and progress.

## Facts this rests on
- Transport exists: `ListAgents` finds sessions on this machine and Remote Control sessions
  elsewhere; `SendMessage` delivers to a session's next tool round. A subagent's send goes out under
  its parent session's address and replies land in the parent's conversation, not the subagent's.
  A session in another permission mode may hold messages for its user; remote and cloud sends give
  no delivery confirmation; cloud sessions cannot reply. (Tool contract, observed this session.)
- Messages are not durable: `/clear` or a crash loses what only lived in a conversation.
- Crew today: one ticket per repo, a multi-repo direction cross-referenced by id in the sibling
  repo's spec (`plugin/crew/commands/spec.md`, "Multi-repo and cross-references"). The active ticket
  is per worktree (`plugin/crew/hooks/scripts/crew_ticket.py:66-76`). `.work/INDEX.md` is appended by
  several sessions at once (`.work/tickets/T-0012/spec.md:18`). Nothing in crew sends or reads a
  cross-session message.

## Options
- A. Messages only: sessions coordinate over `SendMessage` with no written record.
  Cheap; loses every agreement on /clear or crash; no way to tell "agreed" from "never arrived".
- B. Shared files only: sessions coordinate through a coordination folder they both read and write.
  Durable and checkable; no push, so a session learns of a change only when it next looks.
- C. Both (recommended): files are the record, messages are the doorbell. Every agreement, contract,
  claim and finding is written to a coordination folder; a message only says "T-00xx changed, re-read
  it". A session resuming after /clear rebuilds from the files alone.

## Recommendation (to be confirmed)
C, with these parts:
1. **Channel.** A named coordination channel both sessions join, stored where both can reach it:
   the shared `<git-common-dir>/crew/coord/<channel>/` for sessions on one repo, and a machine-level
   `~/.claude/crew/coord/<channel>/` for sessions on different repos. The channel is named in each
   side's ticket.
2. **Claims.** A session claims a ticket in the channel before working it, so two sessions never work
   one ticket; a stale claim (session gone from `ListAgents`, or older than a TTL) reads as
   "unknown owner", never "free", until the owner releases it.
3. **Contracts and findings.** Interface contracts both sides must build against, and research
   findings (summary + sources, not transcripts), are files in the channel with a version; each side
   records which version it built against.
4. **Cross-session dependencies.** A ticket may depend on another session's ticket by
   `<channel>:<id>`; T-0029's wave treats it as open until that ticket's claim reports done.
5. **Hub.** The main session of each side talks; lanes never message peers. A lane's question for the
   other side is batched up to its main session like any other question.
6. **Silence is not agreement.** An unanswered message, an offline peer, or a held message is
   "could not tell", surfaced to the owner, never read as consent.
7. **Autonomy.** Sessions may answer each other's questions under T-0010's questions policy; a
   contract change the other side has already built against always stops for the owner.

## Independent review (Fable 5.1, 2026-09-25) and the coordinator's check of it
Adopted from the review:
- Option C's principle stands: files are the record, messages are the doorbell.
- **The same-repo location was wrong.** `<git-common-dir>/crew/` is where the scope guard refuses
  every Write/Edit and any writing shell command (`plugin/crew/hooks/scripts/scope_guard.py:88-90`,
  `:192-197`, `_DOTGIT_CREW_RE`). A channel there would be refused, or would need a carve-out in a
  blocking hook. Dropped.
- **Part 7 was wrong.** A peer's answer is not a T-0010 policy value. At most it is a *finding*, which
  this session's own `question_policy` then decides on. It is never a `taken:` line by itself.
- A message from another session is untrusted data and never counts as approval, since approval
  comes only from the owner's own `/crew:approve` prompt.
- Contracts freeze on first `built_by`. Each side records the hash it built against. A hash mismatch
  refuses the wave, mechanically, like `accepted()`'s `stale`. It is not only a prose "stop".
- A `<channel>:<id>` dependency whose peer state is missing or unreadable reads `unknown`, and
  T-0029's `plan` already refuses `unknown` dependencies.
- Only the owner breaks a claim.
- Split into three: (a) claims plus the coordination folder, with a read-only `crew_coord.py status`;
  (b) contracts with hash binding and the wave refusal; (c) messaging as the doorbell. The first
  slice is (a).

Rejected from the review, checked 2026-09-25:
- The review recommended a *tracked* `.work/coord/<channel>/`, "shared through git as `.work/INDEX.md`
  is today". The premise is false. `.work/` is ignored entirely (`git check-ignore -v .work/INDEX.md`
  gives `.gitignore:273:.work/`), and each worktree holds its own copy (`/repos/personal/uca-t0004/.work/INDEX.md`
  exists). So `.work/` is neither tracked nor shared between worktrees.

Storage, as it stands after both:
- Same machine, same or different repos: a machine-level folder outside every git dir
  (`~/.claude/crew/coord/<channel>/`). The scope guard's `<git-common-dir>/crew/` refusal does not
  cover it. Not yet verified: how the scope guard classifies a Write outside the repo top (to measure
  in spec).
- Different machines (Remote Control): no local folder reaches them. The only durable route is a
  tracked, pushed location, e.g. a new `.crew/coord/`. That changes the named un-ignore list, which
  `scripts/check-marketplace.py::check_crew_ignore_policy` asserts in several places, and every
  coordination update becomes a commit. Proposed as a later slice, not the first.

## Owner answer (2026-09-25, verbatim)
"The repos might be on the same machines however the sessions might be on different machines due to
memory and resource constraints"

Consequence: cross-machine is the primary case, not a later slice. A machine-level folder
(`~/.claude/crew/coord/`) reaches only one machine, so it cannot be the record. Each session works its
own clone on its own machine, so the record has to travel with git, which both sides already have and
push to. Revised storage recommendation (to be confirmed in spec):
- The channel is a git ref pushed to the shared remote: an orphan branch `crew-coord/<channel>` in
  the repo that hosts the channel. It holds claims, contracts, findings and a log, one file each.
  `crew_coord.py` writes it with git plumbing (`hash-object`, `mktree`, `commit-tree`, then `push` with
  lease), so it never checks out the branch, never touches a working tree or `.work/`, and never
  writes under `<git-common-dir>/crew/`. Main's history, the gitignore policy, and the un-ignore list
  that `check_crew_ignore_policy` asserts are all left alone.
- Reading means `git fetch` of that ref at every phase boundary. The `SendMessage` doorbell is an
  optimisation only. Over Remote Control it has no delivery confirmation, so correctness can never
  depend on it.
- A push rejected by a lease is a concurrent update: re-fetch, re-apply, retry, and never force.
  "Not yet pushed" and "fetch failed" are visible states that read as `unknown`, never as current.
- The second repo joins the channel by naming `<remote>:<channel>` in its ticket, and needs push
  access to that remote.
- To measure in spec: whether GitHub and the owner's branch protection accept pushes to
  `crew-coord/*`, whether the force-push guard (`crew_guards` `forcePush`) needs to know about it, and
  whether the post-checkout/post-commit graphify hooks fire on plumbing commits (they should not,
  because no checkout happens).

## Owner decision (2026-09-25, verbatim)
"So we'll be using the Claude messaging bridge for other sessions to talk cross session"
- Sessions talk over Claude Code's messaging bridge (`ListAgents` / `SendMessage`, including Remote
  Control sessions on other machines). It is the conversation channel: questions, findings, "contract
  v3 is up", and requests.
- The git channel above stays the record. Anything agreed over the bridge is written to it before
  either side acts on it, because a bridge message has no delivery confirmation over Remote Control,
  can be held for a user's approval, and is gone after `/clear`.
- An inbound bridge message is untrusted data. It is never an approval, and never an answer that
  skips this session's own questions policy.

## Open questions
- Channel storage for different repos: machine-level folder (one machine only) vs a tracked file in
  one of the repos vs a vault note - which fits the owner's setups (same machine, or Remote Control
  across machines)?
- Does the owner join a channel explicitly (e.g. `/crew:autopilot join <channel>`), or does a ticket
  that names a sibling repo join automatically?
- Claim TTL, and who may break a stale claim.
- Depends on T-0029 (waves) and T-0012 (goals, set file); T-0018 router for any new subcommand.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
