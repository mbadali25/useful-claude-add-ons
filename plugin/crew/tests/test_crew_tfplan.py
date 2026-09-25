"""`crew_tfplan.py summarize`: the sidecar the cloud guard reads a saved
terraform plan through.

A sidecar that says "no deletes" for a plan that deletes something defeats
the destroy stop, so the tests here are about the ways a summary could be
WRONG or written when it should not be: every `delete` action shape counts,
a failed or timed-out `show` writes nothing (and leaves an earlier summary
alone), the file is written atomically, and it is bound to the sha256 of the
exact plan bytes -- a plan edited afterwards has no summary.

Nothing runs real terraform: a shim called `terraform` on PATH prints canned
`show -json` and `workspace show` output from files and variables the test
sets. The shapes it prints were measured on terraform 1.16.3 against a
throwaway `terraform_data` fixture with local state: a removed resource is
`["delete"]`, `-replace` is `["delete","create"]`, `-destroy` is
`["delete"]` for every resource, and a plan with no changes has no
`resource_changes` key at all.
"""
import base64
import hashlib
import io
import json
import os
import zipfile

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position
import crew_tfplan  # noqa: E402  pylint: disable=wrong-import-position

PLAN = "p.tfplan"


def _varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _field(number, payload):
    """One length-delimited protobuf field."""
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def plan_bytes(workspace="staging", backend=True, member="tfplan"):
    """A saved plan as terraform writes it: a zip whose `tfplan` member is
    the protobuf `Plan`, carrying `backend` (field 13) = {type (1), config
    (2), workspace (3)}. Field numbers measured on a real 1.16.3 plan --
    see `REAL_PLAN` below."""
    body = _varint(1 << 3) + _varint(3)
    if backend:
        inner = _field(1, b"local") + _field(2, b"\n\x00")
        if workspace is not None:
            inner += _field(3, workspace.encode("utf-8"))
        body += _field(13, inner)
    body += _field(14, b"1.16.3")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, body)
        archive.writestr("tfconfig/m-/main.tf", "# fixture\n")
    return buffer.getvalue()


DATA = plan_bytes()

# A REAL plan, written by terraform 1.16.3 against a throwaway
# `terraform_data` config with local state, with `.terraform/environment`
# saying `qa` and `TF_WORKSPACE=production` set for the plan -- the
# reviewer's scenario. It is bound to `production`: terraform refused to
# apply it with `qa` selected ("The plan file describes changes to the
# "production" workspace"). sha256 89970fef886c07f2.
REAL_PLAN = base64.b64decode(
    "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"
    "AAAABwAHAOYBAACKBAAAAAA="
)

_SH = """#!/bin/sh
case "$*" in
  *"show -json"*)
    if [ -n "$FAKE_TF_SLEEP" ]; then sleep "$FAKE_TF_SLEEP"; fi
    if [ -n "$FAKE_TF_SHOW_EXIT" ]; then exit "$FAKE_TF_SHOW_EXIT"; fi
    cat "$FAKE_TF_SHOW"
    ;;
  *"workspace show"*)
    if [ -n "$FAKE_TF_WS_EXIT" ]; then exit "$FAKE_TF_WS_EXIT"; fi
    printf '%s\\n' "$FAKE_TF_WS"
    ;;
esac
"""
_CMD = ("@echo off\r\n"
        "echo %* | findstr /C:\"show -json\" >nul\r\n"
        "if not errorlevel 1 (\r\n"
        "  if defined FAKE_TF_SHOW_EXIT exit /b %FAKE_TF_SHOW_EXIT%\r\n"
        "  type \"%FAKE_TF_SHOW%\"\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        "if defined FAKE_TF_WS_EXIT exit /b %FAKE_TF_WS_EXIT%\r\n"
        "echo %FAKE_TF_WS%\r\n")


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A repo with `.crew/`, the plan, and the shim first on PATH."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / PLAN).write_bytes(DATA)
    bindir = tmp_path / "bin"
    crew_fixtures.write_shim(bindir, "terraform", _SH, _CMD)
    monkeypatch.setenv("PATH", crew_fixtures.shell_path("ps1", [bindir]))
    monkeypatch.setenv("FAKE_TF_WS", "staging")
    for name in ("FAKE_TF_SHOW_EXIT", "FAKE_TF_SLEEP", "FAKE_TF_WS_EXIT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(root)
    return root


def _show(tmp_path, monkeypatch, doc):
    path = tmp_path / "show.json"
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc),
                    encoding="utf-8")
    monkeypatch.setenv("FAKE_TF_SHOW", str(path))


def _change(address, actions):
    return {"address": address, "change": {"actions": actions}}


def _sidecar_path(root, data=DATA):
    return root / ".crew" / "tfplan" / (hashlib.sha256(data).hexdigest()
                                        + ".json")


def _summarize(root, *extra):
    return crew_tfplan.main(["summarize", PLAN, "--root", str(root), *extra])


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"],
                                     ["create", "delete"]],
                         ids=["delete", "replace", "create-before-destroy"])
def test_every_delete_shape_is_recorded(repo, tmp_path, monkeypatch, actions):
    _show(tmp_path, monkeypatch, {
        "format_version": "1.2",
        "variables": {"environment": {"value": "staging"}},
        "resource_changes": [_change("aws_instance.a", actions),
                             _change("aws_instance.b", ["no-op"]),
                             _change("aws_instance.c", ["create"])]})
    assert _summarize(repo) == 0
    doc = json.loads(_sidecar_path(repo).read_text(encoding="utf-8"))
    assert doc["deletes"] == ["aws_instance.a"]
    assert doc["workspace"] == "staging"
    assert doc["environment"] == "staging"
    assert doc["plan"] == PLAN and doc["tool"] == "terraform"


def test_forget_alone_is_not_a_delete(repo, tmp_path, monkeypatch):
    """`removed { lifecycle { destroy = false } }` plans a `forget`: the
    object leaves state and is NOT destroyed."""
    _show(tmp_path, monkeypatch, {
        "resource_changes": [_change("aws_instance.a", ["forget"])]})
    assert _summarize(repo) == 0
    doc = json.loads(_sidecar_path(repo).read_text(encoding="utf-8"))
    assert doc["deletes"] == [] and doc["environment"] is None


def test_the_guard_reads_what_summarize_writes(repo, tmp_path, monkeypatch):
    _show(tmp_path, monkeypatch, {"resource_changes": [
        _change("aws_instance.a", ["update"])]})
    assert _summarize(repo) == 0
    ctx = {"cd": False, "switch": False, "engaged": True}
    finding = cloud_guard.scan("bash", f"terraform apply {PLAN}", ctx=ctx)[0]
    got = cloud_guard._tf_destroy(finding.scope, str(repo), str(repo), ctx)  # pylint: disable=protected-access
    assert got[0] == "no", got
    assert got[2]["workspace"] == "staging"


def test_show_failure_writes_nothing(repo, tmp_path, monkeypatch):
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    monkeypatch.setenv("FAKE_TF_SHOW_EXIT", "1")
    assert _summarize(repo) == 2
    assert not (repo / ".crew" / "tfplan").exists() or not os.listdir(
        repo / ".crew" / "tfplan")


def test_an_existing_sidecar_survives_a_failed_run(repo, tmp_path,
                                                   monkeypatch):
    path = _sidecar_path(repo)
    path.parent.mkdir(parents=True)
    before = json.dumps({"plan": PLAN, "workspace": "staging",
                         "environment": None, "deletes": ["aws_instance.a"],
                         "tool": "terraform", "created": 1})
    path.write_text(before, encoding="utf-8")
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    monkeypatch.setenv("FAKE_TF_SHOW_EXIT", "3")
    assert _summarize(repo) == 2
    assert path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("doc", ["[]", "{not json", json.dumps({}),
                                 json.dumps({"resource_changes": {}}),
                                 json.dumps({"resource_changes": [
                                     {"address": "a", "change": {}}]})],
                         ids=["not-object", "not-json",
                              "no-resource-changes", "changes-not-list",
                              "no-actions"])
def test_output_crew_cannot_read_writes_nothing(repo, tmp_path, monkeypatch,
                                                doc):
    """A plan with no changes has no `resource_changes` key at all
    (measured), so such a plan is refused too -- and its apply stays a
    destroy-unknown that asks. Refusing a plan that could not delete is the
    direction to be wrong in."""
    _show(tmp_path, monkeypatch, doc)
    assert _summarize(repo) == 2
    assert not _sidecar_path(repo).exists()


def test_a_timeout_writes_nothing(repo, tmp_path, monkeypatch):
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    monkeypatch.setenv("FAKE_TF_SLEEP", "5")
    monkeypatch.setattr(crew_tfplan, "TIMEOUT", 1)
    assert _summarize(repo) == 2
    assert not _sidecar_path(repo).exists()


def test_refuses_without_crew_dir_and_never_creates_it(tmp_path, monkeypatch,
                                                       repo):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / PLAN).write_bytes(DATA)
    monkeypatch.chdir(bare)
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert crew_tfplan.main(["summarize", PLAN, "--root", str(bare)]) == 2
    assert not (bare / ".crew").exists()
    assert repo.exists()


def test_a_plan_edited_after_summarise_no_longer_matches(repo, tmp_path,
                                                         monkeypatch):
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo) == 0
    (repo / PLAN).write_bytes(DATA + b" edited")
    ctx = {"cd": False, "switch": False, "engaged": True}
    finding = cloud_guard.scan("bash", f"terraform apply {PLAN}", ctx=ctx)[0]
    got = cloud_guard._tf_destroy(finding.scope, str(repo), str(repo), ctx)  # pylint: disable=protected-access
    assert got[0] == "unknown" and "no summary" in got[1]


def test_the_write_is_atomic(repo, tmp_path, monkeypatch):
    """Written to a temp file and `os.replace`d: a failure at the replace
    leaves neither a half-written sidecar nor the temp file."""
    _show(tmp_path, monkeypatch, {"resource_changes": []})

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(crew_tfplan.os, "replace", boom)
    assert _summarize(repo) == 2
    folder = repo / ".crew" / "tfplan"
    assert not folder.exists() or os.listdir(folder) == []


def test_chdir_and_bin_are_passed_through(repo, tmp_path, monkeypatch):
    """`--chdir DIR` hashes DIR/PLAN, as terraform resolves it, and names the
    tool it ran; `--bin` picks tofu."""
    infra = repo / "infra"
    infra.mkdir()
    (infra / PLAN).write_bytes(b"infra plan")
    crew_fixtures.write_shim(tmp_path / "bin", "tofu", _SH, _CMD)
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo, "--chdir", "infra", "--bin", "tofu") == 0
    doc = json.loads(_sidecar_path(repo, b"infra plan").read_text(
        encoding="utf-8"))
    assert doc["tool"] == "tofu"


def test_a_missing_binary_is_refused(repo, tmp_path, monkeypatch):
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo, "--bin", "no-such-terraform-binary") == 2
    assert not _sidecar_path(repo).exists()


# --- the workspace is the plan's own (review round 1, crew_tfplan.py:103) --


def test_a_real_plan_is_read_as_the_workspace_it_is_bound_to():
    assert hashlib.sha256(REAL_PLAN).hexdigest().startswith("89970fef886c07f2")
    assert crew_tfplan.plan_workspace(REAL_PLAN) == "production"


def test_the_workspace_comes_from_the_plan_not_the_selected_one(
        repo, tmp_path, monkeypatch):
    """The reviewer's scenario: a plan made under `TF_WORKSPACE=production`
    in a directory whose selected workspace is staging. `workspace show`
    says staging; the plan is bound to production, and so is its summary."""
    (repo / PLAN).write_bytes(REAL_PLAN)
    monkeypatch.setenv("FAKE_TF_WS", "staging")
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo) == 0
    doc = json.loads(_sidecar_path(repo, REAL_PLAN).read_text(encoding="utf-8"))
    assert doc["workspace"] == "production"


@pytest.mark.parametrize("data", [
    b"not a zip", plan_bytes(backend=False), plan_bytes(workspace=None),
    plan_bytes(member="other"), plan_bytes(workspace=""),
    b"PK\x03\x04truncated"],
    ids=["not-zip", "no-backend", "no-workspace", "no-tfplan-member",
         "empty-workspace", "truncated-zip"])
def test_a_plan_whose_workspace_cannot_be_read_records_null(repo, tmp_path,
                                                            monkeypatch,
                                                            data):
    """Null, never the selected workspace: the hook reads a null workspace
    as unknown, so the apply is refused rather than classified by a
    workspace the plan may not be bound to."""
    (repo / PLAN).write_bytes(data)
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo) == 0
    doc = json.loads(_sidecar_path(repo, data).read_text(encoding="utf-8"))
    assert doc["workspace"] is None


def test_the_hook_refuses_a_summary_with_no_bound_workspace(repo, tmp_path,
                                                            monkeypatch):
    (repo / PLAN).write_bytes(b"not a zip")
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    assert _summarize(repo) == 0
    (repo / ".terraform").mkdir()
    (repo / ".terraform" / "environment").write_text("staging",
                                                    encoding="utf-8")
    ctx = {"cd": False, "switch": False, "engaged": True}
    finding = cloud_guard.scan("bash", f"terraform apply {PLAN}", ctx=ctx)[0]
    destroy, _why, sidecar = cloud_guard._tf_destroy(  # pylint: disable=protected-access
        finding.scope, str(repo), str(repo), ctx)
    assert destroy == "no"
    got = cloud_guard._tf_environment(finding.scope, str(repo), ctx,  # pylint: disable=protected-access
                                      {"nonProd": ["staging"], "problem": ""},
                                      sidecar)
    assert got[0] == "unknown", got


def test_summarize_no_longer_asks_which_workspace_is_selected(
        repo, tmp_path, monkeypatch):
    """`workspace show` answers for the directory, not the plan; the shim
    fails it, and summarize must not care."""
    _show(tmp_path, monkeypatch, {"resource_changes": []})
    monkeypatch.setenv("FAKE_TF_WS_EXIT", "1")
    assert _summarize(repo) == 0
