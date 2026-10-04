"""T-0013: the ORDER of the resume typing path, read from the senders' source.

Static text only -- nothing here executes a sender. Each check asserts that a
gate sits before the keystroke it guards, in the one order that makes it
load-bearing: in both senders, claim the per-handoff marker after every
refusal, record the run, then spawn; in the tmux sender, delay -> ready probe
-> inhibit -> send-keys; in the .ps1 child, delay -> foreground check -> tab
recheck -> inhibit -> SendWait. A gate moved after its keystroke still passes
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


def _ps1_child():
    source = _read("auto-clear.ps1")
    start = source.index("$child = @'\n")
    return source[start:source.index("\n'@", start)]


def test_sh_resume_block_claims_records_then_spawns():
    block = _sh_resume_block()
    markers = ['crew_autocycle.py" resume-plan', '[ "$STATUS" = "send" ] || refuse',
               '( set -o noclobber; : > "$MARKER" )', 'crew_resume.py" record',
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


def test_ps1_resume_claims_records_then_spawns():
    source = _read("auto-clear.ps1")
    markers = ["resume-plan", "switch ($method)", "if ($declineReason) {",
               "$claim = [System.IO.File]::Open($sentMarker, [System.IO.FileMode]::CreateNew)",
               'crew_resume.py") record', 'Stop-CrewAutoClear "could not record the run',
               'Write-CrewAutoClearNote "would have sent, but CREW_AUTOCLEAR_INHIBIT is set"',
               "Start-Process -FilePath $exe"]

    assert -1 not in _in_order(source, markers), list(zip(markers, _in_order(source, markers)))


def test_ps1_child_delays_rechecks_then_inhibits_then_sends():
    child = _ps1_child()
    markers = ["Start-Sleep -Seconds $Delay", "$fg = [CrewAC.Win]::GetForegroundWindow()",
               "$recheck = Get-CrewChildTabRecheck", 'if ($recheck.Decision -ne "send") {',
               "if ($env:CREW_AUTOCLEAR_INHIBIT) {", "[System.Windows.Forms.SendKeys]:" + ":SendWait($escaped)"]

    assert -1 not in _in_order(child, markers), list(zip(markers, _in_order(child, markers)))
    assert child.count("SendWait(") == 2


def test_ps1_resume_types_the_plans_command_through_the_one_child():
    """Resume mode has no sender of its own: the plan's prompt and delay are
    what the existing child is handed."""
    source = _read("auto-clear.ps1")

    assert ("$command = $planLines[5]" in source, "$delay = Get-CrewAutoClearInt $planLines[6]" in source,
            source.count("$child = @'"), source.count("Start-Process -FilePath $exe")) == (True, True, 1, 1)
