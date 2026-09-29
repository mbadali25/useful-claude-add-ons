"""The output formats of the external tools crew parses, pinned to their docs.

`plugin/crew/docs/external-tool-formats.md` records, with a URL and a read
date for each fact, what crew relies on from Codex CLI, wsl.exe and gh. These
tests hold crew's call sites and the committed golden corpus to that document,
and probe the installed tools where they exist. A probe for a tool that is not
installed SKIPS with its reason -- never a pass; the live Codex probe runs only
with CREW_PROBE_LIVE=1, by hand (T-0087).
"""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_run
import review_verdict as rv

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(CREW, "docs", "external-tool-formats.md")
GOLDEN = os.path.join(CREW, "tests", "golden", "review")


def _doc():
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


def _sections(text):
    found, name = {}, None
    for line in text.split("\n"):
        if line.startswith("## "):
            name = line[3:].strip()
            found[name] = []
        elif name:
            found[name].append(line)
    return {k: "\n".join(v) for k, v in found.items()}


def _help(*cmd):
    return subprocess.run(list(cmd), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=60, check=False).stdout


def test_codex_command_passes_only_documented_flags():
    doc = _doc()
    cmd = review_run.command_for("codex", "codex", "/r", "p", "m", "high")

    flags = [t for t in cmd if t.startswith("-")]

    assert flags
    assert [f for f in flags if f"`{f}`" not in doc] == []


def test_golden_codex_events_use_documented_types():
    events, items = set(), set()
    for path in glob.glob(os.path.join(GOLDEN, "*", "events.jsonl")):
        with open(path, encoding="utf-8", newline="") as fh:
            for line in fh.read().split("\n"):
                if not line.strip():
                    continue
                event = json.loads(line)
                events.add(event.get("type"))
                if isinstance(event.get("item"), dict):
                    items.add(event["item"].get("type"))

    assert events, "no committed Codex stream in the golden corpus"
    assert events <= set(rv.CODEX_EVENT_TYPES), events - set(rv.CODEX_EVENT_TYPES)
    assert items <= set(rv.CODEX_ITEM_TYPES), items - set(rv.CODEX_ITEM_TYPES)


@pytest.mark.parametrize("tool", ["Codex CLI", "wsl.exe", "gh"])
def test_the_doc_cites_a_source_for_every_tool(tool):
    section = _sections(_doc()).get(tool, "")

    assert "https://" in section, f"## {tool} cites no source"
    assert re.search(r"^Probed:", section, re.M), f"## {tool} has no Probed: line"


def test_installed_codex_exec_help_lists_the_flags_crew_passes():
    if not shutil.which("codex"):
        pytest.skip("codex is not on PATH here: the codex exec --help probe did not run")

    text = _help("codex", "exec", "--help")

    for flag in ("--json", "--sandbox", "--skip-git-repo-check", "--cd", "--model", "--config"):
        assert flag in text, flag


def test_installed_gh_pr_review_help_lists_the_flags_review_md_uses():
    if not shutil.which("gh"):
        pytest.skip("gh is not on PATH here: the gh pr review --help probe did not run")

    text = _help("gh", "pr", "review", "--help")

    for flag in ("--approve", "--request-changes", "--body", "--body-file"):
        assert flag in text, flag


def _wsl_list(extra, drop=()):
    env = {k: v for k, v in dict(os.environ, **extra).items() if k not in drop}
    return subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False, env=env)


def _probe_wsl_encoding():
    """A host with wsl.exe and no distribution lists nothing either way (the
    hosted Windows runner, PR #260): that is "could not tell", so it skips
    saying so. It never passes, and a real encoding change still fails."""
    default = _wsl_list({}, drop=("WSL_UTF8",))
    utf8 = _wsl_list({"WSL_UTF8": "1"})
    for proc in (default, utf8):
        out = proc.stdout or b""
        if proc.returncode != 0 or not out.strip(b"\x00\r\n "):
            pytest.skip(f"wsl.exe is on PATH but listed no distribution (exit {proc.returncode}, "
                        f"{len(out)} bytes): its output encoding was researched, not probed")

    assert b"\x00" in default.stdout
    assert b"\x00" not in utf8.stdout


def test_wsl_list_is_utf16_unless_wsl_utf8():
    if not shutil.which("wsl.exe"):
        pytest.skip("wsl.exe is not on PATH here (not Windows or WSL interop): "
                    "its output encoding was researched, not probed")

    _probe_wsl_encoding()


def _fake_wsl(answers):
    def run(cmd, **kwargs):
        rc, out = answers(kwargs.get("env") or {})
        return subprocess.CompletedProcess(cmd, rc, out, b"")
    return run


@pytest.mark.parametrize("rc,out", [(1, b""), (0, b""), (0, b"\x00\r\x00\n\x00")])
def test_wsl_probe_skips_when_no_distribution_answers(monkeypatch, rc, out):
    monkeypatch.setattr(shutil, "which", lambda name: "wsl.exe")
    monkeypatch.setattr(subprocess, "run", _fake_wsl(lambda env: (rc, out)))

    with pytest.raises(pytest.skip.Exception) as skipped:
        _probe_wsl_encoding()

    assert "listed no distribution" in str(skipped.value)
    assert f"exit {rc}" in str(skipped.value)


def test_wsl_probe_asserts_the_encoding_when_a_distribution_answers(monkeypatch):
    def answers(env):
        if env.get("WSL_UTF8") == "1":
            return 0, b"Ubuntu\n"
        return 0, "Ubuntu\r\n".encode("utf-16-le")
    monkeypatch.setattr(subprocess, "run", _fake_wsl(answers))

    _probe_wsl_encoding()


def test_wsl_probe_fails_when_wsl_utf8_does_not_change_the_encoding(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        _fake_wsl(lambda env: (0, "Ubuntu\r\n".encode("utf-16-le"))))

    with pytest.raises(AssertionError):
        _probe_wsl_encoding()


@pytest.mark.parametrize("exe,inline", [
    ("C:\\npm\\codex.cmd", False),
    ("C:\\npm\\copilot.CMD", False),
    ("codex.bat", False),
    ("/usr/local/bin/codex", True),
    ("C:\\bin\\codex.exe", True),
    (None, True),
])
def test_a_batch_shim_never_gets_the_prompt_inline(tmp_path, capsys, exe, inline):
    path = tmp_path / "prompt.txt"
    text = "Review this.\nList every part.\nThen the verdict.\n"
    path.write_text(text, encoding="utf-8", newline="\n")

    argument = review_run.prompt_argument(str(path), exe)

    if inline:
        assert argument == text
    else:
        assert "\n" not in argument
        assert str(path) in argument and "Read that file" in argument
        assert "batch shim" in capsys.readouterr().err


def test_an_over_limit_prompt_says_over_limit_even_through_a_shim(tmp_path, capsys):
    path = tmp_path / "prompt.txt"
    path.write_text("x" * (review_run.INLINE_PROMPT_LIMIT + 1), encoding="utf-8")

    argument = review_run.prompt_argument(str(path), "codex.cmd")

    assert str(path) in argument and "Read that file" in argument
    assert "over the inline limit" in capsys.readouterr().err


def test_live_codex_stream_parses(tmp_path):
    if os.environ.get("CREW_PROBE_LIVE") != "1":
        pytest.skip("live Codex probe is opt-in: set CREW_PROBE_LIVE=1 (it spends a real call)")
    if not shutil.which("codex"):
        pytest.skip("CREW_PROBE_LIVE=1 but codex is not on PATH")

    proc = subprocess.run(
        ["codex", "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
         "-C", str(tmp_path), "Reply with exactly the single word CLEAN and nothing else."],
        capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=300, check=False)
    message, error = rv.codex_final_message(proc.stdout)

    assert ((message or "").strip(), error) == ("CLEAN", None), proc.stdout[-2000:]
    kinds = {json.loads(line).get("type") for line in proc.stdout.split("\n") if line.strip()}
    assert kinds <= set(rv.CODEX_EVENT_TYPES), kinds
