"""Emergency lane state: declare an incident, stand the gates down, record the debt.

An incident is a repo-scoped, time-boxed, written-down decision to stop
gating. Nothing here decides whether that is a good idea - the human does -
but everything here makes sure it is (a) visible in every later session,
(b) automatically over after a while, and (c) accompanied by a list of what
was skipped, so the debt survives the adrenaline.

## The file format IS the contract

The two gates that stand down (`verify-gate` and `promote-gate`) read this
state directly in bash and in PowerShell, without python - Git Bash ships
without python3 and a gate that cannot parse its own state must not guess.
So the format is deliberately dumb:

    .crew/incident.json         {"id":..., "expiresAtEpoch": 1234567890, ...}
    .crew/incident-skips.log    <epoch>\\t<gate>\\t<detail>   (append-only)

`expiresAtEpoch` is an integer of seconds, NOT an ISO timestamp: comparing
integers is one line in every language involved, where parsing ISO-8601 in
bash is a shell-out to python or date(1) and a different answer on macOS.
The ISO strings are also written, for humans, and never parsed by anything.

An expired incident is inert - the gates gate again the moment the clock
passes `expiresAtEpoch`, with no command run and no file touched. That is
the important safety property: forgetting to close an incident cannot leave
a repository permanently ungated.
"""

import json
import os
import time

STATE_PATH = ".crew/incident.json"
SKIP_LOG_PATH = ".crew/incident-skips.log"
ARCHIVE_DIR = ".crew/incidents"
REPORT_DIR = ".work"

DEFAULT_TTL_MINUTES = 120
# A ceiling on `extend`, so "extend it again" cannot quietly become a policy.
# Eight hours is one shift: past that, the environment is not in an incident
# any more, it is in its new normal, and the gates should be back on.
MAX_TTL_MINUTES = 480
# The gates that an incident is allowed to stand down. `guard` is deliberately
# absent and must stay absent: it is the hook that refuses force pushes, secret
# commits and history rewrites, and an incident is exactly when someone is
# tired enough to need it. Standing down the checks that tell you the change is
# wrong is a trade; standing down the ones that stop the change being
# unrecoverable is not.
STANDABLE_GATES = ("verify", "promote")


def _int_or(value, default):
    """`value` as an int when it plausibly is one, else `default`.

    Same shape as crew_state.int_or, duplicated rather than imported: crew_state
    imports this module, and a cycle in a SessionStart hook breaks every session
    opened in the repository. A bool is rejected on purpose - True is an int in
    Python, and `"ttlMinutes": true` means someone was confused.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _dict_or_empty(value):
    return value if isinstance(value, dict) else {}


def emergency_config(cfg):
    """The `emergency` block of .crew/config.json, with defaults applied."""
    block = _dict_or_empty(_dict_or_empty(cfg).get("emergency"))
    ttl = _int_or(block.get("ttlMinutes"), DEFAULT_TTL_MINUTES)
    if ttl <= 0:
        ttl = DEFAULT_TTL_MINUTES
    # A ceiling below the default window would make every declaration shorter
    # than asked for without saying so; the larger of the two is the honest
    # reading of "cap it at this".
    max_ttl = max(_int_or(block.get("maxTtlMinutes"), MAX_TTL_MINUTES), ttl)
    return {
        # standDown false = an incident is still declared, recorded and briefed,
        # and the gates keep gating. For a repo where skipping verification is
        # not a decision anyone local gets to make.
        "standDown": block.get("standDown") is not False,
        "ttlMinutes": ttl,
        "maxTtlMinutes": max_ttl,
    }


def read_json(path):
    """Parsed JSON at `path`, or {} for anything that goes wrong."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_skips(root):
    """The skip log as a list of (epoch, gate, detail), oldest first.

    Deduplicated on (gate, detail) here as well as on write. The writers check
    before appending, but two hook flavours appending at the same instant can
    both miss the row - and the count in a debt list is the number of things
    owed, not the number of times a gate declined to run one. Deduping on read
    makes that true regardless of how the file was written.
    """
    path = os.path.join(root, SKIP_LOG_PATH)
    rows, seen = [], set()
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                row = (parts[1], parts[2] if len(parts) > 2 else "")
                if row in seen:
                    continue
                seen.add(row)
                rows.append((_int_or(parts[0], 0), row[0], row[1]))
    except OSError:
        return []
    return rows


def read_state(root, cfg=None, now=None):
    """Everything a brief or a gate needs to know, and nothing it does not.

    Always returns a dict. `present` is whether a file exists at all;
    `active` is whether it is present AND unexpired AND allowed to stand
    gates down. Those are three different questions and collapsing them is
    how a repository ends up permanently ungated.
    """
    now = int(time.time() if now is None else now)
    state = read_json(os.path.join(root, STATE_PATH))
    emergency = emergency_config(cfg or {})
    if not state.get("id"):
        return {
            "present": False, "active": False, "expired": False,
            "id": None, "summary": "", "skips": 0, "minutesLeft": 0,
            "standDown": emergency["standDown"],
        }
    expires = _int_or(state.get("expiresAtEpoch"), 0)
    expired = expires <= now
    skips = len(read_skips(root))
    return {
        "present": True,
        # An incident with standDown off is real, briefed, and gates nothing.
        "active": not expired and emergency["standDown"],
        "expired": expired,
        "id": state.get("id"),
        "summary": state.get("summary") or "",
        "declaredAt": state.get("declaredAt") or "",
        "expiresAt": state.get("expiresAt") or "",
        "skips": skips,
        "minutesLeft": max(0, (expires - now) // 60),
        "standDown": emergency["standDown"],
        "lanes": state.get("lanes") if isinstance(state.get("lanes"), list) else [],
    }


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _new_id(root, now):
    base = time.strftime("INC-%Y%m%d-%H%M", time.gmtime(now))
    archive = os.path.join(root, ARCHIVE_DIR)
    if not os.path.exists(os.path.join(archive, base + ".json")):
        return base
    # Two incidents inside one minute is unlikely and survivable; silently
    # overwriting the first one's archive is not.
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        candidate = f"{base}{suffix}"
        if not os.path.exists(os.path.join(archive, candidate + ".json")):
            return candidate
    return base + "-x"


def declare(root, summary, cfg=None, ttl_minutes=None, lanes=None, now=None):
    """Open an incident. Returns its state dict.

    Re-declaring while one is already open and unexpired EXTENDS it rather
    than replacing it: two incident records for one outage means two partial
    debt lists, and the second one silently orphans the first one's skips.
    """
    now = int(time.time() if now is None else now)
    emergency = emergency_config(cfg or {})
    ttl = _int_or(ttl_minutes, emergency["ttlMinutes"])
    ttl = max(1, min(ttl, emergency["maxTtlMinutes"]))

    existing = read_json(os.path.join(root, STATE_PATH))
    if existing.get("id") and _int_or(existing.get("expiresAtEpoch"), 0) > now:
        return extend(root, ttl_minutes=ttl, cfg=cfg, now=now)

    expires = now + ttl * 60
    state = {
        "id": _new_id(root, now),
        "summary": summary.strip(),
        "declaredAt": _iso(now),
        "declaredAtEpoch": now,
        "expiresAt": _iso(expires),
        "expiresAtEpoch": expires,
        "ttlMinutes": ttl,
        "standDown": emergency["standDown"],
        "gates": list(STANDABLE_GATES),
        "lanes": list(lanes or []),
    }
    _write_state(root, state)
    # A fresh incident starts with a fresh skip log. The previous one's skips
    # were archived by end(); anything left here belongs to an incident nobody
    # closed, and folding it into this one would misattribute the debt.
    skip_log = os.path.join(root, SKIP_LOG_PATH)
    if os.path.exists(skip_log):
        os.replace(skip_log, skip_log + ".orphaned")
    return read_state(root, cfg, now=now)


def extend(root, ttl_minutes=None, cfg=None, now=None):
    """Push the expiry out from now. Capped by emergency.maxTtlMinutes."""
    now = int(time.time() if now is None else now)
    emergency = emergency_config(cfg or {})
    state = read_json(os.path.join(root, STATE_PATH))
    if not state.get("id"):
        return read_state(root, cfg, now=now)
    ttl = _int_or(ttl_minutes, emergency["ttlMinutes"])
    ttl = max(1, min(ttl, emergency["maxTtlMinutes"]))
    # From `now`, not from the old expiry: an incident extended four times
    # should not be able to reach eight hours past the point anyone was
    # watching. The cap is on the remaining window, every time.
    state["expiresAtEpoch"] = now + ttl * 60
    state["expiresAt"] = _iso(state["expiresAtEpoch"])
    state["ttlMinutes"] = ttl
    state.setdefault("extensions", [])
    state["extensions"].append(_iso(now))
    _write_state(root, state)
    return read_state(root, cfg, now=now)


def _write_state(root, state):
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    path = os.path.join(root, STATE_PATH)
    # PID in the temp name: two processes writing state at once would otherwise
    # share one temp file and interleave into it, and os.replace would publish
    # whichever half won. They can still race on the final replace - one
    # declaration wins outright - but neither can publish a torn file.
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def log_skip(root, gate, detail="", now=None):
    """Append one skipped gate. Called by the gates; safe to call always.

    One row per gate+detail per incident, not per turn - matching
    crew_incident_log in _common.sh and Write-CrewIncidentSkip in the .ps1
    gates. Stop fires every turn and on Windows both flavours of the hook run,
    so a ten-turn incident would otherwise report forty skipped gates: a number
    that measures how long the incident lasted rather than what is owed. The
    closing report is a debt list, and the same unrun check is one debt however
    many times the gate declined to run it.
    """
    now = int(time.time() if now is None else now)
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    path = os.path.join(root, SKIP_LOG_PATH)
    row = (str(gate), str(detail).replace("\t", " "))
    if any(previous[1:] == row for previous in read_skips(root)):
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join((str(now),) + row) + "\n")


def report(root, cfg=None, now=None):
    """The closing report's text. Pointers and a debt list, not a narrative."""
    state = read_state(root, cfg, now=now)
    if not state["present"]:
        return ""
    skips = read_skips(root)
    by_gate = {}
    for _, gate, detail in skips:
        by_gate.setdefault(gate, []).append(detail)

    lines = [
        f"# {state['id']}",
        "",
        f"summary: {state['summary']}",
        f"declared: {state['declaredAt']}",
        f"closed: {_iso(int(time.time() if now is None else now))}",
        "",
        "## Gates that did not run",
        "",
    ]
    if not skips:
        lines.append("None. The gates stood down but nothing tripped them.")
    else:
        for gate in sorted(by_gate):
            details = by_gate[gate]
            lines.append(f"- {gate}: {len(details)} skipped")
            # Distinct details only, and capped: a 40-line list of the same
            # pytest invocation tells you nothing the count did not.
            seen = []
            for detail in details:
                if detail and detail not in seen:
                    seen.append(detail)
            for detail in seen[:10]:
                lines.append(f"  - {detail}")
            if len(seen) > 10:
                lines.append(f"  - ... and {len(seen) - 10} more")
    lines += [
        "",
        "## Owed",
        "",
        "- Run the skipped gates above against the current tree and record the result.",
        "- Open a ticket for every fix made during the incident that has not had a review.",
        "- If a deploy went out ungated, add its row to .work/PROMOTIONS.md now.",
        "",
        "## Verify first",
        "",
        "- This list is what the hooks saw. A change made with no tool call the",
        "  gates watch is not in it; check `git log` for the incident window too.",
    ]
    return "\n".join(lines) + "\n"


def end(root, cfg=None, now=None):
    """Close the incident: write the report, archive the state, re-gate.

    Returns (report_path, state_before_close). Idempotent - closing when
    nothing is open writes nothing and returns (None, state).
    """
    now = int(time.time() if now is None else now)
    before = read_state(root, cfg, now=now)
    if not before["present"]:
        return None, before

    # The state file is read more than once in here, so confirm up front that it
    # is still the same incident, and confirm it BEFORE writing anything. A
    # declaration that landed in between would otherwise be archived under the
    # previous id and then deleted, re-gating a repository somebody had just
    # declared an incident for - and leaving a report for an incident that is
    # still open.
    current = read_json(os.path.join(root, STATE_PATH))
    if current.get("id") and current["id"] != before["id"]:
        return None, before

    text = report(root, cfg, now=now)
    os.makedirs(os.path.join(root, REPORT_DIR), exist_ok=True)
    # Forward slash, not os.path.join: this string is printed to a human, put
    # in the archived record, and quoted in a command they may paste. Every
    # other path crew shows (".work/HANDOFF.md", ".crew/config.json") is
    # written this way, and a lone backslashed one reads like a different repo.
    report_path = f"{REPORT_DIR}/INCIDENT-{before['id']}.md"
    with open(os.path.join(root, report_path), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(text)

    os.makedirs(os.path.join(root, ARCHIVE_DIR), exist_ok=True)
    state = dict(current)
    state["closedAt"] = _iso(now)
    state["closedAtEpoch"] = now
    state["skips"] = before["skips"]
    state["report"] = report_path
    archive = os.path.join(root, ARCHIVE_DIR, f"{before['id']}.json")
    with open(archive, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")

    skip_log = os.path.join(root, SKIP_LOG_PATH)
    if os.path.exists(skip_log):
        os.replace(skip_log, os.path.join(root, ARCHIVE_DIR,
                                          f"{before['id']}-skips.log"))
    # Last, and only after the archive is on disk: while this file exists the
    # gates are down, so the order here is the difference between a crash
    # leaving a stale incident (recoverable) and losing the record (not).
    os.remove(os.path.join(root, STATE_PATH))
    return report_path, before


def format_status(state):
    """One human line for a status query or a brief.

    Every read is .get() with a default: this is called from pm_brief, which
    runs on SessionStart, and it is also called by the crew:pm agent against
    hand-assembled state. A KeyError here would break every session opened in
    the repository, which is a high price for a missing key in a status line.
    """
    if not state.get("present"):
        return "no incident open"
    ident = state.get("id") or "an incident"
    skips = state.get("skips", 0)
    left = state.get("minutesLeft", 0)
    if state.get("expired"):
        return (f"{ident} EXPIRED and not closed - gates are back on, "
                f"{skips} skipped gate(s) still unaccounted for")
    if not state.get("standDown", True):
        return (f"{ident} open, {left}m left - gates are "
                f"NOT standing down (emergency.standDown is false)")
    return f"{ident} open, {left}m left, {skips} gate(s) skipped so far"


def main(argv=None):
    """CLI for /crew:emergency. Prints one line, or the report path."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(prog="crew_incident")
    parser.add_argument("action",
                        choices=("declare", "status", "extend", "end", "log"))
    parser.add_argument("--summary", default="")
    parser.add_argument("--ttl", type=int, default=None)
    parser.add_argument("--gate", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)

    root = args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cfg = read_json(os.path.join(root, ".crew", "config.json"))

    if args.action == "declare":
        if not args.summary.strip():
            print("declare needs --summary: one line on what is actually broken")
            return 2
        print(format_status(declare(root, args.summary, cfg=cfg,
                                    ttl_minutes=args.ttl)))
        return 0
    if args.action == "extend":
        print(format_status(extend(root, ttl_minutes=args.ttl, cfg=cfg)))
        return 0
    if args.action == "log":
        if not args.gate:
            print("log needs --gate")
            return 2
        log_skip(root, args.gate, args.detail)
        return 0
    if args.action == "end":
        path, before = end(root, cfg=cfg)
        if path is None:
            print("no incident open - nothing to close")
            return 0
        print(f"{before['id']} closed, {before['skips']} skipped gate(s), "
              f"report: {path}")
        return 0
    print(format_status(read_state(root, cfg)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
