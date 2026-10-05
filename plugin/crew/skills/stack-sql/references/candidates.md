# SQL candidate standards (not gated)

No gated SQL standards set ships yet (L-0532). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence so that a rule can be promoted into `crew-standards/references/sql.md` (set `SQL`,
`applies-to: ["**/*.sql"]`) once three distinct reviewed change sets earn it.

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message records that a review found the defect.
The owner decided on 2026-10-05 that public third-party change sets do not count toward
that bar. The evidence the spec relies on is the owner's research (SQL-01..SQL-20) and
review-recorded fix commits in the owner's private repositories. **Owner-private evidence
was not consulted. The re-check is tracked as C-0020.** What follows comes from a public
pass on 2026-10-05. The public change sets are recorded as leads, each counted 0 toward
the bar.

**How the public pass read its evidence.** Commit messages came from GitHub commit
search. Diffs and changed paths were not read, so whether a fix touched a `.sql` file is
known only where the message names it. Every Source sentence was string-matched against
the raw page on 2026-10-05: PostgreSQL docs "Current (18)", and Microsoft Learn
`view=sql-server-ver17`. The MySQL documentation site failed to load during the pass, so
no MySQL/MariaDB rule or quote was checked.

**Ids.** `SQL-17` is the owner's research id, and the spec names its content. `SQL-Pn`
are labels from the public pass, not loader ids. Promotion gives a rule its research id,
once the owner's file is read. The other research ids are listed at the end as not
assessed.

## Candidate standards (not gated)

### SQL-P1 PostgreSQL: a `SECURITY DEFINER` function pins `search_path` and revokes `EXECUTE` from `PUBLIC`

0 counted. 6 public change sets, not counted.

Every `CREATE [OR REPLACE] FUNCTION ... SECURITY DEFINER` sets `SET search_path =
<trusted schemas>, pg_temp`, or `''` with fully qualified names. In the same transaction
it runs `REVOKE ALL ON FUNCTION ... FROM PUBLIC` and grants `EXECUTE` only to the roles
that need it. `CREATE OR REPLACE` does not keep an earlier `SET` clause, so state it again
every time. Without the pin, a caller can shadow an object the function uses and run it
with the definer's privileges. The default `EXECUTE` grant to `PUBLIC` makes the function
callable by every role.

Public change sets (message text only):
- `contatoatacadista-83e743a6` (felipebalcao/contatoatacadista@83e743a6): "pin search_path
  on security definer functions ... per code review finding".
- `avya-9f4a0e85` (upendraprasad19/AVYA@9f4a0e85): a quarterly audit found SECURITY DEFINER
  functions EXECUTE-able by anon/authenticated, and the fix revokes EXECUTE from PUBLIC.
- `ruins-45d93489` (coachtomlim/ruins-api@45d93489): a security review found two SECURITY
  DEFINER functions with `set search_path = public`. The fix is a new `.sql` migration.
- `miraya-79f8bfe6` (AbhinavGupta707/miraya@79f8bfe6): a deep review found 12 SECURITY
  DEFINER functions whose `search_path` lacked `pg_temp`.
- `butlers-c085070c` (tzeusy-org/butlers@c085070c): review feedback asked to pin
  `search_path` to the home schema plus `pg_temp`. The file type could not be determined.
- `mytube-33e58055` (ibnetsoft/mytube@33e58055): a static review of a `.sql` migration
  found EXECUTE granted to PUBLIC and no `SET search_path`.

Rejected leads: an issue sweep, two advisor or CI-tool findings, and one fix with no
review marker.

Source: https://www.postgresql.org/docs/current/sql-createfunction.html, "Writing SECURITY
DEFINER Functions Safely": "For security, search_path should be set to exclude any schemas
writable by untrusted users." "To do this, write pg_temp as the last entry in
search_path." "Another point to keep in mind is that by default, execute privilege is
granted to PUBLIC for newly created functions (see Section 5.8 for more information)."

Public verdict: admitted on public stand-ins (6). That does not count under the owner's
decision. Its research id would be SQL-19 or SQL-20, the PostgreSQL ids, but which one
could not be determined.

### SQL-P2 PostgreSQL: index a populated table `CONCURRENTLY`, in a migration that runs outside a transaction

0 counted. 3 public change sets, not counted, and 2 of them are known to be `.sql`.

`CREATE INDEX` on a table that already holds rows uses `CONCURRENTLY`, and `DROP INDEX
CONCURRENTLY` reverses it. `CONCURRENTLY` cannot run inside a transaction block, so the
migration opts out of the runner's wrapping transaction (for example sqlx's
`-- no-transaction` first line) and holds that one statement. An index created in the
same file as its new table needs neither. Builds this on the existing
`CREATE INDEX CONCURRENTLY` pitfall in `SKILL.md`.

Public change sets (message text only):
- `distantsignal-e667de01` (FasterSpeeding/Distant-Signal@e667de01), `.sql`: "Review
  finding: several migrations build a non-CONCURRENTLY index inside sqlx's default
  per-file transaction". The fix is a guard test.
- `mytube-33e58055` (as above), `.sql`: the same static review changed `CREATE INDEX` to
  `CREATE INDEX CONCURRENTLY` on a live table.
- `jidou-222cd2bd` (jamesbconner/Jidou@222cd2bd): "Two bugs found in code review: 1. CREATE
  INDEX CONCURRENTLY cannot run inside a transaction block". This one is an Alembic Python
  migration, outside `**/*.sql`.

Source: https://www.postgresql.org/docs/current/sql-createindex.html: "When this option is
used, PostgreSQL will build the index without taking any locks that prevent concurrent
inserts, updates, or deletes on the table; whereas a standard index build locks out
writes (but not reads) on the table until it's done." "Another difference is that a
regular CREATE INDEX command can be performed within a transaction block, but CREATE
INDEX CONCURRENTLY cannot."

Public verdict: candidate. The bar counts `.sql` changes, and only 2 of the 3 are `.sql`.
The research id could not be determined.

### SQL-17 SQL Server: session SET options are part of the change

0 counted. 0 public change sets found. The owner's private count is unknown.

Rule text from the public pass (the research's own wording was not read): a procedure,
view or index script that depends on `QUOTED_IDENTIFIER` or `ANSI_NULLS`
sets them explicitly in the script. The values in effect at `CREATE` time are stored with
the object and are not taken from the caller's session.

Source: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-quoted-identifier-transact-sql?view=sql-server-ver17:
"When you create a stored procedure, the SET QUOTED_IDENTIFIER and SET ANSI_NULLS settings
are captured and used for subsequent invocations of that stored procedure." "You must set
SET QUOTED_IDENTIFIER to ON when you create or change indexes on computed columns or
indexed views."

## Not assessed

SQL-01 to SQL-16 and SQL-18 to SQL-20 are the owner's research ids. SQL-01..-14 are
general, -15/-16 MySQL/MariaDB, -17/-18 SQL Server and -19/-20 PostgreSQL. Their content
and counts are in the owner's research and private repositories, which were not
consulted (C-0020). Whether SQL-P1 or SQL-P2 duplicates one of them could not be
determined.
