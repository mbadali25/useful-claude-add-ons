"""Which directories does a Bash deploy command name? promote-gate.sh's parser.

T-0505. promote-gate used to judge `CLAUDE_PROJECT_DIR` and never the tree the
deploy runs from. This prints what the COMMAND says about that tree, one record
per line, `<kind>\\t<token>`, and resolves nothing itself: promote-gate.sh does
the resolving with bash's own `cd`, so an MSYS path (`/c/repos/x`) or a Windows
one (`C:\\repos\\x`) under Git Bash means what it means to the shell that runs
the command, which python on Windows would get wrong.

Kinds:
  cd    one step of the LEADING `cd <dir> &&` / `cd <dir>;` chain, in order
  C     a directory the command reads: `git -C <dir>` (git's global option),
        `env -C`/`make -C <dir>`, `--chdir`/`--cwd`/`--directory <dir>`
  bare  a git invocation with no `-C`: it resolves in the chain's directory
  hex   a 7-40 character hex token, a candidate literal sha
  bad   a directory token the shell would expand (`$`, a backtick) or `-`
        (the previous directory) - the gate cannot know what it names, so it
        must refuse rather than guess
  midcd a `cd`/`pushd`/`popd`/`chdir` word AFTER the leading chain (`true &&
        cd x && deploy`, `(cd x && deploy)`, `bash -c 'cd x && deploy'`, a
        second line): the deploy may run somewhere the chain does not say, so
        the gate refuses and asks for the cd to come first
  gitdir `--git-dir`/`--work-tree`/`GIT_DIR=`/`GIT_WORK_TREE=`: git pointed at
        a repository by a route the gate does not follow

promote-gate.ps1 carries the same rules natively for the PowerShell tool; the
branch between the two is which TOOL ran the command, never the OS.
"""
import re
import sys

# A token: double-quoted, single-quoted, or a run of characters that ends the
# word. `)` ends it too, so `$(git -C dir rev-parse HEAD)` reads `dir`.
_TOKEN = r"""(?:"([^"]*)"|'([^']*)'|([^\s;&|()]+))"""
_CD = re.compile(r"\s*(?:cd|pushd)(?:\s+--)?\s+" + _TOKEN + r"\s*(?:&&|;)")
# A directory change anywhere after the chain, as a WORD: after a separator,
# whitespace, a quote (`bash -c 'cd x && deploy'`) or a brace, and followed by
# the end, whitespace, a separator or a quote. Deliberately broad (GEN-05): a
# `cd` the chain did not take is could-not-tell, whatever form it is in.
_MIDCD = re.compile(r"""(?:^|(?<=[\s;&|(){}'"`]))(?:cd|pushd|popd|chdir)(?=$|[\s;&|)'"`])""")
# Other tools that take a directory: `env -C`/`make -C` anywhere in the same
# simple command, and the long flags that mean "run there". `git -C` is only
# its GLOBAL option (before the subcommand; `git log -C` is copy detection).
_TOOLDIR = re.compile(r"(?:^|(?<=[\s(;&|/`'\"]))(?:env|make|gmake)\b[^;&|\n]*?\s-C\s*" + _TOKEN)
_LONGDIR = re.compile(r"(?:^|(?<=\s))--(?:chdir|cwd|directory)(?:=|\s+)" + _TOKEN)
_GITDIR = re.compile(r"--git-dir\b|--work-tree\b|\bGIT_DIR=|\bGIT_WORK_TREE=")
_GIT = re.compile(r"(?:^|(?<=[\s(;&|/`]))git\b((?:\s+-c\s+\S+)*)(\s+-C\s*"
                  + _TOKEN + r")?")
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])")


def _value(match, first):
    """The token's text from whichever of the three alternatives matched, and
    whether the shell would expand it (unquoted or double-quoted `$`/backtick;
    single quotes expand nothing)."""
    dq, sq, bare = match.group(first), match.group(first + 1), match.group(first + 2)
    if sq is not None:
        return sq, False
    text = dq if dq is not None else bare
    return text, ("$" in text or "`" in text)


def records(command):
    """Every record for `command`, in the order promote-gate.sh applies them."""
    out = []
    pos = 0
    while True:
        m = _CD.match(command, pos)
        if not m:
            break
        text, expands = _value(m, 1)
        out.append(("bad" if expands or text == "-" else "cd", text))
        pos = m.end()
    # On the REMAINDER, so `^` means "right after the chain": a `cd` there
    # that the chain did not take (`cd x | deploy`) is not understood either.
    for m in _MIDCD.finditer(command[pos:]):
        out.append(("midcd", m.group(0).strip()))
    for rx in (_TOOLDIR, _LONGDIR):
        for m in rx.finditer(command):
            text, expands = _value(m, 1)
            out.append(("bad" if expands else "C", text))
    for m in _GITDIR.finditer(command):
        out.append(("gitdir", m.group(0)))
    for m in _GIT.finditer(command):
        if m.group(2) is None:
            out.append(("bare", ""))
            continue
        text, expands = _value(m, 3)
        out.append(("bad" if expands else "C", text))
    for m in _HEX.finditer(command):
        out.append(("hex", m.group(0)))
    return out


def main(argv):
    """Print the records for argv[1]; a token holding a newline is `bad`."""
    command = argv[1] if len(argv) > 1 else ""
    for kind, text in records(command):
        if "\n" in text or "\r" in text or "\t" in text:
            kind, text = "bad", text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        print(f"{kind}\t{text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
