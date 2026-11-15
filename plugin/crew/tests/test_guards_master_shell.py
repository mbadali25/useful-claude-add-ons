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


# --- round 9: escape characters and paths the guard cannot resolve (crew 1.3.123) ------------------------------------
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
# the same, where the command names the owner's folder elsewhere and the target is only a variable or a substitution
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


def test_a_path_the_guard_cannot_resolve_is_refused_when_it_could_be_the_owners(home):
    slipped = []
    for shell_verbs, homes in ((BASH_VERBS, BASH_HOMES), (PS_VERBS, PS_HOMES), (CMD_VERBS, CMD_HOMES)):
        slipped += _unrefused(_cells(DYNAMIC, shell_verbs, ("~",)))
        slipped += _unrefused(_cells(DYNAMIC_IN_CONTEXT, [f"ls ~/.claude; {v}" for v in shell_verbs], homes[:1]))
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
    for command in ("cd $D; echo x > config.json; ls ~/.claude",
                    "cd $(pwd)/x && rm confirm-config/cc-ab.json; ls ~/.claude",
                    "Set-Location $env:UNSET; Set-Content config.json x; ls ~/.claude"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("cd $D; echo x > config.json", "cd /tmp/x; echo x > config.json; ls ~/.claude"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_an_unknown_folder_in_front_of_a_name_that_cannot_be_the_owners_is_allowed_in_context(home):
    verbs = [f"ls ~/.claude; {v}" for v in BASH_VERBS + PS_VERBS + CMD_VERBS if "{t}.bak" not in v]
    hit = _refused(_cells(UNKNOWN_FOLDER_OTHER_NAME, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a name that cannot be the owner's:\n" + "\n".join(hit[:60])


def test_an_escape_stripped_reading_of_a_windows_path_is_not_the_owners(home):
    """`C:\\proj\\out.txt` read with its backslashes taken out is a garbled relative word: from a folder a dynamic
    `cd` made unknown it is no more the owner's than the path as written."""
    targets = ("C:\\proj\\out.txt", "C:\\proj\\sub\\notes.md", "D:\\a\\b/.claude/crew/other.json")
    # only verbs whose one relative word is the target: `mv x {t}` also names `x`, which that cd made unknown
    verbs = [f"cd $D; ls ~/.claude; {v}" for v in (
        "echo x > {t}", "echo x >> {t}", "cat a > {t}", "printf x | tee {t}", "Set-Content {t} x",
        "Set-Content -Path {t} -Value x", "Add-Content {t} x", "Out-File {t}", "type x > {t}", "sc {t} x")]
    hit = _refused(_cells(targets, verbs, ("~",)))
    assert not hit, f"{len(hit)} cells refused a Windows path that is not the owner's:\n" + "\n".join(hit[:60])


def test_a_relative_target_with_an_unknown_part_after_a_dynamic_cd_is_unknown(home):
    for command in ("cd $D; echo x > sub/$N; ls ~/.claude", "cd $D; rm sub/$N.json; cat ~/.claude/crew/config.json"):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("cd /tmp/x; echo x > sub/$N; ls ~/.claude", "cd $D; echo x > sub/$N", "echo x > sub/$N"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access


def test_a_word_after_a_parenthesised_expression_is_a_plain_word(home):
    """Only what sits INSIDE the parentheses is an expression; the next word is read as written."""
    for command in ("Copy-Item (Get-Item ~/.claude/crew/config.json) out.txt",
                    "Set-Content (Join-Path $PWD 'a.txt') x; Set-Content out.txt y",
                    "Copy-Item -Path (Get-Item ~/.claude/crew/config.json) -Destination out.txt",
                    "Copy-Item (Get-Item ~/.claude/crew/config.json) -Destination out.txt"):
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
    for command in ("ls ~/.claude; X=/tmp/other; echo x > $X", "ls ~/.claude; X=/tmp/other; echo x > $X/config.json",
                    "ls ~/.claude; export X=/tmp/other; rm -f $X/crew/config.json",
                    "ls ~/.claude; $d = 'C:/other'; Set-Content $d/config.json x",
                    "ls ~/.claude; set X=/tmp/other & echo x > %X%/config.json"):
        assert scope_guard._owner_command_refusal(command) is None, command  # pylint: disable=protected-access
    for command in ("X=~/.claude/crew; echo x > $X/config.json", "$d = '~/.claude/crew'; Set-Content $d/config.json x",
                    "export X=~/.claude/crew/confirm-config; rm $X/cc-ab.json",
                    "ls ~/.claude; X=$(pwd); echo x > $X"):
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
    """The hint is `.claude`, the confirm-config store or `crew/config.json`, in what the command SAYS: a comment
    is not said, and an escape character or a quote does not hide it."""
    for command in ("ls ~/.claude; echo x > $D", "ls /tmp/confirm-config; echo x > $D",
                    "cat crew/config.json; echo x > $D", "ls ~/.cl\\aude; echo x > $D",
                    "ls ~/.cl`aude; echo x > $D", "ls ~/.cl^aude; echo x > $D", "ls ~/'.cl'aude; echo x > $D",
                    "ls ~/.claude; Set-Content $D x", "ls ~/.claude; echo x > \"$(cat p)\""):
        assert scope_guard._owner_command_refusal(command), command  # pylint: disable=protected-access
    for command in ("echo x > $D # ~/.claude/crew/config.json", "echo x > $D # confirm-config", "echo x > $D",
                    "ls ~/.claudefoo; echo x > $D", "ls ~/not-confirm-config; echo x > $D",
                    "ls ~/.claude.md; echo x > $D".replace(".claude.md", "claude-notes")):
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
    "ls /tmp/confirm-config/f; {rm,x}",
    "cat /tmp/confirm-config/x | tee y",
    "python3 -c pass /tmp/confirm-config/f",
])
def test_a_write_verb_beside_the_store_is_still_refused(command, home):
    assert scope_guard.shell_refusal(command, None), command
