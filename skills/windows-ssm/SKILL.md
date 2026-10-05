---
name: windows-ssm
description: >
  Run Linux-style tools on a Windows machine without relearning its traps, and drive nodes
  through AWS Systems Manager (SSM) without acting on silently truncated output. Covers which
  shell a command lands in (Git Bash, WSL, PowerShell, cmd), resolving python3/python/py and
  naming pwsh by full path, MSYS path conversion and MSYS_NO_PATHCONV, cygpath, CRLF line
  endings, WSL's /mnt/c and credential boundary; and SSM's documented limits (Run Command
  returns only the first 24,000 characters of stdout and 8,000 of stderr, document, Parameter
  Store and Session Manager limits), how to get complete output through S3 or CloudWatch, and
  how to push a large payload safely. Ships an offline checker that exits non-zero when a
  get-command-invocation result is or may be cut. Use this skill whenever a command runs on
  Windows through Git Bash, WSL or PowerShell, or a node is driven with aws ssm send-command,
  get-command-invocation or Session Manager - including symptoms like "command not found:
  python3 in Git Bash", "pwsh: command not found", "the path turned into C:/Program
  Files/Git/...", "$'\r': command not found", "the SSM output stops halfway", or "the script
  I sent through SSM ran only part way".
---

# Windows tools and SSM limits

Two references and one helper. Read only the reference the task needs.

| Task | Read |
|---|---|
| A command behaves differently on Windows: wrong shell, missing `python3` or `pwsh`, a rewritten path, CRLF errors, WSL against Git Bash | `references/windows-tools.md` |
| Running commands or sending files through SSM Run Command, Session Manager, documents or Parameter Store | `references/ssm-limits.md` |
| Deciding whether an SSM command result is the whole output | `scripts/ssm_output.py` (below) |

## Check SSM output before using it

Run Command cuts stdout at 24,000 characters and stderr at 8,000 and still reports
`Success`. Check every result you will parse or act on:

```bash
aws ssm get-command-invocation --command-id "$CMD" --instance-id i-02573cafcfEXAMPLE > inv.json
python3 scripts/ssm_output.py inv.json
aws ssm get-command-invocation --command-id "$CMD" --instance-id i-02573cafcfEXAMPLE \
  | python3 scripts/ssm_output.py
python3 scripts/ssm_output.py inv.json && jq -r .StandardOutputContent inv.json > out.txt
py scripts\ssm_output.py inv.json; if ($LASTEXITCODE -ne 0) { throw "SSM output not complete" }
```

| Verdict (stdout) | Exit | Do |
|---|---|---|
| `complete` | 0 | Use the output. |
| `truncated` | 3 | Do not parse it. Read the full text from the S3 URL the helper names, or re-run with `--output-s3-bucket-name` / `--cloud-watch-output-config`. |
| `could not tell` | 4 | The command has not finished, stopped early (`TimedOut`, `Cancelled`), or the input is not a get-command-invocation result. Wait and re-read, or fix the input. |

The helper is Python standard library only and offline: it makes no AWS call, reads no
credentials and writes nothing. It prints lengths and a verdict, never the output itself.
Output exactly at a limit counts as truncated, because it cannot be told apart from cut.

## Rules

- Never treat SSM output as complete because `Status` is `Success`.
- Send large payloads through S3 with a hash check on the node, never inline in
  `--parameters` (see `references/ssm-limits.md`, "Payloads going in").
- Never write a real instance id, account id, profile name or bucket name into a file you
  commit; use AWS's documentation placeholders (`i-02573cafcfEXAMPLE`, `amzn-s3-demo-bucket`).
- Branch on the shell a command runs in, not on the operating system.
