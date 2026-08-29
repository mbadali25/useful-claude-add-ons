"""Re-engages the crew PM when the project's state actually changed.

`pm_brief` fires at SessionStart and then never again, so a session that opens
clean and then closes a ticket, breaks a gate, or moves the code out from under
every diagram hears nothing about any of it. This is the other half: a Stop
hook that speaks when -- and only when -- something transitioned.

## Why not just run on Stop

Stop fires once per TURN. A brief on every turn is unusable noise, and it is
also the failure mode that makes people turn the PM off entirely, at which
point they get nothing. So the event is not the gate; a STATE FINGERPRINT is.

The fingerprint covers the fields a person would act on -- the trigger set,
the open ticket, whether a handoff is pending, the review health verdict. Turns
that only edit code do not move it and stay silent. The turn that closes the
ticket moves it, and that is the turn the PM speaks on.

## Why the fingerprint is also the de-duplicator

Both the .sh and .ps1 flavour of a matcher-less hook are registered, so both
fire wherever both interpreters exist. `hook_once` is the usual answer and is
explicitly WRONG here -- read its module docstring: its marker is keyed on
(hook, session) and never cleared, so a claim taken on turn 1 silences the hook
for the rest of the session. That is precisely what this hook must not do.

Keying the marker on the FINGERPRINT instead solves both problems with one
mechanism. `O_CREAT|O_EXCL` makes creation atomic, so of the two flavours
racing on the same unchanged state exactly one wins. And because the key is the
state rather than the session, a genuine change later produces a different key
and fires again -- which is the whole point.

## Why it blocks

Emitting on stdout would show the user a brief and stop there; the model would
never see it and nothing would get assigned. A Stop hook that exits 2 with
stderr feeds that text back to the model as a reason to keep working, which is
what "the PM should engage without me asking" actually requires.

That makes this a BLOCKING hook, so it carries the matching obligations: a
committed must-block/must-allow suite (the `pm_pulse` section of
_test/run-tests.sh, driven through the wrapper as well as the module), and hard
loop guards. `stop_hook_active` is the first of them -- Claude Code sets it on
a continuation that a Stop hook itself forced, and re-blocking there is an
infinite loop. The fingerprint marker is the second: the same state can only
ever block once. The per-session cap is the third and is a backstop for a
pathological repo whose state oscillates every turn.

## Sharing Stop with verify-gate

`verify-gate` is registered on Stop too and can also exit 2, so both can block
on the same turn. That is noisy but safe, and deliberately not "solved":

- It cannot loop. Both honour `stop_hook_active`, so the forced continuation
  runs with both standing down.
- The finding is not lost. This hook writes its marker only on the turn it
  actually blocks, so its findings were delivered on that turn -- alongside the
  gate failure rather than instead of it.

Suppressing the pulse whenever the gate is red was considered and rejected:
there is no reliable in-process signal for "the gate failed this turn", and
inventing one (a shared marker file, a re-run of the checks) buys tidier output
at the cost of a second thing that can go wrong on every Stop. Noise on a red
turn is a worse-formatted message; a broken Stop chain is a repository nobody
can finish a turn in.
"""

import hashlib
import json
import os
import sys

import crew_state
import pm_brief

# A repo whose state genuinely changes every turn would otherwise block every
# turn. Past this many pulses the hook stands down for the rest of the session
# and says so once, rather than becoming the thing the user disables.
_MAX_PULSES_PER_SESSION = 12

# Findings that are not worth interrupting for. They are real, and the
# SessionStart brief still reports them -- but they describe a standing
# condition rather than something that just happened, and blocking the end of
# a turn to mention one is the noise this hook is designed not to be.
_QUIET_TRIGGERS = frozenset({"ticketsTooLarge", "reviewNotWorking"})


def fingerprint(state):
    """A stable digest of the state worth speaking up about.

    Deliberately NOT the whole state dict. `health.rate` is a float that moves
    on every recorded review and `knowledge.subsystems` moves whenever a map is
    written, so including them verbatim would fire on changes nobody asked to
    hear about. The verdict is included instead of the rate: a review health
    that slips from 0.9 to 0.8 is not news, one that crosses into "broken" is.
    """
    work = crew_state.dict_or_empty(state.get("work"))
    health = crew_state.dict_or_empty(state.get("health"))
    incident = crew_state.dict_or_empty(state.get("incident"))
    material = {
        "triggers": list(state.get("triggers") or []),
        "ticket": work.get("ticket"),
        "handoffPending": bool(work.get("handoffPending")),
        "verdict": health.get("verdict"),
        "incident": bool(incident.get("active")),
    }
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _pulse_dir(root):
    return os.path.join(root, ".crew")


def claim(root, session, digest):
    """True if this process may pulse for `digest`. Atomic across flavours.

    Fails CLOSED, unlike hook_once.claim which fails open. The costs are
    reversed: a hook that fails to speak up is a quiet session, while one that
    blocks the end of every turn because it could not write a marker is a
    session the user has to kill. When in doubt, say nothing.
    """
    if not session:
        return False
    dirpath = _pulse_dir(root)
    if not os.path.isdir(dirpath):
        return False
    marker = os.path.join(dirpath, f".pm-pulse-{session}-{digest}")
    try:
        handle = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except (FileExistsError, OSError):
        return False
    os.close(handle)
    return True


def pulses_taken(root, session):
    """How many distinct states this session has already pulsed on."""
    if not session:
        return 0
    prefix = f".pm-pulse-{session}-"
    try:
        return sum(
            1 for name in os.listdir(_pulse_dir(root)) if name.startswith(prefix)
        )
    except OSError:
        return 0


def should_pulse(state):
    """True when this state is worth interrupting the end of a turn for.

    Requires at least one trigger that is not merely a standing condition. A
    state with no triggers at all is a healthy repo, and a PM that announces
    "nothing to report" every time a ticket closes is the noise this exists to
    avoid.
    """
    if not state.get("isCrew"):
        return False
    pm = crew_state.dict_or_empty(state.get("pm"))
    if not pm.get("enabled", True):
        return False
    triggers = [t for t in (state.get("triggers") or [])
                if t not in _QUIET_TRIGGERS]
    return bool(triggers)


# Prepended to the findings so the model knows what the pulse IS. One per
# authority, and the difference is the whole point of the setting: under `act`
# this is a work order, under `report-only` it is something to put in front of
# the user and then stop. Sending the `act` text to a report-only repo would
# make the switch a lie -- the config would say "ask me" while the hook said
# "go" -- so the text is selected from the same normalised field every other
# consumer reads.
_DIRECTIVES = {
    "act": (
        "Crew PM: the project state changed and these are now outstanding. Act "
        "on them in the order given, using the crew role that fits each one, "
        "and report what you did when finished. If the user has already said "
        "what they want prioritised, that ordering wins over this one. Do not "
        "ask permission to start; do ask before removing a role or deleting "
        "anything. Stay on these findings: fix an unrelated problem only when "
        "it BLOCKS one of them, and ticket or TODO the rest rather than "
        "following it. Dispatch by actually calling the Agent tool -- a "
        "description of who you would send is not a dispatch, and a report "
        "written in the future tense means nothing ran."
    ),
    "report-only": (
        "Crew PM: the project state changed and these are now outstanding. "
        "Present them to the user as recommendations, shortest useful form, "
        "and stop -- do NOT dispatch agents or start fixing them. This repo "
        "has pm.authority set to report-only. If the user wants the work done, "
        "they will say so, or run /crew:pm assign."
    ),
}


def directive(state):
    pm = crew_state.dict_or_empty(state.get("pm"))
    return _DIRECTIVES[crew_state.normalise_authority(pm.get("authority"))]

_STOOD_DOWN = (
    "Crew PM: state has changed more than "
    f"{_MAX_PULSES_PER_SESSION} times this session, so the PM is standing down "
    "to avoid interrupting every turn. Run /crew:pm for the current picture."
)


def render(state):
    """The pulse text, or None when there is nothing worth saying."""
    if not should_pulse(state):
        return None
    lines = pm_brief.render(state)
    if not lines:
        return None
    return directive(state) + "\n\n" + "\n".join(lines)


def main(argv=None):
    """Hook entry point. Reads the Stop payload from stdin.

    Exit 0 stays out of the way. Exit 2 blocks the stop and hands stderr back
    to the model. Every failure path returns 0: a Stop hook that raises would
    block the end of every turn in the repository, which is unrecoverable
    without editing config, and a PM that fails silent is merely quiet.
    """
    del argv
    try:
        raw = sys.stdin.read()
    except OSError:
        return 0
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # Loop guard, and the single most important line in this file. Claude Code
    # sets this when the current turn exists BECAUSE a Stop hook blocked the
    # last one. Blocking again from here never terminates.
    if payload.get("stop_hook_active"):
        return 0

    root = payload.get("cwd") or os.environ.get(
        "CLAUDE_PROJECT_DIR"
    ) or os.getcwd()
    session = payload.get("session_id")

    try:
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    try:
        state = crew_state.collect(root)
        text = render(state)
        if text is None:
            return 0
        digest = fingerprint(state)
        # Count BEFORE claiming, so the claim that trips the cap is the one
        # that reports standing down rather than the one after it.
        over_cap = pulses_taken(root, session) >= _MAX_PULSES_PER_SESSION
        if not claim(root, session, digest):
            return 0
        sys.stderr.write(_STOOD_DOWN if over_cap else text)
        return 2
    except Exception:  # pylint: disable=broad-except
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
