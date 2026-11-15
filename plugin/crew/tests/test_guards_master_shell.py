"""The owner's files through a shell, as a differential corpus (crew 1.3.115, round 8).

Six rounds of review each found one more simple spelling the shell check missed, so this file does not list the
spellings a reviewer last named: it crosses EVERY spelling of each owner target with EVERY write verb in each of
bash, PowerShell and cmd, and asserts each cell (a refusal for the owner's file, silence for another file).
Everything runs in a throwaway home (`HOME` and `USERPROFILE` redirected); no real config is read or written.

On Windows a second test proves the spellings are real, not guessed: each one is opened against the throwaway
home and must be the very file (`os.path.samefile`), so a spelling the corpus calls an alias but Win32 does not
is caught as wrong the other way.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "scripts"))

import scope_guard  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    store = home / ".claude" / "crew" / "confirm-config"
    store.mkdir(parents=True)
    (home / ".claude" / "crew" / "config.json").write_text("{}")
    (store / "cc-ab12.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


# --- the spellings ---------------------------------------------------------------------------------------------

# one path, spelled every way a shell hands it over; `{h}` is the home prefix (`~`, `$HOME`, ...)
FILE_SPELLINGS = (
    "{h}/.claude/crew/config.json",
    "{h}/.claude//crew///config.json",
    "{h}/.claude/./crew/config.json",
    "{h}/x/../.claude/crew/config.json",
    "{h}/.claude/crew/CONFIG.JSON",
    "{h}/.claude/crew/conf*",
    "{h}/.claude/crew/config.js?n",
    "{h}/.claude/crew/config.[j]son",
    "{h}/.claude/crew/config.[!x]son",
    "{h}/.claude/crew/config.[^x]son",
    "{h}/.claude/cr*/config.json",
    "{h}/.claude/crew/*",
    "{h}/.claude/**/config.json",
    "{h}/.claude/crew../config.json",   # not an alias on this Windows (probed), refused anyway: stricter is safe
    "{h}/.claude/crew/config.{json,bak}",
    "{h}/.claude/crew/{config.json,x}",
    "{h}/.claude/crew/config.{a..k}son",
    "{h}/.cl*/cr*/co*",
)
# Win32 resolves these to the same file (trailing dots and spaces per component, NTFS streams, mixed slashes)
WIN32_FILE_SPELLINGS = (
    "{h}/.claude/crew./config.json",
    "{h}/.claude./crew/config.json",
    "{h}/.claude/crew/config.json.",
    "{h}/.claude/crew/config.json..",
    "{h}/.claude/crew/config.json::$DATA",
    "{h}/.claude/crew::$INDEX_ALLOCATION/config.json",
    "{h}\\.claude\\crew\\config.json",
    "{h}\\.claude\\crew.\\config.json",
    "{h}/.claude\\crew./config.json",
)
STORE_DIRS = (
    "{h}/.claude/crew/confirm-config",
    "{h}/.claude/crew/confirm-config/",
    "{h}/.claude/crew./confirm-config",
    "{h}/.claude/crew/confirm-config.",
    "{h}/.claude/crew/confirm*",
    "{h}/.claude/crew/conf?rm-config",
)
RECEIPTS = (
    "{h}/.claude/crew/confirm-config/cc-ab12.json",
    "{h}/.claude/crew/confirm-config/cc-ab.json",
    "{h}/.claude/crew/confirm-config/cc-00000000.json",
    "{h}/.claude/crew/confirm-config//cc-ab.json",
    "{h}/.claude/crew/confirm-config/CC-AB.JSON",
    "{h}/.claude/crew/confirm-config/cc-ab.json.",
    "{h}/.claude/crew/confirm-config/cc-ab.json::$DATA",
    "{h}/.claude/crew./confirm-config/cc-ab.json",
    "{h}/.claude/crew/confirm-config./cc-ab.json",
    "{h}\\.claude\\crew\\confirm-config\\cc-ab.json",
    "{h}\\.claude\\crew.\\confirm-config\\cc-ab.json",
    # every glob that can match a receipt name `cc-<hex>.json`
    "{h}/.claude/crew/confirm-config/cc-*",
    "{h}/.claude/crew/confirm-config/cc-*.json",
    "{h}/.claude/crew/confirm-config/cc-1*",
    "{h}/.claude/crew/confirm-config/cc-1*.json",
    "{h}/.claude/crew/confirm-config/cc-?*",
    "{h}/.claude/crew/confirm-config/cc-?*.json",
    "{h}/.claude/crew/confirm-config/cc-[0-9]*",
    "{h}/.claude/crew/confirm-config/cc-[0-9]*.json",
    "{h}/.claude/crew/confirm-config/cc-[a-f]*",
    "{h}/.claude/crew/confirm-config/cc-[!g-z]*",
    "{h}/.claude/crew/confirm-config/cc-[^g-z]*",
    "{h}/.claude/crew/confirm-config/cc-a?12.json",
    "{h}/.claude/crew/confirm-config/cc-ab1?.json",
    "{h}/.claude/crew/confirm-config/cc-{1,2}*",
    "{h}/.claude/crew/confirm-config/cc-{0..9}*.json",
    "{h}/.claude/crew/confirm-config/c*",
    "{h}/.claude/crew/confirm-config/*",
    "{h}/.claude/crew/confirm-config/*.json",
    "{h}/.claude/crew/*/cc-1*.json",
    "{h}/.claude/crew/*/*",
    "{h}/.claude/**/cc-*.json",
    "{h}/.claude/crew/**/cc-*.json",
    "{h}/.cl*/*/*/cc-*",
)
# 8.3 short names, only meaningful on a file system that makes them; read as the stem followed by anything
SHORT_NAMES = (
    "{h}/CLAUDE~1/CREW~1/CONFIG~1.JSO",
    "{h}/.claude/CREW~1/CONFIG~1.JSO",
    "{h}/.claude/crew/CONFIR~1/CC-AB~1.JSO",
)
HOMES = ("~", "$HOME", "${HOME}")
HOMES_CMD = ("%USERPROFILE%", "$env:USERPROFILE")

# --- the verbs, per shell. `{t}` is the target; a verb is a write (or a delete or a move) to it ----------------

BASH_VERBS = (
    "echo x > {t}", "echo x >> {t}", "echo x >| {t}", ": > {t}", "> {t}", "printf x | tee {t}",
    "printf x | tee -a {t}", "cat a > {t}", "cat a b >> {t}", "echo x 2> {t}", "echo x &> {t}",
    "rm {t}", "rm -f {t}", "rm -rf {t}", "rm -- {t}", "mv x {t}", "mv -f x {t}", "cp x {t}", "cp -f x {t}",
    "ln -sf x {t}", "install x {t}", "sed -i s/a/b/ {t}", "sed -i.bak s/a/b/ {t}", "perl -pi -e s/a/b/ {t}",
    "dd if=x of={t}", "truncate -s 0 {t}", "cp {t} {t}.bak && rm {t}", "true && echo x > {t}",
    "echo x | sponge {t}",
)
PS_VERBS = (
    "Set-Content {t} x", "Set-Content -Path {t} -Value x", "Set-Content -LiteralPath {t} -Value x",
    "Set-Content -Value x -Path {t}", "Add-Content {t} x", "Add-Content -Path {t} -Value x", "Out-File {t}",
    "Out-File -FilePath {t}", "Clear-Content {t}", "Remove-Item {t}", "Remove-Item -Force {t}",
    "Remove-Item -Path {t} -Force", "Remove-Item -LiteralPath {t}", "ri {t}", "rm {t}", "del {t}",
    "Copy-Item x {t}", "Copy-Item x -Destination {t}", "Move-Item x {t}", "Move-Item -Path x -Destination {t}",
    "New-Item {t}", "New-Item -Path {t} -Force", "'x' | Set-Content {t}", "'x' | Out-File {t}",
    "Get-Date | Set-Content {t}", "echo x > {t}", "echo x >> {t}", "$x = 1; Set-Content {t} $x",
    "sc {t} x", "ac {t} x",
)
CMD_VERBS = (
    "copy x {t}", "copy /y x {t}", "move x {t}", "move /y x {t}", "del {t}", "del /f /q {t}", "erase {t}",
    "ren {t} c.bak", "type x > {t}", "echo x > {t}", "echo x >> {t}", "xcopy x {t} /y", "cmd /c copy /y x {t}",
    "cmd /c \"echo x > {t}\"",
)

# the same verbs against another file: silence. `~/.claude/crew/other.json` is the owner's folder, not its files
ELSEWHERE = (
    "C:/other/.claude/crew/config.json",
    "C:/other/.claude/crew/confirm-config/cc-ab.json",
    "C:/other/.claude/crew/confirm-config/cc-*.json",
    "C:\\other\\.claude\\crew\\config.json",
    "/home/other/.claude/crew/config.json",
    "/tmp/x/.claude/crew/config.json",
    "/tmp/x/.claude/crew/confirm-config/cc-ab.json",
    "//server/share/.claude/crew/config.json",
    "{h}/repo/.claude/crew/config.json",
    "{h}/repo/.claude/crew/confirm-config/cc-1*.json",
    "{h}/.claude/settings.json",
    "{h}/.claude/crew/other.json",
    "{h}/.claude/crew/confirm-config.md",
    "{h}/.claude/crewx/config.json",
    "{h}/.claude/crew/config.json.bak",
    "{h}/.claude/crew/configs.json",
    "{h}/notes/config.json",
    "./config.json",
    "out.txt",
    "/tmp/out.txt",
    "$null",
)
# a verb that reads, or only reports: the owner's file is not written
READS = (
    "cat {t}", "cat {t} | grep x", "grep x {t}", "ls -l {t}", "head -n 1 {t}", "wc -l {t}", "diff {t} x",
    "cp {t} /tmp/out", "cp {t} out.txt", "cp -f {t} ./copy.json",
    "Get-Content {t}", "Copy-Item {t} out.txt", "Copy-Item -Path {t} -Destination out.txt", "Get-Item {t}",
    "Test-Path {t}", "Select-String x {t}", "type {t}", "copy {t} out.txt", "echo {t} > out.txt",
    "echo {t} | tee out.txt", "python3 x.py {t}", "sed s/a/b/ {t}", "sed -n p {t} > out.txt",
    "patch --dry-run {t} < /tmp/e.patch", "patch --check {t} < /tmp/e.patch", "patch -C {t} < /tmp/e.patch",
    "patch -p1 --dry-run -i /tmp/e.patch {t}", "Set-Content out.txt (Get-Content {t})",
    "Set-Content out.txt -Value {t}", "echo x > out.txt # {t}",
)


def _expand_spellings(spellings, prefixes):
    return [s.replace("{h}", prefix) for s in spellings for prefix in prefixes]


def _cells(spellings, verbs, prefixes):
    return [(verb.replace("{t}", target), target) for target in _expand_spellings(spellings, prefixes)
            for verb in verbs]


def _unrefused(cells):
    return [f"{command}" for command, _ in cells if scope_guard._owner_command_refusal(command) is None]  # pylint: disable=protected-access


def _refused(cells):
    return [f"{command}" for command, _ in cells if scope_guard._owner_command_refusal(command)]  # pylint: disable=protected-access


# bash uses `~` and `$HOME`; PowerShell and cmd also reach home as `$env:USERPROFILE` and `%USERPROFILE%`
BASH_HOMES = HOMES
PS_HOMES = HOMES + ("$env:USERPROFILE",)
CMD_HOMES = ("~", "%USERPROFILE%")


@pytest.mark.parametrize("name, spellings", [("file", FILE_SPELLINGS), ("win32 file", WIN32_FILE_SPELLINGS),
                                             ("store dir", STORE_DIRS), ("receipt", RECEIPTS),
                                             ("short name", SHORT_NAMES)])
def test_every_spelling_of_the_owners_files_is_refused_by_every_write_verb(name, spellings, home):
    """The matrix: every spelling x every verb x bash, PowerShell and cmd. A cell that slips through is listed
    whole, so the next missed spelling is one line in the failure, not another review round."""
    verbs_for_dir = {"store dir": lambda v: not v.startswith(("sed", "perl", "truncate", "dd ", ": >", "> ", "echo",
                                                              "printf", "cat", "Set-Content", "Add-Content",
                                                              "Out-File", "Clear-Content", "'x'", "Get-Date",
                                                              "$x", "sc ", "ac ", "type x", "install"))}
    slipped = []
    for shell_verbs, homes in ((BASH_VERBS, BASH_HOMES), (PS_VERBS, PS_HOMES), (CMD_VERBS, CMD_HOMES)):
        verbs = [v for v in shell_verbs if verbs_for_dir.get(name, lambda _v: True)(v)]
        slipped += _unrefused(_cells(spellings, verbs, homes))
    assert not slipped, f"{len(slipped)} {name} cells were not refused:\n" + "\n".join(slipped[:60])


def test_another_file_is_not_the_owners_whatever_the_verb(home):
    verbs = BASH_VERBS + PS_VERBS + CMD_VERBS
    hit = _refused(_cells(ELSEWHERE, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a file that is not the owner's:\n" + "\n".join(hit[:60])


def test_reading_the_owners_files_is_not_writing_them(home):
    hit = _refused(_cells(FILE_SPELLINGS + STORE_DIRS + RECEIPTS, READS, ("~",)))
    assert not hit, f"{len(hit)} read cells were refused:\n" + "\n".join(hit[:60])


# --- the named findings of round 8 --------------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "rm ~/.claude/crew/confirm-config/cc-1*.json",
    "rm ~/.claude/crew/confirm-config/cc-?*",
    "rm ~/.claude/crew/confirm-config/cc-[0-9]*",
    "rm -f ~/.claude/crew/confirm-config/cc-*.json",
    "mv x ~/.claude/crew/confirm-config",
    "cp x ~/.claude/crew/confirm-config",
    "Remove-Item ~/.claude/crew/confirm-config/cc-1*.json",
    "Set-Content ~/.claude/crew/confirm-config/cc-1* x",
    "del ~\\.claude\\crew\\confirm-config\\cc-1*.json",
    "rm ~/.claude/crew/confirm-config/{cc-1,cc-2}*",
])
def test_a_glob_that_can_match_a_receipt_is_refused(command, home):
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "echo x > ~\\.claude\\crew.\\config.json",
    "Set-Content ~\\.claude\\crew.\\config.json x",
    "echo x > ~/.claude/crew./confirm-config/cc-ab.json",
    "Set-Content ~\\.claude\\crew.\\confirm-config\\cc-ab.json x",
    "echo x > ~/.claude/crew/config.json.",
    "echo x > ~/.claude/crew/config.json::$DATA",
    "echo x > ~/.claude/crew::$INDEX_ALLOCATION/config.json",
])
def test_a_win32_spelling_of_the_owners_file_is_refused(command, home):
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "echo x > C:/other/.claude/crew/config.json",
    "echo x > /home/other/.claude/crew/config.json",
    "rm /tmp/x/.claude/crew/confirm-config/cc-1*.json",
    "echo x > //server/share/.claude/crew/config.json",
])
def test_a_file_outside_the_owners_home_is_not_the_owners(command, home):
    assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "patch --dry-run ~/.claude/crew/config.json < /tmp/e.patch",
    "patch --check ~/.claude/crew/config.json < /tmp/e.patch",
    "patch -C ~/.claude/crew/config.json < /tmp/e.patch",
])
def test_a_patch_dry_run_writes_nothing(command, home):
    assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "patch ~/.claude/crew/config.json < /tmp/e.patch",
    "patch -p1 ~/.claude/crew/config.json < /tmp/e.patch",
    "patch --dry-run x < /tmp/e.patch && patch ~/.claude/crew/config.json < /tmp/e.patch",
])
def test_a_real_patch_is_still_refused(command, home):
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_a_path_the_shell_cannot_resolve_is_still_judged_by_its_tail(home):
    """`$X` is unknown, so the folder cannot be told: the way the word ENDS decides, component by component."""
    for command in ("echo x > $X/crew/config.json", "echo x > $X/.claude/crew/confirm-config/cc-ab.json",
                    "echo x > $X/crew./config.json", "rm $X/confirm-config/cc-1*", "rm $X/.claude/cr*/config.json"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("echo x > $X/config.json", "echo x > $X/crewx/config.json", "echo x > $X/other/config.json"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_the_drive_spellings_of_the_owners_home_are_refused(home):
    """`/c/Users/...` (Git Bash), `/mnt/c/...` (WSL), `//?/C:/...` and the admin share all name the same file."""
    drive = os.path.splitdrive(str(home))[0]
    if not drive:
        pytest.skip("the drive spellings need a Windows home")
    letter = drive[0].lower()
    rest = str(home)[len(drive):].replace("\\", "/")
    for spelled in (f"{drive}{rest}", f"/{letter}{rest}", f"/mnt/{letter}{rest}", f"/cygdrive/{letter}{rest}",
                    f"//?/{drive}{rest}", f"//localhost/{letter}${rest}",
                    f"\\\\?\\{drive}{rest.replace('/', chr(92))}"):
        command = f"echo x > {spelled}/.claude/crew/config.json"
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


@pytest.mark.skipif(os.name != "nt", reason="the trailing-dot, stream and short-name aliases are Win32's")
def test_every_win32_spelling_in_the_corpus_is_the_real_file(home):
    """The corpus is only worth its name if the aliases are real: open each against the throwaway home."""
    real = home / ".claude" / "crew" / "config.json"
    for spelling in WIN32_FILE_SPELLINGS:
        path = spelling.replace("{h}", str(home)).replace("::$DATA", "").replace("::$INDEX_ALLOCATION", "")
        assert os.path.samefile(path, real), path


def test_the_resolved_path_of_a_link_is_the_owners_file(home, tmp_path):
    """A link in a folder the owner does not own that points at the machine config is that file."""
    link = tmp_path / "elsewhere" / "link.json"
    link.parent.mkdir()
    try:
        os.symlink(home / ".claude" / "crew" / "config.json", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need a privilege this host does not give")
    assert scope_guard._owner_command_refusal(f"echo x > {link}"), link  # pylint: disable=protected-access


def test_a_junctioned_home_is_still_the_owners_home(tmp_path, monkeypatch):
    """HOME is a link to the real folder: the real folder's own spelling of the config is the same file."""
    real = tmp_path / "real"
    (real / ".claude" / "crew").mkdir(parents=True)
    link = tmp_path / "link"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need a privilege this host does not give")
    monkeypatch.setenv("HOME", str(link))
    monkeypatch.setenv("USERPROFILE", str(link))
    command = f"echo x > {real.as_posix()}/.claude/crew/config.json"
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "echo x > ~\\.claude\\crew.\\config.json",
    "Set-Content ~\\.claude\\crew.\\config.json x",
    "echo x > ~/.claude/crew./confirm-config/cc-new.json",
    "echo x > ~/.claude/crew::$INDEX_ALLOCATION/config.json",
    "echo x > ~/.claude/crew/confirm-config./cc-new.json",
    "echo x > ~/.claude./crew/config.json",
])
def test_a_win32_spelling_is_refused_by_name_alone_for_a_file_that_does_not_exist(command, home, monkeypatch):
    """The file system (`realpath`) already resolves an alias of a file that exists; a receipt not yet written, or a
    host that is not Windows, has only the spelling. The resolver is taken away so the name decides."""
    monkeypatch.setattr(os.path, "realpath", lambda path, **_kw: path)
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_the_drive_spellings_are_read_by_name_alone(home, monkeypatch):
    drive = os.path.splitdrive(str(home))[0]
    if not drive:
        pytest.skip("the drive spellings need a Windows home")
    monkeypatch.setattr(os.path, "realpath", lambda path, **_kw: path)
    letter = drive[0].lower()
    rest = str(home)[len(drive):].replace("\\", "/")
    for spelled in (f"/{letter}{rest}", f"/mnt/{letter}{rest}", f"//localhost/{letter}${rest}",
                    f"//127.0.0.1/{letter}${rest}", f"//?/{drive}{rest}"):
        command = f"echo x > {spelled}/.claude/crew/config.json"
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_a_word_that_only_passes_through_the_owners_names_is_not_the_owners(home):
    for command in ("echo x > $X/crew/config.json/sub", "echo x > $X/confirm-config.md",
                    "echo x > $X/.claude/crew/config.json.d/f"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access
