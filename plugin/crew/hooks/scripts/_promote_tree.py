"""Which directories does a Bash deploy command name? promote-gate.sh's parser.

T-0505. promote-gate used to judge `CLAUDE_PROJECT_DIR` and never the tree the
deploy runs from. This prints what the COMMAND says about that tree, one record
per line, `<kind>\\t<token>`, and resolves nothing itself: promote-gate.sh does
the resolving with bash's own `cd`, so an MSYS path (`/c/repos/x`) or a Windows
one (`C:\\repos\\x`) under Git Bash means what it means to the shell that runs
the command, which python on Windows would get wrong.

Kinds:
  cd    one step of the LEADING `cd <dir> &&` / `cd <dir>;` chain, in order
  C     the directory of git's GLOBAL `-C <dir>` (before the subcommand), in
        text the shell executes - unquoted, or inside `$(...)`/backticks
  bare  a git invocation with no `-C`: it resolves in the chain's directory
  hex   a 7-40 character hex token, a candidate literal sha
  bad   anything the gate cannot read with certainty (GEN-05), so it refuses
        rather than guesses: a directory token the shell would expand (`$`, a
        backtick) or `-`; a git global option outside a short allowlist; `-C`
        twice; `git` inside quoted text that is not executed
  midcd a directory change AFTER the leading chain: a `cd`/`pushd`/`popd`/
        `chdir` word anywhere (`true && cd x && deploy`, `(cd x && deploy)`,
        `bash -c 'cd x && deploy'`, a second line), or `env -C`/`--chdir`,
        `make -C`/`--directory`: the deploy may run somewhere the chain does not
        say, so the gate refuses and asks for the cd to come first
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
_GITDIR = re.compile(r"--git-dir\b|--work-tree\b|\bGIT_DIR=|\bGIT_WORK_TREE=")
# Other tools that change directory for what they run. They are NOT read as
# the deploy's tree: the process the deploy runs in is still the chain's, so
# they are could-not-tell (reported as midcd). An application's own
# `--directory` is not listed - its meaning belongs to that program.
_TOOLDIR = re.compile(r"(?:^|(?<=[\s(;&|/`'\"]))(?:env\b[^;&|\n]*?\s(?:-C|--chdir\b)"
                      r"|g?make\b[^;&|\n]*?\s(?:-C|--directory\b))")
_GIT = re.compile(r"""(?:^|(?<=[\s(;&|/`'"]))git(?:\.exe)?(?=$|[\s;&|)'"`])""")
_ARG = re.compile(r"\s+" + _TOKEN)
# Git global options that take no value and move nothing; anything else before
# the subcommand is could-not-tell.
_GIT_FLAGS = {"--no-pager", "-P", "--paginate", "-p", "--no-replace-objects",
              "--literal-pathspecs", "--no-optional-locks", "--no-lazy-fetch"}
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


def executed(command):
    """Per character: True where the shell EXECUTES the text - unquoted, or
    inside `$(...)` or backticks, even within double quotes. False inside
    single quotes and inside the literal part of double quotes, where a
    `git -C x` is only text (Codex r1: `--note "git -C <wt>"` selected a tree
    the deploy never ran in)."""
    out = [True] * len(command)
    stack = ["U"]           # U unquoted, S single, D double, X $( ), B backtick
    i = 0
    while i < len(command):
        c, top = command[i], stack[-1]
        out[i] = top in ("U", "X", "B")
        if top == "S":
            if c == "'":
                stack.pop()
        elif c == "\\" and top != "S":
            if i + 1 < len(command):
                out[i + 1] = out[i]
            i += 2
            continue
        elif top == "D" and c == '"':
            stack.pop()
        elif command.startswith("$(", i):
            stack.append("X")
            if i + 1 < len(command):
                out[i + 1] = True
            i += 2
            continue
        elif c == "`":
            if top == "B":
                stack.pop()
            else:
                stack.append("B")
        elif top in ("U", "X", "B") and c == "'":
            stack.append("S")
            out[i] = False
        elif top in ("U", "X", "B") and c == '"':
            stack.append("D")
            out[i] = False
        elif top == "X" and c == ")":
            stack.pop()
        i += 1
    return out


def _git_records(command, m):
    """Read git's global options after one `git` word: `-C <dir>` once,
    `-c <k=v>`, the no-value allowlist; stop at the subcommand."""
    pos, dirs = m.end(), []
    while True:
        a = _ARG.match(command, pos)
        if not a:
            break
        text, expands = _value(a, 1)
        if expands:
            return [("bad", f"git {text}")]
        if not text.startswith("-"):
            break
        if text in ("-C", "-c"):
            b = _ARG.match(command, a.end())
            if not b:
                return [("bad", f"git {text} with no value")]
            val, vexp = _value(b, 1)
            if text == "-C":
                if vexp or val == "-":
                    return [("bad", val)]
                dirs.append(val)
            pos = b.end()
            continue
        if text.startswith(("--git-dir", "--work-tree")):
            return [("gitdir", text)]
        if expands or text not in _GIT_FLAGS:
            return [("bad", f"git global option {text}")]
        pos = a.end()
    if len(dirs) > 1:
        return [("bad", "git -C given more than once")]
    return [("C", dirs[0])] if dirs else [("bare", "")]


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
    # Quoted or not: `bash -c 'cd x && deploy'` runs the cd.
    for m in _MIDCD.finditer(command[pos:]):
        out.append(("midcd", m.group(0).strip()))
    for m in _TOOLDIR.finditer(command):
        out.append(("midcd", m.group(0).strip()))
    for m in _GITDIR.finditer(command):
        out.append(("gitdir", m.group(0)))
    live = executed(command)
    for m in _GIT.finditer(command):
        if not live[m.start()]:
            out.append(("bad", "git inside quoted text that the shell does not run"))
            continue
        out.extend(_git_records(command, m))
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
