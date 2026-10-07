"""The Stop gate's health and the QA audit's freshness, read for `crew_state.collect`.

Split out of `crew_state` (C0302, its 3,400-line cap) with no behaviour change;
`crew_state` re-exports every public name here, so callers keep reading
`crew_state.read_verify_health` and friends. Standard library only, and every
read fails soft, for the same reason as `crew_state`: it runs from a
SessionStart hook.
"""
import json
import os

from crew_common import git_out, read_text


def _int_or_none(text):
    """`git rev-list --count`'s output as an int, or None -- what
    `crew_state.int_or(text, None)` answers for a string."""
    try:
        return int(text.strip())
    except ValueError:
        return None


# --- Stop gate health --------------------------------------------------------
#
# What the per-rule record and the map itself say about the Stop gate's own
# coverage -- three questions the crew 0.19.93 fix introduced no config key
# for, because none of this is a setting; it is a fact about what is in
# `.crew/verify.json` and what the last Stop actually verified. See
# `hooks/scripts/verify-gate.sh`/`.ps1`, `verify_record.py` and CONFIG.md §18.
#
# UNKNOWN NEVER RESOLVES TO HEALTHY, matching every other reader in this
# module. A value here is `None` exactly when it could not be determined --
# `.crew/verify.json` unreadable, not a git repository, `rev-list` failing --
# and `evaluate_triggers` below reads `None` as "fire the trigger", the same
# direction `graphStale`/`knowledgeUnverifiable` already take: an absent or
# unreadable fact is worse than a bad one, not better, because a bad one at
# least says what is wrong.
VERIFY_MARKER_STALE_COMMITS = 50


def read_verify_health(root):
    """Marker staleness, unpriced rules, undeclared reach -- all read
    straight from the files the gate itself reads, never from a cache.

    `mapPresent` is kept apart from the three counts on purpose: a repo that
    never adopted `.crew/verify.json` (the gate falls back to
    `_verify/smoke.sh`) has nothing to price or declare reach on, and that is
    a normal, healthy state -- not an unknown. A repo whose map EXISTS but
    could not be parsed is a genuine unknown, and `mapPresent=True` with the
    three counts still `None` is how the caller tells the two apart.
    """
    result = {
        "markerPresent": False,
        "markerBehindCommits": None,
        "mapPresent": False,
        "totalRules": None,
        "unpricedRules": None,
        "undeclaredReachRules": None,
    }
    marker_path = os.path.join(root, ".crew", ".verify-verified-at")
    if os.path.isfile(marker_path):
        sha = (read_text(marker_path) or "").splitlines()
        sha = sha[0].strip() if sha else ""
        if sha:
            result["markerPresent"] = True
            # None on ANY failure -- git absent, root not a repo, sha not
            # found (a squash merge, same as the gate's own BASE fallback).
            # A behind-count of None must not read as "0 behind"; see the
            # module note above.
            count = git_out(root, "rev-list", "--count", f"{sha}..HEAD")
            if count is not None:
                result["markerBehindCommits"] = _int_or_none(count)

    vpath = os.path.join(root, ".crew", "verify.json")
    if os.path.isfile(vpath):
        result["mapPresent"] = True
        try:
            with open(vpath, encoding="utf-8") as fh:
                vmap = json.load(fh)
        except (OSError, ValueError):
            vmap = None
        rules = vmap.get("rules") if isinstance(vmap, dict) else None
        if isinstance(rules, list):
            dict_rules = [r for r in rules if isinstance(r, dict)]
            result["totalRules"] = len(dict_rules)
            result["unpricedRules"] = sum(
                1 for r in dict_rules
                if not isinstance(r.get("seconds"), (int, float))
                or isinstance(r.get("seconds"), bool)
            )
            result["undeclaredReachRules"] = sum(
                1 for r in dict_rules if "reach" not in r
            )
    return result


# --- QA audit freshness (L-0618) --------------------------------------------
#
# qa_audit.py --stamp records the HEAD it judged. Fires when there is no stamp
# (every repo set up before the audit hears it once) or the paths it reads
# moved since. `changedSince` is None when git cannot answer, and that fires:
# UNKNOWN NEVER RESOLVES TO HEALTHY, as above.
QA_AUDIT_STAMP = os.path.join(".crew", ".qa-audit-at")
QA_AUDIT_PATHS = (".crew/verify.json", "_verify", ".github/workflows",
                  "bitbucket-pipelines.yml", ".gitlab-ci.yml", "azure-pipelines.yml",
                  ".gitignore")


def read_qa_audit(root):
    """Whether the QA audit has been stamped, and whether the paths it reads
    changed after the stamped commit. Never raises."""
    result = {"stampPresent": False, "stampSha": None, "changedSince": None}
    lines = (read_text(os.path.join(root, QA_AUDIT_STAMP)) or "").splitlines()
    sha = lines[0].strip() if lines else ""
    if not sha:
        return result
    result["stampPresent"] = True
    result["stampSha"] = sha
    if git_out(root, "cat-file", "-e", f"{sha}^{{commit}}") is None:
        return result
    changed = git_out(root, "diff", "--name-only", f"{sha}..HEAD", "--", *QA_AUDIT_PATHS)
    if changed is not None:
        result["changedSince"] = bool(changed)
    return result
