# Linux tools on a Windows system

Each section names the symptom, the command that shows the cause, and the fix. Check
before acting: the same machine can have Git Bash, WSL and PowerShell 7 all installed,
and which one a command reaches is not the one you assumed.

## Which shell a command lands in

| You ran | It went to | Show it |
|---|---|---|
| a Bash tool call, or a bare hook `command` | Git Bash (MSYS2) | `uname -s` prints `MINGW64_NT-...` or `MSYS_NT-...` |
| `wsl.exe -e <cmd>` or `wsl <cmd>` | the default WSL distribution | `wsl.exe -e uname -r` contains `microsoft` |
| `pwsh -c` / `powershell -c` | PowerShell 7 / Windows PowerShell 5.1 | `$PSVersionTable.PSVersion` |
| a `.bat` / `.cmd`, or `cmd /c` | `cmd.exe` | `ver` |

The syntax is the tool's, not the operating system's: a Bash call is bash syntax on
Windows too. Branch on which shell you are in, never on "is this Windows".

## Interpreters that are not where you expect

- **`python3` is missing in Git Bash.** The Windows installer provides `python` and the
  `py` launcher, not `python3`, and a bare `python` may be the Microsoft Store stub, which
  exists on PATH but does not run Python. Pick the first candidate that actually runs, and
  fail loudly:
  ```bash
  PY=
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then
      PY=$c; break
    fi
  done
  [ -n "$PY" ] || { echo "no working python on PATH" >&2; exit 1; }
  ```
  `"$PY" -c 'import sys; print(sys.executable)'` shows which one you got.
- **`pwsh` is not on Git Bash's PATH** on many machines even when PowerShell 7 is
  installed. Name it by full path: `"/c/Program Files/PowerShell/7/pwsh.exe"`. A bare
  `pwsh` fails as "command not found", which a test runner reports as a failed check,
  not a missing tool. `where.exe pwsh` (from `cmd` or PowerShell) shows where it is.

## Path conversion (MSYS)

Git Bash rewrites arguments that look like POSIX paths before a Windows program sees
them: `/tmp/x` becomes `C:/Users/.../AppData/Local/Temp/x`, and an argument such as
`/repo` passed to `git` or `docker` becomes `C:/Program Files/Git/repo`.

- Symptom: a path you passed turned into `C:/Program Files/Git/...`.
- Turn it off for one command: `MSYS_NO_PATHCONV=1 docker run -v /data:/data ...`.
- Turning it off breaks the opposite case: a Windows program given a POSIX path it
  cannot open. Convert that one yourself:
  ```bash
  WIN=$(cygpath -w "$POSIX_PATH")   # C:\Users\...\file.json
  cygpath -u 'C:\Users\me\file'     # back to /c/Users/me/file
  ```
  `cygpath` exists only under Git Bash/MSYS; guard it with `command -v cygpath`.

## Line endings (CRLF)

A shell script with CRLF endings fails with misleading errors: `$'\r': command not
found`, `bad interpreter: /bin/bash^M`, or a variable that silently ends in `\r`.

- The committed blob and the working tree can differ: `core.autocrlf=true` converts on
  checkout, and a program that rewrites the file converts after it. Bash runs the working
  tree, so measure that, and measure the blob separately:
  ```bash
  file script.sh                    # working tree: "with CRLF line terminators"
  od -c script.sh | head -3         # working tree: \r \n pairs
  git show HEAD:script.sh | tr -cd '\r' | wc -c   # committed blob: 0 means LF
  ```
  `git show <rev>:<path>` prints the blob as stored; it does not apply checkout conversion.
- Python's `pathlib.Path.write_text` and `open(..., "w")` write CRLF on Windows. Pass
  `newline="\n"` for any `.sh` you write.
- `.gitattributes` with `*.sh text eol=lf` fixes checkouts, not files a program writes.
- Repair one file: `sed -i 's/\r$//' script.sh`, or `git checkout -- script.sh` when the
  committed copy is right.

## WSL against Git Bash against PowerShell

Prefer **WSL** when a tool exists only for Linux, or a build runs many small processes
(Git Bash process start-up is slow). Prefer **PowerShell** for Windows administration
and anything that needs Windows credentials. **Git Bash** is the default for short shell
glue next to Windows programs.

Two things do not cross the WSL boundary:

- **Speed on `/mnt/c`.** Files on the Windows drive are dramatically slower from inside
  WSL than files on the WSL filesystem. Clone into `~` inside WSL, not under `/mnt/c`.
- **Credentials and tool installs.** A Windows `aws`, `az` or `git` credential helper is
  not the WSL one. `wsl.exe -e aws sts get-caller-identity` can name a different identity
  from `aws sts get-caller-identity` in PowerShell, or none. Configure each side.

Under WSL2, `localhost` inside the distribution is not always the Windows host; use the
host's address from `ip route show default` when a Windows-side service must be reached.

## Crew users

If this repository uses the crew plugin, crew chooses the shell for its own commands with
its `shellRoute` setting (written by `/crew:setup`). Change that setting rather than
working around it in a rule; this file describes the general case only.
