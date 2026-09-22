"""Structural validation for crew's commands, agents and skills.

    python hooks/scripts/_test/validate-prompts.py

Checks what a machine can check: that frontmatter parses, that every named tool
exists, that referenced agents and plugin paths resolve, that a read-only agent
holds no write tools, and that a command spawning a subagent is permitted to.

It does NOT check whether the prompts produce good work. They are instructions
to a model, and only a live session on a real ticket exercises that - which is
what setup phase 7 is for. Passing this file means the wiring is sound, not
that the crew is any good.

Exits 1 if anything failed, so it can gate a commit.
"""

import glob
import os
import re
import sys

try:
    import yaml
except ImportError as exc:  # pragma: no cover - CI job, not a test
    # Fail LOUDLY rather than falling back to the line-splitting parser this
    # file used to ship. A degraded parse here is indistinguishable from a
    # clean run: it reports passes for files the loader will refuse. If this
    # fires in CI, the workflow is missing its `pip install pyyaml`.
    sys.stderr.write(
        "validate-prompts.py needs PyYAML to parse frontmatter the way the "
        "loader does.\nInstall it (`pip install pyyaml`) and re-run. Refusing "
        "to validate with a weaker parser than the thing being validated.\n"
    )
    raise SystemExit(1) from exc

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

PASSED = []
FAILED = []


def ok(msg):
    """Record a passing check."""
    PASSED.append(msg)


def bad(msg):
    """Record a failing check."""
    FAILED.append(msg)


def frontmatter(path):
    """Return (frontmatter dict, body). The dict is None when there is none.

    This parses YAML, and it did not used to. The old version split each line
    on the first `:` and kept the halves, which accepts text the loader
    rejects: `commands/pm.md` shipped an unquoted `argument-hint:` whose value
    was a bracketed, nested flow sequence, PyYAML refused it at the `|`, and
    Claude Code therefore did not load `/crew:pm` at all -- while this script
    reported 293 passes and zero failures.

    A validator whose parse is WEAKER than the loader's cannot fail where the
    loader fails; it can only agree with itself. That is this repo's named bug
    class -- a check placed where the evidence has already been dropped -- in
    the one script whose whole job is to catch exactly this.
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if not text.startswith("---\n"):
        return None, text
    end = text.index("\n---\n", 3)
    raw = text[4:end]
    try:
        fields = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        detail = str(exc).replace("\n", " ")
        bad(f"{path}: frontmatter is not valid YAML, so this file will not "
            f"load: {detail}")
        return {}, text[end + 5:]
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        bad(f"{path}: frontmatter parsed as {type(fields).__name__}, not a "
            f"mapping. It must be `key: value` pairs.")
        return {}, text[end + 5:]
    # Every later check indexes this like a string map and compares with `in`.
    # A value that is legitimately a list or bool would otherwise raise inside
    # an unrelated check and read as that check failing.
    return {str(k): v if isinstance(v, str) else str(v)
            for k, v in fields.items()}, text[end + 5:]


AGENTS = {os.path.basename(f)[:-3] for f in glob.glob("agents/*.md")}
COMMANDS = {os.path.basename(f)[:-3] for f in glob.glob("commands/*.md")}
SKILLS = {os.path.basename(os.path.dirname(f)) for f in glob.glob("skills/*/SKILL.md")}

# Roles that are deliberately NOT on the default tier. Anything absent from this
# map must declare `sonnet`; see check_agents for why each exception exists.
MODEL_TIER = {"pm": "opus", "qa-reviewer": "opus"}

KNOWN_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit", "Bash", "PowerShell", "Grep", "Glob",
    "Agent", "Task", "Skill", "WebSearch", "WebFetch", "ToolSearch", "NotebookEdit",
    # The standing PM is reached by name rather than respawned, which needs both
    # of these: ListAgents to find it, SendMessage to continue it.
    "ListAgents", "SendMessage",
    # A crew SUBAGENT cannot prompt -- `AskUserQuestion` is documented as
    # unavailable in agents spawned via the Task tool, and a subagent blocking
    # on a prompt would stall a dispatch nobody is watching. So a role that
    # needs a decision ends its report with a `**Decision needed:**` block, and
    # the main session RENDERS it. That renderer is a command, not an agent,
    # which is why this name belongs here: `/crew:pm` carries it in
    # `allowed-tools`, and without it the command is told to ask and has no
    # tool to ask with -- it does not error, it quietly does something else.
    "AskUserQuestion",
}

# An MCP tool's name is `mcp__<server>__<tool>`, and which servers exist is a
# property of the machine, not of this repository -- there is no list here to
# check against. Validating the shape still catches the mistake this check is
# for (a typo in a name, or a tool invented wholesale), while letting an agent
# name a real MCP tool it needs. Refusing them outright would push authors to
# describe the tool in prose instead, which produces exactly the failure this
# suite exists to catch: an instruction with no route to execute.
MCP_TOOL = re.compile(r"^mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")


# A SCOPED grant -- `Bash(python3 *)` -- is REFUSED, and the refusal is the
# point. The form parses, and other plugins ship it: dotnet-pilot's
# dnp-architect carries `Bash(dotnet:*)`. It is NOT ENFORCED. Measured
# 2026-09-22 by dispatching that agent and running `ls /` and `whoami`, neither
# of which is a dotnet command: both ran, no denial, no prompt. Whole-tool
# grants ARE enforced -- an agent with no `Bash` in its list reports having no
# shell tool at all -- so removing a NAME works and narrowing one does not.
#
# Accepting the scoped form would let a crew agent declare a restriction that
# does nothing while reading, in review, as though it restricted something.
# That is this repo's named recurring bug: an unknown collapsing into the
# safe-looking value. So it is rejected with the reason attached.
SCOPED_TOOL = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\((.+)\)$")


def unknown_tools(tools):
    """The names in a comma-separated `tools:` value that nothing recognises."""
    unknown = []
    for raw in tools.split(","):
        name = raw.strip()
        if not name:
            continue
        scoped = SCOPED_TOOL.match(name)
        if scoped:
            unknown.append(
                f"{name} (scoped tool specifiers are NOT enforced by the "
                f"runtime - use plain '{scoped.group(1)}' and say in the file "
                f"that it is not narrowed)")
            continue
        if name in KNOWN_TOOLS or MCP_TOOL.match(name):
            continue
        unknown.append(raw.strip())
    return unknown


SPAWNABLE = "|".join(sorted(AGENTS)) or "$^"
PLUGIN_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+)")


def check_plugin_paths(name, body):
    """Every ${CLAUDE_PLUGIN_ROOT} path a file names must exist."""
    for match in PLUGIN_PATH.finditer(body):
        path = match.group(1).rstrip(".,`)")
        if not os.path.exists(path):
            bad(f"{name}: names missing path {path}")


def check_commands():
    """Frontmatter, tool names, subagent permission, referenced paths."""
    print(f"=== COMMANDS ({len(COMMANDS)}) ===")
    for path in sorted(glob.glob("commands/*.md")):
        name = os.path.basename(path)
        fields, body = frontmatter(path)
        if fields is None:
            bad(f"{name}: no YAML frontmatter")
            continue

        desc = fields.get("description", "")
        if not desc:
            bad(f"{name}: no description")
        elif len(desc) > 120:
            bad(f"{name}: description is {len(desc)} chars; keep it to one line")
        else:
            ok(f"{name}: description")

        tools = fields.get("allowed-tools", "")
        if not tools:
            bad(f"{name}: no allowed-tools")
        else:
            unknown = unknown_tools(tools)
            if unknown:
                bad(f"{name}: unknown tool(s) {unknown}")
            else:
                ok(f"{name}: allowed-tools")

        for match in re.finditer(r"`?crew:([a-z-]+)`?", body):
            target = match.group(1)
            if target in COMMANDS or target in SKILLS or target in AGENTS:
                continue
            bad(f"{name}: references crew:{target}, which is not an agent, command or skill")

        check_plugin_paths(name, body)

        # (?<!/) excludes a SLASH-COMMAND reference: `/crew:pm` is an
        # instruction to the human or a pointer to another command, not a
        # subagent dispatch. Several names are both an agent and a command
        # (pm, plan, review), so without this a file that only mentions
        # `/crew:pm` is told to declare the Agent tool it never uses.
        if re.search(rf"(?<!/)crew:({SPAWNABLE})", body):
            if "Agent" not in tools:
                bad(f"{name}: spawns a subagent but allowed-tools has no Agent")
            else:
                ok(f"{name}: Agent permitted for the subagents it spawns")

        if len(body.strip()) < 200:
            bad(f"{name}: body is only {len(body.strip())} chars")


def check_agents():
    """Name matches filename, no unsupported keys, read-only means read-only."""
    print(f"=== AGENTS ({len(AGENTS)}) ===")
    for path in sorted(glob.glob("agents/*.md")):
        name = os.path.basename(path)
        fields, body = frontmatter(path)
        if fields is None:
            bad(f"{name}: no YAML frontmatter")
            continue

        if fields.get("name") != name[:-3]:
            bad(f"{name}: name '{fields.get('name')}' does not match the filename")
        else:
            ok(f"{name}: name matches filename")

        if fields.get("description"):
            ok(f"{name}: description")
        else:
            bad(f"{name}: no description")

        for key in fields:
            if key not in ("name", "description", "tools", "model"):
                bad(f"{name}: unsupported frontmatter key '{key}' - silently ignored")

        tools = fields.get("tools", "")
        unknown = unknown_tools(tools)
        if unknown:
            bad(f"{name}: unknown tool(s) {unknown}")
        else:
            ok(f"{name}: tools")

        model = fields.get("model", "inherit")
        if model not in ("inherit", "opus", "sonnet", "haiku"):
            bad(f"{name}: unrecognised model '{model}'")
        elif model != MODEL_TIER.get(name[:-3], "sonnet"):
            # The tiering is a design decision, not a default: the PM holds the
            # project picture every dispatch derives from, qa-reviewer is the
            # same-family fallback and the model tier is the only compensation
            # left when Codex is absent, and every other role has a narrow brief
            # a fast model does well. `inherit` is not an option for any of them
            # - it silently makes the tier depend on whoever spawned the agent.
            bad(f"{name}: model '{model}' should be "
                f"'{MODEL_TIER.get(name[:-3], 'sonnet')}'")
        else:
            ok(f"{name}: model")

        readonly = "read-only" in fields.get("description", "").lower()
        if readonly or "Read-only" in body[:400]:
            for write_tool in ("Write", "Edit"):
                if write_tool in tools:
                    bad(f"{name}: described as read-only but holds {write_tool}")

        if len(body.strip()) < 200:
            bad(f"{name}: body is only {len(body.strip())} chars")


def check_skills():
    """Name matches directory, supported keys only, referenced paths exist."""
    print(f"=== SKILLS ({len(SKILLS)}) ===")
    total = 0
    for path in sorted(glob.glob("skills/*/SKILL.md")):
        directory = os.path.basename(os.path.dirname(path))
        fields, body = frontmatter(path)
        if fields is None:
            bad(f"{directory}: no frontmatter")
            continue

        if fields.get("name") != directory:
            bad(f"{directory}: name '{fields.get('name')}' does not match the directory")
        else:
            ok(f"{directory}: name matches directory")

        desc = fields.get("description", "")
        if not desc:
            bad(f"{directory}: no description")
        total += len(desc)

        for key in fields:
            if key not in ("name", "description", "license", "allowed-tools"):
                bad(f"{directory}: unsupported frontmatter key '{key}'")

        check_plugin_paths(directory, body)
    return total


def main():
    """Run every check and report."""
    check_commands()
    check_agents()
    description_chars = check_skills()

    print()
    print(f"PASS: {len(PASSED)} checks")
    print(f"FAIL: {len(FAILED)}")
    for failure in FAILED:
        print(f"   - {failure}")
    print()
    print("always-loaded skill description cost: "
          f"{description_chars} chars (~{description_chars // 4} tokens)")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
