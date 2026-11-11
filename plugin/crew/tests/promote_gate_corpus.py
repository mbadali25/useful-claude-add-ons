"""The decision corpus for the one-process promote gate (crew 1.3.41).

Each case is a repository state plus a Bash command, and the decision the gate
had before it became one python process: the exit status and a phrase its
stderr must carry. The expectations were RECORDED by running the shell-only gate (the
`promote-gate.sh` of crew 1.3.32, `git show 48ef62231:...`) over these same
cases on 2026-11-10 (all 41 agreed with the new gate, exit status, phrase,
in-flight marker and skip rows); `test_promote_gate_one_process.py` replays them
on the current gate, so a rule the rewrite dropped or changed turns a case red.

`build(tmp_path, case)` makes the repository; `payload(root, case)` the hook
payload. Nothing here touches real config: the fixture is built under tmp_path.
"""
import datetime
import json
import os
import subprocess

from _train_base import TRAIN_BASE, seed_train_base

TODAY = datetime.date.today()

#: environment blocks, shared by every case; a case may replace one.
STAGING = {"deploy": ["deploy-stg", "gh workflow run deploy.yml -f environment=staging"],
           "rollback": "none", "rollbackReason": "fixture",
           "requireReview": False, "reviewReason": "fixture", "reviewWaiverSha": TRAIN_BASE}
PROD = {"deploy": ["deploy-prod", "gh workflow run deploy.yml -f environment=production"],
        "requires": ["staging"], "rollback": "docs/rb.md", "requireHuman": True,
        "requireReview": False, "reviewReason": "fixture", "reviewWaiverSha": TRAIN_BASE}

SHA = "<sha>"      # the deployed commit, short
FULL = "<full>"    # the deployed commit, full
BASE = "<base>"    # the commit before it (a real commit that is not HEAD)
ROOT = "<root>"    # the repository, as the payload's cwd


def case(name, command, code, why=None, *, state=None, envs=None, cwd=None, fixed=False,
         raw_payload=None):
    """One case. `state` flags select the repository's condition (see build)."""
    return {"name": name, "command": command, "code": code, "why": why,
            "state": state or {}, "envs": envs, "cwd": cwd, "fixed": fixed,
            "raw_payload": raw_payload}


GOOD = {"staging_row": "pass", "runbook": "fresh", "marker": True}

CASES = (
    # --- must allow -------------------------------------------------------
    case("echo-is-no-deploy", "echo hi", 0, state=GOOD),
    case("a-fragment-of-a-declared-command-is-no-deploy", "git rev-parse HEAD", 0, state=GOOD),
    case("an-empty-command-is-nothing", "", 0, state=GOOD),
    case("a-payload-that-is-not-json-is-nothing", "ignored", 0, state=GOOD, raw_payload="not json"),
    case("staging-with-nothing-upstream", "deploy-stg", 0, state={"marker": False}),
    case("prod-with-every-precondition-met", "deploy-prod", 0, state=GOOD),
    case("prod-dispatch-with-every-precondition-met",
         "gh workflow run deploy.yml -f environment=production", 0, state=GOOD),
    case("a-dispatch-of-an-undeclared-workflow", "gh workflow run other.yml -f environment=production",
         0, state=GOOD),
    case("the-match-ignores-case", "DEPLOY-STG", 0, state={"marker": False}),
    case("a-leading-cd-into-the-repo", "cd <root> && deploy-stg", 0, state={"marker": False}),
    case("non-ascii-text-around-a-deploy", "echo é && deploy-stg", 0, state={"marker": False}),
    case("a-crlf-command", "deploy-stg\r\n", 0, state={"marker": False}),
    case("no-map-at-all-is-an-opt-out", "deploy-prod", 0, state={"no_map": True}),
    # --- must block: the preconditions -------------------------------------
    case("prod-without-a-staging-row", "deploy-prod", 2, "has no all-pass row",
         state={"staging_row": None, "runbook": "fresh", "marker": True}),
    case("prod-with-only-a-short-sha-row", "deploy-prod", 2, "short sha",
         state={"staging_row": "short", "runbook": "fresh", "marker": True}),
    case("prod-whose-newest-staging-row-failed", "deploy-prod", 2, "newest row is not all-pass",
         state={"staging_row": "pass-then-fail", "runbook": "fresh", "marker": True}),
    case("prod-without-the-human-marker", "deploy-prod", 2, "requires explicit human approval",
         state={"staging_row": "pass", "runbook": "fresh", "marker": False}),
    case("prod-with-a-stale-runbook", "deploy-prod", 2, "ceiling is 90",
         state={"staging_row": "pass", "runbook": "stale", "marker": True}),
    case("prod-with-a-missing-runbook", "deploy-prod", 2, "does not exist",
         state={"staging_row": "pass", "runbook": "missing", "marker": True}),
    case("prod-with-a-runbook-date-that-is-not-a-date", "deploy-prod", 2, "not a real date",
         state={"staging_row": "pass", "runbook": "baddate", "marker": True}),
    case("prod-with-a-runbook-that-has-no-verified-line", "deploy-prod", 2, "no 'last verified",
         state={"staging_row": "pass", "runbook": "nodate", "marker": True}),
    case("two-environments-name-each-unmet-precondition", "deploy-prod && deploy-stg", 2, "[prod]",
         state={"staging_row": None, "runbook": "stale", "marker": False}),
    case("a-dispatch-of-prod-without-its-staging-row",
         "gh workflow run deploy.yml -f environment=production", 2, "has no all-pass row",
         state={"staging_row": None, "runbook": "fresh", "marker": True}),
    case("a-dispatch-only-the-dispatch-reader-can-see",
         "gh workflow run deploy.yml -f x=1 -f environment=production", 2, "has no all-pass row",
         state={"staging_row": None, "runbook": "fresh", "marker": True}),
    case("a-dispatch-that-fits-no-single-environment", "gh workflow run deploy.yml", 2, None,
         state=GOOD),
    case("an-environment-with-no-rollback-key", "deploy-stg", 2, "no 'rollback' key",
         envs={"staging": {"deploy": "deploy-stg", "requireReview": False,
                           "reviewReason": "fixture", "reviewWaiverSha": TRAIN_BASE}}),
    case("rollback-none-with-no-reason", "deploy-stg", 2, "no rollbackReason",
         envs={"staging": {"deploy": "deploy-stg", "rollback": "none", "requireReview": False,
                           "reviewReason": "fixture", "reviewWaiverSha": TRAIN_BASE}}),
    case("review-is-required-and-there-is-none", "deploy-stg", 2, "requires an accepted review",
         envs={"staging": {"deploy": "deploy-stg", "rollback": "none", "rollbackReason": "fixture"}}),
    case("requireReview-that-is-neither-true-nor-false", "deploy-stg", 2, "not true or false",
         envs={"staging": {"deploy": "deploy-stg", "rollback": "none", "rollbackReason": "fixture",
                           "requireReview": "yes"}}),
    # --- must block: the tree ----------------------------------------------
    case("an-untracked-file-dirties-the-tree", "deploy-stg", 2, "is dirty",
         state={"untracked": True}),
    case("an-edited-tracked-file-dirties-the-tree", "deploy-stg", 2, "is dirty",
         state={"edit_tracked": True}),
    case("an-uncommitted-edit-to-the-map", "deploy-stg", 2, "uncommitted changes",
         state={"edit_map": True}),
    case("the-map-deleted-from-the-working-copy", "deploy-stg", 2, "uncommitted changes",
         state={"delete_map": True}),
    case("a-committed-map-that-is-not-json", "deploy-stg", 2, "NOT a pass",
         state={"garbage_map": True}),
    case("a-literal-sha-that-is-not-the-trees-head", "deploy-stg <base>", 2, "names commit",
         state={"marker": False}),
    case("a-cd-that-resolves-nowhere", "cd /no/such/dir-for-the-gate && deploy-stg", 2,
         "does not resolve", state={"marker": False}),
    case("a-cd-after-the-start-of-the-command", "deploy-stg && cd /tmp && echo done", 2,
         "changes directory after", state={"marker": False}),
    case("a-payload-cwd-that-does-not-exist", "deploy-stg", 2, "does not exist",
         cwd="/no/such/cwd-for-the-gate"),
    # --- the emergency lane -------------------------------------------------
    case("an-open-incident-records-the-skip-and-allows", "deploy-prod", 0, None,
         state={"staging_row": None, "runbook": "stale", "marker": False, "incident": "open"}),
    case("an-expired-incident-blocks-again", "deploy-prod", 2, "has no all-pass row",
         state={"staging_row": None, "runbook": "fresh", "marker": True, "incident": "expired"}),
    # --- a declared deploy that begins with a slash ---------------------------
    # Git Bash rewrites an argument that starts like a POSIX path before python
    # saw it; the command is now read from the payload as written. Measured: the
    # old gate blocked this one too (the rewritten text still contained it).
    case("a-declared-deploy-that-begins-with-a-slash", "/opt/deploy-it.sh stg", 2,
         "has no all-pass row", fixed=False,
         envs={"staging": {"deploy": "/opt/deploy-it.sh stg", "requires": ["setup"],
                           "rollback": "none", "rollbackReason": "fixture",
                           "requireReview": False, "reviewReason": "fixture",
                           "reviewWaiverSha": TRAIN_BASE},
               "setup": {"deploy": "deploy-setup", "rollback": "none", "rollbackReason": "fixture",
                         "requireReview": False, "reviewReason": "fixture",
                         "reviewWaiverSha": TRAIN_BASE}},
         state={"staging_row": None}),
)

NAMES = tuple(c["name"] for c in CASES)


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout.strip()


def build(tmp_path, spec):
    """The repository for `spec`; returns (root, short sha, full sha, base sha)."""
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.autocrlf", "false")
    seed_train_base(root)
    state = spec["state"]
    (root / "README.md").write_text("repo\n", encoding="utf-8")
    (root / ".gitignore").write_text(".crew/*\n!.crew/verify.json\n.work/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    envs = spec["envs"] or {"staging": STAGING, "prod": PROD}
    (root / ".crew").mkdir()
    (root / "docs").mkdir()
    if not state.get("no_map"):
        text = "{ this is not json" if state.get("garbage_map") else json.dumps(
            {"environments": envs}, indent=2) + "\n"
        (root / ".crew" / "verify.json").write_text(text, encoding="utf-8")
    runbook = state.get("runbook")
    if runbook:
        day = {"fresh": TODAY, "stale": TODAY - datetime.timedelta(days=120)}.get(runbook)
        text = {"baddate": "last verified: 2026-99-99\n", "nodate": "no date here\n"}.get(
            runbook, f"last verified: {day}\n" if day else "")
        if runbook != "missing":
            (root / "docs" / "rb.md").write_text(text, encoding="utf-8")
    (root / "docs" / "x.txt").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "fixture")
    full = _git(root, "rev-parse", "HEAD")
    short = _git(root, "rev-parse", "--short", "HEAD")
    (root / ".work").mkdir(exist_ok=True)
    rows = {None: [], "pass": [("pass", full)], "short": [("pass", full[:7])],
            "pass-then-fail": [("pass", full), ("FAIL", full)]}.get(state.get("staging_row"), [])
    lines = ["| when | env | sha | smoke | regression | verify | by |", "|---|---|---|---|---|---|---|"]
    lines += [f"| 2026-11-10 | staging | {sha} | pass | {'pass' if res == 'pass' else res} | pass | t |"
              for res, sha in rows]
    (root / ".work" / "PROMOTIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if state.get("marker"):
        (root / ".crew" / f".approved-prod-{short}").write_text("", encoding="utf-8")
    if state.get("untracked"):
        (root / "scratch.txt").write_text("x\n", encoding="utf-8")
    if state.get("edit_tracked"):
        (root / "README.md").write_text("edited\n", encoding="utf-8")
    if state.get("edit_map"):
        with open(root / ".crew" / "verify.json", "a", encoding="utf-8") as handle:
            handle.write("\n")
    if state.get("delete_map"):
        os.remove(root / ".crew" / "verify.json")
    incident = state.get("incident")
    if incident:
        expires = int(datetime.datetime.now().timestamp()) + (3600 if incident == "open" else -3600)
        (root / ".crew" / "incident.json").write_text(
            json.dumps({"expiresAtEpoch": expires}), encoding="utf-8")
    return root, short, full, base


def fill(text, root, short, full, base):
    """Replace the placeholders a case's command or cwd carries."""
    return (text.replace(ROOT, str(root).replace("\\", "/")).replace(SHA, short)
            .replace(FULL, full).replace(BASE, base))


def payload(root, spec, short, full, base):
    """The hook payload as Claude Code sends it (bytes)."""
    if spec["raw_payload"] is not None:
        return spec["raw_payload"].encode()
    body = {"tool_name": "Bash", "cwd": fill(spec["cwd"] or ROOT, root, short, full, base),
            "tool_input": {"command": fill(spec["command"], root, short, full, base)}}
    return json.dumps(body).encode()
