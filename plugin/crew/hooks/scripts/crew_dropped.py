"""The 60 config keys L-0725 removed, each with the value it held by default and
the code constant that now stands in for it.

One table, three readers: `/crew:migrate` (a dropped key holding its default is
removed; one holding anything else is a conflict until the person accepts it),
`crew_config.inert_settings` (a config still carrying one is told the value has
no effect and what replaced it), and the tests that hold each constant to the
default recorded here. Nothing else lists the dropped keys.

`tier` and `roles` are the two retired keys: they were read only for display.
The other 58 never changed behaviour from a config in any measured layer (see
`.work/tickets/L-0725/spec.md`, Disposition), so each is now a constant in
`crew_state` at its old default.

Standard library only; no imports, so any module may use it.
"""

# dotted key -> (default it held, the constant that replaced it as
# `module.NAME`, or a note when the key was retired outright).
DROPPED = {
    "tier": (0, "retired: read only for display"),
    "roles": (["explorer", "reviewer"], "retired: read only for display"),
    "autopilot.ciTimeoutMinutes": (60, "crew_state.AUTOPILOT_CI_TIMEOUT_MINUTES"),
    "autopilot.knownFailures": ([], "crew_state.AUTOPILOT_KNOWN_FAILURES"),
    "autopilot.sleep.notifyHold": (None, "crew_state.AUTOPILOT_NOTIFY_HOLD"),
    "bitbucket.mergeGate.enabled": (False, "crew_state.MERGE_GATE_ENABLED"),
    "bitbucket.mergeGate.branch": (None, "crew_state.MERGE_GATE_BRANCH"),
    "bitbucket.mergeGate.preset": ("standard", "crew_state.BITBUCKET_MERGE_GATE_PRESET"),
    "github.mergeGate.enabled": (False, "crew_state.MERGE_GATE_ENABLED"),
    "github.mergeGate.branch": (None, "crew_state.MERGE_GATE_BRANCH"),
    "change.requester": (None, "crew_state.CHANGE_REQUESTER"),
    "change.implementor": (None, "crew_state.CHANGE_IMPLEMENTOR"),
    "change.sdpTemplate": ("Change Management Request", "crew_state.CHANGE_SDP_TEMPLATE"),
    "change.jiraIssueType": ("Change", "crew_state.CHANGE_JIRA_ISSUE_TYPE"),
    "change.category": (None, "crew_state.CHANGE_CATEGORY"),
    "context.autoClear.windowTitle": (None, "crew_state.AUTOCLEAR_WINDOW_TITLE"),
    "context.autoClear.command": ("/clear", "crew_state.AUTOCLEAR_COMMAND"),
    "context.autoClear.unsafeFocus": (False, "crew_state.AUTOCLEAR_UNSAFE_FOCUS"),
    "context.autoWrapUp": (True, "crew_state.CONTEXT_AUTO_WRAP_UP"),
    "context.autoResume": (True, "crew_state.CONTEXT_AUTO_RESUME"),
    "context.budgetTokens": (None, "crew_state.CONTEXT_BUDGET_TOKENS"),
    "context.handoffPath": (".work/HANDOFF.md", "crew_state.CONTEXT_HANDOFF_PATH"),
    "context.keepTranscripts": (5, "crew_state.CONTEXT_KEEP_TRANSCRIPTS"),
    "context.staleHandoff.maxAgeHours": (72, "crew_state.STALE_HANDOFF_MAX_AGE_HOURS"),
    "context.staleHandoff.maxCommitsBehind": (3, "crew_state.STALE_HANDOFF_MAX_COMMITS_BEHIND"),
    "docs.theme": (None, "crew_state.DOCS_THEME"),
    "docs.reportTheme": (None, "crew_state.DOCS_REPORT_THEME"),
    "emergency.ttlMinutes": (120, "crew_state.EMERGENCY_TTL_MINUTES"),
    "graph.enabled": (True, "crew_state.GRAPH_ENABLED"),
    "graph.tool": ("graphify", "crew_state.GRAPH_TOOL"),
    "graph.mode": ("code-only", "crew_state.GRAPH_MODE"),
    "graph.commitHook": (False, "crew_state.GRAPH_COMMIT_HOOK"),
    "memory.inject": (True, "crew_state.MEMORY_INJECT"),
    "memory.recall.vaults": ([], "crew_state.MEMORY_RECALL_VAULTS"),
    "memory.recall.maxChars": (800, "crew_state.MEMORY_RECALL_MAX_CHARS"),
    "memory.recall.projects": ([], "crew_state.MEMORY_RECALL_PROJECTS"),
    "notify.urlEnv": (None, "crew_state.NOTIFY_URL_ENV"),
    "notify.questionTypes": (None, "crew_state.NOTIFY_QUESTION_TYPES"),
    "notify.realertHours": (6, "crew_state.NOTIFY_REALERT_HOURS"),
    "obsidian.board": ("Board.md", "crew_state.OBSIDIAN_BOARD"),
    "obsidian.columns.backlog": ("Backlog", "crew_state.OBSIDIAN_COLUMNS"),
    "obsidian.columns.ready": ("Ready", "crew_state.OBSIDIAN_COLUMNS"),
    "obsidian.columns.inProgress": ("In Progress", "crew_state.OBSIDIAN_COLUMNS"),
    "obsidian.columns.review": ("Review", "crew_state.OBSIDIAN_COLUMNS"),
    "obsidian.columns.done": ("Done", "crew_state.OBSIDIAN_COLUMNS"),
    "pm.enabled": (True, "crew_state.PM_ENABLED"),
    "pm.mode": ("adaptive", "crew_state.PM_MODE"),
    "pm.quietLines": (8, "crew_state.PM_QUIET_LINES"),
    "pm.maxLines": (40, "crew_state.PM_MAX_LINES"),
    "pm.ticketGranularity": ("system", "crew_state.GRANULARITY_DEFAULT"),
    "resume.typeDelaySeconds": (2, "crew_state.RESUME_TYPE_DELAY_SECONDS"),
    "resume.readyTimeoutSeconds": (15, "crew_state.RESUME_READY_TIMEOUT_SECONDS"),
    "sdp.portal": (None, "crew_state.SDP_PORTAL"),
    "sdp.noteVisibility": ("private", "crew_state.SDP_NOTE_VISIBILITY"),
    "sdp.closeOnDone": (False, "crew_state.SDP_CLOSE_ON_DONE"),
    "secondOpinion.keyEnv": ("GEMINI_API_KEY", "crew_state.SECOND_OPINION_KEY_ENV"),
    "secondOpinion.sendsCode": (False, "crew_state.SECOND_OPINION_SENDS_CODE"),
    "shellRoute.mode": (None, "crew_state.SHELL_ROUTE_MODE"),
    "shellRoute.distro": (None, "crew_state.SHELL_ROUTE_DISTRO"),
    "worktree.root": (None, "crew_state.WORKTREE_ROOT"),
}

# Keys whose default in the MACHINE file differs from the repo's: the machine
# template wrote `auto` for the shell mode where the repo's was null (inherit).
GLOBAL_DEFAULTS = {"shellRoute.mode": "auto"}
