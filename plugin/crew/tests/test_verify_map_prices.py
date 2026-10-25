"""`.crew/verify.json` prices: a rule whose `why` states a Windows figure must
not be priced below it, and the rules measured over the Stop budget on Windows
(L-0904) must say so, so a cold Windows checkout stops admitting them at Stop.
"""
import json
import math
import os
import re

import context  # noqa: F401  pylint: disable=unused-import

_REPO = os.path.dirname(os.path.dirname(context._ROOT))  # pylint: disable=protected-access
_MAP = os.path.join(_REPO, ".crew", "verify.json")
_WINDOWS = re.compile(r"Windows (\d+)s \(win-repo-2, ")
_STOP_BUDGET = 60

_CROSSING = (
    "root-docs-registration", "promote-gate-rows", "promote-gate-review",
    "crew-ghdeploy", "crew-config", "crew-state", "crew-ticket-approval",
    "claude-md-audit", "crew-docs-check-script", "gizmoduck", "refresh-check",
    "autopilot-ship", "crew-ticket-status", "approval-hook", "refresh-admission",
    "crew-standards", "crew-inflight", "crew-train", "tooling-pr-harness",
    "kimi-provider", "crew-shell", "ci-receipt", "verify-gate-completion",
    "verify-gate-subset-cover", "crew-keys", "status-vocabulary", "crew-split",
    "verify-agents", "crew-help", "graph-ignore",
)


def _rules():
    with open(_MAP, encoding="utf-8", errors="strict") as fh:
        return json.load(fh)["rules"]


def _problems(rules):
    found = []
    for rule in rules:
        name = rule.get("id")
        seconds = rule.get("seconds")
        not_a_price = (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                       or (isinstance(seconds, float) and not math.isfinite(seconds)))
        if not_a_price or seconds < 0:
            found.append(f"{name}: seconds {seconds!r} is not a finite number >= 0")
            continue
        for stated in _WINDOWS.findall(rule.get("why", "")):
            if seconds < int(stated):
                found.append(f"{name}: seconds {seconds} is below its stated Windows {stated}s")
    return found


def test_every_rule_has_nonnegative_seconds_and_a_why_that_names_any_windows_price():
    assert _problems(_rules()) == []


def test_a_rule_priced_below_its_stated_windows_figure_is_reported():
    rules = [{"id": "x", "seconds": 12, "why": "Windows 100s (win-repo-2, d, r)."},
             {"id": "y", "seconds": 0, "why": "unchecked"},
             {"id": "z", "seconds": -1, "why": ""}]

    found = _problems(rules)

    assert len(found) == 2
    assert found[0].startswith("x: seconds 12 is below")
    assert found[1].startswith("z: seconds -1")


def test_a_nan_or_infinite_seconds_is_reported_not_passed():
    rules = [{"id": "n", "seconds": float("nan"), "why": "Windows 100s (win-repo-2, d, r)."},
             {"id": "i", "seconds": float("inf"), "why": ""},
             {"id": "h", "seconds": 10 ** 400, "why": "Windows 100s (win-repo-2, d, r)."}]

    found = _problems(rules)

    assert [f.split(":")[0] for f in found] == ["n", "i"]


def test_the_note_paragraph_for_l_0904_starts_its_own_line():
    with open(_MAP, encoding="utf-8", errors="strict") as fh:
        note = json.load(fh)["_note"]
    shared = [ln for ln in note if "L-0904:" in ln and not ln.startswith("L-0904:")]

    assert shared == []


def test_the_rules_that_cross_the_stop_budget_on_windows_state_it_and_are_priced_over_it():
    by_id = {r["id"]: r for r in _rules()}
    missing = [i for i in _CROSSING if i not in by_id]
    unstated = [i for i in _CROSSING if i in by_id and not _WINDOWS.search(by_id[i]["why"])]
    cheap = [i for i in _CROSSING if i in by_id and by_id[i]["seconds"] <= _STOP_BUDGET]

    assert (missing, unstated, cheap) == ([], [], [])
