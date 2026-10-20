<!-- Moved verbatim from plugin/crew/README.md (18. Document maintenance) by L-0726; the README keeps an index entry. -->

## 18. Document maintenance

```
/crew:docs           # update what this change should touch, and only that
/crew:docs --audit   # report staleness everywhere, change nothing
```

**The default is: do not touch.** Updating every document on every change is how
documentation becomes noise — a CHANGELOG with an entry per typo fix is
unreadable, and a README rewritten every sprint stops being trusted.

So each document has a trigger condition, checked once per ticket by
`/crew:implement`:

| Document | Update when | Never |
|---|---|---|
| `CHANGELOG.md` | Observable behaviour changed | Refactors, formatting, renames |
| `README.md` | Setup, commands, or the mental model changed | Every ticket |
| `SECURITY.md` | Reporting process or supported versions changed | Routine security fixes |
| `TODO.md` | Something deferred, with a reason | As a substitute for tickets |
| `docs/adr/` | A decision with a real rejected alternative | Implementation detail |
| `docs/diagrams/` | The structure a diagram shows moved | Cosmetic changes |

"None of them" is the common and correct answer, and the command says so plainly
rather than finding something to write.

Before editing any markdown it checks for generated-block markers and, if the
target is inside one, edits the source instead and tells you which. That covers
terraform-docs, OpenAPI generators, and anything using `AUTO-GENERATED`.

Two specifics worth stating: CHANGELOG entries are written from the ticket and
the diff in user-facing language — "rejects files with a BOM," not "added BOM
strip in `validate_header()`" — and `SECURITY.md` never logs an unfixed
vulnerability, because a public file describing an open hole is a disclosure.

`--audit` is worth running monthly. It reports rather than fixes: bulk
documentation diffs are unreviewable, which means they get approved unread.
