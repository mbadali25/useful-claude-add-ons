---
type: tool_used
tool: Agent
input_match: '"subagent_type"\s*:\s*"(?:[\w-]+:)?developer"'
min: 1
---

The PM actually dispatched a developer subagent — not "said the word
dispatch", which a refusal like "I cannot dispatch crew:developer." satisfies
without calling anything. Namespace prefix is optional in the match, the same
convention the plugin-evals docs use for `tool_used: Skill` (`crew:developer`
or a bare `developer`).
