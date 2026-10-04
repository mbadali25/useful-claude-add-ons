"""Native Claude Code memories as one-line pointers into a vault note.

    python3 crew_memory.py resolve --file <memory file> [--root <repo>] [--json]
    python3 crew_memory.py check --memory-dir <dir> [--root <repo>] [--json]

A native memory file (`~/.claude/projects/<project>/memory/<fact>.md`) is a
frontmatter block and a body. Its body may be exactly one line,

    vault: <name> | note: <vault-relative path with forward slashes>

naming a vault by the name THIS host's config gives it, never by an absolute
path, so the same file resolves on every machine the vault is synced to.

Rules, each with a test in plugin/crew/tests/test_crew_memory.py:

- The frontmatter is never parsed as YAML. It is split off on its first two
  `---` lines and ignored; the harness owns its shape.
- A body is `pointer`, else `malformed` (one line starting `vault:` that fails
  the grammar -- never read as full text, never resolved), else `full-text`.
- A vault name maps to a path through `vaults.<name>.path` in the machine's
  Obsidian config (`crew_recall.obsidian_config_path`); a `role: ignore`
  entry is not resolved. Only the name `memory`, only when that config has no
  such entry, falls back to the crew config's `memory.vaultPath`, then the
  Obsidian config's legacy top-level `vaultPath`. No other vault is ever
  substituted for an unavailable one, and a config file that exists but does
  not parse is reported, not taken for "no vaults".
- The note must exist under the vault's real path with no symlink component
  between the vault and the note.
- `OBSIDIAN_VAULT_PATH` is not honoured (T-0084, accepted risk).

Standard library only. Read-only: this module writes nothing anywhere.
Exit 0 for `resolved` / `full-text`, 1 for every other state, 2 for usage.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

import crew_common
import crew_config
import crew_recall

# The state table, in the order `check` counts them.
STATES = ("resolved", "full-text", "malformed", "no-vault-config", "vault-unknown",
          "vault-unavailable", "note-missing", "outside-vault", "unreadable")
CLEAN = ("resolved", "full-text")
_POINTER = re.compile(r"vault: ([A-Za-z0-9][A-Za-z0-9 ._-]{0,63}) \| note: (.*)")
_DRIVE = re.compile(r"[A-Za-z]:")
LEGACY_NAME = "memory"


def split_body(text):
    """The body of a memory file: everything after a leading `---` ... `---`
    block, or the whole text when there is none."""
    lines = text.split("\n")
    if lines and lines[0].rstrip("\r") == "---":
        for index in range(1, len(lines)):
            if lines[index].rstrip("\r") == "---":
                return "\n".join(lines[index + 1:])
    return text


def _path_problem(path):
    if any(unicodedata.category(ch) == "Cc" for ch in path):
        return "the note path holds a control character"
    if "\\" in path or "|" in path:
        return "the note path holds a backslash or a second '|' field"
    if path.startswith("/") or _DRIVE.match(path):
        return "the note path is absolute; it must be relative to the vault"
    if not path.endswith(".md"):
        return "the note path does not end .md"
    for segment in path.split("/"):
        if segment in ("", ".", ".."):
            return f"the note path has an empty, '.' or '..' segment: {path!r}"
        if segment != segment.strip(" "):
            return f"a note path segment starts or ends with a space: {segment!r}"
    return None


def classify(body):
    """`(kind, vault, note, reason)` for a body; kind is pointer / malformed /
    full-text."""
    lines = [line.rstrip("\r") for line in body.split("\n")]
    lines = [line for line in lines if line.strip(" \t")]
    if len(lines) != 1 or not lines[0].startswith("vault:"):
        return "full-text", None, None, "not a pointer; nothing to resolve"
    line = lines[0]
    match = _POINTER.fullmatch(line)
    if not match:
        if any(unicodedata.category(ch) == "Cc" for ch in line):
            return "malformed", None, None, "the pointer holds a control character"
        return "malformed", None, None, ("not 'vault: <name> | note: <path>' with a name of "
                                         "1-64 letters, digits, space, '.', '_' or '-'")
    name, path = match.groups()
    if name != name.rstrip(" "):
        return "malformed", None, None, "the vault name ends with a space"
    problem = _path_problem(path)
    if problem:
        return "malformed", name, path, problem
    return "pointer", name, path, None


def _json_file(path):
    """`(data, problem)`: `({}, None)` when absent, `(None, reason)` when it
    exists and is not a JSON object."""
    if not os.path.lexists(path):
        return {}, None
    data = crew_recall._read_json(path)  # pylint: disable=protected-access
    if not isinstance(data, dict):
        return None, f"config unreadable: {path}"
    return data, None


def _crew_vault_path(root):
    """`(memory.vaultPath or None, problem)`. A crew config file that exists
    and does not parse is a problem, not "unset"."""
    for path in (crew_common.repo_config_file(root, "config.json"),
                 crew_config.GLOBAL_CONFIG_PATH):
        problem = _json_file(path)[1]
        if problem:
            return None, problem
    memory = crew_config.resolve_config(root).get("memory")
    raw = memory.get("vaultPath") if isinstance(memory, dict) else None
    return (raw if isinstance(raw, str) and raw else None), None


def vault_path(name, root):
    """`(path, None, None)` or `(None, state, reason)` for vault `name`."""
    config = crew_recall.obsidian_config_path()
    data, problem = _json_file(config)
    if problem:
        return None, "no-vault-config", problem
    vaults = data.get("vaults") if isinstance(data.get("vaults"), dict) else {}
    entry = vaults.get(name)
    if isinstance(entry, dict):
        if entry.get("role") == "ignore":
            return None, "vault-unknown", f"vault {name!r} has role ignore in {config}"
        raw, source = entry.get("path"), f"vaults.{name}.path in {config}"
    else:
        crew_raw, problem = _crew_vault_path(root)
        if problem:
            return None, "no-vault-config", problem
        if not os.path.lexists(config) and crew_raw is None:
            return None, "no-vault-config", (f"no Obsidian config at {config} and no "
                                             "memory.vaultPath in the crew config")
        if name != LEGACY_NAME:
            return None, "vault-unknown", f"this host's config names no vault {name!r}"
        raw, source = crew_raw, "memory.vaultPath in the crew config"
        if raw is None:
            raw, source = data.get("vaultPath"), f"vaultPath in {config}"
        if not raw:
            return None, "vault-unknown", f"this host's config names no vault {name!r}"
    if not isinstance(raw, str) or not raw:
        return None, "vault-unavailable", f"{source} is not set"
    path = os.path.expanduser(raw)
    if not os.path.isabs(path) or not os.path.isdir(path):
        return None, "vault-unavailable", f"{source} is not a directory on this host: {raw}"
    return path, None, None


def _inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def note_path(vault, note):
    """`(real path, None, None)` or `(None, state, reason)`. Every existing
    component below the vault must be a real directory or file, not a link,
    and the real path must stay under the vault's real path."""
    segments = note.split("/")
    current = vault
    for segment in segments:
        current = os.path.join(current, segment)
        if os.path.islink(current):
            return None, "outside-vault", f"{note}: a symlink inside the vault - not followed"
        if not os.path.lexists(current):
            break
    real = os.path.realpath(os.path.join(vault, *segments))
    if not _inside(real, os.path.realpath(vault)):
        return None, "outside-vault", f"{note} resolves outside the vault"
    if not os.path.isfile(real):
        return None, "note-missing", f"{note} is not a file in the vault"
    return real, None, None


def resolve_file(path, root):
    """One row: `{file, state, reason | path, vault, note}`."""
    row = {"file": path, "vault": None, "note": None}
    try:
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return dict(row, state="unreadable", reason=f"cannot read as UTF-8: {exc}")
    kind, name, note, reason = classify(split_body(text.lstrip("﻿")))
    row.update(vault=name, note=note)
    if kind != "pointer":
        return dict(row, state=kind, reason=reason)
    vault, state, reason = vault_path(name, root)
    if vault is None:
        return dict(row, state=state, reason=reason)
    real, state, reason = note_path(vault, note)
    if real is None:
        return dict(row, state=state, reason=reason)
    return dict(row, state="resolved", path=real)


def check_dir(directory, root):
    """`(rows, counts)` for every `*.md` in `directory` except MEMORY.md."""
    names = sorted(n for n in os.listdir(directory)
                   if n.endswith(".md") and n.lower() != "memory.md"
                   and os.path.isfile(os.path.join(directory, n)))
    rows = [dict(resolve_file(os.path.join(directory, n), root), file=n) for n in names]
    counts = {s: sum(r["state"] == s for r in rows) for s in STATES}
    return rows, {s: c for s, c in counts.items() if c}


def _emit(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def _row_text(row):
    if row["state"] == "resolved":
        return f"{row['vault']}/{row['note']}"
    where = f"{row['vault']}/{row['note']}  " if row["vault"] and row["note"] else ""
    return where + row["reason"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("resolve", help="map one memory file's pointer to its note")
    one.add_argument("--file", required=True)
    every = sub.add_parser("check", help="report the state of every memory file")
    every.add_argument("--memory-dir", required=True)
    for each in (one, every):
        each.add_argument("--root", default=".")
        each.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.command == "resolve":
        if not os.path.isfile(args.file):
            print(f"crew_memory: no such file: {args.file}", file=sys.stderr)
            return 2
        row = resolve_file(args.file, root)
        if args.json:
            _emit(json.dumps(row, ensure_ascii=False))
        else:
            _emit(f"state: {row['state']}")
            _emit(f"path: {row['path']}" if "path" in row else f"reason: {row['reason']}")
        return 0 if row["state"] in CLEAN else 1
    if not os.path.isdir(args.memory_dir):
        print(f"crew_memory: no such directory: {args.memory_dir}", file=sys.stderr)
        return 2
    rows, counts = check_dir(args.memory_dir, root)
    if args.json:
        _emit(json.dumps({"rows": rows, "counts": counts}, ensure_ascii=False))
    else:
        for row in rows:
            _emit(f"{row['state']}  {row['file']}  {_row_text(row)}")
        _emit(", ".join(f"{c} {s}" for s, c in counts.items()) or "no memory files")
    return 0 if all(r["state"] in CLEAN for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
