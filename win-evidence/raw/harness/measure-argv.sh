#!/usr/bin/env bash
# Reproduces verify-gate.sh 1.2.68's matcher stage read-only against the named
# repo and stale marker, then measures the EXACT argument vector that
# verify-gate.sh:2826 execs:  "$PY" -c '<inline script>' "$EXTRAS" "$SYNC_SHA" "$BUDGET_FLAG"
set -u
REPO="$1"
MARKER="$2"
OUT="$3"
PY='C:\Users\d3ade\AppData\Local\Python\pythoncore-3.14-64\python.exe'
FP_DIR='C:/Users/d3ade/.claude/plugins/cache/useful-claude-add-ons/crew/1.2.68/hooks/scripts'

cd "$REPO" || exit 1

# verify-gate.sh:774 -- the stale-marker branch, BASE=$MARKER
CHANGED=$(git -c core.quotePath=false diff --name-only "$MARKER" 2>/dev/null; \
          git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null)
CHANGED=$(printf '%s\n' "$CHANGED" | sort -u | sed '/^$/d')
CHANGED_FILE=$(mktemp)
printf '%s\n' "$CHANGED" > "$CHANGED_FILE"

echo "repo=$REPO"
echo "marker=$MARKER"
echo "head=$(git rev-parse HEAD)"
echo "changed_files=$(printf '%s\n' "$CHANGED" | wc -l | tr -d ' ')"
echo "changed_list_bytes=$(wc -c < "$CHANGED_FILE" | tr -d ' ')"

# verify-gate.sh:1344 -- BUDGET_FLAG is empty on a Stop run
BUDGET_FLAG=""
TREE_PRE=$("$PY" "$FP_DIR/verify_record.py" tree-snapshot --stable 2>/dev/null | tr -d '\r\n')
MATCHED=$(CREW_REPO_CONFIG="$REPO/.crew/config.json" "$PY" D:/temp/claude/matcher.py \
          "$CHANGED_FILE" "$BUDGET_FLAG" "$FP_DIR" "$TREE_PRE")
MATCHER_STATUS=$?
MATCHED=$(printf '%s' "$MATCHED" | tr -d '\r')
rm -f "$CHANGED_FILE"
echo "matcher_exit=$MATCHER_STATUS"

# verify-gate.sh:2151 -- record 6 is $EXTRAS
EXTRAS=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 6p)
printf '%s' "$EXTRAS" > "$OUT/extras.json"
SYNC_SHA=$(git rev-parse HEAD 2>/dev/null)

echo "extras_bytes=$(wc -c < "$OUT/extras.json" | tr -d ' ')"
echo "sync_sha_bytes=${#SYNC_SHA}"
echo "budget_flag_bytes=${#BUDGET_FLAG}"
echo "matched_rules=$(printf '%s' "$EXTRAS" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin).get("matched_rules",[])))')"
