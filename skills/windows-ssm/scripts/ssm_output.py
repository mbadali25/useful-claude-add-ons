#!/usr/bin/env python3
"""Tell whether an SSM Run Command result holds the whole output.

Reads one `aws ssm get-command-invocation` result (JSON) from a path, or from
stdin when no path or `-` is given, and prints one verdict line:

  complete        exit 0  the command finished and stdout and stderr are both
                          under the API's limits
  truncated       exit 3  stdout or stderr is at or over its limit, so the
                          returned text is (or may be) cut
  could not tell  exit 4  the command has not finished, stopped early, never
                          started (ResponseCode -1), or the input is not a
                          get-command-invocation result

Exit 2 is a usage error. The reason, the lengths and, for a cut output, where
the full text is go to stderr. The inspected content is never printed.

The limits are GetCommandInvocation's: StandardOutputContent is "the first
24,000 characters" and StandardErrorContent "the first 8,000"
(https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html).
Output exactly at a limit cannot be told apart from cut output, so it counts as
cut. Whether the limit counts characters or bytes for non-ASCII text is not
stated, so both are measured and either one reaching it counts.

Offline and stdlib-only: no AWS call, no credentials, no file written.
"""
from __future__ import annotations

import json
import sys

STDOUT_LIMIT = 24000
STDERR_LIMIT = 8000
COMPLETE, TRUNCATED, UNKNOWN, USAGE = 0, 3, 4, 2
VERDICT = {COMPLETE: "complete", TRUNCATED: "truncated", UNKNOWN: "could not tell"}
# Finished, with output that is whatever the command wrote.
FINISHED = ("Success", "Failed")
# Every other documented Status: still running, or stopped before it finished.
NOT_FINISHED = ("Pending", "InProgress", "Delayed", "Cancelling", "Cancelled", "TimedOut")

# Fields every get-command-invocation result carries, besides the two streams.
IDENTITY = ("CommandId", "InstanceId", "Status")

STREAMS = (
    ("stdout", "StandardOutputContent", "StandardOutputUrl", STDOUT_LIMIT),
    ("stderr", "StandardErrorContent", "StandardErrorUrl", STDERR_LIMIT),
)


def _decode(raw: bytes) -> str:
    # Windows PowerShell 5.1's `>` writes UTF-16 with a BOM; most else is UTF-8.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _read(argv: list[str]) -> str:
    if len(argv) > 1:
        raise SystemExit(f"usage: ssm_output.py [PATH|-]  (got {len(argv)} arguments)")
    if not argv or argv[0] == "-":
        return _decode(sys.stdin.buffer.read())
    with open(argv[0], "rb") as fh:
        return _decode(fh.read())


def judge(text: str) -> tuple[int, list[str]]:
    """Return (exit code, reasons) for one get-command-invocation document."""
    if not text.strip():
        return UNKNOWN, ["input is empty"]
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return UNKNOWN, [f"input is not JSON ({exc.msg}, line {exc.lineno})"]
    if not isinstance(doc, dict):
        return UNKNOWN, [f"input is JSON but not an object ({type(doc).__name__})"]

    missing = [key for key in IDENTITY if not isinstance(doc.get(key), str) or not doc.get(key)]
    if missing:
        return UNKNOWN, [f"{', '.join(missing)} missing or empty: not a get-command-invocation "
                         "result"]

    reasons: list[str] = []
    cut = False
    for name, key, url_key, limit in STREAMS:
        value = doc.get(key)
        if not isinstance(value, str):
            what = "missing" if key not in doc else f"not a string ({type(value).__name__})"
            return UNKNOWN, [f"{key} is {what}: not a get-command-invocation result"]
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            return UNKNOWN, [f"{key} holds text that is not valid Unicode (a lone surrogate)"]
        chars = len(value)
        if chars >= limit or size >= limit:
            cut = True
            unit = "characters" if chars >= limit else "bytes"
            reasons.append(f"{name}: {chars} characters, {size} bytes - at or over the "
                           f"{limit} limit in {unit}, so it is or may be cut")
            url = doc.get(url_key)
            if isinstance(url, str) and url:
                reasons.append(f"{name}: full text is at {url}")
            else:
                reasons.append(f"{name}: no {url_key}; re-run with --output-s3-bucket-name "
                               "or --cloud-watch-output-config to keep the full text")
        else:
            reasons.append(f"{name}: {chars} characters, {size} bytes (limit {limit})")
    if cut:
        return TRUNCATED, reasons

    status = doc.get("Status")
    if status in FINISHED:
        # ResponseCode -1: the command did not start, or the node never got it
        # (GetCommandInvocation's ResponseCode). Its empty output is not a result.
        code = doc.get("ResponseCode")
        if not isinstance(code, int) or isinstance(code, bool):
            return UNKNOWN, reasons + [f"status {status} but ResponseCode is "
                                       f"{'missing' if 'ResponseCode' not in doc else repr(code)}: "
                                       "not a get-command-invocation result"]
        if code == -1:
            return UNKNOWN, reasons + [f"status {status}, ResponseCode -1: the command did not "
                                       "start or the node did not receive it"]
        return COMPLETE, reasons + [f"status {status}, ResponseCode {code}"]
    if status in NOT_FINISHED:
        return UNKNOWN, reasons + [f"status {status}: the command has not finished, "
                                   "or stopped before it did"]
    return UNKNOWN, reasons + [f"status {status!r} is not a documented Status value"]


def main(argv: list[str]) -> int:
    try:
        text = _read(argv)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return USAGE
    except (OSError, UnicodeDecodeError) as exc:
        source = argv[0] if argv and argv[0] != "-" else "stdin"
        code, reasons = UNKNOWN, [f"cannot read {source}: {exc}"]
    else:
        code, reasons = judge(text)
    print(VERDICT[code])
    for reason in reasons:
        print(f"ssm_output: {reason}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
