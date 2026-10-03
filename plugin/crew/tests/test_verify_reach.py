"""`/crew:verify --stamp-reach` (L-0562): proposals come from the Stop gate's
own classifier, `--apply` never changes what the gate runs, a deferred rule
runs only on an explicit `--set`, and the map's text is edited in place, never
re-serialised. Every map is a throwaway file under tmp_path."""
import json

import context  # noqa: F401  pylint: disable=unused-import
import verify_reach
import verify_record

# Hand-formatted on purpose: the stamp must leave every other byte alone.
MAP = """{
  "version": 1,
  "_note": "a value that says \\"rules\\": [ must not be read as the key",
  "rules": [
    { "paths": ["src/**"], "run": ["python3 -m pytest tests -q"], "seconds": 4 },
    { "paths": ["web/**"], "run": ["curl -fsS https://qa.example/health"], "seconds": 2 },
    { "paths": ["db/**"],  "run": ["bash -c 'make migrate-check'"], "seconds": 9 },
    { "paths": ["docs/**"], "run": ["true"], "reach": "local", "seconds": 1 }
  ],
  "unmapped": "fail"
}
"""


def _repo(tmp_path, text=MAP):
    path = tmp_path / ".crew" / "verify.json"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _run(tmp_path, *args):
    return verify_reach.main(["--root", str(tmp_path), *args])


def test_proposals_follow_the_gates_own_classifier(tmp_path):
    _, vmap = verify_reach.load(str(_repo(tmp_path)))
    got = {e["index"]: e["propose"] for e in verify_reach.plan(vmap, str(tmp_path))}
    assert got == {0: "local", 1: "network", 2: None}  # rule 3 already declares reach


def test_dry_run_writes_nothing_and_names_the_undecided_rule(tmp_path, capsys):
    path = _repo(tmp_path)
    assert _run(tmp_path) == 0
    out = capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == MAP
    assert "undecided: rules 2" in out and "SKIPPED on Stop" in out and "dry run" in out


def test_apply_never_changes_what_the_stop_gate_runs(tmp_path):
    path = _repo(tmp_path)
    before = json.loads(MAP)["rules"]
    assert _run(tmp_path, "--apply") == 0
    after = json.loads(path.read_text(encoding="utf-8"))["rules"]
    for old, new in zip(before, after):
        runs_before = "reach" in old and old["reach"] == "local" or "reach" not in old and \
            verify_record.scan_reach(old["run"], str(tmp_path))[0] == "local"
        runs_after = new.get("reach") == "local" or "reach" not in new and \
            verify_record.scan_reach(new["run"], str(tmp_path))[0] == "local"
        assert runs_before == runs_after, new
    assert [r.get("reach") for r in after] == ["local", "network", None, "local"]


def test_apply_edits_text_in_place_and_keeps_every_other_byte(tmp_path):
    path = _repo(tmp_path)
    assert _run(tmp_path, "--apply") == 0
    text = path.read_text(encoding="utf-8")
    assert text.replace(' "reach": "local",', "", 1).replace(' "reach": "network",', "", 1) == MAP


def test_apply_keeps_crlf_line_endings(tmp_path):
    path = tmp_path / ".crew" / "verify.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(MAP.replace("\n", "\r\n").encode("utf-8"))
    assert _run(tmp_path, "--apply") == 0
    raw = path.read_bytes().decode("utf-8")
    assert "\n" not in raw.replace("\r\n", "")
    assert raw.replace(' "reach": "local",', "", 1).replace(' "reach": "network",', "", 1) == MAP.replace("\n", "\r\n")


def test_a_deferred_rule_runs_only_on_an_explicit_set(tmp_path):
    path = _repo(tmp_path)
    assert _run(tmp_path, "--apply", "--set", "2=local") == 0
    assert json.loads(path.read_text(encoding="utf-8"))["rules"][2]["reach"] == "local"


def test_set_overrides_a_proposal(tmp_path):
    path = _repo(tmp_path)
    assert _run(tmp_path, "--apply", "--set", "0=host") == 0
    assert json.loads(path.read_text(encoding="utf-8"))["rules"][0]["reach"] == "host"


def test_bad_sets_are_refused_and_write_nothing(tmp_path, capsys):
    path = _repo(tmp_path)
    for bad, why in (("2=remote", "expected N="), ("9=local", "no rule 9"), ("x=local", "expected N="),
                     ("3=network", "already declares reach")):
        assert _run(tmp_path, "--apply", "--set", bad) == 1, bad
        assert why in capsys.readouterr().err, bad
        assert path.read_text(encoding="utf-8") == MAP


def test_an_unreadable_map_is_refused(tmp_path, capsys):
    _repo(tmp_path, "{ not json")
    assert _run(tmp_path, "--apply") == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_a_fully_declared_map_is_left_alone(tmp_path, capsys):
    text = '{"rules": [{"paths": ["a"], "run": ["true"], "reach": "local"}]}\n'
    path = _repo(tmp_path, text)
    assert _run(tmp_path, "--apply") == 0
    assert "already declares reach" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == text


def test_a_text_edit_that_does_not_round_trip_is_refused(tmp_path):
    text = MAP
    _, vmap = verify_reach.load(str(_repo(tmp_path)))
    vmap["rules"].append({"paths": ["x"], "run": ["true"]})  # text and map now disagree
    try:
        verify_reach.stamp_text(text, vmap, {0: "local"})
    except ValueError as exc:
        assert "disagrees" in str(exc)
    else:
        raise AssertionError("a text/map mismatch was written")


def test_an_insert_at_the_wrong_rule_is_caught_by_the_round_trip(tmp_path, monkeypatch):
    """The parse-back check is what stands between a mis-located insert and a
    silently wrong map; prove it fires on one."""
    _, vmap = verify_reach.load(str(_repo(tmp_path)))
    real = verify_reach._rule_offsets  # pylint: disable=protected-access
    monkeypatch.setattr(verify_reach, "_rule_offsets", lambda text: real(text)[1:] + real(text)[:1])
    try:
        verify_reach.stamp_text(MAP, vmap, {0: "local"})
    except ValueError as exc:
        assert "round-trip" in str(exc)
    else:
        raise AssertionError("an insert into the wrong rule was accepted")
