"""Trivy adapter stub. Task 10 fills this in - one binary serves both `deps`
(--scanners vuln) and `iac` (--scanners misconfig) kinds; parse only the
array matching the requested kind. Exits 0 regardless of findings unless
--exit-code is passed - never infer findings from the exit code (spec 13.7).
No tfsec: its engine folded into Trivy in 2023 (spec 13.4).
"""
NAME = "trivy"
KINDS = ["deps", "iac"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
