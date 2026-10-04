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
- A body is `pointer`, else `malformed`, else `full-text`. The first
  non-blank line, with Cf characters removed and then stripped, that starts
  `vault`, optional whitespace and `:` in any case, and also holds `note:` or
  `|`, is a pointer attempt: it
  must be the whole body and match the grammar exactly, or it is `malformed`
  (never read as full text, never resolved). The note path refuses `:` in
  any segment and any Cc, Cf, Zl or Zp character.
- A vault name maps to a path through `vaults.<name>.path` in the machine's
  Obsidian config (`crew_recall.obsidian_config_path`); a `role: ignore`
  entry is not resolved. Only the name `memory`, only when that config has no
  such entry, falls back to the crew config's `memory.vaultPath`, then -- only
  when the config has no `vaults` block, as obsidian-vault's `list_vaults`
  reads it -- the legacy top-level `vaultPath`. No other vault is ever
  substituted for an unavailable one.
- A config file is absent only when `os.lstat` raises FileNotFoundError.
  Anything else there (a dangling link, any other OSError, bad JSON, a wrong
  shape) must read, parse and pass one schema check, run for both files
  before any resolution, or it is `no-vault-config` ("config unreadable",
  naming the field).
- The note must exist under the vault's real path with no symlink component
  between the vault and the note. A vault that cannot be listed is
  `vault-unavailable`; a component below it that cannot be examined, or a
  note that does not open, is `unreadable`, never `note-missing`. Files are
  opened non-blocking and fstat-checked, and `check` stats every entry
  first, so a FIFO or device is listed `unreadable` and never blocks.
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
_ATTEMPT = re.compile(r"vault\s*:", re.IGNORECASE)
# Without one of these a `vault:` line is prose ("Vault: keep client notes in
# the work vault"), not a pointer attempt.
_ATTEMPT_MARK = re.compile(r"note\s*:|\|", re.IGNORECASE)
CONFIG_CAP = 1024 * 1024  # bytes; a larger config file is "config unreadable"
LEGACY_NAME = "memory"


def _invisible(text):
    """True when `text` holds a control (Cc), format (Cf) or line/paragraph
    separator (Zl/Zp) character: a pointer must read as what it says."""
    return any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in text)


def _open_regular(path):
    """An open binary file for `path`, following links, or OSError. Opened
    non-blocking and checked with fstat, so a FIFO or device is refused
    without ever blocking on it, even if it replaced a regular file after a
    stat."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    handle = os.fdopen(os.open(path, flags), "rb")
    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
        handle.close()
        raise OSError(f"{path} is not a regular file - not read")
    return handle


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
    full-text. The first non-blank line, with Cf characters removed and then
    stripped, that starts `vault` and optional whitespace and `:` (any case)
    and also holds `note:` (optional whitespace) or `|` is a pointer
    attempt: it must be the whole body and match the grammar exactly, or it
    is `malformed`. Without that mark a `vault:` line is prose. A lone CR ends a line, so a CR inside a
    pointer line leaves a second line and is `malformed` too."""
    lines = [line for line in _LINE_BREAK.split(body) if line.strip()]
    probe = "".join(ch for ch in lines[0] if unicodedata.category(ch) != "Cf") if lines else ""
    probe = probe.strip()
    if not (_ATTEMPT.match(probe) and _ATTEMPT_MARK.search(probe)):
        return "full-text", None, None, "not a pointer; nothing to resolve"
    line = lines[0]
    if len(lines) != 1:
        return "malformed", None, None, "a pointer line must be the whole body"
    match = _POINTER.fullmatch(line)
    if not match:
        if _invisible(line):
            return "malformed", None, None, "the pointer holds an invisible or control character"
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


def _obsidian_problem(data):
    """The first field of the Obsidian config outside the schema, or None:
    `vaults` absent or an object of objects each with a string `path`;
    `vaultPath` absent or a string."""
    if "vaults" in data:
        vaults = data["vaults"]
        if not isinstance(vaults, dict):
            return "vaults is not an object"
        for name, entry in vaults.items():
            if not isinstance(entry, dict):
                return f"vaults.{name} is not an object"
            if not isinstance(entry.get("path"), str):
                return f"vaults.{name}.path is not a string"
    if "vaultPath" in data and not isinstance(data["vaultPath"], str):
        return "vaultPath is not a string"
    return None


def _crew_problem(data):
    """The first crew-config field this module reads that is outside the
    schema, or None: `memory` absent or an object; `memory.vaultPath` absent,
    a string, null or ""."""
    if "memory" not in data:
        return None
    memory = data["memory"]
    if not isinstance(memory, dict):
        return "memory is not an object"
    if "vaultPath" in memory and not isinstance(memory["vaultPath"], (str, type(None))):
        return "memory.vaultPath is not a string or null"
    return None


def _no_duplicates(pairs):
    """json's object hook: a key given twice is ambiguous, not "the last"."""
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"duplicate key {key!r}")
        data[key] = value
    return data


def _config(path, schema):
    """`(data, problem, present)`. Absent ONLY when lstat says
    FileNotFoundError; anything else there - a dangling link, any other
    OSError, bad JSON, a wrong shape - must read, parse and pass `schema`, or
    it is a problem naming the file (and the field)."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return {}, None, False
    except OSError as exc:
        return None, f"config unreadable: {path}: {exc.strerror or exc}", True
    try:
        with _open_regular(path) as handle:
            raw = handle.read(CONFIG_CAP + 1)
        if len(raw) > CONFIG_CAP:
            return None, f"config unreadable: {path}: larger than {CONFIG_CAP} bytes", True
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_no_duplicates)
    except RecursionError:
        return None, f"config unreadable: {path}: nested too deeply", True
    except (OSError, ValueError) as exc:
        return None, f"config unreadable: {path}: {getattr(exc, 'strerror', None) or exc}", True
    if not isinstance(data, dict):
        return None, f"config unreadable: {path}: not a JSON object", True
    problem = schema(data)
    if problem:
        return None, f"config unreadable: {path}: {problem}", True
    return data, None, True


def _crew_vault_path(root):
    """`(memory.vaultPath or None, problem)`. Both crew config layers are
    checked against the schema first; a problem is never "unset"."""
    for path in (crew_common.repo_config_file(root, "config.json"),
                 crew_config.GLOBAL_CONFIG_PATH):
        problem = _config(path, _crew_problem)[1]
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
    """`(path, None, None)` or `(None, state, reason)` for vault `name`. Both
    configs are read and schema-checked up front, before any resolution. A
    bad Obsidian config stops every name; a bad crew config stops `memory`,
    the one name it can answer for, and any name when there is no Obsidian
    config to say which failure applies."""
    config = crew_recall.obsidian_config_path()
    data, problem, present = _config(config, _obsidian_problem)
    if problem:
        return None, "no-vault-config", problem
    crew_raw, crew_problem = _crew_vault_path(root)
    vaults = data.get("vaults") or {}
    entry = vaults.get(name)
    if entry is not None:
        if entry.get("role") == "ignore":
            return None, "vault-unknown", f"vault {name!r} has role ignore in {config}"
        return _vault_dir(entry["path"], f"vaults.{name}.path in {config}")
    if name != LEGACY_NAME:
        if present:
            return None, "vault-unknown", f"{config} names no vault {name!r}"
        if crew_problem:
            return None, "no-vault-config", crew_problem
        if crew_raw is None:
            return None, "no-vault-config", f"no Obsidian config at {config}"
        return None, "vault-unknown", (f"no Obsidian config at {config}; memory.vaultPath "
                                       f"names only the vault {LEGACY_NAME!r}")
    if crew_problem:
        return None, "no-vault-config", crew_problem
    if crew_raw is not None:
        return _vault_dir(crew_raw, "memory.vaultPath in the crew config")
    # The legacy single vault, read as obsidian-vault's list_vaults and
    # writer_vault read it: only when the config has no `vaults` block.
    if not vaults and data.get("vaultPath"):
        return _vault_dir(data["vaultPath"], f"vaultPath in {config}")
    if not present:
        return None, "no-vault-config", (f"no Obsidian config at {config} and no "
                                         "memory.vaultPath in the crew config")
    return None, "vault-unknown", (f"{config} names no vault {LEGACY_NAME!r} and "
                                   "memory.vaultPath is not set")


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
        return None, "unreadable", f"{note} is there but not a regular file - not read"
    try:
        _open_regular(real).close()
    except OSError as exc:
        return None, "unreadable", f"{note}: cannot open it: {exc.strerror or exc}"
    return real, None, None


def resolve_file(path, root):
    """One row: `{file, state, reason | path, vault, note}`."""
    row = {"file": path, "vault": None, "note": None}
    try:
        with _open_regular(path) as handle:
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


def _listed(name):
    """A memory file `check` lists: `*.md` (suffix in any case) other than
    the index `MEMORY.md`, whatever it is."""
    return name != "MEMORY.md" and name.lower().endswith(".md")


def _check_one(directory, name, root):
    """One `check` row. `os.stat` follows links; only a regular file is
    opened. A dangling link, a FIFO, a device or a directory is `unreadable`
    without being opened, so `check` cannot block on one."""
    full = os.path.join(directory, name)
    row = {"file": name, "vault": None, "note": None, "state": "unreadable"}
    try:
        mode = os.stat(full).st_mode
    except OSError as exc:
        return dict(row, reason=f"cannot stat it (a dangling link?): {exc.strerror or exc}")
    if not stat.S_ISREG(mode):
        return dict(row, reason="not a regular file (a directory, FIFO or device) - not opened")
    return dict(resolve_file(full, root), file=name)


def check_dir(directory, root):
    """`(rows, counts)` for every memory file in `directory`. Raises OSError
    when the directory cannot be listed."""
    rows = [_check_one(directory, n, root) for n in sorted(os.listdir(directory)) if _listed(n)]
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
