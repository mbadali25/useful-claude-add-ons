"""`/crew:autopilot wave`: an owner-designed set of approved tickets, run as
parallel lanes, one isolated worktree each (T-0029).

    python3 crew_wave.py set --root . --slug <s> --tickets <id>... [--deps <id>=<id>,<id>|none]
    python3 crew_wave.py plan --root . [--set <slug> | --tickets <id>...] [--json]
    python3 crew_wave.py start --root . --set <slug> [--json]
    python3 crew_wave.py lane-init --root . --main <main checkout> --set <slug> --ticket <id>
    python3 crew_wave.py lane-prompt --root . --set <slug> --ticket <id> [--resume-round N]
    python3 crew_wave.py lane-done --main <main checkout> --set <slug> --ticket <id>
                                   --state clean|findings|question|failed --reason <text>
    python3 crew_wave.py collect --root . --set <slug> [--json]
    python3 crew_wave.py cleanup --root . --set <slug> [--json]

## The shape

Design is the main session's: `/crew:brainstorm`, `/crew:spec`, `/crew:plan`
per ticket, then `set` records `.work/autopilot/<slug>.json`. Approval is the
owner's own group approval (T-0024). `plan` is read-only: per ticket
`eligible` or `refused: <reason>`, the lanes of this wave, the later waves and
the landing order. `start` writes one lane file per wave-1 lane under
`.work/autopilot/<slug>/lanes/<id>.json` and prints one launch per lane: an
`Agent`, `isolation: worktree`, prompt from `lane-prompt`. It places no
worktree and launches nothing. Each lane's first command is `lane-init`, in
its isolated worktree; `lane-done` writes its one terminal state; `collect`
reports the whole wave to the owner in one batch. `cleanup` removes a lane's
worktree and branch only once its branch is on origin's default branch and
the worktree is clean with nothing untracked -- `git worktree remove` without
`--force`, `git branch -d`, never `-D` -- and keeps and names everything else.

## Why `isolation: worktree`, and why the checks in lane-init

The Step 1 spike (`.work/tickets/T-0029/spike.md`) measured the scope guard's
payload: an `Agent` with `isolation: worktree` carries `agent_type` and a
`cwd` that is its own worktree; one without isolation carries the MAIN
checkout's `cwd`, so its writes into a lane worktree were judged against the
wrong ticket and allowed. So a lane is only ever an isolated `Agent`
(owner, 2026-09-26), and `lane-init` refuses to run anywhere else: in the
main checkout, outside `<main>/.claude/worktrees/`, or in a worktree another
lane file names. `.crew/config.json` is untracked, so a fresh worktree has
none and the guard reads `off` there: `lane-init` copies it in and refuses
unless the guard would enforce `block` in that worktree.

## Never, at any setting

A lane never accepts or rejects a review, never approves a plan, and never
merges; the rendered prompt carries none of those commands. The scope
guard's subagent never-list (T-0029 Step 7) is review harness and lands
separately (T-0087): until it does, only the prompt stops a lane's accept,
reject or admin merge (`crew_ticket.py approve` is refused already). The wave refuses to run
at all unless `scope.mode` is `block` for every lane ticket
(`scope-not-enforcing`). Anything that cannot be told -- a set file, a lane
file, an INDEX row, a dependency, an approval -- is a refusal or `unknown`,
never the permissive answer.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import crew_autopilot
import crew_common
import crew_config
import crew_state
import crew_ticket
import review_ledger

# A wave set's slug (T-0012's grammar).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
WAVE_ARGS = ("wave takes nothing, `--set <slug>` ([a-z0-9][a-z0-9-]{0,63}), or one or more "
             "ticket ids, never both")
REVIEW_POLICIES = ("stop", "clean-only", "fix-and-rereview")
STATES = ("clean", "findings", "question", "failed")
LIVE = ("pending", "running")
UNKNOWN = "unknown"
SCOPE_STOP = "scope-not-enforcing"
SCOPE_FIX = "set scope.mode to block in .crew/config.json"
SCHEMA = 1
SCRIPTS = os.path.dirname(os.path.abspath(__file__))


class WaveError(RuntimeError):
    """A wave operation that could not be carried out."""


def _top(root):
    return crew_ticket.toplevel(root) or os.path.abspath(root)


def _write_json(path, data):
    """Temp file then os.replace; the text is built before anything opens."""
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _read_json(path):
    """(data, 'ok'|'missing'|'corrupt')."""
    text = crew_common.read_text(path)
    if text is None:
        return None, ("corrupt" if os.path.lexists(path) else "missing")
    try:
        return json.loads(text), "ok"
    except ValueError:
        return None, "corrupt"


# --- settings and the scope precondition --------------------------------------

def settings(root):
    """`{"maxLanes", "maxDispatches", "reviewPolicy", "warnings"}` from
    `crew_config.resolve_config`. `maxLanes` is at most the resolved
    `pm.maxDispatches`; `reviewPolicy` anything but REVIEW_POLICIES is `stop`."""
    cfg = crew_config.resolve_config(_top(root))
    block = cfg.get("autopilot") if isinstance(cfg.get("autopilot"), dict) else {}
    pm = cfg.get("pm") if isinstance(cfg.get("pm"), dict) else {}
    warnings = []
    fallback = crew_state.PM_DEFAULTS["maxDispatches"]
    dispatches = crew_state.int_or(pm.get("maxDispatches", fallback), fallback)
    if dispatches < 1:
        warnings.append(f"pm.maxDispatches is {dispatches!r}, not positive; using {fallback}")
        dispatches = fallback
    lanes = block.get("maxLanes")
    if lanes is None:
        lanes = dispatches
    elif isinstance(lanes, bool) or not isinstance(lanes, int) or lanes < 1:
        warnings.append(f"autopilot.maxLanes is {lanes!r}, not a positive integer; using "
                        f"pm.maxDispatches ({dispatches})")
        lanes = dispatches
    elif lanes > dispatches:
        warnings.append(f"autopilot.maxLanes {lanes} capped to pm.maxDispatches ({dispatches}): "
                        "it can only lower it")
        lanes = dispatches
    policy = block.get("reviewPolicy", "stop")
    if not isinstance(policy, str) or policy not in REVIEW_POLICIES:
        warnings.append(f"autopilot.reviewPolicy is {policy!r}, not one of "
                        f"{'|'.join(REVIEW_POLICIES)}; it reads as stop")
        policy = "stop"
    return {"maxLanes": lanes, "maxDispatches": dispatches, "reviewPolicy": policy,
            "warnings": warnings}


def scope_enforcing(root, tickets):
    """(ok, reason). ok only when the repo config parses and the scope
    guard's effective mode is `block` for every ticket: a lane's writes are
    judged by it and nothing else. Could not tell is not ok. The config is
    read through crew_common.repo_config_file, as the guard reads it: a
    linked worktree with no config of its own reads the main checkout's."""
    top = _top(root)
    stop = f"{SCOPE_STOP}: "
    fix = f"; the wave runs only under the scope guard -- {SCOPE_FIX}"
    data, state = _read_json(crew_common.repo_config_file(top))
    if state != "ok" or not isinstance(data, dict):
        return False, f"{stop}.crew/config.json is {state if state != 'ok' else 'not an object'}{fix}"
    scope = data.get("scope")
    raw = scope.get("mode") if isinstance(scope, dict) else None
    if raw not in ("block", "auto"):
        # The guard fails closed on a value it does not know; the wave does not
        # guess what the owner meant by one.
        return False, f"{stop}scope.mode is {raw!r}{fix}"
    for ticket in tickets or [None]:
        try:
            mode, why = crew_ticket.effective_mode(top, ticket)
        except Exception as exc:  # pylint: disable=broad-except
            return False, f"{stop}scope.mode could not be told ({type(exc).__name__}){fix}"
        if mode != "block":
            return False, f"{stop}scope.mode is {mode} for {ticket or 'this repo'} ({why}){fix}"
    return True, ""


# --- the set file ------------------------------------------------------------------

def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise WaveError(f"set slug {slug!r} is not [a-z0-9][a-z0-9-]{{0,63}}")
    return slug


def set_path(top, slug):
    return os.path.join(top, ".work", "autopilot", check_slug(slug) + ".json")


def write_set(root, slug, tickets, deps=None):
    """Write `.work/autopilot/<slug>.json`. A ticket's `deps` key is written
    only when given: absent means "read INDEX.md", `[]` means none."""
    check_slug(slug)
    deps = deps or {}
    rows = []
    for ticket in tickets:
        crew_ticket.check_ticket(ticket)
        row = {"id": ticket}
        if ticket in deps:
            row["deps"] = [crew_ticket.check_ticket(d) for d in deps[ticket]]
        rows.append(row)
    if not rows:
        raise WaveError("a set names at least one ticket")
    _write_json(set_path(_top(root), slug), {"schema": SCHEMA, "set": slug, "tickets": rows})


def _valid_set(data, slug):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("set") != slug:
        return False
    rows = data.get("tickets")
    if not isinstance(rows, list) or not rows:
        return False
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            return False
        try:
            crew_ticket.check_ticket(row["id"])
            deps = row.get("deps", [])
            if not isinstance(deps, list):
                return False
            for dep in deps:
                crew_ticket.check_ticket(dep)
        except crew_ticket.TicketError:
            return False
    return True


def read_set(root, slug):
    """(data, 'ok'|'missing'|'corrupt'). A set file that does not parse, or
    whose shape is wrong, is `corrupt` -- never an empty set."""
    data, state = _read_json(set_path(_top(root), slug))
    if state != "ok":
        return None, state
    return (data, "ok") if _valid_set(data, slug) else (None, "corrupt")


# --- plan: eligibility, overlap, landing order (read-only) -----------------------------

_DEPENDS_RE = re.compile(r"\bdepends on\b([^);]*)", re.IGNORECASE)
_ID_RE = re.compile(r"[A-Z][A-Z0-9]*-[0-9]+")
_DEP_FILLER_RE = re.compile(r"^(?:[\s,]|\band\b)*$", re.IGNORECASE)
CREW_GLOB = "plugin/crew/**"
PLUGIN_JSON = "plugin/crew/.claude-plugin/plugin.json"


def _index_line(top, ticket):
    """(line, state): the first INDEX.md line whose first id is `ticket`.
    state is ok, missing (no file), unreadable or norow."""
    path = os.path.join(top, ".work", "INDEX.md")
    text = crew_common.read_text(path)
    if text is None:
        return None, ("unreadable" if os.path.lexists(path) else "missing")
    for line in text.splitlines():
        found = crew_state._TICKET_RE.search(line)  # pylint: disable=protected-access
        if found and found.group(1) == ticket:
            return line, "ok"
    return None, "norow"


def _table_cell(line, ticket):
    """The status cell after `ticket`'s own cell, lower-cased, or None when
    `line` is not a table row naming it."""
    if line.count("|") < 2:
        return None
    cells = [c.strip() for c in line.split("|")]
    for index, cell in enumerate(cells):
        if cell == ticket and index + 1 < len(cells):
            return cells[index + 1].lower()
    return None


# The INDEX statuses a lane may run from: crew_tracker.STATUS_ORDER's open rows past
# `direction`, plus `approved`. `needs-owner` waits on the owner; anything else is unknown.
OPEN_STATUSES = frozenset({"ready", "spec", "planned", "approved", "in-progress", "review"})


def _status_refusal(top, ticket):
    line, state = _index_line(top, ticket)
    if state != "ok":
        return line, (f"no .work/INDEX.md row for {ticket} ({state}): its status cannot be told")
    status = _table_cell(line, ticket)
    if status is None:
        return line, f"{ticket}'s INDEX.md line is not a table row: its status cannot be told"
    if status in crew_state._TABLE_DONE_WORDS:  # pylint: disable=protected-access
        return line, f"{ticket} is closed in INDEX.md ({status})"
    if status == "direction":
        return line, f"{ticket} is INDEX status direction: its direction is not approved"
    if status not in OPEN_STATUSES:  # an unrecognised word is could-not-tell, never "open"
        return line, (f"{ticket}'s INDEX status {status!r} is not one a lane runs "
                      f"({'|'.join(sorted(OPEN_STATUSES))}): its status cannot be told")
    return line, None


def _deps(line, given):
    """The dependency list: the set file's when it has one, else the INDEX
    row's `(depends on T-a, T-b)`. None -- unknown -- when neither parses."""
    if given is not None:
        return list(given)
    found = _DEPENDS_RE.search(line or "")
    if not found:
        return None
    ids = _ID_RE.findall(found.group(1))
    if not ids or not _DEP_FILLER_RE.match(_ID_RE.sub("", found.group(1))):
        return None
    return ids


def _dep_refusal(top, deps):
    if deps is None:
        return ("dependencies unknown: no set-file deps and no parseable `(depends on ...)` "
                "in its INDEX.md row")
    for dep in deps:
        line, state = _index_line(top, dep)
        if state != "ok":
            return f"dependency {dep} has no INDEX.md row ({state})"
        if crew_state._table_status(line, dep) is not True:  # pylint: disable=protected-access
            return f"dependency {dep} is not closed"
    return None


def _literal_prefix(entry):
    out = []
    for segment in [s for s in entry.split("/") if s not in ("", ".")]:
        if any(c in segment for c in ("*", "?", "[")):
            break
        out.append(os.path.normcase(segment))
    return out


def _entries_overlap(one, two):
    """Whether two Touch entries could both name one path. Segment-aware
    (`crew_ticket.path_matches`); when either holds a wildcard, prefix-related
    literal parts count as overlap. Anything undecidable is overlap."""
    try:
        if crew_ticket.path_matches(one, two) or crew_ticket.path_matches(two, one):
            return True
        if crew_ticket._is_glob(one) or crew_ticket._is_glob(two):  # pylint: disable=protected-access
            left, right = _literal_prefix(one), _literal_prefix(two)
            short = min(len(left), len(right))
            return left[:short] == right[:short]
        return False
    except Exception:  # pylint: disable=broad-except
        return True


def touch_overlaps(one, two):
    return any(_entries_overlap(a, b) for a in one for b in two)


def _main_version(top):
    """origin/main's crew version as (major, minor, patch), or None."""
    try:
        done = subprocess.run(["git", "-C", top, "show", f"origin/main:{PLUGIN_JSON}"],
                              capture_output=True, text=True, check=False, timeout=30,
                              stdin=subprocess.DEVNULL)
        version = json.loads(done.stdout).get("version") if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None
    found = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version or "")
    return tuple(int(n) for n in found.groups()) if found else None


def _entries(root, slug, tickets):
    """[(ticket, given deps or None)] from the set file or the ids given."""
    if slug:
        data, state = read_set(root, slug)
        if state != "ok":
            raise WaveError(f"set {slug} is {state}: .work/autopilot/{slug}.json")
        return [(row["id"], row.get("deps")) for row in data["tickets"]]
    for ticket in tickets or []:
        crew_ticket.check_ticket(ticket)
    return [(ticket, None) for ticket in tickets or []]


def _judge(top, ticket, given):
    """One plan row: `{"ticket", "eligible", "reason", "deps", "touch"}`."""
    row = {"ticket": ticket, "eligible": False, "reason": "", "deps": None, "touch": []}
    try:
        approval = crew_ticket.accepted(top, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return dict(row, reason=f"its approval could not be told ({type(exc).__name__})")
    if approval["status"] != "approved":
        return dict(row, reason=f"no current approval ({approval['status']}: {approval['why']})")
    line, refusal = _status_refusal(top, ticket)
    if refusal:
        return dict(row, reason=refusal)
    deps = _deps(line, given)
    refusal = _dep_refusal(top, deps)
    if refusal:
        return dict(row, deps=deps, reason=refusal)
    return dict(row, eligible=True, deps=deps, touch=list(approval["touch"]))


def plan(root, slug=None, tickets=None):
    """The wave, read-only. `{"set", "rows", "wave", "later", "land", "stop",
    "stopReason", "maxLanes", "warnings"}`; `later` is [[ticket, why]] and
    `land` [[ticket, version]] for this wave, in set order."""
    top = _top(root)
    conf = settings(top)
    entries = _entries(top, slug, tickets)
    ok, why = scope_enforcing(top, [t for t, _ in entries])
    rows = [_judge(top, ticket, given) for ticket, given in entries]
    wave, later = [], []
    for row in rows:
        if not row["eligible"]:
            continue
        clash = next((w["ticket"] for w in wave if touch_overlaps(row["touch"], w["touch"])), None)
        if clash:
            reason = f"Touch overlaps {clash}: a later wave"
        elif len(wave) >= conf["maxLanes"]:
            reason = f"over autopilot.maxLanes ({conf['maxLanes']}): a later wave"
        else:
            wave.append(row)
            continue
        row.update(eligible=False, reason=reason)
        later.append([row["ticket"], reason])
    base, land, bump = _main_version(top), [], 0
    for row in wave:
        if not touch_overlaps(row["touch"], [CREW_GLOB]):
            land.append([row["ticket"], "-"])
        elif base is None:
            land.append([row["ticket"], UNKNOWN])
        else:
            bump += 1
            land.append([row["ticket"], f"{base[0]}.{base[1]}.{base[2] + bump}"])
    return {"set": slug or "", "rows": rows, "wave": [r["ticket"] for r in wave],
            "later": later, "land": land, "stop": not ok, "stopReason": why,
            "maxLanes": conf["maxLanes"], "warnings": conf["warnings"]}


def list_sets(root):
    """A bare `wave`: the set files there are, and how to name one."""
    folder = os.path.join(_top(root), ".work", "autopilot")
    try:
        names = sorted(n[:-5] for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        names = []
    return ("sets: " + (", ".join(names) or "(none)")
            + "\nname one: /crew:autopilot wave --set <slug>, or wave <id> <id>...")


def plan_text(result):
    lines = [f"stop: {result['stopReason']}"] if result["stop"] else []
    lines += [f"{r['ticket']} eligible" if r["eligible"] else f"{r['ticket']} refused: {r['reason']}"
              for r in result["rows"]]
    lines.append(f"wave 1: {', '.join(result['wave']) or '(none)'}")
    lines += [f"later: {ticket} - {why}" for ticket, why in result["later"]]
    lines.append("land order: " + (", ".join(f"{t} {v}" for t, v in result["land"]) or "(none)"))
    lines += [f"warning: {w}" for w in result["warnings"]]
    return "\n".join(lines)


# --- lane files, start and lane-init ----------------------------------------------------------

AGENT_DIR = os.path.join(".claude", "worktrees")
LAUNCH = "Agent(subagent_type: general-purpose, isolation: worktree)"


def lanes_dir(top, slug):
    return os.path.join(top, ".work", "autopilot", check_slug(slug), "lanes")


def lane_path(top, slug, ticket):
    return os.path.join(lanes_dir(top, slug), crew_ticket.check_ticket(ticket) + ".json")


def read_lane(root, slug, ticket):
    """(lane, 'ok'|'missing'|'corrupt'). A lane file that parses but is not
    an object with a known `state` is `corrupt`: unknown, never a state."""
    data, state = _read_json(lane_path(_top(root), slug, ticket))
    if state != "ok":
        return None, state
    if not isinstance(data, dict) or data.get("state") not in LIVE + STATES:
        return None, "corrupt"
    return data, "ok"


def write_lane(root, slug, ticket, lane):
    _write_json(lane_path(_top(root), slug, ticket), lane)


def branch_for(ticket):
    return f"{crew_ticket.check_ticket(ticket)}-wave"


def _git(top, *args):
    """(returncode, stdout) of one git call; (None, '') when it could not run."""
    try:
        done = subprocess.run(["git", "-C", top] + list(args), capture_output=True, text=True,
                              check=False, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return done.returncode, done.stdout.strip()


def worktrees(top):
    """{real worktree path: branch name or ''} from `git worktree list
    --porcelain`, or None when git could not answer."""
    code, out = _git(top, "worktree", "list", "--porcelain")
    if code != 0:
        return None
    found, path = {}, None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = os.path.realpath(line[len("worktree "):])
            found[path] = ""
        elif line.startswith("branch refs/heads/") and path:
            found[path] = line[len("branch refs/heads/"):]
    return found


def holder(top, branch):
    """The worktree that has `branch` checked out, '' for none, None for
    could not tell."""
    found = worktrees(top)
    if found is None:
        return None
    return next((path for path, name in found.items() if name == branch), "")


def _ledger(top, ticket):
    """review_ledger.status, refusing a ledger it cannot read (`UNKNOWN`):
    could-not-tell is never read as "no round reserved" or "no receipt"."""
    got = review_ledger.status(top, ticket)
    if got.get("state") == review_ledger.UNKNOWN:
        raise WaveError(f"{ticket}'s review ledger is unreadable ({got.get('path')})")
    return got


def _reserved_round(top, ticket):
    """The latest round's number while it is reserved and unrecorded, else
    None. What a relaunch hands back to the lane instead of reserving."""
    rounds = _ledger(top, ticket).get("rounds") or []
    last = rounds[-1] if rounds else {}
    return last.get("round") if last.get("status") == "reserved" else None


def _receipt_mark(top, ticket):
    """[kind, round, accepted_at] of the ledger's receipt, or None: what
    `collect` compares to spot an owner-accepted receipt written mid-lane."""
    receipt = _ledger(top, ticket).get("receipt")
    if not isinstance(receipt, dict):
        return None
    return [receipt.get("kind"), receipt.get("round"), receipt.get("accepted_at")]


def _launch(top, slug, ticket, resume):
    command = (f"python3 {shlex.quote(os.path.join(SCRIPTS, 'crew_wave.py'))} lane-prompt "
               f"--root {shlex.quote(top)} "
               f"--set {slug} --ticket {ticket}")
    if resume is not None:
        command += f" --resume-round {resume}"
    return f"launch {ticket}: {LAUNCH} prompt: the output of `{command}`"


def start_path(top, slug):
    return os.path.join(top, ".work", "autopilot", check_slug(slug), "start.json")


def start(root, slug):
    """`{"stop", "stopReason", "plan", "lines"}`. Writes a `pending` lane file
    for each new wave-1 lane and `start.json` (base commit, lanes, receipt
    kinds at start); prints one isolated launch per lane to (re)launch. Never
    reserves a review round, places a worktree or launches an agent."""
    top = _top(root)
    result = plan(top, slug=slug)
    if result["stop"]:
        return {"stop": True, "stopReason": result["stopReason"], "plan": result,
                "lines": [f"stop: {result['stopReason']}"]}
    code, base = _git(top, "rev-parse", "HEAD")
    if code != 0 or not base:
        raise WaveError("could not read the main checkout's HEAD for the lanes' base commit")
    record, rstate = _read_json(start_path(top, slug))
    if rstate == "missing":
        record = {}
    elif rstate != "ok" or not isinstance(record, dict) or not isinstance(record.get("lanes", []), list):
        # Never rebuilt from nothing: its lanes would drop out of collect's report.
        raise WaveError(f"{start_path(top, slug)} is unreadable; it was left as it is -- the owner "
                        "repairs or removes it")
    receipts = dict(record.get("receipts") or {})
    lanes = list(record.get("lanes") or [])
    versions = dict(result["land"])
    lines = []
    for ticket in result["wave"]:
        lane, state = read_lane(top, slug, ticket)
        if state == "corrupt":
            lines.append(f"{ticket} unknown: its lane file is unreadable; not relaunched")
            continue
        if state == "ok" and lane["state"] in STATES:
            lines.append(f"{ticket} skipped: {lane['state']}")
            continue
        held = holder(top, branch_for(ticket))
        if held is None:
            lines.append(f"{ticket} unknown: git could not list worktrees; not relaunched")
            continue
        if held:
            lines.append(f"{ticket} blocked: {branch_for(ticket)} is checked out in {held}; "
                         "the owner removes that worktree after checking it is clean, or "
                         "resumes the lane there by hand")
            continue
        if state == "missing" and ticket in lanes:
            # Started before, file gone: its outcome cannot be told, so never restart it.
            lines.append(f"{ticket} unknown: start.json lists it but its lane file is missing; "
                         "not relaunched")
            continue
        if state == "missing":
            lane = {"set": slug, "ticket": ticket, "state": "pending", "base": base,
                    "version": versions.get(ticket, UNKNOWN), "worktree": None,
                    "step": "pending", "reason": ""}
            receipts.setdefault(ticket, _receipt_mark(top, ticket))  # an unreadable ledger stops first
            write_lane(top, slug, ticket, lane)
        if ticket not in lanes:
            lanes.append(ticket)
        lines.append(_launch(top, slug, ticket, _reserved_round(top, ticket)))
    _write_json(start_path(top, slug), {"base": record.get("base") or base, "lanes": lanes,
                                        "later": result["later"], "receipts": receipts})
    lines += [f"later: {ticket} - {why}" for ticket, why in result["later"]]
    return {"stop": False, "stopReason": "", "plan": result, "lines": lines}


def _same_bytes(one, two):
    try:
        with open(one, "rb") as left, open(two, "rb") as right:
            return left.read() == right.read()
    except OSError:
        return False


def _copy_in(source, target):
    """Copy one file and prove the bytes arrived; a problem, or None."""
    if not os.path.isfile(source):
        return f"{source} does not exist"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    return None if _same_bytes(source, target) else f"{target} does not match {source}"


def _init_refusal(top, main_top, slug, ticket):
    """Why `lane-init` must not run here (checks that write nothing), or None."""
    if crew_ticket.common_dir(top) != crew_ticket.common_dir(main_top):
        return f"{top} is not a worktree of {main_top}"
    if os.path.normcase(top) == os.path.normcase(main_top):
        return "this is the main checkout; a lane runs only in its own isolated worktree"
    agents = os.path.join(main_top, AGENT_DIR)
    if not os.path.normcase(top).startswith(os.path.normcase(agents) + os.sep):
        return (f"{top} is not under {agents.replace(os.sep, '/')} (.claude/worktrees): a lane "
                "is launched only as an Agent with isolation: worktree")
    lane, state = read_lane(main_top, slug, ticket)
    if state != "ok":
        return f"{ticket}'s lane file is {state}: `crew_wave.py start --set {slug}` names the lanes"
    if lane["state"] not in LIVE:
        return f"{ticket}'s lane is already {lane['state']}"
    try:
        others = [n[:-5] for n in os.listdir(lanes_dir(main_top, slug)) if n.endswith(".json")]
    except OSError:
        return "the set's lane files could not be listed"
    for other in others:
        if other == ticket:
            continue
        found, ostate = read_lane(main_top, slug, other)
        if ostate != "ok":
            return f"{other}'s lane file is {ostate}: whether it names this worktree cannot be told"
        if found.get("worktree") and os.path.normcase(found["worktree"]) == os.path.normcase(top):
            return f"this worktree is {other}'s lane; lanes never share a worktree"
    held = holder(main_top, branch_for(ticket))
    if held is None:
        return "git could not list worktrees, so who holds the branch cannot be told"
    if held and os.path.normcase(held) != os.path.normcase(top):
        return f"{branch_for(ticket)} is checked out in {held}; a lane's branch is in one worktree"
    return None


def lane_init(root, main, slug, ticket):
    """(ok, reason). The lane's first command, in its isolated worktree: the
    ticket branch, the ticket folder and `.crew/config.json` copied in, the
    approval and the scope guard's mode checked there, then activation."""
    crew_ticket.check_ticket(ticket)
    top, main_top = crew_ticket.toplevel(root), crew_ticket.toplevel(main)
    if not top or not main_top:
        return False, "not a git worktree"
    refusal = _init_refusal(top, main_top, slug, ticket)
    if refusal:
        return False, refusal
    lane, _ = read_lane(main_top, slug, ticket)
    branch = branch_for(ticket)
    code, _ = _git(top, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    args = ["checkout", "-q", branch] if code == 0 else ["checkout", "-q", "-b", branch, lane["base"]]
    if _git(top, *args)[0] != 0:
        return False, f"git {' '.join(args)} failed in {top}"
    rel_folder = os.path.join(".work", "tickets", ticket)
    names, failed = [], []
    source = os.path.join(main_top, rel_folder)
    if not os.path.isdir(source):
        return False, f"copy refused: {rel_folder} could not be listed (not a directory)"
    for here, dirs, files in os.walk(source, onerror=failed.append):  # nested files too
        dirs.sort()
        names += [os.path.relpath(os.path.join(here, n), source) for n in sorted(files)
                  if os.path.isfile(os.path.join(here, n))]
    if failed:
        return False, f"copy refused: {rel_folder} could not be listed ({failed[0]})"
    config = os.path.join(".crew", "config.json")
    if not os.path.isfile(os.path.join(main_top, config)):
        return False, (f"{SCOPE_STOP}: {main_top}/.crew/config.json does not exist, so the scope "
                       f"guard would read scope.mode off in this worktree -- {SCOPE_FIX}")
    for rel in [os.path.join(rel_folder, n) for n in names] + [config]:
        if os.path.lexists(os.path.join(top, rel)) and not _same_bytes(os.path.join(main_top, rel),
                                                                         os.path.join(top, rel)):
            # A re-run lane-init must not overwrite the lane's own edits.
            return False, (f"copy refused: {rel} in this worktree differs from the main checkout's; "
                           "nothing overwritten")
        problem = _copy_in(os.path.join(main_top, rel), os.path.join(top, rel))
        if problem:
            return False, f"copy refused: {problem}"
    approval = crew_ticket.accepted(top, ticket)
    if approval["status"] != "approved":
        return False, f"{ticket} is {approval['status']} in this worktree: {approval['why']}"
    ok, why = scope_enforcing(top, [ticket])
    if not ok:
        return False, why
    crew_ticket.activate(top, ticket)
    write_lane(main_top, slug, ticket, dict(lane, state="running", worktree=top, branch=branch,
                                            step="activated"))
    return True, ""


# --- the lane prompt ---------------------------------------------------------------------------

POLICY_TEXT = {
    "stop": ("autopilot.reviewPolicy stop: the lane ends at the first recorded verdict. "
             "FINDINGS or INCOMPLETE: step 8 with --state findings. CLEAN: write the question "
             "`Run /crew:done?` (below; recommended: yes, the review is CLEAN) and go to step 8 "
             "with --state question and the reason `review CLEAN; reviewPolicy stop leaves "
             "/crew:done to the owner`."),
    "clean-only": ("autopilot.reviewPolicy clean-only: CLEAN goes on to step 7. FINDINGS or "
                   "INCOMPLETE: step 8 with --state findings."),
    "fix-and-rereview": ("autopilot.reviewPolicy fix-and-rereview: CLEAN goes on to step 7. On "
                         "FINDINGS, read rounds_left from `{ledger} --status --root . --ticket "
                         "{ticket}`: above 0, fix every BLOCK and FIX inside the ticket's Touch, "
                         "commit, rerun step 4, then step 5 for the next round; at 0, step 8 "
                         "with --state findings. INCOMPLETE: step 8 with --state findings."),
}


# Every place crew's version is declared (CLAUDE.md: a plugin with its own plugin.json
# bumps in both, and PLUGINS.md's version claim is checked against it).
VERSION_FILES = ("plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json and "
                 "plugin/PLUGINS.md's `<!-- claim: plugin-version:crew -->` line")


def lane_prompt(root, slug, ticket, resume_round=None):
    """The one prompt every lane runs, rendered with absolute script paths
    (`${CLAUDE_PLUGIN_ROOT}` is a command-file substitution, not a variable a
    lane's Bash has). It carries no accept, reject, approve or merge command."""
    top = _top(root)
    lane, state = read_lane(top, slug, ticket)
    if state != "ok":
        raise WaveError(f"{ticket}'s lane file is {state}: run `crew_wave.py start --set {slug}`")
    policy = settings(top)["reviewPolicy"]

    def script(name):
        return "python3 " + shlex.quote(os.path.join(SCRIPTS, name))

    version = lane.get("version") or UNKNOWN
    if version == "-":
        bump = ("3. version: this ticket touches no plugin/crew/ path; leave "
                f"{VERSION_FILES} alone.")
    elif version == UNKNOWN:
        bump = ("3. version: the wave could not tell this lane's version. If the ticket changed "
                "any plugin/crew/ path, write a question (the version to set; below) and go to "
                f"step 8 with --state question: never reach clean unbumped. Otherwise leave {VERSION_FILES} "
                "alone.")
    else:
        bump = (f"3. version: set crew's version to {version} in {VERSION_FILES}, "
                "all in one commit.")
    if resume_round is not None:
        resume = (f"Resume: round {resume_round} is already reserved and unrecorded, so do "
                  "not reserve another; run the reviewer for it and record it with "
                  f"`{script('review_run.py')} ... --round {resume_round}`.")
    else:
        resume = (f"Reserve each round with `{script('review_run.py')} ... --reserve-only` "
                  "before the reviewer runs, and record it with `--round N`.")
    shape = "\n".join(f"    {row}" for row in crew_autopilot.QUESTIONS_SHAPE)
    main = shlex.quote(top)
    done = (f"{script('crew_wave.py')} lane-done --main {main} --set {slug} --ticket {ticket} "
            "--state <clean|findings|question|failed> --reason \"<one line>\"")
    return "\n".join([
        f"You are lane {ticket} of wave {slug}. Your current directory is your own isolated "
        "worktree: work only here (--root .) and never write to another checkout's path. "
        "Never ask the owner anything; a question goes to a file and the lane stops.",
        f"1. lane-init: {script('crew_wave.py')} lane-init --root . --main {main} --set {slug} "
        f"--ticket {ticket}. If it prints `refused:` or exits non-zero, go to step 8 with "
        "--state failed and that reason.",
        f"2. implement: follow /crew:implement {ticket} here up to, not including, its last "
        "step's `/crew:review` (step 5 is the only review); commit on the ticket branch.",
        bump,
        f"4. refresh: {script('crew_refresh_check.py')} --root . --ticket {ticket}; run each "
        "refresh command it names (/crew:onboard --refresh, /crew:diagram refresh, graphify "
        "update .) and commit it before the review.",
        f"5. review: follow /crew:review {ticket} (crew:reviewer while Codex is out) up to its "
        "recorded verdict only - none of its after-verdict steps (fixing, another round, accepting, "
        f"asking the owner); this policy decides instead. {resume} "
        + POLICY_TEXT[policy].format(ledger=script("review_ledger.py"), ticket=ticket),
        "6. after a fix, rerun step 4 before the next round.",
        f"7. done checks: {script('completion_audit.py')} --check --ticket {ticket} --root . - "
        "exit 0: step 8 with --state clean; anything else: step 8 with --state failed and its "
        "output.",
        f"8. lane-done, exactly once, then stop: {done}",
        "Questions: research first (crew:explorer for this repo, crew:researcher outside), then "
        f"write .work/tickets/{ticket}/questions.md in this shape, recommendation first, and "
        "go to step 8 with --state question:",
        shape,
        "Never, at any setting: accepting or rejecting a review, approving a plan, merging, or "
        "opening a PR. Those are the owner's. If a step needs one, it is a question.",
    ])


def lane_done(main, slug, ticket, state, reason):
    """Write the lane's one terminal state. Refuses a state outside STATES,
    and a lane file that is missing or unreadable."""
    if state not in STATES:
        raise WaveError(f"state {state!r} is not one of {'|'.join(STATES)}")
    top = _top(main)
    lane, got = read_lane(top, slug, ticket)
    if got != "ok":
        raise WaveError(f"{ticket}'s lane file is {got}; nothing written")
    write_lane(top, slug, ticket, dict(lane, state=state, reason=reason or "", step="done"))


# --- collect: one batch for the owner ------------------------------------------------------------

OWNER_ACCEPTED = "owner-accepted"


def _open_questions(worktree, ticket):
    """(questions, problem): each open `## Q<n>` in the lane's questions.md as
    {"id", "title", "options": [(heading, cost)]}, the recommended option
    first. `problem` names a file that cannot be read."""
    path = os.path.join(worktree or "", ".work", "tickets", ticket, "questions.md")
    text = crew_common.read_text(path) if worktree else None
    if text is None:
        return [], f"{ticket}: questions.md unknown ({'unreadable' if worktree else 'no worktree'})"
    found = []
    blocks = crew_autopilot._question_blocks(text)  # pylint: disable=protected-access
    for number, title, _preamble, options, taken in blocks:
        if taken:
            continue
        rows = []
        for oid, rest, lines in options:
            cost = next((line.split("Cost:", 1)[1].strip() for line in lines
                         if crew_autopilot._COST_RE.match(line)), "")  # pylint: disable=protected-access
            rows.append((f"Option {oid}{rest}".strip(), cost))
        rows.sort(key=lambda row: crew_autopilot.RECOMMENDED not in row[0])
        found.append({"id": f"Q{number}", "title": title, "options": rows})
    return found, None


def _lane_row(top, slug, ticket, started, marks):
    """{"ticket", "state", "reason", "worktree", "version"} for one lane."""
    row = {"ticket": ticket, "state": UNKNOWN, "reason": "", "worktree": None, "version": None}
    if not started:
        return dict(row, reason="the wave was not started (no readable start.json)")
    if ticket not in started:
        return dict(row, state="later", reason="not in a started wave")
    lane, state = read_lane(top, slug, ticket)
    if state != "ok":
        return dict(row, reason=f"its lane file is {state}")
    row.update(state=lane["state"], reason=lane.get("reason") or "", worktree=lane.get("worktree"),
               version=lane.get("version"))
    try:
        now = _receipt_mark(top, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return dict(row, state=UNKNOWN, reason=f"its review ledger could not be read ({exc})")
    if now and now[0] == OWNER_ACCEPTED and now != marks.get(ticket):
        return dict(row, state="failed", reason="accepted without the owner: an owner-accepted "
                    "receipt was written while the lane ran")
    return row


def collect(root, slug):
    """The whole wave, read-only: `{"lanes", "questions", "problems",
    "approvals", "land", "later"}`. A lane that cannot be read is `unknown`,
    never `clean`."""
    top = _top(root)
    data, state = read_set(top, slug)
    if state != "ok":
        raise WaveError(f"set {slug} is {state}")
    record, rstate = _read_json(start_path(top, slug))
    ok = rstate == "ok" and isinstance(record, dict) and isinstance(record.get("lanes"), list)
    started = record["lanes"] if ok else None
    marks = (record.get("receipts") or {}) if ok else {}
    ids = [row["id"] for row in data["tickets"]]
    # A lane that was started stays in the report even if the set file was rewritten without it.
    ids += [t for t in (started or []) if isinstance(t, str) and t not in ids]
    lanes = [_lane_row(top, slug, ticket, started, marks) for ticket in ids]
    questions, problems = [], []
    for lane in lanes:
        if lane["state"] != "question":
            continue
        found, problem = _open_questions(lane["worktree"], lane["ticket"])
        questions += [dict(q, ticket=lane["ticket"]) for q in found]
        problems += [problem] if problem else []
    unapproved = []
    for ticket in ids:
        try:
            approved = crew_ticket.accepted(top, ticket)["status"] == "approved"
        except Exception:  # pylint: disable=broad-except
            approved = False
        if not approved:
            unapproved.append(ticket)
    approvals = ([f"/crew:approve {unapproved[0]}"] if len(unapproved) == 1 else
                 [f"/crew:approve {' '.join(unapproved)}", "/crew:approve --confirm"]
                 if unapproved else [])
    land = [[lane["ticket"], lane["version"] or UNKNOWN] for lane in lanes
            if lane["state"] == "clean"]
    return {"set": slug, "lanes": lanes, "questions": questions, "problems": problems,
            "approvals": approvals, "land": land, "later": (record.get("later") or []) if ok else []}


def collect_text(result):
    lines = [f"{lane['ticket']} {lane['state']}" + (f" - {lane['reason']}" if lane["reason"] else "")
             + (f" [{lane['worktree']}]" if lane["worktree"] else "") for lane in result["lanes"]]
    lines.append(f"Questions ({len(result['questions'])}):")
    for question in result["questions"]:
        lines.append(f"  {question['ticket']} {question['id']}: {question['title']}")
        lines += [f"    {heading} - Cost: {cost}" for heading, cost in question["options"]]
    lines += [f"  {problem}" for problem in result["problems"]]
    lines.append("Approvals to type:")
    lines += [f"  {line}" for line in result["approvals"]] or ["  (none)"]
    lines.append("Land order (clean): " + (", ".join(f"{t} {v}" for t, v in result["land"])
                                           or "(none)"))
    lines.append("Later waves: " + (", ".join(f"{t} ({why})" for t, why in result["later"])
                                    or "(none)"))
    return "\n".join(lines)


# --- cleanup: merged lanes' worktrees (Step 11) --------------------------------------------------

def _default_ref(top):
    """`origin/<default>`, or None when it cannot be told."""
    code, out = _git(top, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and out:
        return out
    code, _ = _git(top, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main")
    return "origin/main" if code == 0 else None


def _merged(top, commit, ref):
    """True, False, or None (could not tell) for `commit` reachable from `ref`."""
    code, _ = _git(top, "merge-base", "--is-ancestor", commit, ref)
    return {0: True, 1: False}.get(code)


# crew's own machine-local state that lane-init's activate writes (scope_base.RECORD);
# not lane work, so it does not keep a worktree.
CREW_STATE = frozenset({".crew/.scope-base"})


def _dirt(worktree, main_top):
    """'' when clean, else why not; None when git could not say. An ignored
    file byte-identical to the main checkout's copy (lane-init's ticket folder
    and config), and crew's own CREW_STATE, are not the lane's and do not count."""
    # --ignored: a lane's .work/ ticket copy, questions.md and review files are ignored
    # by the repo, yet exist only in that worktree (codex review, rush g0).
    code, out = _git(worktree, "status", "--porcelain", "--ignored", "--untracked-files=all")
    if code != 0:
        return None
    lines = [line for line in out.splitlines() if line.strip() and not (
        line.startswith("!! ") and (line[3:] in CREW_STATE or _same_bytes(
            os.path.join(worktree, line[3:]), os.path.join(main_top, line[3:]))))]
    if not lines:
        return ""
    untracked = sum(1 for line in lines if line.startswith("??"))
    ignored = sum(1 for line in lines if line.startswith("!!"))
    changed = len(lines) - untracked - ignored
    parts = ([f"dirty ({changed} changed)"] if changed else []) + (
        [f"untracked ({untracked} files)"] if untracked else []) + (
        [f"ignored files ({ignored})"] if ignored else [])
    return ", ".join(parts)


def _clean_lane(top, lane, ref, trees):
    """(removed, reason) for one lane. Removes only a worktree that is clean,
    with no untracked file, whose HEAD and branch are both on `ref`; never
    `--force`, never `branch -D`."""
    if lane.get("state") not in STATES:  # a pending or running lane has not landed
        return False, f"not landed: the lane is {lane.get('state') or 'unknown'}"
    branch = lane.get("branch") or branch_for(lane["ticket"])
    code, head = _git(top, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    if code == 0 and head == lane.get("base"):
        return False, f"not landed: {branch} has no commit past its base"
    worktree = next((p for p, name in trees.items() if name == branch), None)
    recorded = lane.get("worktree")
    if worktree and not (recorded and os.path.normcase(os.path.realpath(worktree))
                         == os.path.normcase(os.path.realpath(recorded))):
        return False, (f"not the lane's worktree: {branch} is checked out in {worktree}, the lane "
                       f"recorded {recorded or 'none'}")
    if code != 0:
        return False, ("not merged: no lane branch" if worktree is None
                       else f"could not tell: {branch} is not a branch here")
    merged = _merged(top, head, ref)
    if merged is None:
        return False, f"could not tell whether {branch} is on {ref}"
    if not merged:
        return False, f"not merged: {branch} has commits that are not on {ref}"
    if worktree:
        dirt = _dirt(worktree, top)
        if dirt is None:
            return False, f"could not tell whether {worktree} is clean"
        if dirt:
            return False, f"{dirt} in {worktree}"
        code, wt_head = _git(worktree, "rev-parse", "HEAD")
        if code != 0 or _merged(top, wt_head, ref) is not True:
            return False, f"unpushed commits: {worktree}'s HEAD is not on {ref}"
        if _git(top, "worktree", "remove", worktree)[0] != 0:
            return False, f"could not tell: git worktree remove {worktree} refused"
    if _git(top, "branch", "-d", branch)[0] != 0:
        return bool(worktree), (f"worktree removed; {branch} kept: git branch -d refused it "
                                "(not merged into this checkout's HEAD)")
    return True, f"worktree {worktree or '(none)'} and branch {branch} removed"


def cleanup(root, slug):
    """`{"lanes": [{"ticket", "removed", "reason"}]}`: every lane of the set,
    each removed only when merged into origin's default branch and clean.
    Anything that cannot be told is kept and says so."""
    top = _top(root)
    data, state = read_set(top, slug)
    if state != "ok":
        raise WaveError(f"set {slug} is {state}")
    rows = []
    fetched = _git(top, "fetch", "--quiet", "origin")[0] == 0
    ref = _default_ref(top) if fetched else None
    trees = worktrees(top)
    for ticket in [row["id"] for row in data["tickets"]]:
        lane, lstate = read_lane(top, slug, ticket)
        if lstate != "ok":
            rows.append({"ticket": ticket, "removed": False,
                         "reason": f"could not tell: its lane file is {lstate}"})
            continue
        if not fetched or ref is None or trees is None:
            why = ("git fetch origin failed" if not fetched else
                   "origin's default branch is unknown" if ref is None else
                   "git could not list worktrees")
            rows.append({"ticket": ticket, "removed": False, "reason": f"could not tell: {why}"})
            continue
        removed, reason = _clean_lane(top, dict(lane, ticket=ticket), ref, trees)
        if removed:
            write_lane(top, slug, ticket, dict(lane, worktree=None, removed=True))
        rows.append({"ticket": ticket, "removed": removed, "reason": reason})
    _git(top, "worktree", "prune")
    return {"set": slug, "lanes": rows}


def cleanup_text(result):
    return "\n".join(f"{'removed' if row['removed'] else 'kept'} {row['ticket']}: {row['reason']}"
                     for row in result["lanes"])


# --- CLI ------------------------------------------------------------------------------

def _parse_deps(values):
    deps = {}
    for value in values or []:
        ticket, sep, rest = value.partition("=")
        if not sep:
            raise WaveError(f"--deps {value!r} is not <id>=<id>,<id> or <id>=none")
        deps[crew_ticket.check_ticket(ticket.strip())] = (
            [] if rest.strip() == "none" else [d.strip() for d in rest.split(",") if d.strip()])
    return deps


def wave_args(top, got, rest):
    """`crew_autopilot.route_args` for `wave` (T-0029): nothing, `--set <slug>`,
    or ticket ids -- each INDEX-shaped or an existing ticket folder, once.
    Anything else stops (`route` has already applied `focus_guard`). Lives
    here, not in crew_autopilot.py, which is at `.pylintrc`'s max-module-lines."""
    base = dict(got, ticket="", set="", tickets=[])
    if rest[:1] == ["--set"]:
        if len(rest) != 2 or not SLUG_RE.fullmatch(rest[1]):
            return dict(base, stop=True, reason=WAVE_ARGS)
        base["set"] = rest[1]
    elif rest:
        if len(set(rest)) != len(rest) or not all(
                crew_autopilot._INDEX_ID.fullmatch(w)  # pylint: disable=protected-access
                or crew_autopilot._existing_ticket(top, w)  # pylint: disable=protected-access
                for w in rest):
            return dict(base, stop=True, reason=WAVE_ARGS)
        base["tickets"] = list(rest)
    return base


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    made = sub.add_parser("set")
    made.add_argument("--root", default=".")
    made.add_argument("--slug", required=True)
    made.add_argument("--tickets", nargs="+", required=True)
    made.add_argument("--deps", action="append", default=[])
    planned = sub.add_parser("plan")
    planned.add_argument("--root", default=".")
    planned.add_argument("--json", action="store_true")
    which = planned.add_mutually_exclusive_group()
    which.add_argument("--set", dest="slug", default=None)
    which.add_argument("--tickets", nargs="+", default=None)
    started = sub.add_parser("start")
    started.add_argument("--root", default=".")
    started.add_argument("--set", dest="slug", required=True)
    started.add_argument("--json", action="store_true")
    init = sub.add_parser("lane-init")
    done = sub.add_parser("lane-done")
    for action in (init, done):
        action.add_argument("--main", required=True)
        action.add_argument("--set", dest="slug", required=True)
        action.add_argument("--ticket", required=True)
    init.add_argument("--root", default=".")
    prompt = sub.add_parser("lane-prompt")
    prompt.add_argument("--root", default=".")
    prompt.add_argument("--set", dest="slug", required=True)
    prompt.add_argument("--ticket", required=True)
    prompt.add_argument("--resume-round", type=int, default=None)
    done.add_argument("--state", required=True)
    done.add_argument("--reason", default="")
    swept = sub.add_parser("cleanup")
    swept.add_argument("--root", default=".")
    swept.add_argument("--set", dest="slug", required=True)
    swept.add_argument("--json", action="store_true")
    gathered = sub.add_parser("collect")
    gathered.add_argument("--root", default=".")
    gathered.add_argument("--set", dest="slug", required=True)
    gathered.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    # Read-only commands: git must not even refresh the index's stat cache.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        if args.action == "set":
            write_set(args.root, args.slug, args.tickets, _parse_deps(args.deps))
            print(f"set {args.slug}: {' '.join(args.tickets)}")
            return 0
        if args.action == "plan":
            if not args.slug and not args.tickets:
                print(list_sets(args.root))
                return 0
            result = plan(args.root, args.slug, args.tickets)
            print(json.dumps(result, indent=2) if args.json else plan_text(result))
            return 1 if result["stop"] else 0
        if args.action == "start":
            result = start(args.root, args.slug)
            print(json.dumps(result, indent=2) if args.json else "\n".join(result["lines"]))
            return 1 if result["stop"] else 0
        if args.action == "lane-init":
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
            ok, reason = lane_init(args.root, args.main, args.slug, args.ticket)
            print(f"lane-init {args.ticket}: ok" if ok else f"lane-init {args.ticket}: refused: {reason}")
            return 0 if ok else 1
        if args.action == "cleanup":
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
            result = cleanup(args.root, args.slug)
            print(json.dumps(result, indent=2) if args.json else cleanup_text(result))
            return 0
        if args.action == "collect":
            result = collect(args.root, args.slug)
            print(json.dumps(result, indent=2) if args.json else collect_text(result))
            return 0
        if args.action == "lane-prompt":
            print(lane_prompt(args.root, args.slug, args.ticket, args.resume_round))
            return 0
        if args.action == "lane-done":
            lane_done(args.main, args.slug, args.ticket, args.state, args.reason)
            print(f"lane {args.ticket}: {args.state}")
            return 0
    except (WaveError, crew_ticket.TicketError, OSError) as exc:
        sys.stderr.write(f"crew-wave: {exc}\n")
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
