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

**MEASURED, a different reading and a different build: on Windows with
codex-cli 0.154.0, a trusted run prints "Ignored unsupported project-local
config keys in .codex/config.toml: profiles" and its own `sandbox` field
reports `workspace-write`.** `[profiles.*]` is therefore not generated into
`.codex/config.toml` at all -- see `CODEX_CONFIG` below. Read-only enforcement
for the reviewer lives only on the command line
(`codex exec --sandbox read-only`, `review_run.py`'s `command_for`), never in
project-local config. This 0.154.0 finding and the 0.155.1 hook-schema reading
above are two different measurements against two different builds; neither
supersedes the other.

**Hooks fire only when two separate gates both open, and `codex-probe` now
reports on the first of them.** Per `codex-rs/config/src/loader/mod.rs`
(`sanitize_project_config`, `disabled_reason_for_decision`): a project's
`.codex/hooks.json` is not even loaded as a config layer unless
`~/.codex/config.toml` (respecting `CODEX_HOME`) records that project as
`trust_level = "trusted"` under `[projects."<path>"]` -- an untrusted or
unrecorded project is disabled silently, with no warning printed, the same
"gated_features" message class the denylisted `profiles` key would get if it
were project-scoped at all. A hook that *did* load still needs its own
content hash trusted, or the run needs `--dangerously-bypass-hook-trust`
(`codex-rs/hooks/src/engine/discovery.rs`) -- `codex exec` has no interactive
path to grant that trust, so a headless launch that relies on hooks needs the
flag every time. `codex_trust()` below checks the first gate (project trust)
and reports the second (the flag) as a static fact about crew's own launch
sites, because it is not something a config file records.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

try:
    import tomllib as _tomllib  # Python 3.11+, stdlib
except ImportError:  # pragma: no cover - exercised only on 3.8-3.10
    _tomllib = None

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
#
# No `[profiles.*]` table here, and none should be added. MEASURED on Windows
# with codex-cli 0.154.0: `profiles` is on Codex's own project-local config
# denylist (codex-rs/config/src/loader/mod.rs, PROJECT_LOCAL_CONFIG_DENYLIST)
# and is stripped from this file every time it loads, trusted or not --
# "Ignored unsupported project-local config keys in .codex/config.toml:
# profiles. If you want these settings to apply, manually set them in your
# user-level config.toml." A `[profiles.review] sandbox_mode = "read-only"`
# entry here would be silently discarded and enforce nothing; a trusted run
# with no `--sandbox` flag confirmed `workspace-write`, not read-only. The
# reviewer's read-only sandbox is enforced on the command line instead:
# `codex exec --sandbox read-only` (review_run.py's `command_for`).

# AGENTS.md is read natively; CLAUDE.md is the fallback where it is absent.
project_doc_fallback_filenames = ["CLAUDE.md"]
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


# --------------------------------------------------------------------------
# Codex project trust -- gates whether .codex/hooks.json ever loads at all.
#
# Schema confirmed by reading codex-rs (openai/codex, 2026-09-24):
#   codex-rs/config/src/loader/mod.rs `set_project_trust_level_inner` writes,
#   and `disabled_reason_for_decision` / `project_trust.rs` read:
#     [projects]
#     [projects."<native absolute path>"]
#     trust_level = "trusted"            # or "untrusted"
#   (an inline `"<path>" = { trust_level = "..." }` form under a bare
#   `[projects]` table is also accepted -- the same function's own comment
#   says it is what an older write, or a hand edit, can leave behind).
#   Lookup tries the repo root then cwd, canonical (realpath) spelling before
#   the literal one; Windows keys fold ASCII-case-insensitive, POSIX keys do
#   not (project_trust.rs::normalize_lookup_key). `find_codex_home()` resolves
#   `CODEX_HOME` when set, erroring if it is set but does not exist, and
#   otherwise defaults to `~/.codex`.
#
# An untrusted or unrecorded project does not merely leave hooks unproven --
# `disabled_reason_for_decision` names "project-local config, hooks, and exec
# policies" as the features gated on trust, and the layer is skipped with no
# warning printed (the warning path for the denylisted `profiles` key, above,
# is itself gated on `disabled_reason.is_none()`, i.e. it is trust-conditional
# too). So "no entry" and "trust_level = \"untrusted\"" are the SAME closed
# state for this purpose, not two different findings.

TRUST_OK, TRUST_CLOSED, TRUST_UNKNOWN = "trusted", "missing trust", "unknown"
BYPASS_HOOK_TRUST_FLAG = "--dangerously-bypass-hook-trust"

_PROJECTS_TABLE_RE = re.compile(r'^\[projects\]\s*$')
_PROJECTS_ENTRY_RE = re.compile(r'^\[projects\."((?:[^"\\]|\\.)*)"\]\s*$')
_PROJECTS_INLINE_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*=\s*\{(.*)\}\s*$')
_TRUST_LEVEL_RE = re.compile(r'^trust_level\s*=\s*"(trusted|untrusted)"\s*$')
_INLINE_TRUST_LEVEL_RE = re.compile(r'trust_level\s*=\s*"(trusted|untrusted)"')


def _unescape_toml_key(raw):
    """Just enough of a TOML basic string's escapes for a path: `\\\\` and
    `\\"`. Anything more exotic is left as-is rather than guessed at."""
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def _codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def _project_trust_lookup_keys(root):
    """Native path spellings Codex tries for `root`, canonical before literal
    (`ProjectTrustLookup`); we have no cwd distinct from `root` to also try."""
    literal = os.path.abspath(root)
    try:
        canonical = os.path.realpath(root)
    except OSError:
        canonical = literal
    return ([canonical] if canonical != literal else []) + [literal]


# Any table header other than the two `[projects...]` shapes above, and any
# ordinary `key = value` line -- both legal TOML the fallback line-scanner
# below does not need to understand for this one lookup, but must still
# recognise as WELL-FORMED so it does not mistake ordinary content elsewhere
# in the file for the malformed line that makes the whole read untrustworthy.
_TABLE_HEADER_RE = re.compile(r'^\[[^\[\]]*\]$')

# `_GENERIC_KV_RE` used to be `^[^\s=][^=]*=\s*\S.*$` -- ANY non-blank text
# after the `=` counted as a value. That accepted `broken = "unterminated`
# (an unclosed string tomllib rejects outright) as well-formed, and rejected
# a legal multi-line array's continuation lines (`"one",` on their own,
# with no `=` at all) as unclassifiable. Replaced with a small, strict
# grammar for the one subset this scanner (and Codex) actually writes:
# tables, `key = string/bool/number`, and arrays of those spanning one line
# or several. Anything outside that subset is UNKNOWN, never trusted.
_STRING_RE = r'"(?:[^"\\]|\\.)*"|\'[^\']*\''
_SCALAR_RE = r'(?:' + _STRING_RE + r'|true|false|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
_BARE_KEY_RE = r'[A-Za-z0-9_-]+'
_KEY_RE = r'(?:' + _BARE_KEY_RE + r'(?:\.\s*' + _BARE_KEY_RE + r')*|' + _STRING_RE + r')'
_KV_HEAD_RE = re.compile(r'^(' + _KEY_RE + r')\s*=\s*(.*)$')
_SCALAR_FULL_RE = re.compile(r'^(?:' + _SCALAR_RE + r')\s*(?:#.*)?$')
# Zero or more comma-separated scalars, optionally followed by the array's
# closing `]`. Covers a still-open continuation line (`"one",`) and the one
# that closes it (`"two"]` or a bare `]`) alike. No nesting: nothing this
# scanner reads or writes puts an array inside another array.
_ARRAY_LINE_RE = re.compile(
    r'^(?:' + _SCALAR_RE + r'\s*,\s*)*(?:' + _SCALAR_RE + r')?\s*\]?\s*(?:#.*)?$')


def _strip_trailing_comment(line):
    """`line` with a trailing `# ...` comment removed, but only a `#` that
    sits outside every quoted string -- so a literal `#` inside string data
    (`"a#b"`) is never mistaken for a comment start."""
    masked = re.sub(_STRING_RE, lambda m: '"' * len(m.group(0)), line)
    idx = masked.find('#')
    return line if idx == -1 else line[:idx]


def _array_line_state(tail):
    """Classify one line's worth of array content (`tail`: already
    comment-stripped and trimmed). `None` when it is not valid array syntax
    at all. Otherwise `(still_open, pending_close)`:

    - `still_open`: this line's closing `]` has not been seen.
    - `pending_close`: this line ended on a BARE scalar -- no trailing
      comma, no `]` -- which real TOML allows only as the array's LAST
      element. A no-lookahead, per-line scanner cannot confirm that from
      this line alone: it is valid only if the very next non-blank,
      non-comment line is nothing but `]`. Missing-comma finding (Codex
      review): the previous version treated a bare trailing scalar as
      unconditionally "fine, still open" regardless of what followed, so
      `"one"` then `"two"]` on the next line -- two elements with no comma
      between them, which a real TOML parser rejects -- read as a
      perfectly ordinary two-line array. The caller is responsible for
      rejecting any further array content once this is `True` and the next
      line is anything other than a bare `]`.
    """
    if not _ARRAY_LINE_RE.match(tail):
        return None
    still_open = not tail.endswith("]")
    pending_close = still_open and bool(tail) and not tail.rstrip().endswith(",")
    return still_open, pending_close


def _array_open_tail(value_text):
    """`None` when `value_text` -- the RHS of a `key = value` line -- is not
    array syntax at all (does not start with `[`). Otherwise `(still_open,
    pending_close)`, see `_array_line_state`."""
    if not value_text.startswith("["):
        return None
    tail = _strip_trailing_comment(value_text[1:]).strip()
    return _array_line_state(tail)


def _array_continuation_open(line):
    """Same contract as `_array_open_tail`, for a line inside an
    already-open array -- no leading `[` to strip here, since this scanner
    does not support one array nested inside another."""
    tail = _strip_trailing_comment(line).strip()
    return _array_line_state(tail)


def _kv_line_status(line):
    """Classify an ordinary `key = value` line. Returns `(status,
    pending_close)`: `status` is `"ok"` (a complete, recognised scalar or a
    fully-closed single-line array), `"array-open"` (a multi-line array
    that continues past this line), or `"bad"` -- no shape here that a real
    TOML parser would accept, which is what `broken = "unterminated` (an
    `=` followed by *something*, but not a complete value) now returns
    instead of the old regex's blanket accept. `pending_close` is
    `_array_line_state`'s own flag, always `False` for `"ok"`/`"bad"`."""
    head = _KV_HEAD_RE.match(line)
    if not head:
        return "bad", False
    value = head.group(2).strip()
    if _SCALAR_FULL_RE.match(value):
        return "ok", False
    state = _array_open_tail(value)
    if state is None:
        return "bad", False
    still_open, pending_close = state
    return ("array-open" if still_open else "ok"), pending_close


def _scan_project_trust(text, keys):
    """(level, matched_key, bad_line). `bad_line` is the first line this
    narrow scanner could not classify at all -- not a comment, not blank, not
    a table header, not an ordinary `key = value` pair, and not one of the
    two documented `[projects]` shapes -- which is this scanner's only signal
    that the file might not be valid TOML at all (Codex review fix #2: a
    malformed file used to report whatever trust entry the regex still
    happened to match, which is the "unknown collapsing into the
    safe-looking value" bug CLAUDE.md names). `None` means every line was
    recognised, though that is still not a claim that the file is valid TOML
    end to end -- `_project_trust` below prefers a real parser
    (`tomllib`) precisely because this scanner cannot make that claim.

    `(level, matched_key)` alone are `(None, None)` when no entry for `keys`
    is found -- `keys` is tried in order (canonical before literal, per
    `_project_trust_lookup_keys`), fixing Codex review fix #3: the previous
    version returned whichever matching entry happened to come FIRST IN THE
    FILE, not the canonical one Codex itself would prefer."""
    fold = (lambda s: s.lower()) if os.name == "nt" else (lambda s: s)
    mode = None  # None | "bare" | ("entry", key)
    in_array = False  # inside an as-yet-unclosed multi-line array's value
    # True when the array's PREVIOUS line ended on a bare scalar with no
    # trailing comma and no `]` -- see `_array_line_state`. Only a bare `]`
    # may legally follow; anything else is a missing comma.
    array_pending_close = False
    found = {}
    bad_line = None

    def _mark_bad(raw):
        nonlocal bad_line
        if bad_line is None:
            bad_line = raw

    def _dispatch_kv(line, raw_line):
        """Classify an ordinary `key = value` line, common to all three
        modes below: mark it bad, or open a multi-line array and remember
        that this loop is now inside one."""
        nonlocal in_array, array_pending_close
        status, pending_close = _kv_line_status(line)
        if status == "bad":
            _mark_bad(raw_line)
        elif status == "array-open":
            in_array = True
            array_pending_close = pending_close

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if in_array:
            if array_pending_close and _strip_trailing_comment(line).strip() != "]":
                # The previous line's bare trailing scalar is valid TOML
                # only if THIS line is nothing but the closing bracket --
                # anything else here is a missing comma between two
                # elements, not a second element silently accepted.
                _mark_bad(raw_line)
                in_array = False
                array_pending_close = False
                continue
            state = _array_continuation_open(line)
            if state is None:
                _mark_bad(raw_line)
                in_array = False
                array_pending_close = False
            else:
                in_array, array_pending_close = state
            continue
        entry = _PROJECTS_ENTRY_RE.match(line)
        if entry:
            mode = ("entry", _unescape_toml_key(entry.group(1)))
            continue
        if _PROJECTS_TABLE_RE.match(line):
            mode = "bare"
            continue
        if line.startswith("["):
            mode = None
            if not _TABLE_HEADER_RE.match(line):
                _mark_bad(raw_line)
            continue
        if mode == "bare":
            inline = _PROJECTS_INLINE_RE.match(line)
            if inline:
                level = _INLINE_TRUST_LEVEL_RE.search(inline.group(2))
                if level:
                    found[_unescape_toml_key(inline.group(1))] = level.group(1)
                continue
            _dispatch_kv(line, raw_line)
            continue
        if isinstance(mode, tuple):
            level = _TRUST_LEVEL_RE.match(line)
            if level:
                found[mode[1]] = level.group(1)
                continue
            _dispatch_kv(line, raw_line)
            continue
        _dispatch_kv(line, raw_line)

    for key in keys:
        ck = fold(key)
        for found_key, level in found.items():
            if fold(found_key) == ck:
                return level, found_key, bad_line
    return None, None, bad_line


def _trust_from_toml_document(doc, keys):
    """Same `(level, matched_key)` contract as `_scan_project_trust`, read
    from an already-parsed `tomllib` document instead of a regex. Both
    accepted shapes (`[projects."<path>"]` and the bare-table inline-table
    form) land as the identical `{path: {"trust_level": "..."}}` structure
    once parsed, so one reader covers both."""
    projects = doc.get("projects") if isinstance(doc, dict) else None
    if not isinstance(projects, dict):
        return None, None
    found = {
        key: value.get("trust_level")
        for key, value in projects.items()
        if isinstance(value, dict) and value.get("trust_level") in ("trusted", "untrusted")
    }
    fold = (lambda s: s.lower()) if os.name == "nt" else (lambda s: s)
    for key in keys:
        ck = fold(key)
        for found_key, level in found.items():
            if fold(found_key) == ck:
                return level, found_key
    return None, None


def _project_trust(text, keys):
    """(level, matched_key, malformed). `malformed` is a human-readable
    reason the file's trust could not be established, or `None` when it
    could. Prefers `tomllib` (Python 3.11+, stdlib) as the ground truth --
    the closest thing available here to Codex's own TOML reader -- and
    reports a `TOMLDecodeError` as `malformed` rather than falling back to a
    regex that would happily read a trust entry out of an otherwise-broken
    file (Codex review fix #2). On 3.8-3.10, where `tomllib` does not exist,
    falls back to `_scan_project_trust`'s line scanner, whose own `bad_line`
    is treated the same way: unclassifiable is reported as unknown, never as
    a trusted match."""
    if _tomllib is not None:
        try:
            doc = _tomllib.loads(text)
        except _tomllib.TOMLDecodeError as exc:
            return None, None, f"is not valid TOML: {exc}"
        level, matched = _trust_from_toml_document(doc, keys)
        return level, matched, None
    level, matched, bad_line = _scan_project_trust(text, keys)
    if bad_line is not None:
        return None, None, f"has a line this scanner cannot classify: {bad_line!r}"
    return level, matched, None


def codex_trust(root):
    """(state, detail). `state` is one of TRUST_OK / TRUST_CLOSED /
    TRUST_UNKNOWN -- UNKNOWN is its own value and is never reported as
    TRUST_OK just because trust could not be disproven either."""
    home = _codex_home()
    if os.environ.get("CODEX_HOME") and not os.path.isdir(home):
        return TRUST_UNKNOWN, (f"CODEX_HOME={home} does not exist; codex itself refuses "
                               "to start against a CODEX_HOME that is set but missing, so "
                               "nothing here can be inferred either way")
    path = os.path.join(home, "config.toml")
    if not os.path.exists(path):
        return TRUST_CLOSED, f"no {path}: this project has never been recorded as trusted"
    text = read_text(path)
    if text is None:
        return TRUST_UNKNOWN, f"could not read {path}"
    level, matched, malformed = _project_trust(text, _project_trust_lookup_keys(root))
    if malformed:
        return TRUST_UNKNOWN, f"{path} {malformed}"
    if level == TRUST_OK:
        return TRUST_OK, f'trust_level = "trusted" for {matched} in {path}'
    if level == "untrusted":
        return TRUST_CLOSED, f'trust_level = "untrusted" for {matched} in {path}'
    return TRUST_CLOSED, f"no [projects] entry for this repo in {path}"


def codex_probe(root, plugin_root):
    """Report lines. Nothing here counts as "proven" except an invocation the
    context log actually recorded under the codex harness, and nothing here
    reports a closed trust gate as merely unproven."""
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
    trust_state, trust_detail = codex_trust(root)
    lines.append(f"project trust: {trust_state} - {trust_detail}")
    lines.append(f"hook trust bypass ({BYPASS_HOOK_TRUST_FLAG}): review_run.py's codex "
                 "launch does not pass it -- review does not rely on hooks, so that is not "
                 "a gap for it; crew ships no other automated `codex exec` launch today")
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
        elif trust_state == TRUST_CLOSED:
            lines.append(f"{event}: CLOSED - {trust_detail}; .codex/hooks.json is not even "
                         "loaded until this project is trusted, and Codex prints no warning "
                         "when it is skipped")
        elif trust_state == TRUST_UNKNOWN:
            lines.append(f"{event}: unknown - {trust_detail}; cannot tell whether hooks "
                         "load here, so this is neither proven nor closed")
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
