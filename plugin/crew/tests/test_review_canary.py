"""The canary: one whole review, end to end, answered the way a real reviewer answers.

Each test builds a throwaway repository with a change and a ticket, then runs
the pipeline exactly as `commands/review.md` step 2 does -- `review_patch.py`
into several parts, `review_prompt.py` for the contract, `prompt.txt` as a
header plus that contract, `review_run.py --provider codex` -- with the stub
reviewer on PATH in mode `golden`. That mode replays a REAL `codex exec --json`
stream from the golden corpus (raw U+2028, several agent messages, real
command events) and swaps only its final agent message for READ lines naming
this bundle's parts (full paths or bare names) followed by a real reviewer's
finding lines.

The unit tests on each side of a seam pass on each side's own idea of the
format; this is the one test that runs every producer into every consumer at
once. T-0079 (full-path READ lines read as INCOMPLETE) would have failed here
(T-0087).
"""
import json
import os
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_status
import review_ledger
import review_run
from review_fixtures import NO_BACKOFF, env_with_path, fake_reviewer_bin, git, init_repo

SCRIPTS = os.path.dirname(os.path.abspath(review_run.__file__))
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "review",
                      "uca-t0072--T-0072-build--2BJpY8")
STREAM = os.path.join(GOLDEN, "events.jsonl")
GOLDEN_OUT = os.path.join(GOLDEN, "out.txt")
HEADER = ("Review the change read as the parts listed below, as a hostile QA engineer.\n"
          "Output nothing but the READ lines and the finding lines.\n\n")


def _script(name):
    return os.path.join(SCRIPTS, name)


def _repo(tmp_path):
    repo = init_repo(tmp_path / "repo")
    ticket = repo / ".work" / "tickets" / "T1"
    ticket.mkdir(parents=True)
    (ticket / "spec.md").write_text(
        "# T1 spec    status: approved\n\n## Intent\nAdd a greeting module.\n\n"
        "## Acceptance checks\n- `greet()` returns a greeting.\n", encoding="utf-8")
    (ticket / "plan.md").write_text(
        "# T1 plan\n\n### Step 1: greet\nFiles: greet.py\n", encoding="utf-8")
    for n in range(4):
        (repo / f"module_{n}.py").write_text(
            "".join(f"def greet_{n}_{i}():\n    return 'hello {i}'\n\n" for i in range(12)),
            encoding="utf-8")
    return repo


def _bundle(repo, scratch, pad=0):
    """review.md step 2's bundle, contract and prompt; the parsed manifest."""
    scratch.mkdir(parents=True, exist_ok=True)
    manifest = scratch / "manifest.json"
    subprocess.run([sys.executable, _script("review_patch.py"), "--root", str(repo),
                    "--base", git(repo, "rev-parse", "HEAD"), "--out", str(scratch / "diff.txt"),
                    "--manifest", str(manifest), "--max-part-bytes", "200"],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    subprocess.run([sys.executable, _script("review_prompt.py"), "--root", str(repo),
                    "--ticket", "T1", "--manifest", str(manifest),
                    "--out", str(scratch / "contract.txt")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    contract = (scratch / "contract.txt").read_text(encoding="utf-8")
    (scratch / "prompt.txt").write_text(HEADER + contract + "\n" + "#" * pad, encoding="utf-8")
    return json.loads(manifest.read_text(encoding="utf-8"))


def _review(tmp_path, mode="golden", read_form="full", out=GOLDEN_OUT, pad=0):
    repo = _repo(tmp_path)
    scratch = tmp_path / "scratch"
    manifest = _bundle(repo, scratch, pad)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    result = subprocess.run(
        NO_BACKOFF + ["--root", str(repo), "--ticket", "T1",
                      "--scratch", str(scratch), "--provider", "codex"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120,
        env=env_with_path(fakes, FAKE_REVIEWER_MODE=mode, FAKE_REVIEWER_GOLDEN_STREAM=STREAM,
                          FAKE_REVIEWER_GOLDEN_OUT=str(out),
                          FAKE_REVIEWER_READ_FORM=read_form))
    review_path = repo / ".work" / "tickets" / "T1" / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    return repo, scratch, manifest, result, review


def _expected():
    with open(os.path.join(GOLDEN, "expected.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_canary_full_path_reads_and_golden_findings_are_findings(tmp_path):
    _, scratch, manifest, result, review = _review(tmp_path)

    assert len(manifest["parts"]) > 1, manifest["parts"]
    assert result.returncode == 1, result.stdout + result.stderr
    assert (review["counts"], review["parts_missing"]) == (_expected()["counts"], [])
    events = (scratch / "codex-events.jsonl").read_text(encoding="utf-8")
    assert " " in events
    assert events.count('"type": "agent_message"') + events.count('"type":"agent_message"') > 1


def test_canary_bare_name_reads_and_clean_writes_a_receipt_that_checks(tmp_path):
    clean = tmp_path / "clean.txt"
    clean.write_text("CLEAN\n", encoding="utf-8")

    repo, _, _, result, review = _review(tmp_path, read_form="bare", out=clean)

    assert result.returncode == 0, result.stdout + result.stderr
    assert review["verdict"] == "CLEAN"
    assert review_ledger.check_receipt(str(repo), "T1")[0] is True


def test_canary_over_limit_prompt_is_read_from_its_file(tmp_path):
    _, scratch, _, result, review = _review(tmp_path, pad=review_run.INLINE_PROMPT_LIMIT)

    assert len((scratch / "prompt.txt").read_text(encoding="utf-8")) > \
        review_run.INLINE_PROMPT_LIMIT
    assert "over the inline limit" in result.stderr
    assert result.returncode == 1, result.stdout + result.stderr
    assert (review["counts"], review["parts_missing"]) == (_expected()["counts"], [])


def test_canary_turn_failed_is_a_refunded_tool_failure(tmp_path):
    """The failed turn is refunded and retried once (L-0514); the retry
    fails the same way and is refunded too."""
    repo, _, _, result, review = _review(tmp_path, mode="turnfail")

    assert result.returncode == 3, result.stdout + result.stderr
    assert (review["failure_class"], review["refunded"]) == ("tool", True)
    assert any("2 refunded" in line for line in crew_status._review_lines(str(repo)))  # pylint: disable=protected-access
