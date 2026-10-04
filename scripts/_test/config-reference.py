#!/usr/bin/env python3
"""Sabotage suite for crew's generated configuration reference (T-0048).

Covers `docs/guides/crew/src/config_reference.py --check` and the gate check
that runs it, `check_config_reference` in `scripts/check-marketplace.py`.
Every case copies the files the generator reads into a temp directory, edits
the copy, and runs the COPY's generator against it. Nothing touches this
repository's own files.

Must-block: each one is a way the committed reference stops describing the
code, and each must turn both the generator's `--check` and the gate red. The
generator failing to import is in this list on purpose: a check that could not
run compared nothing, and must never read as current.

Must-allow: an unchanged copy, an edit to CONFIG.md's hand-written prose, and a
machine-global config in HOME (the generator reads no config file, so the
output is the same on every machine).

Run: python3 scripts/_test/config-reference.py
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
REPO = os.path.dirname(os.path.dirname(HERE))
TARGET = os.path.join(REPO, "scripts", "check-marketplace.py")
GEN = os.path.join("docs", "guides", "crew", "src", "config_reference.py")
REFERENCE = os.path.join("docs", "guides", "crew", "src", "configuration-reference.md")
CONFIG_MD = os.path.join("plugin", "crew", "CONFIG.md")
SCRIPTS = os.path.join("plugin", "crew", "hooks", "scripts")
# `crew_config` takes four default blocks from `crew_upgrade`, so the defaults
# are not all in SCRIPTS.
UPGRADE = os.path.join("plugin", "crew", "skills", "crew-graph", "scripts")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def build(tmp):
    """The generator, its two outputs and crew's scripts, copied into `tmp`."""
    for rel in (GEN, REFERENCE, CONFIG_MD):
        os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
        shutil.copy2(os.path.join(REPO, rel), os.path.join(tmp, rel))
    for rel in (SCRIPTS, UPGRADE):
        shutil.copytree(os.path.join(REPO, rel), os.path.join(tmp, rel),
                        ignore=shutil.ignore_patterns("__pycache__", "_test"))


def edit(tmp, rel, old, new):
    path = os.path.join(tmp, rel)
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert text.count(old) == 1, f"fixture edit not unique in {rel}: {old!r}"
    text = text.replace(old, new)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def run_gen(tmp, home=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
        env["USERPROFILE"] = home
    done = subprocess.run([sys.executable, "-I", os.path.join(tmp, GEN), "--check"],
                          capture_output=True, text=True, check=False, env=env)
    return done.returncode, done.stdout, done.stderr


def run_gate(tmp):
    problems = []
    CHECKER.check_config_reference(problems.append, root=tmp)
    return problems


def _one_byte(tmp):
    edit(tmp, REFERENCE, "## Coming (not in code yet)", "## Coming (not in code yet).")


def _default_changed(tmp):
    edit(tmp, os.path.join(SCRIPTS, "crew_state.py"), '"quietLines": 8,', '"quietLines": 9,')


def _block_hand_edit(tmp):
    edit(tmp, CONFIG_MD, "| `pm.maxLines` | both |", "| `pm.maxLines` | repo |")


def _no_end_marker(tmp):
    edit(tmp, CONFIG_MD, "<!-- generated:config-keys-repo end -->", "")


def _import_raises(tmp):
    path = os.path.join(tmp, SCRIPTS, "crew_keys.py")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('raise ImportError("sabotaged crew_keys")\n')


# (name, sabotage, expected exit, text the generator must print, text the gate must print)
MUST_BLOCK = [
    ("reference edited by one byte", _one_byte, 1,
     "stale: docs/guides/crew/src/configuration-reference.md", "configuration-reference.md"),
    ("a default changed in crew_state.py", _default_changed, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("a hand edit inside CONFIG.md's block", _block_hand_edit, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("CONFIG.md's end marker missing", _no_end_marker, 2,
     "generated:config-keys-repo end", "generated:config-keys-repo end"),
    ("the generator's import raises", _import_raises, 2,
     "sabotaged crew_keys", "sabotaged crew_keys"),
]


def _prose_edit(tmp):
    edit(tmp, CONFIG_MD, "## 12. Drift found while deriving this",
         "## 12. Drift found while deriving this (edited)")


def _unchanged(_tmp):
    return None


def run():
    failures = []
    for name, sabotage, code, gen_text, gate_text in MUST_BLOCK:
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp)
            sabotage(tmp)
            got, out, err = run_gen(tmp)
            gate = run_gate(tmp)
            ok = (got == code and gen_text in out + err and gate
                  and any(gate_text in p for p in gate))
            if name == "a default changed in crew_state.py":
                ok = ok and "configuration-reference.md" in out
            print(f"  {'ok  ' if ok else 'FAIL'} must-block: {name} (exit {got})")
            if not ok:
                failures.append(f"{name}: exit {got}, stdout {out!r}, stderr {err!r}, "
                                f"gate {gate!r}")

    for name, change in (("an unchanged copy", _unchanged),
                         ("an edit to CONFIG.md prose outside the block", _prose_edit)):
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp)
            change(tmp)
            got, out, err = run_gen(tmp)
            gate = run_gate(tmp)
            ok = got == 0 and not gate
            print(f"  {'ok  ' if ok else 'FAIL'} must-allow: {name} (exit {got})")
            if not ok:
                failures.append(f"{name}: exit {got}, stdout {out!r}, stderr {err!r}, "
                                f"gate {gate!r}")

    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
        build(tmp)
        os.makedirs(os.path.join(home, ".claude", "crew"))
        with open(os.path.join(home, ".claude", "crew", "config.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"qa": {"provider": "codex"}, "pm": {"maxLines": 3}}, fh)
        got, out, err = run_gen(tmp, home=home)
        ok = got == 0
        print(f"  {'ok  ' if ok else 'FAIL'} must-allow: a machine-global config in HOME "
              f"(exit {got})")
        if not ok:
            failures.append(f"HOME config: exit {got}, stdout {out!r}, stderr {err!r}")

    with tempfile.TemporaryDirectory() as tmp:
        build(tmp)
        _default_changed(tmp)
        write = subprocess.run([sys.executable, "-I", os.path.join(tmp, GEN), "--write"],
                               capture_output=True, text=True, check=False)
        got, out, err = run_gen(tmp)
        ok = write.returncode == 0 and got == 0
        print(f"  {'ok  ' if ok else 'FAIL'} must-allow: --write makes a stale copy current "
              f"(exit {got})")
        if not ok:
            failures.append(f"--write: {write.stderr!r}; then exit {got}, {out!r} {err!r}")

    if failures:
        print("\nconfig-reference suite FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("config-reference suite: all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
