"""One emission per event from hooks whose only effect is output or a write.

hooks.json registers every hook twice, a bash `command` and a
`shell: "powershell"` twin. Each .ps1 stands down off Windows, but no .sh
stands down on Windows -- and must not: CLAUDE.md records the release where
an OS-based stand-down left a guard blocking nothing. So on Windows both
flavours can run for one event. For a blocking hook that is only a cost (two
identical verdicts). For a hook that EMITS -- a chat ping, a handoff
skeleton, a transcript copy -- it is a visible duplicate.

Blocking hooks (scope-guard, completion-audit, cloud-guard, role-write-guard,
approval-hook, verify-gate) take NO claim and keep running in both flavours:
a claim would let whichever flavour lost its python decide alone. The cost of
that, measured 2026-09-23 on Linux with pwsh (OS=Windows_NT), median of 5: the
.ps1 run adds ~0.5-0.65s per hook (sh ~0.08s), ~1.2s per Edit/Bash PreToolUse
when two guards match if the harness runs them serially; the burn-in measured
pwsh at ~2.2x python per invocation on Windows itself.

Why not hook_once.py: its key is (hook, session) and never expires inside a
session, which is right for SessionStart and wrong for Notification and
PreCompact, both of which fire many times per session.

IDENTITY. An event is keyed on hook + session + hook_event_name + the
payload's own unique fields where it carries any (`_UNIQUE_FIELDS`:
tool_use_id, prompt_id, timestamp, ...) + a digest of the payload bytes.
Notification and PreCompact payloads carry NO unique field today, so for
them two byte-identical payloads inside WINDOW seconds are ONE event: the
second invocation is indistinguishable from the other flavour's copy of the
first, and is treated as that. A payload that does carry a unique field is
never merged with a different invocation.

CLAIMS ARE GENERATIONS, NOT A MUTATED MARKER. Each event for a key is a new
file `<key>.g<N>`, created with O_CREAT|O_EXCL -- one atomic step, so both
flavours racing for the same N get exactly one winner. There is no second
step whose absence could poison the key: a claimant that dies anywhere
leaves at most one generation file, and that file is an ordinary claim that
expires WINDOW seconds after it was written, like any other. (The previous
design created a takeover file and THEN refreshed the primary's mtime; a
crash between the two left the takeover name permanently taken and every
later identical event lost against it until the 24h prune.)

INTENT, THEN SENT. A generation is written "claimed" before the caller
emits, and the caller reports "sent" (`--sent <token>`) only after the
emission succeeded. The other flavour, finding "claimed", waits up to the
hook's GRACE for "sent"; if it never comes the claimant is presumed dead and
the waiter takes the next generation and emits itself. So a winner that
crashes between exit 0 and its emission costs a delay, not the only
emission. GRACE is bounded by the hook's own latency budget: a winner whose
emission takes longer than GRACE produces a duplicate, which is the safe
side.

UNWRITABLE STORE. When the claim directory cannot be created or written,
both flavours would otherwise fail open and emit. Instead exactly one,
decided by a rule both compute identically without the store, emits:
PowerShell where OS=Windows_NT (the only place both flavours run), bash
everywhere else. A caller that does not say which flavour it is emits.

Usage:  <python> event_claim.py <hook-name> <root> [sh|ps1]   (payload on stdin)
        <python> event_claim.py --sent <token>
Exit 0   emit; stdout carries the token to hand back with --sent (empty
         when there is nothing to report back).
Exit 10  the other flavour has this event -- exit quietly.
Anything else (a crash, a missing interpreter) means "could not decide", and
callers emit: a duplicate is the safe failure, a suppressed handoff is not.
An empty payload is not a hook invocation (a command calling notify.sh by
hand) and always emits.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

LOST = 10
WINDOW = 60
GRACE = 5
# notify: the Notification hook's timeout is 15s and its send is `curl -m 10`,
# so a waiter that takes over must still have ~10s left to send in.
_HOOK_GRACE = {"notify": 4, "handoff-write": 5}
_POLL = 0.1
_STALE_SECONDS = 24 * 60 * 60
_READ_SECONDS = 5
_UNIQUE_FIELDS = ("tool_use_id", "prompt_id", "event_id", "notification_id",
                  "uuid", "id", "timestamp")


def claims_dir(root):
    """`<git-common-dir>/crew/event-claims`, beside crew_context.py's
    context-claims, so a worktree and its main checkout share one set and
    nothing lands in the working tree. Outside git, `.crew/event-claims`."""
    try:
        done = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"],
                              capture_output=True, text=True, timeout=10, check=False)
        common = done.stdout.strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        common = ""
    if common:
        base = common if os.path.isabs(common) else os.path.join(root, common)
        return os.path.join(base, "crew", "event-claims")
    return os.path.join(root, ".crew", "event-claims")


def normalise(raw):
    """The bytes both flavours agree on. bash's `$(cat)` drops trailing
    newlines and a PowerShell read can keep a BOM, so neither survives into
    the key."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.strip()


def _safe(value, limit):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:limit]


def event_key(hook, raw):
    """hook-session-event-unique-digest. The digest covers every byte, so the
    named parts add readability, not uniqueness -- see IDENTITY above."""
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        data = None
    data = data if isinstance(data, dict) else {}
    session = _safe(data.get("session_id") or "nosession", 40)
    event = _safe(data.get("hook_event_name") or "noevent", 20)
    unique = [f"{name}={data[name]}" for name in _UNIQUE_FIELDS if data.get(name) not in (None, "")]
    uid = hashlib.sha256("\0".join(unique).encode("utf-8")).hexdigest()[:8] if unique else "nouid"
    digest = hashlib.sha256(hook.encode("utf-8") + b"\0" + raw).hexdigest()[:32]
    return f"{_safe(hook, 16)}-{session}-{event}-{uid}-{digest}"


def designated(flavour):
    """The one flavour that emits when the claim store is unusable. Both
    flavours compute this from the environment alone."""
    if flavour not in ("sh", "ps1"):
        return True
    return flavour == ("ps1" if os.environ.get("OS") == "Windows_NT" else "sh")


def _prune(directory, now):
    cutoff = now - _STALE_SECONDS
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass


def _generations(directory, key):
    prefix = key + ".g"
    found = []
    for name in os.listdir(directory):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            found.append(int(name[len(prefix):]))
    return found


def _record(state, nonce, at):
    return json.dumps({"state": state, "nonce": nonce, "at": at}).encode("utf-8")


def _create(path, body):
    """O_EXCL: True when this process now owns `path`. The body is written
    after the create, so a reader can see an empty file -- `_read` treats that
    as "claimed at its mtime", which is also what a crash here leaves."""
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(handle, body)
    finally:
        os.close(handle)
    return True


def _read(path):
    """(state, at), or None when the generation vanished (pruned)."""
    try:
        with open(path, "rb") as handle:
            body = handle.read()
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
        return str(data["state"]), float(data["at"])
    except (ValueError, KeyError, TypeError):
        return "claimed", mtime


def _take(directory, key, generation, now):
    nonce = os.urandom(8).hex()
    path = os.path.join(directory, f"{key}.g{generation}")
    if _create(path, _record("claimed", nonce, now)):
        return True, f"{nonce} {path}"
    return False, ""


def decide(root, hook, raw, flavour=None, now=None):
    """(emit, token)."""
    raw = normalise(raw)
    if not raw:
        return True, ""
    now = time.time() if now is None else now
    grace = _HOOK_GRACE.get(hook, GRACE)
    directory = claims_dir(root)
    key = event_key(hook, raw)
    waited = 0.0
    try:
        os.makedirs(directory, exist_ok=True)
        _prune(directory, now)
        while True:
            current = max(_generations(directory, key), default=0)
            seen = _read(os.path.join(directory, f"{key}.g{current}")) if current else None
            if seen is None or now - seen[1] >= WINDOW:
                # No claim, or only one from an EARLIER identical event: this
                # is a new event, and both flavours race for the same next
                # generation.
                ok, token = _take(directory, key, current + 1, now)
                if ok:
                    return True, token
                # Lost the O_EXCL race: the other flavour just created this
                # generation. Loop back rather than returning False here --
                # if the winner then crashes before marking it "sent", a
                # bare loss must not be the loser's final answer, or a
                # winner that dies right after _create costs BOTH flavours
                # their only emission. Falling through to the top treats the
                # winner's fresh claim like any other seen claim: wait for
                # "sent", and take over the NEXT generation ourselves if it
                # never comes.
                continue
            state, at = seen
            if state == "sent":
                return False, ""
            # `waited` bounds this even when `at` is nonsense (a clock step,
            # a hand-edited record): no caller waits longer than one grace.
            if now - at >= grace or waited >= grace:
                ok, token = _take(directory, key, current + 1, now)
                if ok:
                    return True, token
                # Lost the takeover race too; loop back and wait on whoever
                # won it, same reasoning as above.
                continue
            time.sleep(_POLL)
            now += _POLL
            waited += _POLL
    except OSError:
        return designated(flavour), ""


def claim(root, hook, raw, now=None, flavour=None):
    """True when this process emits for this event."""
    return decide(root, hook, raw, flavour, now)[0]


def mark_sent(token):
    """Record that the emission for `token` succeeded. Temp-then-replace, so
    a crash leaves either the old "claimed" record or the new one.

    The generation file NAME alone is not proof that `token` still owns it:
    `_prune` deletes a generation once it is 24h stale, and `decide` can then
    reuse that same generation number for an unrelated, later event. A
    caller that was delayed past that window and only now reports "sent"
    for its OLD claim must not be allowed to stamp the NEW one sharing its
    path -- the nonce in `token` is checked against the nonce actually on
    disk, and a mismatch (or a record too corrupt to carry one) means the
    generation was recycled out from under this token: refuse rather than
    overwrite, the same "refuse rather than destroy" rule `heal_config`
    applies to a config it cannot safely touch."""
    nonce, _, path = token.partition(" ")
    if not nonce or not path:
        return False
    try:
        with open(path, "rb") as handle:
            body = handle.read()
    except OSError:
        return False
    try:
        data = json.loads(body.decode("utf-8"))
        at = float(data["at"])
        stored_nonce = str(data["nonce"])
    except (ValueError, KeyError, TypeError):
        return False
    if stored_nonce != nonce:
        return False
    temp = f"{path}.tmp-{nonce}"
    try:
        with open(temp, "wb") as handle:
            handle.write(_record("sent", nonce, at))
        os.replace(temp, path)
    except OSError:
        return False
    return True


def _read_stdin():
    """stdin, or b"" when nothing arrives in time. A caller that leaves stdin
    open and never writes -- a terminal, a harness pipe -- must not hang the
    hook; the payload Claude Code sends is written and closed at once."""
    box = []
    reader = threading.Thread(target=lambda: box.append(sys.stdin.buffer.read()), daemon=True)
    reader.start()
    reader.join(_READ_SECONDS)
    return box[0] if box else None


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "--sent":
        mark_sent(args[1])
        return 0
    if len(args) < 2:
        return 0
    raw = _read_stdin()
    if raw is None:
        sys.stdout.flush()
        os._exit(0)  # the reader thread is still blocked; do not wait on it
    emit, token = decide(os.path.abspath(args[1]), args[0], raw,
                          args[2] if len(args) > 2 else None)
    if not emit:
        return LOST
    if token:
        print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
