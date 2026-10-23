"""T-0013: the ORDER of the resume typing path, read from the sender's source.

Static text only -- nothing here executes a sender. Each check asserts that a
gate sits before the keystroke it guards, in the one order that makes it
load-bearing: claim the per-handoff marker after every refusal, record the
run, then spawn; in the tmux sender, delay -> ready probe -> inhibit ->
send-keys. A gate moved after its keystroke still passes
every behavioural test that sets CREW_AUTOCLEAR_INHIBIT, which is why this
file exists (after test_auto_clear_review_fixes.py's structural order test).
"""
import os

import context  # noqa: F401  pylint: disable=unused-import

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access


def _read(name):
    with open(os.path.join(_SCRIPTS, name), encoding="utf-8") as handle:
        return handle.read()


def _in_order(text, markers):
    """The offset of each marker, each searched after the previous one; -1
    for one that is missing or out of order."""
    offsets, at = [], 0
    for marker in markers:
        found = text.find(marker, at)
        offsets.append(found)
        at = found + len(marker) if found >= 0 else at
    return offsets


def _sh_resume_block():
    source = _read("auto-clear.sh")
    start = source.index('if [ "$RESUME" -eq 1 ]; then')
    return source[start:source.index("\nFORCE_ARG=()", start)]


def test_sh_resume_block_claims_records_then_spawns():
    block = _sh_resume_block()
    markers = ['crew_autocycle.py")" resume-plan', '[ "$STATUS" = "send" ] || refuse',
               '( set -o noclobber; : > "$MARKER" )', 'crew_resume.py")" record',
               '[ "$RECORDED" = "ok" ] || refuse', 'setsid bash "$send_script"']

    assert -1 not in _in_order(block, markers), list(zip(markers, _in_order(block, markers)))


def test_sh_sender_delays_probes_then_inhibits_then_sends():
    block = _sh_resume_block()
    markers = ["printf 'sleep %q\\n' \"$DELAY\"", 'while [ "$state" != "ready" ]; do',
               'if [ -n "${CREW_AUTOCLEAR_INHIBIT:-}" ]; then', 'tmux send-keys -t "$PANE" -l "$TEXT"',
               "sleep 0.5", 'tmux send-keys -t "$PANE" Enter']

    assert -1 not in _in_order(block, markers), list(zip(markers, _in_order(block, markers)))
    assert block.count("send-keys") == 2


def test_sh_resume_block_exits_before_the_clear_path():
    block = _sh_resume_block()

    assert block.rstrip().endswith("exit 0\nfi")
