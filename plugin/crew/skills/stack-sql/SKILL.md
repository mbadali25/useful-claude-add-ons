---
name: stack-sql
description: |
  SQL Server, MySQL and PostgreSQL pitfalls, checks and verify.json wiring - sargability,
  NULL semantics, per-engine locking and isolation defaults. Use when the repo has a
  migrations directory or *.sql files, or the user asks to write or review a query, an index
  change, or a migration, or asks why a query is slow or a migration might lock a live table.
---

# Stack: SQL (SQL Server / MySQL / PostgreSQL)

## When this applies

Any repo with a migrations directory, a connection string, or `*.sql` files. Establish the
engine and major version before writing anything - a migrations tool, a docker-compose
service, or a dialect tell in existing `.sql` files. Do not write ANSI-flavoured SQL and hope;
ask if it cannot be established. The three engines below disagree on locking, NULLs and
isolation in ways that make a rule true on one and wrong on another.

## Pitfalls that cost time (all three engines)

- **An index is not used because it exists.** A function or cast on the indexed column
  (`WHERE lower(email) = ?`, a `date` vs `timestamp` compare) makes the predicate
  non-sargable against a plain column index - the plan falls to a scan. An expression index
  on `lower(email)` serves that predicate exactly; leading-column order in a composite index
  decides which queries it serves at all.
- **`NULL` is not a value and does not compare.** `NOT IN (subquery)` returns no rows the
  moment the subquery yields one NULL; `= NULL` is never true; an outer join filtered in
  `WHERE` instead of `ON` is an inner join wearing the wrong name.
- **`SELECT *` in a join defeats covering indexes**; `OFFSET` deep in a large table re-reads
  everything it skips - keyset pagination is the fix.
- **Dynamic SQL is an injection sink even inside a stored procedure.** Parameterise; allow-list
  any identifier that genuinely must be dynamic.

## Per-engine locking and isolation

- **PostgreSQL**: `ACCESS EXCLUSIVE` on most `ALTER TABLE` forms - the danger is the queue
  behind a long `SELECT`, not the duration. `ADD COLUMN` with a non-volatile default is
  metadata-only; `CREATE INDEX CONCURRENTLY` avoids the write lock but cannot run in a
  transaction and leaves an invalid index behind on failure. Default isolation `READ
  COMMITTED`; readers never block writers.
- **MySQL/InnoDB**: no transactional DDL - a multi-statement migration that fails partway
  leaves the earlier statements committed. State the algorithm (`ALGORITHM=INSTANT,
  LOCK=NONE`) so a non-qualifying statement fails loudly instead of silently copying the
  table. Default isolation `REPEATABLE READ`; a read-modify-write in a long transaction acts
  on a stale snapshot.
- **SQL Server**: DDL is transactional. `ONLINE = ON` index rebuilds are Enterprise-only - a
  migration proven online on a Developer-edition box is a blocking rebuild on Standard.
  `ALTER COLUMN` on a fixed-width type takes a schema modification lock that blocks readers
  even under snapshot isolation. Default `READ COMMITTED` uses shared locks unless RCSI is on
  (Azure SQL Database defaults it on; the box product does not).

Uniqueness differs too: SQL Server permits one NULL in a unique index, Postgres and MySQL
permit many. A migration is reviewed only once it has actually been applied to a real
database (ephemeral, container, or dev) with rollback proven, not "it will apply at deploy
time" - see `crew:dba` if this crew has that role for the review side of this.

## Verification

Get the plan, not an opinion: `EXPLAIN (ANALYZE, BUFFERS)` (Postgres), `EXPLAIN ANALYZE`
(MySQL 8), or `SET STATISTICS IO, TIME ON` plus the actual plan (SQL Server). A plan on an
empty or thousand-row table proves nothing - say so rather than quoting one that does not
apply to production cardinality.

## verify.json rule to propose

```json
{
  "paths": ["**/*.sql"],
  "run": [
    "sh -c 'command -v sqlfluff >/dev/null 2>&1 || { echo \"TOOL MISSING: sqlfluff is not on PATH, so the lint pass DID NOT RUN. This is a missing tool, not a passing or failing check. Install sqlfluff to check locally.\" >&2; exit 77; }; sqlfluff lint --dialect tsql .'"
  ],
  "reach": "local",
  "why": "sqlfluff catches dialect and style drift before a human reviews the diff"
}
```

Swap `tsql` for `mysql`/`postgres` to match the engine established above. Nothing in this
repo writes rules into `verify.json` on a skill's behalf (see `crew-verification`) - add by
hand.

## LSP

No official SQL LSP plugin is decided for crew 1.0.
