"""OWASP Dependency-Check adapter stub. Task 11 fills this in - CVSS v3 can be
absent (spec 13.8); severity fallback order is plain-text `severity`, then
`cvssv2.score`, then `cvssv3.baseScore`.
"""
NAME = "depcheck"
KINDS = ["deps"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
