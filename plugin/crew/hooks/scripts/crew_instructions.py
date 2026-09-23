"""Generated instruction surface: `.claude/rules/<subsystem>.md`, `AGENTS.md`,
and Codex's `.codex/hooks.json` + `.codex/config.toml`, all from what the repo
already records (the code map, `.crew/verify.json`) and from one hook table.

    python3 crew_instructions.py rules  [--root R] [--check]
    python3 crew_instructions.py agents [--root R] [--check]
    python3 crew_instructions.py codex  [--root R] [--check] [--plugin-root P] [--force]
    python3 crew_instructions.py codex-probe [--root R]
    python3 crew_instructions.py claude-hooks     # the hooks.json entries, for registration

Budgets (docs/review/04-redesign.md, "Instruction surface"): a rules file is at
most RULES_MAX_LINES lines, `paths:`-scoped, and carries the sha256 of the note
it came from; AGENTS.md is at most AGENTS_MAX_LINES. `--check` exits 1 on drift
-- a generated file missing, stale against its source, or orphaned -- and
writes nothing. Hand-written files (no `crew:generated` marker) are never
overwritten or reported as orphans; one sitting at a path a generated file
needs is left alone on a write and FAILS `--check`, because the generated
output that path should hold is absent.

`.codex/hooks.json` cannot carry a comment, so "generated" there means every
hook in it runs crew-context; anything else is hand-written and refused
without `--force`. It holds this machine's absolute plugin paths -- no Codex
variable for a plugin root was found in the 0.155.1 strings -- so it is
MACHINE-LOCAL: regenerate it per machine and do not commit it.

**Codex claims are labelled by how they were established.** The hook schema
keys used below (`matcher`, `hooks`, `type`, `command`, `commandWindows`,
`timeout`) and the event names were read out of the codex 0.155.1 binary's
strings on 2026-09-23 -- DERIVED from the binary, not from documentation.
`codex features list` on that build reports `hooks stable true`. Whether a
generated hook's `additionalContext` actually reaches the Codex model has NOT
been measured, which is why `codex-probe` reports "configured, not proven"
until the context log records a Codex invocation, and even then only claims
the hook was invoked.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

import crew_context
from crew_common import read_text

GENERATOR_VERSION = "1"
RULES_MAX_LINES = 30
AGENTS_MAX_LINES = 80
MARKER = "crew:generated"
KEEP_START, KEEP_END = "<!-- crew:keep:start -->", "<!-- crew:keep:end -->"
SCRIPT = "crew-context"
VAULT_MATCHER = "mcp__.*(obsidian|vault|basic[-_]memory).*"

# The one table both harnesses' registrations are rendered from. `codex`
# overrides a row's matcher for Codex, whose file-edit tool is `apply_patch`;
# None there means the row is not registered for Codex at all.
HOOK_TABLE = (
    {"event": "SessionStart", "matcher": None, "codex": None, "timeout": 20},
    {"event": "UserPromptSubmit", "matcher": None, "codex": None, "timeout": 15},
    {"event": "PostToolUse", "matcher": "Read|Edit|Write|MultiEdit",
     "codex": "apply_patch|Edit|Write", "timeout": 10},
    {"event": "PostToolUse", "matcher": VAULT_MATCHER, "codex": VAULT_MATCHER, "timeout": 10},
    {"event": "SubagentStart", "matcher": None, "codex": None, "timeout": 15},
)


def _sha(text):
    return hashlib.sha256((GENERATOR_VERSION + "\0" + text).encode("utf-8")).hexdigest()[:16]


def rule_digest(sub, covers):
    """The recorded source hash: everything the rule is rendered from, so a
    changed `paths`, anchor, note filename or subsystem name moves it too."""
    return _sha(json.dumps([sub["name"], sub["file"], list(sub["paths"]), sub["anchor"],
                            sub["body"], covers.get(sub["name"], "")]))


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# .claude/rules/<subsystem>.md

def render_rule(sub, covers):
    """The rule file for one code-map note, or None when it has no paths --
    a rules file without `paths:` loads in every session, which is the
    opposite of what a subsystem rule is for."""
    if not sub["paths"]:
        return None
    digest = rule_digest(sub, covers)
    rest = ["---",
            f"<!-- {MARKER} source={sub['file']} sha256={digest} -- do not hand-edit;"
            " regenerate with crew_instructions.py rules -->",
            f"# {sub['name']}",
            f"Code map anchor `{sub['anchor'] or 'none'}`; if it is behind HEAD, re-check with "
            f"`git diff --name-only {sub['anchor'] or '<anchor>'}..HEAD -- <cited paths>`."]
    if covers.get(sub["name"]):
        rest.append("Covers: " + covers[sub["name"]])
    tail = [f"Full note: `{sub['file']}`."]
    # Paths get what the fixed lines leave, less two for a title and one
    # bullet. Past that the list is cut and a YAML comment says how many
    # paths the rule does NOT load for, and where the full list is.
    paths = [f'  - "{p}"' for p in sub["paths"]]
    room_paths = RULES_MAX_LINES - 2 - len(rest) - len(tail) - 2
    if len(paths) > room_paths:
        shown = max(1, room_paths - 1)
        paths = paths[:shown] + [f"  # +{len(sub['paths']) - shown} more paths not scoped here;"
                                 f" see {sub['file']}"]
    head = ["---", "paths:"] + paths + rest
    marks = crew_context.bullets(sub["body"], "Landmines", limit=20, width=220)
    title = "## Landmines"
    if not marks:
        marks = crew_context.bullets(sub["body"], "Entry points", limit=20, width=220)
        title = "## Entry points"
    room = RULES_MAX_LINES - len(head) - len(tail) - 1
    body = [title] + ["- " + m for m in marks[:max(0, room)]] if marks and room > 0 else []
    lines = head + body + tail
    # The final word on the budget, whatever the arithmetic above assumed:
    # drop bullets from the end, then the title, until it fits.
    while len(lines) > RULES_MAX_LINES and body:
        body.pop()
        if body == [title]:
            body = []
        lines = head + body + tail
    if len(lines) > RULES_MAX_LINES:
        return None
    return "\n".join(lines) + "\n"


def expected_rules(root):
    covers = crew_context.index_covers(root)
    out = {}
    for sub in crew_context.subsystems(root):
        text = render_rule(sub, covers)
        if text is not None:
            out[os.path.join(root, ".claude", "rules", sub["name"] + ".md")] = text
    return out


def _is_generated(path):
    return MARKER in (read_text(path) or "")[:2000]


def _hand_written(rel, check):
    """A file with no marker at a path generated output needs. Left alone on
    a write; in --check it is drift, because what should be there is not."""
    if check:
        return f"hand-written file blocks generated output: {rel}"
    return f"hand-written, left alone: {rel}"


def rules(root, check=False):
    """(problems, written). Problems are drift in --check mode, and
    hand-written files left alone in either mode."""
    expected = expected_rules(root)
    problems, written = [], []
    for path, text in sorted(expected.items()):
        rel = os.path.relpath(path, root)
        current = read_text(path)
        if current is not None and not _is_generated(path):
            problems.append(_hand_written(rel, check))
            continue
        if current == text:
            continue
        if check:
            problems.append(("stale: " if current is not None else "missing: ") + rel)
        else:
            _write(path, text)
            written.append(rel)
    rules_dir = os.path.join(root, ".claude", "rules")
    try:
        existing = sorted(os.listdir(rules_dir))
    except OSError:
        existing = []
    for name in existing:
        path = os.path.join(rules_dir, name)
        if name.endswith(".md") and path not in expected and _is_generated(path):
            rel = os.path.relpath(path, root)
            if check:
                problems.append("orphan: " + rel)
            else:
                os.unlink(path)
                written.append("removed " + rel)
    return problems, written


# --------------------------------------------------------------------------
# AGENTS.md

def _verify_commands(root):
    text = read_text(os.path.join(root, ".crew", "verify.json"))
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    commands = []
    for rule in data.get("rules", []) if isinstance(data, dict) else []:
        for command in (rule.get("run") or []) if isinstance(rule, dict) else []:
            if isinstance(command, str) and command not in commands:
                commands.append(command)
    for command in data.get("default", []) if isinstance(data, dict) else []:
        if isinstance(command, str) and command not in commands:
            commands.append(command)
    return commands


def _kept_block(existing):
    if existing and KEEP_START in existing and KEEP_END in existing:
        return existing.split(KEEP_START, 1)[1].split(KEEP_END, 1)[0].strip("\n")
    return "- (repo-owned hard rules go here; this block survives regeneration)"


def render_agents(root, existing=None):
    kept = _kept_block(existing)
    covers = crew_context.index_covers(root)
    subs = crew_context.subsystems(root)
    name = os.path.basename(os.path.abspath(root))
    top = [f"# {name} - instructions for every agent",
           "",
           "Read natively by Codex; Claude Code reads it through `@AGENTS.md` in CLAUDE.md.",
           "",
           "## Work loop",
           "- One session owns a ticket: brainstorm, spec, plan, implement, tests, docs, review, done.",
           "- Before editing an unfamiliar area read `.crew/codemap/INDEX.md` and the subsystem note.",
           "- A code-map `anchor:` behind HEAD means re-check: "
           "`git diff --name-only <anchor>..HEAD -- <cited paths>`; empty output means current.",
           "- Quote failing checks verbatim, and say which checks you did not run.",
           "- Vault recall arrives labelled `[vault:<name>] <note>`: a lead to verify, not a fact."]
    verify = _verify_commands(root)
    mid = []
    if verify:
        mid += ["", "## Verify"] + [f"- `{c}`" for c in verify[:6]]
    mid += ["", "## Hard rules", KEEP_START] + kept.splitlines() + [KEEP_END]
    where = []
    if subs:
        where = ["", "## Where things are (from `.crew/codemap/`)"]
        for sub in subs:
            cover = re.split(r"(?<=[.!?])\s", covers.get(sub["name"], ""), maxsplit=1)[0]
            scope = ", ".join(f"`{p}`" for p in sub["paths"][:2])
            where.append(f"- `{sub['name']}`" + (f" ({scope})" if scope else "")
                         + (f": {cover[:110]}" if cover else ""))
    footer = ["", f"<!-- {MARKER} AGENTS.md -- regenerate with crew_instructions.py agents;"
              " only the crew:keep block is hand-edited -->"]
    lines = top + mid + where + footer
    while len(lines) > AGENTS_MAX_LINES and len(where) > 2:
        where.pop()
        lines = top + mid + where + footer
    return "\n".join(lines) + "\n"


def agents(root, check=False):
    path = os.path.join(root, "AGENTS.md")
    existing = read_text(path)
    if existing is not None and MARKER not in existing:
        return [_hand_written("AGENTS.md", check)], []
    text = render_agents(root, existing)
    if len(text.splitlines()) > AGENTS_MAX_LINES:
        return [f"AGENTS.md would be {len(text.splitlines())} lines (budget {AGENTS_MAX_LINES}): "
                "shorten the crew:keep block"], []
    if existing == text:
        return [], []
    if check:
        return [("stale: " if existing is not None else "missing: ") + "AGENTS.md"], []
    _write(path, text)
    return [], ["AGENTS.md"]


# --------------------------------------------------------------------------
# hook registrations, both harnesses, one table

def claude_hooks():
    """hooks.json entries for crew's plugin manifest: each row once per shell
    flavour (CLAUDE.md: a bare command goes to Git Bash on Windows)."""
    out = {}
    for row in HOOK_TABLE:
        sh = {"type": "command",
              "command": f'bash "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/{SCRIPT}.sh"',
              "timeout": row["timeout"]}
        ps = {"type": "command", "shell": "powershell",
              "command": f'& "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/{SCRIPT}.ps1"; exit $LASTEXITCODE',
              "timeout": row["timeout"]}
        for hook in (sh, ps):
            entry = {"hooks": [hook]}
            if row["matcher"]:
                entry = {"matcher": row["matcher"], "hooks": [hook]}
            out.setdefault(row["event"], []).append(entry)
    return {"hooks": out}


def default_plugin_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def codex_hooks(plugin_root):
    scripts = os.path.join(plugin_root, "hooks", "scripts")
    sh = os.path.join(scripts, SCRIPT + ".sh").replace("\\", "/")
    ps = os.path.join(scripts, SCRIPT + ".ps1").replace("/", "\\")
    out = {}
    for row in HOOK_TABLE:
        hook = {"type": "command", "command": f'bash "{sh}" --harness codex',
                "commandWindows": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps}" -Harness codex',
                "timeout": row["timeout"]}
        entry = {"hooks": [hook]}
        matcher = row["codex"] if row["matcher"] else None
        if matcher:
            entry = {"matcher": matcher, "hooks": [hook]}
        out.setdefault(row["event"], []).append(entry)
    return {"hooks": out}


CODEX_CONFIG = """# crew:generated -- regenerate with crew_instructions.py codex.
# Project config applies only to a TRUSTED project (codex 0.155.1's own help
# text: "Project `.codex/config.toml`: settings for a trusted repository").
# UNVERIFIED on a live run: whether `profiles` are honoured from project
# config rather than only from ~/.codex/config.toml. `crew_instructions.py
# codex-probe` reports what has been observed.

# AGENTS.md is read natively; CLAUDE.md is the fallback where it is absent.
project_doc_fallback_filenames = ["CLAUDE.md"]

# `codex exec --profile review --json` is the reviewer: it cannot write.
[profiles.review]
sandbox_mode = "read-only"
approval_policy = "never"

# `--profile work` implements under crew's scope guard.
[profiles.work]
sandbox_mode = "workspace-write"
approval_policy = "on-request"
"""


def _codex_hooks_generated(text):
    """JSON has no comment to carry the marker, so a hooks.json is ours when
    it parses and every hook in it runs crew-context -- which is all the
    generator ever writes. A file with anything else in it is someone's."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return False
    events = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(events, dict) or set(data) != {"hooks"}:
        return False
    commands = []
    for entries in events.values():
        for entry in entries if isinstance(entries, list) else [None]:
            hooks = entry.get("hooks") if isinstance(entry, dict) else None
            for hook in hooks if isinstance(hooks, list) else [None]:
                commands.append(hook.get("command") if isinstance(hook, dict) else None)
    return bool(commands) and all(isinstance(c, str) and f"/hooks/scripts/{SCRIPT}." in c
                                  for c in commands)


def codex(root, plugin_root, check=False, force=False):
    targets = {os.path.join(root, ".codex", "hooks.json"):
               json.dumps(codex_hooks(plugin_root), indent=2) + "\n",
               os.path.join(root, ".codex", "config.toml"): CODEX_CONFIG}
    problems, written = [], []
    for path, text in targets.items():
        rel = os.path.relpath(path, root)
        current = read_text(path)
        if current == text:
            continue
        ours = _codex_hooks_generated(current) if path.endswith(".json") else MARKER in (current or "")
        if current is not None and not ours and not force:
            problems.append(_hand_written(rel, check))
            continue
        if check:
            problems.append(("stale: " if current is not None else "missing: ") + rel)
        else:
            _write(path, text)
            written.append(rel)
    return problems, written


def _codex_bin():
    explicit = os.environ.get("CREW_CODEX_BIN")
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("codex", "codex.cmd", "codex.exe"):
            path = os.path.join(directory, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def _run(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def codex_probe(root, plugin_root):
    """Report lines. Nothing here counts as "proven" except an invocation the
    context log actually recorded under the codex harness."""
    lines = []
    binary = _codex_bin()
    if not binary:
        return ["codex: not installed - Codex parity not configured"]
    version = (_run([binary, "--version"]) or "").strip() or "version unknown"
    lines.append(f"codex: {binary} ({version})")
    features = _run([binary, "features", "list"])
    flag = "unknown (could not run `codex features list`)"
    for line in (features or "").splitlines():
        parts = line.split()
        if parts and parts[0] == "hooks":
            flag = "enabled" if parts[-1] == "true" else "DISABLED - set [features] hooks = true"
    lines.append(f"hooks feature: {flag}")
    problems, _ = codex(root, plugin_root, check=True)
    lines.append("project files: " + ("current" if not problems else "; ".join(problems)))
    seen = {}
    for raw in crew_context.read_log(root).splitlines():
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("harness") == "codex":
            seen[rec.get("event", "?")] = seen.get(rec.get("event", "?"), 0) + 1
    events = sorted({row["event"] for row in HOOK_TABLE})
    for event in events:
        if seen.get(event):
            lines.append(f"{event}: hook invoked {seen[event]}x under Codex "
                         "(delivery to the model not measured)")
        else:
            lines.append(f"{event}: configured, not proven")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate crew's instruction surface.")
    parser.add_argument("what", choices=("rules", "agents", "codex", "codex-probe", "claude-hooks"))
    parser.add_argument("--root", default="")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--plugin-root", default="")
    parser.add_argument("--force", action="store_true",
                        help="codex only: overwrite a hand-written .codex file")
    args = parser.parse_args(argv)
    root = crew_context.find_root(args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    plugin_root = args.plugin_root or default_plugin_root()
    if args.what == "claude-hooks":
        print(json.dumps(claude_hooks(), indent=2))
        return 0
    if args.what == "codex-probe":
        print("\n".join(codex_probe(root, plugin_root)))
        return 0
    if args.what == "rules":
        problems, written = rules(root, args.check)
    elif args.what == "agents":
        problems, written = agents(root, args.check)
    else:
        problems, written = codex(root, plugin_root, args.check, args.force)
    for item in written:
        line = "wrote " + item if not item.startswith("removed") else item
        if item.endswith("hooks.json"):
            line += " (machine-local: absolute plugin paths for this machine - do not commit it)"
        print(line)
    for item in problems:
        print(item)
    drift = [p for p in problems if not p.startswith("hand-written, left alone")]
    if not drift and not written:
        print(f"{args.what}: up to date")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
