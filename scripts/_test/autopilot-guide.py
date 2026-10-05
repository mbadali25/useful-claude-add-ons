#!/usr/bin/env python3
"""Every owner-requested example is in the /crew:autopilot guide (T-0054).

The guide's source is `docs/guides/crew/src/autopilot.md` and its built HTML
is `docs/guides/crew/crew-autopilot.html` (version-free name, C-0006). A
LANDED row's key phrases must be in both: the source, and the HTML with its
tags stripped, entities unescaped and whitespace collapsed, so a stale build
fails too. A COMING row's ticket ids and phrase must be in the source's
"What is coming" table, not merely somewhere in the guide.

When a coming ticket lands, its own PR moves its row to LANDED and writes the
section. A missing file is a failure naming the file, never a pass. Reads two
files as text; imports neither crew code nor `markdown`.

Run: python3 scripts/_test/autopilot-guide.py
"""

from __future__ import annotations

import html
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join("docs", "guides", "crew", "src", "autopilot.md")
BUILT = os.path.join("docs", "guides", "crew", "crew-autopilot.html")

# (id, example, key phrases) - landed: in the source and in the built HTML.
LANDED = (
    ("1", "arming", ('"mode": "plan"', "maxPhases", "crew_autopilot.py settings --root .",
                     "mode=plan maxPhases=12 deploy=none", "approval=risk questions=risk")),
    ("2", "armed, first phase is spec", ("Its first phase is spec", "ABC-510",
                                         "direction-approval")),
    ("3", "approving", ("/crew:approve", "stale", "T-0010..T-0012")),
    ("4", "policies", ("human", "self", "risk", "scope.allowCliApproval", "self-approved")),
    ("5a", "status", ("/crew:autopilot status", "waiting on:")),
    ("5b", "assign from the command line", ("crew_ticket.py assign", ".work/autopilot/")),
    ("5e", "focus (T-0020)", ("/crew:autopilot focus", "focus off")),
    ("6", "resume after /clear", ("resume: /crew:autopilot", "/clear")),
    ("6b", "resume typed into its own session (T-0013)", ("auto-resume",)),
    ("8", "ship as a PR or a merge (T-0011)", ("crew_autopilot.py ship", "autopilot.ship: merge")),
    ("9", "sleep mode (T-0053, L-0652)", ("/crew:autopilot sleep", "/crew:autopilot wake",
                                          "autopilot.sleep.schedule")),
    ("7", "Telegram pings (T-0051)", ("Telegram",)),
    ("11b", "plain-text continue", ("route.enabled", "keep going")),
    ("11c", "plain-text phrases for autopilot commands (T-0057)", ("what is autopilot doing",
                                                                  "heading to bed")),
    ("12", "deploy policy", ("autopilot.deploy", "deploy-allowed",
                             "environments.prodUnattended")),
    ("13", "review stops and auto-accept", ("review-acceptance", "--auto-accept")),
)

# (id, example, ticket ids, phrase) - in the "What is coming" table.
COMING = (
    ("3c", "approving a goal's split", ("T-0012",), "goal:<slug>"),
    ("5c", "/crew:autopilot assign route", ("L-0611",), "assign"),
    ("5d", "goal", ("T-0012", "L-0541"), "goal"),
    ("5f", "wave", ("T-0029",), "wave"),
    ("5g", "split, PR slices", ("T-0052", "T-0058", "T-0059"), "split"),
    ("10", "a goal survives /clear, a branch switch and a crash", ("T-0056",), "--goal"),
    ("11", "the full goal walkthrough", ("T-0012", "L-0541"), "walkthrough"),
)


def flat(text: str) -> str:
    return " ".join(text.split())


def html_text(raw: str) -> str:
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    return flat(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def coming_rows(source: str) -> list[str]:
    """The data rows of the source's "What is coming" table."""
    match = re.search(r"^## What is coming\s*$(.*?)(?=^## |\Z)", source, re.M | re.S)
    if not match:
        return []
    rows = [line for line in match.group(1).splitlines() if line.startswith("|")]
    return rows[2:]  # past the header and its |---| line


def check(root: str) -> list[str]:
    """Problems, each naming the example or file; empty when every row holds."""
    texts = {}
    for label, rel in (("source", SOURCE), ("HTML", BUILT)):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                texts[label] = fh.read()
        except OSError as exc:
            return [f"{rel}: cannot read the guide {label} ({exc.__class__.__name__})"]
    source, built = flat(texts["source"]), html_text(texts["HTML"])
    problems = []
    for num, example, phrases in LANDED:
        for phrase in phrases:
            if phrase not in source:
                problems.append(f"example {num} ({example}): {phrase!r} missing from {SOURCE}")
            elif phrase not in built:
                problems.append(f"example {num} ({example}): {phrase!r} missing from {BUILT} "
                                "(stale build? rebuild with build.py --guide autopilot)")
    rows = coming_rows(texts["source"])
    if not rows:
        problems.append(f"{SOURCE}: no '## What is coming' table")
    for num, example, tickets, phrase in COMING:
        # One row must carry every ticket id AND the phrase: the same ids in
        # other rows do not stand in for a removed row.
        # The row's Ticket cell names every id and its Phrase cell is exactly the
        # backticked phrase (`goal` must not be satisfied by "the full goal walkthrough").
        def holds(row, tickets=tickets, phrase=phrase):
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            return (len(cells) >= 3 and all(t in cells[1] for t in tickets)
                    and cells[2] == f"`{phrase}`")
        if not any(holds(row) for row in rows):
            problems.append(f"coming example {num} ({example}): no 'What is coming' row with "
                            f"{', '.join(tickets)} and `{phrase}`")
    return problems


# ---- the suite's own cases, on throwaway copies --------------------------------

def _copy(tmp: str) -> str:
    root = os.path.join(tmp, "repo")
    for rel in (SOURCE, BUILT):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copy(os.path.join(REPO, rel), os.path.join(root, rel))
    return root


def _edit(root: str, rel: str, old: str, new: str) -> None:
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if old not in text:
        raise AssertionError(f"fixture: {old!r} not in {rel}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace(old, new))


def _html_escape(text: str) -> str:
    return html.escape(text, quote=False)


def must_fail_landed_phrase_removed(root):
    _edit(root, SOURCE, "Its first phase is spec", "Its first step is spec")
    return "example 2"


def must_fail_stale_build(root):
    _edit(root, BUILT, "Its first phase is spec", "Its first step is spec")
    return "stale build"


def must_fail_coming_id_removed(root):
    _edit(root, SOURCE, "| T-0029 |", "| |")
    return "coming example 5f"


def must_fail_coming_id_only_elsewhere(root):
    _edit(root, SOURCE, "| T-0056 |", "| |")
    _edit(root, SOURCE, "## When something looks wrong", "T-0056 is mentioned here.\n\n"
          "## When something looks wrong")
    return "coming example 10"


def must_fail_coming_row_removed(root):
    # Its ids and phrase all still appear in other rows.
    _edit(root, SOURCE, "| A goal across several tickets | T-0012, L-0541 | `goal` |\n", "")
    return "coming example 5d"


def must_fail_source_missing(root):
    os.remove(os.path.join(root, SOURCE))
    return SOURCE


def must_fail_html_missing(root):
    os.remove(os.path.join(root, BUILT))
    return BUILT


def must_pass_committed(root):
    del root


def must_pass_phrase_split_across_a_wrap(root):
    _edit(root, SOURCE, "Its first phase is spec", "Its first phase\nis spec")


def must_pass_phrase_in_a_fence(root):
    _edit(root, SOURCE, "`continue`, `keep going`", "`continue`, `go on`")
    _edit(root, SOURCE, "## Command table", "```text\nkeep going\n```\n\n## Command table")


CASES = (
    (must_fail_landed_phrase_removed, True), (must_fail_stale_build, True),
    (must_fail_coming_id_removed, True), (must_fail_coming_id_only_elsewhere, True),
    (must_fail_coming_row_removed, True),
    (must_fail_source_missing, True), (must_fail_html_missing, True),
    (must_pass_committed, False), (must_pass_phrase_split_across_a_wrap, False),
    (must_pass_phrase_in_a_fence, False),
)


def main() -> int:
    failures = 0
    problems = check(REPO)
    rows = [(num, example) for num, example, _ in LANDED] + \
        [(num, example) for num, example, _, _ in COMING]
    for num, example in rows:
        mine = [p for p in problems if re.search(rf"example {re.escape(num)} \(", p)]
        print(f"{'FAIL' if mine else 'PASS'} example {num}: {example}")
        for p in mine:
            print(f"     {p}")
    other = [p for p in problems if not re.search(r"example \S+ \(", p)]
    for p in other:
        print(f"FAIL {p}")
    failures += len(problems)
    for case, should_fail in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = _copy(tmp)
                needle = case(root)
                got = check(root)
                if should_fail:
                    ok = bool(got) and any(needle in p for p in got)
                else:
                    ok = not got
            except (OSError, AssertionError) as exc:
                ok, got = False, [f"{type(exc).__name__}: {exc}"]
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} case {case.__name__}" + ("" if ok else f": {got}"))
    print(f"\nautopilot-guide: {'FAIL' if failures else 'OK'} "
          f"({len(rows)} examples, {len(CASES)} cases)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
