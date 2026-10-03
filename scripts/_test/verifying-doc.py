#!/usr/bin/env python3
"""Must-fail / must-pass suite for check-marketplace.py's check_verifying_doc.

VERIFYING.md tells people and agents which commands prove a change. The check
fails when it names a repository path that does not exist. Each case builds a
throwaway root, so nothing here reads or writes the real repository.

Run: python3 scripts/_test/verifying-doc.py
"""

from __future__ import annotations

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
FILES = ("scripts/check.py", "_verify/smoke.sh", ".github/workflows/ci.yml", "AGENTS.md")


def run(doc: str | None, readme: str = "", agents: str = "x\n") -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "README.md"), "w", encoding="utf-8") as fh:
            fh.write(readme)
        for rel in FILES:
            os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write(agents)
        if doc is not None:
            with open(os.path.join(tmp, "VERIFYING.md"), "w", encoding="utf-8") as fh:
                fh.write(doc)
        old_root, CHECKER.ROOT = CHECKER.ROOT, tmp
        problems: list[str] = []
        try:
            CHECKER.check_verifying_doc(problems.append)
        finally:
            CHECKER.ROOT = old_root
        return problems


GOOD = """# Verifying
Run `python3 scripts/check.py`, then `bash _verify/smoke.sh`. See `AGENTS.md`
and [the workflows](.github/workflows/) and [CI](.github/workflows/ci.yml#L3).

```bash
python3 scripts/check.py   # a comment naming nothing/real.py is ignored
```

Ignored: `/crew:verify`, `/dev/null`, `/no/such/absolute.sh`, `scripts/_test/<name>.py`,
`plugin/*/x`, `https://example.com/a/b`, `$CLAUDE_PLUGIN_ROOT/hooks/x.py`, `--flag/value`.
A sentence ending in a path: `scripts/check.py`. A [titled link](_verify/smoke.sh "t").

- ```bash
  bash _verify/smoke.sh
  ```

~~~
python3 scripts/check.py
~~~

Prose after the fences, with and/or in it, is not a path.
"""

# (name, doc, expected substring in the single problem; None = must pass)
CASES = (
    ("every named path exists", GOOD, None),
    ("a missing script in an inline span", GOOD + "\n`python3 scripts/gone.py`\n",
     "`scripts/gone.py`"),
    ("a missing script in a fenced block", GOOD + "\n```\nbash _verify/gone.sh\n```\n",
     "`_verify/gone.sh`"),
    ("a misspelt top-level directory", GOOD + "\n`python3 script/check.py`\n",
     "`script/check.py`"),
    ("a missing link target", GOOD + "\n[gone](docs/gone.md)\n", "`docs/gone.md`"),
    ("a missing link target with an anchor", GOOD + "\n[gone](docs/gone.md#part)\n",
     "`docs/gone.md`"),
    ("a missing path with a trailing dot", GOOD + "\nRun `scripts/gone.py.`\n",
     "`scripts/gone.py`"),
    ("a missing path in a list-item fence", GOOD + "\n- ```bash\n  bash _verify/gone.sh\n  ```\n",
     "`_verify/gone.sh`"),
    ("a missing path in a tilde fence", GOOD + "\n~~~\nbash _verify/gone.sh\n~~~\n",
     "`_verify/gone.sh`"),
    ("a missing path in a span after a list-item fence closed",
     GOOD + "\n- ```\n  x\n  ```\n\n`scripts/gone.py`\n", "`scripts/gone.py`"),
    ("a missing root doc", GOOD + "\nSee `CLAUDE.md`.\n", "`CLAUDE.md`"),
    ("a fence that never closes", GOOD + "\n```\nbash _verify/smoke.sh\n\nProse.\n",
     "never closes"),
    ("a shorter run inside a longer fence does not close it",
     GOOD + "\n````\n```\nbash _verify/gone.sh\n````\n", "`_verify/gone.sh`"),
    ("a missing path in a numbered-list fence", GOOD + "\n1. ```\n   bash _verify/gone.sh\n   ```\n",
     "`_verify/gone.sh`"),
    ("a line opening with an inline triple-backtick span is not a fence",
     GOOD + "\n```x``` inline\n`scripts/gone.py`\n", "`scripts/gone.py`"),
    ("a missing titled link target", GOOD + '\n[x](docs/gone.md "t")\n', "`docs/gone.md`"),
    ("a missing path in parentheses", GOOD + "\n`(scripts/gone.py)`\n", "`scripts/gone.py`"),
    ("a missing directory with a trailing slash", GOOD + "\n`docs/`\n", "`docs`"),
    ("the page is missing and README links to it", None, "VERIFYING.md: missing - README.md"),
    ("the page is missing and nothing links to it", None, None),
    ("the page is missing and only AGENTS.md links to it", None, "VERIFYING.md: missing - AGENTS.md"),
)


def main() -> int:
    failed = 0
    for name, doc, want in CASES:
        link = "[VERIFYING.md](VERIFYING.md)\n"
        problems = run(doc, link if "and README" in name else "",
                       link if "only AGENTS.md" in name else "x\n")
        if want is None:
            ok = problems == []
        else:
            ok = len(problems) == 1 and want in problems[0]
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {'must-pass' if want is None else 'must-fail'} {name}"
              + ("" if ok else f": got {problems}"))
    # main() wiring: the check must run, not just exist.
    wired = "check_verifying_doc(fail)" in inspect.getsource(CHECKER.main)
    failed += not wired
    print(f"  {'ok  ' if wired else 'FAIL'} main() calls check_verifying_doc")
    print(f"verifying-doc: {len(CASES) + 1 - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
