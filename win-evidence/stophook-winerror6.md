# Stop hook on Windows: WinError 6 and related failures (crew 1.2.68)

Evidence from win-repo-2. Not for merge as-is.

## Cases from the Stop run on crew 1.2.68

```
test_diagram_doc.py: collection error at line 178, _bash_has_sha256
  Popen -> _make_inheritable
  OSError: [WinError 6] The handle is invalid
```

```
test_qa_audit.py: 3 failures
test_qa_audit_env.py: 4 failures
7 failed, 261 passed, 6 skipped
```

```
test_recurring_findings.py::test_data_comes_from_the_plugin_not_the_root
1 failed, 157 passed, 11 skipped
```

```
verify-gate.sh: line 2826: python.exe: Argument list too long
```

```
verify-gate: FAILED 3 cmd | PASSED 17 cmd | NOT VERIFIED 74 item(s) ... budget 228s/60s
```

## Note

Repro: the Stop hook child process has an invalid stdin, so any Popen that
inherits handles raises WinError 6. Rule commands run with the default
`--capture=fd`, which does not avoid it.

## Timing from the reprice dry runs

Before reprice (reprice-dryrun-before.log):

```
verify-gate: FAILED 0 cmd | PASSED 19 cmd | NOT VERIFIED 78 item(s) (reach 0, over-budget 8, dirty tree 0, deferred 70, skipped 0, other 0) | credited 0 | budget 530s/60s | detail: .crew/.verify-gate.log
```

After reprice (reprice-dryrun.log):

```
verify-gate: FAILED 0 cmd | PASSED 13 cmd | NOT VERIFIED 85 item(s) (reach 0, over-budget 38, dirty tree 0, deferred 47, skipped 0, other 0) | credited 0 | budget 69s/60s | detail: .crew/.verify-gate.log
```

Charged budget: 530s before, 69s after. Both runs also hit
`verify-gate.sh: line 2826: python.exe: Argument list too long`.