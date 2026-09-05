"""Tests for crew_platform: detect the machine, repair `.crew/config.json`.

`.crew/config.json` is committed, so its `platform` block describes whoever ran
`/crew:init` and is wrong for everybody else. This module fixes that - which
makes it the only hook that WRITES config, so most of what is pinned here is
what it must refuse to write.

The detection paths are exercised by faking `platform.system()` and the two
`/proc` files WSL is recognised by, because the alternative is a suite that only
covers the OS it happens to be running on. That is how a cross-platform bug
survives: the one machine that would have caught it is the one nobody tests on.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_platform
import crew_state


BASE = {
    "schema": 2,
    "tier": 0,
    "roles": ["explorer", "qa-reviewer"],
    "tracker": "files",
    "verifyGate": True,
    "qa": {"provider": "auto"},
    "context": {"warnAt": 0.8, "reserveTokens": 100000},
    "emergency": {"standDown": True, "ttlMinutes": 120},
    "notify": {"provider": "none"},
}


def _repo(tmp_path, platform_block=None, **extra):
    cfg = dict(BASE)
    cfg.update(extra)
    if platform_block is not None:
        cfg["platform"] = platform_block
    return crew_fixtures.make_repo(tmp_path, config=cfg, git=False)


def _cfg(root):
    return json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))


def _fake(monkeypatch, system, *, osrelease=None, distro_env=None,
          msystem=None, route=""):
    """Make detect() see a machine this one is not."""
    monkeypatch.setattr(crew_platform.platform, "system", lambda: system)
    monkeypatch.delenv("MSYSTEM", raising=False)
    if msystem:
        monkeypatch.setenv("MSYSTEM", msystem)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)
    if distro_env:
        monkeypatch.setenv("WSL_DISTRO_NAME", distro_env)

    real_open = open

    def fake_open(path, *args, **kwargs):
        name = str(path).replace("\\", "/")
        if name == "/proc/sys/kernel/osrelease":
            if osrelease is None:
                raise OSError("no such file")
            import io  # pylint: disable=import-outside-toplevel
            return io.StringIO(osrelease)
        if name == "/etc/os-release":
            import io  # pylint: disable=import-outside-toplevel
            return io.StringIO("ID=ubuntu\n")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr(crew_platform.shutil, "which",
                        lambda name: "/usr/bin/ip" if name == "ip" else None)

    class _Done:  # pylint: disable=too-few-public-methods
        stdout = route

    monkeypatch.setattr(crew_platform.subprocess, "run",
                        lambda *a, **k: _Done())


# --- Detection ------------------------------------------------------------


def test_detects_native_linux(monkeypatch):
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    facts = crew_platform.detect("/home/me/repo")
    assert facts["os"] == "linux"
    assert facts["wsl"] == "no"
    assert facts["shell"] == "bash"
    assert facts["repoFilesystem"] == "native"


def test_detects_wsl2_with_its_host_ip(monkeypatch):
    # Under WSL2 the Linux VM has its own network namespace, so a service on the
    # Windows host is NOT on localhost. The gateway is the host, and it changes
    # when the host reboots - which is exactly why committing it is useless.
    _fake(monkeypatch, "Linux",
          osrelease="5.15.0-microsoft-standard-WSL2\n",
          distro_env="Ubuntu", route="default via 172.24.16.1 dev eth0\n")
    facts = crew_platform.detect("/home/me/repo")
    assert facts["os"] == "linux"
    assert facts["wsl"] == "yes"
    assert facts["wslVersion"] == "2"
    assert facts["distro"] == "Ubuntu"
    assert facts["windowsHostIp"] == "172.24.16.1"


def test_detects_wsl1_and_does_not_look_for_a_host_ip(monkeypatch):
    # WSL1 shares the host network stack, so localhost works both ways and there
    # is no gateway to record. Claiming one would be worse than leaving it empty.
    _fake(monkeypatch, "Linux", osrelease="4.4.0-19041-Microsoft\n",
          distro_env="Debian", route="default via 10.0.0.1 dev eth0\n")
    facts = crew_platform.detect("/home/me/repo")
    assert facts["wsl"] == "yes"
    assert facts["wslVersion"] == "1"
    assert facts["windowsHostIp"] == ""


def test_detects_a_clone_on_the_windows_filesystem(monkeypatch, tmp_path):
    # /mnt/<drive> is the Windows filesystem through a translation layer: file
    # operations are roughly an order of magnitude slower, which is the single
    # most common reason a suite that takes 90s somewhere takes minutes here.
    _fake(monkeypatch, "Linux", osrelease="5.15.0-microsoft-standard-WSL2\n")
    monkeypatch.setattr(crew_platform.os.path, "realpath",
                        lambda p: "/mnt/c/repos/thing")
    facts = crew_platform.detect(str(tmp_path))
    assert facts["repoFilesystem"] == "windows-mount"


def test_detects_native_windows_as_powershell(monkeypatch):
    _fake(monkeypatch, "Windows")
    facts = crew_platform.detect("C:/repos/thing")
    assert facts["os"] == "windows"
    assert facts["shell"] == "powershell"


def test_detects_git_bash_on_windows_as_bash(monkeypatch):
    # sys.platform cannot tell a Git Bash session from a cmd one; MSYSTEM can,
    # and getting it wrong means crew writes PowerShell commands for a bash
    # session or the reverse.
    _fake(monkeypatch, "Windows", msystem="MINGW64")
    facts = crew_platform.detect("C:/repos/thing")
    assert facts["os"] == "windows-bash"
    assert facts["shell"] == "bash"


def test_detects_macos(monkeypatch):
    _fake(monkeypatch, "Darwin")
    assert crew_platform.detect("/Users/me/repo")["os"] == "macos"


# --- What it repairs -----------------------------------------------------


def test_repairs_a_config_written_on_the_other_os(tmp_path, monkeypatch):
    root = _repo(tmp_path, platform_block={
        "os": "windows", "wsl": "no", "shell": "powershell",
        "windowsHostIp": None})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    facts = crew_platform.detect(str(root))
    cfg, raw = crew_platform.load(str(root))
    changes = crew_platform.diff(cfg, facts)

    assert changes["os"] == ("windows", "linux")
    assert changes["shell"] == ("powershell", "bash")
    assert crew_platform.apply_changes(str(root), cfg, raw, changes) is True

    written = _cfg(root)
    assert written["platform"]["os"] == "linux"
    assert written["platform"]["shell"] == "bash"


def test_creates_the_block_when_an_older_config_has_none(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    assert "platform" not in _cfg(root)
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    facts = crew_platform.detect(str(root))
    cfg, raw = crew_platform.load(str(root))
    crew_platform.apply_changes(str(root), cfg, raw,
                                crew_platform.diff(cfg, facts))
    assert _cfg(root)["platform"]["os"] == "linux"


def test_no_change_means_no_write(tmp_path, monkeypatch):
    """A hook that rewrites a committed file on every session start would show
    up as a dirty tree in every repo, forever."""
    root = _repo(tmp_path, platform_block={
        "os": "linux", "wsl": "no", "wslVersion": "", "distro": "",
        "shell": "bash", "repoFilesystem": "native", "windowsHostIp": ""})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, raw = crew_platform.load(str(root))
    facts = crew_platform.detect(str(root))
    assert not crew_platform.diff(cfg, facts)
    before = (root / ".crew" / "config.json").read_bytes()
    assert crew_platform.apply_changes(str(root), cfg, raw, {}) is False
    assert (root / ".crew" / "config.json").read_bytes() == before


def test_null_and_empty_string_are_the_same_absence(tmp_path, monkeypatch):
    # /crew:init writes null; this module writes "". Treating them as different
    # would rewrite the file and report a change on the first run in every repo.
    root = _repo(tmp_path, platform_block={
        "os": "linux", "wsl": "no", "shell": "bash",
        "repoFilesystem": "native", "windowsHostIp": None})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, _ = crew_platform.load(str(root))
    assert "windowsHostIp" not in crew_platform.diff(
        cfg, crew_platform.detect(str(root)))


# --- What it must NOT touch ---------------------------------------------


def test_preferences_survive_a_repair(tmp_path, monkeypatch):
    """The whole safety argument. Anything a human chose stays chosen."""
    root = _repo(tmp_path, platform_block={"os": "windows", "shell": "powershell"},
                 tracker="jira", verifyGate=False)
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, raw = crew_platform.load(str(root))
    facts = crew_platform.detect(str(root))
    crew_platform.apply_changes(str(root), cfg, raw,
                                crew_platform.diff(cfg, facts))

    after = _cfg(root)
    assert after["tracker"] == "jira"
    assert after["verifyGate"] is False
    assert after["tier"] == 0
    assert after["roles"] == ["explorer", "qa-reviewer"]
    assert after["qa"] == {"provider": "auto"}
    assert after["context"] == {"warnAt": 0.8, "reserveTokens": 100000}
    assert after["emergency"] == {"standDown": True, "ttlMinutes": 120}
    assert after["notify"] == {"provider": "none"}
    assert after["schema"] == 2


def test_only_derived_keys_are_writable():
    """A guard on the list itself. Every name here is an answer to "what machine
    is this", which a human cannot usefully hand-edit; adding a preference to it
    would turn this module into something that overrules people."""
    assert set(crew_platform.DERIVED_KEYS) == {
        "os", "wsl", "wslVersion", "distro", "shell", "repoFilesystem",
        "windowsHostIp"}


def test_an_unparseable_config_is_left_alone_by_load(tmp_path):
    """`load()` itself is pure -- it only ever reports, never writes. Whether
    a config this broken gets RECREATED is `heal_config`'s decision, covered
    in the "Recreating a missing or broken config" section below; `load()`
    on its own must not guess at what the human was in the middle of."""
    root = crew_fixtures.make_repo(tmp_path, config=BASE, git=False)
    path = root / ".crew" / "config.json"
    path.write_text("{ not json, half-edited", encoding="utf-8")
    cfg, _ = crew_platform.load(str(root))
    assert cfg == {}
    assert path.read_text(encoding="utf-8") == "{ not json, half-edited"


def test_a_read_only_config_is_reported_not_crashed(tmp_path, monkeypatch):
    root = _repo(tmp_path, platform_block={"os": "windows"})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, raw = crew_platform.load(str(root))
    changes = crew_platform.diff(cfg, crew_platform.detect(str(root)))

    def boom(*_a, **_k):
        raise OSError("read-only file system")

    monkeypatch.setattr("builtins.open", boom)
    assert crew_platform.apply_changes(str(root), cfg, raw, changes) is False


def test_line_endings_are_preserved(tmp_path, monkeypatch):
    # A committed config is normally LF. Rewriting it as CRLF on Windows shows
    # up as a whole-file diff on everybody else's machine.
    root = _repo(tmp_path, platform_block={"os": "windows"})
    path = root / ".crew" / "config.json"
    # Re-dump indented first: crew_fixtures writes single-line JSON, so there
    # would be no newline to convert and the test would pass vacuously.
    body = json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2)
    path.write_bytes((body + "\n").replace("\n", "\r\n").encode("utf-8"))
    assert path.read_bytes().count(b"\r\n") > 1, "fixture must really be CRLF"
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, raw = crew_platform.load(str(root))
    crew_platform.apply_changes(str(root), cfg, raw,
                                crew_platform.diff(cfg, crew_platform.detect(str(root))))
    body = path.read_bytes()
    assert body.count(b"\r\n") > 0
    assert body.count(b"\n") == body.count(b"\r\n"), "no bare LF may be mixed in"


# --- Concerns: reported, never changed -----------------------------------


def test_an_autoclear_method_that_cannot_work_here_is_reported(tmp_path,
                                                               monkeypatch):
    root = _repo(tmp_path, context={
        "warnAt": 0.8,
        "autoClear": {"enabled": True, "method": "windows"}})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, raw = crew_platform.load(str(root))
    facts = crew_platform.detect(str(root))
    found = crew_platform.concerns(cfg, facts)
    assert any("does not exist on linux" in c for c in found)
    assert any("'auto'" in c for c in found), "say what to do about it"

    # Reported, NOT rewritten: it is a preference, and this module does not
    # overrule people even when it is confident.
    crew_platform.apply_changes(str(root), cfg, raw,
                                crew_platform.diff(cfg, facts))
    assert _cfg(root)["context"]["autoClear"]["method"] == "windows"


def test_a_disabled_autoclear_is_not_nagged_about(tmp_path, monkeypatch):
    root = _repo(tmp_path, context={
        "autoClear": {"enabled": False, "method": "windows"}})
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, _ = crew_platform.load(str(root))
    assert not crew_platform.concerns(cfg, crew_platform.detect(str(root)))


def test_auto_is_valid_everywhere(tmp_path, monkeypatch):
    root = _repo(tmp_path, context={
        "autoClear": {"enabled": True, "method": "auto"}})
    cfg, _ = crew_platform.load(str(root))
    for system, release in (("Linux", "6.8.0\n"), ("Darwin", None),
                            ("Windows", None)):
        _fake(monkeypatch, system, osrelease=release)
        assert not crew_platform.concerns(cfg, crew_platform.detect(str(root)))


def test_a_windows_mount_clone_is_reported(tmp_path, monkeypatch):
    root = _repo(tmp_path, platform_block={"os": "linux"})
    _fake(monkeypatch, "Linux", osrelease="5.15.0-microsoft-standard-WSL2\n")
    monkeypatch.setattr(crew_platform.os.path, "realpath",
                        lambda p: "/mnt/c/repos/thing")
    cfg, _ = crew_platform.load(str(root))
    found = crew_platform.concerns(cfg, crew_platform.detect(str(root)))
    assert any("/mnt/" in c for c in found)


def test_crlf_in_a_committed_shell_script_is_reported_on_bash_platforms(
        tmp_path, monkeypatch):
    # bash reports this as "bad interpreter: /usr/bin/env bash^M", which reads
    # as a missing interpreter rather than a line-ending problem.
    root = _repo(tmp_path)
    verify = root / "_verify"
    verify.mkdir(exist_ok=True)
    (verify / "smoke.sh").write_bytes(b"#!/usr/bin/env bash\r\necho hi\r\n")
    monkeypatch.chdir(root)
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    cfg, _ = crew_platform.load(str(root))
    found = crew_platform.concerns(cfg, crew_platform.detect(str(root)))
    assert any("CRLF" in c for c in found)
    assert any("gitattributes" in c for c in found), "say how to fix it"


def test_crlf_is_not_reported_on_native_windows(tmp_path, monkeypatch):
    # There, CRLF is simply correct and the .ps1 half is what runs.
    root = _repo(tmp_path)
    verify = root / "_verify"
    verify.mkdir(exist_ok=True)
    (verify / "smoke.sh").write_bytes(b"#!/usr/bin/env bash\r\n")
    monkeypatch.chdir(root)
    _fake(monkeypatch, "Windows")
    cfg, _ = crew_platform.load(str(root))
    assert not crew_platform.concerns(cfg, crew_platform.detect(str(root)))


# --- Recreating a missing or broken config --------------------------------


def _no_crew_dir(tmp_path):
    """A directory that is not a crew repo at all -- no `.crew/`."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("just a repo\n", encoding="utf-8")
    return root


def test_heal_config_does_nothing_without_a_crew_dir(tmp_path):
    """CRITICAL GUARD. A plain repo must not be colonized just because a
    session happened to open in it."""
    root = _no_crew_dir(tmp_path)
    cfg, message = crew_platform.heal_config(str(root))
    assert cfg is None
    assert message is None
    assert not (root / ".crew").exists()


def test_heal_config_recreates_a_missing_config(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert not (root / ".crew" / "config.json").exists()

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "missing" in message
    assert "/crew:init" in message
    written = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert written == crew_config.default_config()
    assert not (root / ".crew" / "config.json.broken").exists()


def test_heal_config_treats_an_empty_file_like_a_missing_one(tmp_path):
    """Nothing to preserve in a zero-byte file -- no backup is worth taking."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    path.write_text("   \n", encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "missing" in message
    assert not (root / ".crew" / "config.json.broken").exists()


def test_heal_config_recreates_an_empty_object(tmp_path):
    """QA finding 4, Critical: `{}` parses, so the healthy branch adopted it
    and left crew permanently switched off.

    `crew_state.collect` derives `isCrew` from the truthiness of the parsed
    config, so an empty object reads as "not a crew repo" -- every hook
    stands down, the PM brief and pulse skip, and nothing ever says why. The
    second face is worse: `schema` is read as SCHEMA_CURRENT when the config
    is falsy, so `/crew:upgrade` reports "already current" forever and the
    repo can never migrate out of it.

    An empty object carries no hand-edits, which is the entire reason the
    healthy branch exists -- so it belongs with the zero-byte file, not with
    the config someone is in the middle of writing. No backup: there is
    nothing in it to lose.
    """
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    path.write_text("{}", encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "empty" in message
    assert not (root / ".crew" / "config.json.broken").exists()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == crew_config.default_config()


def test_heal_config_recreates_an_object_that_is_only_whitespace_keys(tmp_path):
    """The near-miss control: a dict with ANY key is a real config and is
    left alone, however little it says. Only the wholly empty one is healed,
    so this cannot grow into "heal anything that looks incomplete"."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    path.write_text('{"tracker": "files"}', encoding="utf-8")
    before = path.read_bytes()

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg is None
    assert message is None
    assert path.read_bytes() == before


def test_heal_config_backs_up_a_malformed_config_before_recreating(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    broken_text = "{ not json, half-edited"
    path.write_text(broken_text, encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "malformed" in message
    assert "config.json.broken" in message
    backup = root / ".crew" / "config.json.broken"
    assert backup.read_text(encoding="utf-8") == broken_text
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == crew_config.default_config()


def test_heal_config_backs_up_valid_json_that_is_not_an_object(tmp_path):
    """`[]` and `"oops"` both parse, and neither is a usable config -- the
    same rule crew_state.load_config applies for the read side."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "malformed" in message
    assert (root / ".crew" / "config.json.broken").read_text(
        encoding="utf-8") == "[1, 2, 3]"


def test_heal_config_leaves_a_healthy_config_untouched_byte_for_byte(tmp_path):
    """A parseable dict is not this function's business, however unusual --
    it repairs a config that IS NOT ONE, not one it merely disagrees with."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    odd_but_valid = '{"tracker":"jira","roles":["explorer"]}'
    path.write_bytes(odd_but_valid.encode("utf-8"))
    before = path.read_bytes()

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg is None
    assert message is None
    assert path.read_bytes() == before
    assert not (root / ".crew" / "config.json.broken").exists()


def test_a_previous_broken_backup_is_not_overwritten(tmp_path):
    """Two bad sessions in a row must not clobber the first bad file with the
    second -- the first is still the human's best chance at recovery."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    backup = root / ".crew" / "config.json.broken"
    backup.write_text("first broken attempt", encoding="utf-8")
    path.write_text("{ second broken attempt", encoding="utf-8")

    crew_platform.heal_config(str(root))

    assert backup.read_text(encoding="utf-8") == "first broken attempt"


# --- Recreating a missing or broken config, end to end via main() ---------


def _payload(root, session="s1", source="startup"):
    return json.dumps({"cwd": str(root), "session_id": session,
                       "source": source})


def test_main_recreates_a_missing_config_and_reports_it(
        tmp_path, monkeypatch, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr("sys.stdin", _Stdin(_payload(root)))

    assert crew_platform.main() == 0

    out = capsys.readouterr().out
    assert "missing" in out
    assert "/crew:init" in out
    written = _cfg(root)
    # platform-sync runs in the same pass, so platform is no longer all-null
    # by the time the file is read back -- everything else must still match
    # the defaults heal_config wrote.
    default = crew_config.default_config()
    for key, value in default.items():
        if key == "platform":
            continue
        assert written[key] == value, key


def test_main_does_not_create_crew_in_a_plain_repo(tmp_path, monkeypatch, capsys):
    root = _no_crew_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr("sys.stdin", _Stdin(_payload(root)))

    assert crew_platform.main() == 0

    assert not (root / ".crew").exists()
    assert capsys.readouterr().out == ""


def test_main_backs_up_and_recreates_a_malformed_config(
        tmp_path, monkeypatch, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    (root / ".crew" / "config.json").write_text(
        "{ not json, half-edited", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr("sys.stdin", _Stdin(_payload(root)))

    assert crew_platform.main() == 0

    out = capsys.readouterr().out
    assert "malformed" in out
    assert (root / ".crew" / "config.json.broken").read_text(
        encoding="utf-8") == "{ not json, half-edited"
    written = _cfg(root)
    assert written["tracker"] == "files"
    # heal_config writes default_config(), so the recreated file is born
    # current -- SCHEMA_CURRENT, not a literal that goes stale on a bump.
    assert written["schema"] == crew_state.SCHEMA_CURRENT


# --- The brief line ------------------------------------------------------


def test_the_report_leads_with_the_os_change(monkeypatch):
    _fake(monkeypatch, "Linux", osrelease="5.15.0-microsoft-standard-WSL2\n")
    facts = crew_platform.detect("/home/me/repo")
    lines = crew_platform.report({"os": ("windows", "linux")}, [], facts)
    assert lines[0].startswith("## platform - config said windows, this is linux (WSL2)")


def test_nothing_to_say_says_nothing(monkeypatch):
    _fake(monkeypatch, "Linux", osrelease="6.8.0-generic\n")
    assert not crew_platform.report({}, [], crew_platform.detect("/x"))


@pytest.mark.parametrize("payload", [
    "", "not json", "[]", "null", '{"cwd": null}',
])
def test_main_survives_any_payload(payload, monkeypatch, tmp_path, capsys):
    """It runs on SessionStart, where an exception breaks every session opened
    in the repository."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _Stdin(payload))
    assert crew_platform.main() == 0
    capsys.readouterr()


class _Stdin:  # pylint: disable=too-few-public-methods
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


def test_a_second_corruption_gets_its_own_backup(tmp_path):
    """Codex finding 5, Medium.

    Refusing to overwrite the first `.broken` was right; skipping the backup
    and rewriting anyway was not. The sequence that loses work: an old
    incident leaves `config.json.broken`, the human repairs `config.json` and
    edits it for weeks, a second corruption truncates it -- and heal_config
    sees the backup path taken, writes defaults over the current file, and
    reports that it backed it up. Both halves are wrong: the weeks of edits
    are gone and the message says they were saved.
    """
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    (root / ".crew" / "config.json.broken").write_text(
        "first incident", encoding="utf-8")
    path.write_text('{"tracker": "jira", half-edited', encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert (root / ".crew" / "config.json.broken").read_text(
        encoding="utf-8") == "first incident", "the first backup is kept"
    second = root / ".crew" / "config.json.broken.2"
    assert second.read_text(encoding="utf-8") == \
        '{"tracker": "jira", half-edited'
    assert "config.json.broken.2" in message


def test_heal_config_refuses_rather_than_destroy_an_unbackupable_config(
        tmp_path):
    """With every backup slot taken, the only honest move left is to stop.
    Writing defaults over the original would destroy the one copy of it that
    exists in exchange for a config the user did not ask for."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    path = root / ".crew" / "config.json"
    path.write_text("{ the only copy", encoding="utf-8")
    (root / ".crew" / "config.json.broken").write_text("a", encoding="utf-8")
    for n in range(2, crew_platform.CONFIG_BROKEN_MAX + 1):
        (root / ".crew" / f"config.json.broken.{n}").write_text(
            "a", encoding="utf-8")

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg is None
    assert "could NOT be backed up" in message
    assert path.read_text(encoding="utf-8") == "{ the only copy"
