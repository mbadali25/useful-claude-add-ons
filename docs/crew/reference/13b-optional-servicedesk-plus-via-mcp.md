<!-- Moved verbatim from plugin/crew/README.md (13b. Optional: ServiceDesk Plus via MCP) by L-0726; the README keeps an index entry. -->

## 13b. Optional: ServiceDesk Plus via MCP

Same bargain as Jira, a different desk, and one extra category of care.

`tracker: "sdp"` plus a reachable ServiceDesk Plus MCP connector (tools named
`sdp_*`). Crew ships no `.mcp.json` for it: the SDP connector is normally
registered at user or session scope, and a per-repo one would prompt for
approval in every repository where the plugin is enabled. If the tools are not
there, `/crew:sdp-sync` says so and stops rather than quietly writing a file
ticket — a silent fallback splits the source of truth and nobody notices until
two people are working from divergent state.

**The local key is `SDP-<id>`, not the bare request number.** SDP request ids are
plain integers, and the rest of crew recognises a ticket by its `LETTERS-digits`
shape — so a bare `40219` is invisible to `/crew:status`, to `/crew:implement`, and
to the index. `/crew:sdp-sync` accepts either form and always writes `SDP-40219`.

The caching argument is identical to Jira's: a request payload runs thousands of
tokens across resolution HTML, the full note history, SLA timers, approvals and
every UDF the desk has ever defined, and about forty of them affect what you
build. `/crew:sdp-sync` keeps id, subject, status, requester, priority, category
and the last three notes, and `/crew:implement` reads that file instead of the API.

**What is different from Jira, and worth knowing before the first write:**

| | Why it matters |
|---|---|
| Notes are requester-visible unless private | A requester is often not an engineer. `sdp.noteVisibility` defaults to `private`, and that is not a substitute for scrubbing: hostnames, credentials and internal addresses do not belong in a desk record either way. |
| A bad field value rejects the *whole* write | SDP does not partially apply an update. Resolve status, category and priority against `sdp_list_metadata` first and send what the desk accepts, not what the local ticket happens to call it. |
| Closing is somebody's job, not crew's | `sdp.closeOnDone` defaults to `false`: push transitions the request and leaves closure alone. Set it `true` only for a queue that is genuinely yours, and let `sdp_close` do it — it goes through the desk's closure endpoint and satisfies mandatory closure fields, which a faked `sdp_update` does not. |
| A failed write is gone | There is no local outbox. If a note fails it is not queued anywhere; re-read with `sdp_get` before retrying so a partial success is not duplicated. |

The writes act as the signed-in user, so the desk's audit trail names a person
rather than "an automation". `sdp_whoami` tells you which person, and is the
cheapest way to prove the connector is live before configuring a repo around it.
