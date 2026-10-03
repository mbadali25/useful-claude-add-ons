"""Build, and machine-locally check, the golden corpus of real reviewer output.

    python3 golden_build.py [--source /repos/personal] [--out <dir>] [--stream <review-dir>]
    python3 golden_build.py --check-local [--source /repos/personal]

Walks `<source>/*/.work/review/*/` -- every review a lane on this machine has
run -- and writes one fixture per contract-era review into
`plugin/crew/tests/golden/review/<checkout>--<review-dir>/`:

  out.txt        the reviewer's answer, byte for byte after redaction
  parts.json     the bundle part paths its manifest listed, in order, redacted
  expected.json  what the parser makes of it: verdict, counts, parts_missing,
                 delivered, failure_class, read_form (full/bare/none), origin
  events.jsonl   the `codex exec --json` stream -- for ONE review only
                 (`--stream`, default the T-0072 stream with raw U+2028)

Skipped, each with its reason: `main-*` directories (written before the
review contract existed), and directories with no `out.txt` or no manifest
with parts.

REDACTION normalises machine-specific text and changes nothing else: the
checkout root and any `/repos/personal/<checkout>` to `<ROOT>`, the home
directory and any `/home/<user>` (and `C:\\Users\\<user>`, `/Users/<user>`)
to `<HOME>`, the temp directory to `<TMP>`, the host name to `<HOST>`, and an
email address other than @example.com / noreply / `git@<host>` to `<EMAIL>`.
The same function redacts `out.txt` and `parts.json`, so a READ line and the
part it names stay equal. A fixture whose redacted text still matches a leak
pattern (a machine path, the host name, an email other than @example.com /
noreply, including one straight after a JSON escape, an `sk-` token with
hyphenated segments (`sk-proj-`, `sk-ant-`), a `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`/
`github_pat_` GitHub token, an `AKIA`/`ASIA` AWS key, a `xox?-` Slack token, an
`AIza` Google key, an `sk_live_`/`rk_live_` Stripe key, an `npm_` or `glpat-`
token, a PEM header, a `Bearer` token) is REFUSED: nothing is written for it and its id and
pattern are printed (a refusal is the check working, not an error). The
expected verdict is computed from the redacted text
and must equal the unredacted text's, or the fixture is a mismatch.

`--check-local` writes nothing: it replays every source directory (and every
Codex stream, not just the committed one) with the golden assertions -- each
review FINDINGS with no part missing, except the known reviewer-declared
INCOMPLETE (`KNOWN_INCOMPLETE`), redaction changing no verdict, and every
stream yielding exactly its `out.txt` -- and prints
`<n> fixtures, <m> streams, <k> mismatches`, exiting 1 on any mismatch.

Stdlib only. Every output's content is computed before its file is opened.
"""
import argparse
import glob
import json
import os
import re
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks", "scripts"))
import review_verdict  # noqa: E402  pylint: disable=wrong-import-position

DEFAULT_SOURCE = "/repos/personal"
DEFAULT_OUT = os.path.join(HERE, "golden", "review")
DEFAULT_STREAM = "T-0072-build--2BJpY8"
# The one real INCOMPLETE on this machine: a reviewer that wrote `INCOMPLETE:
# I ...` and no READ lines -- a genuine reviewer-class INCOMPLETE.
KNOWN_INCOMPLETE = ("useful-claude-add-ons-aa9d50-T-0028-kimi--T-0028-kimi--t2GDOu",)

_STOP = r"[^/\s\"'`]+"
# A machine path starts where no word or path character precedes it, or right
# after a JSON string escape (`\n/root/x` inside an event stream).
_START = r"(?:(?<![A-Za-z0-9_.-])|(?<=\\[nrt]))"
LEAKS = (
    ("machine path", re.compile(r"/repos/|/root/|/home/|/Users/|C:\\Users\\|\\\\Users\\\\")),
    # `sk-proj-...`, `sk-ant-api03-...`: segments joined by `-` and `_`.
    ("sk- token", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}|github_pat_")),
    ("AWS key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[abposr]-")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("Stripe key", re.compile(r"(?<![A-Za-z0-9])[rs]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("npm token", re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{36}")),
    ("GitLab token", re.compile(r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20}")),
    ("PEM header", re.compile(r"-----BEGIN")),
    ("Bearer token", re.compile(r"Bearer [A-Za-z0-9]")),
)
# An address starts at a word boundary, or straight after a JSON escape
# (`\nalice@corp.com`, `\u003calice@corp.com`) when it starts with a letter or
# digit -- so `\n+@x.y` in an event stream stays a newline then `+@x.y`, not an
# address (review round 5).
EMAIL = re.compile(r"(?:(?<![\\A-Za-z0-9._%+-])|(?<=\\[nrt])(?=[A-Za-z0-9])"
                   r"|(?<=\\u[0-9A-Fa-f]{4})(?=[A-Za-z0-9]))"
                   r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def allowed_address(found):
    """@example.com, noreply, and `git@<host>` -- the SSH transport user of a
    git remote (git@github.com, git@ssh.dev.azure.com), never a person."""
    return found.endswith("@example.com") or "noreply" in found or found.startswith("git@")


def _host_word(host):
    """The host name as a WHOLE word, the one boundary `redact` and `leak` share.
    `leak` used a bare substring, so a host called `vm` was found inside the
    fixture id `...-vmVkDU` and the corpus check failed on that machine only,
    while `redact` (whole word) had correctly left it alone."""
    return re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(host) + r"(?![A-Za-z0-9_-])")


def redact(text, checkout_root):
    """Machine-specific paths and the host name to placeholders; nothing else.
    Each match needs a boundary on BOTH sides: a path starts where no word or
    path character precedes it, and the host name is a whole word, so prose
    that merely contains one (`symlink/root race`) is left as written."""
    text = re.sub(_START + re.escape(checkout_root.rstrip("/")) + r"(?![A-Za-z0-9_.-])",
                  "<ROOT>", text)
    text = re.sub(_START + r"/repos/personal/" + _STOP, "<ROOT>", text)
    home = os.path.expanduser("~").rstrip("/")
    if home and home != "/":
        text = re.sub(_START + re.escape(home) + r"(?![A-Za-z0-9_.-])", "<HOME>", text)
    text = re.sub(_START + r"/home/" + _STOP, "<HOME>", text)
    text = re.sub(_START + r"/Users/" + _STOP, "<HOME>", text)
    text = re.sub(r"(?<![A-Za-z0-9_])[A-Za-z]:(?:\\\\|\\)Users(?:\\\\|\\)[^\\\s\"'`]+",
                  "<HOME>", text)
    tmp = tempfile.gettempdir().rstrip("/")
    if tmp and tmp != "/":
        text = re.sub(_START + re.escape(tmp) + "/", "<TMP>/", text)
    host = socket.gethostname()
    if host:
        text = _host_word(host).sub("<HOST>", text)
    # A person's address (a `git log` author line inside a Codex stream) is
    # normalised like a path; the leak check below stays as the backstop.
    return EMAIL.sub(lambda m: m.group(0) if allowed_address(m.group(0)) else "<EMAIL>", text)


def leak(text):
    """The first leak pattern `text` still matches, or None."""
    for name, pattern in LEAKS:
        if pattern.search(text):
            return name
    host = socket.gethostname()
    if host and _host_word(host).search(text):
        return "host name"
    for found in EMAIL.findall(text):
        if not allowed_address(found):
            return f"email {found}"
    return None


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def read_form(parts_read):
    if not parts_read:
        return "none"
    if any("/" in t.replace("\\", "/") for t in parts_read):
        return "full"
    return "bare"


def expected_for(out, parts, origin):
    result = review_verdict.parse(out, 0, False, parts)
    return {
        "verdict": result["verdict"], "counts": result["counts"],
        "parts_missing": result["parts_missing"], "delivered": result["delivered"],
        "failure_class": review_verdict.failure_class(result["verdict"],
                                                      result["delivered"], False),
        "read_form": read_form(result["parts_read"]), "origin": origin,
    }


def sources(source):
    """[(fixture_id, checkout_root, review_dir, skip_reason_or_None)]."""
    found = []
    for folder in sorted(glob.glob(os.path.join(source, "*", ".work", "review", "*", ""))):
        folder = folder.rstrip("/")
        review = os.path.basename(folder)
        checkout = os.path.dirname(os.path.dirname(os.path.dirname(folder)))
        fid = f"{os.path.basename(checkout)}--{review}"
        why = None
        if review.startswith("main-"):
            why = "pre-contract main-* review"
        elif not os.path.isfile(os.path.join(folder, "out.txt")):
            why = "no out.txt"
        else:
            try:
                manifest = json.loads(_read(os.path.join(folder, "manifest.json")))
                if not manifest.get("parts"):
                    why = "manifest has no parts"
            except (OSError, ValueError):
                why = "no readable manifest.json"
        found.append((fid, checkout, folder, why))
    return found


def fixture(fid, checkout, folder):
    """(files_to_write, expected, raw_expected, problem): computed, nothing written."""
    manifest = json.loads(_read(os.path.join(folder, "manifest.json")))
    parts = [p.get("path") or p["name"] for p in manifest["parts"]]
    out = _read(os.path.join(folder, "out.txt"))
    origin = f"{os.path.basename(checkout)}/{os.path.basename(folder)}"
    red_out = redact(out, checkout)
    red_parts = [redact(p, checkout) for p in parts]
    expected = expected_for(red_out, red_parts, origin)
    raw = expected_for(out, parts, origin)
    files = {"out.txt": red_out,
             "parts.json": json.dumps(red_parts, indent=2) + "\n",
             "expected.json": json.dumps(expected, indent=2, sort_keys=True) + "\n"}
    return files, expected, raw


def problems_for(fid, expected, raw):
    """Why a review does not replay the way the corpus promises; [] when it does."""
    found = []
    if {k: v for k, v in expected.items() if k != "parts_missing"} != \
            {k: v for k, v in raw.items() if k != "parts_missing"} or \
            len(expected["parts_missing"]) != len(raw["parts_missing"]):
        found.append("redaction changed the parse")
    if fid in KNOWN_INCOMPLETE:
        if (expected["verdict"], expected["failure_class"]) != ("INCOMPLETE", "reviewer"):
            found.append(f"expected INCOMPLETE/reviewer, got {expected['verdict']}/"
                         f"{expected['failure_class']}")
    elif expected["verdict"] != "FINDINGS" or expected["parts_missing"]:
        found.append(f"expected FINDINGS with every part read, got {expected['verdict']}, "
                     f"missing {expected['parts_missing']}")
    return found


def stream_problem(folder):
    events = os.path.join(folder, "codex-events.jsonl")
    if not os.path.isfile(events):
        return None, False
    got = review_verdict.codex_final_message(_read(events))
    want = (_read(os.path.join(folder, "out.txt")), None)
    return (None if got == want else f"stream yields {str(got)[:120]!r}"), True


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def build(args):
    written = refused = mismatched = 0
    for fid, checkout, folder, why in sources(args.source):
        if why:
            print(f"SKIP     {fid}: {why}")
            continue
        files, expected, raw = fixture(fid, checkout, folder)
        if os.path.basename(folder) == args.stream:
            files["events.jsonl"] = redact(_read(os.path.join(folder, "codex-events.jsonl")),
                                           checkout)
        found = [f"{name}: {leak(text)}" for name, text in files.items() if leak(text)]
        if found:
            refused += 1
            print(f"REFUSED  {fid}: {'; '.join(found)}")
            continue
        problems = problems_for(fid, expected, raw)
        if problems:
            mismatched += 1
            print(f"MISMATCH {fid}: {'; '.join(problems)}")
        for name, text in files.items():
            _write(os.path.join(args.out, fid, name), text)
        written += 1
        print(f"WROTE    {fid}: {expected['verdict']} {expected['read_form']} "
              f"{expected['counts']}{' +events' if 'events.jsonl' in files else ''}")
    print(f"{written} fixtures written, {refused} refused, {mismatched} mismatches")
    return 1 if mismatched else 0


def check_local(args):
    fixtures = streams = mismatches = 0
    for fid, checkout, folder, why in sources(args.source):
        if why:
            continue
        fixtures += 1
        _, expected, raw = fixture(fid, checkout, folder)
        problems = problems_for(fid, expected, raw)
        problem, has_stream = stream_problem(folder)
        streams += has_stream
        if problem:
            problems.append(problem)
        if problems:
            mismatches += 1
            print(f"MISMATCH {fid}: {'; '.join(problems)}")
    print(f"{fixtures} fixtures, {streams} streams, {mismatches} mismatches")
    return 1 if mismatches else 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--stream", default=DEFAULT_STREAM)
    parser.add_argument("--check-local", action="store_true")
    args = parser.parse_args(argv)
    return check_local(args) if args.check_local else build(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
