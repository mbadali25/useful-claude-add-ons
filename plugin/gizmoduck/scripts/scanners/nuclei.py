"""Nuclei adapter stub. Task 5 fills this in - reuse cmd_scan's existing argv
(gizmoduck.py:63) and parse() must be byte-identical to gizmoduck.load() for
the same input (assert against gizmoduck.load() directly, per the plan).
"""
NAME = "nuclei"
KINDS = ["web", "host"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
