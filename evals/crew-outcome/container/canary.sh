#!/usr/bin/env bash
# L-0728 U10 canary. No model call, no credential: a scripted shell in the real
# arm container, behind the real allowlisting proxy, that must NOT reach the
# paths it is given or github.com, and MUST reach the model API hosts.
#
# Usage: canary.sh <out-file> <host-path>...
#   <host-path>: a path on the host that must not exist inside the container
#   (the host checkout, the task store, an earlier run dir that reuses the same
#   ticket id). Env: DOCKER (default /usr/bin/docker), PYTHON (default
#   /usr/bin/python3), CANARY_IMAGE (default crew-outcome-eval:1).
#
# The proxy is a host process bound to the arm network's gateway address (see
# proxy.py); the arm network is `--internal`.
set -u

DOCKER="${DOCKER:-/usr/bin/docker}"
PYTHON="${PYTHON:-/usr/bin/python3}"
IMAGE="${CANARY_IMAGE:-crew-outcome-eval:1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -lt 2 ]; then
  echo "usage: canary.sh <out-file> <host-path>..." >&2
  exit 2
fi
OUT="$1"
shift
for tool in "$DOCKER" "$PYTHON"; do
  if [ ! -x "$tool" ]; then
    echo "canary: $tool is not executable; set DOCKER / PYTHON to absolute paths" >&2
    exit 2
  fi
done
if ! "$DOCKER" image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "canary: image $IMAGE is missing; build it first: $DOCKER build --network host -t $IMAGE $HERE" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/canary.XXXXXX")"
NET="crew-outcome-int-canary-$$"
PROXY_PID=""
mkdir -p "$WORK/repo" "$WORK/home"
chmod 777 "$WORK/repo" "$WORK/home"

cleanup() {
  if [ -n "$PROXY_PID" ]; then kill "$PROXY_PID" >/dev/null 2>&1; fi
  "$DOCKER" network rm "$NET" >/dev/null 2>&1
  rm -rf "$WORK"
}
trap cleanup EXIT

"$DOCKER" network create --internal "$NET" >/dev/null || { echo "canary: cannot create network" >&2; exit 2; }
GW="$("$DOCKER" network inspect "$NET" -f '{{(index .IPAM.Config 0).Gateway}}')"
"$PYTHON" "$HERE/proxy.py" "$HERE/proxy-allowlist.txt" "$WORK/proxy.jsonl" "$GW" 3128 &
PROXY_PID=$!
sleep 1
if ! kill -0 "$PROXY_PID" 2>/dev/null; then echo "canary: proxy did not start on $GW:3128" >&2; exit 2; fi

echo "canary: $(date -u +%Y-%m-%dT%H:%M:%SZ) image=$("$DOCKER" image inspect -f '{{.Id}}' "$IMAGE") network=$NET gateway=$GW" > "$OUT"

PROBE='
fail=0
check() { # check <label> <expect> <actual>
  if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1 (expected $2, got $3)"; fail=1; fi
}
reach() { # reach <curl args...> -> ok when curl got any HTTP answer
  if curl -sS -m 30 -o /dev/null "$@" >/dev/null 2>&1; then echo ok; else echo fail; fi
}
for p in "$@"; do
  if [ -e "$p" ]; then r=visible; else r=absent; fi
  check "path not visible: $p" absent "$r"
done
export HTTPS_PROXY="http://$PROXY_ADDR"
check "github.com via proxy refused" fail "$(reach https://github.com)"
check "codeload.github.com via proxy refused" fail "$(reach https://codeload.github.com)"
check "api.github.com via proxy refused" fail "$(reach https://api.github.com)"
check "api.anthropic.com direct (no proxy) unreachable" fail "$(reach --noproxy "*" https://api.anthropic.com)"
check "github.com direct (no proxy) unreachable" fail "$(reach --noproxy "*" https://github.com)"
check "api.anthropic.com via proxy reachable" ok "$(reach https://api.anthropic.com)"
check "chatgpt.com via proxy reachable" ok "$(reach https://chatgpt.com)"
exit $fail
'

"$DOCKER" run --rm --network "$NET" --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
  -v "$WORK/repo:/run/repo" -v "$WORK/home:/run/home" -e HOME=/run/home -e "PROXY_ADDR=$GW:3128" \
  "$IMAGE" /bin/bash -c "$PROBE" canary "$@" >> "$OUT" 2>&1
rc=$?

{
  echo "--- proxy log (host, decision) ---"
  "$PYTHON" - "$WORK/proxy.jsonl" <<'PY'
import json
import sys

try:
    lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
except OSError:
    lines = []
for line in lines:
    record = json.loads(line)
    print(record.get("host") or record.get("request"), record["decision"])
PY
} >> "$OUT" 2>&1

if [ "$rc" -eq 0 ]; then echo "canary: PASS" >> "$OUT"; else echo "canary: FAIL" >> "$OUT"; fi
cat "$OUT"
exit "$rc"
