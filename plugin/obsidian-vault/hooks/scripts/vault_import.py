"""Import notes from another vault or a plain Markdown folder INTO the primary vault.

    import --source DIR|VAULT [--dest-subdir SUB] [--suffix-collisions] [--apply] [--json]

Dry run by default: nothing is created, not even a directory. With --apply
each Markdown note is copied to `<primary>/<dest-subdir>/<relative path>`
(dest-subdir defaults to `imported/<source folder name>`), carrying two
provenance keys in its frontmatter:

    imported_from: "<absolute source path of that file>"
    imported_at: YYYY-MM-DD   (UTC)

Never overwrites. A destination that already exists is:
  * `already imported` when its own `imported_from` names this same source
    file - which is what makes a re-run a no-op;
  * a `collision` otherwise - skipped and reported, or, only with
    --suffix-collisions, written beside it as `<name> (imported).md`.

Each file's full text is computed before anything is opened for writing, and
the write is an exclusive create (mode "x"), so an existing file can never be
truncated - not by a collision, not by a race, and not by an exception while
building the payload. Output is LF-only.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_setup  # noqa: E402  pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2

SKIP_DIRS = {".obsidian", ".git", ".trash", "node_modules", ".claude"}
FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)?---\n", re.DOTALL)
IMPORTED_FROM_RE = re.compile(r"^imported_from:\s*(.+?)\s*$", re.MULTILINE)


def utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _yaml_str(value):
    # JSON string syntax is a valid YAML double-quoted scalar, and it escapes
    # the backslashes and colons of a Windows path correctly.
    return json.dumps(value)


def with_provenance(text, source_abs, today):
    """The note text with imported_from/imported_at in its frontmatter.

    Existing provenance keys are kept, not replaced: a note imported twice
    along a chain still names where it first came from.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    extra = []
    match = FRONTMATTER_RE.match(text)
    body_fm = (match.group(1) or "") if match else ""
    if not re.search(r"^imported_from:", body_fm, re.MULTILINE):
        extra.append(f"imported_from: {_yaml_str(source_abs)}")
    if not re.search(r"^imported_at:", body_fm, re.MULTILINE):
        extra.append(f"imported_at: {today}")
    if not extra:
        return text
    if match:
        return "---\n" + body_fm + "\n".join(extra) + "\n---\n" + text[match.end():]
    return "---\n" + "\n".join(extra) + "\n---\n" + text


def imported_from(path):
    """The imported_from value recorded in an existing note, or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    match = FRONTMATTER_RE.match(head.replace("\r\n", "\n"))
    if not match or not match.group(1):
        return None
    found = IMPORTED_FROM_RE.search(match.group(1))
    if not found:
        return None
    raw = found.group(1)
    try:
        return json.loads(raw) if raw.startswith('"') else raw
    except ValueError:
        return raw


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _inside(child, parent):
    child, parent = _norm(child), _norm(parent)
    return child == parent or child.startswith(parent + os.sep)


def walk_notes(source, exclude=None):
    """(markdown relpaths, other file count), sorted, skipping tool dirs and `exclude`."""
    notes, others = [], 0
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not (exclude and _inside(os.path.join(root, d), exclude)))
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), source)
            if name.lower().endswith(".md"):
                notes.append(rel)
            else:
                others += 1
    return notes, others


def suffixed(dest):
    stem, ext = os.path.splitext(dest)
    candidate = f"{stem} (imported){ext}"
    n = 2
    while os.path.exists(candidate):
        candidate = f"{stem} (imported {n}){ext}"
        n += 1
    return candidate


def plan_import(source, target, dest_subdir, suffix_collisions, today):
    """A list of per-file actions; nothing is written here."""
    notes, others = walk_notes(source, exclude=target)
    actions = []
    for rel in notes:
        src = os.path.join(source, rel)
        src_abs = os.path.abspath(src)
        dest = os.path.normpath(os.path.join(target, dest_subdir, rel))
        action = {"source": src_abs, "dest": dest, "status": "write"}
        if os.path.exists(dest):
            if imported_from(dest) == src_abs:
                action["status"] = "already-imported"
            elif suffix_collisions:
                action["status"] = "write-suffixed"
                action["collided_with"] = dest
                action["dest"] = suffixed(dest)
            else:
                action["status"] = "collision"
        if action["status"].startswith("write"):
            try:
                with open(src, "r", encoding="utf-8") as fh:
                    raw = fh.read()
            except UnicodeDecodeError:
                action["status"] = "unreadable"
                action["reason"] = "not UTF-8"
            except OSError as exc:
                action["status"] = "unreadable"
                action["reason"] = f"{type(exc).__name__}: {exc}"
            else:
                action["text"] = with_provenance(raw, src_abs, today)
        actions.append(action)
    return actions, others


def apply_actions(actions):
    """Write every planned file; an existing destination is never opened for write."""
    for action in actions:
        if not action["status"].startswith("write"):
            continue
        text = action["text"]  # computed before anything is opened
        os.makedirs(os.path.dirname(action["dest"]), exist_ok=True)
        try:
            with open(action["dest"], "x", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            action["written"] = True
        except FileExistsError:
            action["status"] = "collision"
            action["written"] = False


def resolve_source(value):
    if os.path.isdir(os.path.expanduser(value)):
        return os.path.abspath(os.path.expanduser(value)), None
    vaults = obsidian_common.discover_vaults()
    if value in vaults:
        return os.path.abspath(vaults[value]["path"]), None
    return None, f"no directory and no known vault named {value!r}"


def cmd_import(args, prober):  # pylint: disable=unused-argument
    source, err = resolve_source(args.source)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    target_name, target = vault_setup.primary_vault()
    if not target:
        print("no primary vault configured - run `adopt --role NAME=primary` first",
              file=sys.stderr)
        return EXIT_USAGE
    target = os.path.abspath(target)
    if _norm(target) == _norm(source):
        print("refused: the source is the primary vault itself", file=sys.stderr)
        return EXIT_USAGE
    if _inside(source, target):
        print("refused: the source is inside the primary vault", file=sys.stderr)
        return EXIT_USAGE
    dest_subdir = args.dest_subdir
    if dest_subdir is None:
        dest_subdir = os.path.join("imported", os.path.basename(os.path.normpath(source)))
    if os.path.isabs(dest_subdir) or ".." in dest_subdir.replace("\\", "/").split("/"):
        print("--dest-subdir must be a relative path inside the vault", file=sys.stderr)
        return EXIT_USAGE

    actions, others = plan_import(source, target, dest_subdir, args.suffix_collisions,
                                  utc_today())
    if args.apply:
        apply_actions(actions)
    counts = {}
    for action in actions:
        counts[action["status"]] = counts.get(action["status"], 0) + 1
    report = {
        "source": source, "target_vault": target_name, "target": target,
        "dest_subdir": dest_subdir, "applied": bool(args.apply),
        "counts": counts, "non_markdown_skipped": others,
        "files": [{k: v for k, v in a.items() if k != "text"} for a in actions],
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        verb = "Imported" if args.apply else "Would import"
        writes = counts.get("write", 0) + counts.get("write-suffixed", 0)
        print(f"{verb} {writes} note(s) from {source} into {target_name} "
              f"({os.path.join(target, dest_subdir)})")
        for status in ("already-imported", "collision", "write-suffixed", "unreadable"):
            if counts.get(status):
                print(f"  {status}: {counts[status]}")
        if others:
            print(f"  non-markdown files skipped: {others}")
        for action in actions:
            if action["status"] == "collision":
                print(f"  COLLISION (skipped, not overwritten): {action['dest']}")
            elif action["status"] == "unreadable":
                print(f"  UNREADABLE: {action['source']} ({action['reason']})")
        if not args.apply:
            print("\nDry run - nothing written. Re-run with --apply to write.")
    if not args.apply:
        pending = counts.get("write", 0) + counts.get("write-suffixed", 0)
        return EXIT_PROBLEMS if pending or counts.get("collision") else EXIT_OK
    return EXIT_PROBLEMS if counts.get("collision") or counts.get("unreadable") else EXIT_OK


def add_parsers(sub):
    s = sub.add_parser("import", help="copy notes from a folder or vault into the primary "
                                      "vault with provenance; never overwrites")
    s.add_argument("--source", required=True, help="a directory, or a known vault name")
    s.add_argument("--dest-subdir", help="relative folder inside the primary vault "
                                         "(default imported/<source folder name>)")
    s.add_argument("--suffix-collisions", action="store_true",
                   help="write a colliding note as '<name> (imported).md' instead of "
                        "skipping it")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_import)
