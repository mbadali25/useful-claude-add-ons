from pathlib import Path


def read_ledger(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").split("\n")


def banner() -> list[str]:
    return "a\nb".splitlines()


def reviewed(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return text.splitlines()  # nosemgrep: crew-splitlines-untrusted-text (display only, never parsed)


def first_error_line(done) -> str:
    return (done.stderr.strip().splitlines() or ["no stderr"])[0]
