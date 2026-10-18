#!/usr/bin/env python3
"""Read the published `crew/review` commit status of one exact head, strictly.

    review_status.py check (--head SHA | --pr N) [--repo OWNER/NAME] [--root DIR]

WHY (L-0780). The review ledger lives under `<git-common-dir>/crew/review/` and
`.work/`, both host-local, so a session on another host finds no ledger. PR #599
merged with 4 open BLOCKs because that absence was read as "nothing to gate". An
absence carries no information; it is COULD_NOT_TELL.

`check` is READ-ONLY and fail-closed. It asks GitHub once for
`repos/<slug>/commits/<sha>/status` and answers as a pure function of that one
reply (`verdict`). It reads no local ledger, no working tree and no HEAD, so it
has no second source of truth to disagree with. `--pr N` takes the head from
GitHub, never from a checkout. The first stdout line is
`REVIEW_GATE <VERDICT> head=<sha> <why>`; exit 0 ALLOW, 1 BLOCK, 2 COULD_NOT_TELL.

The reply is parsed by allowlist; anything the allowlist does not name is
COULD_NOT_TELL, and no branch defaults to ALLOW:
  - the reply is an object whose `sha` is the sha asked and whose `statuses` is a
    list that is complete (`total_count` equals its length);
  - EVERY element of `statuses` is an object;
  - exactly one element has `context == "crew/review"`;
  - `failure` or `error` is BLOCK; `pending` and any other state is COULD_NOT_TELL;
  - `success` needs a description that `fullmatch`es SCHEMA below. `blocks=0` is
    ALLOW, `blocks=<n>` with n above 0 is BLOCK, anything off-schema is
    COULD_NOT_TELL.

No producer exists in this file: until `post` is rebuilt (L-0821) no head has a
`success` status, so every head reads COULD_NOT_TELL. That is safe.

A status ATTESTS; it does not prove. Anyone whose token can write commit
statuses can post one, and a receipt revoked after it was posted leaves the
status as it was. Requiring `crew/review` in branch protection is the repository
owner's setting, and `gh pr merge --admin` bypasses it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

CONTEXT = "crew/review"
ALLOW, BLOCK, UNKNOWN = "ALLOW", "BLOCK", "COULD_NOT_TELL"
EXIT = {ALLOW: 0, BLOCK: 1, UNKNOWN: 2}
GH_TIMEOUT = 60
PER_PAGE = 100
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_PR_RE = re.compile(r"[1-9][0-9]{0,8}")
SCHEMA = re.compile(
    r"receipt r[0-9]+ (?:clean|owner-accepted|auto-accepted) \S+/\S+ "
    r"blocks=(0|[1-9][0-9]*) fix=[0-9]+ nit=[0-9]+ bundle=[0-9a-f]{12}(?: kept-by-delta)?")
_SLUG_RE = re.compile(r"(?:git@|ssh://git@|https://(?:[^@/\s]+@)?)github\.com[:/]+"
                      r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _one_line(text, limit=300):
    """`text` as a single printable line: every control character, including a
    newline, becomes a space, so an API-supplied string can never forge a second
    REVIEW_GATE line."""
    return re.sub(r"[\x00-\x1f\x7f\u0085\u2028\u2029]+", " ", str(text)).strip()[:limit]


def _kill_group(proc):
    """Kill the process and, off Windows, its whole group: a child that inherited
    stdout would otherwise hold the pipe open past the timeout."""
    try:
        if os.name != "nt":
            os.killpg(proc.pid, 9)
        else:
            proc.kill()
    except OSError:
        pass


def _run(argv, cwd):
    """(returncode, stdout, stderr); a missing or hung program is (127|124, "", why),
    never an exception."""
    exe = shutil.which(argv[0])
    if exe is None:
        return 127, "", f"{argv[0]} is not on PATH"
    try:
        proc = subprocess.Popen([exe, *argv[1:]], cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace",
                                start_new_session=os.name != "nt")
    except OSError as exc:
        return 127, "", f"{argv[0]} could not run: {exc}"
    try:
        out, err = proc.communicate(timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return 124, "", f"{argv[0]} timed out after {GH_TIMEOUT}s"
    return proc.returncode, out, err


def _valid_slug(slug):
    """True for OWNER/NAME where neither part is a path component."""
    if not isinstance(slug, str) or not _REPO_RE.fullmatch(slug):
        return False
    return all(part not in (".", "..") for part in slug.split("/"))


def repo_slug(root, override=None):
    """(OWNER/NAME, why): from --repo, else origin's URL. Never guessed."""
    if override is not None:
        if _valid_slug(override):
            return override, ""
        return None, "--repo must be OWNER/NAME"
    code, out, err = _run(["git", "remote", "get-url", "origin"], root)
    if code != 0:
        return None, f"could not read origin: {_one_line(err or out, 200)}"
    match = _SLUG_RE.fullmatch(out.strip())
    if not match or not _valid_slug(f"{match.group(1)}/{match.group(2)}"):
        return None, f"origin {_one_line(out, 200)!r} is not a github.com remote"
    return f"{match.group(1)}/{match.group(2)}", ""


def _json(text):
    """(value, ok): `text` parsed as JSON, or (None, False)."""
    try:
        return json.loads(text), True
    except (ValueError, RecursionError):
        return None, False


def pr_head(root, repo, number):
    """(sha, why) for pull request `number`'s head, as GitHub reports it now."""
    code, out, err = _run(["gh", "api", f"repos/{repo}/pulls/{number}"], root)
    if code != 0:
        return None, f"could not read PR #{number}: {_one_line(err or out, 200)}"
    data, ok = _json(out)
    head = data.get("head") if ok and isinstance(data, dict) else None
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return None, f"PR #{number}: gh returned no 40-hex head sha"
    return sha, ""


def verdict(reply, sha):
    """(verdict, why) from one parsed status reply for `sha`. A pure function:
    no I/O, and no branch that returns ALLOW by default."""
    if not isinstance(reply, dict):
        return UNKNOWN, "the status reply is not an object"
    if reply.get("sha") != sha:
        return UNKNOWN, f"the status reply names {_one_line(reply.get('sha'), 12)!r}, not {sha[:12]}"
    statuses = reply.get("statuses")
    if not isinstance(statuses, list):
        return UNKNOWN, f"the status reply for {sha[:12]} has no statuses list"
    total = reply.get("total_count")
    if type(total) is not int or total != len(statuses):  # pylint: disable=unidiomatic-typecheck
        return UNKNOWN, f"the statuses of {sha[:12]} are not a complete list: could not tell"
    if not all(isinstance(item, dict) for item in statuses):
        return UNKNOWN, f"a status of {sha[:12]} is not an object: could not tell"
    rows = [item for item in statuses if item.get("context") == CONTEXT]
    if not rows:
        return UNKNOWN, (f"no {CONTEXT} status on {sha[:12]}: this head has no published "
                         "review receipt, and absence is not a pass")
    if len(rows) != 1:
        return UNKNOWN, f"{len(rows)} {CONTEXT} statuses on {sha[:12]}: could not tell"
    state, description = rows[0].get("state"), rows[0].get("description")
    if state in ("failure", "error"):
        return BLOCK, f"{CONTEXT} is {state} on {sha[:12]}: {_one_line(description)}"
    if state != "success":
        return UNKNOWN, f"{CONTEXT} is {_one_line(state)!r} on {sha[:12]}, not success"
    match = SCHEMA.fullmatch(description) if isinstance(description, str) else None
    if match is None:
        return UNKNOWN, (f"{CONTEXT} success on {sha[:12]} does not match the receipt schema "
                         f"({_one_line(description)!r}): could not tell")
    if match.group(1) != "0":
        return BLOCK, f"{CONTEXT} success on {sha[:12]} reports {match.group(1)} BLOCK: {description}"
    return ALLOW, f"{CONTEXT} success on {sha[:12]}: {description}"


def lookup(root, repo, sha):
    """(verdict, why): one `gh api` call for `sha`'s combined status, then `verdict`."""
    code, out, err = _run(["gh", "api", f"repos/{repo}/commits/{sha}/status?per_page={PER_PAGE}"],
                          root)
    if code != 0:
        return UNKNOWN, f"could not read the status of {sha[:12]}: {_one_line(err or out, 200)}"
    reply, ok = _json(out)
    if not ok:
        return UNKNOWN, f"the status reply for {sha[:12]} is not JSON"
    return verdict(reply, sha)


def _line(kind, head, why):
    return f"REVIEW_GATE {kind} head={head} {_one_line(why, 600)}"


def check(root, repo=None, pr=None, head=None):
    """(exit code, [line]). Exactly one of `pr` and `head`."""
    if (pr is None) == (head is None):
        return EXIT[UNKNOWN], [_line(UNKNOWN, "?", "give exactly one of --pr and --head")]
    if head is not None and not (isinstance(head, str) and _SHA_RE.fullmatch(head)):
        return EXIT[UNKNOWN], [_line(UNKNOWN, "?", "--head must be a full 40-hex commit sha")]
    if pr is not None and not _PR_RE.fullmatch(str(pr)):
        return EXIT[UNKNOWN], [_line(UNKNOWN, "?", "--pr must be a pull request number")]
    slug, why = repo_slug(root, repo)
    if slug is None:
        return EXIT[UNKNOWN], [_line(UNKNOWN, head or "?", why)]
    if pr is not None:
        head, why = pr_head(root, slug, pr)
        if head is None:
            return EXIT[UNKNOWN], [_line(UNKNOWN, "?", why)]
    kind, why = lookup(root, slug, head)
    return EXIT[kind], [_line(kind, head, why)]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("action", choices=("check",))
    parser.add_argument("--root", default=".")
    parser.add_argument("--repo")
    parser.add_argument("--pr")
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    code, lines = check(args.root, args.repo, args.pr, args.head)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
