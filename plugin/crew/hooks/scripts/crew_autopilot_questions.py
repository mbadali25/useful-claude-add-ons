"""questions.md's block parser for `/crew:autopilot`'s questions policy (T-0010).

Moved unchanged out of `crew_autopilot.py` to keep it under pylint's 3400-line
cap when G6b met release/1.2.0. `crew_autopilot` keeps the name
`_question_blocks` (its `questions_check` and `crew_wave` call it there); the
three patterns had no other reader. Imports nothing from crew_autopilot.
Standard library only.
"""

from __future__ import annotations

import re

Q_RE = re.compile(r"^##[ \t]+Q([0-9]+)\b[ \t]*:?[ \t]*(.*)$")
OPTION_RE = re.compile(r"^###[ \t]+Option[ \t]+([A-Za-z0-9]+)\b(.*)$")
TAKEN_RE = re.compile(r"^taken:[ \t]*(.*?)[ \t]*$")


def question_blocks(text):
    """[(number, title, preamble, options, taken)] -- each `## Q<n>` section;
    `options` is [(id, rest, lines)], `taken` every `taken:` value in it. A
    `#`/`##` heading that is not a question ends the section."""
    blocks, current, option = [], None, None
    for line in (text or "").splitlines():
        found = Q_RE.match(line)
        if found:
            current = (found.group(1), found.group(2).strip(), [], [], [])
            blocks.append(current)
            option = None
            continue
        if re.match(r"^#{1,2}[ \t]", line):
            current = option = None
            continue
        if current is None:
            continue
        taken = TAKEN_RE.match(line)
        if taken:
            current[4].append(taken.group(1))
            continue
        heading = OPTION_RE.match(line)
        if heading:
            option = (heading.group(1), heading.group(2), [])
            current[3].append(option)
            continue
        (option[2] if option is not None else current[2]).append(line)
    return blocks
