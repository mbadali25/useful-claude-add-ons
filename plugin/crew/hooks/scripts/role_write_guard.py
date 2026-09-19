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
`_normalise_role` strips everything up to and including the LAST `:` before
matching -- `"crew:pm"` and `"pm"` both resolve to `"pm"`. If the real wire
form turns out to be neither, this hook still fails to the safe side: an
unmatched value is `unknown-role`, which allows and logs rather than
stranding the role.

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


def _normalise_role(agent_type):
    """`agent_type` as a bare role name, or `None` if absent/blank.

    Strips up to and including the LAST `:` -- see the module docstring's
    "What 'unknown' means here" section for why: this repo's own agents are
    reachable through the Agent tool as `crew:pm`, `crew:analyst`, etc. in at
    least one listing observed this session, and the field was not confirmed
    live against a real dispatched subagent. Stripping a prefix that is not
    there is a no-op, so this is safe either way the wire form turns out to
    be.
    """
    if not isinstance(agent_type, str):
        return None
    cleaned = agent_type.strip()
    if not cleaned:
        return None
    return cleaned.rsplit(":", 1)[-1].strip().lower() or None


def _repo_relative(root, file_path):
    """`file_path` relative to `root`, forward-slashed, or `None`.

    `None` when `file_path` is empty/absent, or when it cannot be related to
    `root` at all (a different drive on Windows raises `ValueError` from
    `os.path.relpath` -- treated as "cannot classify", handled by the caller
    exactly like an out-of-scope path for `pm` and exactly like "not
    unrestricted" for everyone else, never as "must be fine").
    """
    if not file_path:
        return None
    try:
        rel = os.path.relpath(file_path, root)
    except ValueError:
        return None
    return rel.replace(os.sep, "/")


def _pm_in_scope(rel_path):
    if rel_path is None:
        return False
    return any(fnmatch.fnmatch(rel_path, pattern)
               for pattern in _PM_ALLOWED_PATTERNS)


def classify(role, rel_path):
    """`(in_scope, reason)` for `role` writing to `rel_path`.

    `role` is already normalised (see `_normalise_role`) and may be `None`.
    Never raises -- every branch returns, and the fallback at the bottom is
    what makes a role this table has never heard of resolve to "unknown"
    rather than to an `IndexError` reaching the caller as a bare traceback,
    which on a `PreToolUse` hook would print to stderr and be read as a
    refusal reason nobody wrote.
    """
    if role is None:
        return True, "no-agent-type"
    if role in _DENY_ROLES:
        return False, f"role `{role}` has no Write/Edit in its tools: grant"
    if role == _PM_ROLE:
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

    tool_name = data.get("tool_name")
    if tool_name not in ("Write", "Edit"):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."

    resolved = crew_config.resolve_guard(root, "roleWrites")
    policy = resolved["effective"]

    if policy == "off":
        return 0

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    role = _normalise_role(data.get("agent_type"))
    rel_path = _repo_relative(root, file_path)

    in_scope, reason = classify(role, rel_path)
    # Three decisions, not two. "report" is its own value rather than
    # collapsing into "allow": under `guards.roleWrites: report` an
    # out-of-scope write is let through exactly like an in-scope one, but the
    # whole point of `report` is telling the operator which writes WOULD be
    # refused under `block` -- logging it as bare "allow" would erase the one
    # fact `report` exists to keep.
    if in_scope:
        decision = "allow"
    elif policy == "block":
        decision = "block"
    else:
        decision = "report"

    row = (
        str(int(time.time())),
        "roleWrites",
        policy,
        decision,
        role or "-",
        _flatten(rel_path or file_path),
    )
    _log(root, row)

    if decision == "block":
        permitted = (
            ".crew/**, TODO.md, .work/**, docs/diagrams/**" if role == _PM_ROLE
            else "nothing (this role has no Write/Edit grant)"
        )
        sys.stderr.write(
            f"ROLE WRITE BLOCKED: role `{role}` may not write "
            f"`{rel_path or file_path}`.\n"
            f"  Reason: {reason}\n"
            f"  Permitted for this role: {permitted}\n"
            "  This is guards.roleWrites: block, in .crew/config.json or "
            "the machine-global config. See CONFIG.md Section 18.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
