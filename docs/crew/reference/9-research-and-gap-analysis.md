<!-- Moved verbatim from plugin/crew/README.md (9. Research and gap analysis) by L-0726; the README keeps an index entry. -->

## 9. Research and gap analysis

```
/crew:survey
/crew:survey the billing module
```

`crew:explorer` investigates, one pass per subsystem, and returns at most seven
findings, each with a file-and-line anchor, a concrete impact, and three options
where **option A is always "do nothing"** and is always a real option.

The failure mode it is written against is generic advice: "consider adding
caching," "error handling could be improved." That is what gets produced when
nothing was actually read, and it is worse than silence because it costs review
time and teaches you to skim.

It starts from evidence — `git log` file-change frequency, existing findings,
smoke gaps — rather than from a checklist, because the files that change
constantly are where the pain is.

It does not create tickets. You read the findings and decide; `/crew:brainstorm` is a
separate, deliberate step. A survey that automatically becomes a backlog is a way
of committing to seven things nobody agreed to.

Run it after the safety net exists, not before. Findings you cannot safely act on
are just a list.
