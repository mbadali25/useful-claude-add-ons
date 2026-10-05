#!/usr/bin/env bash
# usage: note.sh "HH:MM: text"   -> prepends a log line to cloud-handoff-notes.md and COMMITS locally
#        note.sh --push          -> pushes the notes branch (owner 2026-10-05: push every ~30 min and at each merge,
#                                   not after every action; every push starts CI on the notes PR)
# A log call also pushes when the last push is older than 30 minutes, so a dead session loses at most ~30 min of notes.
set -euo pipefail
cd "${NOTES_DIR:-/home/user/notes}"
B=ccr-b039f2bb-6jks7g
push() { for i in 2 4 8 16; do git push -q origin "$B" && { date -u +%s > .git/notes-last-push; return 0; } || sleep $i; done; echo "note.sh: push FAILED after 4 tries" >&2; return 1; }
if [ "${1:-}" = "--push" ]; then git pull -q --no-rebase --no-edit origin "$B" || true; push; git log -1 --format=%h; exit 0; fi
python3 - "$1" <<'PY'
import pathlib,re,sys,datetime
p=pathlib.Path('cloud-handoff-notes.md'); s=p.read_text()
now=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')
s=re.sub(r"Last updated: .*",f"Last updated: {now} UTC",s,count=1)
s=s.replace("## Log (newest first)\n\n","## Log (newest first)\n\n- "+sys.argv[1].strip()+"\n",1)
p.write_text(s)
PY
git commit -qam "handoff notes: $(date -u +%H:%M)

Claude-Session: https://claude.ai/code/session_016wQA2o38aSB65bpjaGpMVJ"
last=$(cat .git/notes-last-push 2>/dev/null || echo 0)
if [ $(( $(date -u +%s) - last )) -ge 1800 ]; then git pull -q --no-rebase --no-edit origin "$B" || true; push; echo "(pushed)"; fi
git log -1 --format=%h
