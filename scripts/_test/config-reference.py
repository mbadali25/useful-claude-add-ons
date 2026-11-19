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

CONFIG.md is generated WHOLE (L-0725): a one-byte edit anywhere in it, a deleted
file and a changed default are all stale. So are the four R-C2 files in
`plugin/crew/docs/configuration/` (the two blanks, `keys.json` and
`template.annotated.md`), and a `crew_keys.BLANK_EXCLUDED` that breaks the
blank rules (R1, R2, a blank reason, an exclusion outside the layer) stops the
generator with exit 2.

Must-allow: an unchanged copy, a CRLF checkout, and a machine-global config in
HOME (the generator reads no config file, so the output is the same on every
machine).

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
CONF_DIR = os.path.join("plugin", "crew", "docs", "configuration")
CONF_FILES = tuple(os.path.join(CONF_DIR, name) for name in (
    "config.blank.json", "global.blank.json", "keys.json", "template.annotated.md"))
# `crew_config` takes four default blocks from `crew_upgrade`, so the defaults
# are not all in SCRIPTS.
UPGRADE = os.path.join("plugin", "crew", "skills", "crew-graph", "scripts")
TIMEOUT = 300  # seconds for one generator run (PYTHON-07)


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def build(tmp):
    """The generator, its six outputs and crew's scripts, copied into `tmp`."""
    for rel in (GEN, REFERENCE, CONFIG_MD) + CONF_FILES:
        os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
        shutil.copy2(os.path.join(REPO, rel), os.path.join(tmp, rel))
    for rel in (SCRIPTS, UPGRADE):
        shutil.copytree(os.path.join(REPO, rel), os.path.join(tmp, rel),
                        ignore=shutil.ignore_patterns("__pycache__", "_test"))


def edit(tmp, rel, old, new):
    path = os.path.join(tmp, rel)
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    if "\r\n" in text:
        # A CRLF copy (an autocrlf checkout, or `_crlf`): match and write in its
        # own line endings, so a multi-line `old` still matches and the copy
        # stays CRLF.
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert text.count(old) == 1, f"fixture edit not unique in {rel}: {old!r}"
    text = text.replace(old, new)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def run_gen(tmp, home=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
        env["USERPROFILE"] = home
    done = subprocess.run([sys.executable, "-I", os.path.join(tmp, GEN), "--check"],
                          capture_output=True, text=True, check=False, env=env,
                          timeout=TIMEOUT)
    return done.returncode, done.stdout, done.stderr


def run_gate(tmp):
    problems = []
    CHECKER.check_config_reference(problems.append, root=tmp)
    return problems


def _one_byte(tmp):
    edit(tmp, REFERENCE, "## Coming (not in code yet)", "## Coming (not in code yet).")


def _crlf(tmp):
    """Both outputs as a `core.autocrlf=true` checkout holds them: the same text,
    every line ending CRLF. The committed blobs are LF, so this is a checkout
    artefact and never a stale reference."""
    for rel in (REFERENCE, CONFIG_MD) + CONF_FILES:
        path = os.path.join(tmp, rel)
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read().replace("\r\n", "\n").replace("\n", "\r\n")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)


def _crlf_one_byte(tmp):
    _crlf(tmp)
    _one_byte(tmp)


def _default_changed(tmp):
    edit(tmp, os.path.join(SCRIPTS, "crew_state.py"), '"maxDispatches": 3,', '"maxDispatches": 4,')


def _table_hand_edit(tmp):
    edit(tmp, CONFIG_MD, "| `pm.maxDispatches` | both |", "| `pm.maxDispatches` | repo |")


def _preamble_one_byte(tmp):
    edit(tmp, CONFIG_MD, "## The two layers", "## The two layers.")


def _last_byte(tmp):
    path = os.path.join(tmp, CONFIG_MD)
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + " ")


def _config_md_deleted(tmp):
    os.remove(os.path.join(tmp, CONFIG_MD))


def _conf_one_byte(name, old, new):
    def sabotage(tmp):
        edit(tmp, os.path.join(CONF_DIR, name), old, new)
    return sabotage


def _conf_deleted(tmp):
    os.remove(os.path.join(tmp, CONF_DIR, "keys.json"))


def _blank_key_added(tmp):
    edit(tmp, os.path.join(CONF_DIR, "config.blank.json"), '{\n  "schema"',
         '{\n  "zzHandAdded": true,\n  "schema"')


def _crlf_blank_key_added(tmp):
    """The multi-line edit above on a CRLF copy: `edit` matches in the copy's
    own line endings, so the row cannot fail on its fixture before the
    generator runs."""
    _crlf(tmp)
    _blank_key_added(tmp)


_KEYS = os.path.join(SCRIPTS, "crew_keys.py")
_LAYERS_LINE = '\nBLANK_LAYERS = ("repo", "machine")'


def _keys_line_before_layers(tmp, line):
    edit(tmp, _KEYS, _LAYERS_LINE, "\n" + line + _LAYERS_LINE)


def _shadowing_back(tmp):
    """Sabotage: `dev.provider` back in the repo blank, the shadowing D2 removed."""
    edit(tmp, _KEYS, '"dev.provider", "dev.fallback", "dev.roles",', '"dev.fallback", "dev.roles",')


def _blank_reason(tmp):
    _keys_line_before_layers(tmp, 'BLANK_EXCLUDED["repo"]["autopilot.mode"] = "  "')


def _exclusion_not_in_registry(tmp):
    _keys_line_before_layers(tmp, 'BLANK_EXCLUDED["machine"]["zz.nokey"] = "a reason"')


def _exclusion_outside_layer(tmp):
    _keys_line_before_layers(tmp, 'BLANK_EXCLUDED["machine"]["scope.mode"] = "a reason"')


def _personal_back_in_machine(tmp):
    edit(tmp, _KEYS, '"machine": {key: REASON_PERSONAL for key in _PERSONAL},',
         '"machine": {key: REASON_PERSONAL for key in _PERSONAL if key != "autopilot.mode"},')


def _import_raises(tmp):
    path = os.path.join(tmp, SCRIPTS, "crew_keys.py")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('raise ImportError("sabotaged crew_keys")\n')


_NONPROD_SINCE = '"open-table", since="1.1.10", source=_S + "crew_unattended.py",'
_NONPROD_TYPE = '\n        type_="object: environment name -> {profile, identity, region?}"),'


def _row_without_since(tmp):
    edit(tmp, os.path.join(SCRIPTS, "crew_keys.py"), _NONPROD_SINCE,
         '"open-table", source=_S + "crew_unattended.py",')


def _row_without_values(tmp):
    edit(tmp, os.path.join(SCRIPTS, "crew_keys.py"), _NONPROD_TYPE, "),")


# (name, sabotage, expected exit, text the generator must print, text the gate must print)
MUST_BLOCK = [
    ("reference edited by one byte", _one_byte, 1,
     "stale: docs/guides/crew/src/configuration-reference.md", "configuration-reference.md"),
    ("a CRLF checkout of the reference edited by one byte", _crlf_one_byte, 1,
     "stale: docs/guides/crew/src/configuration-reference.md", "configuration-reference.md"),
    ("a default changed in crew_state.py", _default_changed, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("a hand edit inside a CONFIG.md table row", _table_hand_edit, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("a one-byte edit in CONFIG.md's preamble", _preamble_one_byte, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("one byte appended to CONFIG.md", _last_byte, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("CONFIG.md deleted", _config_md_deleted, 1,
     "stale: plugin/crew/CONFIG.md", "CONFIG.md"),
    ("the generator's import raises", _import_raises, 2,
     "sabotaged crew_keys", "sabotaged crew_keys"),
    ("a KEY_META row without its arrival version", _row_without_since, 2,
     "no arrival version", "no arrival version"),
    ("an open-table row without allowed values", _row_without_values, 2,
     "no allowed values", "no allowed values"),
    # R-C2: the four files in plugin/crew/docs/configuration/.
    ("config.blank.json edited by one byte",
     _conf_one_byte("config.blank.json", '"verifyGate": true', '"verifyGate": false'), 1,
     "stale: plugin/crew/docs/configuration/config.blank.json", "config.blank.json"),
    ("global.blank.json edited by one byte",
     _conf_one_byte("global.blank.json", '"maxDispatches": 3', '"maxDispatches": 4'), 1,
     "stale: plugin/crew/docs/configuration/global.blank.json", "global.blank.json"),
    ("keys.json edited by one byte",
     _conf_one_byte("keys.json", '"generatedBy"', '"generatedby"'), 1,
     "stale: plugin/crew/docs/configuration/keys.json", "keys.json"),
    ("template.annotated.md edited by one byte",
     _conf_one_byte("template.annotated.md", "# crew configuration blanks",
                    "# crew configuration blanks."), 1,
     "stale: plugin/crew/docs/configuration/template.annotated.md", "template.annotated.md"),
    ("keys.json deleted", _conf_deleted, 1,
     "stale: plugin/crew/docs/configuration/keys.json", "keys.json"),
    ("a key added to config.blank.json by hand", _blank_key_added, 1,
     "stale: plugin/crew/docs/configuration/config.blank.json", "config.blank.json"),
    ("a CRLF checkout of config.blank.json with a key added by hand", _crlf_blank_key_added, 1,
     "stale: plugin/crew/docs/configuration/config.blank.json", "config.blank.json"),
    ("dev.provider removed from BLANK_EXCLUDED['repo']", _shadowing_back, 2,
     "blank R1: dev.provider", "blank R1: dev.provider"),
    ("a blank exclusion reason for autopilot.mode", _blank_reason, 2,
     "no exclusion reason: repo autopilot.mode", "no exclusion reason"),
    ("an exclusion naming a key not in the registry", _exclusion_not_in_registry, 2,
     "bad exclusion: machine zz.nokey", "bad exclusion"),
    ("an exclusion naming a key outside its layer", _exclusion_outside_layer, 2,
     "bad exclusion: machine scope.mode", "bad exclusion"),
    ("autopilot.mode dropped from BLANK_EXCLUDED['machine']", _personal_back_in_machine, 2,
     "blank R2: autopilot.mode", "blank R2"),
]


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
                         ("an unchanged copy checked out with CRLF line endings", _crlf)):
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
            json.dump({"qa": {"provider": "codex"}, "pm": {"maxDispatches": 9}}, fh)
        got, out, err = run_gen(tmp, home=home)
        plain = run_gen(tmp)
        ok = got == 0 and (got, out, err) == plain
        print(f"  {'ok  ' if ok else 'FAIL'} must-allow: a machine-global config in HOME "
              f"(exit {got})")
        if not ok:
            failures.append(f"HOME config: exit {got}, stdout {out!r}, stderr {err!r}")

    with tempfile.TemporaryDirectory() as tmp:
        build(tmp)
        shutil.rmtree(os.path.join(tmp, CONF_DIR))
        write = subprocess.run([sys.executable, "-I", os.path.join(tmp, GEN), "--write"],
                               capture_output=True, text=True, check=False, timeout=TIMEOUT)
        got, out, err = run_gen(tmp)
        ok = write.returncode == 0 and got == 0
        print(f"  {'ok  ' if ok else 'FAIL'} must-allow: --write recreates a missing "
              f"configuration directory (exit {got})")
        if not ok:
            failures.append(f"--write mkdir: {write.stderr!r}; then exit {got}, {out!r} {err!r}")

    with tempfile.TemporaryDirectory() as tmp:
        build(tmp)
        _default_changed(tmp)
        write = subprocess.run([sys.executable, "-I", os.path.join(tmp, GEN), "--write"],
                               capture_output=True, text=True, check=False, timeout=TIMEOUT)
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
