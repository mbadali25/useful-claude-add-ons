"""Read-only crew status for one repository, at most 40 lines.

    python3 crew_status.py [--root .] [--memory]
    python3 crew_status.py [--root .] --approvals

Replaces what `/crew:pm`, `/crew:roster` and `/crew:scale` reported, and does
none of what they did: no dispatch, no config edit, no file written anywhere.
Every section is a fact read from disk or git, or it says it could not tell.

`--approvals` prints only the tickets whose approval is missing, stale or
unaccepted, as ready-to-paste `/crew:approve <id>` lines (T-0070).

`--memory` adds the context hook's own numbers by running `crew_context.py
--stats --root <root>` from this directory when that script exists, and says
"context hook not installed" when it does not. `--root` is passed explicitly:
without it `crew_context.py` resolves `CLAUDE_PROJECT_DIR` first, so a status
run for one repo from a session in another read the other repo's log.

Read-only is a property, not a promise: git runs with `GIT_OPTIONAL_LOCKS=0`
so `git status` cannot refresh the index and with `core.fsmonitor=false` so a
configured fsmonitor hook never runs, and bytecode writing is off so even
the import of the sibling modules leaves no `__pycache__` behind. The test
suite snapshots every mtime in a fixture repo around a run.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

import crew_common  # noqa: E402
import crew_freshness  # noqa: E402
import crew_migrate  # noqa: E402
import crew_shell  # noqa: E402
import crew_tracker  # noqa: E402
import review_ledger  # noqa: E402
import verify_record  # noqa: E402
from crew_common import read_text  # noqa: E402

MAX_LINES = 40
HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXT_SCRIPT = os.path.join(HERE, "crew_context.py")
_GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def _git(root, *args):
    argv = ("git", "-c", "core.fsmonitor=false") + args
    try:
        # The git which() resolves, never the bare name (L-1508): the argv
        # keeps its literal shape, which sabotage_migrate.py anchors on.
        done = subprocess.run((crew_common.require_tool(argv[0]),) + argv[1:],
                              cwd=root, capture_output=True, text=True,
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


def _tracker_line(root):
    # Both config shapes, through the one resolver every tracker write uses:
    # crew.json's kind shown while the commands gated on config.json's string
    # was how the two disagreed with nothing reporting it.
    return "tracker  " + crew_tracker.describe(crew_tracker.resolve(root))


def _config_lines(root):
    crew = _json(crew_common.repo_config_file(root, "crew.json"))
    legacy = _json(crew_common.repo_config_file(root, "config.json"))
    lines, cfg = _config_lines_for(root, crew, legacy)
    # Which file is in force, when it is not simply this checkout's (T-0088).
    source = crew_common.repo_config_source_line(root)
    if source:
        lines.insert(1, f"config   {source}")
    return lines, cfg


def _config_lines_for(root, crew, legacy):
    if crew is not None and not isinstance(crew, dict):
        return ["config   .crew/crew.json unreadable - status cannot tell the setup"], {}
    if isinstance(crew, dict):
        agents = crew.get("agents") or []
        return [f"config   .crew/crew.json schema {crew.get('schema', '?')}",
                f"roster   {', '.join(agents) or 'none'} (1.0 roster: {', '.join(crew_migrate.ROSTER)})",
                _tracker_line(root)], crew
    if isinstance(legacy, dict):
        roles = legacy.get("roles") if isinstance(legacy.get("roles"), list) else []
        kept = [r for r in crew_migrate.ROSTER
                if r in roles or any(crew_migrate.RENAMED.get(x) == r for x in roles)]
        return [f"config   .crew/config.json schema {legacy.get('schema', '?')} - run /crew:migrate",
                f"roster   {len(roles)} roles active; 1.0 keeps {', '.join(kept) or 'none of them'}",
                _tracker_line(root)], legacy
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
    open_ids, owner_ids = [], []
    for line in (read_text(os.path.join(root, ".work", "INDEX.md")) or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) > 1 and cells[1].lower() in ("open", "in-progress", "in progress", "review"):
            open_ids.append(cells[0])
        elif len(cells) > 1 and cells[1].lower() == "needs-owner":
            # T-0037: open, but waiting on the owner -- its own line. The
            # closed words (cancelled, superseded) appear on neither.
            owner_ids.append(cells[0])
    lines = [f"tickets  {len(dirs)} ticket dir(s), {len(files)} legacy file(s)"]
    if open_ids:
        lines.append(f"open     {_first_five(open_ids)}")
    if owner_ids:
        lines.append(f"owner    {_first_five(owner_ids)} (needs-owner)")
    return lines


def _first_five(ids):
    return ", ".join(ids[:5]) + (f" (+{len(ids) - 5})" if len(ids) > 5 else "")


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
        path = os.path.join(folder, name)
        # The ledger's own summary, so status counts rounds exactly as the
        # budget does: refunded tool-failure rounds are not "used" (T-0087).
        summary = review_ledger.summary(*review_ledger.load(path), name[:-5], path)
        if summary["state"] == review_ledger.UNKNOWN:
            lines.append(f"review   {name[:-5]}: UNKNOWN (ledger unreadable)")
            continue
        used = f"{summary['rounds_spent']}/{summary['budget']} rounds used"
        line = f"review   {name[:-5]}: {summary['state']}, {used}"
        if summary["rounds_refunded"]:
            line += f", {summary['rounds_refunded']} refunded"
        lines.append(line)
    if len(names) > 3:
        lines.append(f"review   (+{len(names) - 3} older ledgers)")
    return lines


def _verify_line(root):
    state, rules = verify_record.read_record(root)
    if state == "absent":
        return "verify   no gate record yet"
    if state != "ok":
        return "verify   UNKNOWN (gate record unreadable)"
    counts = {}
    for rule in rules.values():
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
    """One line: the metrics file in the main checkout's `.crew/` from a linked
    worktree (L-0582), `could not tell` when git cannot name it, and this
    worktree's own stranded copies named as not counted, on the same line so
    the 40-line budget is unchanged."""
    crew_dir, problem = crew_common.metrics_crew_dir(root)
    if problem:
        return f"metrics  could not tell ({' '.join(problem.split())}) - nothing read"
    own = os.path.normcase(os.path.realpath(os.path.join(root, ".crew")))
    shown = None if os.path.normcase(os.path.realpath(crew_dir)) == own else crew_dir
    line = "metrics  none recorded"
    for name in crew_common.METRICS_NAMES:
        path = os.path.join(crew_dir, name)
        text = read_text(path)
        if text is not None:
            rows = sum(1 for row in text.splitlines() if row.strip())
            label = path if shown else f".crew/{name}"
            line = f"metrics  {label}: {rows} row(s)"
            break
    if shown and line.endswith("none recorded"):
        line += f" in the main checkout's {shown}"
    stranded = crew_common.stranded_metrics_copies(root)
    if stranded:
        line += f"; this worktree's own {', '.join(stranded)} not counted"
    return line


def _memory_lines(root, budget):
    if not os.path.isfile(CONTEXT_SCRIPT):
        return ["memory   context hook not installed (crew_context.py absent)"]
    try:
        done = subprocess.run([sys.executable, "-B", CONTEXT_SCRIPT, "--stats", "--root", root],
                              cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20, check=False,
                              stdin=subprocess.DEVNULL,
                              env=dict(_GIT_ENV, CLAUDE_PROJECT_DIR=root))
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"memory  crew_context.py --stats could not run: {exc}"]
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["no stderr"])[0]
        return [f"memory   crew_context.py --stats failed (exit {done.returncode}): {first[:80]}"]
    body = [line.rstrip() for line in done.stdout.splitlines() if line.strip()]
    lines = ["memory   " + (body[0] if body else "no stats reported")]
    lines += ["         " + line for line in body[1:]]
    if len(lines) > budget:
        lines = lines[:budget - 1] + [f"         ... {len(lines) - budget + 1} more line(s) clipped"]
    return lines


def _inert_line(root):
    """`inert    key=value (ticket), ...` for every setting this crew does not
    act on, or None (T-0070). A failed check says so rather than vanishing."""
    try:
        import crew_config  # pylint: disable=import-outside-toplevel
        entries = crew_config.inert_settings(root)
        return "inert    " + crew_config.inert_items(entries, crew_config.INERT_LIMIT) if entries else None
    except Exception as exc:  # pylint: disable=broad-except
        return f"inert    could not tell ({exc.__class__.__name__})"


def pending_approvals(root):
    """`(pending, invalid)`: `pending` is `[(ticket, why)]` for every open INDEX
    ticket with a spec.md and plan.md that validate and whose receipt is
    missing, stale or unaccepted; `invalid` is the open tickets whose spec and
    plan exist but do not validate. Merged, closed, spec-only and currently
    approved tickets are in neither: approving them changes nothing."""
    # pylint: disable=import-outside-toplevel
    import crew_autopilot
    import crew_ticket
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    pending, invalid = [], []
    for ticket in crew_autopilot.open_index_tickets(top):
        folder = crew_ticket.ticket_dir(top, ticket)
        if not all(os.path.isfile(os.path.join(folder, n)) for n in ("spec.md", "plan.md")):
            continue
        if crew_ticket.validate(top, ticket):
            invalid.append(ticket)
            continue
        result = crew_ticket.accepted(top, ticket)
        if result["status"] == "approved":
            continue
        if result["status"] == "none" and result.get("receipt") is None \
                and str(result.get("why", "")).endswith("has no approved plan"):
            why = "no approval"
        else:
            why = f"{result['status']}: {result.get('why')}"
        pending.append((ticket, why))
    return pending, invalid


def _index_unreadable(root):
    """Why `.work/INDEX.md` cannot be read as UTF-8, or None when it can. The
    approvals walk reads INDEX through a reader that turns every failure into
    "no tickets", so an unknown would print as "nothing needs approval"."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    path = os.path.join(top, ".work", "INDEX.md")
    try:
        with open(path, "rb") as fh:
            fh.read().decode("utf-8")
    except FileNotFoundError:
        return "no .work/INDEX.md"
    except UnicodeDecodeError:
        return ".work/INDEX.md is not UTF-8"
    except (OSError, ValueError) as exc:
        return f".work/INDEX.md could not be read: {exc.__class__.__name__}"
    return None


def approvals_lines(root):
    unknown = _index_unreadable(root)
    if unknown:
        return [f"could not tell ({unknown})"]
    pending, invalid = pending_approvals(root)
    lines = [f"/crew:approve {ticket}  ({why})" for ticket, why in pending]
    if invalid:
        one = len(invalid) == 1
        lines.append(f"{len(invalid)} {'ticket' if one else 'tickets'} with a spec and plan "
                     f"that do not validate {'is' if one else 'are'} not listed: "
                     + ", ".join(invalid))
    return lines or ["nothing needs approval"]


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
    inert = _inert_line(root)
    if inert:
        lines.append(inert)
    lines += _ticket_lines(root)
    lines += _review_lines(root)
    lines.append(_verify_line(root))
    # T-0040: native Windows only. Read from config and the machine-local
    # probe cache; runs no wsl.exe, no pwsh and no git.
    shell = crew_shell.status_line(root)
    if shell:
        lines.append(shell)
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
    parser.add_argument("--approvals", action="store_true",
                        help="only the tickets whose approval is missing, stale or unaccepted")
    args = parser.parse_args(argv)
    if args.approvals:
        print("\n".join(approvals_lines(os.path.abspath(args.root))))
        return 0
    print("\n".join(collect(args.root, memory=args.memory)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
