#!/usr/bin/env bash
# usage: note.sh "what happened"   -- appends a UTC-stamped line to the rush log, commits, pushes.
set -u
R=/home/user/useful-claude-add-ons
F=$R/docs/handoff/cloud/rush-1.2.0/cloud-handoff-rush-1.2.0.md
ts=$(date -u +%Y-%m-%dT%H:%MZ)
MSG="$*"
python3 - "$F" "$ts" "$*" <<'P'
import os, sys
f, ts, msg = sys.argv[1:4]
t = open(f).read()
marker = "## Log (newest first)\n\n"
i = t.index(marker) + len(marker)
t = t[:i] + f"- {ts} {msg}\n" + t[i:]
t = t.replace(t[t.index("Last updated: "):t.index("\n", t.index("Last updated: "))], f"Last updated: {ts}", 1)
open(f + ".tmp", "w").write(t); os.replace(f + ".tmp", f)
P
cd $R && git add "$F" && git commit -q -m "rush notes: ${MSG:0:60}

Claude-Session: https://claude.ai/code/session_01QLY3kk7DCXpucXGu3wSniW" && \
  for i in 1 2 3 4; do git push -q origin claude/eloquent-wozniak-iqb4hf 2>/dev/null && break; sleep $((2**i)); done
