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
  `---` lines and ignored; the harness owns its shape. CRLF, LF and a lone CR
  all end a line.
- A body is `pointer`, else `malformed` (one line that, stripped and without
  case, starts `vault:` but is not exactly the grammar -- an indented or
  `Vault:` line included; never read as full text, never resolved), else
  `full-text`. The note path refuses `:` in any segment and any Cc or Cf
  character.
- A vault name maps to a path through `vaults.<name>.path` in the machine's
  Obsidian config (`crew_recall.obsidian_config_path`); a `role: ignore`
  entry is not resolved. Only the name `memory`, only when that config has no
  such entry, falls back to the crew config's `memory.vaultPath`, then -- only
  when the config has no `vaults` block, as obsidian-vault's `list_vaults`
  reads it -- the legacy top-level `vaultPath`. No other vault is ever
  substituted for an unavailable one. A config file that exists but cannot be
  read or parsed, or whose `vaults` block or entry has the wrong shape, is
  `no-vault-config` ("config unreadable"), never "no vaults"; only
  FileNotFoundError means absent.
- The note must exist under the vault's real path with no symlink component
  between the vault and the note. A vault that cannot be listed is
  `vault-unavailable`; a component below it that cannot be examined is
  `unreadable`, never `note-missing`.
- `OBSIDIAN_VAULT_PATH` is not honoured (T-0084, accepted risk).

Standard library only. Read-only: this module writes nothing anywhere.
Exit 0 for `resolved` / `full-text`, 1 for every other state, 2 for usage.
"""
import argparse
import json
import os
import re
import stat
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
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
LEGACY_NAME = "memory"


def _invisible(text):
    """True when `text` holds a control (Cc) or format (Cf) character: a
    pointer must read as what it says."""
    return any(unicodedata.category(ch) in ("Cc", "Cf") for ch in text)


def split_body(text):
    """The body of a memory file: everything after a leading `---` ... `---`
    block, or the whole text when there is none. CRLF, LF and a lone CR all
    end a line."""
    lines = _LINE_BREAK.split(text)
    if lines and lines[0] == "---":
        for index in range(1, len(lines)):
            if lines[index] == "---":
                return "\n".join(lines[index + 1:])
    return "\n".join(lines)


def _path_problem(path):
    if _invisible(path):
        return "the note path holds a control or format character"
    if "\\" in path or "|" in path:
        return "the note path holds a backslash or a second '|' field"
    if path.startswith("/"):
        return "the note path is absolute; it must be relative to the vault"
    if ":" in path:
        return "the note path holds ':' (a drive, drive-relative path or stream name)"
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
    full-text. A single line that starts `vault:` once stripped and compared
    without case is a pointer attempt, so an indented or `Vault:` line is
    `malformed`, never full text."""
    lines = [line for line in _LINE_BREAK.split(body) if line.strip()]
    if len(lines) != 1 or not lines[0].strip().lower().startswith("vault:"):
        return "full-text", None, None, "not a pointer; nothing to resolve"
    line = lines[0]
    match = _POINTER.fullmatch(line)
    if not match:
        if _invisible(line):
            return "malformed", None, None, "the pointer holds a control or format character"
        return "malformed", None, None, ("not exactly 'vault: <name> | note: <path>' (lower "
                                         "case, not indented) with a name of 1-64 letters, "
                                         "digits, space, '.', '_' or '-'")
    name, path = match.groups()
    if name != name.rstrip(" "):
        return "malformed", None, None, "the vault name ends with a space"
    problem = _path_problem(path)
    if problem:
        return "malformed", name, path, problem
    return "pointer", name, path, None


def _json_file(path):
    """`(data, problem, present)`. Only FileNotFoundError is absent; a file
    that cannot be reached (EACCES on a folder), read or parsed as a JSON
    object is a problem, never "no config"."""
    try:
        os.stat(path)
    except FileNotFoundError:
        return {}, None, False
    except OSError as exc:
        return None, f"config unreadable: {path}: {exc.strerror or exc}", True
    data = crew_recall._read_json(path)  # pylint: disable=protected-access
    if not isinstance(data, dict):
        return None, f"config unreadable: {path}", True
    return data, None, True


def _crew_vault_path(root):
    """`(memory.vaultPath or None, problem)`. A crew config file that exists
    and cannot be read or parsed is a problem, not "unset"."""
    for path in (crew_common.repo_config_file(root, "config.json"),
                 crew_config.GLOBAL_CONFIG_PATH):
        problem = _json_file(path)[1]
        if problem:
            return None, problem
    memory = crew_config.resolve_config(root).get("memory")
    raw = memory.get("vaultPath") if isinstance(memory, dict) else None
    return (raw if isinstance(raw, str) and raw else None), None


def _vault_dir(raw, source):
    """`(path, None, None)` or `(None, state, reason)` for a configured path."""
    if not isinstance(raw, str) or not raw:
        return None, "vault-unavailable", f"{source} is not set"
    path = os.path.expanduser(raw)
    if not os.path.isabs(path):
        return None, "vault-unavailable", f"{source} is not an absolute path: {raw}"
    try:
        if not stat.S_ISDIR(os.stat(path).st_mode):
            return None, "vault-unavailable", f"{source} is not a directory: {raw}"
        with os.scandir(path) as listing:
            next(listing, None)
    except FileNotFoundError:
        return None, "vault-unavailable", f"{source} is not there on this host: {raw}"
    except OSError as exc:
        return None, "vault-unavailable", f"{source} cannot be read: {raw}: {exc.strerror or exc}"
    return path, None, None


def vault_path(name, root):
    """`(path, None, None)` or `(None, state, reason)` for vault `name`."""
    config = crew_recall.obsidian_config_path()
    data, problem, present = _json_file(config)
    if problem:
        return None, "no-vault-config", problem
    vaults = data.get("vaults")
    if vaults is not None and not isinstance(vaults, dict):
        return None, "no-vault-config", f"config unreadable: {config}: vaults is not an object"
    vaults = vaults or {}
    entry = vaults.get(name)
    if name in vaults and not isinstance(entry, dict):
        return None, "no-vault-config", (f"config unreadable: {config}: vaults.{name} is not "
                                         "an object")
    if entry is not None:
        if entry.get("role") == "ignore":
            return None, "vault-unknown", f"vault {name!r} has role ignore in {config}"
        return _vault_dir(entry.get("path"), f"vaults.{name}.path in {config}")
    if name != LEGACY_NAME:
        # memory.vaultPath names only `memory`; it matters here just for which
        # of two failure names applies, so a broken crew config reads as unset.
        if not present and _crew_vault_path(root)[0] is None:
            return None, "no-vault-config", (f"no Obsidian config at {config} and no "
                                             "memory.vaultPath in the crew config")
        return None, "vault-unknown", f"this host's config names no vault {name!r}"
    crew_raw, problem = _crew_vault_path(root)
    if problem:
        return None, "no-vault-config", problem
    if crew_raw is not None:
        return _vault_dir(crew_raw, "memory.vaultPath in the crew config")
    # The legacy single vault, read as obsidian-vault's list_vaults and
    # writer_vault read it: only when the config has no `vaults` block.
    if not vaults and data.get("vaultPath"):
        return _vault_dir(data.get("vaultPath"), f"vaultPath in {config}")
    if not present:
        return None, "no-vault-config", (f"no Obsidian config at {config} and no "
                                         "memory.vaultPath in the crew config")
    return None, "vault-unknown", f"this host's config names no vault {name!r}"


def _inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def note_path(vault, note):
    """`(real path, None, None)` or `(None, state, reason)`. Every existing
    component below the vault must be a real directory or file, not a link,
    and the real path must stay under the vault's real path. A component that
    cannot be examined is `unreadable`, never `note-missing`."""
    segments = note.split("/")
    current = vault
    for segment in segments:
        current = os.path.join(current, segment)
        try:
            mode = os.lstat(current).st_mode
        except (FileNotFoundError, NotADirectoryError):
            return None, "note-missing", f"{note} is not in the vault"
        except OSError as exc:
            return None, "unreadable", f"{note}: cannot read {current}: {exc.strerror or exc}"
        if stat.S_ISLNK(mode):
            return None, "outside-vault", f"{note}: a symlink inside the vault - not followed"
    real = os.path.realpath(os.path.join(vault, *segments))
    if not _inside(real, os.path.realpath(vault)):
        return None, "outside-vault", f"{note} resolves outside the vault"
    try:
        mode = os.stat(real).st_mode
    except OSError as exc:
        return None, "unreadable", f"{note}: cannot read it: {exc.strerror or exc}"
    if not stat.S_ISREG(mode):
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
    kind, name, note, reason = classify(split_body(text.lstrip("\ufeff")))
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


def _listed(directory, name):
    """A memory file `check` lists: `*.md` (suffix in any case) other than
    the index `MEMORY.md`, that is a regular file or a symlink - a dangling
    link is listed and reads `unreadable`. Directories and FIFOs are not."""
    if name == "MEMORY.md" or not name.lower().endswith(".md"):
        return False
    full = os.path.join(directory, name)
    return os.path.islink(full) or os.path.isfile(full)


def check_dir(directory, root):
    """`(rows, counts)` for every memory file in `directory`. Raises OSError
    when the directory cannot be listed."""
    names = sorted(n for n in os.listdir(directory) if _listed(directory, n))
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
    try:
        rows, counts = check_dir(args.memory_dir, root)
    except OSError as exc:
        print(f"crew_memory: cannot list {args.memory_dir}: {exc.strerror or exc}",
              file=sys.stderr)
        return 2
    if args.json:
        _emit(json.dumps({"rows": rows, "counts": counts}, ensure_ascii=False))
    else:
        for row in rows:
            _emit(f"{row['state']}  {row['file']}  {_row_text(row)}")
        _emit(", ".join(f"{c} {s}" for s, c in counts.items()) or "no memory files")
    return 0 if all(r["state"] in CLEAN for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
