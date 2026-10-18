#!/usr/bin/env python3
"""Publish an accepted review receipt as a commit status, and read it back.

    review_status.py post  --ticket T [--root .] [--repo OWNER/NAME]
    review_status.py check [--ticket T] [--root .] [--repo OWNER/NAME] [--pr N | --head SHA]

WHY (L-0780). The review ledger lives under `<git-common-dir>/crew/review/`
and `.work/`, both host-local, so a session on another host finds no ledger.
PR #599 merged with 4 open BLOCKs because that absence was read as "nothing to
gate". An absent ledger carries no information; it is COULD_NOT_TELL.

`post` writes the commit status `crew/review` on the exact head SHA, state
`success`, only when `review_ledger.check_receipt` says the receipt stands on
this head AND the round's BLOCK count is exactly 0 (an owner-accepted FINDINGS
round that carries BLOCKs is published as nothing). The description carries the
summary: `receipt r<n> <kind> <provider>/<family> blocks=<n> fix=<n> nit=<n>
bundle=<12 hex>`, plus `kept-by-delta` when the standing-waiver delta gate kept
the receipt across a merge of main or a version bump (that IS the re-post path
for a waived head; nothing is re-reviewed). A status is bound to a SHA, so a
push after the accept clears it by itself.

`check` answers for one head: ALLOW (exit 0), BLOCK (exit 1), COULD_NOT_TELL
(exit 2). The first stdout line is `REVIEW_GATE <VERDICT> head=<sha> <why>`.
  - this host has a ledger for --ticket AND HEAD is the head asked about: the
    ledger decides (`check_receipt`, and 0 BLOCK); a published success does not
    override a local ledger that says the receipt is stale.
  - this host has no ledger (or HEAD is another commit): the published status
    for that exact sha decides. `success` with `blocks=0` allows; `failure` or
    `error` blocks; `success` that reports blocks>0 blocks; no status, `pending`,
    a description with no readable `blocks=`, a reply for another sha, an
    unreadable reply, gh missing, unauthenticated, rate-limited or erroring are
    all COULD_NOT_TELL. A corrupt local ledger is COULD_NOT_TELL as well.
Both non-zero exits refuse. Nothing here reads absence as a pass.

A status ATTESTS; it does not prove. Anyone whose token can write commit
statuses can post one. Requiring `crew/review` in branch protection is the
repository owner's setting, and `gh pr merge --admin` bypasses it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_ledger  # noqa: E402  pylint: disable=wrong-import-position

CONTEXT = "crew/review"
ALLOW, BLOCK, UNKNOWN = "ALLOW", "BLOCK", "COULD_NOT_TELL"
EXIT = {ALLOW: 0, BLOCK: 1, UNKNOWN: 2}
EXIT_REFUSED, EXIT_POST_FAILED = 1, 2
GH_TIMEOUT = 60
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BLOCKS_RE = re.compile(r"(?:^|\s)blocks=(\d+)(?:\s|$)")
_SLUG_RE = re.compile(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DESCRIPTION_MAX = 140


def _run(argv, cwd):
    """(returncode, stdout, stderr); a missing or hung program is (127|124, "", why),
    never an exception."""
    exe = shutil.which(argv[0])
    if exe is None:
        return 127, "", f"{argv[0]} is not on PATH"
    try:
        done = subprocess.run([exe, *argv[1:]], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                              timeout=GH_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]} timed out after {GH_TIMEOUT}s"
    except OSError as exc:
        return 127, "", f"{argv[0]} could not run: {exc}"
    return done.returncode, done.stdout, done.stderr


def head_of(root):
    """The checked-out commit, or None."""
    code, out, _ = _run(["git", "rev-parse", "HEAD"], root)
    sha = out.strip()
    return sha if code == 0 and _SHA_RE.match(sha) else None


def repo_slug(root, override=None):
    """(OWNER/NAME, why): from --repo, else origin's URL. Never guessed."""
    if override:
        return (override, "") if _REPO_RE.match(override) else (None, f"--repo {override!r} is not OWNER/NAME")
    code, out, err = _run(["git", "remote", "get-url", "origin"], root)
    if code != 0:
        return None, f"could not read origin: {(err or out).strip()}"
    match = _SLUG_RE.search(out.strip())
    if not match:
        return None, f"origin {out.strip()!r} is not a github.com remote"
    return f"{match.group(1)}/{match.group(2)}", ""


def pr_head(root, repo, number):
    """(sha, why) for pull request `number`'s head, as GitHub reports it now."""
    code, out, err = _run(["gh", "api", f"repos/{repo}/pulls/{number}"], root)
    if code != 0:
        return None, f"could not read PR #{number}: {(err or out).strip()[:200]}"
    try:
        sha = json.loads(out)["head"]["sha"]
    except (ValueError, KeyError, TypeError):
        return None, f"PR #{number}: gh returned no readable head sha"
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        return None, f"PR #{number}: head sha {sha!r} is not a 40-hex commit"
    return sha, ""


def lookup(root, repo, sha):
    """(verdict, why) from the published `crew/review` status of `sha`."""
    if not _SHA_RE.match(sha or ""):
        return UNKNOWN, f"{sha!r} is not a full 40-hex commit sha"
    code, out, err = _run(["gh", "api", f"repos/{repo}/commits/{sha}/status"], root)
    if code != 0:
        return UNKNOWN, f"could not read the status of {sha[:12]}: {(err or out).strip()[:200]}"
    try:
        data = json.loads(out)
    except ValueError:
        return UNKNOWN, f"the status reply for {sha[:12]} is not JSON"
    if not isinstance(data, dict) or not isinstance(data.get("statuses"), list):
        return UNKNOWN, f"the status reply for {sha[:12]} has no statuses list"
    if data.get("sha") != sha:
        return UNKNOWN, f"the status reply names {str(data.get('sha'))[:12]}, not {sha[:12]}"
    rows = [s for s in data["statuses"] if isinstance(s, dict) and s.get("context") == CONTEXT]
    if not rows:
        return UNKNOWN, (f"no {CONTEXT} status on {sha[:12]}: this head has no published "
                         "review receipt, and absence is not a pass")
    state = rows[0].get("state")
    description = rows[0].get("description")
    description = description if isinstance(description, str) else ""
    if state in ("failure", "error"):
        return BLOCK, f"{CONTEXT} is {state} on {sha[:12]}: {description}"
    if state != "success":
        return UNKNOWN, f"{CONTEXT} is {state!r} on {sha[:12]}, not success: {description}"
    match = _BLOCKS_RE.search(description)
    if not match:
        return UNKNOWN, (f"{CONTEXT} success on {sha[:12]} does not report blocks=<n> "
                         f"({description!r}): could not tell")
    if int(match.group(1)) != 0:
        return BLOCK, f"{CONTEXT} success on {sha[:12]} reports {match.group(1)} BLOCK: {description}"
    return ALLOW, f"{CONTEXT} success on {sha[:12]}: {description}"


def _counts(latest):
    """(blocks, fix, nit) as ints, or None when the round's counts are unreadable."""
    if not isinstance(latest, dict):
        return None
    counts = latest.get("counts")
    if latest.get("verdict") == "CLEAN" and not counts:
        return 0, 0, 0
    if not isinstance(counts, dict):
        return None
    out = []
    for key in ("BLOCK", "FIX", "NIT"):
        value = counts.get(key)
        if type(value) is not int or value < 0:  # pylint: disable=unidiomatic-typecheck
            return None
        out.append(value)
    return tuple(out)


def describe(root, ticket):
    """(ok, text): the status description when the receipt stands on this head
    with 0 BLOCK, else why nothing may be published."""
    ok, message = review_ledger.check_receipt(root, ticket)
    if not ok:
        return False, message
    data, _ = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
    receipt = data.get("receipt") or {}
    latest = (data.get("rounds") or [{}])[-1]
    counts = _counts(latest)
    if counts is None:
        return False, f"round {latest.get('round')} has no readable counts: could not tell"
    if counts[0] != 0:
        return False, (f"round {latest.get('round')} has {counts[0]} BLOCK finding(s); a "
                       f"{CONTEXT} success is published only at 0 BLOCK")
    who = f"{latest.get('provider') or '?'}/{latest.get('model_family') or '?'}"
    text = (f"receipt r{receipt.get('round')} {receipt.get('kind')} {who} blocks={counts[0]} "
            f"fix={counts[1]} nit={counts[2]} bundle={str(receipt.get('bundle_sha256'))[:12]}")
    if message.startswith("receipt kept by delta gate"):
        text += " kept-by-delta"
    return True, text[:DESCRIPTION_MAX]


def post(root, ticket, repo=None):
    """(exit code, lines). 0 posted, 1 refused (nothing stands), 2 could not post."""
    head = head_of(root)
    if head is None:
        return EXIT_POST_FAILED, ["could not read HEAD; nothing posted"]
    slug, why = repo_slug(root, repo)
    if slug is None:
        return EXIT_POST_FAILED, [f"{why}; nothing posted"]
    ok, text = describe(root, ticket)
    if not ok:
        return EXIT_REFUSED, [f"{CONTEXT} not posted for {head[:12]}: {text}"]
    code, out, err = _run(["gh", "api", "-X", "POST", f"repos/{slug}/statuses/{head}",
                           "-f", "state=success", "-f", f"context={CONTEXT}",
                           "-f", f"description={text}"], root)
    if code != 0:
        return EXIT_POST_FAILED, [f"{CONTEXT} could not be posted for {head[:12]}: "
                                  f"{(err or out).strip()[:200]}"]
    return 0, [f"{CONTEXT} success posted on {head} ({slug}): {text}"]


def verdict_for(root, head, ticket=None, repo=None):
    """(verdict, why) for `head`: the local ledger when it covers this head,
    else the published status. Every unknown stays COULD_NOT_TELL."""
    note = ""
    if ticket:
        _, state = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
        local = head_of(root)
        if state == "corrupt":
            return UNKNOWN, f"the local review ledger for {ticket} is unreadable: could not tell"
        if state == "ok" and local == head:
            ok, text = describe(root, ticket)
            return (ALLOW, f"local receipt: {text}") if ok else (BLOCK, f"local ledger: {text}")
        note = ("no review ledger for " + ticket + " on this host (ledgers are host-local)"
                if state == "absent" else
                f"HEAD {str(local)[:12]} is not the head asked about")
    slug, why = repo_slug(root, repo)
    if slug is None:
        return UNKNOWN, f"{why}; {note}".rstrip("; ")
    verdict, why = lookup(root, slug, head)
    return verdict, (f"{note}; {why}" if note else why)


def check(root, ticket=None, repo=None, pr=None, head=None):
    """(exit code, lines)."""
    slug = None
    if pr is not None:
        slug, why = repo_slug(root, repo)
        if slug is None:
            return EXIT[UNKNOWN], [f"REVIEW_GATE {UNKNOWN} head=? {why}"]
        head, why = pr_head(root, slug, pr)
        if head is None:
            return EXIT[UNKNOWN], [f"REVIEW_GATE {UNKNOWN} head=? {why}"]
    elif head is None:
        head = head_of(root)
        if head is None:
            return EXIT[UNKNOWN], [f"REVIEW_GATE {UNKNOWN} head=? could not read HEAD"]
    verdict, why = verdict_for(root, head, ticket, slug or repo)
    return EXIT[verdict], [f"REVIEW_GATE {verdict} head={head} {why}"]


def main(argv):
    review_ledger.utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("action", choices=("post", "check"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--repo")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--pr", type=int)
    target.add_argument("--head")
    args = parser.parse_args(argv)
    if args.ticket:
        review_ledger.check_ticket(args.ticket)
    if args.action == "post":
        if not args.ticket:
            parser.error("post needs --ticket")
        code, lines = post(args.root, args.ticket, args.repo)
    else:
        code, lines = check(args.root, args.ticket, args.repo, args.pr, args.head)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
