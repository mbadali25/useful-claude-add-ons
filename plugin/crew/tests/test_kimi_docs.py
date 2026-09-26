"""The prose /crew:review follows names Kimi the way the code does (T-0028).

review.md is the mechanism, not commentary: a probe row that said
`command -v kimi` would put PATH-as-eligibility back, which is the exact thing
`kimi_probe.py` exists to replace.
"""
import os
import re

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIMI_IDS = ("k3", "kimi-for-coding", "kimi-for-coding-highspeed")


def _read(*parts):
    with open(os.path.join(CREW, *parts), encoding="utf-8") as fh:
        return fh.read()


def _probe_rows(text):
    return [line for line in text.splitlines()
            if line.startswith("| `") and "| step 2" in line]


def test_review_probe_table_has_a_kimi_row_that_runs_the_probe():
    rows = [r for r in _probe_rows(_read("commands", "review.md")) if r.startswith("| `kimi`")]

    assert len(rows) == 1 and "kimi_probe" in rows[0]
    assert "command -v kimi" not in rows[0]


def test_review_never_gates_kimi_on_path_alone():
    assert "command -v kimi" not in _read("commands", "review.md")


def test_review_resolves_and_runs_the_kimi_model():
    text = _read("commands", "review.md")

    assert "QA_KIMI_MODEL=$(qm kimi model)" in text
    assert '--provider kimi --model "$QA_KIMI_MODEL"' in text


def test_review_description_names_kimi():
    front = _read("commands", "review.md").split("---", 2)[1]

    assert "Kimi" in front


def test_review_names_no_kimi_id_outside_the_owner_three():
    text = _read("commands", "review.md")
    named = set(re.findall(r"`(k\d[\w.-]*|kimi-(?!code/)[\w.-]+)`", text))

    assert named <= set(KIMI_IDS), named - set(KIMI_IDS)


def test_the_three_ids_appear_in_crew_providers_and_model_md():
    for text in (_read("skills", "crew-providers", "SKILL.md"), _read("commands", "model.md")):
        assert all(f"`{model}`" in text for model in KIMI_IDS)


def test_model_md_offers_the_pin_table_and_says_it_is_not_shipped():
    text = _read("commands", "model.md")
    rows = [line for line in text.splitlines() if "| kimi |" in line and "`qa.roles." in line
            or "`dev.roles.planner`" in line and "| kimi |" in line]

    assert len(rows) == 4, rows
    assert "not shipped" in text.lower()


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
    section = text.split("## Kimi through Codex", 1)[1][:800]

    assert "--provider kimi" in section or "Kimi Code CLI" in section


def test_providers_sh_reports_kimi_and_probes_only_on_request():
    text = _read("skills", "crew-setup", "scripts", "providers.sh")

    assert "command -v kimi" in text and "kimi_probe.py" in text
    probe_lines = [line for line in text.splitlines()
                   if "kimi_probe.py" in line and not line.lstrip().startswith(("#", "say"))]
    assert probe_lines and all("--probe-kimi" in text for _ in probe_lines)
    assert 'if [ "$PROBE_KIMI" = 1 ]' in text
