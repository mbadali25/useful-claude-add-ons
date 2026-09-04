#!/usr/bin/env bash
# Reports provider availability AND whether they actually work. Read-only.
say() { printf '%-14s %s\n' "$1" "$2"; }

echo "== QA reviewer =="
if command -v codex >/dev/null 2>&1; then
  say "codex:" "found ($(codex --version 2>/dev/null | head -1))"
  say "auth:" "run: codex exec --skip-git-repo-check 'reply OK'  -  must return without prompting"
else
  say "codex:" "NOT FOUND -> /crew:review moves to the next provider in qa.order"
fi

if command -v copilot >/dev/null 2>&1; then
  say "copilot:" "found ($(copilot --version 2>/dev/null | head -1))"
  say "auth:" "run: copilot -p 'reply OK' -s  -  'Access denied by policy settings'"
  say "" "means the org has Copilot CLI off, not that you lack a seat:"
  say "" "org Settings > Copilot > Policies > 'Copilot in the CLI'"
  say "model:" "qa.copilot.model MUST be set, and MUST NOT be a claude-* model."
  say "" "Copilot defaults to claude-sonnet-4.6 - the author's own family, so"
  say "" "an unpinned Copilot reviews its own family while looking independent."
  say "" "Pin gemini-3.1-pro-preview or mai-code-1-flash instead."
else
  say "copilot:" "not found -> npm i -g @github/copilot (needs a Copilot seat)"
fi

echo
echo "== Design second opinion =="
if command -v gemini >/dev/null 2>&1; then
  say "gemini CLI:" "found"
  say "flag check:" "$(gemini --help 2>&1 | grep -oE '\-\-prompt|\-p\b' | head -1 || echo 'confirm non-interactive flag with: gemini --help')"
else
  say "gemini CLI:" "not found"
fi
if [ -n "${GEMINI_API_KEY:-}" ]; then
  say "GEMINI_API_KEY:" "set (${#GEMINI_API_KEY} chars)"
else
  say "GEMINI_API_KEY:" "not set -> get one at aistudio.google.com, export in your shell profile"
fi

echo
echo "== Local fallback =="
if command -v ollama >/dev/null 2>&1; then
  say "ollama:" "found"
  say "models:" "$(ollama list 2>/dev/null | awk 'NR>1{print $1}' | tr '\n' ' ' | sed 's/ $//' || echo none)"
else
  say "ollama:" "not found -> only needed if code must stay local"
fi

echo
echo "Presence on PATH is not working auth. Make one real call per provider"
echo "before trusting it: a provider that fails silently turns every gate green."
