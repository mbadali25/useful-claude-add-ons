#!/usr/bin/env python3
"""Must-fail / must-pass suite for check-marketplace.py's check_diagram_embeds.

crew_diagrams.py writes each diagram into the README nearest its anchors
between `crew-diagrams` markers. The check fails when a section differs from
what `embed` would write now (a hand edit, a source changed and not
re-embedded), when markers are malformed, and when a source cannot be read.
Each case builds a throwaway root, so nothing here reads or writes the real
repository's READMEs or diagrams.

Run: python3 scripts/_test/check-diagram-embeds.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-marketplace.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()
SOURCE = ("%% Generated from repo@abc1234 on 2026-10-04. Verify before trusting.\n"
          "%% Anchors: plugin/x/a.py\n%% Purpose: How x flows.\n"
          "flowchart LR\n  a -->|go| b\n")


def _write(root, rel, text, binary=False):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if binary else "w", **({} if binary else
                                               {"encoding": "utf-8", "newline": "\n"})) as fh:
        fh.write(text)


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def _embed(root):
    """Write the sections with the shipped generator, as a user would."""
    with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
        return CHECKER.load_crew_diagrams().main(["embed", "--root", root])


def run(mutate) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "README.md", "# root\n")
        _write(tmp, "plugin/x/README.md", "# x\n\nProse.\n")
        _write(tmp, "plugin/x/a.py", "a\n")
        _write(tmp, "docs/diagrams/data-flow-x.mmd", SOURCE)
        if _embed(tmp) != 0:
            return ["fixture: embed refused"]
        mutate(tmp)
        old_root, CHECKER.ROOT = CHECKER.ROOT, tmp
        problems: list[str] = []
        try:
            CHECKER.check_diagram_embeds(problems.append)
        finally:
            CHECKER.ROOT = old_root
        return problems


def _replace(rel, old, new):
    def mutate(root):
        text = _read(root, rel)
        assert old in text, (rel, old)
        _write(root, rel, text.replace(old, new))
    return mutate


def _restored(root):
    """Hand-edit the block, then put it back: green again."""
    _replace("plugin/x/README.md", "|go|", "|hand edit|")(root)
    _replace("plugin/x/README.md", "|hand edit|", "|go|")(root)


# (name, mutate, expected substrings in the single problem; None = must pass)
CASES = (
    ("embeds match their sources", lambda root: None, None),
    ("a hand-edited block", _replace("plugin/x/README.md", "|go|", "|hand edit|"),
     ("plugin/x/README.md", "data-flow-x")),
    ("a hand edit, restored", _restored, None),
    ("a source changed and not re-embedded",
     _replace("docs/diagrams/data-flow-x.mmd", "|go|", "|went|"),
     ("plugin/x/README.md", "data-flow-x")),
    ("an end marker deleted",
     _replace("plugin/x/README.md", "<!-- crew-diagrams:end -->", ""),
     ("plugin/x/README.md", "marker")),
    ("an unreadable source",
     lambda root: _write(root, "docs/diagrams/bad.mmd", b"\xff\xfe bad \xc3", binary=True),
     ("bad.mmd",)),
    ("a README never embedded is pending, not a failure",
     lambda root: (_write(root, "plugin/y/README.md", "# y\n"), _write(root, "plugin/y/b.py", "b\n"),
                   _write(root, "docs/diagrams/process-y.mmd",
                          SOURCE.replace("plugin/x/a.py", "plugin/y/b.py"))),
     None),
    ("prose edited outside the markers is not drift",
     _replace("plugin/x/README.md", "Prose.", "Prose, edited."), None),
)


def main() -> int:
    failed = 0
    for name, mutate, want in CASES:
        problems = run(mutate)
        if want is None:
            ok = problems == []
        else:
            ok = len(problems) == 1 and all(w in problems[0] for w in want)
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {'must-pass' if want is None else 'must-fail'} {name}"
              + ("" if ok else f": got {problems}"))
    # main() wiring: the check must run, not just exist.
    wired = "check_diagram_embeds(fail)" in inspect.getsource(CHECKER.main)
    failed += not wired
    print(f"  {'ok  ' if wired else 'FAIL'} main() calls check_diagram_embeds")
    print(f"check-diagram-embeds: {len(CASES) + 1 - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
