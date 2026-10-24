import os, sys

GATE = r"C:\Users\d3ade\.claude\plugins\cache\useful-claude-add-ons\crew\1.2.68\hooks\scripts\verify-gate.sh"
with open(GATE, "rb") as fh:
    lines = fh.read().split(b"\n")

# verify-gate.sh:2826 opens  "$PY" -c '  and line 2843 closes with  '
head = lines[2825]                      # line 2826, 1-indexed
assert head.endswith(b"\"$PY\" -c '"), head
tail = lines[2842]                      # line 2843, 1-indexed
# The single-quoted argument: everything after the opening quote on 2826
# through the closing quote at the start of 2843.
close = tail.index(b"'")
body = b"\n".join([b""] + lines[2826:2842] + [tail[:close]])
# ^ leading b"" reproduces the newline immediately after the opening quote.

extras = open(r"D:\temp\claude\argv\extras.json", "rb").read()
py = b"/c/Users/d3ade/AppData/Local/Python/pythoncore-3.14-64/python.exe"
sha = b"32122ca33f2a7f5c8e789d9fb2d35455ba98ce69"
flag = b""

argv = [py, b"-c", body, extras, sha, flag]
names = ["argv[0] $PY (as bash execs it)", "argv[1] -c",
         "argv[2] inline python script", "argv[3] $EXTRAS (record 6 JSON)",
         "argv[4] $SYNC_SHA", "argv[5] $BUDGET_FLAG (empty on Stop)"]
for n, a in zip(names, argv):
    print("%-34s %8d bytes" % (n, len(a)))
total = sum(len(a) for a in argv)
print("%-34s %8d bytes" % ("sum of argv elements", total))
# execve/CreateProcess accounting: each element contributes its bytes plus a
# NUL terminator (POSIX) or a separating space (Windows command line).
print("%-34s %8d bytes" % ("+ one terminator per element", total + len(argv)))
print()
print("Windows CreateProcess lpCommandLine hard limit      32767 chars")
print("argv[3] alone exceeds that limit by              %6d chars" % (len(extras) - 32767))
print("whole vector exceeds it by                       %6d chars" % (total + len(argv) - 32767))
