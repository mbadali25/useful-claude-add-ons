# What AWS Systems Manager will and will not carry

Every number below is copied from the AWS or Microsoft page on its row. A limit this file
cannot cite is written as "not documented", with the safe route instead of a guess.

## Limits

| What | Limit | Source |
|---|---|---|
| Run Command stdout returned by the API (`StandardOutputContent`) | first 24,000 characters | [GetCommandInvocation](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html) |
| Run Command stderr returned by the API (`StandardErrorContent`) | first 8,000 characters | [GetCommandInvocation](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html) |
| `Comment` on a command | 100 characters | [GetCommandInvocation](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html) |
| SSM document size | 64 KB | [Systems Manager quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) |
| Parameter Store value, standard tier | 4 KB | [Systems Manager quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) |
| Parameter Store value, advanced tier | 8 KB | [Systems Manager quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) |
| Session Manager idle timeout | 20 minutes by default, settable from 1 to 60 | [Systems Manager quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) |
| Automation `aws:executeScript` output | 100 KB | [Systems Manager quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) |
| `cmd.exe` command line on the node | 8,191 characters | [Command prompt line string limitation](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation) |
| Any Windows process command line (`CreateProcess`) | 32,767 characters | [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) |
| Total size of `SendCommand` `Parameters` | not documented: stage the payload in S3 and verify its hash on the node | [SendCommand](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_SendCommand.html) |

## The cut is silent

Output over the API limit is cut and the call still succeeds: `Status` is `Success` and
nothing in the response says text is missing. Output exactly at the limit cannot be told
apart from cut output, so treat it as cut. Never parse `StandardOutputContent` as a whole
answer without checking it first:

```bash
aws ssm get-command-invocation --command-id "$CMD" --instance-id i-02573cafcfEXAMPLE > inv.json
python3 scripts/ssm_output.py inv.json      # complete=0, truncated=3, could not tell=4
```

`Status` values `Pending`, `InProgress`, `Delayed` and `Cancelling` mean the command is still
going; `TimedOut` and `Cancelled` mean it stopped before it finished. Output read in any of
those states is not the whole answer, which is why the helper reports "could not tell".

## Getting the complete output

Pick one when you send the command, not after: neither route can be added to a command
that has already run.

```bash
# S3: the full stdout and stderr land as objects; get-command-invocation then
# fills StandardOutputUrl / StandardErrorUrl.
aws ssm send-command --instance-ids i-02573cafcfEXAMPLE \
  --document-name AWS-RunPowerShellScript \
  --parameters 'commands=["Get-ChildItem C:\\ -Recurse"]' \
  --output-s3-bucket-name amzn-s3-demo-bucket --output-s3-key-prefix ssm-out/

# CloudWatch Logs: the full output streams to a log group.
aws ssm send-command --instance-ids i-02573cafcfEXAMPLE \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["journalctl -n 5000"]' \
  --cloud-watch-output-config CloudWatchOutputEnabled=true,CloudWatchLogGroupName=/ssm/run-command
```

Both are described on the [SendCommand](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_SendCommand.html)
page (`OutputS3BucketName`, `CloudWatchOutputConfig`). The node's instance profile needs
write access to the bucket or log group; without it the command still runs and the full
text is lost.

When neither is available, make the output small on the node: filter there, write the
result to a file and return only its size and SHA-256, or page through it with several
commands that each return well under 24,000 characters.

## Payloads going in

A script or file pushed through a command parameter has no limit this file can cite for
the parameter as a whole, and on Windows it also passes through a command line (the two
Windows rows above). Do not inline anything large:

1. Upload it to S3 from the workstation and record its SHA-256.
2. On the node, download it (`Read-S3Object` or `aws s3 cp`) and compare the hash
   (`Get-FileHash -Algorithm SHA256` or `sha256sum`) before running it.
3. Fail the command when the hash differs. A partial file must not run.

Use `AWS-RunRemoteScript` when the script itself lives in S3 or GitHub.

## Session Manager

An interactive session ends after the idle timeout above. A long-running job started from
a session dies with it: start it as a Run Command, a scheduled task or a service instead,
and poll for its result.
