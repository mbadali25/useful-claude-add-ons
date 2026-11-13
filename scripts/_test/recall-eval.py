#!/usr/bin/env python3
"""Suite for scripts/recall-eval.py, the Obsidian recall evaluation harness.

Runs under pytest (`python3 -m pytest scripts/_test/recall-eval.py -q -p no:cacheprovider`) or
as a plain script (`python3 scripts/_test/recall-eval.py`). Everything builds throwaway
fixtures in a temp directory and points recall at them through OBSIDIAN_VAULT_CONFIG; the
owner's real vault and config are never read, and nothing is installed.

Must-pass: the golden set holds on the recall code in this checkout; the metric arithmetic is
right; thresholds turn a miss into exit 1; a missing golden file is exit 2.

Must-block (sabotage): each mutation below breaks one behaviour in a COPY of the recall
scripts and the harness must go red naming it. A mutation that no longer applies (the source
moved) fails the suite, so the sabotage cannot silently become a no-op.

  ranker sorts ascending by score        -> hook-spawn-cost recall@3 drops
  budget loop stops setting truncated    -> budget-tight expects truncated
  archive prefix no longer excluded      -> an archived note comes back (rejected)
  project rank order reversed            -> project-match-first order check fails
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
RUNNER = os.path.join(SCRIPTS, "recall-eval.py")
PLUGIN_SCRIPTS = os.path.join(os.path.dirname(SCRIPTS), "plugin", "obsidian-vault", "hooks",
                              "scripts")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EVAL = load("recall_eval_under_test", RUNNER)
FIXTURE = EVAL.fixture


def run_runner(*args):
    proc = subprocess.run([sys.executable, RUNNER, *args], capture_output=True, text=True,
                          check=False, timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


def copy_scripts(dest):
    for name in os.listdir(PLUGIN_SCRIPTS):
        if name.endswith(".py"):
            shutil.copy(os.path.join(PLUGIN_SCRIPTS, name), os.path.join(dest, name))


def mutate(dest, old, new):
    """Rewrite vault_recall.py in the copy; fail loudly when `old` is not exactly once there."""
    path = os.path.join(dest, "vault_recall.py")
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert text.count(old) == 1, f"sabotage target moved, found {text.count(old)}x: {old!r}"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace(old, new))


def sabotaged_run(old, new):
    with tempfile.TemporaryDirectory(prefix="recall-eval-sab-") as tmp:
        copy_scripts(tmp)
        mutate(tmp, old, new)
        return run_runner("--scripts-dir", tmp, "--strict-gaps")


# ---- must-pass ------------------------------------------------------------------------

def test_golden_set_holds_on_this_checkout():
    code, out = run_runner("--strict-gaps")
    assert code == 0, out
    assert "OK" in out.splitlines()[-1], out


def test_unmutated_copy_is_green():
    with tempfile.TemporaryDirectory(prefix="recall-eval-copy-") as tmp:
        copy_scripts(tmp)
        code, out = run_runner("--scripts-dir", tmp, "--strict-gaps")
    assert code == 0, out


def test_fixture_is_self_contained_and_covers_every_note_kind():
    with tempfile.TemporaryDirectory(prefix="recall-eval-fx-") as root:
        config = FIXTURE.build(root, bulk=5)
        data = json.load(open(config, encoding="utf-8"))  # pylint: disable=consider-using-with
        paths = [v["path"] for v in data["vaults"].values()]
        assert all(os.path.commonpath([p, root]) == root for p in paths), paths
        names = [os.path.relpath(os.path.join(d, f), paths[0]).replace(os.sep, "/")
                 for d, _, files in os.walk(paths[0]) for f in files]
        for needed in ("wiki/concepts/", "wiki/decisions/", "wiki/sessions/archive/", "daily/",
                       "wiki/sessions/bulk/"):
            assert any(n.startswith(needed) for n in names), needed
        text = open(os.path.join(paths[0], "wiki/concepts/Recall file triggers.md"),  # pylint: disable=consider-using-with
                    encoding="utf-8").read()
        assert "files:" in text and "[[" in "".join(FIXTURE.main_notes().values())
        big = os.path.join(paths[0], "wiki/concepts/Enormous log.md")
        assert os.path.getsize(big) > 256 * 1024


def test_metric_arithmetic():
    case = {"expect": ["a:1", "a:2"], "also_ok": ["a:3"], "reject": ["a:9"], "k": 3,
            "order": [["a:2", "a:1"]], "expect_held": 1}
    res = {"results": [{"vault": "a", "path": p, "snippet": "x"} for p in ("3", "1", "9", "2")],
           "truncated": True}
    full = {"results": res["results"] + [{"vault": "a", "path": "7", "snippet": "x"}]}
    out = EVAL.metrics_for(case, res, full)
    assert out["recall_k"] == 0.5          # only a:1 is in the top 3
    assert abs(out["precision_k"] - 2 / 3) < 1e-9   # a:3 and a:1 of a:3, a:1, a:9
    assert out["rr"] == 0.5                # first expected note is at rank 2
    assert out["rejected"] == ["a:9"]
    assert out["order_bad"], "a:2 is below a:1, the pair must be reported"
    assert out["held"] == 1 and out["truncated"] is True
    assert any("recall@3" in r for r in out["reasons"])


def test_thresholds_turn_a_miss_into_exit_1_and_setup_errors_into_2():
    with tempfile.TemporaryDirectory(prefix="recall-eval-gold-") as tmp:
        gold = os.path.join(tmp, "golden.json")
        impossible = {"cases": [{"id": "never", "query": "port collision bridge",
                                 "projects": ["crew"],
                                 "expect": ["main:wiki/does/not/exist.md"]}]}
        with open(gold, "w", encoding="utf-8") as fh:
            json.dump(impossible, fh)
        code, out = run_runner("--golden", gold)
        assert code == 1 and "recall@k 0.000 < 1.0" in out, out
        code, out = run_runner("--golden", gold, "--min-recall", "0", "--min-mrr", "0",
                               "--min-precision", "0")
        assert code == 1 and "gated case(s) failed" in out, out   # the case itself still fails
        code, out = run_runner("--golden", os.path.join(tmp, "missing.json"))
        assert code == 2 and "setup error" in out, out


def test_gate_flags_deadline_and_p95():
    args = EVAL.parser().parse_args(["--max-p95-ms", "100", "--fail-on-deadline"])
    agg = {"recall_at_k": 1.0, "precision_at_k": 1.0, "mrr": 1.0, "rejected": 0,
           "gated_failed": 0, "gaps_closed": []}
    fine = {"p95_ms": 50.0, "deadline_hits": 0, "samples": 30}
    assert EVAL.gate(agg, fine, args) == []
    slow = {"p95_ms": 900.0, "deadline_hits": 2, "samples": 30}
    failures = EVAL.gate(agg, slow, args)
    assert any("p95" in f for f in failures) and any("deadline" in f for f in failures)
    closed = dict(agg, gaps_closed=["files-keyed-recall"])
    assert EVAL.gate(closed, None, EVAL.parser().parse_args(["--strict-gaps"]))


def test_latency_block_reports_the_numbers_a_baseline_needs():
    with tempfile.TemporaryDirectory(prefix="recall-eval-lat-") as root:
        config = FIXTURE.build(root)
        block = EVAL.latency(PLUGIN_SCRIPTS, config, 1)
    for key in ("p50_ms", "p95_ms", "max_ms", "interpreter_start_p50_ms",
                "p50_over_interpreter_start", "deadline_hits", "deadline_ms", "samples"):
        assert key in block, key
    assert block["samples"] == 3 and block["deadline_hits"] == 0   # 3 queries x 1 run, 8 ms walk


def test_a_one_ms_deadline_over_bulk_notes_is_seen_as_truncated():
    with tempfile.TemporaryDirectory(prefix="recall-eval-dl-") as root:
        os.environ["OBSIDIAN_VAULT_CONFIG"] = FIXTURE.build(root, bulk=300)
        sys.path.insert(0, PLUGIN_SCRIPTS)
        vr = EVAL.load_recall(PLUGIN_SCRIPTS)
        probe = EVAL.deadline_probe(vr, 300)
    assert probe["truncated"] is True, probe


# ---- must-block: sabotage ------------------------------------------------------------

def test_sabotage_ranker_ascending_score():
    code, out = sabotaged_run('KIND_RANK[h["kind"]], -h["score"],',
                              'KIND_RANK[h["kind"]], h["score"],')
    assert code == 1 and "hook-spawn-cost" in out and "recall@3" in out, out


def test_sabotage_truncation_counter():
    code, out = sabotaged_run("        if len(line) > room:\n            truncated = True\n",
                              "        if len(line) > room:\n            pass\n")
    assert code == 1 and "truncated=False want True" in out, out


def test_sabotage_archive_exclusion():
    code, out = sabotaged_run("else (ARCHIVE_PREFIX,)", "else ()")
    assert code == 1 and "rejected returned" in out and "archive" in out, out


def test_sabotage_project_rank_reversed():
    code, out = sabotaged_run('PROJECT_RANK = {"match": 0, "none": 1, "other": 2}',
                              'PROJECT_RANK = {"match": 2, "none": 1, "other": 0}')
    assert code == 1 and "order" in out and "project-match-first" in out, out


def main():
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {str(exc)[:600]}")
    print(f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
