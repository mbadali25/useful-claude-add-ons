"""OWASP ZAP adapter stub. Task 6 fills this in - the local path is the
Automation Framework (`zap.bat -cmd -autorun plan.yaml`, a `report` job of
`template: traditional-json`), not zap-baseline.py/zap-full-scan.py, which
shell out to Docker internally (spec 13.3). ACTIVE=True: this design has no
passive-only mode, so the whole module is gated - never runs unless a target
opts in, same as sqlmap.
"""
NAME = "zap"
KINDS = ["web"]
ACTIVE = True
DEFAULT_ENABLED = False


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
