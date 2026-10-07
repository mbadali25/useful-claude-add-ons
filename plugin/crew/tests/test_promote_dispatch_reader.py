"""Unit cases for T-0062's dispatch reading: `crew_dispatch.dispatch_read`
and promote-gate's helper `_promote_dispatch.py`.

`dispatch_read` is `dispatch_answer`'s reading without
`environments.workflows` and without classification. `dispatch_answer` keeps
its own copy of the steps (T-0009's suite reads its source), so the table
below holds the two to one answer: whatever `dispatch_read` calls unsure,
`dispatch_answer` calls could-not-tell under a map listing every workflow,
and the reverse.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_dispatch
import _promote_dispatch as helper

EVERY = {"nonProd": ["*"], "workflows": {"*": "input:environment"},
         "problem": ""}

LINES = [
    ("gh workflow run deploy.yml -f environment=dev", "read"),
    ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
     "-f ref=main -f 'inputs[environment]=dev'", "read"),
    ("gh workflow run deploy.yml --help", "read"),
    ("gh api repos/o/r/actions/workflows/deploy.yml/runs", "none"),
    ("echo done", "none"),
    ('gh pr create --title "$T"', "none"),
    ("gh workflow run deploy.yml -f environment=$E", "unsure"),
    ('gh workflow run deploy.yml -f "environment=dev"', "unsure"),
    ("gh workflow run deploy.yml --json", "unsure"),
    ("gh workflow run deploy.yml --input body.json", "unsure"),
    ("echo gh workflow run deploy.yml | bash", "unsure"),
    ("bash -c 'gh workflow run deploy.yml'", "unsure"),
    ("gh api repos/o/r/actions/workflows/$WF/dispatches -f x=y", "unsure"),
]


@pytest.mark.parametrize("text,kind", LINES)
def test_dispatch_read_kinds(text, kind):
    got, why, scopes = crew_dispatch.dispatch_read(text, "bash")
    assert got == kind, why
    assert (scopes != []) == (kind == "read" and "--help" not in text)


@pytest.mark.parametrize("text,kind", LINES)
def test_dispatch_read_agrees_with_dispatch_answer(text, kind):
    """One reading, two callers: no drift between the copies."""
    state, _why, scope = crew_dispatch.dispatch_answer(text, "bash", EVERY)
    unsure = state == crew_dispatch.ENV_UNKNOWN and (scope or {}).get(
        "op") == crew_dispatch.OP_LINE_NOT_LITERAL
    assert unsure == (kind == "unsure")
    assert crew_dispatch.dispatch_read(text, "bash")[0] == kind


def test_dispatch_read_returns_the_scope_shape():
    kind, _why, scopes = crew_dispatch.dispatch_read(
        "gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
        "-f ref=main -f 'inputs[environment]=prod'", "bash")
    assert kind == "read"
    assert scopes[0]["workflow"] == "deploy.yml"
    assert scopes[0]["inputs"] == [("environment", "prod", "")]


@pytest.mark.parametrize("text,want", [
    ("-f ref=$(git rev-parse HEAD)", "-f ref=SUBSTITUTED"),
    ("-f ref=`git rev-parse HEAD`", "-f ref=SUBSTITUTED"),
    ("x=$(a $(b) c) y", "x=SUBSTITUTED y"),
    ("'$(kept)'", "'$(kept)'"),
    ("x=$(unbalanced", "x=$(unbalanced"),
])
def test_substitute_replaces_declared_substitutions(text, want):
    assert helper.substitute(text) == want


DEV = "gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)"
PROD = "gh workflow run .github/workflows/deploy.yml -f environment=production"


@pytest.fixture(name="project")
def _project(tmp_path, monkeypatch):
    (tmp_path / ".crew").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CREW_MAP_DIRTY", raising=False)

    def write(envs):
        (tmp_path / ".crew" / "verify.json").write_text(
            json.dumps({"environments": envs}), encoding="utf-8")
    write({"dev": {"deploy": DEV}, "prod": {"deploy": [PROD]}})
    return write


@pytest.mark.parametrize("command,want", [
    ("gh workflow run deploy.yml -f environment=development", ["env\tdev"]),
    ("gh workflow run deploy.yml -f environment=production -f extra=1",
     ["env\tprod"]),
    ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'", ["env\tprod"]),
    ("gh workflow run ci.yml -f environment=production", []),
    ("echo done", []),
])
def test_decide(project, command, want):  # pylint: disable=unused-argument
    assert helper.decide(command) == want


@pytest.mark.parametrize("command,reason", [
    ("gh workflow run deploy.yml -f environment=development "
     "-f environment=production", "two values"),
    ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
     "-f '$x=1'", "may be any input"),
    ("gh workflow run 42", "not a file name"),
    ("gh workflow run deploy.yml", "fits no declared environment"),
])
def test_decide_blocks(project, command, reason):  # pylint: disable=unused-argument
    with pytest.raises(helper.Block, match=reason):
        helper.decide(command)


def test_a_declared_dispatch_the_reader_refuses_is_could_not_tell(project):
    project({"dev": {"deploy": 'gh workflow run deploy.yml -f "a=b"'}})
    with pytest.raises(helper.Block, match="cannot read"):
        helper.decide("gh workflow run ci.yml")


def test_no_declared_dispatch_reads_nothing(project):
    project({"dev": {"deploy": "./deploy.sh dev"}})
    assert helper.decide("gh workflow run x.yml -f a=$B") == []


def test_main_prints_a_block_record(project, capsys):  # pylint: disable=unused-argument
    assert helper.main(["x", "gh workflow run deploy.yml -f environment=$E"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("block\t") and "could not tell" in out
    assert "\n" not in out.rstrip("\n")


def test_the_helper_never_names_the_endpoint_itself():
    """No second reader: the endpoint's spelling is crew_dispatch's alone."""
    here = os.path.dirname(os.path.abspath(helper.__file__))
    for name in ("_promote_dispatch.py", "promote-gate.sh"):
        with open(os.path.join(here, name), encoding="utf-8") as fh:
            text = fh.read()
        assert "_DISPATCH_RE" not in text and "/dispatches" not in text, name


def test_a_literal_placeholder_word_is_compared_like_any_value(project):
    """T-0062 review r1: a declared value written as the placeholder word,
    with no substitution behind it, must not match every value."""
    project({"dev": {"deploy": "gh workflow run deploy.yml -f environment=SUBSTITUTED"}})
    with pytest.raises(helper.Block, match="fits no declared environment"):
        helper.decide("gh workflow run deploy.yml -f environment=production")
    assert helper.decide("gh workflow run deploy.yml -f environment=SUBSTITUTED") \
        == ["env\tdev"]


def test_a_substitution_beside_a_literal_placeholder_word_is_still_skipped(project):
    project({"dev": {"deploy": "gh workflow run deploy.yml -f environment=SUBSTITUTED "
                               "-f ref=$(git rev-parse HEAD)"}})
    assert helper.decide("gh workflow run deploy.yml -f environment=SUBSTITUTED "
                         "-f ref=abc") == ["env\tdev"]
    with pytest.raises(helper.Block, match="fits no declared environment"):
        helper.decide("gh workflow run deploy.yml -f environment=production -f ref=abc")


@pytest.mark.parametrize("text,word", [
    ("x", "SUBSTITUTED"), ("a=SUBSTITUTED", "SUBSTITUTED1"),
    ("SUBSTITUTED SUBSTITUTED1", "SUBSTITUTED2")])
def test_placeholder_is_a_word_the_text_does_not_hold(text, word):
    assert helper.placeholder(text) == word
