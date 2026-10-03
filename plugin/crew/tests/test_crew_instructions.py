"""crew_instructions.py: generated `.claude/rules/`, AGENTS.md and Codex files.

Budgets are asserted on generator output for oversized inputs, drift is
asserted by editing a source after generation, and the Codex hooks file is
asserted to come from the same table as the Claude registration.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_instructions as ci
from context_fixtures import make_repo
from crew_common import read_text


def _big_repo(tmp_path, count=3, marks=40):
    subs = {f"sub{i:03d}": ([f"s{i}/a.py", f"s{i}/b.py", f"s{i}/c.py"],
                            [f"landmine {i}.{m} " + "w" * 80 for m in range(marks)])
            for i in range(count)}
    return make_repo(tmp_path, subsystems=subs)


def test_every_rules_file_is_path_scoped_hashed_and_at_most_30_lines(tmp_path):
    root = _big_repo(tmp_path)

    problems, written = ci.rules(str(root))

    assert not problems
    assert len(written) == 3
    for rel in written:
        text = (root / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 30
        assert lines[:2] == ["---", "paths:"]
        assert '  - "s' in lines[2] and lines[2].endswith('/**"')
        assert "sha256=" in text and "crew:generated" in text


def test_rules_check_reports_no_drift_right_after_generation(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))

    assert ci.rules(str(root), check=True) == ([], [])


def test_rules_check_flags_a_stale_rule_when_its_note_changes(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))
    note = root / ".crew" / "codemap" / "sub001.md"
    note.write_text(note.read_text(encoding="utf-8") + "- a new landmine.\n", encoding="utf-8")

    problems, _ = ci.rules(str(root), check=True)

    assert problems == ["stale: " + os.path.join(".claude", "rules", "sub001.md")]
    assert ci.main(["rules", "--root", str(root), "--check"]) == 1


def test_rules_check_flags_an_orphan_and_leaves_hand_written_rules_alone(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))
    (root / ".crew" / "codemap" / "sub002.md").unlink()
    hand = root / ".claude" / "rules" / "mine.md"
    hand.write_text("---\npaths:\n  - x/**\n---\nmine\n", encoding="utf-8")

    problems, _ = ci.rules(str(root), check=True)

    assert problems == ["orphan: " + os.path.join(".claude", "rules", "sub002.md")]
    assert hand.read_text(encoding="utf-8").endswith("mine\n")


def test_agents_md_stays_within_80_lines_for_a_large_code_map(tmp_path):
    root = _big_repo(tmp_path, count=120, marks=1)

    problems, written = ci.agents(str(root))

    assert (problems, written) == ([], ["AGENTS.md"])
    assert len((root / "AGENTS.md").read_text(encoding="utf-8").splitlines()) <= 80


def test_agents_md_regeneration_preserves_the_keep_block(tmp_path):
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    path = root / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    start = text.index(ci.KEEP_START) + len(ci.KEEP_START)
    end = text.index(ci.KEEP_END)
    path.write_text(text[:start] + "\n- NEVER-PUSH-TO-MAIN\n" + text[end:], encoding="utf-8")
    (root / ".crew" / "codemap" / "sub000.md").unlink()

    ci.agents(str(root))

    after = path.read_text(encoding="utf-8")
    assert "- NEVER-PUSH-TO-MAIN" in after
    assert "`sub000`" not in after


def test_a_hand_written_agents_md_is_never_overwritten(tmp_path):
    root = _big_repo(tmp_path)
    (root / "AGENTS.md").write_text("# mine\n", encoding="utf-8")

    problems, written = ci.agents(str(root))

    assert written == [] and problems == ["hand-written, left alone: AGENTS.md"]
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# mine\n"


def _registrations(hooks):
    return sorted((event, entry.get("matcher")) for event, entries in hooks["hooks"].items()
                  for entry in entries)


def test_codex_hooks_and_claude_hooks_come_from_the_same_table():
    claude = ci.claude_hooks()
    codex = ci.codex_hooks("/opt/crew")

    expected = sorted((row["event"], row["matcher"]) for row in ci.HOOK_TABLE)
    assert sorted(set(_registrations(claude))) == sorted(set(expected))
    assert sorted((e, m and next(r["matcher"] for r in ci.HOOK_TABLE if r["codex"] == m and r["event"] == e))
                  for e, m in _registrations(codex)) == expected
    assert len(_registrations(claude)) == 2 * len(ci.HOOK_TABLE)


def test_every_codex_hook_has_a_windows_command_and_passes_the_codex_harness():
    for entries in ci.codex_hooks("/opt/crew")["hooks"].values():
        for entry in entries:
            hook = entry["hooks"][0]
            assert hook["command"].endswith("--harness codex")
            assert hook["commandWindows"].endswith("-Harness codex")
            assert "crew-context.ps1" in hook["commandWindows"]


def test_claude_entries_satisfy_the_marketplace_hook_command_rules():
    for entries in ci.claude_hooks()["hooks"].values():
        for entry in entries:
            hook = entry["hooks"][0]
            assert '"${CLAUDE_PLUGIN_ROOT}' in hook["command"]
            if hook.get("shell") == "powershell":
                assert hook["command"].rstrip().endswith("exit $LASTEXITCODE")


def test_the_registered_crew_context_rows_are_exactly_the_generated_ones():
    """hooks.json is hand-formatted, so this compares parsed rows: every
    crew-context registration is what `claude-hooks` prints, event by event,
    and nothing else registers crew-context."""
    path = os.path.join(os.path.dirname(os.path.abspath(ci.__file__)), os.pardir, "hooks.json")
    with open(path, encoding="utf-8") as handle:
        registered = json.load(handle)["hooks"]
    ours = {event: [row for row in rows if "crew-context" in json.dumps(row)]
            for event, rows in registered.items()}

    assert {e: rows for e, rows in ours.items() if rows} == ci.claude_hooks()["hooks"]


def test_codex_generation_writes_both_files_and_detects_drift(tmp_path):
    root = _big_repo(tmp_path)

    assert ci.codex(str(root), "/opt/crew")[1] == [os.path.join(".codex", "hooks.json"),
                                                   os.path.join(".codex", "config.toml")]
    assert ci.codex(str(root), "/opt/crew", check=True) == ([], [])
    config = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert 'project_doc_fallback_filenames = ["CLAUDE.md"]' in config
    # No real [profiles.*] table: measured on codex-cli 0.154.0, `profiles` is
    # on Codex's own project-local config denylist and is stripped whether the
    # project is trusted or not, so writing one here would be a no-op that
    # looks like enforcement. (A mention of the phrase in the explanatory
    # comment is fine; an actual table header is not.)
    assert not re.search(r"^\[profiles\.", config, re.MULTILINE)
    assert "codex-cli 0.154.0" in config
    assert json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert ci.codex(str(root), "/elsewhere", check=True)[0] == ["stale: " + os.path.join(".codex", "hooks.json")]


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    path = tmp_path / "codex"
    path.write_text("#!/bin/sh\n[ \"$1\" = --version ] && echo 'codex-cli 9.9.9' && exit 0\n"
                    "echo 'hooks                                    stable             true'\n",
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    # A bare POSIX shebang script has no extension Windows can execute at
    # all -- and `_codex_bin()` returns CREW_CODEX_BIN verbatim when it is
    # set (the PATH/PATHEXT search it does otherwise never runs), so
    # every `_run()` call against `path` on a real Windows host fails with
    # an OSError the probe correctly reports as "could not run", not a
    # defect in the probe. A `.cmd` companion, the same shape
    # review_fixtures.fake_reviewer_bin already uses for the same reason,
    # makes this fixture runnable on Windows too.
    cmd_path = tmp_path / "codex.cmd"
    cmd_path.write_text(
        '@echo off\r\n'
        'if "%1"=="--version" (echo codex-cli 9.9.9 & exit /b 0)\r\n'
        'echo hooks                                    stable             true\r\n',
        encoding="utf-8", newline="")
    monkeypatch.setenv("CREW_CODEX_BIN", str(cmd_path if os.name == "nt" else path))
    return path


def _toml_string(value):
    """`value` escaped for a TOML basic string. Windows burn-in, win-repo:
    every fixture below embeds a real filesystem path straight into
    `[projects."{path}"]` -- fine on POSIX, where `os.path.abspath` never
    emits a backslash, but a native Windows path (`C:\\Users\\...\\AppData\\
    Local\\Temp\\...`) carries plenty of them, and a bare backslash is not
    a value f-string interpolation escapes for TOML. `tomllib` reads `\\U`,
    `\\A`, `\\L`... as the start of a Unicode escape and rejects the whole
    file as malformed, so a fixture built to prove "trusted" instead proves
    "unknown" -- the trust probe correctly refusing TOML that was never
    valid, not a defect in it. Escaping only `\\` and `"` (the two characters
    a path can contain that TOML's basic-string grammar treats specially) is
    what a real `config.toml` write already does; `_project_trust_lookup_keys`
    compares against the UN-escaped path, so this only has to be reversible
    by TOML's own rules, not by anything crew's reader does."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _codex_home_trusting(tmp_path, monkeypatch, root, level="trusted", inline=False):
    """Point CODEX_HOME at a fresh, isolated directory recording `level` for
    `root` -- so a test never reads whatever trust state happens to be on the
    machine actually running it."""
    home = tmp_path / "codex-home"
    home.mkdir()
    path = _toml_string(os.path.abspath(str(root)))
    if inline:
        body = f'[projects]\n"{path}" = {{ trust_level = "{level}" }}\n'
    else:
        body = f'[projects."{path}"]\ntrust_level = "{level}"\n'
    (home / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def _codex_home_empty(tmp_path, monkeypatch):
    """CODEX_HOME exists but has never recorded any project trust."""
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def test_codex_probe_says_configured_not_proven_without_an_observed_invocation(tmp_path, fake_codex, monkeypatch):
    root = _big_repo(tmp_path)
    ci.codex(str(root), "/opt/crew")
    _codex_home_trusting(tmp_path, monkeypatch, root)

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert "hooks feature: enabled" in lines
    assert "project files: current" in lines
    assert any(l.startswith("project trust: trusted - ") for l in lines)
    assert "SubagentStart: configured, not proven" in lines


def test_codex_probe_reports_an_invocation_only_as_invoked(tmp_path, fake_codex, monkeypatch):
    root = _big_repo(tmp_path)
    _codex_home_trusting(tmp_path, monkeypatch, root)
    log = root / ".git" / "crew" / "context-log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"harness": "codex", "event": "SessionStart"}) + "\n", encoding="utf-8")

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert "SessionStart: hook invoked 1x under Codex (delivery to the model not measured)" in lines


def test_codex_probe_without_codex_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("CREW_CODEX_BIN", str(tmp_path / "nope"))

    assert ci.codex_probe(str(tmp_path), "/opt/crew") == ["codex: not installed - Codex parity not configured"]


# --- codex-probe: project trust is CLOSED, not merely unproven ---------------

def test_codex_trust_is_trusted_for_an_exploded_projects_entry(tmp_path, monkeypatch):
    root = _big_repo(tmp_path)
    _codex_home_trusting(tmp_path, monkeypatch, root)

    assert ci.codex_trust(str(root)) == (
        ci.TRUST_OK, f'trust_level = "trusted" for {os.path.abspath(str(root))} in '
                     f"{os.path.join(str(tmp_path / 'codex-home'), 'config.toml')}")


def test_codex_trust_is_trusted_for_the_inline_table_form(tmp_path, monkeypatch):
    root = _big_repo(tmp_path)
    _codex_home_trusting(tmp_path, monkeypatch, root, inline=True)

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_OK and "trusted" in detail


def test_codex_trust_is_closed_when_explicitly_untrusted(tmp_path, monkeypatch):
    root = _big_repo(tmp_path)
    _codex_home_trusting(tmp_path, monkeypatch, root, level="untrusted")

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_CLOSED and "untrusted" in detail


def test_codex_trust_is_closed_when_no_entry_was_ever_recorded(tmp_path, monkeypatch):
    root = _big_repo(tmp_path)
    _codex_home_empty(tmp_path, monkeypatch)

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_CLOSED
    assert "config.toml" in detail


def test_codex_trust_is_closed_when_codex_home_has_never_been_used(tmp_path, monkeypatch):
    """No CODEX_HOME env var and no ~/.codex -- the common fresh-machine case.
    Redirect HOME so this does not depend on whatever is on the machine
    actually running the suite. Windows burn-in, win-repo: `_codex_home()`
    falls back to `os.path.expanduser("~")`, and `ntpath.expanduser` (what
    runs there) checks `USERPROFILE` first and never looks at `HOME` at all
    -- setting only `HOME` leaves this test reading the REAL machine's
    `~/.codex`, not this fixture's empty one, on Windows. Both are set so
    the isolation holds under either `expanduser` implementation."""
    root = _big_repo(tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "empty-home"))
    (tmp_path / "empty-home").mkdir()

    state, _ = ci.codex_trust(str(root))

    assert state == ci.TRUST_CLOSED


def test_codex_trust_is_unknown_when_codex_home_is_set_but_missing(tmp_path, monkeypatch):
    root = _big_repo(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "does-not-exist"))

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_UNKNOWN and "does-not-exist" in detail


# --- W8 review fix #2: malformed TOML must never report "trusted" ----------

def _write_config_toml(tmp_path, monkeypatch, body):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def test_codex_trust_is_unknown_for_malformed_toml_even_with_a_trusted_entry(tmp_path, monkeypatch):
    """`broken =` (a key with no value) is not valid TOML. A real trust
    entry for `root` sits right above it in the same file, so the previous
    regex scanner reported TRUST_OK regardless -- the false "trusted" this
    fix closes."""
    root = _big_repo(tmp_path)
    path = _toml_string(os.path.abspath(str(root)))
    body = f'[projects."{path}"]\ntrust_level = "trusted"\n\nbroken =\n'
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_UNKNOWN
    assert "not valid TOML" in detail


def test_codex_trust_malformed_fallback_scanner_also_reports_unknown(tmp_path, monkeypatch):
    """Same fixture, but with `tomllib` unavailable (as on Python 3.8-3.10) --
    the fallback line scanner must independently refuse to call this
    trusted, not just tomllib."""
    root = _big_repo(tmp_path)
    monkeypatch.setattr(ci, "_tomllib", None)
    path = _toml_string(os.path.abspath(str(root)))
    body = f'[projects."{path}"]\ntrust_level = "trusted"\n\nbroken =\n'
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_UNKNOWN
    assert "broken =" in detail


def test_codex_trust_fallback_scanner_still_trusts_a_clean_file(tmp_path, monkeypatch):
    """The fallback path is not simply disabled -- a well-formed file with no
    unclassifiable line still resolves TRUST_OK without tomllib."""
    root = _big_repo(tmp_path)
    monkeypatch.setattr(ci, "_tomllib", None)
    path = _toml_string(os.path.abspath(str(root)))
    body = f'[projects."{path}"]\ntrust_level = "trusted"\n'
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(root))

    assert state == ci.TRUST_OK and "trusted" in detail


# --- Codex review (gpt-5.6-sol) findings #5/#6: fallback scanner grammar ----

def test_codex_trust_multiline_array_is_not_misread_as_malformed(tmp_path, monkeypatch):
    """A legal multi-line array's continuation lines carry no `=` at all --
    the previous fallback scanner (`_GENERIC_KV_RE`) required one on every
    line and reported the whole file UNKNOWN despite it being valid TOML.
    Checked against tomllib (the real parser, which already accepted this
    shape) and then again with tomllib forced unavailable, so the fallback
    scanner is shown to independently agree rather than merely not being
    exercised."""
    root = _big_repo(tmp_path)
    path = _toml_string(os.path.abspath(str(root)))
    body = (
        '[hooks]\n'
        'args = [\n'
        '  "one",\n'
        '  "two",\n'
        ']\n'
        f'[projects."{path}"]\n'
        'trust_level = "trusted"\n'
    )
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(root))
    assert state == ci.TRUST_OK and "trusted" in detail

    monkeypatch.setattr(ci, "_tomllib", None)
    state, detail = ci.codex_trust(str(root))
    assert state == ci.TRUST_OK and "trusted" in detail


def test_codex_trust_fallback_scanner_rejects_an_unterminated_string_value(tmp_path, monkeypatch):
    """`broken = "unterminated` has an `=` and *something* non-blank right
    after it -- exactly the shape the old `_GENERIC_KV_RE` (`\\S.*$`)
    accepted as a complete value, even though the string is never closed
    and a real parser rejects the file outright. A genuine trust entry
    sits earlier in the same file, so the previous scanner reported
    TRUST_OK regardless -- the false "trusted" this fix closes, the same
    way `broken =` (fix #2, above) already does for an empty RHS."""
    root = _big_repo(tmp_path)
    path = _toml_string(os.path.abspath(str(root)))
    body = (f'[projects."{path}"]\ntrust_level = "trusted"\n\n'
            'broken = "unterminated\n')
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(root))
    assert state == ci.TRUST_UNKNOWN
    assert "not valid TOML" in detail

    monkeypatch.setattr(ci, "_tomllib", None)
    state, detail = ci.codex_trust(str(root))
    assert state == ci.TRUST_UNKNOWN
    assert "unterminated" in detail


def test_scan_project_trust_accepts_a_multiline_array_directly(monkeypatch):
    text = ('args = [\n'
            '  "one",\n'
            '  "two",\n'
            ']\n'
            '[projects."/repo"]\n'
            'trust_level = "trusted"\n')

    level, matched, bad_line = ci._scan_project_trust(text, ["/repo"])

    assert (level, matched, bad_line) == ("trusted", "/repo", None)


def test_scan_project_trust_rejects_an_unterminated_string_value_directly():
    text = ('[projects."/repo"]\ntrust_level = "trusted"\n\n'
            'broken = "unterminated\n')

    _, _, bad_line = ci._scan_project_trust(text, ["/repo"])

    assert bad_line is not None
    # `bad_line` is reassigned via `nonlocal` inside a nested closure in
    # `_scan_project_trust` -- astroid does not trace that reassignment
    # into the function's inferred return type, so it infers `None` only
    # regardless of the `is not None` check just above (reproduced in
    # isolation: the same nonlocal-closure shape triggers E1135 even with
    # an `isinstance(bad_line, str)` guard immediately before the `in`).
    # pylint: disable-next=unsupported-membership-test
    assert "unterminated" in bad_line


def test_scan_project_trust_rejects_a_missing_comma_between_array_elements_directly():
    """A bare scalar with no trailing comma is legal TOML only as the
    array's LAST element -- `"one"` immediately followed by a bare `]` on
    the next line closes cleanly. `"one"` then `"two"]` (or `"two"` on a
    further line) with nothing between them but whitespace is a MISSING
    COMMA a real TOML parser rejects; the previous fallback scanner read a
    bare trailing scalar as unconditionally "fine, still open" regardless
    of what followed, so this read as an ordinary two-element array."""
    text = ('[projects."/repo"]\ntrust_level = "trusted"\n\n'
            'args = [\n'
            '  "one"\n'
            '  "two"\n'
            ']\n')

    _, _, bad_line = ci._scan_project_trust(text, ["/repo"])

    assert bad_line is not None
    # See the same disable a few tests up: astroid does not trace
    # `bad_line`'s `nonlocal` reassignment inside `_scan_project_trust`'s
    # nested closure into its inferred return type.
    # pylint: disable-next=unsupported-membership-test
    assert '"two"' in bad_line


def test_scan_project_trust_still_accepts_a_bare_last_element_before_a_lone_bracket():
    """The must-allow twin: a bare scalar (no trailing comma) IS valid when
    the very next content line is nothing but the closing `]` -- proving
    the missing-comma check above did not also break this legal shape."""
    text = ('[projects."/repo"]\ntrust_level = "trusted"\n\n'
            'args = [\n'
            '  "one",\n'
            '  "two"\n'
            ']\n')

    level, matched, bad_line = ci._scan_project_trust(text, ["/repo"])

    assert (level, matched, bad_line) == ("trusted", "/repo", None)


# --- W8 review fix #3: canonical (realpath) beats literal, Codex's own order

def test_codex_trust_prefers_the_canonical_path_over_a_symlinked_literal(tmp_path, monkeypatch):
    """A symlinked root: the literal (symlink) path is trusted, the
    canonical (realpath) target is untrusted. Codex looks up canonical
    before literal, so the overall answer must be untrusted, not trusted --
    the previous implementation returned whichever entry came first in the
    FILE, which this fixture writes in the trust-first order to prove the
    fix reads by lookup order, not file order."""
    real = tmp_path / "real-repo"
    real.mkdir()
    link = tmp_path / "link-to-repo"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")
    literal = os.path.abspath(str(link))
    canonical = os.path.realpath(str(link))
    body = (f'[projects."{_toml_string(literal)}"]\ntrust_level = "trusted"\n\n'
            f'[projects."{_toml_string(canonical)}"]\ntrust_level = "untrusted"\n')
    _write_config_toml(tmp_path, monkeypatch, body)

    state, detail = ci.codex_trust(str(link))

    assert state == ci.TRUST_CLOSED and "untrusted" in detail


def test_codex_trust_windows_paths_fold_case_insensitively(monkeypatch):
    monkeypatch.setattr(ci.os, "name", "nt")
    text = '[projects."C:\\\\Repos\\\\thing"]\ntrust_level = "trusted"\n'

    level, matched, bad_line = ci._scan_project_trust(text, ["c:\\repos\\thing"])

    assert (level, matched, bad_line) == ("trusted", "C:\\Repos\\thing", None)


def test_codex_probe_reports_a_closed_trust_gate_plainly_not_as_fine(tmp_path, fake_codex, monkeypatch):
    root = _big_repo(tmp_path)
    ci.codex(str(root), "/opt/crew")
    _codex_home_empty(tmp_path, monkeypatch)

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert any(l.startswith("project trust: missing trust - ") for l in lines)
    assert any(l.startswith("SessionStart: CLOSED - ") for l in lines)
    assert not any("configured, not proven" in l for l in lines)


def test_codex_probe_reports_unknown_trust_as_its_own_state(tmp_path, fake_codex, monkeypatch):
    root = _big_repo(tmp_path)
    ci.codex(str(root), "/opt/crew")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nope"))

    lines = ci.codex_probe(str(root), "/opt/crew")

    assert any(l.startswith("project trust: unknown - ") for l in lines)
    assert any(l.startswith("SessionStart: unknown - ") for l in lines)
    assert not any("CLOSED" in l or "configured, not proven" in l for l in lines)


# --- T6 review fixes ----------------------------------------------------------

def _sub(**over):
    base = {"name": "alpha", "file": ".crew/codemap/alpha.md", "paths": ["src/alpha/**"],
            "anchor": "abc1234", "body": "# alpha\n"}
    base.update(over)
    return base


@pytest.mark.parametrize("field, value", [
    ("paths", ["src/other/**"]), ("anchor", "def5678"),
    ("file", ".crew/codemap/renamed.md"), ("name", "renamed"),
])
def test_the_recorded_source_hash_moves_with_every_rendered_input(field, value):
    assert ci.rule_digest(_sub(), {}) != ci.rule_digest(_sub(**{field: value}), {})


def test_a_rule_with_24_scoped_paths_still_fits_30_lines():
    paths = [f"pkg{i:02d}/**" for i in range(24)]
    sub = _sub(paths=paths, body="# alpha\n\n## Landmines\n\n" + "".join(f"- mine {i}.\n" for i in range(10)))

    text = ci.render_rule(sub, {"alpha": "The alpha subsystem."})

    lines = text.splitlines()
    assert len(lines) <= ci.RULES_MAX_LINES
    assert any(l.startswith("  # +") and "more paths not scoped here" in l for l in lines)
    assert lines.count("---") == 2 and "## Landmines" in lines


def test_rules_check_fails_on_a_hand_written_file_at_a_generated_path(tmp_path):
    root = _big_repo(tmp_path)
    ci.rules(str(root))
    blocker = root / ".claude" / "rules" / "sub001.md"
    blocker.write_text("---\npaths:\n  - x/**\n---\nmine\n", encoding="utf-8")

    problems, _ = ci.rules(str(root), check=True)

    assert problems == ["hand-written file blocks generated output: "
                        + os.path.join(".claude", "rules", "sub001.md")]
    assert ci.main(["rules", "--root", str(root), "--check"]) == 1


def test_agents_check_fails_on_a_hand_written_agents_md(tmp_path):
    root = _big_repo(tmp_path)
    (root / "AGENTS.md").write_text("# mine\n", encoding="utf-8")

    assert ci.main(["agents", "--root", str(root), "--check"]) == 1


def _verify_json(root, rules=(), default=()):
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": list(rules), "default": list(default)}), encoding="utf-8")


def _cmd_rule(*commands):
    return {"paths": ["**"], "seconds": 1, "reach": "local", "why": "t", "run": list(commands)}


def test_agents_md_says_claude_code_does_not_load_it_without_an_import(tmp_path):
    root = _big_repo(tmp_path)
    (root / "CLAUDE.md").write_text("# repo\n", encoding="utf-8")

    ci.agents(str(root))

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Claude Code does not load it" in text and "reads it through" not in text


def test_agents_md_says_claude_code_reads_it_when_claude_md_imports_it(tmp_path):
    root = _big_repo(tmp_path)
    (root / "CLAUDE.md").write_text("# repo\n@AGENTS.md\n", encoding="utf-8")

    ci.agents(str(root))

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "reads it through `@AGENTS.md`" in text and "does not load it" not in text


def test_the_smoke_harness_is_the_first_verify_command_and_listed_once(tmp_path):
    root = _big_repo(tmp_path)
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text("exit 0\n", encoding="utf-8")
    _verify_json(root, [_cmd_rule("make test", "bash _verify/smoke.sh")])

    ci.agents(str(root))

    lines = (root / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    commands = [ln for ln in lines if ln.startswith("- `") and ln.endswith("`")]
    assert commands[:2] == ["- `bash _verify/smoke.sh`", "- `make test`"]
    assert sum("_verify/smoke.sh" in ln for ln in lines) == 1


def test_verify_commands_past_six_are_counted_not_dropped_silently(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule(*[f"check {i}" for i in range(9)])])

    ci.agents(str(root))

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "`check 5`" in text and "`check 6`" not in text
    assert "...and 3 more in `.crew/verify.json`." in text


def test_a_plugin_root_command_comes_with_how_to_run_it_outside_claude_code(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [ci.agents_rule()])

    ci.agents(str(root))

    assert "`$CLAUDE_PLUGIN_ROOT` is the crew plugin's install directory" in \
        (root / "AGENTS.md").read_text(encoding="utf-8")


def test_the_title_survives_a_clone_under_another_directory_name(tmp_path):
    """The drift rule runs --check in every clone, worktree and CI checkout;
    the directory name differs there and must not read as drift."""
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    moved = tmp_path / "some-other-checkout"
    root.rename(moved)

    problems, written = ci.agents(str(moved), check=True)

    assert (problems, written) == ([], [])
    assert (moved / "AGENTS.md").read_text(encoding="utf-8").startswith(
        "# repo - instructions for every agent")


def test_a_map_without_the_drift_rule_gets_a_note_that_is_not_drift(tmp_path, capsys):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule("make test")])
    ci.agents(str(root))

    assert ci.main(["agents", "--root", str(root), "--check"]) == 0
    assert "has no AGENTS.md drift rule" in capsys.readouterr().out


def test_a_map_with_the_drift_rule_gets_no_note(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [ci.agents_rule()])

    problems, written = ci.agents(str(root))

    assert (problems, written) == ([], ["AGENTS.md"])


def test_stale_with_the_rule_missing_still_fails_the_check(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule("make test")])
    ci.agents(str(root))
    _verify_json(root, [_cmd_rule("make test", "make lint")])

    assert ci.main(["agents", "--root", str(root), "--check"]) == 1


def test_agents_rule_prints_the_rule(capsys):
    assert ci.main(["agents-rule"]) == 0
    rule = json.loads(capsys.readouterr().out)
    assert rule["reach"] == "local" and rule["seconds"] >= 1
    assert "agents --check" in rule["run"][0] and "AGENTS.md" in rule["paths"]


@pytest.mark.skipif(sys.platform.startswith("win") or not shutil.which("bash"),
                    reason="POSIX bash with python3 on PATH; Git Bash ships without python3")
@pytest.mark.parametrize("plugin_root, want", [(None, 77), ("crew", 0), ("crew-stale", 1)])
def test_the_rule_command_skips_without_a_plugin_root_and_checks_with_one(
        tmp_path, plugin_root, want):
    root = _big_repo(tmp_path)
    _verify_json(root, [ci.agents_rule()])
    ci.agents(str(root))
    if plugin_root == "crew-stale":
        _verify_json(root, [ci.agents_rule(), _cmd_rule("make lint")])
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = context._ROOT  # pylint: disable=protected-access

    done = subprocess.run(["bash", "-c", ci.AGENTS_RULE_COMMAND], cwd=str(root), env=env,
                          capture_output=True, text=True, check=False, timeout=60)

    assert done.returncode == want, done.stdout + done.stderr


def test_where_things_are_follows_git_not_the_disk(tmp_path):
    """A file a note cites that exists here but is not tracked (gitignored,
    or not yet added) must not change AGENTS.md: a clone would not have it,
    and the committed file would read as stale there."""
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    before = (root / "AGENTS.md").read_text(encoding="utf-8")
    note = root / ".crew" / "codemap" / "sub000.md"
    (root / "build" / "gen").mkdir(parents=True)
    for i in range(6):  # cited often enough that, on disk, it would lead the note's scope
        (root / "build" / "gen" / f"out{i}.py").write_text("x\n", encoding="utf-8")
    note.write_text(note.read_text(encoding="utf-8") + "".join(
        f"\n- `build/gen/out{i}.py:1` generated\n" for i in range(6)), encoding="utf-8")
    assert "build/gen" in str(crew_context.subsystems(str(root))[0]["paths"])  # disk would
    ci.agents(str(root))
    with_untracked = (root / "AGENTS.md").read_text(encoding="utf-8")
    shutil.rmtree(root / "build")

    problems, _ = ci.agents(str(root), check=True)

    assert "build" not in with_untracked
    assert with_untracked == before and problems == []


@pytest.mark.parametrize("source", ["CLAUDE.md", ".crew/verify.json",
                                    ".crew/codemap/sub000.md", "_verify/smoke.sh"])
def test_every_input_that_changes_agents_md_is_in_the_rule_s_paths(tmp_path, source):
    root = _big_repo(tmp_path)
    _verify_json(root, [ci.agents_rule()])
    ci.agents(str(root))
    before = (root / "AGENTS.md").read_text(encoding="utf-8")
    path = root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    if source == ".crew/verify.json":
        _verify_json(root, [ci.agents_rule(), _cmd_rule("make lint")])
    elif source == "CLAUDE.md":
        path.write_text("# repo\n@AGENTS.md\n", encoding="utf-8")
    elif source.endswith("smoke.sh"):
        path.write_text("exit 0\n", encoding="utf-8")
    else:
        path.unlink()

    ci.agents(str(root))

    assert (root / "AGENTS.md").read_text(encoding="utf-8") != before
    assert any(crew_context.glob_match(source, g) for g in ci.agents_rule()["paths"])


def test_seven_commands_show_six_and_count_one(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule(*[f"check {i}" for i in range(7)])])

    ci.agents(str(root))

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "...and 1 more in `.crew/verify.json`." in text
    assert "Exit 77 is SKIP, not a pass." in text


def test_the_plugin_root_line_is_only_for_commands_that_are_shown(tmp_path):
    root = _big_repo(tmp_path)
    hidden = 'python3 "$CLAUDE_PLUGIN_ROOT/x.py"'
    _verify_json(root, [_cmd_rule(*[f"check {i}" for i in range(6)], hidden)])

    ci.agents(str(root))

    assert "CLAUDE_PLUGIN_ROOT" not in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_the_write_path_reports_the_missing_rule_note(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule("make test")])

    problems, written = ci.agents(str(root))

    assert written == ["AGENTS.md"] and len(problems) == 1
    assert problems[0].startswith(ci.NOTE)


def test_a_rule_with_its_flags_in_another_order_still_counts(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule('python3 "$X/crew_instructions.py" agents --root . --check')])

    problems, _ = ci.agents(str(root))

    assert problems == []


def test_a_mention_of_the_import_in_prose_is_not_the_import(tmp_path):
    root = _big_repo(tmp_path)
    (root / "CLAUDE.md").write_text("# repo\nDo not add @AGENTS.md here.\n", encoding="utf-8")

    ci.agents(str(root))

    assert "Claude Code does not load it" in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_a_forged_title_cannot_make_the_file_grow(tmp_path):
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    path = root / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(f"# x {ci.KEEP_START}{ci.TITLE_TAIL}\n" + text.split("\n", 1)[1],
                    encoding="utf-8")
    ci.agents(str(root))
    once = path.read_text(encoding="utf-8")

    ci.agents(str(root))

    assert path.read_text(encoding="utf-8") == once
    assert once.startswith("# repo - instructions for every agent")


@pytest.mark.parametrize("value", [None, 5, "x"])
def test_a_map_whose_rules_or_default_is_not_a_list_does_not_crash(tmp_path, value):
    root = _big_repo(tmp_path)
    (root / ".crew" / "verify.json").write_text(json.dumps({"rules": value, "default": value}),
                                                encoding="utf-8")

    problems, written = ci.agents(str(root))

    assert written == ["AGENTS.md"] and problems[0].startswith(ci.NOTE)


def test_a_stale_check_says_how_to_regenerate(tmp_path):
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    _verify_json(root, [_cmd_rule("make lint")])

    problems, _ = ci.agents(str(root), check=True)

    assert problems[0].startswith("stale: AGENTS.md - regenerate: ")
    assert "crew_instructions.py\" agents --root ." in problems[0]


def test_tracked_files_scope_a_note_to_their_directory(tmp_path):
    """The positive half of the git-judged scopes: three tracked files in one
    directory scope the note to `dir/**`, with no note about falling back."""
    root = make_repo(tmp_path)

    problems, _ = ci.agents(str(root))

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "`alpha` (`src/alpha/**`)" in text and "`beta` (`src/beta/**`)" in text
    assert not any("git ls-files failed" in p for p in problems)


def test_a_cited_tracked_directory_counts_as_existing(tmp_path):
    root = make_repo(tmp_path)
    note = root / ".crew" / "codemap" / "alpha.md"
    body = note.read_text(encoding="utf-8")
    note.write_text(body.replace("src/alpha/core.py:1", "src/alpha").replace(
        "src/alpha/util.py:1", "src/alpha").replace("src/alpha/io.py:1", "src/alpha"),
        encoding="utf-8")

    ci.agents(str(root))

    assert "`alpha` (`src/alpha/**`)" in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_a_blank_title_falls_back_to_the_directory_name(tmp_path):
    root = _big_repo(tmp_path)
    ci.agents(str(root))
    path = root / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(f"# {ci.TITLE_TAIL}\n" + text.split("\n", 1)[1], encoding="utf-8")

    ci.agents(str(root))

    assert path.read_text(encoding="utf-8").startswith("# repo - instructions for every agent")


def test_outside_a_git_work_tree_the_disk_decides_and_says_so(tmp_path):
    # A copy without `.git`, not an rmtree of it: git's object files are
    # read-only, and on Windows that rmtree fails with WinError 5.
    repo = make_repo(tmp_path)
    root = tmp_path / "no-git"
    shutil.copytree(repo, root, ignore=shutil.ignore_patterns(".git"))

    problems, _ = ci.agents(str(root))

    assert "`alpha` (`src/alpha/**`)" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert any(p.startswith(ci.NOTE) and "git ls-files failed" in p for p in problems)


def test_a_look_alike_flag_is_not_the_drift_check(tmp_path):
    root = _big_repo(tmp_path)
    _verify_json(root, [_cmd_rule('python3 "$X/crew_instructions.py" agents --check-not-real')])

    problems, _ = ci.agents(str(root))

    assert any("has no AGENTS.md drift rule" in p for p in problems)


def _hand_codex(root):
    path = root / ".codex" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    mine = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}})
    path.write_text(mine, encoding="utf-8")
    return path, mine


def test_codex_never_overwrites_a_hand_written_hooks_json(tmp_path):
    root = _big_repo(tmp_path)
    path, mine = _hand_codex(root)

    problems, _ = ci.codex(str(root), "/opt/crew")

    assert (path.read_text(encoding="utf-8"), problems) == \
        (mine, ["hand-written, left alone: " + os.path.join(".codex", "hooks.json")])


def test_codex_force_overwrites_a_hand_written_hooks_json(tmp_path):
    root = _big_repo(tmp_path)
    path, _ = _hand_codex(root)

    ci.codex(str(root), "/opt/crew", force=True)

    assert json.loads(path.read_text(encoding="utf-8")) == ci.codex_hooks("/opt/crew")


def test_codex_regenerates_its_own_hooks_json_for_a_moved_plugin(tmp_path):
    root = _big_repo(tmp_path)
    ci.codex(str(root), "/opt/crew")

    ci.codex(str(root), "/elsewhere")

    assert json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8")) == \
        ci.codex_hooks("/elsewhere")


def test_codex_write_says_the_hooks_file_is_machine_local(tmp_path, capsys):
    root = _big_repo(tmp_path)

    ci.main(["codex", "--root", str(root), "--plugin-root", "/opt/crew"])

    assert "machine-local" in capsys.readouterr().out


# --- W8 review fix: docs must not tell users to run `--profile review|work` --
# against PROJECT config -----------------------------------------------------
#
# CODEX_CONFIG (above) deliberately never writes a `[profiles.*]` table into
# the generated `.codex/config.toml`, because `profiles` is on Codex's own
# project-local config denylist and is stripped every time it loads, trusted
# or not (MEASURED, codex-cli 0.154.0). A doc telling a reader to run
# `codex exec --profile review` / `--profile work` describes a project
# profile that was never applied in the first place. `--profile NAME` is a
# real flag -- it just layers a USER-level `$CODEX_HOME/NAME.config.toml`,
# never this repo's `.codex/config.toml` -- so the only wrong claim is
# "against the project config", which this scans the repo's shipped docs for.

_REPO_ROOT = os.path.abspath(os.path.join(context._ROOT, os.pardir, os.pardir))  # pylint: disable=protected-access
_BAD_PROFILE_INVOCATION_RE = re.compile(r"codex\s+exec\b[^\n<]*--profile\s+(review|work)\b")
_SKIP_DIRS = {".git", "node_modules", "graphify-out"}


def _doc_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.endswith((".md", ".html")):
                yield os.path.join(dirpath, name)


def test_no_shipped_doc_tells_users_to_run_a_profile_against_project_config():
    """A doc MAY still explain that `--profile NAME` exists (it does, and is
    real) -- this only refuses the specific runnable invocation
    (`codex exec --profile review|work ...`) that implies a PROJECT profile
    applied, which CODEX_CONFIG's own comment says never happens."""
    offenders = []
    for path in _doc_files(_REPO_ROOT):
        text = read_text(path)
        if text is None:
            continue
        for match in _BAD_PROFILE_INVOCATION_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{os.path.relpath(path, _REPO_ROOT)}:{line}")

    assert offenders == []
