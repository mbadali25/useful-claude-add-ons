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
import pathlib
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "scripts"))

import scope_guard  # noqa: E402  pylint: disable=wrong-import-position


ELSEWHERE_ROOT = "/tmp"   # the folder this corpus spells for "a file that is not the owner's"
_HOME_ROOTS = ("/var/tmp", "/dev/shm")   # where the throwaway home goes when pytest's own folder is under /tmp


def _below_elsewhere(folder):
    """True when `/tmp` is an ancestor of `folder`, as spelled or as the file system resolves it."""
    spellings = (scope_guard._canon(str(folder), None),  # pylint: disable=protected-access
                 scope_guard._canon(os.path.realpath(str(folder)), None))  # pylint: disable=protected-access
    return any(spelled is None or spelled.startswith(ELSEWHERE_ROOT + "/") for spelled in spellings)


def _home_folder(tmp_path):
    """The (folder, made here) the throwaway home lives in. On Linux pytest's `tmp_path` is under `/tmp`, the
    folder this corpus uses for "elsewhere": with the home there, `echo x > /tmp/$NAME` and `find /tmp -exec sh ...`
    MAY reach the owner's files and the guard is right to refuse them (crew 1.3.151;
    `test_an_unresolvable_target_below_an_ancestor_of_home_is_refused` pins that), so the must-allow rows would be
    asking for a hole. The home then goes to a folder `/tmp` is no ancestor of. No such folder is a failure, not
    a skip and not a silent fall back to the home under `/tmp`."""
    if not _below_elsewhere(tmp_path):
        return tmp_path / "home", None
    for root in _HOME_ROOTS:
        if os.path.isdir(root) and os.access(root, os.W_OK) and not _below_elsewhere(root):
            made = tempfile.mkdtemp(prefix="crew-guards-home-", dir=root)
            return pathlib.Path(made) / "home", made
    return pytest.fail(f"pytest's temporary folder {tmp_path} is under {ELSEWHERE_ROOT} and none of {_HOME_ROOTS} "
                       "is a writable folder outside it: run with --basetemp=<a folder outside /tmp>")


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    home, made = _home_folder(tmp_path)
    store = home / ".claude" / "crew" / "confirm-config"
    store.mkdir(parents=True)
    (home / ".claude" / "crew" / "config.json").write_text("{}")
    (store / "cc-ab12.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    yield home
    if made:
        shutil.rmtree(made, ignore_errors=True)


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
                    "echo x > $X/crew./config.json", "rm $X/confirm-config/cc-1*", "rm $X/.claude/cr*/config.json",
                    "echo x > crew./config.json", "rm .claude/crew/confirm-config./cc-ab.json"):
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


# --- round 9: escape characters and paths the guard cannot resolve (crew 1.3.151) ------------------------------------
# Round 8 was refused for `confi\g.json`, ``confi`g.json`` and `confi^g.json` (each shell strips its escape
# character before it uses the word) and for `Set-Content -Path (Join-Path $HOME ...)`. The owner's decision: stop
# chasing spellings. A word with an escape is read as each shell reads it; a write target the guard cannot resolve to
# one path is refused when it could be the owner's. Reading, and writing elsewhere, still pass.

# the same paths with an escape character the shell strips, in every place a name can hold one
BASH_ESCAPES = (
    "{h}/.claude/crew/confi\\g.json",
    "{h}/.claude/crew/c\\onfig.json",
    "{h}/.claude/crew/\\config.json",
    "{h}/.claude/\\crew/config.json",
    "{h}/.cl\\aude/crew/config.json",
    "{h}/\\.claude/crew/config.json",
    "{h}/.claude/crew/confirm\\-config/cc-ab.json",
    "{h}/.claude/crew/\\confirm-config/cc-ab.json",
    "{h}/.claude/crew/confirm-config/c\\c-ab.json",
    "{h}/.claude/crew/confirm-config/cc-ab.js\\on",
    "{h}/.claude/crew/confirm-config/cc-\\*.json",
    "{h}/.claude/crew/confi\\g.j\\son",
)
PS_ESCAPES = tuple(spelled.replace("\\", "`") for spelled in BASH_ESCAPES) + (
    "{h}\\.claude\\crew\\confi`g.json",
    "{h}\\.claude\\crew\\confirm-config\\cc-a`b.json",
    "{h}\\.claude\\cr`ew\\config.json",
)
CMD_ESCAPES = tuple(spelled.replace("\\", "^") for spelled in BASH_ESCAPES) + (
    "{h}\\.claude\\crew\\confi^g.json",
    "{h}\\.claude\\crew\\confirm-config\\cc-a^b.json",
)


@pytest.mark.parametrize("name, spellings, verbs, homes", [
    ("bash escape", BASH_ESCAPES, BASH_VERBS, BASH_HOMES),
    ("powershell escape", PS_ESCAPES, PS_VERBS, PS_HOMES),
    ("cmd escape", CMD_ESCAPES, CMD_VERBS, CMD_HOMES),
])
def test_an_escape_character_does_not_hide_the_owners_file(name, spellings, verbs, homes, home):
    """Every escape placement x every write verb of its shell x every way to reach home."""
    slipped = _unrefused(_cells(spellings, verbs, homes))
    assert not slipped, f"{len(slipped)} {name} cells were not refused:\n" + "\n".join(slipped[:60])


def test_the_escape_of_one_shell_is_read_in_every_shell(home):
    """The splitter cannot tell which shell a command is for, so an escape is read as any shell reads it."""
    slipped = []
    for spellings in (BASH_ESCAPES, PS_ESCAPES, CMD_ESCAPES):
        for verbs in (BASH_VERBS, PS_VERBS, CMD_VERBS):
            slipped += _unrefused(_cells(spellings, verbs, ("~",)))
    assert not slipped, f"{len(slipped)} cells were not refused:\n" + "\n".join(slipped[:60])


def test_an_escaped_verb_is_still_the_verb(home):
    for command in ("r\\m ~/.claude/crew/config.json", "\\rm ~/.claude/crew/config.json",
                    "c\\p x ~/.claude/crew/config.json", "Set-Cont`ent ~/.claude/crew/config.json x",
                    "Remo`ve-Item ~/.claude/crew/config.json", "co^py x ~/.claude/crew/config.json",
                    "echo x | te\\e ~/.claude/crew/config.json", "bash -c \"echo x > ~/.claude/crew/confi\\g.json\"",
                    "pwsh -Command \"Set-Content ~/.claude/crew/confi`g.json x\"",
                    "cmd /c \"echo x > ~\\.claude\\crew\\confi^g.json\""):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


# a path the shell builds: the front of it, a piece of it, or all of it is a substitution, a variable the command did
# not set, a backtick, an ANSI-C string or a parenthesised expression
DYNAMIC = (
    "~/.claude/crew/$NAME",
    "~/.claude/crew/${NAME}",
    "~/.claude/crew/conf$SUFFIX",
    "~/.claude/crew/$(echo config.json)",
    "~/.claude/crew/\"$(echo config).json\"",
    "~/.claude/$A/config.json",
    "~/.claude/crew/confirm-config/$R",
    "~/.claude/crew/confirm-config/cc-$ID.json",
    "~/.claude/crew/`echo config.json`",
    "$(echo ~/.claude/crew)/config.json",
    "\"$(printf %s ~/.claude/crew)/config.json\"",
    "`echo ~/.claude/crew`/config.json",
    "$'~/.claude/crew/conf\\x69g.json'",
    "$'~/.claude/crew/\\143onfig.json'",
    "~/.claude/crew/c\"$(true)\"onfig.json",
    "~/.claude/crew/`date`",
    "~/.claude/crew/conf$X\\ig.json",
    "~/$A/config.json",
    "~/$A/confirm-config/cc-ab.json",
    "$UNSET/.claude/crew/config.json",
    "${UNSET}/crew/confirm-config/cc-ab.json",
    "%UNSET%\\.claude\\crew\\config.json",
    "$env:UNSET\\.claude\\crew\\config.json",
)
# the same, where the command names the owner's folder elsewhere (as something it may write: `NAMED`, not a read of
# it) and the target is only a variable or a substitution
DYNAMIC_IN_CONTEXT = (
    "$D/config.json", "$D", "${D}", "\"$D\"", "$(cat p)", "\"$(cat p)/config.json\"", "$D/crew/config.json",
    "%D%\\config.json", "$env:D\\config.json", "`cat p`", "$D/confirm-config/cc-ab.json", "$D/CONFIG.JSON",
    "$D/config.json.", "$D/Crew/Config.Json", "$D/confirm-config/CC-AB.JSON", "$D/conf\\ig.json",
)
# beside the owner's folder in the command, but a name that cannot end one of the owner's paths: not the owner's
UNKNOWN_FOLDER_OTHER_NAME = (
    "$D/out.txt", "$D/notes.md", "$D/crew/config.json/sub", "$D/.claude/crew/config.json.d/f", "$D/confirm-config.md",
    "\"$D/out.txt\"", "${D}/out.txt", "%D%\\out.txt", "$env:D\\out.txt", "$(cat p)/out.txt",
)
PS_PARENS = (
    "(Join-Path $HOME \".claude/crew/config.json\")",
    "(Join-Path $HOME '.claude\\crew\\config.json')",
    "(Join-Path $env:USERPROFILE \".claude\\crew\\confirm-config\\cc-ab.json\")",
    "(Join-Path (Join-Path $HOME \".claude\") \"crew\\config.json\")",
    "(Join-Path (Join-Path $HOME '.claude') (Join-Path 'crew' 'config.json'))",
    "($HOME + '\\.claude\\crew\\config.json')",
    "(\"$HOME\\.claude\\crew\\config.json\")",
    "(Resolve-Path ~/.claude/crew/config.json)",
    "$($HOME)/.claude/crew/config.json",
    "((Get-Item ~).FullName + '\\.claude\\crew\\config.json')",
)


# what makes a command one that NAMES the owner's folder (crew 1.3.151): `.claude/crew` outside a read
NAMED = "mkdir -p ~/.claude/crew; "


def test_a_path_the_guard_cannot_resolve_is_refused_when_it_could_be_the_owners(home):
    slipped = []
    for shell_verbs, homes in ((BASH_VERBS, BASH_HOMES), (PS_VERBS, PS_HOMES), (CMD_VERBS, CMD_HOMES)):
        slipped += _unrefused(_cells(DYNAMIC, shell_verbs, ("~",)))
        slipped += _unrefused(_cells(DYNAMIC_IN_CONTEXT, [f"{NAMED}{v}" for v in shell_verbs], homes[:1]))
    assert not slipped, f"{len(slipped)} cells were not refused:\n" + "\n".join(slipped[:60])


def test_a_parenthesised_path_is_refused_by_every_powershell_write(home):
    slipped = _unrefused(_cells(PS_PARENS, PS_VERBS, ("~",)))
    assert not slipped, f"{len(slipped)} cells were not refused:\n" + "\n".join(slipped[:60])


def test_the_round_9_findings_are_refused_through_the_whole_guard(home):
    """The four escape spellings and the parenthesised path, through `shell_refusal`, the hook's entry point."""
    for command in ("echo x > ~/.claude/crew/confi\\g.json",
                    "echo x > ~/.claude/crew/confirm-config/cc-ab.json".replace("confirm-config", "confirm\\-config"),
                    "Set-Content ~\\.claude\\crew\\confi`g.json x",
                    "echo x > %USERPROFILE%\\.claude\\crew\\confi^g.json",
                    "Set-Content -Path (Join-Path $HOME \".claude/crew/config.json\") -Value x"):
        assert scope_guard.shell_refusal(command, None), command


# where nothing in the command names the owner's folder, an unresolvable target is just a target
UNRELATED_TARGETS = (
    "$D/out.txt", "$OUT", "\"$OUT\"", "${OUT}", "$(git rev-parse --show-toplevel)/out.txt", "`pwd`/out.txt",
    "$X/config.json", "%TEMP%\\out.txt", "$env:TEMP\\out.txt", "$'/tmp/out\\x2etxt'", "/tmp/$NAME", "out-$ID.json",
    "(Join-Path $PWD \"out.txt\")", "(Join-Path $env:TEMP 'out.txt')", "(Get-Location).Path", "$HOME/notes/$NAME",
    "~/proj/$NAME", "~/proj/conf$SUFFIX", "~/.cache/$NAME",
)


def test_an_unresolvable_target_in_a_command_that_never_names_the_owner_is_allowed(home):
    verbs = BASH_VERBS + PS_VERBS + CMD_VERBS
    verbs = [v for v in verbs if "{t}.bak" not in v]   # `cp {t} {t}.bak` is two targets
    hit = _refused(_cells(UNRELATED_TARGETS, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a target that is not the owner's:\n" + "\n".join(hit[:60])


def test_an_unresolvable_target_below_an_ancestor_of_home_is_refused(home):
    """The other side of the cell above (crew 1.3.151). `<folder>/$NAME` can be any path below `<folder>`, so when
    the folder is an ANCESTOR of the owner's home the guard cannot tell the target from the owner's file and
    refuses; so does a `find` that starts there and deletes, or hands what it finds to a shell. That is what the
    Linux CI run showed when the throwaway home sat under `/tmp` (the fixture's fault, not the guard's). A folder
    that only shares the ancestor's spelling as a prefix is not an ancestor and stays allowed, and a real write to
    the owner's files is refused under this fixture as under any."""
    above = str(home.parent).replace("\\", "/")
    spelled = str(home).replace("\\", "/")
    must_block = [f"echo x > {above}/$NAME", f"echo x >> {above}/$NAME", f"rm -f {above}/$NAME",
                  f"printf x | tee {above}/$NAME", f"cp x {above}/$NAME", f"Set-Content {above}/$NAME x",
                  f"Remove-Item {above}/$NAME", f"echo x > {above}/$(basename $w)",
                  f"find {above} -exec sh -c 'echo x > {ELSEWHERE_ROOT}/out.bin' \\;", f"find {above} -delete",
                  f"echo x > {spelled}/.claude/crew/config.json", "echo x > ~/.claude/crew/config.json",
                  f"rm {spelled}/.claude/crew/confirm-config/cc-ab12.json",
                  f"find {spelled}/.claude -name config.json -delete"]
    missed = _unrefused([(command, None) for command in must_block])
    assert not missed, f"{len(missed)} commands that may write the owner's files were allowed:\n" + "\n".join(missed)
    must_allow = [f"echo x > {above}-other/$NAME", f"rm -f {above}x/$NAME", f"find {above}-other -delete",
                  f"find {above}x -exec sh -c 'echo x > {ELSEWHERE_ROOT}/out.bin' \\;",
                  f"echo x > {ELSEWHERE_ROOT}/$NAME", f"find {ELSEWHERE_ROOT} -delete"]
    hit = _refused([(command, None) for command in must_allow])
    assert not hit, f"{len(hit)} commands aimed beside the home's ancestor were refused:\n" + "\n".join(hit)


def test_the_throwaway_home_is_not_below_the_folder_the_corpus_calls_elsewhere(home):
    """The fixture's own promise: `/tmp` is no ancestor of the home, spelled or resolved."""
    assert not _below_elsewhere(home), home


def test_an_escape_in_another_file_is_not_the_owners(home):
    elsewhere = [spelled.replace("config.json", "confi\\g.json") for spelled in ELSEWHERE if "config.json" in spelled]
    elsewhere += [spelled.replace("cc-ab.json", "cc-a\\b.json") for spelled in ELSEWHERE if "cc-ab.json" in spelled]
    hit = _refused(_cells(elsewhere, BASH_VERBS, ("~",)))
    hit += _refused(_cells([e.replace("\\", "`") for e in elsewhere if "\\" in e and ":" not in e], PS_VERBS, ("~",)))
    assert not hit, f"{len(hit)} cells refused a file that is not the owner's:\n" + "\n".join(hit[:60])


def test_reading_through_an_escape_or_a_dynamic_path_is_not_writing(home):
    sources = [spelled.replace("{h}", "~") for spelled in BASH_ESCAPES] + [
        spelled.replace("{h}", "~") for spelled in PS_ESCAPES] + [
        s for s in DYNAMIC + DYNAMIC_IN_CONTEXT if "{h}" not in s] + list(PS_PARENS)
    reads = ["cat {t}", "cat {t} | grep x", "grep x {t}", "ls -l {t}", "head -n 1 {t}", "Get-Content {t}",
             "Get-Item {t}", "Test-Path {t}", "type {t}", "echo {t} > out.txt", "cp {t} /tmp/out",
             "Copy-Item -Path {t} -Destination out.txt"]
    hit = _refused(_cells(sources, reads, ("~",)))
    assert not hit, f"{len(hit)} read cells were refused:\n" + "\n".join(hit[:60])


def test_a_dynamic_cd_makes_a_relative_target_unknown(home):
    for command in ("cd $D; echo x > config.json; mkdir -p ~/.claude/crew",
                    "cd $D; echo x > ./config.json; mkdir -p ~/.claude/crew",
                    "cd $(pwd)/x && rm confirm-config/cc-ab.json; mkdir -p ~/.claude/crew",
                    "Set-Location $env:UNSET; Set-Content config.json x; mkdir -p ~/.claude/crew"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    # ... but not from a folder that is known, not for a name that cannot end an owner path (`out.txt`, `mv x y`),
    # and not where the command only reads the owner's file or mentions `.claude` (crew 1.3.151)
    for command in ("cd $D; echo x > config.json", "cd /tmp/x; echo x > config.json; mkdir -p ~/.claude/crew",
                    "cd $D; echo x > out.txt; mkdir -p ~/.claude/crew", "cd $D; mv x y; mkdir -p ~/.claude/crew",
                    "cd $D; echo x > config.json; ls ~/.claude",
                    "cd $D; echo x > config.json; cat ~/.claude/crew/config.json",
                    "cd $D && cat ~/.claude/CLAUDE.md > out.txt",
                    "cd $WT; sed -i s/a/b/ plugin/crew/foo.py; cat ~/.claude/crew/config.json"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_an_unknown_folder_in_front_of_a_name_that_cannot_be_the_owners_is_allowed_in_context(home):
    verbs = [f"mkdir -p ~/.claude/crew; {v}" for v in BASH_VERBS + PS_VERBS + CMD_VERBS if "{t}.bak" not in v]
    hit = _refused(_cells(UNKNOWN_FOLDER_OTHER_NAME, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a name that cannot be the owner's:\n" + "\n".join(hit[:60])


def test_an_escape_stripped_reading_of_a_windows_path_is_not_the_owners(home):
    """`C:\\proj\\out.txt` read with its backslashes taken out is a garbled relative word: from a folder a dynamic
    `cd` made unknown it is no more the owner's than the path as written."""
    targets = ("C:\\proj\\out.txt", "C:\\proj\\sub\\notes.md", "D:\\a\\b/.claude/crew/other.json")
    # only verbs whose one relative word is the target: `mv x {t}` also names `x`, which that cd made unknown
    verbs = [f"cd $D; mkdir -p ~/.claude/crew; {v}" for v in (
        "echo x > {t}", "echo x >> {t}", "cat a > {t}", "printf x | tee {t}", "Set-Content {t} x",
        "Set-Content -Path {t} -Value x", "Add-Content {t} x", "Out-File {t}", "type x > {t}", "sc {t} x")]
    hit = _refused(_cells(targets, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a Windows path that is not the owner's:\n" + "\n".join(hit[:60])


def test_a_relative_target_with_an_unknown_part_after_a_dynamic_cd_is_unknown(home):
    """Refused only when what is spelled of it could end one of the owner's paths (crew 1.3.151)."""
    for command in ("cd $D; echo x > conf$N; mkdir -p ~/.claude/crew", "cd $D; rm crew/$N; mkdir -p ~/.claude/crew",
                    "cd $D; rm confirm-config/$N.json; mkdir -p ~/.claude/crew"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("cd /tmp/x; echo x > sub/$N; mkdir -p ~/.claude/crew", "cd $D; echo x > sub/$N", "echo x > sub/$N",
                    "cd $D; echo x > sub/$N; mkdir -p ~/.claude/crew", "cd $D; echo x > conf$N; ls ~/.claude",
                    "cd $D; rm sub/$N.json; cat ~/.claude/crew/config.json"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_a_word_after_a_parenthesised_expression_is_a_plain_word(home):
    """Only what sits INSIDE the parentheses is an expression; the next word is read as written."""
    for command in ("Copy-Item (Get-Item ~/.claude/crew/config.json) out.txt",
                    "Set-Content (Join-Path $PWD 'a.txt') x; Set-Content out.txt y",
                    "Copy-Item -Path (Get-Item ~/.claude/crew/config.json) -Destination out.txt",
                    "Copy-Item (Get-Item ~/.claude/crew/config.json) -Destination out.txt",
                    # ... also in a command that names the owner's folder, where an expression would be refused
                    "mkdir -p ~/.claude/crew; Write-Output (Get-Date) > out.txt"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


@pytest.mark.parametrize("command", [
    "[System.IO.File]::WriteAllText((Join-Path $HOME '.claude/crew/config.json'),'x')",
    "[System.IO.File]::AppendAllText((Join-Path $HOME '.claude/crew/config.json'),'x')",
    "[System.IO.File]::Delete((Join-Path $HOME '.claude/crew/config.json'))",
    "[System.IO.File]::Create((Join-Path $HOME '.claude/crew/config.json'))",
    "[System.IO.File]::Copy('x',(Join-Path $HOME '.claude/crew/config.json'))",
    "[System.IO.File]::Move('x',(Join-Path $HOME '.claude/crew/config.json'))",
    "[IO.File]::Delete((Join-Path $HOME '.claude/crew/config.json'))",
    "[IO.File]::Create((Join-Path $HOME '.claude/crew/config.json'))",
    "[IO.File]::Copy('x',(Join-Path $HOME '.claude/crew/config.json'))",
    "[IO.File]::Move('x',(Join-Path $HOME '.claude/crew/config.json'))",
    "[IO.File]::AppendAllText((Join-Path $HOME '.claude/crew/config.json'),'x')",
    "pwsh -c \"[System.IO.File]::Delete((Join-Path $HOME '.claude/crew/config.json'))\"",
    "pwsh -c \"if (1) { [System.IO.File]::Copy('x',(Join-Path $HOME '.claude/crew/config.json')) }\"",
])
def test_a_dotnet_write_to_a_built_path_is_refused(command, home):
    """The destination is an expression, so only its text can say it is the owner's file."""
    assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_a_dotnet_write_through_an_escape_is_the_owners_file(home):
    for command in ("[System.IO.File]::WriteAllText('~/.claude/crew/confi`g.json', 'x')",
                    "[IO.File]::AppendAllText(\"~/.claude/crew/confi`g.json\", 'x')",
                    "[IO.File]::Delete('~\\.claude\\crew\\confi`g.json')"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


# a write inside a block, a loop or a condition is still a write: the verb is not the first word of the line
PS_BLOCKS = (
    "foreach ($f in 1) { <C> }", "if ($true) { <C> }", "1..3 | ForEach-Object { <C> }", "& { <C> }",
    "try { <C> } catch { }", "& {<C>}", "$b = { <C> }; & $b", "while ($false) { <C> }", "if ($false) { } else { <C> }",
    "foreach ($f in 1) {<C>}", "Invoke-Command -ScriptBlock { <C> }", ". { <C> }",
)
BASH_BLOCKS = (
    "for f in a; do <C>; done", "if true; then <C>; fi", "while false; do <C>; done", "{ <C>; }", "if <C>; then :; fi",
    "! <C>", "true && { <C>; }", "until true; do <C>; done", "if false; then :; else <C>; fi",
    "for f in a; do for g in b; do <C>; done; done", "case x in x) <C>;; esac",
    "case x in a) true;; b) <C>;; esac", "case x in a|b) <C>;; esac",
)


def test_a_write_inside_a_block_or_a_loop_is_a_write(home):
    slipped = []
    for blocks, verbs, home_prefix in ((PS_BLOCKS, PS_VERBS, "~"), (BASH_BLOCKS, BASH_VERBS, "~")):
        for block in blocks:
            for verb in verbs:
                command = block.replace("<C>", verb.replace("{t}", f"{home_prefix}/.claude/crew/config.json"))
                if scope_guard._owner_command_refusal(command) is None:  # pylint: disable=protected-access
                    slipped.append(command)
    assert not slipped, f"{len(slipped)} cells were not refused:\n" + "\n".join(slipped[:60])


def test_a_read_or_another_file_inside_a_block_is_not_the_owners(home):
    hit = []
    for blocks, verbs in ((PS_BLOCKS, PS_VERBS), (BASH_BLOCKS, BASH_VERBS)):
        for block in blocks:
            for verb in verbs:
                for target in ("/tmp/out.txt", "C:/other/.claude/crew/config.json"):
                    command = block.replace("<C>", verb.replace("{t}", target))
                    if scope_guard._owner_command_refusal(command):  # pylint: disable=protected-access
                        hit.append(command)
            for read in ("cat ~/.claude/crew/config.json", "Get-Content ~/.claude/crew/config.json",
                         "echo ~/.claude/crew/config.json > out.txt"):
                command = block.replace("<C>", read)
                if scope_guard._owner_command_refusal(command):  # pylint: disable=protected-access
                    hit.append(command)
    assert not hit, f"{len(hit)} cells were refused:\n" + "\n".join(hit[:60])


def test_a_brace_expansion_word_is_not_a_block(home):
    for command in ("rm {a,b}", "rm {x} out.txt", "echo {Set-Content,x} out.txt", "cp ${HOME}/x /tmp/y"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access
    for command in ("rm {x} ~/.claude/crew/config.json", "rm -f ${X} ~/.claude/crew/config.json",
                    "cp x ${D} ~/.claude/crew/config.json", "echo ${H} > ~/.claude/crew/config.json"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_a_variable_the_command_set_is_followed_not_guessed(home):
    """With the folder named in the command, an unknown variable is refused; one the command SET is its value."""
    for command in ("X=/tmp/other; echo x > $X", "X=/tmp/other; echo x > $X/config.json",
                    "export X=/tmp/other; rm -f $X/crew/config.json", "$d = 'C:/other'; Set-Content $d/config.json x",
                    "$d='C:/other'; Set-Content $d/config.json x", "$d ='C:/other'; Set-Content $d/config.json x",
                    "$env:D = 'C:/other'; Set-Content $env:D/config.json x",
                    "$d = 'C:/other'; $d -replace 'x','y' | Out-Null; Set-Content $d/config.json x",
                    "set X=/tmp/other & echo x > %X%/config.json",
                    "for i in 1; do echo x > ~/.claude/crew/c$i.json; done"):
        assert scope_guard._owner_command_refusal(NAMED + command) is None, command  # pylint: disable=protected-access
    for command in ("X=~/.claude/crew; echo x > $X/config.json", "$d = '~/.claude/crew'; Set-Content $d/config.json x",
                    "export X=~/.claude/crew/confirm-config; rm $X/cc-ab.json",
                    "mkdir -p ~/.claude/crew; X=$(pwd); echo x > $X"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access


def test_a_relative_word_with_no_working_directory_is_judged_by_its_tail(home):
    """No folder to join it to: the way it ENDS decides. With a folder (the hook always has one) it is joined."""
    for command in ("echo x > crew/config.json", "rm confirm-config/cc-1.json", "cp x .claude/crew/config.json",
                    "echo x > confirm-config/cc-ab.json"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
        assert scope_guard._owner_command_refusal(command, "/tmp/x") is None, command  # pylint: disable=protected-access
    for command in ("echo x > other/config.json", "echo x > crewx/config.json", "echo x > config.json"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_a_backtick_substitution_is_read_as_a_command(home):
    for command in ("echo `rm ~/.claude/crew/config.json`", "echo \"`rm ~/.claude/crew/config.json`\"",
                    "ls `echo x > ~/.claude/crew/confirm-config/cc-ab.json`"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    assert scope_guard._owner_command_refusal("echo `date`") is None  # pylint: disable=protected-access


def test_what_makes_a_command_name_the_owners_folder(home):
    """The hint is `.claude/crew`, the confirm-config store or `crew/config.json`, in what the command SAYS it may
    write: a comment is not said, an escape character or a quote does not hide it, and a READ of the owner's file
    (the operand of `cat`, `Get-Content`, the source of a copy) does not count (crew 1.3.151)."""
    for command in ("mkdir -p ~/.claude/crew; echo x > $D", "mkdir /tmp/confirm-config; echo x > $D",
                    "echo crew/config.json; echo x > $D", "mkdir ~/.cl\\aude/crew; echo x > $D",
                    "mkdir ~/.cl`aude/crew; echo x > $D", "mkdir ~/.cl^aude/crew; echo x > $D",
                    "mkdir ~/'.cl'aude/crew; echo x > $D", "mkdir ~\\.claude\\crew; echo x > $D",
                    "mkdir -p ~/.claude/crew; Set-Content $D x", "mkdir -p ~/.claude/crew; echo x > \"$(cat p)\"",
                    "cp x ~/.claude/crew/other.json; echo y > $D", "robocopy a ~/.claude/crew/sub x; echo y > $D",
                    "Copy-Item -Destination ~/.claude/crew/other.json x; echo y > $D",
                    "cp -t ~/.claude/crew/sub x; echo y > $D",
                    "echo ~/.claude/crew/config.json > /tmp/p; echo x > \"$(cat /tmp/p)\"",
                    "bash -c \"mkdir ~/.claude/crew\"; echo x > $D",
                    "for f in a ~/.claude/crew/config.json; do echo x > $f; done"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("echo x > $D # ~/.claude/crew/config.json", "echo x > $D # confirm-config", "echo x > $D",
                    "mkdir ~/.claude/crewx; echo x > $D", "mkdir ~/not-confirm-config; echo x > $D",
                    "mkdir ~/claude-notes/crew; echo x > $D",
                    # `.claude` alone, and crew's worktrees folder, are not the owner's folder
                    "ls ~/.claude; echo x > $D", "mkdir -p ~/.claude; echo x > $D", "cd .claude && echo x > $F",
                    "mkdir -p ~/.claude/crew/worktrees/repo; echo x > $D",
                    "git -C ~/.claude/crew/worktrees/repo/lane status; echo x > $D",
                    # a read of the owner's file is not a write to it
                    "cat ~/.claude/crew/config.json; echo x > $D", "cat ~/.claude/crew/config.json > \"$OUT\"",
                    "cat ~/.claude/crew/config.json | tee \"$OUT\"",
                    "ls -la ~/.claude/crew/confirm-config; echo x > $D",
                    "Get-Content ~/.claude/crew/config.json | Set-Content $D",
                    "cat ~/.claude/crew/config.json | jq .guards > \"$OUT\"", "grep x crew/config.json; echo x > $D",
                    "cp ~/.claude/crew/config.json \"$BACKUP\"", "cp -f ~/.claude/crew/config.json $D",
                    "Copy-Item ~/.claude/crew/config.json (Join-Path $PWD 'c.json')",
                    "bash -c \"cat ~/.claude/crew/config.json\" > $OUT",
                    "pwsh -Command \"Get-Content ~/.claude/crew/config.json\" > $OUT",
                    "if test -f ~/.claude/crew/config.json; then echo yes > $OUT; fi",
                    # a heredoc `cat` copies out is text, not something the command says it may write
                    "cat <<EOF > \"$OUT\"\nsee ~/.claude/crew/config.json\nEOF",
                    "cat > $OUT <<'EOF'\nthe receipts live in ~/.claude/crew/confirm-config/\nEOF"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


# --- round 9, finding 3: the write reading belongs to the verb, not to a word in a file name ------------------------

@pytest.mark.parametrize("command", [
    "Get-Content C:\\tmp\\confirm-config\\echo.txt",
    "Get-Content C:/tmp/confirm-config/echo.txt",
    "cat /tmp/confirm-config/echo.txt",
    "cat /tmp/confirm-config/printf.log | grep x",
    "cat /tmp/confirm-config/echo",
    "Get-Content C:\\tmp\\confirm-config\\echo",
    "Get-Content ~/.claude/crew/confirm-config/echo.txt",
    "ls /tmp/confirm-config/rm-list.txt",
    "Select-String x C:\\tmp\\confirm-config\\sed.out",
])
def test_a_verb_inside_a_file_name_in_the_store_is_not_a_write(command, home):
    assert scope_guard.shell_refusal(command, None) is None, command


@pytest.mark.parametrize("command", [
    "echo x /tmp/confirm-config/f",
    "Set-Content C:\\tmp\\confirm-config\\echo.txt x",
    "rm /tmp/confirm-config/echo.txt",
    "/bin/rm /tmp/confirm-config/f",
    "ls /tmp/confirm-config/f > x",
    "ls /tmp/confirm-config/f; {rm,x}",   # `rm x`, from a folder nobody can tell (no working directory here)
    "ls /tmp/confirm-config/f; {rm,/tmp/confirm-config/f}",
    "cat /tmp/confirm-config/x | tee y",
    "python3 -c pass /tmp/confirm-config/f",
])
def test_a_write_verb_beside_the_store_is_still_refused(command, home):
    assert scope_guard.shell_refusal(command, None), command


# =====================================================================================================================
# Round 10 (crew 1.3.151). Every case below runs twice: with no working directory, and with `top` SET to a repo root
# as the real hook always has it -- several round-10 bypasses only showed with `top` set, where a relative word is
# joined to the folder instead of being judged by its tail.
# =====================================================================================================================

@pytest.fixture(name="top", params=["no-top", "top"])
def _top(request, tmp_path):
    if request.param == "no-top":
        return None
    repo = tmp_path / "repo"
    (repo / ".claude" / "worktrees").mkdir(parents=True)
    return str(repo)


def _slipped(commands, top):
    return [c for c in commands if scope_guard.shell_refusal(c, None, top) is None]


def _hit_by(commands, top):
    return [f"{c}  =>  {scope_guard.shell_refusal(c, None, top)}" for c in commands
            if scope_guard.shell_refusal(c, None, top)]


def _report(found, what):
    return f"{len(found)} commands {what}:\n" + "\n".join(found[:60])


# a write verb whose one target is the relative word `{t}`: what a command writes after it has moved into a folder
RELATIVE_VERBS = (
    "echo x > {t}", "echo x >> {t}", "cat a > {t}", "printf x | tee {t}", "rm {t}", "rm -f {t}", "cp x {t}",
    "mv x {t}", "sed -i s/a/b/ {t}", "truncate -s 0 {t}", "del {t}", "del /f /q {t}", "erase {t}", "copy /y x {t}",
    "type x > {t}", "Set-Content {t} x", "Set-Content -Path {t} -Value x", "Add-Content {t} x", "Out-File {t}",
    "Remove-Item {t}", "Clear-Content {t}", "New-Item {t} -Force",
)


# --- BLOCK 1: cmd's `cd /d <folder>`: the switch is not the folder ------------------------------------------------

def _owner_folders(home):
    """The owner's folder as cmd, PowerShell and bash spell it: by variable, by `~`, and by its absolute path."""
    return ("%USERPROFILE%\\.claude\\crew", "~/.claude/crew", "$HOME/.claude/crew",
            str(home / ".claude" / "crew"), str(home / ".claude" / "crew").replace("\\", "/"))


CD_SWITCHES = ("cd /d {d}", "cd /D {d}", "chdir /d {d}", "cd /d \"{d}\"", "cd {d}", "pushd {d}", "Set-Location {d}")
JOINERS = (" && ", " & ", "&&", "; ")


def test_a_cmd_cd_switch_is_not_the_folder(home, top):
    commands = []
    for folder in _owner_folders(home):
        for moved in CD_SWITCHES:
            for joiner in JOINERS:
                for verb in RELATIVE_VERBS:
                    commands.append(moved.replace("{d}", folder) + joiner + verb.replace("{t}", "config.json"))
        commands += [f"cmd /c \"cd /d {folder}&&echo x > config.json\"",
                     f"cmd /c \"cd /d {folder} && del config.json\"",
                     f"cmd.exe /c \"cd /D {folder} & type x > config.json\"",
                     f"cd /d {folder}\\confirm-config && del cc-ab12.json",
                     f"cd /d {folder} && echo x > confirm-config\\cc-ab12.json"]
    slipped = _slipped(commands, top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_cd_switch_to_another_folder_is_followed_there(home, top):
    commands = [moved.replace("{d}", folder) + " && " + verb.replace("{t}", "config.json")
                for folder in ("C:\\repos\\other", "C:/other/.claude/crew", "/tmp/x", "%TEMP%\\w")
                for moved in CD_SWITCHES for verb in RELATIVE_VERBS]
    hit = _hit_by(commands, top)
    assert not hit, _report(hit, "were refused in a folder that is not the owner's")


# --- BLOCK 2: a PowerShell variable assigned from an expression ---------------------------------------------------

PS_VARIABLE_VERBS = tuple(v for v in PS_VERBS if "{t}" in v)
# `$p` is the owner's file, built by an expression the guard cannot evaluate
PS_ASSIGNED = (
    "$p = Join-Path $HOME \".claude/crew/config.json\"",
    "$p = Join-Path $HOME '.claude\\crew\\config.json'",
    "$p = $HOME + \"\\.claude\\crew\\config.json\"",
    "$p = \"$HOME\" + '/.claude/crew/config.json'",
    "$p=Join-Path $HOME \".claude/crew/config.json\"",
    "$p =Join-Path $HOME \".claude/crew/config.json\"",
    "$p = (Join-Path $HOME \".claude/crew/config.json\")",
    "$p = Join-Path (Join-Path $HOME \".claude\") \"crew\\config.json\"",
    "$p = Join-Path $env:USERPROFILE \".claude\\crew\\confirm-config\\cc-ab12.json\"",
    "$p = Resolve-Path ~/.claude/crew/config.json",
    "$p = (Resolve-Path ~/.claude/crew/config.json).Path",
    "$global:p = Join-Path $HOME \".claude/crew/config.json\"",
    # in pieces: nothing in the command spells `.claude/crew`, the expression joins it
    "$p = [IO.Path]::Combine($HOME, \".claude\", \"crew\", \"config.json\")",
    "$p = Join-Path $HOME \".claude\" \"crew\" \"config.json\"",
    "$p = $HOME, \".claude\", \"crew\", \"config.json\" -join \"/\"",
    # a literal: followed, not guessed
    "$p = \"$HOME/.claude/crew/config.json\"", "$p=\"$HOME/.claude/crew/config.json\"",
    "$p = '~/.claude/crew/config.json'", "$p ='~/.claude/crew/config.json'",
)
PS_ASSIGNED_FOLDER = (
    "$d = Join-Path $HOME \".claude/crew\"", "$d = $HOME + '\\.claude\\crew'", "$d=Join-Path $HOME .claude/crew",
    "$d = [IO.Path]::Combine($HOME, \".claude\", \"crew\")", "$d = \"$HOME/.claude/crew\"",
)
BASH_ASSIGNED = (
    "P=$(echo ~/.claude/crew/config.json)", "P=\"$(printf %s ~/.claude/crew)/config.json\"",
    "P=`echo ~/.claude/crew/config.json`", "P=$(cat ~/.claude/crew/where.txt)",
    "P=$(realpath ~/.claude/crew)/config.json",
    "export P=$(echo ~/.claude/crew/config.json)", "P=~/.claude/crew/config.json",
)
# the same shapes, building a path that is not the owner's
PS_ASSIGNED_ELSEWHERE = (
    "$p = Join-Path $wt \"x.json\"", "$p = Join-Path $PWD \"out.txt\"", "$p = $env:TEMP + \"\\out.txt\"",
    "$p = Join-Path $repo \"plugin/crew/README.md\"", "$p = Join-Path $root \".claude/rules/crew.md\"",
    "$p = Join-Path $wt \".claude/worktrees/a/plugin/crew/x.py\"", "$p = Join-Path $wt \".claude/x.json\"",
    "$p = (Get-Location).Path", "$p = [IO.Path]::Combine($PWD, \"out\", \"x.txt\")", "$p = \"C:/other/x.json\"",
    "$p = New-TemporaryFile", "$p = Join-Path $HOME \".claude\" \"settings.json\"",
)
BASH_ASSIGNED_ELSEWHERE = (
    "P=$(mktemp)", "P=$(pwd)/.claude/worktrees/a/f.txt", "P=$(git rev-parse --show-toplevel)/plugin/crew/x.py",
    "P=/tmp/out.txt", "P=`pwd`/out.txt", "P=$(cat ~/.claude/settings.json)",
)


def test_a_powershell_variable_built_by_an_expression_fails_closed(home, top):
    commands = [f"{assigned}; {verb.replace('{t}', target)}" for assigned in PS_ASSIGNED
                for verb in PS_VARIABLE_VERBS for target in ("$p", "\"$p\"")]
    commands += [f"{assigned}; {verb.replace('{t}', target)}" for assigned in PS_ASSIGNED_FOLDER
                 for verb in PS_VARIABLE_VERBS for target in ("$d/config.json", "\"$d\\config.json\"",
                                                             "(Join-Path $d \"config.json\")")]
    commands += [f"{assigned}; {verb.replace('{t}', target)}" for assigned in BASH_ASSIGNED
                 for verb in BASH_VERBS for target in ("$P", "\"$P\"", "${P}")]
    slipped = _slipped(commands, top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_variable_built_for_another_path_is_not_the_owners(home, top):
    commands = [f"{assigned}; {verb.replace('{t}', '$p')}" for assigned in PS_ASSIGNED_ELSEWHERE
                for verb in PS_VARIABLE_VERBS]
    commands += [f"{assigned}; {verb.replace('{t}', '$P')}" for assigned in BASH_ASSIGNED_ELSEWHERE
                 for verb in BASH_VERBS if "{t}.bak" not in verb]
    hit = _hit_by(commands, top)
    assert not hit, _report(hit, "were refused for a variable that is not the owner's path")


def test_the_right_hand_side_of_an_assignment_is_a_command_too(home, top):
    slipped = _slipped(["$r = Set-Content ~/.claude/crew/config.json x",
                        "$null = Remove-Item ~/.claude/crew/config.json",
                        "$r=Set-Content ~/.claude/crew/config.json x",
                        "$ok = rm ~/.claude/crew/confirm-config/cc-ab12.json",
                        "$t = [IO.File]::WriteAllText(\"$HOME/.claude/crew/config.json\", 'x')"], top)
    assert not slipped, _report(slipped, "were not refused")
    hit = _hit_by(["$c = Get-Content ~/.claude/crew/config.json", "$n = 5; Set-Content out.txt $n",
                   "$x = \"rm\"; Write-Output $x", "$a -eq 1",
                   "$files = Get-ChildItem *.tmp; $files | Remove-Item"], top)
    assert not hit, _report(hit, "were refused")


# --- BLOCK 3: `${env:X}` and its siblings inside a word ------------------------------------------------------------

ENV_WORDS = (
    "~/.claude/crew/c${env:Q}nfig.json", "~/.claude/crew/${env:Q}config.json", "~/.claude/crew/config${env:Q}.json",
    "~/.claude/crew/config.json${env:Q}", "\"~/.claude/crew/${env:Q}config.json\"",
    "~/.claude/crew/c$($env:Q)nfig.json",
    "~/.claude/crew/c$env:Q.json", "~/.claude/crew/$env:Qconfig.json", "~/.claude/crew/c${Q}nfig.json",
    "~/.claude/crew/c$Q.json", "~/.claude/crew/c${Q:-o}nfig.json", "~/.claude/crew/${env:NAME}",
    "~/.claude/crew/c$([Environment]::GetEnvironmentVariable('X'))nfig.json",
    "~/.claude/${env:D}/config.json", "~/.claude/crew/confirm-config/cc-${env:ID}.json",
    "~/.claude/crew/confirm-config/${env:R}", "${env:USERPROFILE}/.claude/crew/config.json",
    "${env:USERPROFILE}\\.claude\\crew\\config.json", "${env:HOME}/.claude/crew/confirm-config/cc-ab12.json",
    "${env:UNSET}/.claude/crew/config.json", "~\\.claude\\crew\\c${env:Q}nfig.json",
)
ENV_WORDS_ELSEWHERE = (
    "~/proj/c${env:X}nfig.json", "${env:TEMP}\\out.txt", "out-${env:ID}.json", "~/.cache/${env:NAME}",
    "${env:USERPROFILE}/notes/out.txt", "~/.claude/projects/${env:P}/memory.md", "$env:TEMP\\x${env:N}.txt",
    "~/.claude/crew/other${env:X}.txt", "~/.claude/crew/worktrees/${env:REPO}/config.json",
)


def test_an_environment_variable_in_braces_is_unknown_not_a_stream(home, top):
    verbs = BASH_VERBS + PS_VERBS + CMD_VERBS
    slipped = _slipped([v.replace("{t}", word) for word in ENV_WORDS for v in verbs], top)
    assert not slipped, _report(slipped, "were not refused")


def test_an_environment_variable_in_another_path_is_not_the_owners(home, top):
    verbs = [v for v in BASH_VERBS + PS_VERBS + CMD_VERBS if "{t}.bak" not in v]
    hit = _hit_by([v.replace("{t}", word) for word in ENV_WORDS_ELSEWHERE for v in verbs], top)
    assert not hit, _report(hit, "were refused for a path that is not the owner's")


# --- FIX 4: the write verbs and indirections round 10 named --------------------------------------------------------

R10_TARGETS = (
    "{h}/.claude/crew/config.json", "{h}\\.claude\\crew\\config.json", "{h}/.claude/crew/CONFIG.JSON",
    "{h}/.claude/crew./config.json", "{h}/.claude/crew/confirm-config/cc-ab12.json",
    "{h}/.claude/crew/confirm-config/cc-*.json",
)
R10_ELSEWHERE = (
    "out.txt", "/tmp/out.txt", "C:/other/.claude/crew/config.json", "{h}/.claude/settings.json",
    "{h}/.claude/crew/other.json", "{h}/.claude/crew/worktrees/repo/lane/config.json",
    "{h}/repo/.claude/crew/config.json",
)
PS_R10_VERBS = (
    "echo x | Tee-Object {t}", "echo x | Tee-Object -FilePath {t}", "echo x | Tee-Object -LiteralPath {t}",
    "echo x | Tee-Object -Append -FilePath {t}", "Get-Process | Export-Csv {t}", "Get-Process | Export-Csv -Path {t}",
    "Get-Process | Export-Csv -NoTypeInformation {t}", "Get-Process | epcsv {t}",
    "Export-Clixml -Path {t} -InputObject 1", "Get-Date | Export-Clixml {t}", "clc {t}",
    "Get-ChildItem {t} | Remove-Item", "Get-ChildItem {t} | Remove-Item -Force", "gci {t} | ri", "Get-Item {t} | del",
    "Get-Item {t} | Clear-Content", "Get-ChildItem {t} | clc", "Get-Item {t} | Set-Content -Value x",
    "Get-Item {t} | Add-Content -Value x", "Get-Item {t} | sc -Value x",
    "Get-Item {t} | Move-Item -Destination out.txt",
    "Get-Item {t} | Rename-Item -NewName c.bak", "Get-Item {t} |\n Remove-Item",
    "gci {t} | % { Set-Content $_.FullName x }", "gci {t} | ForEach-Object { Remove-Item $_ }",
    "gci {t} | ForEach-Object { Clear-Content $PSItem.FullName }", "gci {t} | % { $_ } | % { Remove-Item $_ }",
    ". Set-Content {t} x", "iex \"Set-Content {t} x\"", "Invoke-Expression \"sc {t} x\"",
    "Invoke-Expression -Command \"Set-Content {t} x\"", "\"Set-Content {t} x\" | iex",
    "\"Set-Content {t} x\" | Invoke-Expression", "echo \"Set-Content {t} x\" | pwsh -",
    "Start-Process pwsh -ArgumentList \"-c sc {t} x\"", "Start-Process pwsh -ArgumentList \"-c\",\"sc {t} x\"",
    "Start-Process -FilePath pwsh -ArgumentList \"-Command Set-Content {t} x\" -Wait",
    "saps cmd -ArgumentList \"/c echo x > {t}\"", "Set-Alias w Set-Content; w {t} x",
    "New-Alias -Name w -Value Set-Content; w {t} x", "sal w Remove-Item; w {t}",
    "$sb = [scriptblock]::Create(\"sc {t} x\"); & $sb", "$sb=[scriptblock]::Create('Remove-Item {t}'); & $sb",
)
BASH_R10_VERBS = (
    "sed -n \"w {t}\" a", "sed -n 'w {t}' a", "sed -e \"1w {t}\" a", "sed -n -e p -e \"w {t}\" a",
    "sed \"s/a/b/w {t}\" a", "sed \"s/a/b/gw {t}\" a", "sed --expression \"w {t}\" a", "cat a | sed -n \"w {t}\"",
    "ex -sc \"w {t}|q\" a", "vim -es -c \"w! {t}\" -c q a", "vim \"+w {t}\" a",
    "awk \"BEGIN{print 1 > \\\"{t}\\\"}\"", "awk '{print > \"{t}\"}' a", "gawk '{print >> \"{t}\"}' a",
    "timeout 5 bash -c \"echo x > {t}\"", "timeout 5 tee {t}", "timeout -s KILL 5 tee {t}",
    "timeout --foreground 5 rm {t}", "/usr/bin/timeout 5 tee {t}", "nice tee {t}", "nice -n 10 tee {t}",
    "nice bash -c \"echo x > {t}\"", "stdbuf -oL tee {t}", "stdbuf -o L tee {t}", "ionice -c 3 cp x {t}",
    "setsid rm {t}", "busybox tee {t}", "busybox rm -f {t}", "sudo -u root tee {t}", "env -u X tee {t}",
    "wsl -e sh -c \"echo x > {t}\"", "wsl bash -c \"rm {t}\"", "wsl -d Ubuntu sh -c \"echo x > {t}\"",
    "wsl.exe -e rm {t}", "echo x | xargs tee {t}", "xargs -a list rm {t}", "xargs tee {t} <<< x",
    "echo {t} | xargs rm", "echo {t} | xargs -n 1 rm -f", "echo {t} | xargs -0 -r rm",
    "printf '%s' {t} | xargs -I% cp x %",
    "echo {t} | xargs sed -i s/a/b/", "echo {t} | xargs sh -c 'echo x > $0'", "eval \"echo x > {t}\"",
    "trap \"rm {t}\" EXIT", "trap -- \"echo x > {t}\" EXIT", "bash <<< \"echo x > {t}\"", "sh <<< \"rm {t}\"",
    "echo \"echo x > {t}\" | bash", "echo \"rm {t}\" | sh", "printf 'rm %s' x; echo \"rm -f {t}\" | bash -s",
    "alias w=tee; echo x | w {t}", "alias w='tee -a'; echo x | w {t}", "for f in {t}; do echo x > $f; done",
    "for f in {t}; do rm \"$f\"; done", "for f in a {t}; do rm $f; done", "for f in $(ls {t}); do rm $f; done",
    "for f in a $(ls {t}); do rm $f; done", "ls {t} | while read f; do echo x > \"$f\"; done",
    "ls {t} | while read -r f; do rm \"$f\"; done", "while read f; do echo x > $f; done <<< {t}",
    "echo x > \"$(cat {t}.where)\"", "echo x > `cat {t}.where`", "echo x > \"`cat {t}.where`\"",
    "P=$(cat {t}.where); echo x > $P",
)
# what walks or lists a FOLDER and writes what it finds there
FOLDER_VERBS = (
    "find {d} -name config.json -delete", "find {d} -name 'conf*' -delete", "find {d} -iname CONFIG.JSON -delete",
    "find {d} -type f -delete", "find {d} -delete", "find {d} -name config.json -exec rm {} +",
    "find {d} -name '*.json' -exec rm -f {} \\;", "find {d} -name '*.json' -execdir rm {} +",
    "find {d} -name config.json -exec cp /tmp/a {} \\;", "find {d} -name '*.json' -exec sed -i s/a/b/ {} +",
    "find {d} -type f -exec sh -c 'echo x > \"$1\"' _ {} \\;", "find {d} -name 'cc-1*' -delete",
    "find {d} -type f -exec sh ./wipe.sh {} \\;",   # a shell handed what find found: no `-c` text to read
    "find {d} -name config.json | xargs rm", "find {d} -name config.json -print0 | xargs -0 rm -f",
    "cd {d}; ls | xargs rm", "cd {d} && ls *.json | xargs -I{} cp /tmp/a {}",
    "cd {d} && find . -name config.json -delete",
    "cd {d} && find -name config.json -delete", "cd {d}; echo x > $F", "cd {d}; Get-ChildItem | Remove-Item",
    "Get-ChildItem {d} | Remove-Item", "Get-ChildItem {d} | Remove-Item -Recurse -Force",
    "Get-ChildItem {d} -Filter config.json | Remove-Item -Force", "gci {d} | % { Set-Content $_.FullName x }",
    "ls {d}/*.json | while read f; do echo x > \"$f\"; done", "ls {d} | xargs rm",
    # what writes into the folder it stands in
    "cd {d} && unzip a.zip", "cd {d}; tar -xf a.tar", "cd {d} && git checkout -- .", "cd {d}; curl -sO http://x/y",
    "cd {d} && patch -p1 < a.patch",
)
OWNER_FOLDERS = ("~/.claude/crew", "$HOME/.claude/crew", "~/.claude/crew/confirm-config", "~/.claude/crew/")
# a `find` that starts ABOVE the owner's folder reaches it too, unless its `-name` rules the owner's names out
FIND_ABOVE = (
    "find ~/.claude -name config.json -delete", "find ~ -name 'config.json' -delete", "find ~/.claude -delete",
    "find ~/.claude -name '*.json' -exec rm {} +", "find ~ -name 'cc-*.json' -delete",
    "find ~/.claude/crew/confirm-config/old -type f -delete", "find ~/.claude ~/x -name config.json -delete",
)


def _spelled(verbs, targets, prefixes=("~", "$HOME")):
    return [verb.replace("{t}", target) for target in _expand_spellings(targets, prefixes) for verb in verbs]


def test_the_round_10_write_verbs_are_refused(home, top):
    slipped = _slipped(_spelled(PS_R10_VERBS, R10_TARGETS, ("~", "$HOME", "$env:USERPROFILE")), top)
    slipped += _slipped(_spelled(BASH_R10_VERBS, [t for t in R10_TARGETS if "\\" not in t]), top)
    assert not slipped, _report(slipped, "were not refused")


def test_the_round_10_write_verbs_on_another_file_are_allowed(home, top):
    """Two kinds of verb are judged by what the command SAYS, not by one resolved target, and so stay refused for
    another folder spelled `.claude/crew`: inline code handed to `pwsh -Command` (text only, as `python -c` is), and
    a target that is only a variable a loop or a pipe fills (`$f`, `$0`), which fails closed in a command that names
    that folder. Every other verb is judged by its target, and for those the folder's spelling does not matter."""
    said = ("-Command", "pwsh -", "$f", "$0", "$P", "read f", "read -r f", "% cp x %", ".where")
    by_target = [v for v in PS_R10_VERBS + BASH_R10_VERBS if not any(mark in v for mark in said)]
    by_text = [v for v in PS_R10_VERBS + BASH_R10_VERBS if any(mark in v for mark in said)]
    plain = [t for t in R10_ELSEWHERE if ".claude/crew" not in t]
    hit = _hit_by(_spelled(by_target, R10_ELSEWHERE, ("~",)) + _spelled(by_text, plain, ("~",)), top)
    assert not hit, _report(hit, "were refused for a file that is not the owner's")


def test_what_walks_the_owners_folder_and_writes_is_refused(home, top):
    slipped = _slipped([verb.replace("{d}", folder) for folder in OWNER_FOLDERS for verb in FOLDER_VERBS], top)
    slipped += _slipped(FIND_ABOVE + (NAMED + "find $D -name config.json -delete",), top)
    assert not slipped, _report(slipped, "were not refused")
    # by the owner-file check itself, which is all that runs with `scope.mode: off` (the store rule, round 11,
    # refuses a find inside a store spelled `confirm-config/` as well, and must not be what holds this up)
    for command in ("find ~/.claude/crew/confirm-config/old -type f -delete",
                    "find ~/.claude/crew/confirm-config -name 'cc-*' -delete"):
        assert scope_guard._owner_command_refusal(command, top), command  # pylint: disable=protected-access


def test_what_walks_another_folder_is_allowed(home, top):
    folders = ("build", ".", "/tmp/x", "~/proj", "~/.claude/projects", "~/.claude/crew/worktrees/repo/lane",
               ".claude/worktrees/a", "C:/other/crew")
    hit = _hit_by([verb.replace("{d}", folder) for folder in folders for verb in FOLDER_VERBS], top)
    hit += _hit_by(["find ~/.claude -name '*.log' -delete", "find ~ -name '*.pyc' -delete",
                    "find . -name config.json -delete",
                    "find ~/.claude/crew -name config.json", "find ~/.claude/crew -name config.json -print",
                    "find ~/.claude/crew -name config.json -exec cat {} +",
                    "find ~/.claude/crew -type f -exec sed -n p {} +",
                    "find ~/.claude/crew -name config.json | xargs cat", "ls ~/.claude/crew | xargs cat",
                    "ls ~/.claude/crew | xargs -n 1 echo", "git ls-files -o | xargs rm", "ls | xargs rm -f",
                    "echo ~/.claude/crew/config.json; git ls-files -o | xargs rm",
                    "ls ~/.claude/crew; Get-ChildItem *.tmp | Remove-Item", "Get-ChildItem *.tmp | Remove-Item",
                    "test -f ~/.claude/crew/config.json || ls build | xargs rm",
                    "Get-ChildItem ~/.claude/projects | Select-Object Name",
                    "Get-Item ~/.claude/crew/config.json | Set-Content out.txt",
                    "Get-Content ~/.claude/crew/config.json | Set-Content $out",
                    "Get-Content ~/.claude/crew/config.json | Add-Content -Path out.txt",
                    "Get-Item ~/.claude/crew/config.json | Copy-Item -Destination out.txt",
                    "Get-ChildItem .claude | ForEach-Object { Set-Content $_.FullName x }",
                    "Get-ChildItem ~/.claude/crew | ForEach-Object { Write-Output $_ }",
                    "Get-ChildItem ~/.claude/crew | % { Get-Content $_.FullName }",
                    "Get-ChildItem build | % { $_ } | % { Remove-Item $_ }"], top)
    assert not hit, _report(hit, "were refused")


# --- the tilde forms bash expands itself ----------------------------------------------------------------------------

def test_the_bash_tilde_forms_are_read(home, top):
    user = home.name
    commands = [verb.replace("{t}", target) for verb in BASH_VERBS for target in (
        f"~root/../{user}/.claude/crew/config.json", "~someone/.claude/crew/config.json",
        "~-/.claude/crew/config.json", "~other/.claude/crew/confirm-config/cc-ab12.json")]
    commands += ["cd ~; " + verb.replace("{t}", "~+/.claude/crew/config.json") for verb in BASH_VERBS]
    commands += ["cd ~/.claude && " + verb.replace("{t}", "~+/crew/config.json") for verb in BASH_VERBS]
    commands.append(NAMED + "echo x > $D/../config.json")
    slipped = _slipped(commands, top)
    assert not slipped, _report(slipped, "were not refused")
    hit = _hit_by(["echo x > ~someone/notes/out.txt", "cd /tmp/x; echo x > ~+/.claude/crew/config.json",
                   "cat ~someone/.claude/crew/config.json", "rm '~$report.docx'", "echo x > ~+/out.txt"], top)
    assert not hit, _report(hit, "were refused")


# --- a path built from pieces: refused without the command naming the owner's folder --------------------------------

PIECES = (
    "Set-Content -Path (Join-Path $HOME \".claude\" \"crew\" \"config.json\") -Value x",
    "Set-Content ([IO.Path]::Combine($HOME, '.claude', 'crew', 'config.json')) x",
    "Remove-Item (Join-Path (Join-Path $HOME .claude) crew)",
    "$p = [IO.Path]::Combine($HOME, \".claude\", \"crew\", \"config.json\"); Set-Content $p x",
    "$d = Join-Path (Join-Path $HOME \".claude\") \"crew\"; Set-Content \"$d/config.json\" x",
    "P=$(cat ~/.claude/crew/where.txt); echo x > $P", "echo x > \"$(cat ~/.claude/crew/where.txt)\"",
    "echo x > `cat ~/.claude/crew/where.txt`", "echo x > \"`cat ~/.claude/crew/where.txt`\"",
    "cd $(cat ~/.claude/crew/where.txt); echo x > config.json", "cd $(cat ~/.claude/crew/where.txt); echo x > conf$N",
    "cd $(cat ~/.claude/crew/where.txt) && rm crew/config.json",
    "cd ~/.claude/crew; echo x > $F", "cd ~/.claude/crew/confirm-config; rm $F",
    "cd ~/.claude; cd crew; echo x > $F", "pushd ~/.claude; pushd crew; Set-Content $F x",
    "cd ~/.claude/crew; Set-Content (Get-Name) x",
    "for f in a $(ls ~/.claude/crew); do rm $f; done",
)
PIECES_ELSEWHERE = (
    "Set-Content -Path (Join-Path $wt \".claude/x.json\") -Value hi",
    "Set-Content -Path (Join-Path $repo \"plugin/crew/README.md\") -Value x",
    "Set-Content -Path (Join-Path $root \".claude/rules/crew.md\") -Value $x",
    "Set-Content -Path (Join-Path $wt \".claude/worktrees/a/plugin/crew/x.py\") -Value x",
    "Set-Content -Path (Join-Path $HOME \".claude\" \"settings.json\") -Value x",
    "P=$(cat ~/.claude/settings.json); echo x > $P", "cd $(cat ~/.claude/where.txt); echo x > config.json",
    "cd $(cat ~/.claude/crew/where.txt); echo x > out.txt",
    "cd $(cat ~/.claude/crew/where.txt); cd /tmp/x; echo x > $F",
    "cd ~/.claude/crew/worktrees/repo/lane; echo x > $F", "cd ~/.claude; echo x > $F", "cd .claude && echo x > $F",
    "W=$(pwd)/.claude/worktrees/a; cd $W && echo x > f.txt",
    "cd $(git rev-parse --show-toplevel)/.claude/worktrees/x && cp a b",
)


def test_a_path_built_from_pieces_of_the_owners_fails_closed(home, top):
    slipped = _slipped(PIECES, top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_path_built_from_other_pieces_is_allowed(home, top):
    hit = _hit_by(PIECES_ELSEWHERE, top)
    assert not hit, _report(hit, "were refused")


# --- the overblocks round 9 introduced, and ordinary commands: the must-allow set ---------------------------------

# round 10's eight regressions against the 97fa35794 copy, word for word
ROUND_10_OVERBLOCKS = (
    "cd .claude && echo x > $F", "cd $D && cat ~/.claude/CLAUDE.md > out.txt",
    "W=$(pwd)/.claude/worktrees/a; cd $W && echo x > f.txt",
    "cd $(git rev-parse --show-toplevel)/.claude/worktrees/x && cp a b",
    "cd $WT; sed -i s/a/b/ plugin/crew/foo.py; cat ~/.claude/crew/config.json",
    "cat ~/.claude/crew/config.json > \"$OUT\"", "cat ~/.claude/crew/config.json | tee \"$OUT\"",
    "Set-Content -Path (Join-Path $wt \".claude/x.json\") -Value hi",
)
# what a lane runs all day: reads, ordinary writes, worktree commands (also under crew's own worktrees folder)
ORDINARY = (
    "git status", "git diff main...HEAD", "ls -la", "ls ~/.claude/crew", "cat ~/.claude/crew/config.json",
    "cat ~/.claude/crew/config.json | jq .", "grep -r foo plugin/", "python3 -m pytest plugin/crew/tests -q",
    "python3 scripts/check-marketplace.py", "git log --oneline -5", "echo hello", "echo hi > /tmp/a.txt", "cp a b",
    "rm -rf build", "npm test", "cd plugin/crew && ls", "cd $D && ls", "cd $D && echo hi > out.txt",
    "cd \"$(git rev-parse --show-toplevel)\" && python3 scripts/gate-runner.py", "echo $HOME",
    "X=$(date); echo $X > /tmp/x", "for f in *.py; do echo $f > /tmp/$f.out; done", "echo x > $TMPDIR/out",
    "echo x > \"$OUT\"", "tee $LOG <<< x", "cp a \"$BACKUP\"", "git commit -m \"touch .claude/settings.json\"",
    "gh pr view 774 --json headRefOid", "cat .claude/settings.json", "echo x > .claude/settings.local.json",
    "Get-Content $HOME\\.claude\\crew\\config.json", "Get-ChildItem | Where-Object { $_.Name -like \"a*\" }",
    "Set-Content $env:TEMP\\x.txt hi", "(Get-Content a.txt) | Set-Content b.txt", "Write-Output (Get-Date)",
    "echo `date` > /tmp/d", "ls `pwd`", "cat a | grep \"foo|bar\" | wc -l", "curl -s http://x -o /tmp/y",
    "git -C \"$REPO\" status", "sed -i s/a/b/ \"$FILE\"", "mkdir -p \"$D/sub\"",
    "printf \"%s\\n\" \"$X\" > \"$D/out.txt\"",
    "cd $WT && git commit -am x", "python3 -c \"print(1)\"", "bash -c \"echo hi\"", "pwsh -c \"Get-Date\"",
    "Remove-Item $env:TEMP\\foo -Recurse", "ls {H}\\.claude\\projects", "echo x > {H}\\.claude\\projects\\memory\\a.md",
    "cat C:\\tmp\\confirm-config\\echo.txt", "Get-Content C:\\tmp\\confirm-config\\echo.txt",
    "cd $D && grep -r foo ~/.claude/crew/config.json", "cd ~/.claude/projects && ls",
    "cd $D && python3 -m pytest .claude/x", "ls .claude/worktrees/foo", "cd .claude/worktrees/x && git status",
    "cd .claude/worktrees/x && echo hi > out.txt", "cd \"$WT\" && git diff -- .claude/",
    "for w in .claude/worktrees/*; do git -C $w status; done",
    "for w in .claude/worktrees/*; do echo $w > /tmp/$(basename $w); done",
    "git worktree add .claude/worktrees/a-$(date +%s) HEAD", "mkdir -p .claude/worktrees/\"$N\"",
    "cp -r \"$SRC\" .claude/worktrees/x/", "rm -rf .claude/worktrees/\"$N\"", "rm -rf \"$WT/.claude/worktrees/$N\"",
    "echo x > \"$WT/.claude/settings.local.json\"", "echo x > $REPO/.claude/crew/state.json",
    "Set-Content \"$wt\\.claude\\x.json\" hi", "Get-ChildItem .claude | ForEach-Object { Set-Content $_.FullName x }",
    "ls \"{H}\\.claude\\crew\" | ForEach-Object { Write-Output $_ }",
    # crew's own worktrees live under the owner's folder: a checkout there is an ordinary checkout
    "cd ~/.claude/crew/worktrees/repo/lane && git checkout main", "cd ~/.claude/crew/worktrees/repo/lane && git stash",
    "cd ~/.claude/crew/worktrees/repo/lane && git pull --rebase",
    "cd ~/.claude/crew/worktrees/repo/lane && echo x > $F",
    "cd ~/.claude/crew/worktrees/repo/lane && patch -p1 < a.patch", "cd ~/.claude/crew/worktrees/r/w && unzip a.zip",
    "cd ~/.claude/crew/worktrees/r/w && tar -xf a.tar", "cd ~/.claude/crew/worktrees/r/w && curl -sO http://x/y",
    "git -C ~/.claude/crew/worktrees/repo/lane checkout main", "rm -rf ~/.claude/crew/worktrees/repo/lane",
    "cd {H}/.claude/crew/worktrees/repo/lane && sed -i s/a/b/ config.json",
    "git worktree add ~/.claude/crew/worktrees/repo/lane-$(date +%s) HEAD",
    "cd ~/.claude/crew/worktrees/repo/lane; git ls-files -o | xargs rm",
    "cd ~/.claude/crew/worktrees/repo/lane; find . -name '*.pyc' -delete",
    # the round-10 verbs on ordinary files
    "timeout 5 bash -c \"echo hi > out.txt\"", "nice -n 10 make", "timeout 300 python3 -m pytest -q", "stdbuf -oL make",
    "echo x | Tee-Object out.txt", "Get-Process | Export-Csv out.csv", "sed -n \"w out.txt\" a", "iex \"Get-Date\"",
    "cd /d C:\\repos && echo x > config.json", "echo \"ls\" | bash", "trap 'rm -f \"$tmp\"' EXIT",
    "sed s/wow/now/ a > b", "sed -n '/crew\\/config.json/p' notes.txt",
    "awk '$3 > 5 {print}' ~/.claude/crew/config.json",
    "awk '{print $1}' ~/.claude/crew/config.json", "sed s/a/b/ ~/.claude/crew/config.json > out.txt",
    "alias ll='ls -la'; ll ~/.claude/crew", "Set-Alias g git; g status", "$x = 1; Set-Content out.txt $x",
    "alias ls='ls --color'; ls ~/.claude/crew", "ls | xargs", "ls ~/.claude/crew | xargs -n 1",
    "git add .claude/settings.json plugin/crew/README.md && echo ok > \"$OUT\"",
    "cat ~/.claude/crew/config.json | sort",
    "Get-Content ~/.claude/crew/config.json | Measure-Object -Line", "ls ~/.claude/crew | wc -l",
    "for d in build dist; do rm -rf $d; done",
    "for i in 1 2 3; do echo $i > /tmp/$i.txt; done", "ls | while read f; do echo \"$f\" > /tmp/names; done",
    "cat ~/.claude/crew/config.json | while read line; do echo \"$line\"; done",
    "wsl -e ls", "busybox ls ~/.claude/crew", ". ./env.sh; make", "bash <<< \"echo hi\"",
    "Start-Process pwsh -ArgumentList \"-c Get-Date\"", "$sb = [scriptblock]::Create(\"Get-Date\"); & $sb",
    "cat ~/.claude/crew/config.json | jq .guards > \"$OUT\"", "cp ~/.claude/crew/config.json \"$BACKUP\"",
    "Copy-Item ~/.claude/crew/config.json (Join-Path $PWD 'c.json')", "nice python verify_trust.py status",
)


def test_the_round_10_overblocks_are_allowed_again(home, top):
    hit = _hit_by(ROUND_10_OVERBLOCKS, top)
    assert not hit, _report(hit, "of the eight round-10 regressions are still refused")


def test_ordinary_read_only_and_worktree_commands_are_allowed(home, top):
    hit = _hit_by([command.replace("{H}", str(home)) for command in ORDINARY], top)
    assert not hit, _report(hit, "ordinary commands were refused")


# --- the confirm-config store check: a write VERB, in command position ------------------------------------------

STORE_READS = (
    "grep echo {s}/x.json", "rg printf {s}/", "cat {s}/x.json | grep echo", "Select-String echo {s}/x.json",
    "ls {s}/ | grep sed", "git log --grep=install -- {s}/", "grep -c sed {s}/cc-ab12.json",
    "Get-Content {s}/x.json | Select-String printf", "ls {s}/ | sort | grep -v tee",
    "diff {s}/a.json {s}/b.json | grep rm",
    "findstr echo {s}/x.json", "cat {s}/x.json | grep -E \"cp|mv|rm\"", "grep -rn \"python3\" {s}/",
    "Get-ChildItem {s}/ | Where-Object { $_.Name -match \"touch\" }", "pwsh -c Get-Content {s}/echo",
    "bash -c \"grep rm {s}/x.json\"",
)
STORE_WRITES = (
    "find {s}/ -name x -exec rm {} +", "ls {s}/ | xargs rm", "ls {s}/ | xargs -n 1 rm -f", "sudo rm {s}/f",
    "env A=1 rm {s}/f", "timeout 5 rm {s}/f", "nice -n 5 cp a {s}/f", "bash -c \"rm {s}/f\"", "sh -c 'touch {s}/f'",
    "if true; then rm {s}/f; fi", "Get-ChildItem {s}/ | ForEach-Object { Remove-Item $_ }", "ls {s}/$(rm {s}/x)",
    "cat \"$(rm {s}/f)\"",
    "nice python3 x.py {s}/f", "cmd /c \"echo x {s}/f\"", "eval \"touch {s}/f\"", "bash <<EOF\nrm {s}/f\nEOF",
    "A=1 rm {s}/f", "! rm {s}/f", "ls {s}/f; {rm,{s}/x}", "pwsh -Command \"Remove-Item {s}/f\"",
    "pwsh -c \"echo x {s}/f\"",
)


def test_a_search_term_beside_the_store_is_not_a_write(home, top):
    stores = ("~/.claude/crew/confirm-config", "/tmp/confirm-config", "C:\\tmp\\confirm-config")
    hit = _hit_by([read.replace("{s}", store) for store in stores for read in STORE_READS], top)
    assert not hit, _report(hit, "reads beside the store were refused")


def test_a_write_verb_in_command_position_beside_the_store_is_refused(home, top):
    # a store that is NOT the owner's real one, so only the string check can refuse
    slipped = _slipped([write.replace("{s}", "/tmp/confirm-config") for write in STORE_WRITES], top)
    assert not slipped, _report(slipped, "were not refused")


# --- single cases the mutations in sabotage_guards_master.py need a test for ---------------------------------------

def test_a_lone_slash_d_is_a_folder(home, top):
    """`cd /d` with nothing after it is Git Bash's drive D:, not cmd's switch with the folder left out."""
    hit = _hit_by(["cd /d && echo x > .claude/crew/config.json", "cd /d; rm -rf .claude"], top or "/tmp/x")
    assert not hit, _report(hit, "were refused")


def test_a_taint_is_carried_from_variable_to_variable(home, top):
    built = "$d = [IO.Path]::Combine($HOME, \".claude\", \"crew\")"
    slipped = _slipped([f"{built}; $p = Join-Path $d \"config.json\"; Set-Content $p x",
                        f"{built}; $p = $d + \"\\config.json\"; Remove-Item $p",
                        "D=$(cat ~/.claude/crew/where.txt); P=$D/config.json; echo x > $P"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_an_assignment_before_a_read_still_names_the_folder(home, top):
    """Only the OPERANDS of a read are left out of what the command says; what stands before it is still said."""
    assert scope_guard.shell_refusal("D=~/.claude/crew cat x; echo y > $F", None, top)
    assert scope_guard.shell_refusal("sudo -u x cat ~/.claude/crew/config.json; echo y > $F", None, top) is None


def test_a_find_iname_narrows_like_a_name(home, top):
    hit = _hit_by(["find ~/.claude -iname '*.LOG' -delete", "find ~ -iname '*.Pyc' -exec rm {} +"], top)
    assert not hit, _report(hit, "were refused")
    slipped = _slipped(["find ~/.claude -iname 'CONFIG.json' -delete"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_xargs_hands_a_writer_what_the_pipe_names(home, top):
    slipped = _slipped(["echo ~/.claude/crew/config.json | xargs tee",
                        "echo ~/.claude/crew/config.json | xargs -n 1 truncate -s 0",
                        "ls ~/.claude/crew/confirm-config/cc-ab12.json | xargs sponge"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_pipe_of_both_streams_is_a_pipe(home, top):
    slipped = _slipped(["echo ~/.claude/crew/config.json |& xargs rm",
                        "ls ~/.claude/crew/config.json |& xargs rm -f"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_substitution_inside_a_pipeline_does_not_cut_it(home, top):
    """A `$(...)` in the command a pipe feeds is read as commands of its own; the pipeline it stands in is kept."""
    slipped = _slipped(["echo ~/.claude/crew/config.json | xargs rm $(echo -f)",
                        "Get-Item ~/.claude/crew/config.json | Remove-Item -Force:$(Get-Flag)"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_only_a_shell_reads_the_pipe_as_a_script(home, top):
    hit = _hit_by(["echo \"rm ~/.claude/crew/config.json\" | cat",
                   "echo \"echo x > ~/.claude/crew/config.json\" | grep x",
                   "echo \"Set-Content ~/.claude/crew/config.json x\" | tee notes.txt",
                   "echo \"rm ~/.claude/crew/config.json\" | Select-String rm"], top)
    assert not hit, _report(hit, "were refused")


def test_read_is_fed_by_a_here_string_too(home, top):
    slipped = _slipped(["read f <<< $(ls ~/.claude/crew/config.json); echo x > $f",
                        "read -r f <<< \"$(ls ~/.claude/crew/config.json)\"; rm \"$f\""], top)
    assert not slipped, _report(slipped, "were not refused")
    hit = _hit_by(["read f <<< $(ls build/out.txt); echo x > $f", "read f <<< hello; echo x > $f"], top)
    assert not hit, _report(hit, "were refused")


# --- the trust check keeps its own wrappers -----------------------------------------------------------------------

def test_the_trust_check_still_reads_past_nice(home, top):
    """Until crew 1.3.151 the owner-file check's wrapper set carried the name of the trust check's and replaced it,
    so `nice` was no wrapper there. The two sets are apart again: the trust check reads past its own wrappers, as on
    main, and not past the owner-file check's (a dot call, `start`, `call`)."""
    for command in ("nice /tmp/x approve", "nice -n 5 /tmp/x revoke", "env A=1 /tmp/x approve"):
        assert scope_guard.shell_refusal(command, None, top), command
    for command in ("nice python3 verify_trust.py status", ". ./env.sh approve", "start ./tool.cmd approve"):
        assert scope_guard.shell_refusal(command, None, top) is None, command


# --- the tail: what the guard does NOT read (CONFIG.md, "The guards master switch") ---------------------------------

def test_the_documented_tail_is_not_read(home, top):
    """Stated, not wished away: these still reach the owner's file. A guardrail against an accident, not a boundary.
    A case that starts being refused belongs in the must-block lists, and out of CONFIG.md's list."""
    tail = ("$a = @{Path=\"$HOME/.claude/crew/config.json\"}; Set-Content @a -Value x",
            "bash script.sh", "python3 helper.py", "pwsh -File x.ps1", "pwsh -EncodedCommand cwBjACAAeAA=",
            "touch ~/.claude/crew/config.json", "chmod 600 ~/.claude/crew/config.json",
            "iex (\"sc ~/.claude/cr\" + \"ew/config.json x\")", "gtee ~/.claude/crew/config.json",
            "git config --file ~/.claude/crew/config.json a b", "scp host:a ~/.claude/crew/config.json",
            "(New-Object IO.StreamWriter(\"$HOME/.claude/crew/config.json\")).Write(\"x\")",
            "python3 -c \"import os;os.system('echo x > ~/.claude/crew/config.json')\"",
            "cmd /v:on /c \"set P=%USERPROFILE%\\.claude\\crew\\config.json&&echo x > !P!\"",
            "ln -s ~/.claude/crew /tmp/l; echo x > /tmp/l/config.json", "cat list.txt | xargs rm",
            # round 11: named by the review, left to the tail
            "yq -i '.guards.enabled = false' ~/.claude/crew/config.json",
            "[IO.Directory]::Delete(\"$HOME/.claude/crew/confirm-config\", $true)",
            "[System.IO.Directory]::Delete(\"$HOME/.claude/crew\", $true)",
            "attrib +r ~/.claude/crew/config.json", "icacls ~/.claude/crew/config.json /grant x:F",
            "zip ~/.claude/crew/config.json src", "uniq in ~/.claude/crew/config.json",
            "find . -exec python3 helper.py {} +")
    for command in tail:
        assert scope_guard._owner_command_refusal(command, top) is None, command  # pylint: disable=protected-access


# =====================================================================================================================
# Round 11 (crew 1.3.151): the bundled options of the archive and download tools, the store rule judged by its
# target, and a `cd` that ends with its subshell or its `popd`. As in round 10, every case runs with and without
# `top`.
# =====================================================================================================================

R11_TARGETS = ("{h}/.claude/crew/config.json", "{h}/.claude/crew/confirm-config/cc-ab12.json",
               "{h}/.claude/crew/CONFIG.JSON")
R11_ELSEWHERE = ("/tmp/out.bin", "{h}/.claude/crew/other.json", "{h}/repo/.claude/crew/config.json",
                 "{h}/.claude/crew/worktrees/repo/lane/config.json")
R11_FOLDERS = ("~/.claude/crew", "$HOME/.claude/crew", "~/.claude/crew/confirm-config")

# --- FIX 1: tar, however its options are bundled -------------------------------------------------------------------

TAR_WRITES = (
    "tar -cf {t} src", "tar -czf {t} src", "tar cf {t} src", "tar czf {t} src", "tar -rf {t} src", "tar rf {t} src",
    "tar -uf {t} src", "tar -cvzf {t} src", "tar -c -z -f {t} src", "tar -cf{t} src", "tar --create --file={t} src",
    "tar --append --file {t} src", "tar --update -f {t} src", "tar -Af {t} other.tar", "tar --delete -f {t} member",
    "bsdtar -cf {t} src", "tar -cC src -f {t} .", "tar cfC {t} src .", "tar cbf 20 {t} src", "tar -f {t} --create src",
    "tar -czvf {t} -C src .",
)
TAR_EXTRACTS = (
    "tar -xC {d} -f a.tar", "tar -xzf a.tgz -C {d}", "tar xfC a.tar {d}", "tar -xf a.tar --directory={d}",
    "tar --extract --file a.tar --directory {d}", "tar -C {d} -xf a.tar", "tar -xzC {d} -f a.tgz",
    "tar -xC{d} -f a.tar",
    "tar xzfC a.tgz {d}", "tar --get -f a.tar -C {d}",
)
TAR_READS = (
    "tar -tf ~/.claude/crew/config.json", "tar tf ~/.claude/crew/config.json",
    "tar -xf ~/.claude/crew/config.json -C /tmp/x", "tar -cf /tmp/a.tar ~/.claude/crew/config.json",
    "tar czf backup.tgz ~/.claude/crew", "tar -cf out.tar -C ~/.claude/crew config.json", "tar -xf a.tar -C build",
    "tar xfC a.tar /tmp/x", "tar -df ~/.claude/crew/config.json", "tar --list --file ~/.claude/crew/config.json",
    "tar -cf /tmp/a.tar -T ~/.claude/crew/config.json", "tar -cXf ~/.claude/crew/config.json /tmp/a.tar src",
)


def test_a_tar_archive_written_as_the_owners_file_is_refused_however_bundled(home, top):
    slipped = _slipped(_spelled(TAR_WRITES, R11_TARGETS), top)
    slipped += _slipped([verb.replace("{d}", folder) for folder in R11_FOLDERS for verb in TAR_EXTRACTS], top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_tar_that_reads_the_owners_file_or_writes_elsewhere_is_allowed(home, top):
    hit = _hit_by(_spelled(TAR_WRITES, R11_ELSEWHERE, ("~",)), top)
    hit += _hit_by([verb.replace("{d}", folder) for folder in ("build", "/tmp/x", "~/.claude/projects")
                    for verb in TAR_EXTRACTS], top)
    hit += _hit_by(TAR_READS, top)
    assert not hit, _report(hit, "were refused")


# --- FIX 2 and 3: a value at the end of a bundle of short flags (`wget -qO`, `sort -uo`) -----------------------------

BUNDLED_WRITES = (
    "wget -qO {t} http://x", "wget -qO{t} http://x", "wget -nvO {t} http://x", "wget -q -O {t} http://x",
    "wget -cqO {t} http://x", "wget http://x -qO {t}",
    "sort -o {t} in", "sort in -o {t}", "sort -uo {t} in", "sort -o{t} in", "sort --output={t} in",
    "sort --output {t} in", "sort -u --out={t} in", "sort -nro {t} in", "cat in | sort -o {t}",
)
BUNDLED_READS = (
    "sort ~/.claude/crew/config.json", "sort -o /tmp/sorted ~/.claude/crew/config.json",
    "sort ~/.claude/crew/config.json > /tmp/x", "sort -to ~/.claude/crew/config.json",   # -t o: a separator
    "sort -k 2 ~/.claude/crew/config.json -o out.txt", "sort -u ~/.claude/crew/config.json | head",
    "wget -qO /tmp/x http://x", "wget -qO - http://x | cat", "wget -q http://x",
    "cat ~/.claude/crew/config.json | sort --output=/tmp/sorted",
)


def test_an_output_option_at_the_end_of_a_bundle_is_read(home, top):
    slipped = _slipped(_spelled(BUNDLED_WRITES, R11_TARGETS), top)
    slipped += _slipped(["wget -qP ~/.claude/crew http://x/config.json", "wget -qP ~/.claude/crew/ http://x/a"], top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_bundle_that_writes_elsewhere_or_only_reads_is_allowed(home, top):
    hit = _hit_by(_spelled(BUNDLED_WRITES, R11_ELSEWHERE, ("~",)) + list(BUNDLED_READS), top)
    assert not hit, _report(hit, "were refused")


# --- FIX 4: the archive a tool creates ------------------------------------------------------------------------------

ARCHIVE_WRITES = (
    "7z a {t} src", "7z u {t} src", "7za a {t} src", "7z a -tzip {t} src", "7zz a {t} src", "7z d {t} member",
    "7z.exe a {t} src", "7z a -mx9 {t} src more",
    "Compress-Archive -Path x -DestinationPath {t}", "Compress-Archive x {t}",
    "Compress-Archive -DestinationPath {t} -Path x", "Compress-Archive -Path a, b -DestinationPath {t}",
    "Compress-Archive a, b {t}", "Compress-Archive -Path x {t}", "Compress-Archive -Path a, b {t}",
    "Compress-Archive x -Dest {t} -Force",
    "Compress-Archive -LiteralPath x -DestinationPath:{t}", "Compress-Archive x {t} -Update",
    "Compress-Archive -Force x {t}", "Compress-Archive -CompressionLevel Fastest x {t}",
    "Get-ChildItem src | Compress-Archive -DestinationPath {t}",
    "git archive --output={t} HEAD", "git archive -o {t} HEAD", "git archive --format=zip --output {t} HEAD",
    "git -C repo archive -o {t} HEAD",
)
ARCHIVE_READS = (
    "7z x ~/.claude/crew/config.json -o/tmp/out", "7z l ~/.claude/crew/config.json", "7z t ~/.claude/crew/config.json",
    "7z a /tmp/a.7z ~/.claude/crew/config.json", "Compress-Archive ~/.claude/crew/config.json /tmp/a.zip",
    "Compress-Archive -Path ~/.claude/crew/config.json -DestinationPath out.zip",
    "Compress-Archive -Path ~/.claude/crew/config.json out.zip",
    "Compress-Archive ~/.claude/crew/config.json, b out.zip",
    "git archive -o /tmp/a.zip HEAD", "git archive HEAD | tar -x -C /tmp/x", "git archive --output=out.zip HEAD",
)


def test_an_archive_created_as_the_owners_file_is_refused(home, top):
    slipped = _slipped(_spelled(ARCHIVE_WRITES, R11_TARGETS, ("~", "$HOME", "$env:USERPROFILE")), top)
    assert not slipped, _report(slipped, "were not refused")


def test_an_archive_created_elsewhere_or_from_the_owners_file_is_allowed(home, top):
    hit = _hit_by(_spelled(ARCHIVE_WRITES, R11_ELSEWHERE, ("~",)) + list(ARCHIVE_READS), top)
    assert not hit, _report(hit, "were refused")


# --- FIX 5: `find -exec <command>`, `env -C <folder>`, `fsutil file createNew` --------------------------------------

EXTRA_WRITES = (
    "find . -exec cp x {t} \\;", "find . -exec cp x {t} ;", "find . -name '*.txt' -exec cp {} {t} \\;",
    "find /tmp -exec sh -c 'echo x > {t}' \\;", "find . -execdir rm {t} +", "find . -name x -exec mv {} {t} \\;",
    "find . -type f -ok tee {t} \\;", "find . -name a -exec rm -f {t} \\; -print",
    "fsutil file createNew {t} 10", "fsutil file createnew {t} 0", "fsutil.exe file createNew {t} 10",
    # the second `-exec` of one find, after the escaped `;` that ends the first
    "find . -name a -exec true \\; -exec rm -f {t} \\;", "find . -exec true \\; -o -name b -exec cp x {t} \\;",
    # wget's log file
    "wget -o {t} http://x", "wget --output-file={t} http://x", "wget -a {t} http://x",
    "wget -q --append-output {t} http://x",
)
EXTRA_READS = (
    "find . -exec cat ~/.claude/crew/config.json \\;", "find . -name '*.py' -exec grep -l crew {} +",
    "find . -exec cp ~/.claude/crew/config.json /tmp/y \\;", "find . -name x -exec rm {} \\; -print",
    "fsutil file layout ~/.claude/crew/config.json", "fsutil fsinfo volumeinfo C:",
    "find . -name a -exec true \\; -exec cat ~/.claude/crew/config.json \\;", "wget -o /tmp/log http://x",
    "wget -i ~/.claude/crew/config.json -o wget.log", "-x ~/.claude/crew/config.json",
)
ENV_CHDIR = ("env -C {d} tee config.json", "env --chdir={d} tee config.json", "env --chdir {d} rm config.json",
             "env -C {d} sh -c 'echo x > config.json'", "env -u X -C {d} tee config.json",
             "env A=1 -C {d} truncate -s 0 config.json",
             # the folder is the child's for ALL of its commands, not only the first
             "env -C {d} sh -c 'ls; echo x > config.json'", "env -C {d} bash -c 'true && rm config.json'")
ENV_ELSEWHERE = (
    "env -C ~/.claude/crew ls; echo x > config.json", "env -C ~/.claude/crew ls && rm config.json",
    "env -C /tmp tee config.json", "env -C ~/.claude/crew cat config.json > out.json",
    "env --chdir=~/.claude/crew cat config.json | tee /tmp/copy.json", "env -C build tee config.json",
    "env -C ~/.claude/crew/worktrees/repo/lane tee config.json",
)


def test_the_round_11_extras_are_refused(home, top):
    slipped = _slipped(_spelled(EXTRA_WRITES, R11_TARGETS), top)
    slipped += _slipped([verb.replace("{d}", folder) for folder in ("~/.claude/crew", "$HOME/.claude/crew")
                         for verb in ENV_CHDIR], top)
    assert not slipped, _report(slipped, "were not refused")


def test_the_round_11_extras_elsewhere_are_allowed(home, top):
    hit = _hit_by(_spelled(EXTRA_WRITES, R11_ELSEWHERE, ("~",)) + list(EXTRA_READS + ENV_ELSEWHERE), top)
    assert not hit, _report(hit, "were refused")


# --- FIX 6: the store rule judges where the command writes, not that it writes ----------------------------------------

R11_STORES = ("~/.claude/crew/confirm-config", "/tmp/confirm-config", "C:/tmp/confirm-config",
              "C:\\tmp\\confirm-config")
# a read of the store beside a write that lands somewhere the guard can resolve
STORE_READ_WRITE_ELSEWHERE = (
    "cp {s}/cc-ab12.json /tmp/", "cat {s}/cc-ab12.json | jq .x > /tmp/x", "ls {s}/cc-ab12.json && echo ok > /tmp/ok",
    "grep -c x {s}/cc-ab12.json > /tmp/out.txt", "Copy-Item {s}/cc-ab12.json -Destination C:/tmp/x.json",
    "Get-Content {s}/cc-ab12.json | Set-Content C:/tmp/x.json", "cat {s}/cc-ab12.json | tee /tmp/copy.json",
    "tar -cf /tmp/receipts.tar {s}/", "diff {s}/a.json {s}/b.json > /tmp/d.txt", "rsync -a {s}/ /tmp/backup/",
    "ls {s}/ | wc -l > /tmp/count.txt", "cat {s}/cc-ab12.json >> ~/notes.txt", "ls {s}/; rm /tmp/scratch.txt",
    "ls {s}/$(rm /tmp/x)", "cp {s}/cc-ab12.json ~/backup/", "ls {s}/; mkdir /tmp/new && touch /tmp/new/f",
    "test -f {s}/cc-ab12.json && echo yes", "ls {s}/ 2> /tmp/err.txt",
)
# the same with a RELATIVE target: a file of the working directory, where one is known
STORE_READ_WRITE_RELATIVE = (
    "cp {s}/cc-ab12.json out.json", "cat {s}/cc-ab12.json | jq .x > x.json", "ls {s}/ > listing.txt",
    "ls {s}/f; {rm,x}", "ls {s}/$(rm x)", "cat {s}/x | tee y", "cd build && cat {s}/x.json > copy.json",
)
STORE_TARGETED = (
    "cp /tmp/a {s}/cc-ab12.json", "echo x > {s}/cc-ab12.json", "cat a >> {s}/x.json", "rm {s}/cc-ab12.json",
    "rm -rf {s}/", "mv {s}/cc-ab12.json /tmp/", "cp a {s}/", "tee {s}/x.json < a", "cat {s}/a.json | tee {s}/b.json",
    "sed -i s/a/b/ {s}/cc-ab12.json", "cd {s}/ && rm cc-ab12.json", "cd {s}/ && echo x > cc-new.json",
    "truncate -s 0 {s}/cc-ab12.json", "Set-Content {s}/cc-ab12.json x", "Remove-Item {s}/cc-ab12.json",
    "ls {s}/ > $OUT", "cat {s}/x.json > \"$(mktemp)\"", "cp {s}/x.json $DEST", "ls {s}/ | tee \"$LOG\"",
    "cd {s}/ && unzip -o a.zip > /tmp/unzip.log", "(cd {s}/ && rm cc-ab12.json)", "pushd {s}/; rm cc-ab12.json; popd",
    "cp /tmp/a {s}/cc-ab12.json; echo done > /tmp/ok", "ls {s}/ > /tmp/a; echo x > {s}/cc-ab12.json",
    "echo x {s}/f", "touch {s}/f", "mkdir {s}/sub", "python3 tool.py {s}/f",
    "(Set-Location {s}/); Remove-Item cc-ab12.json",
)


def _stores(commands):
    return [command.replace("{s}", store) for store in R11_STORES for command in commands]


def test_a_read_of_the_store_beside_a_write_elsewhere_is_allowed(home, top):
    """#679's test only asks that writes are refused; this is the other half. Until round 11 the store rule refused
    every one of these: a write verb or a redirect ANYWHERE in a command that names the store."""
    hit = _hit_by(_stores(STORE_READ_WRITE_ELSEWHERE), top)
    assert not hit, _report(hit, "reads of the store were refused for a write that lands elsewhere")


def test_a_relative_write_beside_a_read_of_the_store_is_a_file_of_the_working_directory(home, top):
    """With a working directory (the real hook always has one) a relative target is a file there. With none, it is
    a target nobody can resolve, and the rule fails closed as it did before round 11."""
    if top is None:
        slipped = _slipped(_stores(c for c in STORE_READ_WRITE_RELATIVE if not c.startswith("cd ")), top)
        assert not slipped, _report(slipped, "relative writes from an unknown folder were not refused")
    else:
        hit = _hit_by(_stores(STORE_READ_WRITE_RELATIVE), top)
        assert not hit, _report(hit, "relative writes into the working directory were refused")


def test_a_write_aimed_at_the_store_is_refused(home, top):
    slipped = _slipped(_stores(STORE_TARGETED), top)
    assert not slipped, _report(slipped, "writes to the store were not refused")


def test_a_store_spelled_relatively_keeps_a_relative_target_refused(home, top):
    """`ls confirm-config/ > x` stands beside the store, in the owner's folder: #679's verdict, kept whatever the
    working directory is. A target that resolves elsewhere is still elsewhere."""
    slipped = _slipped(["ls confirm-config/ > x", "cat confirm-config/cc-ab12.json | tee copy.json",
                        "ls ./confirm-config/ > x", "ls $D/confirm-config/ > x",
                        "cp confirm-config/a.json b.json"], top)
    assert not slipped, _report(slipped, "were not refused")
    hit = _hit_by(["ls confirm-config/ > /tmp/x", "cp confirm-config/a.json /tmp/", "ls confirm-config/"], top)
    assert not hit, _report(hit, "were refused")


# --- FIX 7: a `cd` ends with its subshell, a `pushd` with its `popd` --------------------------------------------------

CWD_RESTORED = (
    "(cd {d} && ls); echo x > config.json", "(cd {d}; ls)\necho x > config.json", "(cd {d} && ls) && rm config.json",
    "( cd {d}; ls; ); echo x > config.json", "pushd {d} && ls && popd && echo b > config.json",
    "pushd {d}; ls; popd; rm config.json", "Push-Location {d}; Get-ChildItem; Pop-Location; Set-Content config.json x",
    "pushd {d} && pushd /tmp && popd && popd && echo x > config.json",
    "(cd {d} && (cd confirm-config && ls)); echo x > config.json", "(cd {d} && ls) > /tmp/out.txt; rm config.json",
    "(cd {d} && ls | wc -l); cp a config.json", "pushd {d} > /dev/null && ls && popd > /dev/null && rm config.json",
    # a child process and a `$(...)` are subshells too
    "bash -c 'cd {d} && ls'; echo x > config.json", "echo $(cd {d} && pwd); echo x > config.json",
    "cmd /c \"cd /d {d} && dir\" & echo x > config.json", "sh <<EOF\ncd {d}\nls\nEOF\nrm config.json",
    "pwsh -c \"Set-Location {d}; Get-ChildItem\"; Set-Content config.json x",
    "Start-Process pwsh -ArgumentList \"-c cd {d}\"; Set-Content config.json x",
    "echo \"$(cd {d}; (cd confirm-config; ls))\"; rm config.json",
    "pushd {d}; bash -c 'popd'; popd; echo x > config.json",
    # a `case` pattern's `)` ends no subshell; the `)` after `esac` does
    "(cd {d}; case x in a) ls;; esac); echo x > config.json", "(cd {d}; pushd /tmp; ls); echo x > config.json",
)
CWD_STILL_THERE = (
    "(cd {d} && echo x > config.json)", "(cd {d}; rm config.json)", "pushd {d} && echo b > config.json && popd",
    "pushd {d} && pushd /tmp && popd && echo x > config.json", "(cd /tmp && ls); cd {d} && echo x > config.json",
    "cd {d} && (cd /tmp && ls); echo x > config.json", "Push-Location {d}; Set-Content config.json x; Pop-Location",
    "cd {d}; pushd /tmp; ls; popd; rm config.json", "(cd {d} && (cd /tmp && ls) && rm config.json)",
    "( cd {d}; ls; ); cd {d}; rm config.json",
    "bash -c 'cd {d} && echo x > config.json'", "eval \"cd {d}\"; echo x > config.json",
    "cd {d}; bash -c 'echo x > config.json'", "cd {d} && echo $(rm config.json)",
    "cd {d}; bash -c 'cd /tmp && ls'; rm config.json", "cd {d}; echo $(cd /tmp; ls) > config.json",
    "iex \"Set-Location {d}\"; Set-Content config.json x",
    # PowerShell's `( ... )` is an expression that runs in the shell itself: its Set-Location stays
    "(Set-Location {d}); Set-Content config.json x", "(cd {d}) ; Set-Content config.json x",
    "(Push-Location {d}); Set-Content config.json x", "(cd {d}); Get-ChildItem | Out-File config.json",
    # a `case` pattern's `)` is not the end of the subshell (or of anything) around it
    "(cd {d}; case x in a) echo x > config.json;; esac)",
    "pushd /tmp; cd {d}; case x in a) echo x > config.json;; esac",
    "cd {d}; case x in a) (cd /tmp; ls);; esac; echo x > config.json",
    "if true; then case x in a) cd {d};; esac; fi; echo x > config.json",
    # a subshell does not undo the `pushd` before it, and `env -C` around a child shell ends with that command
    "pushd {d}; (cd /tmp; ls); echo x > config.json", "pushd {d}; (popd); echo x > config.json",
    "cd {d}; env -C /tmp sh -c 'ls'; echo x > config.json",
)


def test_a_cd_inside_a_subshell_or_before_a_popd_does_not_leak(home, top):
    hit = _hit_by([command.replace("{d}", folder) for folder in ("~/.claude/crew", "$HOME/.claude/crew")
                   for command in CWD_RESTORED], top)
    hit += _hit_by(["case $x in a) ls;; esac; echo x > out.txt", "popd; echo x > config.json",
                    "popd && echo x > out.txt", "echo ~/.claude/crew; popd; echo x > out.txt"], top)
    assert not hit, _report(hit, "were refused")


def test_a_write_while_still_in_the_owners_folder_is_refused(home, top):
    slipped = _slipped([command.replace("{d}", folder) for folder in ("~/.claude/crew", "$HOME/.claude/crew")
                        for command in CWD_STILL_THERE], top)
    assert not slipped, _report(slipped, "were not refused")


def test_a_popd_with_nothing_to_go_back_to_fails_closed_only_beside_the_owners_folder(home, top):
    """`popd` with no `pushd` before it: the folder is one the guard cannot tell. A relative target that could be
    the owner's is refused there only in a command that names the owner's folder as something to write."""
    assert scope_guard.shell_refusal("echo ~/.claude/crew; popd; echo x > config.json", None, top)
    assert scope_guard.shell_refusal("popd; echo x > config.json", None, top) is None


# --- the fail-closed side of the tail: refused though it writes nothing (CONFIG.md) ---------------------------------

def test_a_whatif_delete_handed_the_owners_folder_fails_closed(home, top):
    """`-WhatIf` deletes nothing; the guard does not read it and refuses. Documented as an overblock, by design."""
    assert scope_guard.shell_refusal("Get-ChildItem ~/.claude/crew | Remove-Item -WhatIf", None, top)
