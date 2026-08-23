#!/usr/bin/env bash
# Reports provider availability AND whether they actually work. Read-only.
say() { printf '%-14s %s\n' "$1" "$2"; }

echo "== QA reviewer =="
if command -v codex >/dev/null 2>&1; then
  say "codex:" "found ($(codex --version 2>/dev/null | head -1))"
  say "auth:" "run: codex exec --skip-git-repo-check 'reply OK' — must return without prompting"
else
  say "codex:" "NOT FOUND -> /crew:review falls back to the qa-reviewer agent"
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
