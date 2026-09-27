"""T-0046: the review bundle lists the three graphify outputs by hash instead
of diffing them, and the receipt still binds them.

`review_patch.compute` omits exactly `graphify-out/graph.json`,
`graphify-out/GRAPH_REPORT.md` and `graphify-out/graph.html` at the repository
root when they arrive as a plain add, modify or delete of a regular file, and
appends one listing line each to the patch bytes: status, path, both blob ids,
the sha256 of the new content and its size. Because the listing is inside the
patch, `bundle_sha256`, the part check, the receipt, `--accept` and
`--check-receipt` all bind it. Anything else -- a rename or copy, a link, a
mode change, another file under `graphify-out/`, a nested or case-variant
name, or a `graphify-out` that is itself a link -- is diffed in full, as
before. A receipt written before this change carries no `bundle_scheme` and is
checked against today's full diff (`omit_generated=False`), so none goes stale
on upgrade; an unknown scheme reads as not current, never as a fallback.

`sabotage_bookkeeping.py` breaks each refusing branch and the matching case
here goes red.
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
import review_prompt
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_LEDGER = os.path.join(_SCRIPTS, "review_ledger.py")
_RUN = os.path.join(_SCRIPTS, "review_run.py")
GRAPH, REPORT = "graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md"
LISTED = re.compile(r"^omitted (?P<status>[AMD]) (?P<path>\S+) old (?P<old>[0-9a-f]+) "
                    r"new (?P<new>[0-9a-f]+) sha256 (?P<sha>[0-9a-f]{64}|-) "
                    r"bytes (?P<bytes>\d+|-)$", re.MULTILINE)


def _write(root, rel, text):
    path = root.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _graph(n):
    return json.dumps({"nodes": [{"id": i} for i in range(n)]}, indent=1) + "\n"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = init_repo(tmp_path / "r")
    _write(root, GRAPH, _graph(200))
    _write(root, "src/app.py", "x = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    return root


def _commit(root, message="change"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def _bundle(root, base, **kwargs):
    manifest, patch, _parts = review_patch.compute(str(root), base, **kwargs)
    return manifest, patch.decode("utf-8", "replace")


def _base(root):
    return git(root, "rev-parse", "HEAD")


def _diffed(patch, rel):
    return f"diff --git a/{rel} " in patch or f" b/{rel}\n" in patch


def _listed(patch):
    return {m.group("path"): m.groupdict() for m in LISTED.finditer(patch)}


# --- must-block: diffed in full, never listed -----------------------------------

def test_renamed_into(repo):
    git(repo, "rm", "-q", GRAPH)
    _commit(repo, "graph removed")
    base = _base(repo)
    (repo / "graphify-out").mkdir()
    git(repo, "mv", "src/app.py", GRAPH)

    manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, GRAPH), _listed(patch), manifest["renames"]) == (True, {}, [GRAPH])


def test_symlink_graph(repo):
    base = _base(repo)
    repo.joinpath(*GRAPH.split("/")).unlink()
    os.symlink("../src/app.py", repo.joinpath(*GRAPH.split("/")))

    _manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, GRAPH), _listed(patch)) == (True, {})


def test_dir_symlink(repo):
    """`graphify-out` becomes a link to `real-out/`, whose graph.json shares
    no line with the old one, so git reports the old graph deleted rather
    than renamed. That delete is diffed, not listed."""
    base = _base(repo)
    os.replace(repo / "graphify-out", repo / "real-out")
    _write(repo, "real-out/graph.json", "unrelated\n")
    os.symlink("real-out", repo / "graphify-out")

    _manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, GRAPH), _listed(patch)) == (True, {})


@pytest.mark.parametrize("rel", ["graphify-out/evil.py", "plugin/graphify-out/graph.json",
                                 "graphify-out/Graph.json"],
                         ids=["other-file", "nested", "case-variant"])
def test_not_a_generated_path(repo, rel):
    base = _base(repo)
    _write(repo, rel, "print('reviewed')\n")

    _manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, rel), _listed(patch)) == (True, {})


def test_mode_change(repo):
    base = _base(repo)
    os.chmod(repo.joinpath(*GRAPH.split("/")), 0o755)

    _manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, GRAPH), _listed(patch)) == (True, {})


# --- must-allow: omitted and listed ---------------------------------------------

def test_graph_modified(repo):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))

    manifest, patch = _bundle(repo, base)
    legacy, _ = _bundle(repo, base, omit_generated=False)

    row = _listed(patch)[GRAPH]
    blob = subprocess.run(["git", "cat-file", "blob", row["new"]], cwd=repo, check=True,
                          capture_output=True).stdout
    assert (_diffed(patch, GRAPH), row["status"], row["sha"], int(row["bytes"]),
            manifest["patch_bytes"] < legacy["patch_bytes"]) == (
                False, "M", hashlib.sha256(blob).hexdigest(), len(blob), True)


def test_report_added(repo):
    base = _base(repo)
    _write(repo, REPORT, "# Graph report\n")

    manifest, patch = _bundle(repo, base)

    assert (_diffed(patch, REPORT), _listed(patch)[REPORT]["status"],
            [g["path"] for g in manifest["generated"]]) == (False, "A", [REPORT])


def test_graph_deleted(repo):
    base = _base(repo)
    repo.joinpath(*GRAPH.split("/")).unlink()

    _manifest, patch = _bundle(repo, base)

    row = _listed(patch)[GRAPH]
    assert (_diffed(patch, GRAPH), row["status"], row["sha"], row["bytes"]) == (
        False, "D", "-", "-")


def test_only_generated_changed(repo, tmp_path):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))

    manifest, code = review_patch.build(str(repo), base, str(tmp_path / "diff.txt"),
                                        str(tmp_path / "manifest.json"))

    text = (tmp_path / "diff.txt").read_text(encoding="utf-8")
    assert (code, text.startswith(review_patch.LISTING_PREFIX), list(_listed(text)),
            manifest["bundle_scheme"]) == (0, True, [GRAPH], review_patch.BUNDLE_SCHEME)


def test_legacy_bytes(repo):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "x = 2\n")
    _commit(repo)

    manifest, patch, _ = review_patch.compute(str(repo), base, omit_generated=False)

    expected = subprocess.run(["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv",
                               "-M", "--full-index", base, "HEAD", "--", ".",
                               ":(exclude).work"], cwd=repo, check=True,
                              capture_output=True).stdout
    assert (patch == expected, "bundle_scheme" in manifest, "generated" in manifest) == (
        True, False, False)


def test_split_keeps_listing_whole(repo):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "".join(f"line = {i}\n" for i in range(400)))
    listing_size = len(_bundle(repo, base)[1].split(review_patch.LISTING_PREFIX)[1]) + 200

    manifest, patch, parts = review_patch.compute(str(repo), base, max_part_bytes=listing_size)

    holding = [i for i, part in enumerate(parts)
               if review_patch.LISTING_PREFIX.encode() in part]
    assert (len(parts) > 2, holding, parts[-1].endswith(patch[-40:]),
            b"".join(parts) == patch, manifest["patch_bytes"] == len(patch)) == (
                True, [len(parts) - 1], True, True, True)


def test_no_generated_change_builds_todays_bytes(repo):
    base = _base(repo)
    _write(repo, "src/app.py", "x = 3\n")

    new, _ = _bundle(repo, base)
    old, _ = _bundle(repo, base, omit_generated=False)

    assert (new["bundle_sha256"], new["generated"]) == (old["bundle_sha256"], [])


def test_prompt_names_generated_files(repo):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    manifest, _ = _bundle(repo, base)
    manifest["parts"] = []

    block = "\n".join(review_prompt._bundle_block(manifest))  # pylint: disable=protected-access

    assert f"generated (listed by path and sha256 at the end of the last part, not shown; " \
           f"do not report them unread): {GRAPH}" in block


# --- the receipt ---------------------------------------------------------------

def _record(repo, verdict, base, manifest, scheme="new"):
    ok, number, _ = rl.reserve(str(repo), "T1", "codex")
    assert ok
    review = {"verdict": verdict, "counts": {}, "bundle_sha256": manifest["bundle_sha256"],
              "base": base, "head": manifest["head"], "provider": "codex", "model": None,
              "model_family": "gpt"}
    if scheme == "new":
        review["bundle_scheme"] = manifest.get("bundle_scheme")
    elif scheme is not None:
        review["bundle_scheme"] = scheme
    rl.record(str(repo), "T1", number, review)


def _check(repo):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", "T1",
                           "--check-receipt"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def _graph_changed_and_reviewed(repo, verdict):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "x = 4\n")
    manifest, _ = _bundle(repo, base)
    _record(repo, verdict, base, manifest)
    return base


def test_graph_edited_after_clean(repo):
    _graph_changed_and_reviewed(repo, "CLEAN")
    _write(repo, GRAPH, _graph(301))

    result = _check(repo)

    assert (result.returncode, "stale" in result.stdout) == (1, True), result.stdout


def test_accept_after_graph_edit(repo):
    _graph_changed_and_reviewed(repo, "FINDINGS")
    _write(repo, GRAPH, _graph(301))

    with pytest.raises(rl.LedgerError, match="the tree has changed"):
        rl.accept(str(repo), "T1", "the owner")


def test_accept_copies_the_scheme_into_the_receipt(repo):
    _graph_changed_and_reviewed(repo, "FINDINGS")

    receipt = rl.accept(str(repo), "T1", "the owner")

    assert (receipt["bundle_scheme"], _check(repo).returncode) == (
        review_patch.BUNDLE_SCHEME, 0)


def test_unknown_scheme(repo):
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    manifest, _ = _bundle(repo, base)
    _record(repo, "CLEAN", base, manifest, scheme="crew-review/9")

    result = _check(repo)

    assert (result.returncode, "crew-review/9" in result.stdout) == (1, True), result.stdout


def test_legacy_receipt_unchanged(repo):
    """A round recorded before this change: no `bundle_scheme`, and its hash
    is over today's full diff, graph included."""
    base = _base(repo)
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "x = 5\n")
    legacy, _ = _bundle(repo, base, omit_generated=False)
    _record(repo, "CLEAN", base, legacy, scheme=None)

    result = _check(repo)

    assert result.returncode == 0, result.stdout


def test_new_receipt_unchanged(repo):
    _graph_changed_and_reviewed(repo, "CLEAN")

    result = _check(repo)

    assert result.returncode == 0, result.stdout


def _claude_round(repo, tmp_path, tamper=None):
    """Build the bundle with review_patch.py, optionally tamper with a part
    file, answer READ for every part plus CLEAN, and finish a claude round
    through review_run.py."""
    base = _base(repo)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    review_patch.build(str(repo), base, str(scratch / "diff.txt"),
                       str(scratch / "manifest.json"))
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    if tamper:
        tamper(manifest)
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['name']}\n" for p in manifest["parts"]) + "CLEAN\n",
        encoding="utf-8")
    common = [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
              "--scratch", str(scratch), "--provider", "claude"]
    subprocess.run(common + ["--reserve-only"], capture_output=True,
                   stdin=subprocess.DEVNULL, check=True)
    done = subprocess.run(common + ["--round", "1", "--output", str(scratch / "out.txt"),
                                    "--exit-code", "0", "--work-dir", str(tmp_path / "w")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False)
    return done, scratch


def test_listing_line_edited_in_part(repo, tmp_path):
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "x = 6\n")

    def edit_listed_hash(manifest):
        last = pathlib.Path(manifest["parts"][-1]["path"])
        data = last.read_bytes()
        found = re.search(rb"sha256 ([0-9a-f])", data)
        flipped = b"0" if found.group(1) != b"0" else b"1"
        last.write_bytes(data[:found.start(1)] + flipped + data[found.end(1):])

    done, _ = _claude_round(repo, tmp_path, edit_listed_hash)

    assert (done.returncode, _check(repo).returncode) == (3, 1), done.stdout + done.stderr


def test_round_row_carries_scheme(repo, tmp_path):
    _write(repo, GRAPH, _graph(300))
    _write(repo, "src/app.py", "x = 7\n")

    done, _ = _claude_round(repo, tmp_path)

    review = json.loads((tmp_path / "w" / "review.json").read_text(encoding="utf-8"))
    row = rl.status(str(repo), "T1")["rounds"][-1]
    assert (done.returncode, review["bundle_scheme"], row["bundle_scheme"],
            _check(repo).returncode) == (0, review_patch.BUNDLE_SCHEME,
                                         review_patch.BUNDLE_SCHEME, 0), done.stderr
