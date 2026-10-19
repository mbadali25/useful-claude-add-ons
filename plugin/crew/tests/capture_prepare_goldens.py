"""Capture the pre-cut goldens for `review_run.py --prepare` (L-0726).

    python3 capture_prepare_goldens.py [--rev REV] [--out DIR]

Reads `commands/review.md` as it was at REV (default SNIPPET_REV, the last
commit that still carried the shell snippets), builds each scenario of
`review_fixtures.PREPARE_SCENARIOS` in a temp directory, runs the snippets in
`bash` there with a fixed scratch path, and writes what they produced to
`golden/prepare/<scenario>/`:

  changed.txt, context.txt   the files the snippets wrote
  prompt.txt                 the prompt, with the contract (`review_prompt.py`'s
                             output, which moves with the standards set and is
                             tested on its own) replaced by CONTRACT_MARK
  manifest.json              the bundle manifest
  parts.sha256               `<sha256>  <part name>` for each bundle part
  bundle.patch               the parts joined, only when small enough to read
  facts.json                 the values the snippets echoed
  stderr.txt, stdout.txt     what the snippets printed
  exit.txt                   the snippets' exit status

The temp root is replaced by `<ROOT>` everywhere. Run twice and diff: the
output must not change (the test does exactly that). The probe lines
(`review.md:324-326`) are not run: no scenario asks Codex anything.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import context  # noqa: F401  pylint: disable=unused-import
import review_fixtures as fx

SNIPPET_REV = "1e1db88a3"
CONTRACT_MARK = "<<CONTRACT>>"
BUNDLE_PATCH_LIMIT = 20_000
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "prepare")
# 1-based inclusive line ranges of review.md at SNIPPET_REV: the ticket line,
# the base block, the Step 2 resolution block, the bundle-to-prompt block.
RANGES = ((21, 22), (123, 173), (267, 307), (327, 429))


def snippet_script(markdown):
    lines = markdown.split("\n")
    parts = ["mkdir -p .work/review", f'SCRATCH={fx.PREPARE_SCRATCH}; mkdir -p "$SCRATCH"']
    for number, (first, last) in enumerate(RANGES):
        parts.append("\n".join(lines[first - 1:last]))
        if number == 2:
            parts.append("PROBE_STATUS=; PROBE_DETAIL=")
    return "\n".join(parts) + "\n"


def review_md_at(rev):
    return subprocess.run(
        ["git", "show", f"{rev}:plugin/crew/commands/review.md"], check=True,
        capture_output=True, text=True, encoding="utf-8").stdout


def _text(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def capture(scenario, markdown, work):
    """{file name: text} for `scenario`, built and run under `work`."""
    root = fx.build_prepare_repo(work / "repo", scenario)
    env = fx.prepare_env(work / "fakes", work / "home")
    script = work / "snippets.sh"
    script.write_text(snippet_script(markdown), encoding="utf-8", newline="\n")
    done = subprocess.run(["bash", str(script)], cwd=root, env=env, capture_output=True,
                          text=True, encoding="utf-8", stdin=subprocess.DEVNULL, check=False)
    out = {"exit.txt": f"{done.returncode}\n"}
    norm = lambda text: fx.normalise_root(text, root)  # noqa: E731
    facts = {}
    for line in done.stdout.splitlines():
        found = re.match(r"authors=(.*?) source=(.*?) eligible=(.*)$", line)
        if found:
            facts.update(authors=found[1], author_source=found[2], eligible=found[3])
        found = re.match(r"record=(\d+) base=(\d+) branch=(.*)$", line)
        if found:
            facts.update(record=int(found[1]), base_at=int(found[2]), branch=found[3])
    base = re.search(r"^scope-base: ([0-9a-f]+)", done.stderr, re.M)
    if base:
        facts["base"] = base[1]
    out["facts.json"] = json.dumps(facts, indent=2, sort_keys=True) + "\n"
    out["stderr.txt"] = norm(done.stderr)
    out["stdout.txt"] = norm(done.stdout)
    scratch = root / fx.PREPARE_SCRATCH
    if not (scratch / "changed.txt").exists():
        return out
    out["changed.txt"] = _text(scratch / "changed.txt")
    out["context.txt"] = _text(scratch / "context.txt")
    out["manifest.json"] = norm(_text(scratch / "manifest.json"))
    contract = _text(scratch / "contract.txt").rstrip("\n")
    prompt = _text(scratch / "prompt.txt")
    assert contract in prompt, "the contract is not in the prompt verbatim"
    out["prompt.txt"] = norm(prompt.replace(contract, CONTRACT_MARK, 1))
    names, joined, rows = [], [], []
    parts_dir = scratch / "diff.txt.parts"
    for name in sorted(os.listdir(parts_dir)):
        data = (parts_dir / name).read_bytes()
        rows.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        joined.append(data.decode("utf-8"))
        names.append(name)
    out["parts.sha256"] = "".join(rows)
    if sum(len(j) for j in joined) <= BUNDLE_PATCH_LIMIT:
        out["bundle.patch"] = "".join(joined)
    return out


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rev", default=SNIPPET_REV)
    parser.add_argument("--out", default=GOLDEN)
    args = parser.parse_args(argv)
    markdown = review_md_at(args.rev)
    for scenario in fx.PREPARE_SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            files = capture(scenario, markdown, Path(tmp))
        folder = os.path.join(args.out, scenario)
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
        for name, text in files.items():
            with open(os.path.join(folder, name), "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        print(f"{scenario}: {', '.join(sorted(files))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
