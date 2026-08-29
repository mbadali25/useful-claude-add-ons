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
    """Return (frontmatter dict, body). The dict is None when there is none."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if not text.startswith("---\n"):
        return None, text
    end = text.index("\n---\n", 3)
    fields = {}
    for line in text[4:end].split("\n"):
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields, text[end + 5:]


AGENTS = {os.path.basename(f)[:-3] for f in glob.glob("agents/*.md")}
COMMANDS = {os.path.basename(f)[:-3] for f in glob.glob("commands/*.md")}
SKILLS = {os.path.basename(os.path.dirname(f)) for f in glob.glob("skills/*/SKILL.md")}

# Roles that are deliberately NOT on the default tier. Anything absent from this
# map must declare `sonnet`; see check_agents for why each exception exists.
MODEL_TIER = {"pm": "opus", "qa-reviewer": "opus"}

KNOWN_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit", "Bash", "PowerShell", "Grep", "Glob",
    "Agent", "Task", "Skill", "WebSearch", "WebFetch", "ToolSearch", "NotebookEdit",
}
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
            unknown = [t.strip() for t in tools.split(",")
                       if t.strip() and t.strip() not in KNOWN_TOOLS]
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
        unknown = [t.strip() for t in tools.split(",")
                   if t.strip() and t.strip() not in KNOWN_TOOLS]
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
