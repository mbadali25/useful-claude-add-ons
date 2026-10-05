"""T-0041: crew verifies before it states.

    python3 -m pytest plugin/crew/tests/test_verify_before_stating.py -q

Two halves. The text-presence tests read the tracked prompts: the
verify-before-you-state rule is in the free-form agents and in
`crew-best-practices`, every free-form agent report and the done/debug
reports end with a "Not verified" section, and plan/brainstorm look up a
recorded decision before proposing to change it. The `validate-prompts.py`
tests prove the same thing is enforced by the script verify rule 13 runs:
each mutates a COPY of the prompt tree under tmp_path (never the tracked
files), runs the copy's own validator, and expects it to fail by name.

Out of scope here, on purpose: `agents/reviewer.md` and `commands/review.md`.
Both are review-harness paths (`HARNESS` in `scripts/check-tooling-pr.py`), and
the owner rule of 2026-09-28 (T-0087) lands a harness change alone. Their part
of T-0041 -- the rule in reviewer.md, the "claims without evidence" FIX
category, `not reproduced:` and the copy-the-bytes Claude fallback -- is a
harness follow-up, and `validate-prompts.py` exempts reviewer.md by name until
it lands.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(CREW, "agents")
COMMANDS = os.path.join(CREW, "commands")
SKILLS = os.path.join(CREW, "skills")
VALIDATOR = os.path.join("hooks", "scripts", "_test", "validate-prompts.py")
MAX_LINES = 120

RULE = "Verify before you state"
NOT_VERIFIED = "**Not verified"
# reviewer.md is review harness (T-0087): its rule edit is a harness follow-up.
RULE_AGENTS = ("explorer.md", "researcher.md", "security.md")
RULE_FILES = tuple(os.path.join(AGENTS, a) for a in RULE_AGENTS) + (
    os.path.join(SKILLS, "crew-best-practices", "SKILL.md"),)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _section(text, heading):
    """The body of the `heading` section, up to the next heading of the same level."""
    level = heading.split(" ", 1)[0]
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1:]
    nxt = re.search(rf"^{re.escape(level)} ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


@pytest.mark.parametrize("path", RULE_FILES, ids=os.path.basename)
def test_every_agent_carries_the_rule(path):
    text = _read(path)
    assert RULE in text, f"{path}: missing {RULE!r}"
    assert "could not tell" in text.lower(), f"{path}: missing 'could not tell'"


@pytest.mark.parametrize("agent", RULE_AGENTS)
def test_free_form_agents_report_not_verified(agent):
    text = _read(os.path.join(AGENTS, agent))
    assert NOT_VERIFIED in text, f"{agent}: report template has no {NOT_VERIFIED!r} section"
    assert "**Unverified" not in text, f"{agent}: still names the old **Unverified** block"


def test_done_and_debug_report_not_verified():
    done = _read(os.path.join(COMMANDS, "done.md"))
    for phrase in ("**Not verified:**", "exited 77", "drift-detection.sh"):
        assert phrase in done, f"done.md: missing {phrase!r}"
    debug = _read(os.path.join(COMMANDS, "debug.md"))
    assert "**Not verified**" in _section(debug, "## 4. Report"), \
        "debug.md: '## 4. Report' has no **Not verified** bullet"
    for name, text in (("done.md", done), ("debug.md", debug)):
        assert len(text.splitlines()) <= MAX_LINES, f"{name}: over {MAX_LINES} lines"


def test_plan_and_brainstorm_look_up_prior_decisions():
    plan = _section(_read(os.path.join(SKILLS, "crew-plan", "SKILL.md")),
                    "## Self-review, before showing the human")
    item = re.search(r"^6\. \*\*Recorded decisions\.\*\*(.*?)(?=^\S|\Z)", plan, re.M | re.S)
    assert item, "crew-plan/SKILL.md: self-review has no item 6, Recorded decisions"
    for phrase in ("docs/adr/", "direction.md", "CHANGELOG.md"):
        assert phrase in item.group(1), f"crew-plan/SKILL.md: item 6 does not name {phrase}"
    method = _section(_read(os.path.join(SKILLS, "crew-brainstorm", "SKILL.md")), "## The method")
    assert "docs/adr/" in method, "crew-brainstorm/SKILL.md: the method does not name docs/adr/"


# --- validate-prompts.py enforces it -----------------------------------------

def _tree(tmp_path):
    """A copy of the prompt tree the validator reads, rooted where it chdirs to."""
    root = tmp_path / "plugin" / "crew"
    shutil.copytree(CREW, root, ignore=shutil.ignore_patterns(
        "tests", "__pycache__", "*.pyc", "evals", "docs"))
    return root


def _run(root):
    proc = subprocess.run([sys.executable, str(root / VALIDATOR)], capture_output=True,
                          text=True, check=False, stdin=subprocess.DEVNULL, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def _drop(path, needle):
    """Remove every line of `path` containing `needle`; fail if there was none."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if needle not in ln]
    assert len(kept) < len(lines), f"{path}: {needle!r} not found to remove"
    path.write_text("".join(kept), encoding="utf-8", newline="\n")


def test_validate_prompts_passes_on_the_real_tree():
    code, out = _run(pathlib.Path(CREW))
    assert code == 0, out
    assert "=== VERIFICATION RULE ===" in out, out


def test_validate_prompts_passes_on_an_untouched_copy(tmp_path):
    code, out = _run(_tree(tmp_path))
    assert code == 0, out


def test_validate_prompts_fails_without_not_verified(tmp_path):
    root = _tree(tmp_path)
    _drop(root / "agents" / "explorer.md", NOT_VERIFIED)
    code, out = _run(root)
    assert code == 1, out
    assert re.search(r"explorer\.md.*Not verified", out), out


def test_validate_prompts_fails_when_done_loses_not_verified(tmp_path):
    root = _tree(tmp_path)
    _drop(root / "commands" / "done.md", NOT_VERIFIED)
    code, out = _run(root)
    assert code == 1, out
    assert re.search(r"done\.md.*Not verified", out), out


def test_validate_prompts_fails_when_debug_loses_not_verified(tmp_path):
    root = _tree(tmp_path)
    _drop(root / "commands" / "debug.md", NOT_VERIFIED)
    code, out = _run(root)
    assert code == 1, out
    assert re.search(r"debug\.md.*Not verified", out), out


def test_validate_prompts_fails_without_the_rule(tmp_path):
    root = _tree(tmp_path)
    _drop(root / "agents" / "security.md", RULE)
    code, out = _run(root)
    assert code == 1, out
    assert re.search(r"security\.md.*Verify before you state", out), out


def test_validate_prompts_fails_when_best_practices_loses_the_rule(tmp_path):
    root = _tree(tmp_path)
    _drop(root / "skills" / "crew-best-practices" / "SKILL.md", RULE)
    code, out = _run(root)
    assert code == 1, out
    assert "crew-best-practices" in out, out


def test_validate_prompts_exempts_the_reviewer_report():
    """reviewer.md has no **Not verified section (its output is the machine
    contract review_verdict.py parses), and the real tree still passes."""
    assert NOT_VERIFIED not in _read(os.path.join(AGENTS, "reviewer.md"))
    code, out = _run(pathlib.Path(CREW))
    assert code == 0, out
    assert "reviewer" in out and "exempt" in out, out


def test_a_new_agent_is_checked_by_default(tmp_path):
    """Omission fails closed: an agent nobody listed still needs the rule."""
    root = _tree(tmp_path)
    shutil.copy(root / "agents" / "explorer.md", root / "agents" / "newcomer.md")
    text = (root / "agents" / "newcomer.md").read_text(encoding="utf-8")
    (root / "agents" / "newcomer.md").write_text(
        text.replace("name: explorer", "name: newcomer").replace(RULE, "Check things"),
        encoding="utf-8", newline="\n")
    code, out = _run(root)
    assert code == 1, out
    assert re.search(r"newcomer\.md.*Verify before you state", out), out
