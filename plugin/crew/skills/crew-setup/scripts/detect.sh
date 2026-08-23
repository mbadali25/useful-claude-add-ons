#!/usr/bin/env bash
# Reports what a repo already has. Read-only.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 1
say() { printf '%-16s %s\n' "$1" "$2"; }

s=""
[ -n "$(ls *.sln *.csproj 2>/dev/null)" ] && s="$s dotnet"
{ [ -f requirements.txt ] || [ -f pyproject.toml ]; } && s="$s python"
[ -f package.json ] && s="$s node"
[ -f composer.json ] && s="$s php"
[ -n "$(ls *.tf 2>/dev/null)" ] && s="$s terraform"
grep -rqs 'angular.module' --include=*.js . 2>/dev/null && s="$s angularjs"
say "stack:" "${s:-  unknown}"

say "smoke:" "$([ -f scripts/smoke.sh ] && echo present || echo MISSING)"
say "tests:" "$(find . -path ./node_modules -prune -o \( -iname '*test*' -o -iname '*spec*' \) -type f -print 2>/dev/null | grep -c . ) files matching test/spec"
say "ci:" "$([ -d .github/workflows ] || [ -f azure-pipelines.yml ] || [ -f .gitlab-ci.yml ] && echo present || echo none)"
say "crew:" "$([ -f .crew/config.json ] && echo 'already set up' || echo new)"
say "claude.md:" "$([ -f CLAUDE.md ] && echo present || echo none)"
say "codex:" "$(command -v codex >/dev/null && echo available || echo 'not found - will use Claude fallback')"
say "migrations:" "$(find . -type d \( -iname 'migrations' -o -iname 'migrate' \) 2>/dev/null | head -1 | grep -q . && echo present || echo none)"
say "playwright:" "$([ -f playwright.config.js ] || [ -f playwright.config.ts ] && echo configured || echo 'none - phase 6')"
say "mermaid:" "$(command -v mmdc >/dev/null && echo 'mmdc found' || echo 'npm i -g @mermaid-js/mermaid-cli')"
say "cloud:" "$(command -v aws >/dev/null && printf 'aws '; command -v az >/dev/null && printf 'az '; command -v uvx >/dev/null && printf 'uvx '; echo)"
say "branch:" "$(git branch --show-current 2>/dev/null || echo 'not a git repo')"
