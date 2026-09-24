"""`gizmoduck_ci.py render` - golden files for both platforms, dry-run by default,
no overwrite without --force, and the render-time half of the prod-refusal guard.

Golden files live in fixtures/ci/. They are rendered from GOLDEN_CFG below with a
fixed version, so a plugin version bump does not churn them. After an intended
template change, regenerate with:

    GIZMODUCK_UPDATE_GOLDEN=1 python3 -m pytest scripts/_test/test_ci_render.py

and read the diff before committing it.
"""
import os
import subprocess
import sys
from pathlib import Path

import ci_render
import pytest
import yaml

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"
_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "ci"

GOLDEN_CFG = {
    "version": "0.0.0-golden",
    "staging_urls": ["https://staging.example.com"],
    "authorized_by": "Jane Doe (CISO), ticket SEC-42 - 'quoted' \"too\"",
    "enable": ["nikto", "nmap"],
    "image": "ghcr.io/example/gizmoduck-ci:0.0.0-golden",
    "gizmoduck_ref": "0123456789abcdef0123456789abcdef01234567",
    "source_repo": ci_render.SOURCE_REPO,
    "default_branch": "main",
    "staging_environment": "staging",
    "deploy_workflow": "Deploy staging",
    "bitbucket_out": None,
}

GOLDEN_FILES = {
    ".github/workflows/gizmoduck-code.yml": "github-code.yml",
    ".github/workflows/gizmoduck-endpoints.yml": "github-endpoints.yml",
    "bitbucket-pipelines.yml": "bitbucket-pipelines.yml",
}


@pytest.mark.parametrize("rel,golden", sorted(GOLDEN_FILES.items()))
def test_golden(rel, golden):
    rendered = ci_render.render_all(GOLDEN_CFG, ("github", "bitbucket"))[rel]
    path = _GOLDEN / golden
    if os.environ.get("GIZMODUCK_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rendered.encode("utf-8"))
    assert rendered == path.read_bytes().decode("utf-8")


@pytest.mark.parametrize("rel", sorted(GOLDEN_FILES))
def test_rendered_yaml_parses_and_carries_the_config(rel):
    text = ci_render.render_all(GOLDEN_CFG, ("github", "bitbucket"))[rel]
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    assert "\r" not in text and "@@" not in text
    assert "Jane Doe (CISO)" in text


def test_every_action_is_pinned_by_full_sha():
    text = "".join(ci_render.render_all(GOLDEN_CFG, ("github",)).values())
    uses = [ln.split("uses:", 1)[1].strip() for ln in text.splitlines() if "uses:" in ln]
    assert uses
    for u in uses:
        ref = u.split("@", 1)[1].split()[0]
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), u


def test_endpoint_workflow_guards_before_it_scans():
    text = ci_render.github_endpoints(GOLDEN_CFG)
    for job in ("  scan:\n", "  scan-bootstrap:\n"):
        body = text.split(job, 1)[1]
        assert body.index(" targets ") < body.index(" endpoint-stage ")
    bb = ci_render.bitbucket(GOLDEN_CFG)
    step = bb.split("&gizmoduck-endpoint-scan", 1)[1]
    assert step.index(" targets ") < step.index(" endpoint-stage ")


def test_opt_in_tools_off_by_default():
    cfg = dict(GOLDEN_CFG, enable=[])
    text = "".join(ci_render.render_all(cfg, ("github", "bitbucket")).values())
    assert 'GIZMODUCK_ENABLE: ""' in text and "export GIZMODUCK_ENABLE=''" in text
    assert "nikto" not in text and "sqlmap" not in text and "nmap" not in text


def test_no_workflow_run_trigger_without_deploy_workflow():
    text = ci_render.github_endpoints(dict(GOLDEN_CFG, deploy_workflow=None))
    assert "workflow_run" not in text


# --- the CLI ----------------------------------------------------------------

def render(tmp_path, *extra):
    argv = [sys.executable, str(_CLI), "render", "--platform", "both",
            "--staging-url", "https://staging.example.com", "--authorized-by", "Jane Doe",
            "--repo", str(tmp_path), *extra]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def written(tmp_path):
    return sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())


def test_dry_run_prints_and_writes_nothing(tmp_path):
    p = render(tmp_path)
    assert p.returncode == 0, p.stderr
    assert written(tmp_path) == []
    assert "===== .github/workflows/gizmoduck-code.yml (new) =====" in p.stdout
    assert "name: gizmoduck code scan" in p.stdout
    assert "dry run - nothing written" in p.stdout


def test_apply_writes_lf_files(tmp_path):
    p = render(tmp_path, "--apply")
    assert p.returncode == 0, p.stderr
    assert written(tmp_path) == sorted(GOLDEN_FILES)
    for rel in GOLDEN_FILES:
        assert b"\r" not in (tmp_path / rel).read_bytes()


def test_existing_file_refused_without_force_and_nothing_written(tmp_path):
    (tmp_path / "bitbucket-pipelines.yml").write_text("image: mine\n", encoding="utf-8")
    p = render(tmp_path, "--apply")
    assert p.returncode == 1 and "GIZMODUCK_CI_REFUSED" in p.stderr
    assert (tmp_path / "bitbucket-pipelines.yml").read_text() == "image: mine\n"
    assert not (tmp_path / ".github").exists()


def test_force_overwrites(tmp_path):
    (tmp_path / "bitbucket-pipelines.yml").write_text("image: mine\n", encoding="utf-8")
    assert render(tmp_path, "--apply", "--force").returncode == 0
    assert "gizmoduck" in (tmp_path / "bitbucket-pipelines.yml").read_text()


def test_bitbucket_out_writes_beside_an_existing_file(tmp_path):
    (tmp_path / "bitbucket-pipelines.yml").write_text("image: mine\n", encoding="utf-8")
    p = render(tmp_path, "--apply", "--bitbucket-out", "bitbucket-pipelines.gizmoduck.yml")
    assert p.returncode == 0, p.stderr
    assert (tmp_path / "bitbucket-pipelines.yml").read_text() == "image: mine\n"
    assert (tmp_path / "bitbucket-pipelines.gizmoduck.yml").is_file()


@pytest.mark.parametrize("extra,needle", [
    (["--staging-url", "https://www.example.com", "--production-url", "https://www.example.com"],
     "both staging and production"),
    (["--staging-url", "http://10.0.0.5"], "R6"),
    (["--staging-url", "https://localhost:8443"], "R6"),
    (["--staging-url", "https://staging@evil.test"], "R3"),
    (["--staging-url", "ftp://staging.example.com"], "R1"),
    (["--enable", "hydra"], "--enable accepts only"),
    (["--authorized-by", " "], "--authorized-by is required"),
    (["--default-branch", "main; rm -rf /"], "unsafe name"),
    (["--image", "evil image"], "unsafe image"),
    (["--authorized-by", "${{ secrets.SDP_API_KEY }}"], "GitHub expression"),
    (["--staging-url", "https://staging.example.com/${{github.token}}"], "GitHub expression"),
])
def test_render_refuses(tmp_path, extra, needle):
    p = render(tmp_path, "--apply", *extra)
    assert p.returncode == 2, p.stdout
    assert "GIZMODUCK_CI_REFUSED" in p.stderr and needle in p.stderr, p.stderr
    assert written(tmp_path) == []


def test_ip_staging_allowed_with_ip_allow_list(tmp_path):
    p = render(tmp_path, "--staging-url", "http://10.0.0.5", "--allow-ip-origin", "http://10.0.0.5")
    assert p.returncode == 0, p.stderr


def test_unpinned_ref_warns(tmp_path):
    assert "is not a commit SHA" in render(tmp_path).stderr
    sha = "0123456789abcdef0123456789abcdef01234567"
    assert "is not a commit SHA" not in render(tmp_path, "--gizmoduck-ref", sha).stderr
