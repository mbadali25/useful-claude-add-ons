"""crew-qa-standards' QA-process doc generator (L-0618): dry run writes
nothing, the diagrams are embedded in the Markdown and drawn from declared
data only, and a hand-written file is refused rather than overwritten."""
import json
import re

import context  # noqa: F401  pylint: disable=unused-import
import qa_audit_env
import qa_doc


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _ladder_repo(root):
    _write(root, ".crew/verify.json", json.dumps({
        "rules": [{"paths": ["src/**"], "run": ["pytest -q"], "reach": "local", "seconds": 3}],
        "environments": {
            "development": {"deploy": ["./d.sh dev"], "smoke": ["bash _verify/smoke.sh --env dev"],
                            "promotesTo": "qa"},
            "qa": {"requires": ["development"], "deploy": ["./d.sh qa"], "smoke": ["s"],
                   "regression": ["r"], "promotesTo": "production"},
            "production": {"requires": ["qa"], "deploy": ["./d.sh prod"], "requireHuman": True},
        }}))


def test_dry_run_writes_nothing(tmp_path, capsys):
    _ladder_repo(tmp_path)
    assert qa_doc.main(["--root", str(tmp_path)]) == 0
    assert "dry run" in capsys.readouterr().out
    assert not (tmp_path / "docs").exists()


def test_write_embeds_both_diagrams_in_the_markdown(tmp_path):
    _ladder_repo(tmp_path)
    assert qa_doc.main(["--root", str(tmp_path), "--write"]) == 0
    md = (tmp_path / "docs/qa/README.md").read_text(encoding="utf-8")
    assert md.count("```mermaid") == 3
    assert "flowchart LR" in md and "flowchart TD" in md
    html = (tmp_path / "docs/qa/qa-process.html").read_text(encoding="utf-8")
    assert html.count('<pre class="mermaid">') == 3 and "<table>" in html
    for rel in ("docs/diagrams/process-qa-gates.mmd", "docs/diagrams/process-qa-ladder.mmd",
                "docs/diagrams/process-qa-audit.mmd"):
        assert (tmp_path / rel).read_text(encoding="utf-8").startswith("%% anchor: ")


def test_ladder_draws_each_edge_once_and_marks_missing_gates():
    envs = {"development": {"deploy": ["d"], "promotesTo": "qa"},
            "qa": {"requires": ["development"], "deploy": ["d"], "smoke": ["s"], "regression": ["r"]}}
    text = qa_doc.ladder_diagram(envs)
    assert text.count("env_development -->|promote| env_qa") == 1
    assert "merge --> env_development" in text and "merge --> env_qa" not in text
    dev = next(ln for ln in text.splitlines() if ln.strip().startswith("env_development["))
    assert dev.endswith(":::gap") and "missing: smoke, regression" in dev


def _edges(text):
    """Every edge, including each link of a chain like `a --> b --> a`."""
    edges = []
    for line in text.splitlines():
        parts = line.split("-->")
        ids = [re.match(r"\s*(?:\|[^|]*\|)?\s*(\w+)", part).group(1) for part in parts]
        edges += list(zip(ids, ids[1:]))
    return edges


def test_the_gate_diagram_has_no_back_edge():
    """A red result that loops back to an earlier gate is what made Mermaid
    cross lines; every node may be entered only from above it."""
    edges = _edges(qa_doc.gates_diagram("ok", [{}], ["ci.yml"]))
    order = []
    for src, dst in edges:
        for node in (src, dst):
            if node not in order:
                order.append(node)
    assert all(order.index(src) < order.index(dst) for src, dst in edges), edges


def test_the_audit_diagram_says_partial_not_record_why_not():
    text = qa_doc.audit_diagram([])
    assert "partial" in text and "record why not" not in text


def test_no_environments_is_drawn_as_missing_not_invented():
    text = qa_doc.ladder_diagram({})
    assert "no environments declared" in text and "env_" not in text


def test_labels_cannot_break_mermaid():
    assert qa_doc._label('a "quoted" name') == '"a #quot;quoted#quot; name"'  # pylint: disable=protected-access


def test_a_hand_written_doc_is_refused_and_kept(tmp_path, capsys):
    _ladder_repo(tmp_path)
    _write(tmp_path, "docs/qa/README.md", "# our QA notes\n")
    assert qa_doc.main(["--root", str(tmp_path), "--write"]) == 1
    assert (tmp_path / "docs/qa/README.md").read_text(encoding="utf-8") == "# our QA notes\n"
    assert "REFUSED docs/qa/README.md" in capsys.readouterr().err
    assert (tmp_path / "docs/qa/qa-process.html").exists()


def test_a_generated_doc_is_regenerated(tmp_path):
    _ladder_repo(tmp_path)
    assert qa_doc.main(["--root", str(tmp_path), "--write"]) == 0
    assert qa_doc.main(["--root", str(tmp_path), "--write"]) == 0


def test_html_escapes_repo_content(tmp_path):
    _write(tmp_path, ".crew/verify.json", json.dumps({"rules": [
        {"paths": ["<script>"], "run": ["echo <b>x</b>"], "reach": "local", "seconds": 1}]}))
    html = qa_doc.render_html(qa_doc.collect(str(tmp_path)))
    assert "<script>\"" not in html and "&lt;script&gt;" in html


def test_printed_paths_use_forward_slashes_on_every_os():
    """crew-windows-default printed `docs\\qa\\README.md`; output must not depend on the OS."""
    assert qa_audit_env.posix("docs\\qa\\README.md") == "docs/qa/README.md"
