"""crew 1.3.82: a DIFFERENTIAL test of `guards.git.allow`'s one reader
(`crew_gitallow.line_git_commands`) against the real shells (PR #769 review
round 5).

Five review rounds each found a line the reader read one way and bash or
PowerShell ran another. This test asks the shells themselves: every line of a
generated corpus that the allowlist ACCEPTS is run under real bash and real
PowerShell 7 with `git` replaced by a shim that only logs the argv it was
handed, and git must never get an argv the reader did not see (as a multiset
of git invocations per line, git exiting 0 and then 1 so both sides of every
`&&` / `||` run). A line the allowlist refuses is not run.

The corpus is command templates crossed with fragments: redirection and fd
forms (`>`, `>>`, `2>&1`, `>&-`, `<&-`, `n>&`, `{var}>`, an fd prefix before
the subcommand), quotes (`'..'`, `".."`, `$'..'`, `$".."`), expansions,
separators (`;`, `&`, `&&`, `||`, `|`, `|&`, newline, CR, tab, NBSP, a
fullwidth hyphen, zero-width characters, backslash-newline, `#`), config and
program options, wrappers (`time`, `env`, `command`, ...), and every repro of
review rounds 1-5 from `test_git_allow.py`. The default run is a fixed slice
of a few hundred lines; `--run-slow` runs the whole cross product and a
seeded random fuzz (fixed seed, so a failure reproduces).

Nothing real runs: the shim is the only `git` the shells can find, every line
runs in a throwaway directory, and no case installs anything or touches real
config. A shell this host does not have is a SKIP, never a pass: bash from
`crew_fixtures.resolve_bash`, PowerShell 7 from `resolve_pwsh`, and on Windows
the PowerShell shim is a native `git.exe` built with the .NET Framework's
`csc.exe` (skipped when there is none). That shim reads its argv the .NET
Framework's way, which matches git for Windows' own parsing for every word
the allowlist accepts (no embedded quotes or trailing backslashes reach it
unexamined) -- an approximation stated here rather than hidden.
"""
import json
import os
import pathlib
import random
import shutil
import stat
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_gitallow

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
_CSC = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / \
    "Framework64" / "v4.0.30319" / "csc.exe"

_US, _RS, _GS = "\x1f", "\x1e", "\x1d"

# --- the corpus -------------------------------------------------------------------------

TEMPLATES = [
    "git push {} origin main", "git push -f {} origin main", "git {} push origin main",
    "git rebase {} origin/main", "git fetch {} origin", "git grep {} foo",
    "git config {} user.name", "git init {} q", "git send-pack {} r main",
    "git status {}", "git {} status", "git commit -m x {}", "git -c user.name=x {} log -1",
    "git log -1 {}", "git -C sub {} status", "git commit -m 'a b' {} --allow-empty",
    "git {}"]
WRAPPERS = [
    "time git status {}", "nohup git status {}", "command git push {} o m",
    "env git status {}", "exec git status {}", "sudo git status {}", "xargs git {}",
    "bash -c 'git status {}'", "builtin git {}", "\\git status {}", "'git' status {}",
    "\"git\" push {} o m"]

BASH_FRAGMENTS = [
    # redirections and descriptors
    ">out", "> out", ">>out", "2>&1", "2>/dev/null", ">&-", "<&-", "3>&-", ">&2", "1>&2",
    ">&1-", "2>&-1", "0<&-", "9>out", "2 >out", "2>&1 >out", ">out 2>&1", ">&- -x",
    ">&---receive-pack=deploy-prod", ">& ---receive-pack=deploy-prod",
    "<&-\"--receive-pack=deploy-prod\"", "2>&---upload-pack=x", ">&-'--exec=x'",
    "{v}>out", "\"2\">out", "\\2>out", "2\\>out", "''2>out", ">|out", "&>out", "&>>out",
    "<in", "<>f", ">", ">&", "2>", ">&out", "<<<x", "<<<'--exec=x'", ">\"$X\"",
    # quotes
    "'a b'", "\"a b\"", "$'\\x2d-exec=x'", "$\"x\"", "\"--receive-pack=x\"", "'--exec=x'",
    "--re\"\"ceive-pack=x", "'--upload-pack'=x", "\"\\$X\"", "\\-\\-exec=x", "a\\ b",
    "\"a\\\"b\"",
    # expansions
    "$X", "${X}", "$(echo -x)", "`echo -y`", "{a,b}", "x*", "x?", "~", "~/x", "@{u}",
    "HEAD@{1}", "@{a,b}", "[ab]", "$((1+1))", "!x", "<(echo x)",
    # separators and characters
    "; git status", "&& git status", "|| git log", "| git status", "|& git log",
    "& git status", "\ngit status", "\r", "\t-x", "\u00a0-x", "\uff0dx", "\u200b-x",
    "\\\n--exec=x", "# --exec=x", ";", "&&", "|", ";; git x", "\\\n", "&",
    # config and program options
    "-c alias.p='!printf HIT'", "--exec-path=/tmp/x", "--receive-pack=x", "--rece=x",
    "--exec=x", "-x x", "--upload-pack=x", "-O", "--template=/t", "--config-env=a=b",
    "core.sshCommand x", "--get user.name", "-l", "-v", "--force-with-lease"]

PS_FRAGMENTS = [
    # redirections
    "2>&1", "*>&1", "> out.txt", ">> log.txt", "2>$null", "3>&1", "1>&2", ">", "2>",
    "2>err.txt", ">out.txt", "6>&1",
    # quotes
    "'a b'", "\"a b\"", "\"a`\"b\"", "'it''s'", "@'\nx\n'@", "\"$x\"", "`u{2d}-exec=x",
    "\u2018a\u2019", "\u201ca\u201d", "'--exec=x'", "\"--receive-pack=x\"",
    # expansions
    "$X", "$(1)", "@(1)", "(1)", "@a", "{x}", "[x]", "x*", "~", "%P%", "--%", "$env:X",
    # separators and characters
    "; git status", "&& git status", "|| git log", "| git status", "& git status",
    "\ngit status", "\r", "\t-x", "\u00a0-x", "\u2013x", "# --exec=x", "`\n-x", ";",
    # config and program options
    "-c alias.p='!printf HIT'", "--exec-path=/tmp/x", "--receive-pack=x", "--rece=x",
    "--exec=x", "-x x", "--upload-pack=x", "--template=/t", "-l", "-v",
    "--force-with-lease"]


def _repros():
    """Every bash / PowerShell repro of review rounds 1-5 in `test_git_allow.py`."""
    import test_git_allow as t  # pylint: disable=import-outside-toplevel
    bash, ps = [], []
    for name, value in vars(t).items():
        if not name.isupper() or not isinstance(value, (list, tuple, dict)):
            continue
        items = value.values() if isinstance(value, dict) else value
        for item in items:
            if isinstance(item, str):
                bash.append(item)
                ps.append(item)
            elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                command, shell = item
                if shell in ("bash", "Bash"):
                    bash.append(command)
                elif shell in ("powershell", "PowerShell"):
                    ps.append(command)
                elif command in ("Bash", "PowerShell") and isinstance(shell, str):
                    (bash if command == "Bash" else ps).append(shell)
    return bash, ps


def _cross(templates, fragments):
    return [t.format(f) for t in templates for f in fragments]


def _slice(templates, fragments):
    """A fixed, small slice: each fragment under two templates."""
    count = len(templates)
    out = []
    for index, fragment in enumerate(fragments):
        for pick in (index % count, (index * 7 + 3) % count):
            out.append(templates[pick].format(fragment))
    return out


def _fuzz(templates, fragments, count, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        pieces = [rng.choice(fragments) for _ in range(rng.randint(1, 3))]
        joiner = rng.choice((" ", " ", ""))
        out.append(rng.choice(templates).format(joiner.join(pieces)))
    return out


def corpus(shell, slow):
    bash_repros, ps_repros = _repros()
    if shell == "bash":
        fragments, repros = BASH_FRAGMENTS, bash_repros
    else:
        fragments, repros = PS_FRAGMENTS, ps_repros
    lines = list(repros) + _slice(TEMPLATES, fragments) + _slice(WRAPPERS, fragments[:12])
    if slow:
        lines += _cross(TEMPLATES + WRAPPERS, fragments)
        lines += _fuzz(TEMPLATES + WRAPPERS, fragments, 3000, seed=769)
    seen, out = set(), []
    for line in lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


# --- the shims and the drivers ----------------------------------------------------------

_SH_SHIM = ("#!/bin/sh\n"
            "rec=$(printf '%s\\037' \"$#\" \"$@\"; printf '\\036')\n"
            "printf '%s\\n' \"$rec\" >> \"$SHIMLOG\"\n"
            "exit \"${SHIMRC:-0}\"\n")

_BASH_DRIVER = r"""
SHIMDIR=$1; LOG=$2; LINES=$3
if command -v cygpath >/dev/null 2>&1; then
  SHIMDIR=$(cygpath -u "$SHIMDIR"); LOG=$(cygpath -u "$LOG"); LINES=$(cygpath -u "$LINES")
fi
export SHIMLOG="$LOG"
PATH="$SHIMDIR:$PATH"; hash -r
i=0
while IFS= read -r -d '' line; do
  printf '\035%d\n' "$i" >> "$SHIMLOG"
  ( eval "$line"
    wait ) </dev/null >/dev/null 2>&1
  i=$((i+1))
done < "$LINES"
"""

_CS_SHIM = r"""
using System; using System.IO; using System.Text;
class Shim { static void Main(string[] a) {
  var sb = new StringBuilder(); sb.Append(a.Length).Append('\x1f');
  foreach (var s in a) { sb.Append(s).Append('\x1f'); }
  sb.Append('\x1e').Append('\n');
  File.AppendAllText(Environment.GetEnvironmentVariable("SHIMLOG"), sb.ToString(),
                     new UTF8Encoding(false));
  Environment.Exit(Environment.GetEnvironmentVariable("SHIMRC") == "1" ? 1 : 0);
} }
"""

_PS_DRIVER = r"""
param([string]$ShimDir, [string]$Log, [string]$LinesFile)
$env:SHIMLOG = $Log
$env:PATH = $ShimDir + [IO.Path]::PathSeparator + $env:PATH
$lines = [IO.File]::ReadAllText($LinesFile) | ConvertFrom-Json
$i = 0
foreach ($line in $lines) {
  [IO.File]::AppendAllText($Log, [string][char]0x1d + "$i`n")
  try { $null = Invoke-Expression $line *>&1 } catch { }
  $i++
}
"""


def _write(path, text):
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture(name="shim_dir", scope="module")
def _shim_dir(tmp_path_factory):
    where = tmp_path_factory.mktemp("gitshim")
    shim = where / "git"
    _write(shim, _SH_SHIM)
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return where


def _ps_shim_dir(base):
    """The directory holding a `git` PowerShell will run, or None (skip)."""
    if sys.platform != "win32":
        return base
    if not _CSC.is_file():
        return None
    where = base / "win"
    where.mkdir(exist_ok=True)
    exe = where / "git.exe"
    if not exe.is_file():
        source = where / "shim.cs"
        _write(source, _CS_SHIM)
        proc = subprocess.run([str(_CSC), "/nologo", f"/out:{exe}", str(source)],
                              capture_output=True, text=True, check=False, timeout=120)
        if proc.returncode != 0 or not exe.is_file():
            return None
    return where


def _parse(log, count):
    """Per input line, the sorted list of argv lists the shim logged."""
    out = [[] for _ in range(count)]
    if not log.is_file():
        return out, set()
    seen = set()
    for chunk in log.read_bytes().decode("utf-8", "surrogateescape").split(_GS)[1:]:
        head, _, body = chunk.partition("\n")
        index = int(head)
        seen.add(index)
        for record in body.split(_RS + "\n"):
            if not record.strip("\n"):
                continue
            fields = record.split(_US)
            argc = int(fields[0])
            out[index].append(fields[1:1 + argc])
    return [sorted(item) for item in out], seen


def _fresh(work):
    if os.path.exists(work):
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "sub").mkdir()


def run_bash(lines, shim_dir, work, rc=0):
    """Per line, the sorted argv lists bash handed the shim (exiting `rc`)."""
    _fresh(work)
    listing, driver, log = work / "lines.bin", work / "driver.sh", work / "shim.log"
    listing.write_bytes(b"".join(line.encode("utf-8") + b"\0" for line in lines))
    _write(driver, _BASH_DRIVER)
    subprocess.run([_BASH, driver.as_posix(), shim_dir.as_posix(), log.as_posix(),
                    listing.as_posix()], cwd=str(work), capture_output=True, check=False,
                   timeout=900, env=dict(os.environ, SHIMRC=str(rc)))
    return _parse(log, len(lines))


def run_pwsh(lines, shim_dir, work, rc=0):
    """Per line, the sorted argv lists PowerShell handed the shim."""
    _fresh(work)
    listing, driver, log = work / "lines.json", work / "driver.ps1", work / "shim.log"
    _write(listing, json.dumps(lines))
    _write(driver, _PS_DRIVER)
    subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(driver),
                    "-ShimDir", str(shim_dir), "-Log", str(log), "-LinesFile", str(listing)],
                   cwd=str(work), capture_output=True, check=False, timeout=900,
                   env=dict(os.environ, SHIMRC=str(rc)))
    return _parse(log, len(lines))


def _accepted(lines, shell):
    out = []
    for line in lines:
        commands = crew_gitallow.line_git_commands(line, shell)
        if commands:
            out.append((line, sorted(list(a) for a in commands)))
    return out


def _union(first, second):
    """Each argv as often as the run that ran it most often: git exiting 0
    and exiting 1 between them take both sides of every `&&` and `||`."""
    out = []
    for argv in sorted({tuple(a) for a in first + second}):
        out += [list(argv)] * max(first.count(list(argv)), second.count(list(argv)))
    return sorted(out)


def _divergences(shell, lines, runner, shim_dir, work):
    """`(accepted, bad, short)`. BAD: an accepted line that handed git an
    argv the reader did not see -- any argv, or the same one more often than
    the reader read it. SHORT: a line that ran fewer git commands than the
    reader read, or none: the shell refused the line or a redirection could
    not be opened on this host (`2>/dev/null` under Windows PowerShell, a
    target that is a directory), which hands git nothing it did not read.
    Counted, never a failure; every git argv that did run is still held to
    the reader's."""
    accepted = _accepted(lines, shell)
    assert accepted, "the corpus has no accepted line: nothing was compared"
    texts = [line for line, _ in accepted]
    ok_run, seen_ok = runner(texts, shim_dir, work / "rc0", 0)
    fail_run, seen_fail = runner(texts, shim_dir, work / "rc1", 1)
    every = set(range(len(accepted)))
    assert seen_ok == every and seen_fail == every, "the driver did not reach every line"
    bad, short = [], []
    for (line, reader), got_ok, got_fail in zip(accepted, ok_run, fail_run):
        got = _union(got_ok, got_fail)
        if any(got.count(argv) > reader.count(argv) for argv in got):
            bad.append((line, reader, got))
        elif got != reader:
            short.append(line)
    return len(accepted), bad, short


# --- the tests --------------------------------------------------------------------------

_NEED_BASH = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
_NEED_PWSH = pytest.mark.skipif(_PWSH is None, reason="no PowerShell 7")


@_NEED_BASH
def test_the_bash_harness_sees_what_bash_runs(shim_dir, tmp_path):
    """The harness measures bash, not the reader: round 5's BLOCK 1 line
    really hands git `--receive-pack` (the reader refuses it now)."""
    real, _seen = run_bash(["git push >&---receive-pack=x origin main", "git status 2>&1"],
                           shim_dir, tmp_path / "w")
    assert real == [[["push", "--receive-pack=x", "origin", "main"]], [["status"]]]
    # What the round-4 reader saw for the first line: the check calls it bad.
    old = [["push", "origin", "main"]]
    assert any(real[0].count(argv) > old.count(argv) for argv in real[0])


@_NEED_PWSH
def test_the_powershell_harness_sees_what_powershell_runs(shim_dir, tmp_path):
    where = _ps_shim_dir(shim_dir)
    if where is None:
        pytest.skip("no way to build a native git shim for PowerShell here")
    real, _seen = run_pwsh(["git push origin 'a b' 2>&1", "git status; git log -1"],
                           where, tmp_path / "w")
    assert real == [[["push", "origin", "a b"]], sorted([["status"], ["log", "-1"]])]


def _check(shell, slow, shim_dir, tmp_path):
    lines = corpus(shell, slow)
    if shell == "bash":
        count, bad, _nothing = _divergences(shell, lines, run_bash, shim_dir,
                                            tmp_path / "w")
    else:
        where = _ps_shim_dir(shim_dir)
        if where is None:
            pytest.skip("no way to build a native git shim for PowerShell here")
        count, bad, _nothing = _divergences(shell, lines, run_pwsh, where, tmp_path / "w")
    assert not bad, f"{len(bad)} of {count} accepted lines ran another argv: {bad[:5]}"


@_NEED_BASH
def test_every_accepted_bash_line_runs_the_argv_the_reader_saw(shim_dir, tmp_path):
    _check("bash", False, shim_dir, tmp_path)


@_NEED_PWSH
def test_every_accepted_powershell_line_runs_the_argv_the_reader_saw(shim_dir, tmp_path):
    _check("powershell", False, shim_dir, tmp_path)


@pytest.mark.slow
@_NEED_BASH
def test_every_accepted_bash_line_of_the_whole_corpus_and_fuzz(shim_dir, tmp_path):
    _check("bash", True, shim_dir, tmp_path)


@pytest.mark.slow
@_NEED_PWSH
def test_every_accepted_powershell_line_of_the_whole_corpus_and_fuzz(shim_dir, tmp_path):
    _check("powershell", True, shim_dir, tmp_path)


def test_the_default_corpus_stays_small():
    """A few hundred lines by default; the rest is `--run-slow`."""
    for shell in ("bash", "powershell"):
        assert len(corpus(shell, False)) <= 600, shell
        assert len(corpus(shell, True)) > len(corpus(shell, False))
