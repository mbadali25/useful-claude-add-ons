# crew 0.2.0 hardening and a full QA pass over the skills marketplace

- **Session:** `2026-08-23-session-01`
- **Started:** Sunday, August 23, 2026 at 4:09 AM UTC-05:00
- **Ended:** Sunday, August 23, 2026 at 4:10 AM UTC-05:00

## Summary

Reviewed the crew plugin and the 25 skills in this marketplace, and shipped three merged PRs closing roughly 45 defects. The through-line: almost none were visible by reading the code. crew's Windows hooks had never run - the command guard blocked nothing and the Stop gate ran nothing, silently. cisco-meraki could destroy live network config with no confirmation while its own docstring promised otherwise, and leaked pre-shared keys into diffs. intune-graph exposed device wipe from a one-liner. work-log-reporter could not run on Windows at all and would mail its SMTP password in cleartext on a plausible typo. Each of those was found by executing the code with real inputs, not by review. Every gate that can block now has a committed suite that was verified to go red when the bug is reintroduced. One thing remains genuinely unproven: the crew command and agent prompts are structurally valid but their judgement is untested, which needs a live ticket rather than another test.

## Touched in this session

- **Code:** `plugin/crew/hooks/hooks.json`, `plugin/crew/hooks/scripts/_common.sh`, `plugin/crew/hooks/scripts/guard.sh`, `plugin/crew/hooks/scripts/verify-gate.sh`, `plugin/crew/hooks/scripts/verify-gate.ps1`, `plugin/crew/commands/promote.md`, `plugin/crew/hooks/scripts/promote-gate.sh`, `plugin/crew/hooks/scripts/promote-gate.ps1`, `plugin/crew/hooks/scripts/_test/run-tests.sh`, `plugin/crew/hooks/scripts/_test/setup-walkthrough.sh`, `plugin/crew/hooks/scripts/_test/validate-prompts.py`, `skills/cisco-meraki/scripts/meraki_config.py`, `skills/intune-graph/scripts/graph.py`, `skills/cisco-meraki/scripts/meraki_diff.py`, `skills/work-log-reporter/scripts/mailer.py`, `skills/work-log-reporter/scripts/render.py`, `skills/work-log-reporter/scripts/wlconfig.py`, `skills/intune-graph/scripts/auth.py`, `skills/**/*.py`, `skills/bitbucket/scripts/bb.sh`, `skills/cloudflare/scripts/cloudflare_client.py`, `skills/cloudflare/references/auth.md`, `skills/notify/scripts/inbox.py`, `skills/notify/tests/test_inbox_concurrency.py`, `skills/notify/scripts/notifyd.py`, `skills/visio-diagrams/scripts/vsdx_writer.py`, `skills/visio-diagrams/scripts/New-VisioDiagram.ps1`, `plugin/crew/hooks/scripts/context-watch.sh`, `plugin/crew/skills/crew-context/SKILL.md`, `docs/HANDOFF.md`
- **Systems:** `Claude Code plugin hooks`, `Windows/Git Bash`, `Cisco Meraki Dashboard API`, `Microsoft Intune / Graph`, `Windows`, `Cloudflare API v4`, `Telegram Bot API`, `Windows filesystem`
- **Commands:** `bash plugin/crew/hooks/scripts/_test/run-tests.sh`, `python -m pytest skills/notify/tests/ -q`
- **Tickets / Refs:** `PR #28`, `PR #29`, `PR #30`

## Log

### 1. Fixed crew's hooks, which had never run on Windows

`4:09 AM` · done

guard.sh and verify-gate.sh exited 0 on MSYS/MINGW to defer to .ps1 twins, and hooks.json registered those twins with a 'shell: powershell' field Claude Code does not read. Net effect on Windows: the command guard blocked nothing and the Stop gate ran nothing, which reads as 'the gate passed' rather than 'the gate never ran'. Each hook is now registered once as bash; only the PreToolUse guard branches, and it branches on tool_name rather than the OS. That distinction matters: a Bash tool call is bash syntax even on Windows, and an earlier OS-based fix made things worse by judging bash commands with PowerShell rules, blocking the correct secret-capture form while allowing a secret to be written to disk.

- **Code:** `plugin/crew/hooks/hooks.json`, `plugin/crew/hooks/scripts/_common.sh`, `plugin/crew/hooks/scripts/guard.sh`, `plugin/crew/hooks/scripts/verify-gate.sh`
- **Systems:** `Claude Code plugin hooks`, `Windows/Git Bash`
- **Tickets / Refs:** `PR #28`

### 2. Fixed a verification map that silently skipped every root-level file

`4:09 AM` · done

fnmatch and PowerShell's -like both let * span a slash, so a '**/*.tf' rule demanded a literal slash and never matched main.tf - the file a Terraform module keeps at its root. Combined with unmapped:fail, editing main.tf both failed the gate and skipped fmt, validate and tflint. Both gate implementations now also test the pattern with the leading '**/' stripped.

- **Code:** `plugin/crew/hooks/scripts/verify-gate.sh`, `plugin/crew/hooks/scripts/verify-gate.ps1`
- **Tickets / Refs:** `PR #28`

### 3. Added promotion gates that a hook enforces, not just instructions

`4:09 AM` · done

New /crew:promote drives development -> qa -> production as five gates: pre-deploy, deploy, smoke, regression, post-soak verify. promote-gate.sh runs on PreToolUse and refuses any command matching a declared deploy entry unless the upstream environment has an all-pass row for THAT sha, the rollback runbook is verified inside 90 days, requireHuman is approved, and the tree is clean. verify-gate.sh additionally refuses to end a turn after a deploy that recorded nothing. What a hook cannot see - that smoke and regression actually ran afterwards - is documented as a claim rather than implied as coverage.

- **Code:** `plugin/crew/commands/promote.md`, `plugin/crew/hooks/scripts/promote-gate.sh`, `plugin/crew/hooks/scripts/promote-gate.ps1`
- **Tickets / Refs:** `PR #28`

### 4. Committed three sabotage-tested suites for the crew gates

`4:09 AM` · done

50 hook cases covering what the command guard must block and must allow plus the promotion preconditions, 32 cases running every setup-phase script against a real mixed-stack scratch repo, and 91 structural checks over the commands, agents and skills. Each was verified by reintroducing the bug it is meant to catch and confirming it goes red - guard.sh had shipped two real regressions in two review passes, both found only by running it.

- **Code:** `plugin/crew/hooks/scripts/_test/run-tests.sh`, `plugin/crew/hooks/scripts/_test/setup-walkthrough.sh`, `plugin/crew/hooks/scripts/_test/validate-prompts.py`
- **Commands:** `bash plugin/crew/hooks/scripts/_test/run-tests.sh`
- **Tickets / Refs:** `PR #28`

### 5. Closed two paths that could damage live infrastructure with no confirmation

`4:10 AM` · done

cisco-meraki's batch_commit PUT confirmed:true with no snapshot, no diff, no prompt and no --yes flag, while the module docstring promised that apply() cannot reach a PUT without all three - 'control flow, not a rule someone has to remember'. An action batch creates, updates and destroys across every network in an org in one call. confirm is now a required positional argument. Separately, intune-graph exposed POST/PATCH/PUT/DELETE against any Graph path with no guard at all; a single command could wipe a laptop. Irreversible actions are now refused outright and pointed at the portal where they are logged against a name.

- **Code:** `skills/cisco-meraki/scripts/meraki_config.py`, `skills/intune-graph/scripts/graph.py`
- **Systems:** `Cisco Meraki Dashboard API`, `Microsoft Intune / Graph`
- **Tickets / Refs:** `PR #29`

### 6. Stopped two paths that exposed credentials

`4:10 AM` · done

cisco-meraki redacted secrets with an exact-match list of nine lowercase key names, so wpaPreSharedKey, ikePresharedKey, vpnSecret and radiusSecret all printed in the clear into diffs, tickets and snapshot files - a denylist only redacts the names someone thought of. Now substring-matched. Separately, work-log-reporter's SMTP branch is ssl -> SMTP_SSL, anything else -> plain socket, then starttls only on an exact match: so security 'tls', a plausible typo and the spelling several providers document, opened an unencrypted socket and called login() over it with nothing reporting the downgrade.

- **Code:** `skills/cisco-meraki/scripts/meraki_diff.py`, `skills/work-log-reporter/scripts/mailer.py`
- **Tickets / Refs:** `PR #29`

### 7. Fixed two things that were broken only on Windows

`4:10 AM` · done

work-log-reporter could not render a report at all: strftime's no-pad modifier %-I and %-d is glibc-only and Python raises ValueError rather than degrading, so every email and PDF path died before producing anything. And intune-graph's Azure CLI call used subprocess.run with the bare launcher name - which ships as a .cmd on Windows, where CreateProcess does not apply PATHEXT - so it raised FileNotFoundError with the CLI correctly installed, and the handler blamed PATH. Both verified on a real Windows machine.

- **Code:** `skills/work-log-reporter/scripts/render.py`, `skills/work-log-reporter/scripts/wlconfig.py`, `skills/intune-graph/scripts/auth.py`
- **Systems:** `Windows`
- **Tickets / Refs:** `PR #29`

### 8. Removed 356 bytes of non-ASCII from 23 script files

`4:10 AM` · done

Em dashes, middle dots, ellipses and smart quotes. Seven sat on human-facing output: the HTML email title, the email body, PDF headings and PDF metadata. Quoted-printable turns an em dash into =E2=80=94 and a client that mis-decodes shows mojibake - it looks correct on the machine that sent it and wrong on the one that receives it, with nothing reporting the difference. One replacement broke an f-string; py_compile caught it.

- **Code:** `skills/**/*.py`, `skills/bitbucket/scripts/bb.sh`
- **Tickets / Refs:** `PR #29`

### 9. Made the Cloudflare client work with a scoped token instead of fighting it

`4:10 AM` · done

It already preferred CLOUDFLARE_API_TOKEN. The friction was account_id(name) enumerating /accounts to resolve an org display name - and a scoped token frequently cannot enumerate, returning 403 or an empty array even with full permission on that account. The lookup failed in a way that reads as a broken token. CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_ZONE_ID now short-circuit it, the name argument is optional, and enumeration failure explains what to set instead. verify() no longer reports success for a Global API Key without having checked anything, since there is no verify endpoint for it.

- **Code:** `skills/cloudflare/scripts/cloudflare_client.py`, `skills/cloudflare/references/auth.md`
- **Systems:** `Cloudflare API v4`
- **Tickets / Refs:** `PR #29`

### 10. Fixed a race in notify's inbox that silently dropped messages

`4:10 AM` · done

read() and _trim() both do read-all, filter, os.replace. An append landing between the read and the replace is in neither list, so the replace destroyed it - the exact message loss inbox.py exists to prevent. Every read-modify-write now holds an O_CREAT|O_EXCL lock, stale-broken after 30s. Fixing it surfaced two Windows-only bugs: os.replace fails with PermissionError if anything holds the destination for an instant, and deletion is deferred so O_CREAT against a pending-delete lock file raises PermissionError rather than EEXIST - which turned ordinary lock churn into the very loss the lock was added to prevent. Before: 4 of 240 messages lost per run, flaky 1 in 3. After: 8 of 8 runs clean.

- **Code:** `skills/notify/scripts/inbox.py`, `skills/notify/tests/test_inbox_concurrency.py`
- **Systems:** `Telegram Bot API`, `Windows filesystem`
- **Commands:** `python -m pytest skills/notify/tests/ -q`
- **Tickets / Refs:** `PR #30`

### 11. Made the notify daemon single-instance

`4:10 AM` · done

run() overwrote the pidfile unconditionally. Telegram allows exactly one long-poll per bot token - a second getUpdates gets 409 Conflict - so two daemons would fight for updates and stop would kill whichever pid was written last. It now refuses to start when a live daemon holds the spool, checking the pid for liveness rather than trusting the file to exist, and cross-checking the heartbeat so a recycled pid is not mistaken for ours.

- **Code:** `skills/notify/scripts/notifyd.py`
- **Tickets / Refs:** `PR #30`

### 12. Stopped the Visio writer emitting files Visio refuses to open

`4:10 AM` · done

Attribute values were written raw into V="...". escape() covers ampersand, less-than and greater-than but not the quote character, and these are attribute values - a colour or label in a user-authored spec can easily carry one, closing the attribute early. Now quoteattr, verified by round-tripping a value containing a quote, an ampersand and a less-than through an XML parser. Also added overwrite guards: zipfile 'w' truncates, and the PowerShell path suppressed Visio's own overwrite prompt then never checked whether the file appeared.

- **Code:** `skills/visio-diagrams/scripts/vsdx_writer.py`, `skills/visio-diagrams/scripts/New-VisioDiagram.ps1`
- **Tickets / Refs:** `PR #30`

### 13. Rewrote crew's context watch to measure the window instead of estimating it

`4:10 AM` · done

Reported as 'the 80% warning never fired'. Root cause was not a bug - crew's hooks are inert until /crew:init runs in that repo, which nothing said where a person would look. But testing it found two real bugs. The estimate read transcript file size, and the transcript is cumulative - it keeps every turn ever written including ones a compaction discarded - so it read 45% high, 950k against 654k actual. The transcript already carries message.usage; the hook now reads the real prompt size. And budgetTokens defaulted to 200000 against a 1M window, so the gate would fire on turn one forever. It now derives itself from the model id corrected by observed peak usage, because a 1M variant reports its base id and observed usage cannot exceed the real window.

- **Code:** `plugin/crew/hooks/scripts/context-watch.sh`, `plugin/crew/skills/crew-context/SKILL.md`
- **Tickets / Refs:** `PR #30`

### 14. Left the crew prompts unverified, and said so

`4:10 AM` · blocked

The 16 slash commands and 9 subagents are instructions to a model. Their structure is validated - frontmatter parses, tool names are real, referenced agents and plugin paths resolve, read-only agents hold no write tools, commands that spawn subagents are permitted to. Their judgement is not, and no test closes that. It needs /crew:init in a real repository and one ticket run end to end, which is what setup Phase 7 exists for. Recorded in docs/HANDOFF.md as the main open item rather than left implicit.

- **Code:** `docs/HANDOFF.md`
- **Tickets / Refs:** `PR #28`
