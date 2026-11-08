---
description: Confirm a sensitive crew config change - only you can, by typing this twice
argument-hint: <change_id>
allowed-tools: Read, Bash
disable-model-invocation: true
---

The user typed `/crew:confirm-config $1`. A change that lifts a human step
(today: `humanOnly.approve` or `humanOnly.promoteMarker` set to `false`) is
never written by `/crew:config` or `crew_config.py --set`. It is proposed with
`crew_confirm_config.py propose`, which prints a change id, and it applies only
after the owner types `/crew:confirm-config <change_id>` **twice, in two
separate prompts**, within 15 minutes. The second confirmation writes the key
and leaves the receipt `crew_humanonly.resolve` requires; a `false` written any
other way reads as human-only.

**crew 1.3.8: no hook records this confirmation yet.** Recording it from the
user's own prompt is the UserPromptSubmit hook's job, and that wiring is a
review-harness change that lands separately. Until it does, typing this
command records nothing, so tell the user exactly that: the change
`$1` is still pending (or expired), nothing was confirmed, and the human-only
rules hold as before. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_confirm_config.py status $1`
shows the change's state; read it and report it.

**Never confirm a change yourself.** There is no CLI subcommand for it, and a
confirmation counts only when the prompt hook saw the user type this command.
Never write into `~/.claude/crew/confirm-config/`, and never edit a
`humanOnly` key to `false` by hand or through Edit: crew reads such a value as
human-only, and doing it is the step the owner asked to keep for themselves.
