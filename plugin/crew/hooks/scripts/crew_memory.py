"""Native Claude Code memories as one-line pointers into a vault note.

    python3 crew_memory.py resolve --file <memory file> [--root <repo>] [--json]
    python3 crew_memory.py check --memory-dir <dir> [--root <repo>] [--json]
    python3 crew_memory.py save --file <memory file> --tag <tag> [--tag ...]
        [--title <t>] [--note <path>] [--type <type>] [--project <p>]
        [--root <repo>] [--apply] [--json]

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
  `vault`, optional whitespace and `:` in any case, and has the `note:`/`|`
  mark on that line, or a second line starting `|` or `note:`, or is a bare
  vault name alone, is a pointer attempt: it must be the whole body and
  match the grammar exactly, or it is `malformed` (never read as full text,
  never resolved). The note path refuses `:` in any segment and any Cc, Cf,
  Zl or Zp character.
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

`save` (L-0677; tests in plugin/crew/tests/test_crew_memory_save.py) is the
only writer. It computes the whole note text and the new native bytes first,
writes the note in the single writable vault (`writer_vault`) through a temp
file, reads it back and resolves the pointer, and only then replaces the
native body through a temp file and `os.replace`. Every refusal or failure
leaves the native file byte-identical; a dangling pointer is never written.
Dry run by default.

Standard library only. `resolve` and `check` write nothing anywhere.
Exit 0 for `resolved` / `full-text`, 1 for every other state, 2 for usage.
"""
import argparse
import datetime
import json
import os
import re
import stat
import sys
import tempfile
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
_ATTEMPT_MARK = re.compile(r"\bnote\s*:|\|", re.IGNORECASE)
_WRAPPED = re.compile(r"\||note\s*:", re.IGNORECASE)
# A bare vault name, or nothing at all after the colon (a pointer broken
# right after `vault:`), is a pointer attempt too.
_BARE = re.compile(r"vault\s*:(?:\s*[A-Za-z0-9][A-Za-z0-9 ._-]{0,63})?", re.IGNORECASE)
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


def _strip_cf(text):
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _attempt(lines):
    """True when the body is a pointer attempt: its first non-blank line, Cf
    removed and stripped, starts `vault` + optional whitespace + `:` (any
    case), and either the `note:`/`|` mark is on that line, or the second
    non-blank line starts with `|` or `note:` (a pointer wrapped before its
    `|`), or the first line is a bare vault name with nothing after it, or
    is only `vault` + optional whitespace + `:` with nothing after the colon. A
    mark further down - a table, a `Note:` line - is prose, as is
    `footnote:` (`note` must start a word). `Vault: keep client notes in the
    work vault, not personal.` has none of these, so it is prose."""
    probe = _strip_cf(lines[0]).strip() if lines else ""
    if not _ATTEMPT.match(probe):
        return False
    second = _strip_cf(lines[1]).strip() if len(lines) > 1 else ""
    return bool(_ATTEMPT_MARK.search(probe) or _WRAPPED.match(second)
                or _BARE.fullmatch(probe))


def _grammar(lines):
    """`(kind, vault, note, reason)` for a pointer attempt."""
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


def classify(body):
    """`(kind, vault, note, reason)` for a body; kind is pointer / malformed /
    full-text. A pointer attempt (`_attempt`) must be the whole body and match
    the grammar exactly, or it is `malformed`; any other body is full text. A
    lone CR ends a line, so a CR inside a pointer leaves a second line and is
    `malformed` too."""
    lines = [line for line in _LINE_BREAK.split(body) if line.strip()]
    if not _attempt(lines):
        return "full-text", None, None, "not a pointer; nothing to resolve"
    kind, name, path, reason = _grammar(lines)
    if kind == "malformed":
        reason += "; if this is prose, reword the first line"
    return kind, name, path, reason


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
    state, reason, real = resolve_pointer(name, note, root)
    if real is None:
        return dict(row, state=state, reason=reason)
    return dict(row, state="resolved", path=real)


def resolve_pointer(name, note, root):
    """`("resolved", None, real path)` or `(state, reason, None)` for a
    pointer's vault name and note path: `resolve`'s logic, which `save` also
    runs on the pointer it is about to write."""
    vault, state, reason = vault_path(name, root)
    if vault is None:
        return state, reason, None
    real, state, reason = note_path(vault, note)
    if real is None:
        return state, reason, None
    return "resolved", None, real


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


# --- save (L-0677): the vault note first, the pointer second ---------------

NOTE_TYPES = ("concept", "decision", "source", "meta", "project-index")
TAG = re.compile(r"[a-z0-9][a-z0-9/_-]*")
_NAME_LINE = re.compile(r"name:[ \t]*(.+?)[ \t]*")
_MEMORY_ID = re.compile(r"memory_id:[ \t]*(.+?)[ \t]*")
_UPDATED = re.compile(r"^updated:[^\r\n]*", re.MULTILINE)
_UPDATE_HEAD = re.compile(r"^## Update \d{4}-\d{2}-\d{2}[ \t]*$", re.MULTILINE)


def today():
    """`YYYY-MM-DD`, UTC: the one clock read in `save` (tests replace it)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _read_bytes(path):
    with _open_regular(path) as handle:
        return handle.read()


def _split_raw(text):
    """`(frontmatter, body)` with every byte and line ending kept: the
    frontmatter runs through its closing `---` line, as `split_body` splits."""
    lines, start = [], 0
    for match in _LINE_BREAK.finditer(text):
        lines.append(text[start:match.end()])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    if lines and _LINE_BREAK.sub("", lines[0]) == "---":
        for index in range(1, len(lines)):
            if _LINE_BREAK.sub("", lines[index]) == "---":
                return "".join(lines[:index + 1]), "".join(lines[index + 1:])
    return "", text


def _field(frontmatter, pattern):
    """The first frontmatter line matching `pattern` (a single-line match,
    never YAML), one pair of surrounding quotes removed; or None."""
    for line in _LINE_BREAK.split(frontmatter)[1:-1]:
        match = pattern.fullmatch(line)
        if match:
            value = match.group(1)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def writer_vault(root):
    """`(vault, reason, exit)`: vault is `{name, path, ascii}` for the ONE
    vault `save` may write, else None with the kept-full-text reason. The rule
    is obsidian-vault's `writer_vault`, restated: with roles, the single
    `primary`; without, `default: true`, else the first; with no `vaults`
    block, the name `memory`. The name is resolved by `vault_path`, so the
    writer and the resolver always agree, and an unavailable vault is never
    replaced by another."""
    config = crew_recall.obsidian_config_path()
    data, problem = _config(config, _obsidian_problem)[:2]
    if problem:
        return None, problem, 1
    guard = data.get("guard", {})
    if not isinstance(guard, dict) or not isinstance(guard.get("asciiOnly", False), bool):
        return None, f"config unreadable: {config}: guard.asciiOnly is not a boolean", 1
    vaults = data.get("vaults") or {}
    if vaults and any(entry.get("role") for entry in vaults.values()):
        found = sorted(n for n, entry in vaults.items() if entry.get("role") == "primary")
        if not found:
            return None, ("no primary: no vault has role primary; nothing is written to a "
                          "recall or ignore vault"), 1
        if len(found) > 1:
            return None, f"several primaries ({', '.join(found)}); refusing to guess", 1
        name = found[0]
    elif vaults:
        name = next((n for n, e in vaults.items() if e.get("default") is True), next(iter(vaults)))
    else:
        crew_raw, crew_problem = _crew_vault_path(root)
        if crew_problem:
            return None, crew_problem, 1
        if crew_raw is None and not data.get("vaultPath"):
            return None, "no vault configured", 0
        name = LEGACY_NAME
    path, _state, reason = vault_path(name, root)
    if path is None:
        return None, f"vault unavailable: {reason}; no other vault is used instead", 1
    if not os.path.isdir(os.path.join(path, ".obsidian")):
        return None, f"not a vault: {name!r} has no .obsidian/ folder", 1
    return {"name": name, "path": path, "ascii": guard.get("asciiOnly") is True}, None, 0


def _contained(vault, note):
    """`(existing note path or None, problem)`: walk the note path below the
    vault with lstat; a symlink is `outside-vault`, and the deepest existing
    component's real path must stay under the vault's real path."""
    current, real_vault = vault, os.path.realpath(vault)
    segments = note.split("/")
    for index, segment in enumerate(segments):
        current = os.path.join(current, segment)
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            return None, f"bad-note-path: cannot examine {note}: {exc.strerror or exc}"
        if stat.S_ISLNK(mode):
            return None, f"outside-vault: {note} passes a symlink inside the vault"
        if not _inside(os.path.realpath(current), real_vault):
            return None, f"outside-vault: {note} resolves outside the vault"
        last = index == len(segments) - 1
        if last and not stat.S_ISREG(mode):
            return None, f"bad-note-path: {note} is there but not a regular file"
        if last:
            return current, None
        if not stat.S_ISDIR(mode):
            return None, f"bad-note-path: {segment!r} on the note path is not a folder"
    return None, None


def _note_text(kind, title, tags, project, memory_id, body, day):
    tag_lines = "".join(f"  - {tag}\n" for tag in tags)
    return (f"---\ntype: {kind}\ntitle: {json.dumps(title, ensure_ascii=False)}\n"
            f"created: {day}\nupdated: {day}\nstatus: seed\ntags:\n{tag_lines}"
            f"project: {json.dumps(project, ensure_ascii=False)}\n"
            f"memory_id: {json.dumps(memory_id, ensure_ascii=False)}\n---\n\n{body}\n")


def _existing_action(existing, memory_id, body, day):
    """`(action, new note text or None, problem)` for a note already there."""
    text = existing.decode("utf-8", errors="replace").lstrip("﻿")
    frontmatter, rest = _split_raw(text)
    found = _field(frontmatter, _MEMORY_ID)
    if found != memory_id:
        return None, None, (f"collision: the note belongs to memory_id {found!r}, not "
                            f"{memory_id!r}; nothing written")
    heads = list(_UPDATE_HEAD.finditer(rest))
    last = rest[heads[-1].end():] if heads else rest
    if _LINE_BREAK.sub("\n", last).strip("\n") == body:
        return "unchanged", None, None
    frontmatter = _UPDATED.sub(f"updated: {day}", frontmatter, count=1)
    return "append", (frontmatter + rest.rstrip("\r\n") + "\n" +
                      f"\n## Update {day}\n\n{body}\n"), None


def _kept(reason, code=1):
    return {"state": f"kept-full-text: {reason}", "reason": reason, "exit": code}


def plan_save(path, root, tags, title=None, note=None, kind="concept", project=None):
    """The whole save, decided and computed before anything is opened for
    write. `state` is `pending` when writes are due (with the note text and
    the new native bytes), else the final state; `exit` is its exit code."""
    try:
        raw = _read_bytes(path)
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"state": "unreadable", "reason": f"cannot read as UTF-8: {exc}", "exit": 1}
    bom = "﻿" if text.startswith("﻿") else ""
    frontmatter, body = _split_raw(text[len(bom):])
    found, vname, vnote, reason = classify(split_body(text[len(bom):]))
    if found == "pointer":
        state, reason, _real = resolve_pointer(vname, vnote, root)
        if state == "resolved":
            return {"state": "already-pointer", "reason": "already a pointer", "exit": 0}
        return {"state": state, "reason": reason, "exit": 1}
    if found == "malformed":
        return {"state": "malformed", "reason": reason, "exit": 1}
    title = title or _field(frontmatter, _NAME_LINE)
    if not title and not note:
        return {"state": "usage", "reason": "no name: line in the memory and no --title",
                "exit": 2}
    vault, reason, code = writer_vault(root)
    if vault is None:
        return _kept(reason, code)
    project = project or os.path.basename(os.path.abspath(root))
    if note is None:
        if "/" in title or "/" in project:
            return _kept(f"bad-note-path: the title or project holds '/': {title!r}")
        note = f"memories/{project}/{title}.md"
    problem = _path_problem(note)
    if problem:
        return _kept(f"bad-note-path: {problem}")
    title = note.rsplit("/", 1)[-1][:-3]
    body = _LINE_BREAK.sub("\n", body).strip("\n")
    if not body.strip():
        return _kept("the memory has no body to save")
    if vault["ascii"] and not all(s.isascii() for s in (title, project, body, *tags)):
        return _kept("ascii-required: the vault sets guard.asciiOnly and the title, project, "
                     "tags or body hold a non-ASCII character; crew does not transliterate")
    pointer = f"vault: {vault['name']} | note: {note}"
    if classify(pointer)[0] != "pointer":
        return _kept(f"the vault name {vault['name']!r} cannot be written as a pointer")
    existing, problem = _contained(vault["path"], note)
    if problem:
        return _kept(problem)
    memory_id = os.path.splitext(os.path.basename(path))[0]
    day = today()
    plan = {"state": "pending", "exit": 1, "file": path, "root": root, "vault": vault["name"],
            "note": note, "pointer": pointer, "note_path": os.path.join(vault["path"], note),
            "vault_path": vault["path"], "native": raw, "existing": None}
    if existing is None:
        plan.update(action="create", text=_note_text(kind, title, tags, project, memory_id,
                                                     body, day))
    else:
        try:
            plan["existing"] = _read_bytes(existing)
        except OSError as exc:
            return _kept(f"bad-note-path: cannot read the existing note: {exc}")
        action, new, problem = _existing_action(plan["existing"], memory_id, body, day)
        if problem:
            return _kept(problem)
        plan.update(action=action, text=new)
    if frontmatter and not frontmatter.endswith(("\n", "\r")):
        frontmatter += "\n"
    plan["new_native"] = (bom + frontmatter + pointer + "\n").encode("utf-8")
    return plan


def _write_temp(directory, data):
    """A new temp file in `directory` holding `data`, flushed to disk."""
    handle, temp = tempfile.mkstemp(dir=directory, prefix=".crew-memory-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        os.unlink(temp)
        raise
    return temp


def _drop(temp):
    if temp and os.path.lexists(temp):
        os.unlink(temp)


def apply_note(plan):
    """Write the note: create through a temp file linked to its name (never
    over an existing file), append through a temp file and `os.replace` after
    re-reading it. Raises OSError; never touches the native memory."""
    if plan["action"] == "unchanged":
        return
    dest, data = plan["note_path"], plan["text"].encode("utf-8")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    existing, problem = _contained(plan["vault_path"], plan["note"])
    if problem or (existing is None) != (plan["existing"] is None):
        raise OSError(problem or "the note appeared or vanished during save")
    if existing is not None and _read_bytes(dest) != plan["existing"]:
        raise OSError("the note changed during save")
    temp = _write_temp(os.path.dirname(dest), data)
    try:
        if existing is not None:
            os.replace(temp, dest)
            return
        try:
            os.link(temp, dest)
        except FileExistsError as exc:
            raise OSError("the note appeared during save") from exc
        except OSError:
            if os.path.lexists(dest):  # no hard links here: the closest equivalent
                raise
            os.replace(temp, dest)
    finally:
        _drop(temp)


def apply_pointer(plan):
    """Replace the native memory's body with the pointer: frontmatter bytes
    kept, temp file in the same folder, mode copied, `os.replace`. Raises
    OSError; refuses a file that changed since it was planned."""
    path = plan["file"]
    if _read_bytes(path) != plan["native"]:
        raise ValueError("the memory file changed during save")
    temp = _write_temp(os.path.dirname(os.path.abspath(path)), plan["new_native"])
    try:
        os.chmod(temp, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(temp, path)
    finally:
        _drop(temp)


def apply_save(plan):
    """Note first, read back, then the pointer. Returns the final row."""
    row = {k: plan[k] for k in ("file", "vault", "note", "pointer", "action")}
    try:
        apply_note(plan)
    except OSError as exc:
        return dict(row, **_kept(f"note write failed: {exc}"))
    want = plan["text"].encode("utf-8") if plan["text"] is not None else plan["existing"]
    try:
        same = _read_bytes(plan["note_path"]) == want
    except OSError:
        same = False
    state, reason, _real = resolve_pointer(plan["vault"], plan["note"], plan["root"])
    if not same or state != "resolved":
        why = reason if state != "resolved" else "its bytes are not what was written"
        return dict(row, **_kept(f"note not readable after write ({state}: {why})"))
    try:
        apply_pointer(plan)
    except ValueError as exc:
        return dict(row, **_kept(str(exc)))
    except OSError as exc:
        return dict(row, **_kept(f"pointer write failed (the note is saved): {exc}"))
    return dict(row, state="pointer-written", reason=None, exit=0)


def _emit(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def _row_text(row):
    if row["state"] == "resolved":
        return f"{row['vault']}/{row['note']}"
    where = f"{row['vault']}/{row['note']}  " if row["vault"] and row["note"] else ""
    return where + row["reason"]


def _save_cli(args, root):
    if not os.path.isfile(args.file):
        print(f"crew_memory: no such file: {args.file}", file=sys.stderr)
        return 2
    plan = plan_save(args.file, root, args.tag, args.title, args.note, args.type, args.project)
    if plan["state"] == "usage":
        print(f"crew_memory save: {plan['reason']}", file=sys.stderr)
        return 2
    row = plan
    if plan["state"] == "pending" and args.apply:
        row = apply_save(plan)
    shown = {k: row.get(k) for k in ("state", "reason", "file", "vault", "note", "action",
                                     "pointer")}
    if args.json:
        _emit(json.dumps(shown, ensure_ascii=False))
    else:
        _emit(f"state: {'dry-run' if row['state'] == 'pending' else row['state']}")
        for key in ("vault", "note", "action", "pointer"):
            if row.get(key):
                _emit(f"{key}: {row[key]}")
        if row["state"] == "pending":
            _emit("nothing written; run again with --apply to write")
        elif row.get("reason") and not row["state"].startswith("kept-full-text"):
            _emit(f"reason: {row['reason']}")
    return row["exit"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("resolve", help="map one memory file's pointer to its note")
    one.add_argument("--file", required=True)
    every = sub.add_parser("check", help="report the state of every memory file")
    every.add_argument("--memory-dir", required=True)
    keep = sub.add_parser("save", help="write the vault note, then make the memory a pointer")
    keep.add_argument("--file", required=True)
    keep.add_argument("--tag", action="append", default=[])
    keep.add_argument("--title")
    keep.add_argument("--note")
    keep.add_argument("--type", choices=NOTE_TYPES, default="concept")
    keep.add_argument("--project")
    keep.add_argument("--apply", action="store_true")
    for each in (one, every, keep):
        each.add_argument("--root", default=".")
        each.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.command == "save":
        if not args.tag or not all(TAG.fullmatch(tag) for tag in args.tag):
            keep.error(f"at least one --tag, each matching {TAG.pattern}")
        return _save_cli(args, root)
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
