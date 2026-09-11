"""Checkov adapter stub. Task 12 fills this in - `severity` is normally null
in an open-source run (populated only via --bc-api-key), so `default="medium"`
is the normal path, not an edge case (spec 13.5). Output may be a JSON array
of framework reports, not a single object - the parser must accept both.
"""
NAME = "checkov"
KINDS = ["iac"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
