"""Read-only crew status for one repository, at most 40 lines.

    python3 crew_status.py [--root .] [--memory]

Replaces what `/crew:pm`, `/crew:roster` and `/crew:scale` reported, and does
none of what they did: no dispatch, no config edit, no file written anywhere.
Every section is a fact read from disk or git, or it says it could not tell.

`--memory` adds the context hook's own numbers by running `crew_context.py
--stats --root <root>` from this directory when that script exists, and says
"context hook not installed" when it does not. `--root` is passed explicitly:
without it `crew_context.py` resolves `CLAUDE_PROJECT_DIR` first, so a status
run for one repo from a session in another read the other repo's log.

Read-only is a property, not a promise: git runs with `GIT_OPTIONAL_LOCKS=0`
so `git status` cannot refresh the index, and bytecode writing is off so even
the import of the sibling modules leaves no `__pycache__` behind. The test
suite snapshots every mtime in a fixture repo around a run.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse
import json
import os
import subprocess

import crew_freshness
import crew_migrate
from crew_common import read_text

MAX_LINES = 40
HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXT_SCRIPT = os.path.join(HERE, "crew_context.py")
_GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def _git(root, *args):
    try:
        done = subprocess.run(("git",) + args, cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10, check=False,
                              stdin=subprocess.DEVNULL, env=_GIT_ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return "corrupt"


def _config_lines(root):
    crew = _json(os.path.join(root, ".crew", "crew.json"))
    legacy = _json(os.path.join(root, ".crew", "config.json"))
    if isinstance(crew, dict):
        agents = crew.get("agents") or []
        tracker = (crew.get("tracker") or {}).get("kind", "?") if isinstance(crew.get("tracker"), dict) else "?"
        return [f"config   .crew/crew.json schema {crew.get('schema', '?')}",
                f"roster   {', '.join(agents) or 'none'} (1.0 roster: {', '.join(crew_migrate.ROSTER)})",
                f"tracker  {tracker}"], crew
    if isinstance(legacy, dict):
        roles = legacy.get("roles") if isinstance(legacy.get("roles"), list) else []
        kept = [r for r in crew_migrate.ROSTER
                if r in roles or any(crew_migrate.RENAMED.get(x) == r for x in roles)]
        return [f"config   .crew/config.json schema {legacy.get('schema', '?')} - run /crew:migrate",
                f"roster   {len(roles)} roles active; 1.0 keeps {', '.join(kept) or 'none of them'}",
                f"tracker  {legacy.get('tracker', '?')}"], legacy
    if crew == "corrupt" or legacy == "corrupt":
        return ["config   unreadable JSON in .crew/ - status cannot tell the setup"], {}
    return ["config   none - run /crew:init"], {}


def _ticket_lines(root):
    folder = os.path.join(root, ".work", "tickets")
    try:
        names = os.listdir(folder)
    except OSError:
        return ["tickets  none (.work/tickets/ absent)"]
    dirs = sorted(n for n in names if os.path.isdir(os.path.join(folder, n)))
    files = [n for n in names if n.endswith(".md")]
    open_ids = []
    for line in (read_text(os.path.join(root, ".work", "INDEX.md")) or "").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 1 and cells[1].lower() in ("open", "in-progress", "in progress", "review"):
            open_ids.append(cells[0])
    lines = [f"tickets  {len(dirs)} ticket dir(s), {len(files)} legacy file(s)"]
    if open_ids:
        shown = ", ".join(open_ids[:5]) + (f" (+{len(open_ids) - 5})" if len(open_ids) > 5 else "")
        lines.append(f"open     {shown}")
    return lines


def _review_lines(root):
    common = _git(root, "rev-parse", "--git-common-dir")
    if common is None:
        return ["review   unknown (not a git repository)"]
    folder = os.path.join(root, common, "crew", "review")
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
    except OSError:
        return ["review   no ledgers"]
    names.sort(key=lambda n: os.path.getmtime(os.path.join(folder, n)), reverse=True)
    lines = []
    for name in names[:3]:
        data = _json(os.path.join(folder, name))
        if not isinstance(data, dict):
            lines.append(f"review   {name[:-5]}: UNKNOWN (ledger unreadable)")
            continue
        rounds = data.get("rounds") if isinstance(data.get("rounds"), list) else []
        lines.append(f"review   {name[:-5]}: {data.get('state') or 'EMPTY'}, {len(rounds)}/2 rounds")
    if len(names) > 3:
        lines.append(f"review   (+{len(names) - 3} older ledgers)")
    return lines


def _verify_line(root):
    record = _json(os.path.join(root, ".crew", ".verify-gate.record.json"))
    if record is None:
        return "verify   no gate record yet"
    if not isinstance(record, dict) or not isinstance(record.get("rules"), dict):
        return "verify   UNKNOWN (gate record unreadable)"
    counts = {}
    for rule in record["rules"].values():
        state = rule.get("status", "unknown") if isinstance(rule, dict) else "unknown"
        counts[state] = counts.get(state, 0) + 1
    return "verify   " + (", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no rules recorded")


def _codemap_line(root, cfg):
    if not os.path.isdir(os.path.join(root, ".crew", "codemap")):
        return "codemap  none - /crew:onboard writes one"
    info = crew_freshness.read_knowledge(root, cfg if isinstance(cfg, dict) else {})
    line = f"codemap  {info['subsystems']} subsystem(s)"
    if info["behind"]:
        line += f", behind: {', '.join(info['behind'][:4])}"
    if info["unresolvable"]:
        line += f", unresolvable: {', '.join(info['unresolvable'][:4])}"
    return line


def _metrics_line(root):
    for name in ("metrics.jsonl", "metrics.md"):
        text = read_text(os.path.join(root, ".crew", name))
        if text is not None:
            rows = sum(1 for line in text.splitlines() if line.strip())
            return f"metrics  .crew/{name}: {rows} row(s)"
    return "metrics  none recorded"


def _memory_lines(root, budget):
    if not os.path.isfile(CONTEXT_SCRIPT):
        return ["memory   context hook not installed (crew_context.py absent)"]
    try:
        done = subprocess.run([sys.executable, "-B", CONTEXT_SCRIPT, "--stats", "--root", root],
                              cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20, check=False,
                              stdin=subprocess.DEVNULL, env=_GIT_ENV)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"memory   crew_context.py --stats could not run: {exc}"]
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["no stderr"])[0]
        return [f"memory   crew_context.py --stats failed (exit {done.returncode}): {first[:80]}"]
    body = [line.rstrip() for line in done.stdout.splitlines() if line.strip()]
    lines = ["memory   " + (body[0] if body else "no stats reported")]
    lines += ["         " + line for line in body[1:]]
    if len(lines) > budget:
        lines = lines[:budget - 1] + [f"         ... {len(lines) - budget + 1} more line(s) clipped"]
    return lines


def collect(root, memory=False):
    root = os.path.abspath(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git(root, "rev-parse", "--short=8", "HEAD") or "?"
    porcelain = _git(root, "status", "--porcelain")
    tree = "unknown" if porcelain is None else (
        "clean" if not porcelain else f"{len(porcelain.splitlines())} changed path(s)")
    lines = [f"crew status  {os.path.basename(root)}  {branch}@{head}  tree {tree}"]
    config_lines, cfg = _config_lines(root)
    lines += config_lines
    lines += _ticket_lines(root)
    lines += _review_lines(root)
    lines.append(_verify_line(root))
    lines.append(_codemap_line(root, cfg))
    lines.append(_metrics_line(root))
    handoff = os.path.isfile(os.path.join(root, ".work", "HANDOFF.md"))
    lines.append("handoff  " + ("pending (.work/HANDOFF.md)" if handoff else "none"))
    interrupted = crew_migrate.find_interrupted(root)
    if interrupted:
        lines.append(f"migrate  INTERRUPTED apply at {interrupted} - /crew:migrate --rollback it")
    if memory:
        lines += _memory_lines(root, MAX_LINES - len(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + [f"... {len(lines) - MAX_LINES + 1} line(s) clipped"]
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--memory", action="store_true", help="add crew_context.py --stats")
    args = parser.parse_args(argv)
    print("\n".join(collect(args.root, memory=args.memory)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
