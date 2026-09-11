"""Nikto adapter stub. Task 7 fills this in - parse CSV or XML, never JSON
(-Format json emits invalid JSON on target-not-a-webserver, spec 13.6). Nikto
has no severity field at all, so every finding is a heuristic assignment and
must carry severity-assigned.
"""
NAME = "nikto"
KINDS = ["web"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
