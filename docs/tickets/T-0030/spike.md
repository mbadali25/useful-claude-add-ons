# T-0030 spike (plan step 1)

## 1. Remote acceptance - DONE 2026-09-25 ~21:30 CDT, owner-approved
- Commit: `git commit-tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904` (the empty tree) -> 09fde842e0ec4980b5ea3a2d319e7639098cadca
- `git push origin 09fde842...:refs/heads/crew-coord/spike-test` (no force flag): exit 0, `* [new branch] 09fde842... -> crew-coord/spike-test`. GitHub printed only its usual "Create a pull request" hint. No branch protection or ruleset refused it.
- `git ls-remote origin 'refs/heads/crew-coord/*'` showed the ref, then `git push origin --delete crew-coord/spike-test` gave exit 0 `- [deleted]`, and ls-remote then printed nothing: the ref is gone.
- Decision: origin accepts `crew-coord/*`, so Step 2 may proceed.

## 6. Hooks - PARTIAL
- `~/.cache/graphify-rebuild.log` does not exist on this machine (stat: none before and after), so the post-commit/post-checkout rebuild hooks CLAUDE.md cites are not installed in this clone, or log elsewhere. `commit-tree` and `push` ran with no hook output. The claim that no hook fires can't be confirmed here; re-check on a clone with `graphify hook install`.

## 3. Owner signal - PARTIAL (2026-09-25, owner's screenshot)
- The owner ran `env | cut -d= -f1 | grep -i claude | sort` in a **plain terminal outside any Claude session** (root@dadeush-buntu-laptop:/repos, just after exiting a session). It printed only `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION` and `CLAUDE_CODE_ENABLE_TODO_TOOLS`.
- Claude's Bash tool, in this session, carries `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_BRIDGE_SESSION_ID`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_PID` and others.
- Candidate signal: `release --break` runs only when `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID` are both absent, which means the owner runs it from their own terminal, outside Claude.
- **Limit, stated plainly:** Claude could strip these with `env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID ...`, so this stops accidental breaks, not a determined agent. `--break` also requires `--by` and is logged. Making it hard would need a scope-guard rule refusing `crew_coord ... --break` from Claude's shell, which is a hook change outside T-0030 (candidate follow-up, T-0029's guard pattern).
- NOT measured: the `!`-prefix path inside a session. It probably inherits Claude's environment, so it would not work as a signal. Instruction for the owner: run breaks from a plain terminal.

## 2, 4, 5. Identity across /clear, heartbeat survival, PID proof - NOT YET RUN
- Windows parts go to win-repo-2.

## 4-5 (Windows). Heartbeat survival and PID proof - MEASURED by win-repo-2 on DADEUSH-DESKTOP, 2026-09-26, Python 3.14.6, ELEVATED (IsUserAnAdmin=True)
- (a) Detached child SURVIVES the tool call: `Popen([sys.executable, child.py], creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP (0x208), stdin/stdout/stderr=DEVNULL, close_fds=True)` from a Claude Bash tool call; the call returned 01:42:22, child pid 61700 wrote all 16 ticks 01:42:18..01:57:18 at 60s intervals, none missed, exited on its own; tasklist showed it gone 01:59:23. NOT tested across a session exit or Windows logoff.
- (b) PID existence + start time via `OpenProcess(access, False, pid)` + `GetProcessTimes` / `GetExitCodeProcess`:
  - live child: 0x1000 (PROCESS_QUERY_LIMITED_INFORMATION) ok, create time returned, exitcode 259; 0x400 same.
  - dead, no handle held: OpenProcess NULL, **err 87** (both masks).
  - dead but its handle still held (by Popen): OpenProcess **succeeds**, create AND exit FILETIME set, exitcode 0.
  - PID 4 System / lsass.exe: 0x1000 ok; 0x400 NULL **err 5** (access denied).
  - `tasklist /FI "PID eq n"`: rc=0 for live AND dead; dead only detectable by parsing the locale-dependent INFO text; no start time. Do not use.
- Decision for the implementation (rule: cannot tell = ALIVE):
  - open with 0x1000 (LIMITED); only err 87 = DEAD; err 5 or any other error = ALIVE (presented, never adopted);
  - a successful open is not proof of life: DEAD only if GetProcessTimes gives a nonzero exit FILETIME (or WaitForSingleObject(h,0) == WAIT_OBJECT_0); do not use exitcode==259 alone (259 is a legal exit code);
  - PID reuse: compare the creation FILETIME with the recorded `pid_start`; mismatch = the recorded process is gone.
  - NOT verified: non-elevated behaviour of 0x1000 on system processes.
