# Claude Code session records: what auto-clear binds to (T-0016 spike)

Measured 2026-10-04 in a cloud container: Claude Code **2.1.289**, Linux
(kernel 6.18), scratch `HOME` and `CLAUDE_CONFIG_DIR` under a throwaway
directory, so no real repo or session was touched. `auto-clear` (both
flavours) binds a session to its own process through these records; this file
is the evidence behind the values `crew_autocycle.py` and `auto-clear.ps1`
trust, and behind `crew_fixtures.write_session_record`'s shape.

## Where the record is

`$CLAUDE_CONFIG_DIR/sessions/<pid>.json` when `CLAUDE_CONFIG_DIR` is set; with
it set, nothing is written under `~/.claude/sessions`. Unset, the directory is
`~/.claude/sessions` (this session's own record, measured the same day). A
sibling `<pid>.<sha>.key` file also appears and is not read. The record is
removed when the process exits normally, and **left behind** when the process
is killed (a `tmux kill-server` left `<pid>.json` in place), so a record alone
does not prove a live session: its pid must exist and, where readable, its
start time must match.

Keys (all present in every record measured): `pid, sessionId, cwd, startedAt,
procStart, version, peerProtocol, peerFeatures, kind, entrypoint, pidDomain,
messagingSocketPath, name, nameSource, nameSince, status, updatedAt,
statusUpdatedAt`. `procStart` is a string equal to `/proc/<pid>/stat` field 22.

## The cases

| How the session was started | `kind` | `entrypoint` | `tty_nr` (field 7) | `procStart` = field 22 |
|---|---|---|---|---|
| `claude` interactive, as a tmux pane's own process (pane pid = the claude pid) | `interactive` | `cli` | 34816 (`/dev/pts/0`) | yes (`219820`) |
| `claude -p "say ok"` from a plain shell with no tty | `interactive` | `sdk-cli` | 0 | yes (`213653`) |
| `claude -p "say ok"` started from that interactive session's own shell (`!` shell mode) | `interactive` | `sdk-cli` | 0 (the session's shell is a new session with no controlling tty) | yes (`223711`) |
| `script -qc "claude -p 'say ok'"` from the same shell (a pty around `-p`) | `interactive` | `sdk-cli` | 34817 (`/dev/pts/1`) | yes (`223815`) |
| this cloud session (remote, stdin a pipe) | `interactive` | `remote_mobile` | 0 | yes (`268`) |

What follows from the table, and what the code does with it:

- `kind` is `interactive` for every case, `-p` included, so `kind` alone proves
  nothing.
- `-p` is `sdk-cli` with or without a pty, so an `sdk*` entrypoint is headless
  even when `tty_nr` is non-zero. `tty_nr` 0 is headless whatever the
  entrypoint.
- Only `cli` was measured with a terminal, so the allowlist is `{"cli"}`.
  `remote_mobile` and every other value are unknown, never a terminal.
- **`sessionId` follows `/clear`.** The interactive record's `sessionId` changed
  from `f87770c7-...` to `9c7d7f33-...` on `/clear`, with `pid` and `procStart`
  unchanged. The new session's SessionStart (T-0013's resume typing) therefore
  binds by its own id.

## Not measured

- An interactive `script -qc claude` child started from a session's shell (the
  child never wrote its record before the measurement's time limit). The suite
  models it from the rows above: entrypoint `cli`, its own pty.
- Native Windows: `entrypoint`, `kind`, `procStart`'s format, and the record
  path. There is no tty there, so `terminal` rests on kind plus the allowlist,
  and a record is bound by pid and session id with `procStart` unchecked.
- macOS: no `/proc`; parent and tty come from `ps -o ppid=,tty=,comm=` and
  `procStart` is unchecked.
- A live end-to-end `-p` child inside a parent's tmux pane with auto-clear armed
  (TODO.md).
