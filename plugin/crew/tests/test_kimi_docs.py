"""The Kimi provider docs say what the code does (T-0028).

crew-providers, model.md and providers.sh name the owner's three ids, the
probe's states and how to run it. review.md, which /crew:review follows, names
the Kimi launch the way review_run.py does (L-0527): it is the mechanism, not
commentary, and a probe row that said `command -v kimi` would put
PATH-as-eligibility back, which is the exact thing `kimi_probe.py` replaces.
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_state
import review_run

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(CREW, "..", "..", "docs", "crew", "review.md")
KIMI_IDS = ("k3", "kimi-for-coding", "kimi-for-coding-highspeed")


def _read(*parts):
    with open(os.path.join(CREW, *parts), encoding="utf-8") as fh:
        return fh.read()


def _doc():
    """docs/crew/review.md: the rationale the cut-down review.md no longer carries (L-0726)."""
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


def _report(kimi_model="k3"):
    return {"qa": [{"role": "review", "provider": "kimi", "model": kimi_model}],
            "qaProviders": {"codex": {"model": "gpt-x", "reasoningEffort": "high"}},
            "qaFallThrough": [{"provider": "codex", "eligible": True},
                              {"provider": "kimi", "eligible": True},
                              {"provider": "claude", "eligible": False}]}


def _context(report=None):
    return review_run.Context(".", "T1", ".work/review/x", report or _report(), "claude", "config")


def test_review_walk_has_a_kimi_row_that_runs_the_review_not_a_path_check():
    """The walk launches Kimi directly (review_run.py probes it itself); Codex is the one probed."""
    kimi = _context().walk(["kimi"])
    codex = _context().walk(["codex"])

    assert "--provider kimi" in kimi and "--probe" not in kimi and "kimi_probe" not in kimi
    assert "command -v kimi" not in kimi
    assert "--probe" in codex


def test_review_never_gates_kimi_on_path_alone():
    assert "command -v kimi" not in _read("commands", "review.md")


def test_review_resolves_and_runs_the_kimi_model():
    assert review_run.qm(_report("k3"), "kimi", "model") == "k3"
    assert review_run.qm(_report(""), "kimi", "model") == ""
    assert "--provider kimi --model k3" in _context().walk(["kimi"])
    assert "--provider kimi --model ''" in _context(_report("")).walk(["kimi"])


def test_review_description_names_kimi():
    front = _read("commands", "review.md").split("---", 2)[1]

    assert "Kimi" in front


def test_review_names_no_kimi_id_outside_the_owner_three():
    text = _read("commands", "review.md")
    named = set(re.findall(r"`(k\d[\w.-]*|kimi-(?!code/)[\w.-]+)`", text))

    assert named <= set(KIMI_IDS), named - set(KIMI_IDS)


def test_review_eligible_filter_keeps_kimi():
    """L-0527: the $ELIGIBLE filter named codex, copilot and claude only, so a kimi the
    report called eligible was dropped with "no review runner"."""
    said = []

    result = review_run.eligible(_report(), said.append)

    assert result == ["codex", "kimi"] and said == []
    assert "kimi" in review_run.PROVIDERS


def test_the_three_ids_appear_in_crew_providers_and_model_md():
    for text in (_read("skills", "crew-providers", "SKILL.md"), _read("commands", "model.md")):
        assert all(f"`{model}`" in text for model in KIMI_IDS)


def test_model_md_offers_the_pin_table_and_says_it_is_not_shipped():
    """One line, not a table: model.md is at its `.budget-allowance.json`
    ceiling, so the offered pins are stated compactly."""
    line = next(l for l in _read("commands", "model.md").splitlines()
                if l.startswith("**Kimi pins crew OFFERS"))

    for pin in ("`qa.roles.review` -> kimi `k3`", "`qa.roles.gate` -> kimi `kimi-for-coding`",
                "`qa.roles.smoke` -> kimi `kimi-for-coding-highspeed`",
                "`dev.roles.planner` -> kimi `k3`"):
        assert pin in line, pin
    assert "not shipped" in line


def test_crew_providers_documents_the_probe_states_and_the_read_only_gap():
    text = _read("skills", "crew-providers", "SKILL.md")

    for state in ("not-installed", "not-authenticated", "rate-limited", "unknown"):
        assert f"`{state}`" in text, state
    assert "outside the repo" in text
    assert "kimi login" in text
    assert "https://code.kimi.com/kimi-code/install.sh" in text


def test_crew_providers_family_rule_is_not_the_retired_split():
    text = _read("skills", "crew-providers", "SKILL.md")

    assert 'model.split("-")[0]' not in text
    assert len(text.splitlines()) < 500


def test_alternative_providers_points_to_the_first_class_kimi_route():
    text = _read("skills", "crew-providers", "alternative-providers.md")
    section = " ".join(text.split("## Kimi through Codex", 1)[1][:800].split())

    assert "Kimi Code CLI is its own provider" in section


def _providers_sh(tmp_path, *args):
    """Run providers.sh with a fake `kimi` and fake pythons on PATH; return
    (stdout, every argv a python was invoked with)."""
    fakes = tmp_path / "bin"
    fakes.mkdir(parents=True)
    log = tmp_path / "python-calls.txt"
    (fakes / "kimi").write_text("#!/bin/sh\necho 'kimi 2.1.1'\n", encoding="utf-8",
                                newline="\n")
    for name in ("python3", "python", "py"):
        (fakes / name).write_text(f'#!/bin/sh\necho "$*" >> "{log}"\n'
                                  'echo "kimi: ok - fake"\n', encoding="utf-8", newline="\n")
    for script in fakes.iterdir():
        script.chmod(0o755)
    env = dict(os.environ, PATH=f"{fakes}{os.pathsep}/usr/bin{os.pathsep}/bin",
               HOME=str(tmp_path))
    done = subprocess.run(["bash", os.path.join(CREW, "skills", "crew-setup", "scripts",
                                                "providers.sh"), *args],
                          env=env, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL, timeout=60)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return done.stdout, calls


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt",
                    reason="providers.sh is a bash script; runs where bash is /bin-rooted")
def test_providers_sh_reports_kimi_and_probes_only_on_request(tmp_path):
    """Round 1 FIX (test_kimi_docs.py:103): the old check never used its loop
    variable, so an UNCONDITIONAL probe -- one Kimi request on every
    providers.sh run -- passed. Run the script instead of reading it."""
    quiet_out, quiet_calls = _providers_sh(tmp_path / "quiet")
    asked_out, asked_calls = _providers_sh(tmp_path / "asked", "--probe-kimi")

    assert "kimi 2.1.1" in quiet_out and "kimi: ok - fake" in asked_out
    assert [c for c in quiet_calls if "kimi_probe.py" in c] == []
    assert len([c for c in asked_calls if "kimi_probe.py" in c]) == 1


def _gate_matches(path, pat):
    """verify-gate.sh's `matches()`, as written there."""
    cands = {pat}
    if pat.startswith("**/"):
        cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)


_KIMI_SUITE = ("test_kimi_probe.py", "test_kimi_stream.py", "test_kimi_docs.py",
               "test_review_run_kimi.py")


@pytest.mark.parametrize("path,needs", [
    *[(f"plugin/crew/{p}", _KIMI_SUITE) for p in (
        "hooks/scripts/kimi_probe.py", "hooks/scripts/review_run.py",
        "tests/test_kimi_probe.py", "tests/test_review_run_kimi.py", "tests/sabotage_kimi.py",
        "commands/review.md",
        "tests/test_kimi_stream.py", "tests/test_kimi_docs.py", "tests/kimi_fixtures.py",
        "tests/fixtures/kimi-stream-2.1.1/ok.jsonl",
        "tests/fixtures/kimi-stream-2.1.1/ok.exit",
        "skills/crew-setup/scripts/providers.sh",
        "skills/crew-providers/SKILL.md", "commands/model.md",
        "skills/crew-providers/alternative-providers.md")],
    ("plugin/crew/hooks/scripts/crew_state.py", ("test_provider_table.py",)),
    ("plugin/crew/skills/crew-setup/SKILL.md", ("test_crew_config.py",)),
    ("plugin/crew/CONFIG.md", ("test_crew_config.py",)),
    ("plugin/crew/templates/config.template.json", ("test_crew_config.py",)),
])
def test_every_kimi_file_reaches_a_rule_that_runs_its_tests(path, needs):
    """Round 1 FIX (.crew/verify.json:263): the fake kimi, the fixture and two
    Kimi test files matched no rule running the Kimi suite, and crew_state.py's
    rule never ran test_provider_table.py, which holds the family guard. Round
    3 FIX (.crew/verify.json:168): crew-setup SKILL.md carries the Kimi
    defaults test_crew_config.py compares, yet no rule that maps it ran that
    module, so a broken template passed the Stop gate."""
    with open(os.path.join(CREW, "..", "..", ".crew", "verify.json"), encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]

    runs = " ".join(c for r in rules if any(_gate_matches(path, p) for p in r["paths"])
                    for c in r["run"])

    assert [n for n in needs if n not in runs] == [], path


def test_every_file_this_module_reads_is_mapped_to_it():
    """Round 2 FIX (.crew/verify.json:275): model.md and
    alternative-providers.md carried Kimi prose this module checks, yet no rule
    that runs this module mapped them. Derived from this file's own `_read`
    calls, so a new prose check cannot land without its mapping."""
    with open(os.path.abspath(__file__), encoding="utf-8") as fh:
        source = fh.read()
    read = {"/".join(re.findall(r'"([^"]+)"', args))
            for args in re.findall(r"_read\(((?:\s*\"[^\"]+\",?)+)\s*\)", source)}
    with open(os.path.join(CREW, "..", "..", ".crew", "verify.json"), encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]

    unmapped = [rel for rel in sorted(read)
                if not any("test_kimi_docs.py" in " ".join(r["run"]) for r in rules
                           if any(_gate_matches(f"plugin/crew/{rel}", p) for p in r["paths"]))]

    assert (len(read) >= 4, unmapped) == (True, [])


def test_the_kimi_verify_rule_is_timed_not_a_placeholder():
    """Round 6 FIX 4: the Kimi rule shipped saying its seconds were a placeholder."""
    with open(os.path.join(CREW, "..", "..", ".crew", "verify.json"), encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]
    rule = next(r for r in rules if "plugin/crew/hooks/scripts/kimi_probe.py" in r["paths"])

    assert "placeholder" not in rule["why"] and "timed" in rule["why"].lower()


def _step_1b_rows():
    table = _doc().split("| `dev.provider` | Struck from QA |", 1)[1].split("\n\n", 1)[0]
    return {line.split("|")[1].strip(): line for line in table.splitlines()
            if line.startswith("| `")}


def test_review_step_1b_strikes_kimi_for_a_kimi_author():
    """Round 1 FIX: the strike table had no kimi row, so a kimi-authored diff gave the
    agent nothing to strike. The rule is crew_state.family's; the table is its rationale."""
    row = _step_1b_rows()["`kimi`"]

    assert "`kimi`" in row.split("|")[2] and "`kimi-*`" in row
    assert crew_state.family("kimi", None) == "kimi"


def test_review_step_1b_copilot_kimi_pin_strikes_kimi():
    assert "`kimi-*` strikes Kimi" in _step_1b_rows()["`copilot`"]
    assert crew_state.family("copilot", "kimi-for-coding") == "kimi"


def test_review_kimi_probe_row_spends_one_request_not_two():
    """Round 1 NIT: the walk ran kimi_probe.py, and then review_run.py ran it again -- two
    live requests per Kimi review."""
    text = _read("commands", "review.md")
    step = text.split("**Step 2e - Kimi.**", 1)[1].split("\n\n", 1)[0]

    assert "Needs no probe from you" in step and "review_run.py` runs `kimi_probe.py` itself" in step
    assert "--probe" not in _context().walk(["kimi"])


def test_review_kimi_step_label_names_one_step():
    """Round 3 NIT: Kimi was labelled 2d beside an existing **Step 2d** heading, so a
    "step 2d" led to two steps."""
    body = _read("commands", "review.md")
    headings = re.findall(r"^\*\*Step ([^*]+?)\*\*", body, re.M)
    kimi = [h for h in headings if "Kimi" in h]
    labelled_2d = [h for h in headings if re.match(r"2d\b", h)]

    assert len(kimi) == 1 and kimi[0].startswith("2e "), kimi
    assert len(labelled_2d) == 1 and "Kimi" not in labelled_2d[0], labelled_2d


def test_review_kimi_paragraph_names_what_is_set_aside():
    """Round 3 NIT: the prose said only graph.out was set aside while the code set aside
    more; it now names the same set as the code."""
    para = next(line for line in _doc().splitlines()
                if line.startswith("Kimi reads the same `$SCRATCH/prompt.txt`"))

    assert [t for t in ("graph.out", ".idea/", ".vscode/", ".crew/guard.log",
                        ".crew/.autoclear.log", "__pycache__") if t not in para] == []


# --- review round 4 (T-0028): the exit code and the fingerprint facts ------------


def _probe_changed_code():
    found = re.findall(r"^EXIT_PROBE_CHANGED = (\d+)$",
                       _read("hooks", "scripts", "review_run.py"), re.MULTILINE)
    assert len(found) == 1, found
    return found[0]


def test_review_md_names_the_probe_changed_exit_code():
    """An exit code review.md does not name reads as "not run", and walks to
    the next provider against a tree the probe changed."""
    body = " ".join(_read("commands", "review.md").split())
    code = _probe_changed_code()

    assert (f"Exit {code}, the probe changed the tree: stop and report the named paths; "
            "do not walk to the next provider") in body
    assert "do not walk to the next provider" in review_run.NEXT_CODES[review_run.EXIT_PROBE_CHANGED]


def test_review_md_states_the_round_4_fingerprint_facts():
    """crew-providers SKILL.md states the same facts in the follow-up feature PR."""
    text = " ".join(_doc().split())

    assert [t for t in ("permission bits", "symlink", "never opened",
                        "outside the repository is could-not-tell",
                        "`GRAPH_REPORT.md`", "never reserved unprobed")
            if t not in text] == []


def test_review_md_a_pinned_kimi_hard_fails_on_a_failed_probe():
    """Round 5 of T-0028: the Kimi step said exit 2 always skips, contradicting
    the rule that a pinned provider whose probe fails is an error."""
    body = " ".join(_read("commands", "review.md").split())

    assert "skip it, or hard-fail if `qa.provider` pins `kimi`" in body
