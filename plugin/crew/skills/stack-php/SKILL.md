---
name: stack-php
description: |
  PHP 8 pitfalls, checks and verify.json wiring - loose comparison, array key behaviour,
  bound SQL parameters, output escaping, unserialize, time zones - and PHP's candidate
  standards. Use when the repo has *.php files or a composer.json, or the user asks to write
  or review PHP, a PDO/mysqli query, a template that echoes data, or a composer change.
---

# Stack: PHP

## When this applies

Any repo with `*.php`/`*.phtml` files or a `composer.json`. Read `composer.json` (`require.php`,
the framework, autoload rules) and the PHP version the deploy target runs before writing
anything - PHP 8.0 changed string-to-number comparison, and 8.1+ features (enums, readonly
properties, first-class callables) do not parse on older hosts. Write in the idiom the repo
already uses: a framework's query builder, escaping helper or container wins over a hand-rolled one.

## Pitfalls that cost time

- **`==` compares after juggling types.** `"1e3" == "1000"` is true because both are numeric
  strings; `in_array()` and `array_search()` compare loosely unless the third argument is
  `true`. Security and identity decisions use `===`, strict `in_array(..., true)` and
  `hash_equals()` for secrets. `"abc" == 0` changed from true to false in PHP 8.0.
- **`empty("0")` is true.** So are `0`, `""`, `[]` and `null`. Test for the case meant:
  `isset`, `=== null`, `=== ""`, `count() === 0`.
- **Array keys survive more than expected.** `array_filter()` keeps the original keys, so
  when it removes anything but the tail, `json_encode()` emits an object, not a list - wrap
  it in `array_values()`.
  `array_merge()` renumbers integer keys; `+` keeps the left side's keys and drops the
  right side's duplicates.
- **SQL values go through the driver's bound parameters** (PDO/mysqli prepared statements)
  or, where the framework offers no binding, its placeholder API (WordPress's
  `$wpdb->prepare`) - never concatenation, even after an escaping call; identifiers come
  from an allow-list. Use `charset=utf8mb4` in a MySQL/MariaDB DSN.
  (Candidate PHP-01 in `references/candidates.md`.)
- **Output is escaped for its context at the point it is echoed** - HTML text and
  attributes with `htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')`; each value
  placed inside a URL (a path segment, a query value) with `rawurlencode`, never the whole
  URL, and the assembled URL then escaped for its HTML attribute; JavaScript with
  `json_encode` and the `JSON_HEX_*` flags. (Candidate PHP-P2.)
- **`unserialize()` instantiates objects.** Data another party can write is decoded with
  `json_decode`. (Candidate PHP-P1.)
- **`strict_types=1` is per file** and governs calls made from that file; a file without
  it still coerces `"5"` into an `int` parameter.
- **Strings are bytes.** `strlen`, `substr` and `strtoupper` count and change bytes; use
  the `mb_*` functions for text, with the encoding stated.
- **Time zones come from `php.ini` unless stated.** Pass a `DateTimeZone` explicitly and
  prefer `DateTimeImmutable` - `DateTime::modify()` changes the object every caller holds.
- **`composer.lock` belongs in an application's commit** (not a library's); a
  `composer update` in a feature change is a dependency change - say which packages moved.

## Standards

No gated PHP standards set ships yet (L-0533). This build showed no PHP rule with three
reviewed change sets that count: public change sets do not count (owner, 2026-10-05), and
the owner-private evidence, which may hold more, was not consulted (re-check: C-0020). When
earned, the set is `crew-standards/references/php.md`, set `PHP`, `applies-to:
["**/*.php", "**/*.phtml"]`. The candidates, their sources and public verdicts are in
`references/candidates.md`; they are guidance, not rows of the self-check.

## Verification

`php -l` proves only that a file parses. Run what the repo runs (PHPUnit, Pest, PHPStan or
Psalm at the repo's level) with the PHP version the deploy target uses, and report exit
codes, never the summary line. A query change is checked against a real database with the
production engine and charset, not SQLite.

## verify.json rule to propose

```json
{
  "paths": ["**/*.php", "**/*.phtml"],
  "run": [
    "sh -c 'command -v php >/dev/null 2>&1 || { echo \"TOOL MISSING: php is not on PATH, so the syntax check DID NOT RUN. This is a missing tool, not a passing or failing check. Install PHP to check locally.\" >&2; exit 77; }; [ -n \"$(git ls-files --cached --others --exclude-standard -- \"*.php\" \"*.phtml\")\" ] || { echo \"NO INPUT: no tracked or untracked .php/.phtml file, so the syntax check DID NOT RUN.\" >&2; exit 77; }; git -c core.quotePath=false ls-files --cached --others --exclude-standard -- \"*.php\" \"*.phtml\" | { rc=0; n=0; while IFS= read -r f; do if [ ! -e \"$f\" ]; then git ls-files --error-unmatch -- \"$f\" >/dev/null 2>&1 && continue; echo \"UNREADABLE: $f is listed but cannot be checked\" >&2; rc=1; continue; fi; n=$((n+1)); php -l \"./$f\" || rc=1; done; [ $n -gt 0 ] || [ $rc -ne 0 ] || { echo \"NO INPUT: every listed .php/.phtml path is missing from the worktree, so the syntax check DID NOT RUN.\" >&2; exit 77; }; exit $rc; }'"
  ],
  "reach": "local",
  "why": "php -l refuses a file that does not parse before a human reviews the diff"
}
```

PHPStan or Psalm is the stronger check where the repo already runs one. Nothing in this
repo writes rules into `verify.json` on a skill's behalf (see `crew-verification`) - add by
hand.

## LSP

No official PHP LSP plugin is decided for crew.
