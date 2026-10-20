<!-- Moved verbatim from plugin/crew/README.md (13c. Optional: an Obsidian Kanban board) by L-0726; the README keeps an index entry. -->

## 13c. Optional: an Obsidian Kanban board

The fourth tracker, and the only one with nothing to connect to. `tracker:
"obsidian"` (`tracker.kind` in `crew.json`) plus a vault path that exists and
holds `.obsidian/`. The board is a markdown file the
[Kanban plugin](https://github.com/mgmeyers/obsidian-kanban) round-trips, so
crew writes files and Obsidian draws a board — there is no API, no auth, and no
payload to amortise.

```
vault/
  Boards/<repo>/
    Board.md          # kanban-plugin: board
    T-0042.md         # the ticket note
    T-0041.md
```

**One interface, called by the lifecycle itself.** `hooks/scripts/crew_tracker.py`
is the only code that writes a tracker, and the lifecycle commands call it at
their status transitions — no sync command to remember:

| Command | Call | Lane |
|---|---|---|
| `/crew:brainstorm` | `create` (INDEX row, card, ticket note); on approval `move --to ready` | Backlog |
| `/crew:spec`, `/crew:plan` | `move --to spec`, `move --to planned` | Ready |
| `/crew:implement` step 1 | `move --to in-progress` | In Progress |
| `/crew:implement` step 6, before `/crew:review` | `move --to review` | Review |
| `/crew:done` | `move --to done` | Done |

`/crew:fix` makes the same calls, compressed. `resolve` reads the kind from
`.crew/config.json` (`tracker`) and, in a repository that ran `/crew:migrate`,<!-- claim: crew-config-file:config.json -->
`.crew/crew.json` (`tracker.kind`) alike; when both state one and they differ it says `could not tell`
and every write refuses — it never picks one. The same holds for the vault and
`boardDir` each file *yields*, fallbacks included: crew.json falling back to
`memory.vaultPath` while config.json names another vault is `could not tell`,
not a quiet write to the memory vault. Jira and ServiceDesk Plus are pushed at
the boundaries only: `move --to in-progress` and `--to done` answer `delegated`
with `/crew:jira-sync <KEY> --push --to <status>` (or `/crew:sdp-sync`), which
the model runs because a script cannot call an MCP tool; every other move
prints `nothing to push`.

**Forward only, unless you say otherwise.** A move backwards by the lifecycle
order (`direction`, `ready`, `spec`, `planned`, `in-progress`, `review`,
`done`) exits 1 unless `--reopen` is passed, and so does a move from a status
crew does not know (`merged`, say), because whether it goes backwards cannot be
told. `/crew:implement` passes `--reopen` on a successor plan.

**Archive (L-0509).** `crew_tracker.py archive --ticket <ID>` moves ONE done or
merged ticket out of the lanes, in three halves, one line each: the folder
`.work/tickets/<ID>/` to `.work/tickets/Complete/<ID>/`; under obsidian the note
`<boardDir>/<ID>.md` to `<boardDir>/Complete/<ID>.md`, only when the note says
the card is this repo's, through the same no-follow directory walk as every
vault write; then the card's whole span off the Done lane through the atomic
board write. It refuses unless INDEX says `done` or `merged`, refuses a ticket
any worktree's active-ticket pointer names (or when that map cannot be read),
refuses a card in any lane but Done, and never renames over an existing
destination. Every vault check runs before the folder moves. Each half is
idempotent (`unchanged`), so a re-run after a crash completes the rest; a failed
half stops the ones after it. INDEX.md is never edited: the row keeps its
status, which keeps the id taken. jira and sdp archive the folder only. After
it, `read` reports the ticket archived (lane `Complete/`), `move` refuses it
(`--reopen` included: un-archiving is by hand), and `create` treats its id as
taken. The note's `ticket:` link to the live folder goes stale; the note is
never rewritten, and `[[ID]]` links resolve by name. The one-time archive of
the existing done tickets is an ops step run after this release, one
`archive` per ticket, never part of the code.

**A tracker write never undoes a transition.** A write that fails prints
`could not update: <reason>` and exits 1; the command tells you "tracker not
updated" and the phase stands.

**Confined to the vault, atomic, and loud.** Before anything is written —
`INDEX.md` included — the vault must exist and hold `.obsidian/`, `boardDir`
must be relative with no `..`, `board` a bare file name, the board and note must
not resolve out of the vault through a symlink, and a board or note inside the
worktree must be ignored by git (otherwise it would enter the review bundle) —
checked per file, so a vault that *contains* the repo is caught too. Any of
those fails, the board lacks its frontmatter key, a configured lane is
missing or doubled, or the done lane lacks exactly one `**Complete**`: exit 1,
nothing written anywhere. Board writes are an
exclusively created temp file (a link planted at its name is never followed)
plus `os.replace`, keeping the board's mode and owner, re-reading the board
first and recomputing if Obsidian saved it meanwhile. Every vault write reaches
its directory from the vault root one component at a time with
`O_DIRECTORY|O_NOFOLLOW` and writes relative to that directory, so a directory
swapped for a link after the checks is refused rather than written through.
Every directory from the vault down is also matched against the one the checks
found (T-0081): by device and inode on POSIX, by volume and file id on Windows,
so a real directory renamed away and replaced by another, even a byte-identical
copy, is refused too. An identity that cannot be told (none recorded, or an
inode or file id of 0) refuses as "could not tell", never "the same".
That fd follows its directory if it is renamed out of the vault, so the walk is
repeated and matched by device and inode before the temp is written, before the
replace and after it; a note that landed in a directory that left is removed
through the fd. Windows has no such calls, so it holds the directories instead (since 1.0.49, T-0077): it opens a handle on the vault and on every directory down to the target, each denying `FILE_SHARE_DELETE`, and keeps them open for the length of the write, so the OS refuses to rename any of them meanwhile. A handle that is a reparse point, not a directory, the wrong vault, or has no file id is refused (no file id is "could not tell", never "the same"), and the path is still re-checked against the held directory's id at the same three points.
A platform with neither mechanism refuses the write. On POSIX a move inside the last window
remains a residual race; on Windows the held handles close it.

**Whose card.** The ticket note is written once and never rewritten, and
records `repo-id:` — the origin URL with `.git` dropped and only its scheme and
host (with the port) case-folded, or the git common dir's real path when there is no origin or the origin is a relative path
(`../origin/app.git` from `a/app` and `b/app` is one string naming two
repositories). The ssh username and the path keep their case (since T-0071):
`ssh://Alice@host/~/repo.git` and `ssh://alice@host/~/repo.git`, or
`https://host/Team/Repo` and `https://host/team/repo`, are two owners. A note an
older crew wrote for an origin with capitals in its user or path holds the
all-lowercase id and is refused like any foreign note; the refusal says so and
names the fix, `repo-id: <this repo's id>`, which you edit in by hand — crew
never accepts the old id on its own, because it is exactly the ambiguous one.
An ssh origin keeps its username and drops only a password:
`alice@host:repo.git` and `bob@host:repo.git` are two users' repositories. Every
other scheme drops the whole userinfo, because `https://<token>@host/...` puts a
token where a username goes and the id is written into a note a human reads. A
local origin is its real path, and a `file://` one is percent-decoded first, as
git decodes it: `file:///srv/a%20b.git` is `/srv/a b.git`. A `file://`
authority is not path text: on POSIX any authority is dropped, as git drops it,
so `file:///srv/app.git`, `file://localhost/srv/app.git` and `/srv/app.git` are
one owner; on Windows an empty or `localhost` authority is dropped with the `/`
before a drive letter (`file:///C:/repos/app.git` is `C:/repos/app.git`), and any
other authority keeps the common-dir identity (git for Windows not measured).
A quote around the note's `repo-id:` value is stripped only as a matched pair
(`"<id>"` or `'<id>'`); a lone quote is part of the id. An id that itself begins
and ends with the same quote character loses that pair when read back.
Never the directory's name: `a/app` and `b/app` share that. With `boardDir` unset every
repo shares one board, so a note naming another repo refuses `create`, `move`
and `read`. A card whose owner cannot be told — no note, a note with no
`repo-id:` — refuses `create` and `move` (`read` says so on its line), naming
the fix: put `repo-id: <this repo's>` in the note. There is no exception: ids
start over in every repo and titles repeat, so a card's text matching this
repo's INDEX row proves nothing. `create` refuses an id INDEX already holds —
read before the vault, so a vault failure never hides it — whatever its title,
and an id the board holds for another or an unknown repo. Its claim on a new id
is the note's exclusive creation, before the INDEX row and the card: a note
another repo creates after the owner check makes the claim fail, and nothing
follows it. Each refusal begins `id taken`, and `/crew:brainstorm` and
`/crew:fix` then take the next free id; any other failed `create` stops them
before anything is written under that id. A `move` whose INDEX
half refuses — another session moved the ticket on meanwhile — leaves the
board alone, and a card already in its lane is repaired in place (checked in
Done, below `**Complete**`; unchecked elsewhere; a card with no checkbox gets one,
and a marker glued to its text, `- [ ]T-0042`, is given its space). The board
half places the card where INDEX has the ticket when the board is written, not
where the call meant to put it, and reads INDEX again after the write, so two
overlapping moves leave the board and INDEX agreeing (since T-0071; the line
says `(INDEX moved on to <status>)`). INDEX unreadable or holding an unknown
status at that point leaves the board alone: `could not tell where INDEX has`.

**There is no `.work/cache/` mirror.** The ticket's content lives in
`.work/tickets/<id>/` (or `.work/tickets/Complete/<id>/` once archived) for
every mode; the board carries status only. The key keeps the `LETTERS-digits`
shape, any prefix (`T-`, `L-`, `W-`), so nothing else in crew needed a new
format; a new ticket takes the next number above every id in `.work/INDEX.md`
with the prefix this box mints.

**Unlike Jira and ServiceDesk Plus, this mode also keeps `.work/INDEX.md`.**
The session brief finds the open ticket by reading that file, and a key shaped
`SDP-40219` was never going to be in it — `T-0042` can be. So the board is the
human's view of the work and `INDEX.md` is the session's; the same `move`
writes both, and each half reports its own result.

**Five lanes, named by `obsidian.columns`.**

| Lane | Means |
|---|---|
| Backlog | Deferred or untriaged. Where a non-blocking finding is parked. |
| Ready | Scoped by `/crew:spec` and pickup-able. |
| In Progress | `/crew:implement` has it. |
| Review | Implementation done, `/crew:review` outstanding. |
| Done | Complete and verified. Carries the `**Complete**` marker. |

Dragging a card is yours to do; crew does not read it back as status.
`/crew:obsidian-sync $1` shows the board lane beside the INDEX status and says
when they disagree; `--push` moves the card to the lane the INDEX status names
and reports the lane it came from. Both sides are local markdown and both look
equally authoritative — which makes the divergence hazard *worse* than Jira's,
not absent — so a silent fallback to file tickets is refused the same way
`/crew:jira-sync` refuses it.

**The board file has three load-bearing parts** and a naive rewrite destroys all
three, after which the file silently opens as plain text instead of a board: the
`kanban-plugin: board` frontmatter, the trailing `%% kanban:settings` block, and
the `**Complete**` marker in the done lane. An archive, when one exists, sits
below a `***` break under `## Archive` and is nobody's business but Obsidian's.
So `crew_tracker.py` cuts one card and inserts it under the target heading;
every other byte, the archive included, is the byte it read.

**Two things to accept before choosing this.** The vault lives outside the repo,
so ticket state does not travel with a branch and is not on a colleague's
machine — that is the trade for a board you can drag cards on. And crew never
commits the vault; if it is versioned, its history is yours to manage, and a
board edited in two places at once conflicts the way any markdown file does.
