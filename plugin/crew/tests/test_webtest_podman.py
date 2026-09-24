"""webtest_guard visual: Podman is a container runtime like Docker.

The Windows burn-in host declined Docker Desktop, so its visual baselines run
in the same pinned image under Podman in WSL. Podman leaves
`/run/.containerenv` (not Docker's `/.dockerenv`) and a `libpod` cgroup; either
is container evidence. Off the image the check says how to get there with
whichever runtime is on PATH, and names both when neither is.
"""
import json
import os
import pathlib
import shutil
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import webtest_guard


def _write(root, rel, text):
    path = os.path.join(str(root), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _host(tmp, monkeypatch, dockerenv=False, containerenv=False, cgroup="0::/init.scope\n"):
    docker = os.path.join(str(tmp), "dockerenv")
    podman = os.path.join(str(tmp), "containerenv")
    if dockerenv:
        _write(tmp, "dockerenv", "")
    if containerenv:
        _write(tmp, "containerenv", 'engine="podman-5.4.0"\n')
    _write(tmp, "cgroup", cgroup)
    os.makedirs(os.path.join(str(tmp), "ms-playwright", "chromium-1200"))
    monkeypatch.setattr(webtest_guard, "CONTAINER_MARKERS", (docker, podman))
    monkeypatch.setattr(webtest_guard, "CGROUP_FILE", os.path.join(str(tmp), "cgroup"))
    monkeypatch.setattr(webtest_guard, "BROWSERS_DIR", os.path.join(str(tmp), "ms-playwright"))


def _repo(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "node_modules/@playwright/test/package.json",
           json.dumps({"version": webtest_guard.PINNED_PLAYWRIGHT}))
    _write(repo, "node_modules/playwright-core/browsers.json",
           json.dumps({"browsers": [{"name": "chromium", "revision": "1200"}]}))
    return str(repo)


def _in_image(monkeypatch):
    monkeypatch.setenv(webtest_guard.IMAGE_ENV, webtest_guard.PINNED_IMAGE)
    monkeypatch.setattr(sys, "platform", "linux")


def _on_path(monkeypatch, present):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name in present else None)


def test_the_shipped_markers_cover_both_runtimes():
    """The cases below point the markers at tmp files; this pins the real
    ones, so dropping Podman's from the constant cannot pass unnoticed."""
    shipped = (set(webtest_guard.CONTAINER_MARKERS), {"podman", "libpod"} <= set(webtest_guard.CGROUP_WORDS))

    assert shipped == ({"/.dockerenv", "/run/.containerenv"}, True)


@pytest.mark.parametrize("evidence", [
    {"containerenv": True},
    {"cgroup": "0::/machine.slice/libpod-0123abcd.scope\n"},
    {"dockerenv": True},
])
def test_a_podman_or_docker_container_is_evidence_and_the_suite_runs(tmp_path, monkeypatch, evidence):
    _in_image(monkeypatch)
    host = tmp_path / "host"
    _host(host, monkeypatch, **evidence)
    ran = []

    code, _lines = webtest_guard.check_visual(_repo(tmp_path),
                                              runner=lambda *a, **k: ran.append(a) or 0)

    assert (code, len(ran)) == (0, 1)


def test_the_verified_line_names_the_podman_marker(tmp_path, monkeypatch):
    _in_image(monkeypatch)
    _host(tmp_path / "host", monkeypatch, containerenv=True)

    _code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert "containerenv" in lines[0]


def test_no_marker_from_either_runtime_is_unverified_and_names_both(tmp_path, monkeypatch):
    _in_image(monkeypatch)
    _host(tmp_path / "host", monkeypatch)

    code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert (code, "dockerenv" in lines[0] and "containerenv" in lines[0]) == (77, True)


@pytest.mark.parametrize("present, runtime", [(("podman",), "podman"), (("docker",), "docker"),
                                              (("docker", "podman"), "docker")])
def test_off_the_image_it_shows_the_run_line_for_the_runtime_on_path(monkeypatch, tmp_path,
                                                                     present, runtime):
    monkeypatch.delenv(webtest_guard.IMAGE_ENV, raising=False)
    _on_path(monkeypatch, present)

    code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert (code, f"{runtime} run --rm" in lines[1], webtest_guard.PINNED_IMAGE in lines[1]) \
        == (77, True, True)


@pytest.mark.parametrize("present, runtime", [(("podman",), "podman"), (("docker",), "docker")])
def test_the_run_line_relabels_the_bind_mount_for_selinux(monkeypatch, tmp_path, present, runtime):
    """Codex r1 finding 5: the advertised bind mount (`-v "$PWD":/work`) had
    no SELinux relabel option, so the printed command is unreadable inside
    the container on an SELinux-enforcing host (Fedora/RHEL) -- podman and
    docker both refuse access to a mismatched-label mount. `:Z` is the fix;
    untested on an actual enforcing host (none available here), but `:Z` is
    documented as a no-op where SELinux is absent, so this only asserts the
    printed command carries it."""
    monkeypatch.delenv(webtest_guard.IMAGE_ENV, raising=False)
    _on_path(monkeypatch, present)

    code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert (code, f'{runtime} run --rm --ipc=host -v "$PWD":/work:Z -w /work' in lines[1]) \
        == (77, True)


def test_off_the_image_with_neither_runtime_it_is_unverified_and_names_both(monkeypatch, tmp_path):
    monkeypatch.delenv(webtest_guard.IMAGE_ENV, raising=False)
    _on_path(monkeypatch, ())

    code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert (code, "UNVERIFIED" in lines[0], "neither docker nor podman" in lines[1]) == (77, True, True)


def test_inside_a_container_without_the_browsers_no_run_line_is_offered(tmp_path, monkeypatch):
    """The runtime line is for a host. Inside a container the fix is the
    image, not another `run`."""
    _in_image(monkeypatch)
    _host(tmp_path / "host", monkeypatch, containerenv=True)
    monkeypatch.setattr(webtest_guard, "BROWSERS_DIR", str(tmp_path / "absent"))

    code, lines = webtest_guard.check_visual(_repo(tmp_path), runner=lambda *a, **k: 0)

    assert (code, len(lines)) == (77, 1)


# --- the documented command must not drift from runtime_line()'s own one ------

@pytest.mark.parametrize("rel", ["commands/webtest.md", "skills/stack-web/SKILL.md"])
def test_the_documented_bind_mount_carries_the_selinux_relabel(rel):
    """`runtime_line()` prints `-v "$PWD":/work:Z -w /work` (the SELinux
    relabel above). The two docs that copy this command by hand had drifted
    to the pre-`:Z` form -- this pins both against the product's own flag
    rather than each other, so a future flag change has to touch all three
    or this goes red."""
    text = pathlib.Path(context._ROOT, rel).read_text(encoding="utf-8")  # pylint: disable=protected-access

    assert '-v "$PWD":/work:Z -w /work' in text, (
        rel + " does not carry the SELinux-relabeled bind mount "
        "(-v \"$PWD\":/work:Z -w /work) that webtest_guard.py's "
        "runtime_line() actually prints")
