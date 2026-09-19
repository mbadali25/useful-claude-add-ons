"""PreToolUse guard on Write/Edit, keyed on which crew role is dispatching.

Mechanical enforcement of the write-scope prose every agent file already
carries. `agents/pm.md:49-53` says "You do not write application code,
tests, docs..." and nothing stopped it doing exactly that for four hours on
2026-09-19 -- prose is not enforcement, and three other roles had `tools:`
grants that disagreed with their own prose the same way. This is the harness
doing what the prompt could not: refusing the tool call outright.

## Policy, in one table

Every crew agent falls into exactly one bucket, decided by whether its
`tools:` frontmatter in `agents/<name>.md` grants Write and Edit at all --
NOT by what the role's prose says it should do, which is the distinction the
whole hook exists to enforce:

  * **`_DENY_ROLES`** -- the role's `tools:` line has neither `Write` nor
    `Edit`. It may not write or edit ANY file, regardless of path. A
    dispatch that reaches this hook anyway (a role can still be handed a
    Write/Edit tool_use if the harness or a jailbreak forces one) is refused
    outright.
  * **`pm`** -- the one path-scoped role. May Write/Edit only under
    `_PM_ALLOWED_PATTERNS`: `.crew/**`, `TODO.md`, `.work/**`,
    `docs/diagrams/**`. Everything else -- application code, tests, other
    docs -- is out of scope, which is the literal rule `agents/pm.md`
    already states in prose.
  * **`_UNRESTRICTED_ROLES`** -- every other role whose `tools:` line grants
    both Write and Edit. Developer-type and content-type roles alike; this
    hook does not further narrow them. (`docs-writer` and `scribe` write
    prose rather than code, but the binary "has Write/Edit or does not" is
    the rule the harness can check without re-deriving what kind of writer
    each one is -- see `tests/test_role_write_guard.py` for the table this
    was measured against.)

`tests/test_role_write_guard.py::test_policy_table_matches_the_agent_files`
parses every `agents/*.md`'s `tools:` frontmatter and asserts the three sets
above are exactly the partition that produces -- so a `tools:` grant added or
removed in an agent file, with this table left alone, is a failing test
rather than a silent drift.

## What "unknown" means here, and why it allows

Per `crew_state.GUARD_DEFAULTS` / CLAUDE.md's "the recurring bug is an
unknown collapsing into the safe-looking value": an unknown must not wear the
label of a decision. Two different unknowns reach this hook and both resolve
to ALLOW, because a hook that fails closed on "I cannot tell who is running"
would strand every role the harness does not yet report cleanly, but each
is distinguished in the log rather than silently merged:

  * **no `agent_type` at all** -- the hook fired outside a subagent (the
    main thread has full write access already, by design) or on a Claude
    Code build old enough not to send the field. Logged as
    `no-agent-type`.
  * **`agent_type` present but not a crew role this table has an opinion
    about** -- a built-in agent (`Explore`), a different plugin's agent, or
    a typo. Logged as `unknown-role:<value>`.

`agent_type`'s exact wire form was NOT observed live against a real
dispatched subagent in this session (see the commit report for what was and
was not verified) -- the docs describe it only as "Agent name (for example
`"Explore"` or `"security-reviewer"`)", with no worked example for a
plugin-scoped agent. `crew`'s own agents are registered as `crew:pm`,
`crew:analyst`, etc. in at least one tool listing this session observed, so
`_normalise_role` strips a LEADING `crew:` prefix before matching --
`"crew:pm"` and `"pm"` both resolve to `"pm"`. It strips ONLY that prefix,
not the last `:`-segment of anything: an earlier draft stripped up to the
last colon unconditionally, so `"other-plugin:analyst"` collapsed onto this
table's own `analyst` (a `_DENY_ROLES` member) and a completely unrelated
plugin's agent was refused under crew's policy for a role it has never heard
of. A prefix that is not `crew:` is left on the string, so it cannot collide
with a bare crew role name and falls through to `unknown-role:<value>`,
carrying the ORIGINAL prefixed value rather than a stripped one.

## Modes -- `guards.roleWrites`

  * `off` *(default)* -- this script exits 0 immediately, before reading
    the policy table at all. Nothing is refused, nothing is logged. Every
    repo that has never set the key is here; see `crew_guards.ROLE_WRITE_DEFAULT`
    for why the default is not the floor.
  * `report` -- every decision (in-scope AND out-of-scope) is allowed, and
    every decision is appended to `.crew/guard.log`.
  * `block` -- an out-of-scope write is refused (exit 2, message on
    stderr naming the role, the path and the permitted set); an in-scope
    write is allowed. Both are logged.

**Exception, over BOTH layers, and UNCONDITIONAL:** if EITHER the repo
config (`.crew/config.json`) or the machine-global one is present but does
not parse into the shape this key needs (see `crew_config.layer_state`),
the effective policy is forced to `block` regardless of what the ratchet
already computed from the OTHER, surviving layer. A repo or machine that
once armed this guard and now has a corrupted config file is not the same
fact as one that never armed it, and CLAUDE.md's "unknown collapsing into
the safe-looking value" is exactly this case if left alone. Reported in
three rounds, 2026-09-19: (1) a corrupt repo config with no global override
resolved to `off`; (2) a `.crew/config.json` that is a DIRECTORY read as
"absent", and an explicit `"guards": null` read as an unset key, both
through the first fix's own blind spots; (3) a corrupt repo config with a
VALID, non-`off` global policy (say `report`) resolved to THAT value
through the ordinary ratchet, because the first fix only intervened when
the ratchet's own answer was `off` -- so a repo that used to say `block`
and got corrupted silently downgraded to `report`, which never blocks
anything, instead of the floor. `layer_state` and this unconditional check
close all three the same way.

## Symlinks and junctions

Scope is checked against the REAL, filesystem-resolved path
(`_real_repo_relative`), never the lexical one a tool call names. A path
that TEXTUALLY reads `.crew/link/app.py` fnmatches `.crew/**` and would
classify as in-scope for `pm` on the string alone -- but if `.crew/link` is
a symlink or a Windows junction pointing at `src/` (still inside the repo,
just outside `pm`'s permitted prefixes), the write actually lands in
`src/app.py`, outside pm's declared scope, and the tool call itself still
opens the real target regardless of what the lexical path said. Reported
and fixed 2026-09-19; see `_resolve_real_target`.

`_resolve_real_target` NEVER calls `os.path.abspath`/`os.path.normpath`
on the raw path, and this is load-bearing, not stylistic: both collapse a
literal `..` LEXICALLY, before any symlink is resolved. Reported and
fixed 2026-09-19, the most serious finding in this whole series:
`.crew/link/../app.py`, with `.crew/link` a symlink to `src/subdir`,
lexically normalises to `.crew/app.py` -- in scope, on the string alone
-- while the OS resolves the SAME path by following `.crew/link` to
`src/subdir` FIRST and applying `..` against the RESOLVED parent
afterward, landing in `src/app.py`. `_resolve_real_target` now walks the
path one component at a time, resolving whatever exists on disk as it
goes, and pops the RESOLVED parent for a `..` -- never a lexical one --
exactly mirroring how the kernel itself walks a path.

## A target outside the repo root is not this guard's business

Reported and fixed 2026-09-19, a probe finding on the first commit above.
This hook's whole purpose is the REPO's write scope: once `pm`'s target is
resolved (following any symlink/junction as above), if it lands OUTSIDE the
repo root entirely -- the harness-sanctioned scratchpad under
`AppData/Local/Temp/claude/<session>/scratchpad`, which every role including
`pm` is told to use, or a `.crew/escape -> /elsewhere` symlink `pm` itself
staged under a path it is trusted to write -- refusing it would police a
location the repo write-scope rule was never written to reach. `pm` writing
outside the repo is `allow`, logged `outside-repo: ...`
(`_is_outside_repo`). This is judged on the REAL resolved path ONLY, same as
the escape case above it -- there is no separate "but the tool call NAMED a
path inside the repo" carve-out, because the guard's business is where the
write actually lands, not what the string said before the filesystem was
asked. `_DENY_ROLES` gets none of this: its restriction is "no `Write`/
`Edit` at all", not "confined to the repo", so an outside-repo write is a
different, stronger rule that role has no exception from.

A target on a DIFFERENT DRIVE than the repo root (Windows) is provably
outside the repo the same way -- `os.path.relpath` raises `ValueError`
for it, same as for an unrelated `TypeError`/`OSError` during resolution,
but the two are NOT the same fact: a different drive is CONFIRMED
outside, not merely unverifiable. `_real_repo_relative` returns the
sentinel `".."` for this one case specifically (the same string a
same-drive `../`-prefixed escape produces), so it gets the identical
`outside-repo: allow` answer without `_is_outside_repo` needing a third
code path. Reported and fixed 2026-09-19.

## Malformed hook input

Never lets an unexpected shape reach `sys.exit` as a bare traceback, which
`PreToolUse` would show as a non-blocking failure (any exit code other than
0 or 2 is NOT a block) -- an accident that ALLOWS a write is worse than a
correct block, for a role this table already knows is restricted. A JSON
array or scalar at the top level, a non-string `file_path`, or a non-string
`cwd` (which would otherwise reach `root`, and then every filesystem call
below it, including this file's OWN outermost exception handler's logging
call) is degraded to "cannot classify" / `"."` rather than crashing; an
exception this file did not anticipate is caught at the outermost level of
`main`, whose OWN logging is wrapped in a further try/except so IT cannot
raise a second time, and for `pm` or a `_DENY_ROLES` member still exits 2
rather than falling through to an accidental allow. Reported and fixed
2026-09-19.

Stdin is read as raw bytes (`sys.stdin.buffer`) and decoded as UTF-8
explicitly, with a leading BOM stripped, rather than via `sys.stdin.read()`
-- which decodes using `PYTHONIOENCODING` / the interpreter's default text
encoding, a setting this hook does not control and a caller's environment
can leave unset or wrong regardless of what bytes role-write-guard.ps1's
own stdin fix correctly sent. `role-write-guard.sh`/`.ps1` both also set
`PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` in the child environment as a
second, independent layer -- belt and braces for the input path, and the
actual fix for this script's own stdout/stderr writes of a non-ASCII path,
which still depend on the interpreter's text-mode default the same way
stdin used to. Reported and fixed 2026-09-19.

A `file_path` using Windows' `\\\\?\\` extended-length prefix is never
classified at all -- see `_is_extended_length_prefix_path` for why. An
earlier version of this file NORMALISED the prefix away
(`_strip_extended_prefix`) and then classified the result like any other
path. Codex round 5 on 2026-09-19 found that this is unsound, not just
imprecise: the `\\\\?\\` prefix exists specifically to make Win32 skip its
OWN path normalisation -- trailing dots and spaces are preserved, `..` is
NOT collapsed -- so stripping the prefix and then running this module's
normal classifier against the bare remainder answers a question about a
DIFFERENT path than the one Windows will actually open. `\\\\?\\C:\\repo\\
.crew.\\app.py` and `C:\\repo\\.crew\\app.py` are NOT the same file --
Windows preserves the trailing dot on `.crew.` under the extended-length
form -- but the old strip-then-normalise code treated them as
interchangeable, so a write actually landing in a directory literally
named `.crew.` (outside every scope `pm` is granted) classified as the
in-scope `.crew/app.py` and was allowed. `\\\\?\\` paths are now refused to
classify at all: for `pm` or a `_DENY_ROLES` member this fails CLOSED
(exit 2), and for every other role (including no `agent_type`) it allows,
since Claude Code itself never emits an extended-length path for a
`Write`/`Edit` call and there is nothing here worth blocking a role this
table already trusts with Write/Edit generally.
"""
import fnmatch
import json
import os
import re
import sys
import time

import crew_config
import crew_state

# --- The policy table -------------------------------------------------
#
# Source of truth for THIS hook. Kept as plain tuples, not derived from the
# agent files at hook time, so a PreToolUse call costs one process start and
# a few string compares, not 54 file reads on every Write/Edit in the
# session. `tests/test_role_write_guard.py` is what keeps this table honest
# against the files -- see the module docstring above.
#
# Built from `agents/*.md`'s `tools:` frontmatter on 2026-09-19: every role
# whose tools line names neither `Write` nor `Edit`.
_DENY_ROLES = frozenset({
    "analyst",
    "compliance-auditor",
    "dba",
    "explorer",
    "infrastructure-architect",
    "kimi-consult",
    "penetration-tester",
    "planner",
    "qa-researcher",
    "qa-reviewer",
    "researcher",
    "security",
})

# Every remaining role whose tools line grants BOTH Write and Edit, minus
# `pm`, which gets its own path-scoped branch below. Also built from
# `agents/*.md` on 2026-09-19.
_UNRESTRICTED_ROLES = frozenset({
    "ad-security-reviewer",
    "ai-writing-auditor",
    "angular-architect",
    "api-designer",
    "architect-reviewer",
    "backend-developer",
    "browser-tester",
    "code-reviewer",
    "database-administrator",
    "design-bridge",
    "developer",
    "docs-writer",
    "dotnet-core-expert",
    "dotnet-framework-4.8-expert",
    "exchange-online-specialist",
    "fintech-engineer",
    "git-workflow-manager",
    "graphql-architect",
    "legacy-modernizer",
    "microservices-architect",
    "multi-agent-coordinator",
    "network-engineer",
    "node-developer",
    "payment-integration",
    "php-pro",
    "platform-engineer",
    "power-automate-specialist",
    "powershell-5.1-expert",
    "powershell-7-expert",
    "powershell-security-hardening",
    "python-pro",
    "react-specialist",
    "rust-engineer",
    "scribe",
    "sharepoint-developer",
    "skill-author",
    "smoke-author",
    "sql-pro",
    "terraform-engineer",
    "windows-infra-admin",
    "workflow-orchestrator",
})

_PM_ROLE = "pm"

# `agents/pm.md:49-53`'s own prose, made mechanical. fnmatch, not pathlib
# glob: these run against a flat repo-relative STRING (see `_repo_relative`),
# not a filesystem walk, and fnmatch's `*` already matches across `/` the
# way a doubled `**` implies for a single string comparison -- the same
# choice `crew_guards.matches_production` makes for `production.*` patterns.
_PM_ALLOWED_PATTERNS = (
    ".crew/**",
    ".crew/*",
    "TODO.md",
    ".work/**",
    ".work/*",
    "docs/diagrams/**",
    "docs/diagrams/*",
)


_CREW_PREFIX = "crew:"


def _normalise_role(agent_type):
    """`agent_type` as a bare role name, or `None` if absent/blank.

    Strips ONLY a leading `crew:` -- see the module docstring's "What
    'unknown' means here" section for the wire-form uncertainty this exists
    to survive, and its "Malformed hook input" section for why the first
    draft (strip up to the LAST `:`, unconditionally) was wrong: it folded
    ANY plugin's `<namespace>:analyst` onto this table's own `analyst`
    entry, applying crew's deny-list to an agent this table has no business
    judging. A string that does not start with `crew:` is returned exactly
    as given (lowercased and stripped) precisely so it CANNOT match a bare
    crew role name by coincidence -- `classify` below falls through to
    `unknown-role:<value>` for it, carrying the full original value.
    """
    if not isinstance(agent_type, str):
        return None
    cleaned = agent_type.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith(_CREW_PREFIX):
        rest = lowered[len(_CREW_PREFIX):].strip()
        return rest or None
    return lowered


def _is_extended_length_prefix_path(path):
    """Is `path` spelled with Windows' `\\\\?\\` extended-length prefix
    (including the `\\\\?\\UNC\\` form, which also starts with `\\\\?\\`)?

    Round 3 (2026-09-19) NORMALISED this prefix away and classified the
    remainder like any other path -- `os.path.relpath` otherwise treats
    `\\\\?\\C:\\repo\\...` and `C:\\repo` as different mounts and raises,
    which read as "cannot classify" and incorrectly refused a legitimate,
    in-scope write. Codex round 5 found that normalising is itself wrong,
    not just the raising: `\\\\?\\` exists specifically so Win32 will SKIP
    its own path normalisation for this one call -- trailing dots and
    spaces are preserved on disk, and a literal `..` component is never
    collapsed. Stripping the prefix and running this module's ordinary
    classifier against the bare remainder answers a question about a
    DIFFERENT path than the one Windows actually opens. Concretely:
    `\\\\?\\C:\\repo\\.crew.\\app.py` (note the trailing dot on `.crew.`)
    strips to `C:\\repo\\.crew.\\app.py`, which this module's own path
    handling then further normalises to `C:\\repo\\.crew\\app.py` --
    in-scope for `pm` -- while Windows itself opens a directory literally
    named `.crew.`, distinct from `.crew` and outside every scope `pm` is
    granted. No classifier built to be faithful to ordinary Windows path
    semantics can also be faithful to a syntax whose entire purpose is
    bypassing those semantics, so this file does not try: `main` uses this
    check to skip classification entirely for such a path, rather than
    calling `_repo_relative`/`_real_repo_relative` on it at all.
    """
    return isinstance(path, str) and path.startswith("\\\\?\\")


def _repo_relative(root, file_path):
    """`file_path` relative to `root`, forward-slashed, or `None`. DISPLAY
    ONLY -- see `_real_repo_relative` for the string classification uses.

    `None` when `file_path` is empty/absent/not a string (a hook payload
    this script did not anticipate -- see the module docstring's "Malformed
    hook input" -- must degrade to "cannot classify" here rather than raise
    a `TypeError` out of `os.path.relpath`), or when it cannot be related to
    `root` at all (a different drive on Windows raises `ValueError` --
    treated as "cannot classify", handled by the caller exactly like an
    out-of-scope path for `pm` and exactly like "not unrestricted" for
    everyone else, never as "must be fine").
    """
    if not file_path or not isinstance(file_path, str):
        return None
    try:
        rel = os.path.relpath(file_path, root)
    except (ValueError, TypeError, OSError):
        return None
    return rel.replace(os.sep, "/")


def _resolve_real_target(file_path):
    """The REAL, symlink/junction-resolved absolute form of `file_path`.
    Dispatches on `os.name`, because Windows and POSIX apply `..` to a
    symlink/junction chain in OPPOSITE orders -- getting this backwards
    is a real escape in one direction and a false refusal in the other,
    both reported 2026-09-19, one round apart.

    **POSIX** (`_resolve_real_target_posix`): the kernel resolves each
    path component, including any symlink, DURING the walk itself, and
    `..` is applied AFTER, against wherever that walk landed.
    `.crew/link/../app.py`, with `.crew/link` a symlink to `src/subdir`,
    resolves `.crew/link` to `src/subdir` FIRST and pops `..` against
    THAT, landing in `src/app.py` -- outside a scope the lexical string
    alone would have called in-scope. `_resolve_real_target_posix`
    resolves-then-pops to match.

    **Windows** (`_resolve_real_target_windows`): the Win32 path
    canonicaliser collapses a literal `..` LEXICALLY, in the path
    string, BEFORE the filesystem driver ever sees it -- a reparse point
    (junction or symlink) at the component `..` just popped is never
    traversed at all. `.crew\\link\\..\\app.py`, with `.crew\\link` a
    junction to `src\\subdir`, collapses to `.crew\\app.py` lexically --
    `link` is popped as a plain path segment, its target never
    consulted -- and THAT is the path Windows actually opens (in scope
    for `pm`: allow). The reverse case is what makes resolve-then-pop
    actively wrong here, not just imprecise: `src\\link\\..\\new.py`,
    with `src\\link` a junction to `.crew\\subdir`, ALSO collapses `..`
    first (`src\\link\\..` -> `src`), so Windows writes `src\\new.py`,
    never touching `.crew` at all -- out of scope, block. Resolving
    `link` to `.crew/subdir` BEFORE popping `..` (the POSIX answer)
    would land back inside `.crew` and wrongly ALLOW an out-of-scope
    write. `_resolve_real_target_windows` collapses `..` lexically
    first, exactly mirroring the OS, then walks the remaining
    (`..`-free) path resolving junctions as it goes.

    Both branches split the raw path on `..`-free components before
    touching the filesystem. Only the WINDOWS branch splits on BOTH `\\`
    and `/` (`re.split(r"[\\\\/]+", ...)`) -- POSIX keeps `/` alone,
    since a literal backslash is a legal POSIX filename character and
    must never be treated as a separator there. Reported 2026-09-19: a
    Windows target named with forward slashes (`C:/repo/.crew/link/
    new.py`, which tools commonly send even on Windows) split into ONE
    component on `os.sep` (`\\`) alone under the earlier, separator-
    naive version of this function -- the walk below never actually
    walked anything, so a junction anywhere in the path was never
    followed at all.
    """
    if os.name == "nt":
        return _resolve_real_target_windows(file_path)
    return _resolve_real_target_posix(file_path)


def _resolve_real_target_posix(file_path):
    """POSIX half of `_resolve_real_target`: resolve-then-pop. Walks the
    path one component at a time, keeping only the RESOLVED form built
    up so far:
      * a plain name is appended, then that whole prefix is
        `os.path.realpath`'d if it exists on disk (resolving whatever
        symlink the newly-added component turned out to be, and
        everything already ahead of it in the same call, since
        `realpath` is itself recursive);
      * `..` pops the last RESOLVED component -- never a lexical one,
        because by the time `..` is reached every component before it
        has already gone through the `realpath` step above, exactly
        mirroring kernel path resolution;
      * a component that does not exist yet (the common case for a
        brand-new `Write` target) is kept exactly as given and resolved
        no further -- nothing on disk can have relinked something that
        was never there.
    """
    if os.path.isabs(file_path):
        absolute = file_path
    else:
        absolute = os.path.join(os.getcwd(), file_path)
    parts = [p for p in absolute.split("/") if p and p != "."]

    resolved_parts = []
    for part in parts:
        if part == "..":
            if resolved_parts:
                resolved_parts.pop()
            continue
        resolved_parts.append(part)
        current = "/" + "/".join(resolved_parts)
        if os.path.lexists(current):
            real = os.path.realpath(current)
            resolved_parts = [p for p in real.split("/") if p]

    return "/" + "/".join(resolved_parts) if resolved_parts else "/"


def _resolve_real_target_windows(file_path):
    """Windows half of `_resolve_real_target`: collapse `..` LEXICALLY
    first, matching Win32's own path canonicalisation, THEN walk the
    (now `..`-free) path resolving whatever junction or symlink exists
    at each step. Doing this POSIX-style (resolve-then-pop) on Windows
    is backwards in both directions -- see `_resolve_real_target`'s own
    docstring for the two-sided repro.
    """
    if os.path.isabs(file_path):
        absolute = file_path
    else:
        absolute = os.path.join(os.getcwd(), file_path)
    drive, rest = os.path.splitdrive(absolute)
    raw_parts = [p for p in re.split(r"[\\/]+", rest) if p and p != "."]

    lexical_parts = []
    for part in raw_parts:
        if part == "..":
            if lexical_parts:
                lexical_parts.pop()
            continue
        lexical_parts.append(part)

    resolved_parts = []
    for part in lexical_parts:
        resolved_parts.append(part)
        current = drive + "\\" + "\\".join(resolved_parts)
        if os.path.lexists(current):
            real = os.path.realpath(current)
            real_drive, real_rest = os.path.splitdrive(real)
            drive = real_drive
            resolved_parts = [p for p in real_rest.split(os.sep) if p]

    if resolved_parts:
        return drive + "\\" + "\\".join(resolved_parts)
    return drive + "\\"


def _real_repo_relative(root, file_path):
    """`file_path`'s REAL, resolved path relative to the REAL root, or
    `None`. THIS is the string `classify`/`_pm_in_scope` judge scope
    against -- never `_repo_relative`'s lexical one.

    A path that textually sits inside an allowed prefix can still, through a
    symlink or a Windows junction staged under that prefix, write somewhere
    else entirely once the tool actually opens it -- see the module
    docstring's "Symlinks and junctions" section. Resolving BOTH sides
    through the filesystem before comparing is what closes that; comparing
    a resolved target against a lexical root (or vice versa) would just
    move the gap rather than close it.

    `None` on the same "cannot classify" terms as `_repo_relative`: absent,
    not a string, or any `OSError`/`TypeError` resolving either side -- a
    permissions failure walking the filesystem is not evidence the write
    is in scope.

    A DIFFERENT DRIVE (Windows) is NOT one of those "cannot classify"
    cases, even though `os.path.relpath` raises `ValueError` for it the
    same way it does for other unrelatable paths -- reported and fixed
    2026-09-19: a target on `D:` with the repo on `C:` was previously
    caught by the same blanket `except`, returned `None`, and `pm` writing
    it was refused as "cannot classify" even though a different drive is
    PROVABLY outside the repo root, not merely unverifiable. This returns
    the sentinel `".."` for that case instead -- the exact string
    `_is_outside_repo` already treats as proof of a resolved escape (see
    that function's own docstring), so the different-drive case gets the
    SAME `outside-repo: allow` answer a same-drive `../`-prefixed escape
    does, without `_is_outside_repo` itself needing to know why.
    """
    if not file_path or not isinstance(file_path, str):
        return None
    try:
        real_target = _resolve_real_target(file_path)
        real_root = os.path.realpath(root)
    except (TypeError, OSError):
        return None
    try:
        rel = os.path.relpath(real_target, real_root)
    except ValueError:
        return ".."
    return rel.replace(os.sep, "/")


def _pm_in_scope(rel_path):
    if rel_path is None:
        return False
    return any(fnmatch.fnmatch(rel_path, pattern)
               for pattern in _PM_ALLOWED_PATTERNS)


def _is_outside_repo(rel_path):
    """True when `rel_path` -- a `_real_repo_relative` output -- names
    something outside the repo root: `os.path.relpath` prefixes a result
    with `..` when the target is not under `root`.

    Deliberately `False` for a bare `rel_path is None`: that is
    `_real_repo_relative`'s OTHER meaning, "cannot resolve this at all"
    (an absent or non-string `file_path` -- see the module docstring's
    "Malformed hook input"), and treating an unverifiable path as "known to
    be outside the repo" would let a malformed payload buy the exact
    "outside-repo, allow" exception a genuinely-resolved escape earns. A
    `..`-prefixed STRING is proof the resolution succeeded and landed
    outside; a bare `None` is not evidence of anything about location.
    """
    return rel_path is not None and (rel_path == ".." or rel_path.startswith("../"))


def classify(role, rel_path):
    """`(in_scope, reason)` for `role` writing to `rel_path` -- the REAL,
    symlink/junction-resolved path relative to the REAL repo root
    (`_real_repo_relative`'s output), NEVER the lexical one a tool call
    named (`_repo_relative`'s output is for DISPLAY only -- see `main`).

    `role` is already normalised (see `_normalise_role`) and may be `None`.

    This hook's whole purpose is the REPO's write scope, so once `pm`'s
    target is resolved through any symlink or junction in its path, if it
    lands OUTSIDE the repo root entirely -- a harness-sanctioned scratchpad
    path under `AppData/Local/Temp`, for instance, which every role
    including `pm` is told to use, or a `.crew/escape -> /elsewhere` symlink
    pm itself staged under a path it is trusted to write -- the write is not
    touching anything this guard governs at all, and refusing it polices a
    location the rule was never written to reach. Reported 2026-09-19.
    `_is_outside_repo` is the ONLY function that may answer this, and it is
    asked about `rel_path` -- the REAL path -- not the lexical one: judging
    by what the tool call merely NAMED would have to trust that string
    before the filesystem confirms it, which is the same class of gap
    `_real_repo_relative` exists to close for the in-scope case below.

    A target that resolves INSIDE the repo but outside `pm`'s permitted
    prefixes -- `.crew/escape -> src/`, still under the repo root -- is a
    DIFFERENT case and stays refused: `_pm_in_scope` below still runs for
    it, and `src/app.py` does not fnmatch `.crew/**`.

    Never raises -- every branch returns, and the fallback at the bottom is
    what makes a role this table has never heard of resolve to "unknown"
    rather than to an `IndexError` reaching the caller as a bare traceback,
    which on a `PreToolUse` hook would print to stderr and be read as a
    refusal reason nobody wrote.
    """
    if role is None:
        return True, "no-agent-type"
    if role in _DENY_ROLES:
        # Deliberately NOT given the same "outside this guard's jurisdiction"
        # exception as `pm` below. A deny-role's `tools:` frontmatter grants
        # neither `Write` nor `Edit` at all -- its restriction is "may not
        # write ANY file", not "may not write outside the repo" -- so an
        # outside-repo write is not a narrower case of the same rule, it is
        # a DIFFERENT, stronger rule this role has no exception from.
        return False, f"role `{role}` has no Write/Edit in its tools: grant"
    if role == _PM_ROLE:
        if _is_outside_repo(rel_path):
            return True, ("outside-repo: the resolved target is not under "
                           "the repo root, outside this guard's jurisdiction")
        if _pm_in_scope(rel_path):
            return True, "pm: path is in the allowed set"
        return False, ("pm may write only under .crew/**, TODO.md, "
                        ".work/**, docs/diagrams/**")
    if role in _UNRESTRICTED_ROLES:
        return True, f"role `{role}` is unrestricted"
    return True, f"unknown-role:{role}"


def _log(root, row):
    """Append one tab-separated row to `.crew/guard.log`. Best effort.

    Mirrors `crew_config._log_guard` exactly, including its two load-bearing
    rules, rather than importing it: never raises (a hook that dies writing
    its own audit line turns a logging failure into a blocked write, worse
    than a missing row), and NEVER creates `.crew/` -- see
    `crew_config._log_guard`'s docstring for why an allowed write in a plain
    repo must not be what silently adopts it into crew.
    """
    try:
        path = os.path.join(root, crew_state.GUARD_LOG_PATH)
        if not os.path.isdir(os.path.dirname(path)):
            return
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\t".join(row) + "\n")
    except OSError:
        pass


def _flatten(text):
    flat = text or "-"
    for char in ("\t", "\r", "\n"):
        flat = flat.replace(char, " ")
    return flat


def _permitted_text(role):
    return (
        ".crew/**, TODO.md, .work/**, docs/diagrams/**" if role == _PM_ROLE
        else "nothing (this role has no Write/Edit grant)"
    )


def _log_row(root, policy, decision, role, path_text, reason):
    """Build and append the one `.crew/guard.log` row for this decision.

    Six columns, not five: `reason` is its OWN column, appended last.
    An earlier draft computed `reason` (`no-agent-type`, `unknown-role:...`,
    "pm: path is in the allowed set", ...) and then never wrote it anywhere
    -- the module docstring and CONFIG.md Sec18 both promise the two
    distinct unknowns are "named differently in `.crew/guard.log` rather
    than merged into one unreadable 'allow' row", and the code did not keep
    that promise. Reported and fixed 2026-09-19. `_flatten` is applied to
    `reason` for the same tab/newline-safety reason it already applies to
    the path.
    """
    row = (
        str(int(time.time())),
        "roleWrites",
        policy,
        decision,
        role or "-",
        _flatten(path_text),
        _flatten(reason),
    )
    _log(root, row)


def _read_stdin_text():
    """Raw stdin, decoded as UTF-8 with a leading BOM stripped, INDEPENDENT
    of `PYTHONIOENCODING` / `PYTHONUTF8` or the OS locale's codepage.
    Returns `(text, error)`; `error` is `None` on success, a short
    description on failure. Never raises.

    `sys.stdin.buffer` is bytes, never text, so no environment setting can
    make this decode with the wrong codec. Reported 2026-09-19: plain
    `sys.stdin.read()` decodes using the interpreter's default text
    encoding, which a caller's environment can set to anything (or leave
    unset, falling back to the OS locale) -- so even a byte stream
    role-write-guard.ps1's own stdin fix sent correctly could still be
    MISDECODED here, on the python side, independent of what PowerShell
    did. Reading bytes and decoding them explicitly removes that
    dependency. The BOM strip moves here too (BOTH shells shared one
    Python implementation now have one, instead of role-write-guard.ps1
    carrying its own copy the .sh never had).
    """
    try:
        raw_bytes = sys.stdin.buffer.read()
    except (OSError, ValueError) as exc:
        return "", f"could not read stdin ({type(exc).__name__})"
    if raw_bytes[:3] == b"\xef\xbb\xbf":
        raw_bytes = raw_bytes[3:]
    try:
        return raw_bytes.decode("utf-8"), None
    except UnicodeDecodeError:
        return "", "stdin is not valid UTF-8"


def main(argv=None):  # pylint: disable=unused-argument
    raw, read_error = _read_stdin_text()
    if read_error:
        sys.stderr.write(
            f"role-write-guard: {read_error}; allowing the call unjudged.\n")
        return 0
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        # Cannot parse the hook's own input. This is a PreToolUse call this
        # script cannot judge at all -- fail OPEN on the classification (an
        # unreadable hook payload is not evidence a write is out of scope)
        # but say so on stderr, because a silently-swallowed parse error is
        # exactly the "unknown wearing the label of a check that happened"
        # failure CLAUDE.md names.
        sys.stderr.write(
            "role-write-guard: hook input did not parse as JSON; "
            "allowing the call unjudged.\n")
        return 0

    # A JSON payload need not be an object -- `[]` and `42` are both valid
    # JSON and both crash `data.get(...)` with an AttributeError, which
    # `sys.exit(main(...))` never gets a chance to turn into an exit code:
    # the exception reaches the interpreter directly and the process exits
    # 1, a NON-BLOCKING failure `PreToolUse` treats as noisy success. A
    # shape this script cannot even read a `tool_name` from is handled the
    # same as one that read no fields at all.
    if not isinstance(data, dict):
        data = {}

    tool_name = data.get("tool_name")
    if tool_name not in ("Write", "Edit"):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    if not isinstance(root, str):
        # A malformed payload (`"cwd": [1]`, `"cwd": 42`, ...) must not
        # propagate a non-string root into every filesystem call below.
        # Reported 2026-09-19: an earlier draft let this through, and a
        # non-string `root` reaching `os.path.join` inside the exception
        # handler's OWN logging call raised a SECOND, uncaught exception --
        # see that handler's docstring for the rest of this repro.
        # `os.environ.get` and the `"."` fallback are always strings, so
        # only `data.get("cwd")` can be the culprit.
        root = "."
    role = _normalise_role(data.get("agent_type"))

    # Everything from here on touches the filesystem (config, the target
    # path, possibly a symlink chain) and none of it may reach `sys.exit`
    # as a bare traceback -- see the module docstring's "Malformed hook
    # input". A role this table already knows is restricted (`pm` or a
    # `_DENY_ROLES` member) fails CLOSED on an unexpected exception, the
    # same direction every other unknown in this file fails; anything else
    # was already going to be allowed, so there is nothing an exception
    # here could make more permissive.
    try:
        resolved = crew_config.resolve_guard(root, "roleWrites")
        policy = resolved["effective"]

        # ONE rule, checked for BOTH layers -- see `crew_config.layer_state`
        # for the full reasoning. A layer that is CORRUPT (present but
        # unreadable as this key needs, including a directory at the
        # config path or an explicit `"guards": null`) forces `block`
        # UNCONDITIONALLY, regardless of what the ratchet already computed
        # from the surviving layer. Reported 2026-09-19, as three separate
        # findings this one rule now closes together: a directory at
        # `.crew/config.json` read as "absent" through the first fix's
        # `text is None` check; `{"guards": null}` read as an unset key
        # through `parsed.get("guards") is not None`; and -- the gap the
        # first fix's `if policy == "off"` guard could not see -- a
        # corrupt REPO config with a VALID, non-off global policy (say
        # `report`) resolved to that global value through the ordinary
        # ratchet without ever reaching the corruption check at all, so a
        # repo that used to say `block` and got corrupted read as `report`
        # -- which never blocks anything -- instead of the floor.
        repo_config_path = os.path.join(root, ".crew", "config.json")
        repo_state = crew_config.layer_state(repo_config_path)
        global_state = crew_config.layer_state(crew_config.GLOBAL_CONFIG_PATH)
        forced_by_corruption = repo_state == "corrupt" or global_state == "corrupt"

        if forced_by_corruption:
            policy = "block"
        elif policy == "off":
            return 0

        tool_input = data.get("tool_input") or {}
        file_path = (tool_input.get("file_path")
                     if isinstance(tool_input, dict) else None)

        if _is_extended_length_prefix_path(file_path):
            # See `_is_extended_length_prefix_path`'s own docstring: this
            # path is never classified at all -- skip `_repo_relative`/
            # `_real_repo_relative`/`classify` entirely and decide by role
            # alone, the same "scoped role" set the outermost exception
            # handler below already treats as restricted.
            restricted = role == _PM_ROLE or role in _DENY_ROLES
            decision = "block" if restricted else "allow"
            reason = ("extended-length path (\\\\?\\) is not classifiable; "
                       "refused for a scoped role" if restricted
                       else "extended-path-unclassified")
            _log_row(root, policy, decision, role, file_path, reason)
            if decision == "block":
                sys.stderr.write(
                    f"ROLE WRITE BLOCKED: role `{role}` may not write "
                    f"`{file_path}`.\n"
                    f"  Reason: {reason}\n"
                    "  A Windows \\\\?\\ extended-length path bypasses Win32's "
                    "own path normalisation (trailing dots/spaces kept, `..` "
                    "not collapsed) and cannot be judged against "
                    "guards.roleWrites' scope patterns -- refused outright "
                    "for a role this table restricts. See CONFIG.md "
                    "Section 18.\n"
                )
                return 2
            return 0

        # `rel_path` is lexical, for DISPLAY only -- what the tool call
        # NAMED. `scope_path` is filesystem-resolved, and is the ONLY one
        # `classify` ever judges against: what the write would actually
        # TOUCH once symlinks/junctions are followed, including whether
        # that lands outside the repo root entirely. See `_real_repo_
        # relative`'s and `classify`'s own docstrings.
        rel_path = _repo_relative(root, file_path)
        scope_path = _real_repo_relative(root, file_path)

        in_scope, reason = classify(role, scope_path)
        if forced_by_corruption:
            corrupt_layers = []
            if repo_state == "corrupt":
                corrupt_layers.append(".crew/config.json")
            if global_state == "corrupt":
                corrupt_layers.append("the machine-global config")
            reason = (" and ".join(corrupt_layers)
                       + " exists but could not be read as guards.roleWrites"
                         " needs; " + reason)
        # Three decisions, not two. "report" is its own value rather than
        # collapsing into "allow": under `guards.roleWrites: report` an
        # out-of-scope write is let through exactly like an in-scope one,
        # but the whole point of `report` is telling the operator which
        # writes WOULD be refused under `block` -- logging it as bare
        # "allow" would erase the one fact `report` exists to keep.
        if in_scope:
            decision = "allow"
        elif policy == "block":
            decision = "block"
        else:
            decision = "report"

        _log_row(root, policy, decision, role, rel_path or file_path, reason)

        if decision == "block":
            corruption_note = (
                "  a config layer exists but did not parse; failing closed "
                "to block rather than trusting an unreadable file.\n"
                if forced_by_corruption else "")
            sys.stderr.write(
                f"ROLE WRITE BLOCKED: role `{role}` may not write "
                f"`{rel_path or file_path}`.\n"
                f"  Reason: {reason}\n"
                f"  Permitted for this role: {_permitted_text(role)}\n"
                f"{corruption_note}"
                "  This is guards.roleWrites: block, in .crew/config.json or "
                "the machine-global config. See CONFIG.md Section 18.\n"
            )
            return 2
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        # The outermost safety net must never itself raise. Reported
        # 2026-09-19: a malformed `cwd` (a JSON array) reached `root`
        # unsanitised in an earlier draft, and THIS handler's own
        # `_log_row(root, ...)` call raised a SECOND, uncaught `TypeError`
        # building `.crew/guard.log`'s path from a non-string `root` --
        # crashing the process with exit 1, which `PreToolUse` treats as
        # non-blocking (an accidental allow, for a role -- `pm` -- this
        # table already knows is restricted). `root` is sanitised to a
        # string earlier now, closing that specific repro, but this
        # handler also does not trust that as its only guard: its own
        # logging is wrapped in its own try/except, and the fail-closed
        # decision below is computed from `role` via `str()` only, which
        # cannot raise for any value `_normalise_role` can produce (`None`
        # or an already-lowercased string).
        role_text = str(role) if role is not None else None
        restricted = role_text == _PM_ROLE or role_text in _DENY_ROLES
        try:
            _log_row(root, "error",
                      "block" if restricted else "allow",
                      role, "-", f"internal-error:{type(exc).__name__}")
        except Exception:  # pylint: disable=broad-except
            pass
        if restricted:
            try:
                sys.stderr.write(
                    f"ROLE WRITE BLOCKED: role `{role}`'s write could not be "
                    f"classified ({type(exc).__name__}); failing closed for "
                    "a restricted role rather than allowing an unverifiable "
                    "write.\n"
                    f"  Permitted for this role: {_permitted_text(role)}\n"
                    "  See CONFIG.md Section 18.\n"
                )
            except Exception:  # pylint: disable=broad-except
                pass
            return 2
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
