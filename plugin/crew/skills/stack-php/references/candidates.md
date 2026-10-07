# PHP candidate standards (not gated)

No gated PHP standards set ships yet (L-0533). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence. A rule is promoted once three distinct reviewed change sets earn it, into
`crew-standards/references/php.md` (set `PHP`, `applies-to: ["**/*.php", "**/*.phtml"]`).
Framework-specific rules stay out of the plugin set. They belong in a repository's own
overlay.

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message or CHANGELOG entry records that a review
found the defect. There is no file-type condition, and a clean audit that found nothing
is not a finding. The evidence the spec relies on is the owner's research (PHP-01..PHP-20
and a short list of left-out candidates) and review-recorded fix commits in one PHP 8.3 /
MariaDB codebase the owner holds privately. **Owner-private evidence was not consulted.
The re-check is tracked as C-0020.** The owner decided on 2026-10-05 that public
third-party change sets do not count. The rules below come from a public pass on
2026-10-05, and each public change set is a lead counted 0.

**How the public pass read its evidence.** Commit messages came from GitHub commit
search. Diffs were not read. Most public change sets are WordPress plugins: each rule is
written framework-neutral, but its evidence leans on WordPress. Every Source sentence was
string-matched against the raw php.net page on 2026-10-05. PHP-01 is the owner's research
id, which L-0532's direction describes as supplementing the SQL parameterisation rule.
Mapping it to the rule below is inferred. `PHP-Pn` are labels from the public pass, not
research ids.

## Candidate standards (not gated)

### PHP-01 Every SQL value goes through the driver's bound parameters or the framework's placeholder API, and identifiers come from an allow-list (research id inferred)

Counted toward the bar: unknown (owner-private evidence not consulted; C-0020).
3 public change sets, which do not count, all WordPress plugins.

Values reach SQL only through the driver's bound parameters (PDO or mysqli prepared
statements, with a generated placeholder list for `IN (...)`), or, where a framework offers
no binding, through its placeholder API: WordPress's `$wpdb->prepare` substitutes escaped
values into the SQL string rather than binding them. Never concatenate, even after
`esc_sql` or `real_escape_string`. An identifier (an `ORDER BY`
column, a table) comes from a fixed allow-list. A query with no values at all is a fixed
literal: it is never assembled by the same string-building code that handles values (with
WordPress, which wants at least one placeholder in `prepare`, it is passed as it is).

Public change sets (message text only):
- `immosuite-79e94957` (dbwmedia/Immo-Suite@79e94957): "fix review findings — ... Harden
  SQL order clause with $wpdb->prepare() for meta key values".
- `logindelay-162ab78c` (mikedamoiseau/login-delay-shield@162ab78c): "address code review
  findings ... Always use $wpdb->prepare() (remove raw SQL path when params empty)".
- `404solution-3b3989e7` (aaron13100/404solution@3b3989e7): a pre-release design review
  found an `IN (...)` list built by `esc_sql()` plus string concatenation instead of
  `$wpdb->prepare()`.

Leads not counted: two where it could not be determined whether a review, not a tool,
found the defect, two with no review marker, and one whose audit finding was disputed and
never fixed.

Source: https://www.php.net/manual/en/pdo.prepared-statements.php: "If an application
exclusively uses prepared statements, the developer can be sure that no SQL injection
will occur (however, if other portions of the query are being built up with unescaped
input, SQL injection is still possible)."

The Source covers driver binding. The public evidence is all WordPress's placeholder API,
which is escaping, not binding. Public verdict: admitted on public stand-ins (3, all
WordPress). That does not count under the owner's decision.

### PHP-P1 Never `unserialize()` data an attacker can influence: decode it as JSON

Counted toward the bar: unknown (owner-private evidence not consulted; C-0020).
4 public change sets, which do not count.

This is probably the spec's left-out "untrusted-input `unserialize`" candidate. Data from
a request, cookie, cache, queue or database column that another party can write is
decoded with `json_decode`, not `unserialize` or `maybe_unserialize`. `allowed_classes`
is not a defence for such data: the manual says it is unsafe for untrusted input whatever
the option. For serialized data only trusted code wrote, pass `['allowed_classes' => false]`
or an explicit class list and check the result's type.

Public change sets (message text only):
- `askmydocs-29d98922` (lopadova/AskMyDocs@29d98922): a Copilot PR review found a queued
  job unserialized without `allowed_classes`, which left object injection open.
- `slimstat-87b8ba52` (wp-slimstat/wp-slimstat@87b8ba52): "security improvements from PR
  review - Remove maybe_unserialize() backward compatibility to prevent PHP Object
  Injection".
- `luna-551e9816` (jeromev/Luna@551e9816): a code-review pass moved cookies to
  `json_encode`/`json_decode` and guarded `unserialize()` against object payloads.
- `wpbutler-7437580b` (tripex/WP-Butler-Search-replace@7437580b): a plugin-directory review
  blocker. `unserialize` is now limited to `stdClass`.

Source: https://www.php.net/manual/en/function.unserialize.php: "Do not pass untrusted
user input to unserialize() regardless of the options value of allowed_classes."

Two reviews plainly found attacker-influenced data reaching `unserialize`, and their fixes do
what this rule asks: slimstat drops `maybe_unserialize`, and Luna moves cookies to JSON. The
other two (AskMyDocs, which restricts `allowed_classes` on a queued job, and WP-Butler, which
limits stored payloads to `stdClass`) found unrestricted `unserialize` calls and hardened
them. From the commit messages alone, who could write that data could not be determined. The
public pass's verdict was "admitted on public stand-ins (4)". On this reading it is 2 clear
findings plus 2 whose input provenance is unknown. Either way, public change sets do not count
under the owner's decision.

### PHP-P2 Escape output for its context at every echo of request or stored data

Counted toward the bar: unknown (owner-private evidence not consulted; C-0020).
2 public change sets, which do not count.

HTML text and quoted attribute values use `htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE,
'UTF-8')`. An attribute value is always quoted, because in an unquoted attribute a space in the
data starts a new attribute that this escaping leaves untouched. Event-handler and `style`
attributes, URLs and JavaScript use their own encoders, or take no untrusted data.

Public change sets: `sanskrit-e660dc37` (sanskrit-lexicon/csl-websanlexicon@e660dc37), where
a security review found a query parameter echoed raw into an HTML attribute, and
`luna-551e9816` (as above), where a code review found a requested path reflected without
`htmlspecialchars()`.

Source: https://www.php.net/manual/en/function.htmlspecialchars.php: "Certain characters have
special significance in HTML, and should be represented by HTML entities if they are to
preserve their meanings." Public verdict: candidate (2).

### PHP-P3 Security decisions use strict comparison (`===`, `in_array(..., true)`, `hash_equals`)

Counted toward the bar: unknown (owner-private evidence not consulted; C-0020).
0 public change sets found.

Source: https://www.php.net/manual/en/function.in-array.php: "Searches for needle in
haystack using loose comparison unless strict is set." Public verdict: candidate (0).

## Not assessed

PHP-02 to PHP-20 and the research's other left-out candidates are the owner's research
ids. Their content and counts are in the owner's research and private repository, which
were not consulted (C-0020). Whether PHP-P1, -P2 or -P3 duplicates one of them could not
be determined.
