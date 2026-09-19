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
    for why the default is not the floor. **Exception:** if `.crew/config.json`
    EXISTS but does not parse into the shape this key needs (see
    `crew_config.repo_config_is_corrupt`), `off` is NOT trusted -- the
    policy is forced to `block` instead, because a repo that once armed this
    guard and now has a corrupted config file is not the same fact as a repo
    that never armed it, and CLAUDE.md's "unknown collapsing into the
    safe-looking value" is exactly this case if left alone. Reported and
    fixed 2026-09-19.
  * `report` -- every decision (in-scope AND out-of-scope) is allowed, and
    every decision is appended to `.crew/guard.log`.
  * `block` -- an out-of-scope write is refused (exit 2, message on
    stderr naming the role, the path and the permitted set); an in-scope
    write is allowed. Both are logged.

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

## Malformed hook input

Never lets an unexpected shape reach `sys.exit` as a bare traceback, which
`PreToolUse` would show as a non-blocking failure (any exit code other than
0 or 2 is NOT a block) -- an accident that ALLOWS a write is worse than a
correct block, for a role this table already knows is restricted. A JSON
array or scalar at the top level, or a non-string `file_path`, is degraded
to "cannot classify" rather than crashing; an exception this file did not
anticipate is caught at the outermost level of `main` and, for `pm` or a
`_DENY_ROLES` member, still exits 2 rather than falling through to an
accidental allow.
"""
import fnmatch
import json
import os
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

    `file_path` may not exist yet -- `Write` creates new files -- so this
    cannot just call `os.path.realpath(file_path)` and trust it: this walks
    UP from `file_path` to the deepest ancestor that actually exists on
    disk (`os.path.lexists`, which is true for a symlink even when what it
    points at is missing, so a link itself always counts as "exists" for
    this walk), `os.path.realpath`s THAT ancestor -- which resolves any
    symlink or, on Windows from Python 3.8 on, junction earlier in the
    chain -- and re-appends the not-yet-existing tail lexically, since
    nothing on disk can have relinked a component that is not there yet.

    Returns `file_path` unchanged (as an absolute path) if nothing on the
    walk up exists at all, e.g. a bare relative name with no real parent --
    there is then nothing to resolve against, and the caller's classify
    step treats an unrelatable path as out of scope regardless.
    """
    path = os.path.abspath(file_path)
    tail = []
    current = path
    while current and not os.path.lexists(current):
        parent, name = os.path.split(current)
        if not name or parent == current:
            break
        tail.append(name)
        current = parent
    if not os.path.lexists(current):
        return path
    resolved = os.path.realpath(current)
    for name in reversed(tail):
        resolved = os.path.join(resolved, name)
    return resolved


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
    not a string, or unrelatable to the resolved root (a different drive, or
    any `OSError` resolving either side -- a permissions failure walking the
    filesystem is not evidence the write is in scope).
    """
    if not file_path or not isinstance(file_path, str):
        return None
    try:
        real_target = _resolve_real_target(file_path)
        real_root = os.path.realpath(root)
        rel = os.path.relpath(real_target, real_root)
    except (ValueError, TypeError, OSError):
        return None
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


def main(argv=None):  # pylint: disable=unused-argument
    raw = sys.stdin.read()
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

        forced_by_corruption = False
        if policy == "off":
            if crew_config.repo_config_is_corrupt(root):
                policy = "block"
                forced_by_corruption = True
            else:
                return 0

        tool_input = data.get("tool_input") or {}
        file_path = (tool_input.get("file_path")
                     if isinstance(tool_input, dict) else None)
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
            reason = (".crew/config.json exists but could not be parsed as "
                       "guards.roleWrites needs; " + reason)
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
                "  .crew/config.json exists but did not parse; failing "
                "closed to block rather than trusting an unreadable file.\n"
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
        restricted = role == _PM_ROLE or role in _DENY_ROLES
        _log_row(root, "error",
                  "block" if restricted else "allow",
                  role, "-", f"internal-error:{type(exc).__name__}")
        if restricted:
            sys.stderr.write(
                f"ROLE WRITE BLOCKED: role `{role}`'s write could not be "
                f"classified ({type(exc).__name__}); failing closed for a "
                "restricted role rather than allowing an unverifiable "
                "write.\n"
                f"  Permitted for this role: {_permitted_text(role)}\n"
                "  See CONFIG.md Section 18.\n"
            )
            return 2
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
