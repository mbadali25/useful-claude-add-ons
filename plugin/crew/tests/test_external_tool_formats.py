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

import context  # noqa: F401  pylint: disable=unused-import
import pytest
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
    assert re.search(r"^Probed:", section, re.MULTILINE), f"## {tool} has no Probed: line"


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


def test_wsl_list_is_utf16_unless_wsl_utf8():
    if not shutil.which("wsl.exe"):
        pytest.skip("wsl.exe is not on PATH here (not Windows or WSL interop): "
                    "its output encoding was researched, not probed")

    def raw(extra):
        env = dict(os.environ, **extra)
        return subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=60, check=False, env=env).stdout

    assert b"\x00" in raw({"WSL_UTF8": ""})
    assert b"\x00" not in raw({"WSL_UTF8": "1"})


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
