"""promote-gate's sha rule and review evidence (L-0703).

Two guards, both flavours:

1. EXACT SHA. A `requires` row in `.work/PROMOTIONS.md` counts only when its
   sha cell is the deploying commit's full 40-character sha (case ignored).
   Before this ticket `cells[2].startswith(sha[:7])` admitted a PASS row for a
   DIFFERENT commit sharing the first 7 characters, and a short row of any
   length was cut to 7. No back-compat for short rows (spec, "Back-compat
   decision"): accepting one that resolves to the deploying sha re-opens the
   hole whenever the row's own commit is no longer in the object store.

2. REVIEW EVIDENCE. Every gated environment needs an accepted review receipt
   whose reviewed head has the deploying commit's tree and which
   `review_ledger.check_receipt`, run in the deploying tree, says stands -
   `requireHuman` or not - unless it sets `requireReview: false` with a
   `reviewReason` string. Decided by `_promote_review.py`, which both
   flavours call; a helper that cannot run, runs out of the gate's deadline
   or cannot decide blocks.

A guard that can BLOCK carries must-block AND must-allow cases (repo
CLAUDE.md). The ledgers are written through `review_ledger`'s own reserve /
record / accept / reject with bundle hashes from `review_patch.compute`, so a
must-allow case is a receipt crew itself would mint. Every repository is
built under tmp_path; `CLAUDE_PROJECT_DIR` names it, never this repo.

The pwsh flavour runs wherever PowerShell 7 resolves, with `OS=Windows_NT` in
the child only (see test_promote_gate_effective_tree.py). Native Windows is
not exercised here.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import review_ledger  # pylint: disable=wrong-import-order
import review_patch  # pylint: disable=wrong-import-order

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_SH = _SCRIPTS / "promote-gate.sh"
_PS1 = _SCRIPTS / "promote-gate.ps1"
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
_GIT = shutil.which("git")

_NEEDS_PWSH = pytest.mark.skipif(_PWSH is None, reason="no PowerShell 7 on this machine")
FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")),
    pytest.param("ps1", marks=[_NEEDS_PWSH, pytest.mark.slow]),
]
# Every default-set ps1 case is `wallclock`, and so are the two ps1-only tests
# below (test_ps1_refuses_a_map_that_is_not_a_regular_file,
# test_ps1_without_python_blocks_a_declared_deploy): promote-gate.ps1 holds a
# 16s deadline from process start (it has to fit the 20s hook timeout, L-0703),
# and under CI's `-n 16` on a 4-vCPU hosted runner PowerShell start-up alone
# spent it, so admit cases read "the gate's deadline passed" (run 38033960181,
# test (3.11) and test (3.13)). They run in the serial wallclock step instead.
# FLAVOURS' ps1 is `slow`, which `-m wallclock` never selects (conftest), so
# it stays in the slow job.
FLAVOURS_DEFAULT = [FLAVOURS[0], pytest.param("ps1", marks=[_NEEDS_PWSH, pytest.mark.wallclock])]
_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="PATH shims are POSIX scripts")

_ROLLBACK = {"rollback": "none", "rollbackReason": "fixture"}
_OPT_OUT = {"requireReview": False, "reviewReason": "fixture: the sha rule alone"}

# The review tests: development and prod need review (the default).
REVIEW_MAP = {"environments": {
    "development": {"deploy": "deploy-dev", **_ROLLBACK},
    "prod": {"deploy": "deploy-prod", "requireHuman": True, **_ROLLBACK},
}}
# The sha tests: review opted out, so only the `requires` row decides.
SHA_MAP = {"environments": {
    "development": {"deploy": "deploy-dev", **_ROLLBACK, **_OPT_OUT},
    "qa": {"deploy": "deploy-qa", "requires": ["development"], **_ROLLBACK, **_OPT_OUT},
}}


def _git(cwd, *args):
    return subprocess.run((_GIT,) + args, cwd=cwd, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


class Repo:
    """One checkout on `main`: a base commit B, then the ticket's commit H."""

    def __init__(self, tmp_path, verify, extra=None, base_extra=None,
                 ignore=".crew/*\n!.crew/verify.json\n.work/\n"):
        self.root = tmp_path / "main"
        self.root.mkdir(parents=True)
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "t@example.invalid")
        _git(self.root, "config", "user.name", "T")
        _git(self.root, "config", "commit.gpgsign", "false")
        (self.root / ".gitignore").write_text(ignore, encoding="utf-8")
        (self.root / ".crew").mkdir()
        (self.root / ".work").mkdir()
        self.write_map(verify)
        (self.root / "app.txt").write_text("v1\n", encoding="utf-8")
        for rel, body in (base_extra or {}).items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base")
        self.base = _git(self.root, "rev-parse", "HEAD")
        (self.root / "app.txt").write_text("v2\n", encoding="utf-8")
        for rel, body in (extra or {}).items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "ticket")

    def write_map(self, verify):
        (self.root / ".crew" / "verify.json").write_text(json.dumps(verify, indent=2) + "\n",
                                                         encoding="utf-8")

    def commit_map(self, verify):
        self.write_map(verify)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "map")

    @property
    def head(self):
        return _git(self.root, "rev-parse", "HEAD")

    @property
    def short(self):
        return _git(self.root, "rev-parse", "--short", "HEAD")

    def commit(self, rel="app.txt", body=None, empty=False):
        if empty:
            _git(self.root, "commit", "-q", "--allow-empty", "-m", "empty")
            return
        (self.root / rel).write_text(body or f"{time.time()}\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "more")

    def promotions(self, *rows):
        body = ["| when | env | sha | smoke | regression | verify | by |",
                "|---|---|---|---|---|---|---|"]
        body += [f"| 2026-10-06 | {env} | {sha} | {res} | {res} | {res} | t |"
                 for env, sha, res in rows]
        (self.root / ".work" / "PROMOTIONS.md").write_text("\n".join(body) + "\n",
                                                           encoding="utf-8")

    def in_flight(self):
        path = self.root / ".crew" / ".deploy-in-flight"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    # --- ledgers, written through review_ledger itself -------------------

    def _round(self, ticket, verdict, counts, findings=None):
        root = str(self.root)
        manifest = review_patch.compute(root, self.base)[0]
        ok, number, msg = review_ledger.reserve(root, ticket, "codex", "m")
        assert ok, msg
        review = {"verdict": verdict, "bundle_sha256": manifest["bundle_sha256"],
                  "base": self.base, "head": manifest["head"], "provider": "codex",
                  "model": "m", "model_family": "gpt", "counts": counts}
        if findings is not None:
            review["findings"] = findings
        review_ledger.record(root, ticket, number, review)
        return manifest

    def clean_receipt(self, ticket="T-0001"):
        return self._round(ticket, "CLEAN", {"BLOCK": 0, "FIX": 0, "NIT": 0})

    def findings_round(self, ticket="T-0001"):
        return self._round(ticket, "FINDINGS", {"BLOCK": 0, "FIX": 1, "NIT": 0},
                           ["FIX|app.txt|fixture"])

    def ledger(self, ticket="T-0001"):
        return pathlib.Path(review_ledger.ledger_path(str(self.root), ticket))


def run_gate(flavour, repo, command, env=None, scripts=None, path=None, timeout=60):
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}, "cwd": str(repo.root)}
    child = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo.root))
    child.pop(_BUDGET, None)
    child.update(env or {})
    if path is not None:
        child["PATH"] = path
    where = pathlib.Path(scripts) if scripts else _SCRIPTS
    if flavour == "sh":
        argv = [_BASH, (where / "promote-gate.sh").as_posix()]
    else:
        child["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(where / "promote-gate.ps1")]
    start = time.monotonic()
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          check=False, env=child, cwd=str(repo.root), timeout=timeout)
    return proc.returncode, proc.stderr, time.monotonic() - start


_BUDGET = "CREW_PROMOTE_REVIEW_BUDGET"


def _fake_other_sha(full):
    """A different 40-hex sha sharing `full`'s first 7 characters."""
    tail = "".join("0123456789abcdef"[(int(c, 16) + 1) % 16] for c in full[7:])
    return full[:7] + tail


# =============================================================================
# 1. exact sha
# =============================================================================

@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_pass_row_for_a_same_prefix_different_sha_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    other = _fake_other_sha(repo.head)
    assert other != repo.head and other[:7] == repo.head[:7]
    repo.promotions(("development", other, "pass"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 2, err
    assert "no all-pass row" in err and repo.head in err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("length", [1, 6, 7, 12, 39])
def test_a_short_row_for_the_deploying_sha_is_refused(flavour, length, tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    repo.promotions(("development", repo.head[:length], "pass"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 2, err
    assert f"records the short sha {repo.head[:length]}" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_row_for_another_sha_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    repo.promotions(("development", repo.base, "pass"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 2, err


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
@pytest.mark.parametrize("upper", [False, True])
def test_a_full_sha_row_admits(flavour, upper, tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    repo.promotions(("development", repo.head.upper() if upper else repo.head, "pass"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 0, err
    assert repo.in_flight() == f"qa {repo.short}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_prefix_pass_row_does_not_rescue_a_failing_full_row(flavour, tmp_path):
    """Holds under first-row and newest-row selection (L-0665)."""
    repo = Repo(tmp_path, SHA_MAP)
    repo.promotions(("development", repo.head[:7], "pass"), ("development", repo.head, "fail"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 2, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_prefix_fail_row_does_not_shadow_a_passing_full_row(flavour, tmp_path):
    """Holds under first-row and newest-row selection (L-0665)."""
    repo = Repo(tmp_path, SHA_MAP)
    repo.promotions(("development", repo.head[:7], "fail"), ("development", repo.head, "pass"))
    code, err, _ = run_gate(flavour, repo, "deploy-qa")
    assert code == 0, err


# =============================================================================
# 2. review evidence: must-block
# =============================================================================

def _blocked_for_review(code, err):
    assert code == 2, err
    assert "requires an accepted review" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_no_ledger_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)
    assert "no review ledger" in err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_reviewed_not_accepted_ledger_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.findings_round()
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_needs_replan_ledger_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.findings_round()
    review_ledger.reject(str(repo.root), "T-0001", "owner")
    assert review_ledger.status(str(repo.root), "T-0001")["state"] == review_ledger.NEEDS_REPLAN
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_receipt_for_another_tree_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    repo.commit(body="unreviewed\n")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)
    assert "tree identical" in err


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_change_the_bundle_cannot_see_is_still_a_different_tree(flavour, tmp_path):
    """The tree-identity rule's own case. graphify-out/graph.json is left out
    of the review bundle and is check E's one allowed modification, so
    `check_receipt` alone still says the receipt stands after it changes -
    but the bytes deployed are not the bytes reviewed."""
    repo = Repo(tmp_path, REVIEW_MAP, base_extra={"graphify-out/graph.json": "{}\n"})
    repo.clean_receipt()
    repo.commit("graphify-out/graph.json", '{"changed": "after review"}\n')
    assert review_ledger.check_receipt(str(repo.root), "T-0001")[0], \
        "the receipt check alone must keep this receipt, or the case proves nothing"
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)
    assert "tree identical" in err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_receipt_superseded_by_a_new_round_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    ok, _, msg = review_ledger.reserve(str(repo.root), "T-0001", "codex", "m")
    assert ok, msg
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_receipt_whose_bundle_no_longer_matches_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    data = json.loads(repo.ledger().read_text(encoding="utf-8"))
    data["receipt"]["bundle_sha256"] = "0" * 64
    data["rounds"][-1]["bundle_sha256"] = "0" * 64
    repo.ledger().write_text(json.dumps(data), encoding="utf-8")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)
    assert "do not stand" in err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_dirty_tree_review_is_refused(flavour, tmp_path):
    """The round read an uncommitted edit; the commit deployed does not hold it."""
    repo = Repo(tmp_path, REVIEW_MAP)
    (repo.root / "app.txt").write_text("v2 plus an edit nobody committed\n", encoding="utf-8")
    repo.clean_receipt()
    _git(repo.root, "checkout", "--", "app.txt")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_excluded_path_change_is_refused(flavour, tmp_path):
    """Check E: graphify-out/ is left out of the bundle, so a file added
    there in the reviewed range was never shown."""
    repo = Repo(tmp_path, REVIEW_MAP, extra={"graphify-out/unseen.txt": "never reviewed\n"})
    repo.clean_receipt()
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


# L-0739: a repository that tracks `.work/` (TSS's shape: only folders under it ignored).
_TRACKS_WORK = ".crew/*\n!.crew/verify.json\n.work/review/\n.work/PROMOTIONS.md\n"


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_committed_work_text_change_in_the_reviewed_range_is_admitted(flavour, tmp_path):
    """Must-allow: the bundle carried `.work/FINDINGS.md`, so the receipt stands
    and the clean deploy tree passes (REL-69AB9DD7's shape)."""
    repo = Repo(tmp_path, REVIEW_MAP, extra={".work/FINDINGS.md": "- a finding\n"},
                ignore=_TRACKS_WORK)
    assert repo.clean_receipt()["included_excluded"] == [".work/FINDINGS.md"]
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_committed_binary_work_file_in_the_reviewed_range_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP, ignore=_TRACKS_WORK)
    (repo.root / ".work" / "blob.bin").write_bytes(b"\x00\x01binary\x00")
    _git(repo.root, "add", "-A")
    _git(repo.root, "commit", "-q", "-m", "binary")
    repo.clean_receipt()
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)
    assert "outside the bundle" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_auto_accepted_receipt_without_its_review_json_is_refused(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.findings_round()
    data = json.loads(repo.ledger().read_text(encoding="utf-8"))
    row = data["rounds"][-1]
    data["receipt"] = {"kind": review_ledger.AUTO_KIND, "round": row["round"],
                       "bundle_sha256": row["bundle_sha256"], "base": row["base"],
                       "verdict": "FINDINGS", "accepted_by": review_ledger.AUTO_BY,
                       "accepted_at": "2026-10-06T00:00:00+00:00",
                       "findings": row["findings"], "provider": "codex",
                       "model_family": "gpt", "follow_up": "T-0002",
                       "review_json_sha256": "a" * 64, "ignored_lines": 0}
    data["state"] = review_ledger.ACCEPTED
    repo.ledger().write_text(json.dumps(data), encoding="utf-8")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    _blocked_for_review(code, err)


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_require_human_true_still_needs_the_receipt(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    (repo.root / ".crew" / f".approved-prod-{repo.short}").write_text("", encoding="utf-8")
    code, err, _ = run_gate(flavour, repo, "deploy-prod")
    _blocked_for_review(code, err)
    assert "requires explicit human approval" not in err


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("reason", [None, "", "   ", 5, ["x"]])
def test_require_review_false_without_a_reason_string_is_refused(flavour, reason, tmp_path):
    env = {"deploy": "deploy-dev", "requireReview": False, **_ROLLBACK}
    if reason is not None:
        env["reviewReason"] = reason
    repo = Repo(tmp_path, {"environments": {"development": env}})
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 2, err
    assert "no reviewReason string" in err


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("value", ["false", 0, None, {"a": 1}])
def test_require_review_not_a_bool_is_refused(flavour, value, tmp_path):
    env = {"deploy": "deploy-dev", "requireReview": value, "reviewReason": "x", **_ROLLBACK}
    repo = Repo(tmp_path, {"environments": {"development": env}})
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 2, err
    assert "not true or false" in err


def _copy_scripts(tmp_path):
    """A copy of the gate's scripts in the plugin's own layout: the dispatch
    reader (crew 1.2.0) imports crew_config, which loads crew_upgrade from
    ../../skills/crew-graph/scripts, so hooks/scripts alone cannot run."""
    plugin = tmp_path / "plugin"
    scripts = plugin / "hooks" / "scripts"
    skip = shutil.ignore_patterns("_test", "__pycache__")
    shutil.copytree(_SCRIPTS, scripts, ignore=skip)
    graph = pathlib.Path("skills") / "crew-graph" / "scripts"
    shutil.copytree(_SCRIPTS.parents[1] / graph, plugin / graph, ignore=skip)
    return scripts


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_helper_that_cannot_run_blocks(flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    (scripts / "_promote_review.py").unlink()
    repo = Repo(tmp_path, SHA_MAP)
    code, err, _ = run_gate(flavour, repo, "deploy-dev", scripts=scripts)
    assert code == 2, err
    assert "could not be evaluated" in err
    assert repo.in_flight() is None


def _git_shim(tmp_path, hang_on="diff"):
    """A `git` first on PATH that hangs on `hang_on` and records its pid."""
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    pids = tmp_path / "hung.pids"
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do [ "$a" = "{hang_on}" ] && {{ echo $$ >> "{pids}"; '
        "exec sleep 120; }; done\n"
        f'exec "{_GIT}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return shim_dir, pids


def _all_dead(pids_file, within=5.0):
    if not pids_file.exists():
        return True
    pids = [int(p) for p in pids_file.read_text(encoding="utf-8").split()]
    end = time.monotonic() + within
    while time.monotonic() < end:
        if not any(crew_fixtures.pid_alive(p) for p in pids):
            return True
        time.sleep(0.2)
    return False


@_POSIX_ONLY
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_hung_receipt_check_blocks_within_the_hook_timeout(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    shim_dir, pids = _git_shim(tmp_path)
    code, err, took = run_gate(flavour, repo, "deploy-dev", env={_BUDGET: "2"},
                               path=f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    _blocked_for_review(code, err)
    assert "did not finish" in err, err
    assert took < 15, took
    assert pids.exists(), "the shim never hung: the case proves nothing"
    assert _all_dead(pids), "a hung git outlived the gate"


@_POSIX_ONLY
@pytest.mark.slow
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_slow_python_plus_a_hung_check_still_ends_inside_the_hook_timeout(flavour, tmp_path):
    """Default budget: a python that costs 1.8s per start (crew_py's probe and
    every interpreter the gate runs - seven since crew 1.2.0 added the dispatch
    and github readers, about 11.5s before the search starts; 2.5s per start
    spent the whole deadline before the search) plus
    a receipt check that never ends. The gate's own 16s deadline must still
    land it inside the 20s hook; a search that took a fixed 12s from its own
    start would not."""
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    shim_dir, pids = _git_shim(tmp_path)
    real = os.path.realpath(sys.executable)
    for name in ("python3", "python"):
        slow = shim_dir / name
        slow.write_text(f'#!/bin/sh\nsleep 1.8\nexec "{real}" "$@"\n', encoding="utf-8")
        slow.chmod(0o755)
    code, err, took = run_gate(flavour, repo, "deploy-dev",
                               path=f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    assert code == 2, err
    assert took < 20, took
    assert pids.exists(), "the hung git was never reached: the case proves nothing"
    assert _all_dead(pids)


@_POSIX_ONLY
@pytest.mark.slow
def test_a_slow_first_git_probe_counts_against_the_deadline(tmp_path):
    """L-0703 review r1: the deadline is taken before the payload read and the
    map probe, so 8s lost there plus a hung receipt check still end inside
    the 20s hook timeout."""
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    shim_dir, pids = _git_shim(tmp_path)
    once = tmp_path / "slow-once"
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        f'case "$*" in *HEAD:./.crew/verify.json*) [ -e "{once}" ] || {{ : > "{once}"; sleep 8; }} ;; esac\n'
        + shim.read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
    code, err, took = run_gate("sh", repo, "deploy-dev",
                               path=f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    assert code == 2, err
    assert once.exists(), "the slow probe never ran: the case proves nothing"
    assert took < 20, took
    assert _all_dead(pids)


def _path_without_python(tmp_path, with_jq=True):
    """A PATH of symlinks to the tools the gate uses, with no python."""
    bin_dir = tmp_path / "nopy-bin"
    bin_dir.mkdir()
    tools = ["bash", "sh", "cat", "dirname", "git", "grep", "sed", "tr", "mkdir", "rm", "head",
             "tail", "cut", "date", "env", "uname", "basename", "sort", "od", "wc", "printf",
             "readlink", "realpath", "timeout", "sleep"]
    if with_jq:
        tools.append("jq")
    for tool in tools:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    return str(bin_dir)


@_POSIX_ONLY
@pytest.mark.parametrize("with_jq", [True, False])
def test_sh_without_python_blocks_a_declared_deploy(with_jq, tmp_path):
    if with_jq and shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    code, err, _ = run_gate("sh", repo, "deploy-dev --now",
                            path=_path_without_python(tmp_path, with_jq))
    assert code == 2, err
    assert "no usable python" in err, err


@_POSIX_ONLY
def test_sh_without_python_passes_an_unrelated_command(tmp_path):
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    code, err, _ = run_gate("sh", repo, "ls -la", path=_path_without_python(tmp_path))
    assert code == 0, err


@_POSIX_ONLY
def test_sh_without_python_refuses_a_map_with_a_repeated_key(tmp_path):
    """jq keeps only the last of two equal keys, so the first deploy would
    never be scanned; python refuses such a map, and so does the fallback."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    (repo.root / ".crew" / "verify.json").write_text(
        '{"environments": {"development": {"deploy": "ship-it", "deploy": "other", '
        '"rollback": "none", "rollbackReason": "x"}}}\n', encoding="utf-8")
    _git(repo.root, "add", "-A")
    _git(repo.root, "commit", "-q", "-m", "twin keys")
    code, err, _ = run_gate("sh", repo, "ship-it", path=_path_without_python(tmp_path))
    assert code == 2, err
    assert "repeats a key" in err, err


@_POSIX_ONLY
def test_sh_without_python_sees_a_match_after_a_newline_only_value(tmp_path):
    """A value of only newlines matched first and was stripped to nothing by
    $(...), which read as "no match" (L-0703 review r1)."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, {"environments": {"development": {
        "note": "\n", "deploy": "deploy-dev", **_ROLLBACK, **_OPT_OUT}}})
    code, err, _ = run_gate("sh", repo, "x\ndeploy-dev", path=_path_without_python(tmp_path))
    assert code == 2, err


@_POSIX_ONLY
def test_sh_without_python_blocks_when_jq_stalls(tmp_path):
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    bin_dir = pathlib.Path(_path_without_python(tmp_path))
    (bin_dir / "jq").unlink()
    (bin_dir / "jq").write_text("#!/bin/sh\nexec sleep 60\n", encoding="utf-8")
    (bin_dir / "jq").chmod(0o755)
    code, err, took = run_gate("sh", repo, "deploy-dev", path=str(bin_dir))
    assert code == 2, err
    assert took < 20, took


def test_the_helper_ignores_an_uncommitted_opt_out(tmp_path):
    """The gate refuses an uncommitted map, then the helper reads the map
    again: an opt-out written in between must not waive review. Since L-0768
    the helper reads the map COMMITTED in the deployed sha, so the working
    file's opt-out is never read at all."""
    repo = Repo(tmp_path, REVIEW_MAP)
    loose = {"environments": {"development": {"deploy": "deploy-dev", **_ROLLBACK, **_OPT_OUT}}}
    repo.write_map(loose)
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "_promote_review.py"), str(repo.root),
                           repo.head, str(int(time.time()) + 15), "development"],
                          cwd=str(repo.root), capture_output=True, text=True, check=False,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "requires an accepted review" in proc.stdout, proc.stdout


def test_the_fallback_refuses_a_map_that_is_not_the_committed_one(tmp_path):
    """The project-dir fallback (a deployed sha carrying no map) still holds
    the working file to the project dir's HEAD: an opt-out written after the
    gate's check must not waive review."""
    repo = Repo(tmp_path, REVIEW_MAP)
    nomap = _no_map_commit(repo)
    loose = {"environments": {"development": {"deploy": "deploy-dev", **_ROLLBACK, **_OPT_OUT}}}
    repo.write_map(loose)
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "_promote_review.py"), str(repo.root),
                           nomap, str(int(time.time()) + 15), "development"],
                          cwd=str(repo.root), capture_output=True, text=True, check=False,
                          timeout=60)
    assert proc.returncode != 0, proc.stdout
    assert "not the map committed at HEAD" in proc.stderr


def _helper(repo, deadline_in=15, path=None):
    env = dict(os.environ)
    env.pop(_BUDGET, None)
    if path is not None:
        env["PATH"] = path
    start = time.monotonic()
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "_promote_review.py"), str(repo.root),
                           repo.head, str(int(time.time()) + deadline_in), "development"],
                          cwd=str(repo.root), capture_output=True, text=True, check=False,
                          timeout=60, env=env)
    return proc, time.monotonic() - start


def _git_wrapper(tmp_path, body):
    shim_dir = tmp_path / "gitwrap"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(f'#!/bin/sh\n{body}\nexec "{_GIT}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return f"{shim_dir}{os.pathsep}{os.environ['PATH']}"


@_POSIX_ONLY
def test_the_helper_never_reads_a_failed_map_probe_as_no_map(tmp_path):
    """L-0703 review r2: a failing probe of HEAD's map must not pass for "HEAD
    has no map", which would let an uncommitted opt-out waive review."""
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.write_map({"environments": {"development": {"deploy": "deploy-dev", **_ROLLBACK,
                                                     **_OPT_OUT}}})
    path = _git_wrapper(tmp_path, 'case "$*" in *"ls-tree --full-tree"*) exit 128 ;; esac')
    proc, _ = _helper(repo, path=path)
    assert proc.returncode != 0, proc.stdout
    assert "could not list .crew/verify.json in the deployed sha" in proc.stderr


@_POSIX_ONLY
def test_the_helper_bounds_its_map_probes_by_the_deadline(tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    path = _git_wrapper(tmp_path, 'case "$*" in *"cat-file blob"*) exec sleep 30 ;; esac')
    proc, took = _helper(repo, deadline_in=3, path=path)
    assert proc.returncode != 0, proc.stdout
    assert took < 8, took


def _no_map_commit(repo):
    """A commit carrying no `.crew/verify.json` (the project-dir fallback's
    case), left in the object store while HEAD keeps its map."""
    _git(repo.root, "rm", "-q", "--cached", ".crew/verify.json")
    _git(repo.root, "commit", "-q", "-m", "no map")
    nomap = repo.head
    _git(repo.root, "reset", "-q", "--hard", "HEAD~1")
    return nomap


def _helper_at(repo, sha, deadline_in=15, path=None):
    env = dict(os.environ)
    env.pop(_BUDGET, None)
    if path is not None:
        env["PATH"] = path
    start = time.monotonic()
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "_promote_review.py"), str(repo.root),
                           sha, str(int(time.time()) + deadline_in), "development"],
                          cwd=str(repo.root), capture_output=True, text=True, check=False,
                          timeout=60, env=env)
    return proc, time.monotonic() - start


@_POSIX_ONLY
def test_the_fallback_never_reads_a_failed_head_probe_as_no_map(tmp_path):
    """The project-dir fallback's probe of HEAD's map failing must not pass
    for "HEAD has no map", which would let an uncommitted opt-out waive review."""
    repo = Repo(tmp_path, REVIEW_MAP)
    nomap = _no_map_commit(repo)
    repo.write_map({"environments": {"development": {"deploy": "deploy-dev", **_ROLLBACK,
                                                     **_OPT_OUT}}})
    path = _git_wrapper(tmp_path, 'case "$*" in *"ls-tree HEAD"*) exit 128 ;; esac')
    proc, _ = _helper_at(repo, nomap, path=path)
    assert proc.returncode != 0, proc.stdout
    assert "could not list HEAD's" in proc.stderr


@_POSIX_ONLY
def test_the_fallback_bounds_its_map_probes_by_the_deadline(tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    nomap = _no_map_commit(repo)
    path = _git_wrapper(tmp_path, 'case "$*" in *hash-object*) exec sleep 30 ;; esac')
    proc, took = _helper_at(repo, nomap, deadline_in=3, path=path)
    assert proc.returncode != 0, proc.stdout
    assert took < 8, took


@_POSIX_ONLY
def test_windows_cleanup_stays_inside_the_reap_allowance(tmp_path, monkeypatch):
    """The gate's 16s deadline leaves 4s of the 20s hook timeout for the
    helper to stop its search. On Windows that stop ran `taskkill` for up to
    5s and then waited 2s more for the pipes, so a refusal could arrive after
    the hook had already timed out, which is not a block (L-0703 Codex r3).
    The Windows branch is driven here with a `taskkill` that hangs."""
    import _promote_review  # pylint: disable=import-outside-toplevel
    bin_dir = tmp_path / "winbin"
    bin_dir.mkdir()
    (bin_dir / "taskkill").write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    (bin_dir / "taskkill").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(_promote_review.os, "name", "nt")
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start = time.monotonic()
    _promote_review._stop(proc)  # pylint: disable=protected-access
    took = time.monotonic() - start
    monkeypatch.undo()
    assert proc.poll() is not None, "the search was left running"
    assert took <= _promote_review.REAP_SECONDS + 0.5, took


def test_an_unreadable_ledger_is_reported_as_could_not_tell(tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    repo.ledger().write_text("{not json", encoding="utf-8")
    proc, _ = _helper(repo)
    assert proc.returncode == 0, proc.stderr
    assert "requires an accepted review" in proc.stdout
    assert "could not tell: 1 ledger(s) could not be read (T-0001)" in proc.stdout


@_POSIX_ONLY
@pytest.mark.parametrize("with_python", [False, True])
def test_sh_refuses_a_map_that_is_not_a_regular_file(with_python, tmp_path):
    """A FIFO map held `git hash-object` (and every later read) past the hook
    timeout, which is not a block (L-0703 review r2)."""
    if not with_python and shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    path = repo.root / ".crew" / "verify.json"
    path.unlink()
    os.mkfifo(path)
    code, err, took = run_gate("sh", repo, "deploy-dev", timeout=30,
                               path=None if with_python else _path_without_python(tmp_path))
    assert code == 2, err
    assert took < 10, took


@_POSIX_ONLY
@_NEEDS_PWSH
@pytest.mark.wallclock
@pytest.mark.parametrize("kind", ["fifo", "link-to-fifo"])
def test_ps1_refuses_a_map_that_is_not_a_regular_file(kind, tmp_path):
    """The .ps1 runs for the PowerShell tool on any OS; a FIFO map held it past
    the hook timeout just as it held the .sh (L-0703 review r2)."""
    repo = Repo(tmp_path, SHA_MAP)
    path = repo.root / ".crew" / "verify.json"
    path.unlink()
    if kind == "fifo":
        os.mkfifo(path)
    else:
        os.mkfifo(repo.root / ".crew" / "pipe")
        path.symlink_to("pipe")
    code, err, took = run_gate("ps1", repo, "deploy-dev", timeout=30)
    assert code == 2, err
    assert "not a regular file" in err, err
    assert took < 10, took


@_POSIX_ONLY
@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_map_reached_through_a_link_to_a_regular_file_is_read(flavour, tmp_path):
    """Must-allow twin of the two above: a link is judged by its target, so a
    map symlinked to a regular file is a map, not "not a regular file". The
    map is an ignored, never-committed one (policy as it stands, not dirt):
    git stores a committed link as its target's path, not as a map."""
    repo = Repo(tmp_path, SHA_MAP)
    path = repo.root / ".crew" / "verify.json"
    (repo.root / ".crew" / "real-map.json").write_bytes(path.read_bytes())
    _git(repo.root, "rm", "-q", "--cached", ".crew/verify.json")
    (repo.root / ".gitignore").write_text(".crew/\n.work/\n", encoding="utf-8")
    _git(repo.root, "add", "-A")
    _git(repo.root, "commit", "-q", "-m", "stop tracking the map")
    path.unlink()
    path.symlink_to("real-map.json")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.short}"


@_POSIX_ONLY
def test_sh_without_python_bounds_the_committed_map_read(tmp_path):
    """Must-block: with the working map dirty, the fallback reads the
    committed map too; a `git cat-file` that stalls must block inside the
    hook's 20s, never run past it (L-0703 Codex r3)."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    repo.write_map({**SHA_MAP, "note": "an uncommitted edit"})
    bin_dir = pathlib.Path(_path_without_python(tmp_path))
    (bin_dir / "git").unlink()
    (bin_dir / "git").write_text(
        f'#!/bin/sh\n[ "$1" = cat-file ] && exec sleep 60\nexec "{_GIT}" "$@"\n',
        encoding="utf-8")
    (bin_dir / "git").chmod(0o755)
    code, err, took = run_gate("sh", repo, "ls -la", path=str(bin_dir), timeout=40)
    assert code == 2, err
    assert "committed .crew/verify.json could not be read" in err, err
    assert took < 19, took


@_POSIX_ONLY
@pytest.mark.wallclock
def test_sh_without_python_scans_a_large_map_quickly(tmp_path):
    """One jq process per map: a fork per string took 20.8s on this repo's
    own 847-string map, past the hook timeout.

    `wallclock`: it bounds elapsed time, and under CI's `-n 16` on a 4-vCPU
    hosted runner the gate's own 16s deadline ran out mid-jq, so the block
    read "jq could not read it" (run 37984138378, test (3.12))."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    big = {"environments": {f"env{i}": {"deploy": f"deploy-number-{i}", "rollback": "none",
                                        "rollbackReason": f"reason {i}", "smoke": [f"s{i}"] * 5}
                            for i in range(400)}}
    repo = Repo(tmp_path, big)
    code, err, took = run_gate("sh", repo, "npm test", path=_path_without_python(tmp_path))
    assert code == 0, err
    assert took < 5, took


# Maps python's strict reading refuses (status 4 in promote-gate.sh, a
# Deny-UnreadableMap in the .ps1), none of which holds a string the deploy
# command contains: the jq fallback found no string to match, so it let
# `deploy-prod` through (L-0703 Codex r1 BLOCK 1).
_MALFORMED_MAPS = {
    "deploy-true": '{"environments": {"prod": {"deploy": true}}}',
    "deploy-null": '{"environments": {"prod": {"deploy": null}}}',
    "deploy-number": '{"environments": {"prod": {"deploy": 5}}}',
    "deploy-object": '{"environments": {"prod": {"deploy": {}}}}',
    "deploy-list-of-bool": '{"environments": {"prod": {"deploy": [true]}}}',
    "deploy-case-key": '{"environments": {"prod": {"Deploy": false}}}',
    "env-not-object": '{"environments": {"prod": 7}}',
    "environments-list": '{"environments": [1]}',
    "environments-null": '{"Environments": null}',
    "doc-list": '[1]',
    "require-human-list": '{"environments": {"prod": {"deploy": "x", "requireHuman": []}}}',
    "env-name-comma": '{"environments": {"a,b": {"deploy": "x"}}}',
    "env-name-control": '{"environments": {"a\\u0001": {"deploy": "x"}}}',
    "case-twin-keys": '{"environments": {"prod": {"deploy": "x", "DEPLOY": "y"}}}',
    "case-twin-envs": '{"environments": {"prod": {"deploy": "x"}, "PROD": {"deploy": "y"}}}',
    # Codex r2: a key repeated with DIFFERENT child paths. The leaf-path
    # check saw no repeat, and jq kept only the second `prod`.
    "dup-key-other-children": '{"environments": {"prod": {"deploy": "deploy-prod"}, '
                              '"prod": {"rollback": "none"}}}',
    "dup-key-container-then-leaf": '{"environments": {"prod": {"deploy": "deploy-prod"}, '
                                   '"prod": 1}}',
    # rush 1.2.1: main's L-0648 strict reading refuses a `github` entry that is
    # not an object or a non-empty list of objects; the fallback must too.
    "github-string": '{"environments": {"prod": {"deploy": "x", "github": "nope"}}}',
    "github-empty-list": '{"environments": {"prod": {"deploy": "x", "GitHub": []}}}',
    "github-list-of-number": '{"environments": {"prod": {"deploy": "x", "github": [1]}}}',
}


def _commit_raw_map(repo, text, message="malformed map"):
    (repo.root / ".crew" / "verify.json").write_text(text + "\n", encoding="utf-8")
    _git(repo.root, "add", "-A")
    _git(repo.root, "commit", "-q", "-m", message)


@_POSIX_ONLY
@pytest.mark.parametrize("case", sorted(_MALFORMED_MAPS))
@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_without_python_a_map_it_cannot_classify_blocks(flavour, case, tmp_path):
    """Must-block: with no python, a map the gate cannot classify is unknown,
    never "no environment matched" (L-0703 Codex r1 BLOCK 1). The .ps1 reads
    the map natively, so its case holds the parity: both refuse."""
    if flavour == "sh" and shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    _commit_raw_map(repo, _MALFORMED_MAPS[case])
    code, err, _ = run_gate(flavour, repo, "deploy-prod", path=_path_without_python(tmp_path))
    assert code == 2, err
    assert repo.in_flight() is None
    if flavour == "sh":
        assert "cannot classify" in err or "repeats a key" in err, err
    else:
        # Refused for the MAP, not by the review step's own "no usable python".
        assert "verify.json" in err and "review-evidence" not in err, err


@_POSIX_ONLY
@pytest.mark.parametrize("github", [{"workflow": "deploy.yml"}, [{"workflow": "deploy.yml"}]],
                         ids=["object", "list-of-objects"])
def test_without_python_a_well_formed_github_entry_is_classified(github, tmp_path):
    """Must-allow twin of the github cases above: a `github` entry python
    accepts does not make the no-python fallback refuse the map, so a command
    that is no deploy still runs."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    _commit_raw_map(repo, json.dumps({"environments": {"prod": {
        "deploy": "deploy-prod", "github": github}}}))
    code, err, _ = run_gate("sh", repo, "npm test", path=_path_without_python(tmp_path))
    assert code == 0, err


@_POSIX_ONLY
@pytest.mark.parametrize("case", sorted(_MALFORMED_MAPS))
def test_with_python_the_same_maps_are_refused(case, tmp_path):
    """The reference the fallback is held to: python refuses every one."""
    repo = Repo(tmp_path, SHA_MAP)
    _commit_raw_map(repo, _MALFORMED_MAPS[case])
    code, err, _ = run_gate("sh", repo, "deploy-prod")
    assert code == 2, err


# Codex r2: python folds case per character over Unicode (`fold` in
# promote-gate.sh), so `DÉPLOY` matches `déploy` and `deploy-ſ` (long s)
# matches `DEPLOY-S`; jq's ascii_downcase matched neither and let the
# declared deploy through. Each pair is (declared deploy, command run).
_UNICODE_FOLDS = {
    "e-acute": ("D\u00c9PLOY", "d\u00e9ploy"),
    "long-s": ("deploy-\u017f", "DEPLOY-S"),
    "dotless-i": ("deploy-\u0131", "deploy-I"),
    "command-holds-it": ("D\u00c9PLOY", "x d\u00e9ploy --now"),
}


@_POSIX_ONLY
@pytest.mark.parametrize("case", sorted(_UNICODE_FOLDS))
@pytest.mark.parametrize("with_python", [False, True])
def test_sh_without_python_matches_as_the_matcher_folds_case(with_python, case, tmp_path):
    """Must-block: whatever python's matcher calls a deploy, the fallback
    blocks too; with_python=True is the reference it is held to."""
    if not with_python and shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    declared, command = _UNICODE_FOLDS[case]
    repo = Repo(tmp_path, {"environments": {"prod": {"deploy": declared, **_ROLLBACK}}})
    code, err, _ = run_gate("sh", repo, command,
                            path=None if with_python else _path_without_python(tmp_path))
    assert code == 2, err
    if not with_python:
        assert "contain one another" in err, err


@_POSIX_ONLY
def test_sh_without_python_passes_an_unrelated_command_on_a_unicode_map(tmp_path):
    """Must-allow twin: a non-ASCII value does not make every command a deploy."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, {"environments": {"prod": {"deploy": "d\u00e9ploy-pr\u00f8d",
                                                     **_ROLLBACK}}})
    code, err, _ = run_gate("sh", repo, "ls -la", path=_path_without_python(tmp_path))
    assert code == 0, err


# Maps python reads, holding nothing the command matches: the fallback must
# not refuse them, or a host without python is locked out of every command.
_WELL_FORMED_MAPS = {
    "deploy-list": '{"environments": {"prod": {"deploy": ["deploy-p", "ship-p"]}}}',
    "deploy-absent": '{"environments": {"prod": {"rollback": "none"}}}',
    "deploy-empty-list": '{"environments": {"prod": {"deploy": []}}}',
    "no-environments": '{"smoke": ["x"]}',
    "require-human-bool": '{"environments": {"prod": {"deploy": "deploy-p", "requireHuman": true}}}',
    "case-key": '{"Environments": {"prod": {"DEPLOY": "deploy-p"}}}',
    "nested-objects": '{"environments": {"prod": {"deploy": "deploy-p", "x": {"y": [{"z": 1}]}}}}',
}


@_POSIX_ONLY
@pytest.mark.parametrize("case", sorted(_WELL_FORMED_MAPS))
def test_sh_without_python_passes_an_unrelated_command_on_a_valid_map(case, tmp_path):
    """Must-allow twin of the case above."""
    if shutil.which("jq") is None:
        pytest.skip("no jq on this machine")
    repo = Repo(tmp_path, SHA_MAP)
    _commit_raw_map(repo, _WELL_FORMED_MAPS[case])
    code, err, _ = run_gate("sh", repo, "ls -la", path=_path_without_python(tmp_path))
    assert code == 0, err


@_POSIX_ONLY
@_NEEDS_PWSH
@pytest.mark.wallclock
def test_ps1_without_python_blocks_a_declared_deploy(tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    code, err, _ = run_gate("ps1", repo, "deploy-dev", path=_path_without_python(tmp_path))
    assert code == 2, err
    assert "python" in err, err


# =============================================================================
# 2. review evidence: must-allow
# =============================================================================

@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_clean_receipt_for_the_deploying_head_admits(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.short}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_owner_accepted_receipt_admits(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.findings_round()
    review_ledger.accept(str(repo.root), "T-0001", "owner")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.short}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_receipt_for_a_same_tree_commit_admits(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    repo.commit(empty=True)
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_one_standing_receipt_among_unrelated_ledgers_admits(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.findings_round("T-0009")
    repo.clean_receipt("T-0001")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_require_review_false_with_reason_admits(flavour, tmp_path):
    repo = Repo(tmp_path, SHA_MAP)
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.short}"


@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_crlf_checkout_of_the_committed_map_is_the_committed_map(flavour, tmp_path):
    """Windows CI: under core.autocrlf the working map is CRLF and its blob LF;
    the helper's hold-to-HEAD check must hash it as git stores the path."""
    repo = Repo(tmp_path, SHA_MAP)
    _git(repo.root, "config", "core.autocrlf", "true")
    path = repo.root / ".crew" / "verify.json"
    path.unlink()
    _git(repo.root, "checkout", "--", ".crew/verify.json")
    assert b"\r\n" in path.read_bytes(), "the checkout did not write CRLF: the case proves nothing"
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_require_human_true_with_marker_and_receipt_admits(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    repo.clean_receipt()
    (repo.root / ".crew" / f".approved-prod-{repo.short}").write_text("", encoding="utf-8")
    code, err, _ = run_gate(flavour, repo, "deploy-prod")
    assert code == 0, err


# =============================================================================
# union rule and emergency lane
# =============================================================================

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_union_refuses_for_the_environment_that_did_not_opt_out(flavour, tmp_path):
    repo = Repo(tmp_path, {"environments": {
        "a": {"deploy": "deploy-x", **_ROLLBACK, **_OPT_OUT},
        "b": {"deploy": "deploy-x", **_ROLLBACK},
    }})
    code, err, _ = run_gate(flavour, repo, "deploy-x")
    assert code == 2, err
    assert "[b] 'b' requires an accepted review" in err, err
    assert "'a' requires an accepted review" not in err


def _scripts_with_broken_helper(tmp_path, how):
    scripts = _copy_scripts(tmp_path)
    helper = scripts / "_promote_review.py"
    if how == "missing":
        helper.unlink()
    else:
        helper.write_text("import sys\nprint('helper broke', file=sys.stderr)\nsys.exit(3)\n",
                          encoding="utf-8")
    return scripts


@pytest.mark.parametrize("how", ["missing", "exits-nonzero"])
@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_a_failing_helper_blocks_outside_an_incident(flavour, how, tmp_path):
    """Must-block half of the pair below."""
    repo = Repo(tmp_path, REVIEW_MAP)
    scripts = _scripts_with_broken_helper(tmp_path, how)
    code, err, _ = run_gate(flavour, repo, "deploy-dev", scripts=scripts)
    assert code == 2, err
    assert "could not be evaluated" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("how", ["missing", "exits-nonzero"])
@pytest.mark.parametrize("flavour", FLAVOURS_DEFAULT)
def test_an_open_incident_records_a_failing_helper_as_a_skip(flavour, how, tmp_path):
    """Must-allow in an incident: a review check that could not run is an
    unmet precondition like any other, recorded as a skip - it used to exit 2
    before the emergency lane ran (L-0703 Codex r1 BLOCK 2)."""
    repo = Repo(tmp_path, REVIEW_MAP)
    (repo.root / ".crew" / "incident.json").write_text(
        json.dumps({"expiresAtEpoch": int(time.time()) + 3600}), encoding="utf-8")
    scripts = _scripts_with_broken_helper(tmp_path, how)
    code, err, _ = run_gate(flavour, repo, "deploy-dev", scripts=scripts)
    assert code == 0, err
    log = (repo.root / ".crew" / "incident-skips.log").read_text(encoding="utf-8")
    assert "review-evidence check could not be evaluated" in log, log
    assert repo.in_flight() == f"development {repo.short}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_open_incident_records_the_missing_review_as_a_skip(flavour, tmp_path):
    repo = Repo(tmp_path, REVIEW_MAP)
    (repo.root / ".crew" / "incident.json").write_text(
        json.dumps({"expiresAtEpoch": int(time.time()) + 3600}), encoding="utf-8")
    code, err, _ = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    log = (repo.root / ".crew" / "incident-skips.log").read_text(encoding="utf-8")
    assert "requires an accepted review" in log
