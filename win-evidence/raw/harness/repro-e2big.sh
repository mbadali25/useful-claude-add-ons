#!/usr/bin/env bash
# Minimal standalone repro of verify-gate.sh:2826's failure under Git Bash on
# Windows: one oversized argv element handed to python.exe.
# No crew code, no repo state. Bisects the threshold.
PY='C:\Users\d3ade\AppData\Local\Python\pythoncore-3.14-64\python.exe'

echo "uname:        $(uname -a)"
echo "bash:         $BASH_VERSION"
echo "python:       $("$PY" -c 'import sys;print(sys.version)' 2>&1 | head -n 1)"
echo "env bytes:    $(env | wc -c | tr -d ' ')"
echo

try() { # $1 = argv element length in bytes
  local n="$1" arg
  arg=$(printf 'x%.0s' $(seq 1 "$n"))
  local out
  out=$("$PY" -c 'import sys; print(len(sys.argv[1]))' "$arg" 2>&1)
  local rc=$?
  printf '%7d  rc=%d  %s\n' "$n" "$rc" "$out"
  return $rc
}

echo "== fixed sizes =="
for n in 1000 8000 16000 30000 32000 32500 32700 32767 32800 33000 37237; do
  try "$n"
done

echo
echo "== bisect last size that execs =="
lo=1000; hi=40000
while [ $((hi - lo)) -gt 1 ]; do
  mid=$(( (lo + hi) / 2 ))
  arg=$(printf 'x%.0s' $(seq 1 "$mid"))
  if "$PY" -c 'import sys' "$arg" >/dev/null 2>&1; then lo=$mid; else hi=$mid; fi
done
echo "largest single argv element that execs: $lo bytes"
echo "smallest that fails:                    $hi bytes"
echo
echo "== the raw error, verbatim =="
arg=$(printf 'x%.0s' $(seq 1 37237))
"$PY" -c 'import sys' "$arg"
echo "exit=$?"
