"""testssl.sh adapter stub. Task 9 fills this in - `--jsonfile <file> <host>`,
severity via sev_from_text. OK/INFO are non-findings at info; the full WARN/
FATAL value set needs verifying against a real run before finalizing
(spec 13.11).
"""
NAME = "testssl"
KINDS = ["web", "host"]
ACTIVE = False
DEFAULT_ENABLED = True


def is_available():
    raise NotImplementedError


def run(target, outdir, opts):
    raise NotImplementedError


def parse(raw_path, target):
    raise NotImplementedError
