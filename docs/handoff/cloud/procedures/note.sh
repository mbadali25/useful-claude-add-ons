#!/usr/bin/env bash
# usage: note.sh "HH:MM: text"   -> prepends a log line to cloud-handoff-notes.md on ccr-b039f2bb-6jks7g and pushes
set -euo pipefail
cd "${NOTES_DIR:-/home/user/notes}"
git pull -q --ff-only origin ccr-b039f2bb-6jks7g || true
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
for i in 2 4 8 16; do git push -q origin ccr-b039f2bb-6jks7g && break || sleep $i; done
git log -1 --format=%h
