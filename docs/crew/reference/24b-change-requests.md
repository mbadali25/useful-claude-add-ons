<!-- Moved verbatim from plugin/crew/README.md (24b. Change requests) by L-0726; the README keeps an index entry. -->

## 24b. Change requests

`/crew:change` files a change request. One process, three backends, selected by
the `tracker` you already use: ServiceDesk Plus against the
`change.sdpTemplate` template, Jira as a `change.jiraIssueType` issue, or
`.work/changes/<id>.md` in files mode. **The content is identical in all
three** — the wording lives once, in `skills/crew-change/SKILL.md`.

```
/crew:change new
/crew:change status CHG-40219
/crew:change close CHG-40219
/crew:change list
```

**The gate is the feature.** The ServiceDesk Plus Change Management Request
template prints its own rule above its ten questions — *ALL THE BELOW
QUESTIONS MUST BE ANSWERED. ANY PERTINENT MISSING INFORMATION WILL RESULT IN
THE REQUEST BEING DENIED* — and `new` refuses to file while any of questions
1–9 is unanswered or answered with a placeholder, naming which one and whether
the box was empty or held a non-answer. That check is
`hooks/scripts/crew_change.py`, a program with no I/O, not a paragraph asking
an agent to be careful: "I read them and they looked complete" is exactly the
unknown-wearing-the-label-of-a-check this repo keeps rediscovering. Question 10
is the post-change validation results, collected by `close`, which refuses
without them.

**Missing tooling is a stop, never a fallback.** If `tracker` is `sdp` and the
`sdp_*` tools are not connected, the command names the connection and stops. A
silent fall-through to a local file produces a change nobody on the change
board can see, sitting in a file, looking filed.

**Production promotion can require one.** `change.requireForProduction` ships
`false`, and at `false` nothing about `/crew:promote production` changes. At
`true`, gate 1 needs a change in an **approved** state for the sha being
promoted — read from the backend at that moment, never from the local cache or
from the session — and refuses outside the change's scheduled window. "Could
not read the state" is a stop, not a pass.

It is the one key in crew a repo may only turn **on**: it ratchets across the
two config layers like `install.policy` and the `guards.*` keys, but the
narrower value is `true`, so a machine-global `true` survives a `false` in a
repo you cloned. A value that is neither `true` nor `false` reads as `true`.
`docs/crew/config-rationale.md` ("change.requireForProduction") has the reasoning.
