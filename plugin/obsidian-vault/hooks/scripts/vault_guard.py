#!/usr/bin/env python3
"""PostToolUse guard for an Obsidian vault.

Generalized from a personal ~/.claude/hooks/obsidian-vault-guard.py written for
one vault's own contract. The checks below are the same mechanics, but every
one is now a config toggle under ~/.claude/obsidian/config.json -> "guard",
because a vault's frontmatter contract, ASCII rule and tag vocabulary are that
vault's decision, not this plugin's. Defaults are all OFF: a fresh install must
not suddenly reject edits against rules a different vault chose. /obsidian-vault:init
turns a toggle on only when it finds the matching rule stated in the target
vault's own CLAUDE.md, and says so when it does.

  guard.asciiOnly           bool, default false
  guard.requireFrontmatter  bool, default false
  guard.sixKeys             list, default the six below (only checked if
                             requireFrontmatter is true)
  guard.typeKeys            dict, default the four below
  guard.checkCanvas         bool, default true (canvas JSON-shape checks cost
                             nothing to run unconditionally and catch a file
                             that would silently open blank)

Exits 2 with feedback on stderr so Claude fixes it in the same turn. Exits 0
and stays silent for anything outside the vault, or when nothing is configured
to check.
"""
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402

# CLAUDE.md itself must show the real characters, so it is exempt by design
# whenever asciiOnly is on.
ASCII_EXEMPT_NAMES = {"claude.md"}

ASCII_MAP = {
    "—": " - ", "–": " - ", "·": "|", "•": "-",
    "→": "->", "←": "<-", "↔": "<->",
    "≤": "<=", "≥": ">=", "≠": "!=", "≈": "~=", "×": "x",
    "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"',
    "─": "-", "│": "|", "├": "+",
    "✅": "[x]", "❌": "[FAIL]", "⚠": "[!]", "⏳": "[WAIT]",
}

DEFAULT_SIX_KEYS = ["type", "title", "created", "updated", "status", "tags"]
DEFAULT_TYPE_KEYS = {
    "concept":  ["complexity", "domain", "aliases", "related", "sources", "claim_ids", "project"],
    "session":  ["session_id", "store", "observation_count", "sources"],
    "source":   ["source_type", "author", "date_published", "url", "source_id", "sha256",
                 "authority", "independence_key", "review_status"],
    "decision": ["decision_id", "decision_status", "date_decided", "deciders",
                 "supersedes", "superseded_by"],
}


def edited_paths(payload):
    ti = payload.get("tool_input") or {}
    out = []
    for key in ("file_path", "path", "notebook_path"):
        if ti.get(key):
            out.append(ti[key])
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and e.get("file_path"):
            out.append(e["file_path"])
    return out


def written_text(payload):
    """Only the bytes this edit introduced, not the file's pre-existing drift."""
    ti = payload.get("tool_input") or {}
    chunks = []
    for key in ("content", "new_string", "new_source"):
        if isinstance(ti.get(key), str):
            chunks.append(ti[key])
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            chunks.append(e["new_string"])
    return "\n".join(chunks) if chunks else None


def in_vault(p, vault):
    try:
        return os.path.normcase(os.path.abspath(p)).startswith(
            os.path.normcase(vault) + os.sep)
    except Exception:
        return False


def check_ascii(path, text, issues):
    if os.path.basename(path).lower() in ASCII_EXEMPT_NAMES:
        return
    bad = {}
    for i, ch in enumerate(text):
        if ord(ch) > 0x7F:
            bad.setdefault(ch, text[:i].count("\n") + 1)
    if not bad:
        return
    parts = []
    for ch, line in sorted(bad.items(), key=lambda kv: kv[1])[:8]:
        sub = ASCII_MAP.get(ch)
        parts.append("  near line %d: U+%04X -> %s"
                     % (line, ord(ch), ("'%s'" % sub) if sub else "drop it"))
    issues.append(
        "NON-ASCII introduced into a vault configured as ASCII-only "
        "(%d distinct char%s):\n%s" % (len(bad), "" if len(bad) == 1 else "s", "\n".join(parts))
    )


def parse_frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    fm, key = {}, None
    for raw in m.group(1).split("\n"):
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+-\s", line) and key:
            if not isinstance(fm.get(key), list):
                fm[key] = [] if fm.get(key) in ("", None) else [fm[key]]
            fm[key].append(line.split("-", 1)[1].strip())
            continue
        km = re.match(r"^([A-Za-z0-9_]+)\s*:\s*(.*)$", line)
        if km:
            key = km.group(1)
            fm[key] = km.group(2).strip()
    return fm


def check_note(path, text, issues, advisory, six_keys, type_keys, root, notes_glob):
    rel = os.path.relpath(path, root).replace("\\", "/")
    if notes_glob and not rel.startswith(notes_glob):
        return
    if "/templates/" in rel:
        return
    fm = parse_frontmatter(text)
    if fm is None:
        issues.append("NO FRONTMATTER. Required keys: " + ", ".join(six_keys))
        return

    missing = [k for k in six_keys if k not in fm or fm[k] in ("", None)]
    if missing:
        issues.append("MISSING required frontmatter: " + ", ".join(missing))

    ntype = fm.get("type")
    ntype = (ntype if isinstance(ntype, str) else "").strip().strip('"')
    absent = [k for k in type_keys.get(ntype, []) if k not in fm]
    if absent:
        advisory.append("type: %s has no %s"
                        % (ntype, ", ".join("'%s:'" % k for k in absent)))

    def scalar(k):
        v = fm.get(k)
        return v.strip().strip('"') if isinstance(v, str) else ""

    title = scalar("title")
    stem = os.path.splitext(os.path.basename(path))[0]
    if title and title != stem:
        issues.append("title: %r does not match filename %r - they must be identical" % (title, stem))

    today = date.today().isoformat()
    upd = scalar("updated")
    if upd and upd != today:
        issues.append("updated: %s but you just edited it - bump to %s" % (upd, today))


def check_canvas(path, text, issues, advisory, root):
    try:
        data = json.loads(text)
    except Exception as e:
        issues.append("CANVAS DOES NOT PARSE AS JSON (%s). It will open blank with no error." % e)
        return
    nodes = data.get("nodes") or []
    ids = [n.get("id") for n in nodes]
    dupes = {i for i in ids if i and ids.count(i) > 1}
    if dupes:
        issues.append("duplicate node ids: " + ", ".join(sorted(dupes)))
    idset = set(ids)
    for e in data.get("edges") or []:
        for end in ("fromNode", "toNode"):
            if e.get(end) and e[end] not in idset:
                issues.append("edge %s references missing node id %r" % (e.get("id", "?"), e[end]))
    for n in nodes:
        if n.get("type") == "file" and n.get("file"):
            if not os.path.exists(os.path.join(root, n["file"].replace("/", os.sep))):
                advisory.append("file node %s points at a missing note: %s"
                                % (n.get("id", "?"), n["file"]))
    advisory.append("a canvas holds no facts - anything stated only here needs a note")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    vault = obsidian_common.resolve_vault_path()
    if not vault:
        return 0

    cfg = obsidian_common.read_config()
    guard_cfg = cfg.get("guard") if isinstance(cfg.get("guard"), dict) else {}
    ascii_only = guard_cfg.get("asciiOnly") is True
    require_fm = guard_cfg.get("requireFrontmatter") is True
    check_canvas_shape = guard_cfg.get("checkCanvas") is not False
    six_keys = guard_cfg.get("sixKeys") or DEFAULT_SIX_KEYS
    type_keys = guard_cfg.get("typeKeys") or DEFAULT_TYPE_KEYS
    notes_glob = guard_cfg.get("notesPrefix", "")  # e.g. "wiki/" - "" checks every note

    if not (ascii_only or require_fm or check_canvas_shape):
        return 0

    added = written_text(payload)
    blocking, notes = [], []

    for path in edited_paths(payload):
        if not in_vault(path, vault) or not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".md", ".canvas", ".base"):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            continue

        issues, advisory = [], []
        if ascii_only:
            check_ascii(path, added if added is not None else text, issues)
        if ext == ".md" and require_fm:
            check_note(path, text, issues, advisory, six_keys, type_keys, vault, notes_glob)
        elif ext == ".canvas" and check_canvas_shape:
            check_canvas(path, text, issues, advisory, vault)

        rel = os.path.relpath(path, vault).replace("\\", "/")
        if issues:
            blocking.append("%s\n%s" % (rel, "\n".join("- " + i for i in issues)))
        if advisory:
            notes.append("%s\n%s" % (rel, "\n".join("- " + a for a in advisory)))

    if blocking:
        msg = ("Obsidian vault contract violations - fix these before moving on:\n\n"
               + "\n\n".join(blocking))
        if notes:
            msg += "\n\nAlso worth fixing while you are in these files:\n\n" + "\n\n".join(notes)
        sys.stderr.write(msg + "\n")
        return 2

    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "Obsidian vault - not blocking, but worth fixing:\n\n"
                                 + "\n\n".join(notes),
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
