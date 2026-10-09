"""Read-only crew status for one repository, at most 40 lines.

    python3 crew_status.py [--root .] [--memory]
    python3 crew_status.py [--root .] --approvals
    python3 crew_status.py [--root .] --owner

Replaces what `/crew:pm`, `/crew:roster` and `/crew:scale` reported, and does
none of what they did: no dispatch, no config edit, no file written anywhere.
Every section is a fact read from disk or git, or it says it could not tell.
The `agents` line runs `verify_agents.check`: the agents `.crew/verify.json`
names that are not installed on this machine, or `unknown` when a registry or
settings file will not parse.
`in-flight` lines (T-0049) are `crew_inflight.survey`'s, which only reads.

`--approvals` prints only the tickets whose approval is missing, stale or
unaccepted, as ready-to-paste `/crew:approve <id>` lines (T-0070).

`--owner` (L-0551) lists every open ticket stopped on a person, one line each with the
command to type, from `crew_autopilot_owner.owner_items` -- autopilot's own phase read with
no policy and no bundle rebuild; the default report carries its count as the `waiting`
line. A module that cannot be imported, or no INDEX.md, is `unknown`, never "nothing".

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

The `graph-ignore` line (T-0064) is `crew_graph_ignore.coverage`: whether the
next graph build would read a secrets-denylisted path the root
`.graphifyignore` does not exclude -- `ok`, `UNCOVERED` with the paths, or
`unknown` with the reason. Paths only, never file content.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

import crew_common  # noqa: E402
import crew_freshness  # noqa: E402
import crew_graph_ignore  # noqa: E402
import crew_migrate  # noqa: E402
import crew_shell  # noqa: E402
import crew_state  # noqa: E402
import crew_tracker  # noqa: E402
import review_ledger  # noqa: E402
import verify_agents  # noqa: E402
import verify_record  # noqa: E402
from crew_common import read_text  # noqa: E402

MAX_LINES = 40
INFLIGHT_SHOWN = 5
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
    legacy_setup, why = _is_0_20_setup(root, legacy) if isinstance(legacy, dict) else (None, "")
    if isinstance(legacy, dict) and legacy_setup is False:
        # L-0713: `/crew:init` writes this file, every gate reads it, and
        # nothing in it needs `/crew:migrate`.
        roles = [r for r in legacy.get("roles") or [] if isinstance(r, str)]
        return [f"config   .crew/config.json schema {legacy.get('schema')}",
                f"roster   {', '.join(roles) or 'none'} (1.0 roster: {', '.join(crew_migrate.ROSTER)})",
                _tracker_line(root)], legacy
    if isinstance(legacy, dict) and legacy_setup is None:
        roles = [r for r in legacy.get("roles") or [] if isinstance(r, str)] \
            if isinstance(legacy.get("roles"), list) else []
        return [f"config   .crew/config.json schema {legacy.get('schema', '?')} - could not tell "
                f"whether /crew:migrate is needed ({why})",
                f"roster   {', '.join(roles) or 'none'} (1.0 roster: {', '.join(crew_migrate.ROSTER)})",
                _tracker_line(root)], legacy
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


def _is_0_20_setup(root, legacy):
    """Whether `.crew/config.json` (with no crew.json beside it) still holds
    something only `/crew:migrate` moves, as (True | False | None, reason).

    True: a schema older than the current one, a role the 1.0 roster does not
    have (`qa-reviewer` included: migrate renames it), a `.work/tickets/<ID>.md`
    ticket file (an id-shaped name, as `crew_migrate._ticket_candidates` reads
    it, so a README there is not one), or a PM journal. A config `/crew:init`
    wrote has none of these: False. None is could-not-tell - a `schema` that is
    not an integer (migrate refuses it too), a `roles` that is not a list, or
    a `.crew/` or `.work/tickets/` that cannot be listed - and status says so
    rather than answering either way. `.crew/metrics.md` and
    `.work/cache/<ID>.md` are not markers: crew 1.x writes both itself."""
    if "schema" not in legacy:
        return True, ""  # pre-0.20: migrate upgrades it in the same run
    schema = legacy["schema"]
    if isinstance(schema, bool) or not isinstance(schema, int):
        return None, "`schema` is not an integer"
    if schema < crew_state.SCHEMA_CURRENT:
        return True, ""
    roles = legacy.get("roles", [])
    if not isinstance(roles, list):
        return None, "`roles` is not a list"
    if any(r not in crew_migrate.ROSTER for r in roles):
        return True, ""
    try:
        crew_dir = set(os.listdir(os.path.join(root, ".crew")))
    except OSError as exc:
        return None, f".crew/ could not be listed: {exc.strerror or exc}"
    if crew_dir.intersection(crew_migrate.JOURNAL_FILES):
        return True, ""
    folder = os.path.join(root, ".work", "tickets")
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return False, ""
    except OSError as exc:
        return None, f".work/tickets/ could not be listed: {exc.strerror or exc}"
    return any(n.endswith(".md") and crew_common.TICKET_ID.match(n[:-3])
               and not os.path.isdir(os.path.join(folder, n)) for n in names), ""


def _ticket_lines(root):
    folder = os.path.join(root, ".work", "tickets")
    try:
        names = os.listdir(folder)
    except OSError:
        return ["tickets  none (.work/tickets/ absent)"]
    # Complete/ is the archive (L-0509), never a ticket: its folders are
    # counted apart, and a listing that fails is said, not read as none.
    dirs = sorted(n for n in names if n != crew_common.ARCHIVE_DIR
                  and os.path.isdir(os.path.join(folder, n)))
    files = [n for n in names if n.endswith(".md")]
    archive = os.path.join(folder, crew_common.ARCHIVE_DIR)
    try:
        archived = f"{sum(1 for n in os.listdir(archive) if os.path.isdir(os.path.join(archive, n)))} " \
                   f"archived in {crew_common.ARCHIVE_DIR}/"
    except (FileNotFoundError, NotADirectoryError):
        archived = f"0 archived in {crew_common.ARCHIVE_DIR}/"
    except OSError as exc:
        archived = f"archived: could not tell ({exc.strerror or exc})"
    open_ids, owner_ids = [], []
    for line in (read_text(os.path.join(root, ".work", "INDEX.md")) or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) > 1 and cells[1].lower() in ("open", "in-progress", "in progress", "review"):
            open_ids.append(cells[0])
        elif len(cells) > 1 and cells[1].lower() == "needs-owner":
            # T-0037: open, but waiting on the owner -- its own line. The
            # closed words (cancelled, superseded) appear on neither.
            owner_ids.append(cells[0])
    lines = [f"tickets  {len(dirs)} ticket dir(s), {archived}, {len(files)} legacy file(s)"]
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
    # L-0712: every ledger is read for the same-family share, not only the
    # three newest shown, so the share is repo-wide.
    tally = {"same": 0, "cross": 0, "unknown": 0, "unreadable": 0}
    for index, name in enumerate(names):
        path = os.path.join(folder, name)
        # The ledger's own summary, so status counts rounds exactly as the
        # budget does: refunded tool-failure rounds are not "used" (T-0087).
        summary = review_ledger.summary(*review_ledger.load(path), name[:-5], path)
        if summary["state"] == review_ledger.UNKNOWN:
            tally["unreadable"] += 1
            if index < 3:
                lines.append(f"review   {name[:-5]}: UNKNOWN (ledger unreadable)")
            continue
        rounds = summary.get("rounds")
        if not isinstance(rounds, list):
            tally["unreadable"] += 1  # rounds the share cannot read: could not tell
            rounds = []
        marks = [same_family_round(row) for row in rounds
                 if isinstance(row, dict) and row.get("status") == "completed"]
        tally["same"] += marks.count(True)
        tally["cross"] += marks.count(False)
        tally["unknown"] += marks.count(None)
        if index >= 3:
            continue
        used = f"{summary['rounds_spent']}/{summary['budget']} rounds used"
        line = f"review   {name[:-5]}: {summary['state']}, {used}"
        if summary["rounds_refunded"]:
            line += f", {summary['rounds_refunded']} refunded"
        if True in marks:
            line += ", same-family round"
        lines.append(line)
    if len(names) > 3:
        lines.append(f"review   (+{len(names) - 3} older ledgers)")
    lines.append(_same_family_line(tally))
    return lines


def same_family_round(row):
    """L-0712: True when a completed ledger row was reviewed by the author's
    own family, False when by another, None when the row cannot say.

    The row's own `same_family` label wins when it is a bool. Otherwise the
    ledger's author is `review_ledger.AUTHOR_FAMILY` (crew's developer runs
    in-session), so a `claude` provider or model family is same-family. A row
    with no provider is could-not-tell, never cross-family: counting it as
    independent would understate the share this line exists to show.
    """
    label = row.get("same_family")
    if isinstance(label, bool):
        return label
    provider, fam = row.get("provider"), row.get("model_family")
    if not isinstance(provider, str) or not provider:
        return None
    author = review_ledger.AUTHOR_FAMILY
    if provider == author or (isinstance(fam, str) and fam.strip().lower() == author):
        return True
    return False


def _same_family_line(tally):
    known = tally["same"] + tally["cross"]
    line = "review   same-family: "
    if known:
        line += (f"{tally['same']} of {known} completed rounds "
                 f"({round(100 * tally['same'] / known)}%)")
    else:
        line += "no completed rounds"
    unknown = [f"{tally['unknown']} round(s)" if tally["unknown"] else "",
               f"{tally['unreadable']} ledger(s) unreadable" if tally["unreadable"] else ""]
    unknown = [u for u in unknown if u]
    if unknown:
        line += f"; could not tell: {', '.join(unknown)}"
    return line


def _inflight_lines(root):
    """T-0049: one line per in-flight marker (at most INFLIGHT_SHOWN, then
    `+N more`), with the owner's clear command for stale and unknown. An import
    error or an unreadable directory is `unknown`, never `none`."""
    try:
        found = importlib.import_module("crew_inflight").survey(root)
    except Exception as exc:  # pylint: disable=broad-except
        return [" ".join(f"in-flight: unknown - crew_inflight could not tell: {exc!r}".split())]
    if found["state"] != "ok":
        return [f"in-flight: unknown - {found['why']}"]
    entries = found["entries"]
    if not entries:
        return ["in-flight: none"]
    lines = []
    for entry in entries[:INFLIGHT_SHOWN]:
        line = (f"in-flight: {entry['ticket']} {entry['state']} runner={entry['runner'] or '?'} "
                f"since={entry['since'] or '?'}")
        if entry["clear"]:
            line += f" clear: {entry['clear']}"
        lines.append(line)
    if len(entries) > INFLIGHT_SHOWN:
        lines.append(f"in-flight: +{len(entries) - INFLIGHT_SHOWN} more")
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


def _agents_line(root):
    """Agents `.crew/verify.json` names that are not installed here (T-0065).
    Reads no installation state when no agent is named."""
    result = verify_agents.check(root)
    if result["status"] == "ok":
        return f"agents   ok ({result['named']} named)" if result["named"] else "agents   none named"
    if result["status"] == "unknown":
        return f"agents   unknown - {result['unknown'][0]['reason']}"
    missing = list(result["missing"].items())
    line = "agents   MISSING " + ", ".join(name for name, _ in missing[:3])
    if len(missing) > 3:
        line += f" (+{len(missing) - 3} more) - verify_agents.py --check lists their rules"
    elif len(missing) == 1:
        line += f" (verify.json rule: {', '.join(missing[0][1]) or 'no paths'})"
    else:
        line += " - verify_agents.py --check lists their rules"
    if result["unknown"]:
        line += f"; {len(result['unknown'])} unknown"
    return line


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


def _gitignore_line(root):
    # T-0039. Imported here, not at the top: a missing or broken module must
    # still print the line - an omitted line reads as "nothing to say".
    try:
        import crew_gitignore  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except
        return "gitignore unknown (crew_gitignore.py not importable)"
    try:
        return "gitignore " + crew_gitignore.summary(root)
    except Exception as exc:  # pylint: disable=broad-except
        return f"gitignore unknown ({type(exc).__name__}: {exc})"[:120]
def _graph_ignore_line(root):
    """T-0064: whether a graph build would read a secrets-denylisted path.
    graphify's post-commit hook bypasses crew, so this line is the warning.
    `coverage` runs git with the same fsmonitor and optional-lock settings as
    `_git`, and its matching happens in a scratch repository outside `root`."""
    cover = crew_graph_ignore.coverage(root)
    if cover["status"] == crew_graph_ignore.COVERED:
        return "graph-ignore  ok"
    if cover["status"] == crew_graph_ignore.UNCOVERED:
        paths = cover["uncovered"]
        shown = crew_graph_ignore.listed(paths, 3)
        return (f"graph-ignore  UNCOVERED {len(paths)} denylisted path(s) graphify would read: "
                f"{shown} - {crew_graph_ignore.FIX}")
    return f"graph-ignore  unknown - {cover['reason']}"


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
    """Why an INDEX.md the approvals walk reads cannot be read as UTF-8, or
    None when every one can. The walk reads this checkout's `.work/INDEX.md`
    and, in a linked worktree, the main checkout's too (T-0063), through a
    reader that turns every failure into "no tickets", so an unknown in
    EITHER would print as "nothing needs approval"."""
    # pylint: disable=import-outside-toplevel
    import crew_autopilot
    import crew_ticket
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    here = os.path.join(top, ".work", "INDEX.md")
    main, why = crew_autopilot._main_checkout(top)  # pylint: disable=protected-access
    if why:
        return f"the main checkout's .work/INDEX.md could not be read: {why}"
    there = os.path.join(main, ".work", "INDEX.md") \
        if main and os.path.abspath(main) != os.path.abspath(top) else None
    found = 0
    for path, label in ((here, ".work/INDEX.md"), (there, f"{there}")):
        if path is None:
            continue
        try:
            with open(path, "rb") as fh:
                fh.read().decode("utf-8")
            found += 1
        except FileNotFoundError:
            continue
        except UnicodeDecodeError:
            return f"{label} is not UTF-8"
        except (OSError, ValueError) as exc:
            return f"{label} could not be read: {exc.__class__.__name__}"
    return None if found else "no .work/INDEX.md"


def _index_disagreement(root):
    """Why this checkout's INDEX and the main checkout's disagree on whether a
    ticket is open, or None. The walk takes this checkout's row and skips the
    main checkout's for that ticket, so a ticket closed here but open there
    (or the reverse) would be left out silently (`_index_row` names the same
    disagreement for `next`)."""
    # pylint: disable=import-outside-toplevel,protected-access
    import crew_autopilot
    import crew_ticket
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    main, why = crew_autopilot._main_checkout(top)
    if why or not main or os.path.abspath(main) == os.path.abspath(top):
        return None
    def opened(rows):
        out = {}
        for ticket, line in rows:
            out.setdefault(ticket, crew_autopilot._is_open(ticket, line))
        return out
    here = opened(crew_autopilot._index_rows(top))
    there = opened(crew_autopilot._index_rows(top, os.path.join(main, ".work", "INDEX.md")))
    split = sorted(t for t, is_open in here.items() if t in there and is_open != there[t])
    if not split:
        return None
    return (f"this checkout's .work/INDEX.md and the main checkout's disagree on whether "
            f"{', '.join(split)} {'is' if len(split) == 1 else 'are'} open - make them agree")


def _index_note(root):
    """A linked worktree whose main checkout has no `.work/INDEX.md`: said, so
    `nothing needs approval` is read as "nothing in THIS checkout's INDEX",
    never as a verdict on rows the main checkout does not have. None when
    there is nothing to say (or `_index_unreadable` already said it)."""
    # pylint: disable=import-outside-toplevel
    import crew_autopilot
    import crew_ticket
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    main, why = crew_autopilot._main_checkout(top)  # pylint: disable=protected-access
    if why or not main or os.path.abspath(main) == os.path.abspath(top):
        return None
    there = os.path.join(main, ".work", "INDEX.md")
    if os.path.lexists(there):
        return None
    return (f"note: the main checkout ({main}) has no .work/INDEX.md, so only this "
            "checkout's rows were read")


def approvals_lines(root):
    unknown = _index_unreadable(root)
    if unknown:
        return [f"could not tell ({unknown})"]
    split = _index_disagreement(root)
    if split:
        return [f"could not tell ({split})"]
    note = _index_note(root)
    pending, invalid = pending_approvals(root)
    # The paste line alone: `/crew:approve T-1  (why)` would read as a group of
    # three ids. The reason goes on its own line under it.
    lines = [row for ticket, why in pending
             for row in (f"/crew:approve {ticket}", "  why: " + " ".join(str(why).split()))]
    if invalid:
        one = len(invalid) == 1
        lines.append(f"{len(invalid)} {'ticket' if one else 'tickets'} with a spec and plan "
                     f"that do not validate {'is' if one else 'are'} not listed: "
                     + ", ".join(invalid))
    return (lines or ["nothing needs approval"]) + ([note] if note else [])


OWNER_LINE_MAX = 160


def _owner():
    """`(owner_items, None)`, or `(None, why)` when the module cannot be imported."""
    try:
        return importlib.import_module("crew_autopilot_owner").owner_items, None
    except Exception as exc:  # pylint: disable=broad-except
        return None, f"crew_autopilot_owner could not be imported: {type(exc).__name__}"


def _owner_read(root):
    """owner_items' answer, or an `unknown` one naming why it could not run."""
    owner_items, why = _owner()
    if owner_items is None:
        return {"state": "unknown", "why": why, "items": [], "unread": [], "held": [], "blocked": [],
                "unknown": []}
    try:
        return owner_items(root)
    except Exception as exc:  # pylint: disable=broad-except
        return {"state": "unknown", "why": f"owner_items raised {type(exc).__name__}",
                "items": [], "unread": [], "held": [], "blocked": [], "unknown": []}


def waiting_line(got):
    """`waiting  N on you (/crew:status --owner)[, H held][, B blocked][, C in review
    not read][, U could not tell]` (each count only when non-zero); `nothing on you`
    when N is 0 and nothing is unread or unknown."""
    if got["state"] != "ok":
        return f"waiting  unknown ({got['why']})"
    counts = [(len(got.get("held", [])), "held"), (len(got.get("blocked", [])), "blocked"),
              (len(got["unread"]), "in review not read"), (len(got["unknown"]), "could not tell")]
    extra = "".join(f", {n} {words}" for n, words in counts if n)
    if not got["items"] and not got["unread"] and not got["unknown"]:
        return f"waiting  nothing on you{extra}"
    return f"waiting  {len(got['items'])} on you (/crew:status --owner){extra}"


def _one(*fields, clip=True):
    """The fields joined by two spaces, each folded to one line; clipped to
    OWNER_LINE_MAX unless `clip` is False (a command to paste is never cut)."""
    text = "  ".join(" ".join(str(field).split()) for field in fields)
    return text if not clip or len(text) <= OWNER_LINE_MAX else text[:OWNER_LINE_MAX - 3] + "..."


def owner_lines(root):
    """`--owner`: the count line, one line per item, the unread, the could-not-tell;
    clipped to MAX_LINES, the last line `... N more`."""
    got = _owner_read(os.path.abspath(root))
    lines = [waiting_line(got)]
    lines += [_one(ticket, phase, action, clip=action.startswith("answer: "))
              for ticket, phase, action in got["items"]]
    lines += [_one(ticket, "review-unread", f"/crew:autopilot status {ticket}", clip=False)
              for ticket in got["unread"]]
    lines += [_one(ticket, "unknown", f"could not tell ({why})") for ticket, why in got["unknown"]]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + [f"... {len(lines) - MAX_LINES + 1} more"]
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
    inert = _inert_line(root)
    if inert:
        lines.append(inert)
    lines += _ticket_lines(root)
    lines.append(waiting_line(_owner_read(root)))  # L-0551
    lines += _review_lines(root)
    lines += _inflight_lines(root)
    lines.append(_verify_line(root))
    # T-0040: native Windows only. Read from config and the machine-local
    # probe cache; runs no wsl.exe, no pwsh and no git.
    shell = crew_shell.status_line(root)
    if shell:
        lines.append(shell)
    # After the shell line, which test_status_shell_line_on_windows pins
    # directly below verify.
    lines.append(_agents_line(root))
    lines.append(_codemap_line(root, cfg))
    lines.append(_gitignore_line(root))
    lines.append(_graph_ignore_line(root))
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
    parser.add_argument("--owner", action="store_true",
                        help="only what waits on the owner, with the command to type")
    args = parser.parse_args(argv)
    if args.owner and (args.memory or args.approvals):
        sys.stderr.write("crew_status.py: --owner stands alone (not with --memory or --approvals)\n")
        return 2
    if args.owner:
        print("\n".join(owner_lines(args.root)))
        return 0
    if args.approvals:
        print("\n".join(approvals_lines(os.path.abspath(args.root))))
        return 0
    print("\n".join(collect(args.root, memory=args.memory)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
