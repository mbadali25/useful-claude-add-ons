# L-0656 plan - held pings while asleep, and the morning summary sent once (notify half)

Written by the implementing session, 2026-10-07, on `rush/g6b-goals-sleep` (T-0053, L-0652,
L-0653, L-0654 and T-0051/T-0060's `crew_notify.py` on the base).

## Which half

- **Notify half: built.** T-0051 is merged: the notifier is `crew_notify.py`, one Python module
  behind `notify.sh` and `notify.ps1` (thin wrappers that hand it the event), so the hold is
  decided once, in Python, where the event is sent (`crew_notify.send`), and both shell flavours
  reach it unchanged.
- **Review half: still blocked.** `autopilot.reviewPolicy` is not on the base
  (`crew_keys._coming("autopilot.reviewPolicy", "T-0029", ...)`; `git grep reviewPolicy` finds no
  reader). `autopilot.sleep.reviewPolicy` keeps reading "not available in this crew version". It
  stays in this ticket for when T-0029 / T-0067 lands.

## Decisions

- **Key.** `autopilot.sleep.notifyHold`: `null` (default) or exactly `true`. Anything else
  (`false` included, `"true"`, `1`) is refused with a warning and the hold stays off: what crew
  cannot read never hides a ping.
- **When it holds.** Only while autopilot is armed, the resolved state is `asleep`, and that
  state is not `tightenOnly` (a manual sleep outside the scheduled window may only tighten until
  L-1504; hiding the owner's pings is not a tightening). Awake, off, `unknown`, a crash while
  deciding: every event sends as before.
- **What it holds.** The pings that only ask for attention: every `question` (permission and
  ask) and the `blocker` kinds `approval` (Approval waiting) and `rounds` (Review out of
  rounds). Never held: every `deploy` result (a failure, an unknown outcome and a silent pass),
  `blocker` `gate` (Stop gate refused, the failed gate), `lane` and `lane-unknown`, and a blocker
  with no or an unknown kind. A positive list: a kind not on it sends.
- **Held means dropped and counted** (the hand-off's recommended answer). `<git-common-dir>/crew/
  notify/held.json` keeps one key per distinct held message (the same material `_deliver`'s
  dedupe fingerprint is made of), so a ping repeated in one waiting episode counts once. If the
  record cannot be written the ping is sent instead.
- **The morning summary.** `sleep-summary` (and `wake`, which runs it) not asleep, with
  unreported entries or held pings: prints L-0653's summary plus `held pings: <n>`, writes the
  marker, empties the held record and passes the same text to the notifier once, under a lock so
  two runs never both send. The send goes through the configured provider and credentials
  (`crew_notify._credentials`, factored out of `_deliver`), silent, only when `question` or
  `blocker` is in `notify.events`; no new event exists. A held record that cannot be read is
  said so, never read as zero.
- **The first run after the window.** `settings` warns `<n> pings were held while asleep - run
  crew_autopilot.py sleep-summary` beside L-0653's warning, and `autopilot.md`'s settings step
  runs `sleep-summary` when either warning is printed.
- **Where the code goes.** `crew_autopilot.py` is at pylint's 3,400-line cap: nothing is added
  there. The rule and the record are a new module, `crew_notify_hold.py`; `crew_sleep.py` reads
  the key; `crew_autopilot_sleep.py` sends the summary.

## Steps
### Step 1: the key
Files: crew_sleep.py, crew_state.py, crew_keys.py, crew_config_menu.py,
templates/config.template.json, skills/crew-setup/SKILL.md, tests.
### Step 2: the hold and the summary send
Files: crew_notify_hold.py (new), crew_notify.py, crew_autopilot_sleep.py, commands/autopilot.md,
tests/test_crew_autopilot_sleep.py.
### Step 3: docs
CONFIG.md, README, configuration reference rebuilt, codemap, CHANGELOG, verify.json.

Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py plugin/crew/tests/test_crew_notify.py plugin/crew/tests/test_crew_notify_blocker.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py plugin/crew/tests/test_crew_keys.py -q
