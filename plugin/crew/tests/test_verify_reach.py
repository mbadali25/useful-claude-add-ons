"""`/crew:verify --stamp-reach` (L-0562): proposals come from the Stop gate's
own classifier, `--apply` changes neither what the gate runs nor its price (caches re-keyed), a deferred rule
runs only on an explicit `--set`, and the map's text is edited in place, never
re-serialised. Every map is a throwaway file under tmp_path."""
import json
import os

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


def test_proposals_follow_the_gates_own_classifier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, vmap = verify_reach.load(str(_repo(tmp_path)))
    got = {e["index"]: e["propose"] for e in verify_reach.plan(vmap)}
    assert got == {0: "local", 1: "network", 2: None}  # rule 3 already declares reach


def test_dry_run_writes_nothing_and_names_the_undecided_rule(tmp_path, capsys):
    path = _repo(tmp_path)
    assert _run(tmp_path) == 0
    out = capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == MAP
    assert "undecided: rules 2" in out and "SKIPPED on Stop" in out and "dry run" in out


CACHED = """{"rules": [
  {"paths": ["a"], "run": ["true"], "seconds": 200},
  {"paths": ["b"], "run": ["python3 -m pytest b -q"]},
  {"paths": ["c"], "run": ["curl -fsS https://qa.example/x"], "seconds": 3},
  {"paths": ["d"], "run": ["true"], "requiresCleanTree": true}
]}
"""


def _gate_view(rule, timings, root):
    """verify-gate.sh's view of one matched rule on Stop (~1036-1081): what
    excludes it, its price, and whether it is truly unknown (mandatory)."""
    cached = timings.get(verify_record.rule_key(rule))
    secs = rule.get("seconds")
    if isinstance(secs, (int, float)):
        price = cached if isinstance(cached, int) and 0 < cached < secs else secs
    else:
        price = cached if isinstance(cached, int) and cached > 0 else None
    reach = rule.get("reach")
    if rule.get("requiresCleanTree") is True:
        excluded = "clean_tree_required"
    elif isinstance(reach, str) and reach != "local":
        excluded = "reach_declared"
    elif reach is None and verify_record.scan_reach(rule["run"], root)[0] != "local":
        excluded = "reach_undeclared"
    else:
        excluded = None
    return excluded is None, price, price is None


def test_apply_never_changes_what_the_stop_gate_runs(tmp_path):
    """Runs, price and mandatory status are the same before and after, with
    the measured-timings cache and the record in play: `reach` is part of
    rule_key, so the stamp has to carry their entries to the new keys."""
    path = _repo(tmp_path, CACHED)
    before = json.loads(CACHED)["rules"]
    keys = [verify_record.rule_key(r) for r in before]
    timings = tmp_path / ".crew" / ".verify-gate.timings.json"
    timings.write_text(json.dumps({"rules": {keys[0]: 5, keys[1]: 7}}), encoding="utf-8")
    record = tmp_path / ".crew" / ".verify-gate.record.json"
    owed = {"status": "reach_undeclared", "reason": "x", "label": "rules[2]", "sha": "s"}
    record.write_text(json.dumps({"rules": {keys[2]: owed}}), encoding="utf-8")
    view = [_gate_view(r, {keys[0]: 5, keys[1]: 7}, str(tmp_path)) for r in before]
    assert view[:2] == [(True, 5, False), (True, 7, False)]  # priced from the cache

    assert _run(tmp_path, "--apply") == 0
    after = json.loads(path.read_text(encoding="utf-8"))["rules"]
    assert [r.get("reach") for r in after] == ["local", "local", "network", "local"]
    cache = json.loads(timings.read_text(encoding="utf-8"))["rules"]
    assert [_gate_view(r, cache, str(tmp_path)) for r in after] == view
    rec = json.loads(record.read_text(encoding="utf-8"))["rules"]
    assert rec == {verify_record.rule_key(after[2]): owed}  # the obligation moved, not orphaned


def test_an_unreadable_cache_is_named_and_the_map_still_written(tmp_path, capsys):
    path = _repo(tmp_path, CACHED)
    (tmp_path / ".crew" / ".verify-gate.timings.json").write_text("{ nope", encoding="utf-8")
    assert _run(tmp_path, "--apply") == 0
    assert "timings.json is unreadable" in capsys.readouterr().err
    assert json.loads(path.read_text(encoding="utf-8"))["rules"][0]["reach"] == "local"


def test_a_null_reach_is_undeclared_and_replaced_not_duplicated(tmp_path):
    text = ('{"rules": [{"paths": ["a"], "run": ["true"], "reach": null},\n'
            '  {"paths": ["b"], "run": ["bash -c x"], "reach": null}, {}]}\n')
    path = _repo(tmp_path, text)
    assert _run(tmp_path, "--apply", "--set", "1=host") == 0
    out = path.read_text(encoding="utf-8")
    assert out.count('"reach"') == 3 and "null" not in out
    assert [r.get("reach") for r in json.loads(out)["rules"]] == ["local", "host", "local"]


def test_it_classifies_from_root_as_the_gate_classifies_from_its_cwd(tmp_path, monkeypatch):
    seen = []
    real = verify_record.scan_reach
    monkeypatch.setattr(verify_record, "scan_reach",
                        lambda run, root: seen.append((root, os.getcwd())) or real(run, root))
    _repo(tmp_path)
    assert _run(tmp_path) == 0
    assert seen and all(r == cwd == os.path.realpath(tmp_path) for r, cwd in seen)


def test_a_clean_tree_rule_is_not_shown_as_running(tmp_path, capsys):
    _repo(tmp_path, CACHED)
    assert _run(tmp_path) == 0
    row = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("| 3 |")][0]
    assert "SKIPPED on Stop (requiresCleanTree)" in row


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
