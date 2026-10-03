"""One definition per review-format seam, and a producer-to-consumer test for each.

A contract test that feeds a consumer its own idea of the format is the defect
it replaces: T-0079's READ-line parser passed its tests against hand-written
bare names while every real reviewer wrote the full paths the prompt listed.
So each test here builds the PRODUCER's real output and hands it to the real
CONSUMER (T-0087).
"""
import ast
import glob
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_resume
import crew_status
import crew_ticket
import review_checks
import review_ledger
import review_patch
import review_prompt
import review_run
import review_verdict
import verify_record
from review_fixtures import git, init_repo

CREW = context._ROOT  # pylint: disable=protected-access
REPO = os.path.dirname(os.path.dirname(CREW))
GOLDEN = os.path.join(CREW, "tests", "golden", "review")


class Recording(dict):
    """A dict that logs every key a consumer reads from it."""
    log = None

    def _note(self, key):
        if Recording.log is not None:
            Recording.log.append((id(self), key))

    def __getitem__(self, key):
        self._note(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._note(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._note(key)
        return super().__contains__(key)


def _keys(log, obj):
    return {key for ident, key in log if ident == id(obj)}


def _recorded(manifest):
    rec = Recording(manifest)
    rec["parts"] = [Recording(p) for p in manifest["parts"]]
    return rec


@pytest.fixture(name="bundled")
def _bundled(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    base = git(repo, "rev-parse", "HEAD")
    manifest, _ = review_patch.build(str(repo), base, str(scratch / "diff.txt"),
                                     str(scratch / "manifest.json"))
    return repo, scratch, manifest


def test_manifest_consumers_read_only_keys_the_producer_writes(bundled, monkeypatch):
    repo, scratch, manifest = bundled
    allowed = set(review_patch.MANIFEST_KEYS) | set(review_patch.OPTIONAL_MANIFEST_KEYS)
    assert set(manifest) == set(review_patch.MANIFEST_KEYS)
    assert all(set(p) == set(review_patch.PART_KEYS) for p in manifest["parts"])

    Recording.log = []
    rec = _recorded(manifest)
    review_prompt.build(str(repo), "T1", rec)
    prompt_top, prompt_parts = _keys(Recording.log, rec), set().union(
        *(_keys(Recording.log, p) for p in rec["parts"]))

    Recording.log, parsed = [], []

    def loads(text, **kw):
        parsed.append(json.loads(text, object_hook=Recording, **kw))
        return parsed[-1]

    monkeypatch.setattr(review_run, "json", types.SimpleNamespace(loads=loads, dumps=json.dumps))
    assert review_ledger.reserve(str(repo), "T1", "codex")[0]
    out = "\n".join("READ|" + p["path"] for p in manifest["parts"]) + "\nCLEAN\n"
    args = types.SimpleNamespace(manifest=str(scratch / "manifest.json"), scratch=str(scratch),
                                 root=str(repo), ticket="T1", provider="codex", model="",
                                 work_dir=str(scratch / "work"))
    code = review_run.finish(args, 1, out, 0, False)
    run_top = _keys(Recording.log, parsed[0])
    run_parts = set().union(*(_keys(Recording.log, p) for p in parsed[0]["parts"]))
    Recording.log = None

    assert code == review_run.EXIT_CLEAN
    assert prompt_top and run_top and prompt_parts and run_parts
    assert (prompt_top | run_top) <= allowed, (prompt_top | run_top) - allowed
    assert (prompt_parts | run_parts) <= set(review_patch.PART_KEYS)


def _read(*parts):
    with open(os.path.join(CREW, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_reviewer_agent_states_the_read_form_the_parser_accepts():
    assert review_verdict.READ_FORM in _read("agents", "reviewer.md")


@pytest.mark.parametrize("doc", [
    ("commands", "review.md"),
    ("agents", "reviewer.md"),
    ("evals", "qa-reviewer-stays-read-only", "prompt.md"),
])
def test_every_prose_statement_of_the_finding_line_is_the_parsers(doc):
    assert review_verdict.FINDING_FORM in _read(*doc)


def _grader():
    text = _read("evals", "qa-reviewer-stays-read-only", "graders", "verdict-format.md")
    front = text.split("---")[1]
    raw = re.search(r"^pattern:\s*'(.*)'\s*$", front, re.M).group(1)
    return re.compile(raw)


def _golden_finding_lines():
    lines = []
    for out in sorted(glob.glob(os.path.join(GOLDEN, "*", "out.txt"))):
        with open(out, encoding="utf-8", newline="") as fh:
            for raw in fh.read().split("\n"):
                line = raw.strip()
                if line.split("|", 1)[0] in review_verdict.SEVERITIES:
                    lines.append(line)
    return lines


# The grader deliberately refuses `|` inside a field (its own body); the parser
# lets the last field carry one. Real reviewers wrote this many such lines in the
# committed corpus -- a known gap, recorded, not "fixed" (spec Exclusions).
GRADER_REFUSED_GOLDEN_LINES = 9


def test_every_grader_accepted_line_parses_as_a_finding():
    grader = _grader()
    synthetic = ["FIX|a.py:1|x|y", "BLOCK|a/b.py:12|breaks|run it", "NIT|c.md:3|typo|read it"]
    for line in synthetic:
        assert grader.match(line) and review_verdict._FINDING.match(line), line  # pylint: disable=protected-access
    golden = _golden_finding_lines()
    if not golden:
        pytest.skip("no golden corpus yet (plugin/crew/tests/golden/review is empty)")
    refused = [line for line in golden if not grader.match(line)]
    for line in golden:
        if grader.match(line):
            assert review_verdict._FINDING.match(line), line  # pylint: disable=protected-access
    assert len(refused) == GRADER_REFUSED_GOLDEN_LINES, refused


def _review(verdict, failure_class=None):
    return {"verdict": verdict, "counts": {"BLOCK": 0, "FIX": 1, "NIT": 0},
            "bundle_sha256": "b" * 64, "base": "c" * 40, "head": "c" * 40,
            "model_family": "gpt", "provider": "codex", "model": None,
            "failure_class": failure_class}


def _record(root, ticket, verdict, failure_class=None):
    ok, number, message = review_ledger.reserve(str(root), ticket, "codex")
    assert ok, message
    review_ledger.record(str(root), ticket, number, _review(verdict, failure_class))


def test_ledger_writes_only_verdicts_the_parser_defines(tmp_path):
    repo = init_repo(tmp_path / "r")
    for ticket, verdict in (("T1", "CLEAN"), ("T2", "FINDINGS"), ("T3", "INCOMPLETE")):
        _record(repo, ticket, verdict, "tool" if verdict == "INCOMPLETE" else None)

    rows = [r for t in ("T1", "T2", "T3") for r in review_ledger.status(str(repo), t)["rounds"]]

    assert {r["verdict"] for r in rows} <= set(review_verdict.VERDICTS)
    assert {r["status"] for r in rows} <= {"reserved", "completed"}


@pytest.mark.parametrize("verdict, failure, phase, stop", [
    ("FINDINGS", None, "accept-review", True),
    ("INCOMPLETE", "tool", "review", False),
    ("INCOMPLETE", "reviewer", "accept-review", True),
])
def test_autopilot_reads_a_ledger_the_real_api_wrote(tmp_path, monkeypatch, verdict, failure,
                                                     phase, stop):
    repo = init_repo(tmp_path / "r")
    _record(repo, "T1", verdict, failure)
    monkeypatch.setattr(review_ledger, "check_receipt", lambda root, ticket: (False, "no receipt"))
    monkeypatch.setattr(crew_autopilot, "_refresh_state", lambda root, ticket: {
        "state": crew_autopilot.FRESH, "command": "", "reason": ""})
    # T-0022's docs phase precedes the refresh; this test is about the ledger.
    monkeypatch.setattr(crew_autopilot, "_docs_state", lambda root, ticket: {
        "state": crew_autopilot.DOCS_OK, "missing": [], "reason": ""})

    def answer(phase, stop, reason, command=""):
        return {"phase": phase, "stop": stop, "reason": reason, "command": command}

    got = crew_autopilot._review_phase(str(repo), "T1", [], answer)  # pylint: disable=protected-access

    assert (got["phase"], got["stop"]) == (phase, stop), got


_RECORDS = [
    (None, "absent", "MISSING", "verify   no gate record yet"),
    ("{not json", "corrupt", "UNREADABLE", "verify   UNKNOWN (gate record unreadable)"),
    (json.dumps({"rules": []}), "corrupt", "UNREADABLE",
     "verify   UNKNOWN (gate record unreadable)"),
    (json.dumps({"rules": {}}), "ok", "Per-rule record: no rule is outstanding",
     "verify   no rules recorded"),
    (json.dumps({"rules": {"k": {"label": "rules[3]", "reason": "SKIP", "status": "skipped"}}}),
     "ok", "NOT VERIFIED: rules[3]: SKIP", "verify   1 skipped"),
]


@pytest.mark.parametrize("raw, state, prompt_line, status_line", _RECORDS,
                         ids=["absent", "corrupt", "rules-list", "empty", "one-skip"])
def test_gate_record_consumers_share_one_reader(tmp_path, raw, state, prompt_line, status_line):
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    if raw is not None:
        (root / ".crew" / ".verify-gate.record.json").write_text(raw, encoding="utf-8")

    assert verify_record.read_record(str(root))[0] == state
    assert review_prompt._receipts_block(str(root), {})[-1].startswith(prompt_line)  # pylint: disable=protected-access
    assert crew_status._verify_line(str(root)) == status_line  # pylint: disable=protected-access


def _code_strings(path):
    """Every string constant in a module's code, docstrings excluded."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
            and isinstance(n.value, str) and id(n) not in docstrings]


@pytest.mark.parametrize("module", [review_prompt, crew_status])
def test_gate_record_path_is_named_only_by_its_producer(module):
    assert not [s for s in _code_strings(module.__file__) if ".verify-gate.record.json" in s]


class _Stdout:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kw):
        self.calls.append(kw)

    def write(self, text):
        return len(text)

    def flush(self):
        pass


def test_importing_verify_record_leaves_stdout_alone(tmp_path, monkeypatch):
    fake = _Stdout()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.chdir(tmp_path)

    importlib.reload(verify_record)
    on_import = list(fake.calls)
    verify_record.main(["verify_record.py", "report"])

    assert (on_import, fake.calls) == ([], [{"newline": "\n"}])


def test_status_review_lines_come_from_the_ledger_summary(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "r")
    _record(repo, "T1", "FINDINGS")
    monkeypatch.setattr(review_ledger, "summary", lambda data, state, ticket, path: {
        "state": "SENTINEL", "rounds_spent": 7, "budget": 9, "rounds_refunded": 5})

    lines = crew_status._review_lines(str(repo))  # pylint: disable=protected-access

    assert lines == ["review   T1: SENTINEL, 7/9 rounds used, 5 refunded"]


def test_resume_fingerprint_watches_the_paths_the_producers_write(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / ".work" / "tickets" / "T1").mkdir(parents=True)
    (repo / ".work" / "tickets" / "T1" / "spec.md").write_text("# T1\n", encoding="utf-8")
    seen = [crew_resume.progress_fingerprint(str(repo), "T1")]
    for path in (crew_ticket.approval_path(str(repo), "T1"),
                 review_ledger.ledger_path(str(repo), "T1")):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{}")
        seen.append(crew_resume.progress_fingerprint(str(repo), "T1"))

    assert None not in seen and len(set(seen)) == 3, seen



# The suites the harness rule must both run and trigger on: the five T-0087
# suites and test_status.py, the one that exercises crew_status's ledger line.
HARNESS_SUITES = (
    "scripts/_test/tooling-pr.py",
    "plugin/crew/tests/test_review_golden.py",
    "plugin/crew/tests/test_review_contracts.py",
    "plugin/crew/tests/test_review_canary.py",
    "plugin/crew/tests/test_review_refund.py",
    "plugin/crew/tests/test_external_tool_formats.py",
    "plugin/crew/tests/test_status.py",
    "plugin/crew/tests/test_review_metrics.py",
)


def _harness_rule():
    verify = os.path.join(REPO, ".crew", "verify.json")
    checker_path = os.path.join(REPO, "scripts", "check-tooling-pr.py")
    if not (os.path.isfile(verify) and os.path.isfile(checker_path)):
        pytest.skip("the crew dir is not inside the marketplace repo (an installed copy): "
                    "no .crew/verify.json or scripts/check-tooling-pr.py beside it")
    with open(verify, encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]
    spec = importlib.util.spec_from_file_location("check_tooling_pr", checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    matching = [r for r in rules if any("scripts/check-tooling-pr.py" in c for c in r["run"])]
    assert len(matching) == 1, [r["paths"] for r in matching]
    return matching[0], checker


def test_verify_rule_paths_cover_the_harness_its_seams_and_suites():
    rule, checker = _harness_rule()
    run = set(re.findall(r"[\w./-]+\.py", " ".join(rule["run"])))

    assert (set(HARNESS_SUITES) - run, set(rule["paths"])) == (set(), set(
        checker.HARNESS + checker.SEAM + HARNESS_SUITES
        + ("plugin/crew/docs/external-tool-formats.md",)))


def test_tooling_alone_checker_passes_its_must_block_must_allow_suite():
    _harness_rule()
    suite = os.path.join(REPO, "scripts", "_test", "tooling-pr.py")
    done = subprocess.run([sys.executable, suite], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)

    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]


def test_prereview_reads_only_manifest_keys(tmp_path, monkeypatch):
    """L-0574: review_checks reads the manifest review_patch really wrote, and
    only the keys (and entry fields) that producer writes."""
    repo = init_repo(tmp_path / "r")
    (repo / "gone.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "ruff.toml").write_text("[lint]\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "gone.py").unlink()
    (repo / "m.py").write_text("x = 2\n", encoding="utf-8")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text(json.dumps({review_checks.CONFIG_KEY: {"linters": [
        {"tool": "ruff", "command": [sys.executable, "-c", "print('[]')"]}]}}), encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    manifest, _ = review_patch.build(str(repo), base, str(scratch / "diff.txt"),
                                     str(scratch / "manifest.json"))
    produced_entry_keys = set().union(*(set(e) for e in manifest["entries"]))
    seen = []

    # The manifest is read through read_regular and parsed by strict_json
    # (json.loads with a duplicate-key object_pairs_hook, review round 9): the
    # parse of exactly its text is the one recorded, each object still passing
    # through the strict hook before it is wrapped.
    manifest_text = (scratch / "manifest.json").read_text(encoding="utf-8")

    def loads(text, **kw):
        if text != manifest_text or seen:
            return json.loads(text, **kw)
        strict = kw.pop("object_pairs_hook", dict)
        rec = json.loads(text, object_pairs_hook=lambda pairs: Recording(strict(pairs)), **kw)
        seen.append(rec)
        return rec

    monkeypatch.setattr(review_checks, "json", types.SimpleNamespace(
        load=json.load, loads=loads, dumps=json.dumps))
    Recording.log = []
    results, configured = review_checks.run_checks(str(repo), str(scratch / "manifest.json"))
    top = _keys(Recording.log, seen[0])
    entry_keys = set().union(*(_keys(Recording.log, e) for e in seen[0]["entries"]))
    Recording.log = None

    assert (configured, [r["status"] for r in results]) == (True, [review_checks.PASS]), results
    assert top and top <= set(review_patch.MANIFEST_KEYS), top
    assert entry_keys and entry_keys <= produced_entry_keys, entry_keys - produced_entry_keys


def test_the_install_scripts_rule_loads_for_the_install_scripts():
    """Review round 8 FIX .claude/rules/install-scripts.md:3: the rule's paths
    were derived from citation counts, and other tickets' re-anchor notes
    pushed `scripts/` under the 15% floor. The map names its paths, and the
    generated rule carries them."""
    import crew_context  # pylint: disable=import-outside-toplevel
    with open(os.path.join(REPO, ".crew", "codemap", "install-scripts.md"), encoding="utf-8") as fh:
        derived = crew_context.derive_paths(REPO, fh.read())
    with open(os.path.join(REPO, ".claude", "rules", "install-scripts.md"), encoding="utf-8") as fh:
        rule = fh.read().split("\n---\n", 1)[0]

    assert ("scripts/**" in derived, '  - "scripts/**"' in rule) == (True, True), (derived, rule)
