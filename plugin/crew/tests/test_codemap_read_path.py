"""The roles that touch code must be told to read the code map.

Crew wrote a per-repo "what breaks here" store -- each codemap note's
`## Landmines` section -- and then never told the roles that do the work to
open it. Measured before crew 0.19.61: `grep -ci codemap` returned 0 for
commands/review.md, commands/work.md, and the developer, dba, qa-reviewer and
smoke-author agents. Every reviewer re-derived this repo's failure modes from
the diff plus CLAUDE.md, in an empty context, every single time.

These assertions are deliberately about the PROMPT TEXT rather than about
behaviour. A subagent prompt is not executable, so there is nothing to run; the
only thing that can regress mechanically is the instruction going missing from
the file, and that is exactly what happened for the whole life of the feature
before this. A prose-only fix here is not a weaker test than a behavioural one,
it is the only kind available -- but it is also why this file asserts the
SPECIFIC strings a reader needs rather than merely that the word appears.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]


def _norm(text):
    """Collapse runs of whitespace so an assertion survives a rewrap.

    Same helper, same reason, as test_scope_discipline.py. These files are
    hand-wrapped prose: a phrase on one line today can straddle two after any
    edit, and a test that fails on that is one people learn to "fix" by
    deleting the assertion. Collapsing whitespace keeps the test sensitive to
    the sentence being REMOVED -- the actual regression -- while blind to
    where the line breaks fall.
    """
    return re.sub(r"\s+", " ", text)


# The roles that read or write code, and therefore need this repo's landmines.
# crew 1.0 cut the roster to four agents. `reviewer` is the only one that
# judges a diff against the map; the writers (developer, dba, smoke-author)
# were deleted, and the interactive session that replaced them reads the map
# through the context hook rather than an agent file.
DOING_ROLES = ("reviewer",)


def _agent(name):
    return _norm((PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8"))


def _command(name):
    return _norm((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"))


def _command_raw(name):
    """Unnormalised. The prompt.txt invariant below is about heredoc
    STRUCTURE -- it splits on a newline-anchored terminator -- so _norm, which
    removes every newline, would make that test split on nothing and assert
    against the wrong slice of the file."""
    return (PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8")


def test_every_doing_role_is_told_to_read_the_codemap():
    for name in DOING_ROLES:
        body = _agent(name)
        assert ".crew/codemap/INDEX.md" in body, (
            f"{name}.md no longer names the codemap index, so the role has no "
            "entry point into the map and will re-derive the repo's failure "
            "modes from the diff, which is the defect 0.19.61 fixed"
        )
        assert "## Landmines" in body, (
            f"{name}.md no longer names the Landmines section by name. "
            "Pointing at the codemap without naming the section is not "
            "enough: the section is the part that carries what breaks here"
        )


def test_every_doing_role_carries_the_anchor_recheck_rule():
    """A stale anchor means re-check, and a role that does not know that
    either ignores a current note or distrusts a correct one. Both are worse
    than not reading it, because both look like diligence."""
    for name in DOING_ROLES:
        body = _agent(name)
        assert "git diff --name-only" in body, (
            f"{name}.md dropped the per-path freshness check. Without it the "
            "role treats 'anchor behind HEAD' as 'note is wrong', which "
            "over-reports staleness and sends it re-deriving anyway"
        )


def test_data_touching_roles_are_pointed_at_the_schema_note():
    for name in DOING_ROLES:
        body = _agent(name)
        assert "schema-<datasource>.md" in body, (
            f"{name}.md does not name the schema note, so a migration or "
            "index change is reviewed with no column, key or index facts"
        )


def test_onboard_writes_the_schema_note_and_refuses_to_invent_one():
    body = _command("onboard")
    assert ".crew/codemap/schema-<datasource>.md" in body
    assert "no datasource found" in body, (
        "onboard.md must tell the writer to report an absent datasource "
        "rather than writing an empty or inferred schema file. A schema note "
        "nobody can trace to a migration is the failure the command exists "
        "to prevent"
    )
    assert "`## Unverified`, not in" in body, (
        "onboard.md must route schema it could not trace to a file into "
        "## Unverified. Collapsing 'confirmed' and 'could not confirm' into "
        "one section is this repo's named recurring defect"
    )


def _prepared(tmp_path, scenario):
    """`review_run.py --prepare` run in a deterministic fixture repo; returns
    (repo root, scratch directory)."""
    import os
    import subprocess
    import sys
    import review_fixtures as fx
    root = fx.build_prepare_repo(tmp_path / "repo", scenario)
    env = fx.prepare_env(tmp_path / "fakes", tmp_path / "home")
    done = subprocess.run(
        [sys.executable, os.path.join(str(PLUGIN), "hooks", "scripts", "review_run.py"),
         "--root", ".", "--prepare", "--scratch", fx.PREPARE_SCRATCH], cwd=root, env=env,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)
    assert done.returncode == 0, done.stderr
    return root, root / fx.PREPARE_SCRATCH


def test_review_injects_repo_landmines_into_the_shared_prompt(tmp_path):
    """0.19.61 wired the FALLBACK reviewer and nobody else.

    /crew:review tries Codex then Copilot before falling back to the in-session
    qa-reviewer, and all three read one prompt.txt that had no codemap content.
    So on any machine with Codex installed, the reviewer that actually ran
    never saw the landmines. Wiring an agent file is not wiring the reviewer.
    Since L-0726 `review_run.py --prepare` gathers them (review.md's shell loop
    is gone), so the proof is the prompt it writes.
    """
    _, scratch = _prepared(tmp_path, "codemap-landmines")

    prompt = (scratch / "prompt.txt").read_text(encoding="utf-8")
    changed = (scratch / "changed.txt").read_text(encoding="utf-8")

    assert "src/a.py truncates on CRLF" in prompt
    assert "src/a.py is written by build, read by deploy" in prompt
    assert "## Landmines" in prompt and "## Written by / Read by" in prompt
    assert "src/zzz.py is not in this diff" not in prompt
    # changed.txt is the manifest's list (dirty and untracked files included), and
    # the landmines were chosen by it, not by a second `git diff`.
    assert changed == "src/a.py\n"


def test_gather_landmines_caps_announces_and_says_when_empty(tmp_path):
    import review_prompt
    notes = tmp_path / ".crew" / "codemap"
    notes.mkdir(parents=True)
    (notes / "big.md").write_text("## Landmines\n" + "- src/a.py\n" * 300, encoding="utf-8")

    capped = review_prompt.gather_landmines(str(tmp_path), ["src/a.py"]).decode("utf-8")
    nothing = review_prompt.gather_landmines(str(tmp_path), ["other.py"])
    no_changes = review_prompt.gather_landmines(str(tmp_path), [])

    assert capped.count("\n") == 202 and "[TRUNCATED at 200 lines of 301." in capped
    assert nothing == no_changes == review_prompt.NO_LANDMINES
    assert nothing.startswith(b"No codemap note intersects this diff")


def test_gather_landmines_refuses_a_note_it_cannot_read(tmp_path):
    import pytest
    import review_prompt
    notes = tmp_path / ".crew" / "codemap"
    notes.mkdir(parents=True)
    (notes / "dir.md").mkdir()

    with pytest.raises(OSError):
        review_prompt.gather_landmines(str(tmp_path), ["src/a.py"])


def test_review_keeps_the_byte_identical_prompt_invariant(tmp_path):
    """All three providers must receive the same bytes.

    The prompt's reason for being built in one place: 'a defect count that
    differs between them is a fact about the model and not about how you
    worded it'. Injecting landmines for one provider would destroy exactly
    that. Since L-0726 one function (`review_prompt.prompt_text`) writes the
    one prompt.txt, `--prepare` calls it once, and nothing else in
    review_run.py or review.md writes or appends to it.
    """
    import review_prompt
    _, scratch = _prepared(tmp_path, "codemap-landmines")
    run_source = (PLUGIN / "hooks" / "scripts" / "review_run.py").read_text(encoding="utf-8")

    prompt = (scratch / "prompt.txt").read_bytes()
    expected = review_prompt.prompt_text(
        ".work/review/golden", (scratch / "contract.txt").read_bytes(),
        (scratch / "context.txt").read_bytes())

    assert prompt == expected
    assert run_source.count('_write_bytes(os.path.join(args.scratch, "prompt.txt")') == 1
    assert run_source.count("review_prompt.prompt_text(") == 1
    assert '>> "$SCRATCH/prompt.txt"' not in _command_raw("review")
    assert "prompt.txt" in _command_raw("review")
