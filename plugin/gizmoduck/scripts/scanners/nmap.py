"""Nmap adapter stub. Task 8 fills this in - `-oX <file> -sV <host>` runs by
default; `--script vuln` only when `opts.nmap_vuln` is set.

ACTIVE is False at the module level: base version/port scanning is not
intrusive and does not need the same opt-in gate as sqlmap/ZAP. The `vuln`
NSE opt-in is a per-run option (`opts.nmap_vuln`), not the registry-level
ACTIVE/DEFAULT_ENABLED gate - see the Global Constraints note in the plan
("Nmap `vuln` NSE" is listed among the active-behaviors that need explicit
opt-in, but that opt-in lives in `opts`, not in this module flipping ACTIVE).
"""
NAME = "nmap"
KINDS = ["web", "host"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
