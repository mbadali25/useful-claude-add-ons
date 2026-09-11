"""sqlmap adapter stub. Task 13 fills this in - there is no JSON report
(no --report-json flag exists, spec 13.9); parse session.sqlite / the target
`log` for a persisted injection Type + Payload. ACTIVE=True and gated behind
an explicit confirm token at the routine level, same as ZAP active scan - a
run with no persisted injection yields zero findings, never a low-severity one.
"""
NAME = "sqlmap"
KINDS = ["web"]
ACTIVE = True
DEFAULT_ENABLED = False


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
