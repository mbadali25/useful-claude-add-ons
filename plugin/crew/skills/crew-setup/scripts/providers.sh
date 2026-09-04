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

  # Gate 2, checked locally and for free: has `copilot login` ever run here?
  # The token itself lives in the OS keychain; config.json records who owns it.
  cop_cfg="$HOME/.copilot/config.json"
  if [ -f "$cop_cfg" ] && grep -q '"lastLoggedInUser"' "$cop_cfg" 2>/dev/null; then
    say "login:" "yes ($(sed -n 's/.*"login": *"\([^"]*\)".*/\1/p' "$cop_cfg" | head -1))"
  else
    say "login:" "NO -> run: copilot login   (gate 2 - the CLI needs its OWN token)"
  fi

  # A borrowed token silently outranks that login and is the classic false lead:
  # it authenticates, then fails the policy check, which reads like a billing bug.
  for v in COPILOT_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN; do
    if [ -n "$(eval "printf '%s' \"\${$v:-}\"")" ]; then
      say "WARNING:" "$v is set and OVERRIDES your copilot login."
      say "" "If it lacks Copilot entitlement you get 'Access denied by"
      say "" "policy settings' that no policy change will ever fix. Unset it."
      break
    fi
  done

  say "gate 1:" "policy must allow the CLI - this is an ACCOUNT setting, not local:"
  say "" "gh api orgs/<org>/copilot/billing --jq '.cli'   # must be: enabled"
  say "" "if greyed out in org settings, the enterprise policy overrides it:"
  say "" "github.com/settings/enterprises > Policies > Copilot"
  say "gate 3:" "copilot -p 'reply OK' -s; echo \$?   # check the EXIT CODE"
  say "" "do not pipe to head/tail while reading \$? - you get the pipe's 0"
  say "model:" "pin LAST, only after gate 3 returns. MUST NOT be a claude-* model."
  say "" "Copilot defaults to claude-sonnet-4.6 - the author's own family, so"
  say "" "an unpinned Copilot reviews its own family while looking independent."
  say "" "Pin a Google model such as gemini-3.7-flash instead. Names churn -"
  say "" "a stale one fails at startup, before any diff is sent."
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
