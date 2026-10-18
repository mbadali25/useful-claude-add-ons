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
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_BLOCKS_RE = re.compile(r"(?<!\S)blocks=(\d+)(?!\S)")
_SLUG_RE = re.compile(r"^(?:git@|ssh://git@|https://(?:[^@/\s]+@)?)github\.com[:/]+"
                      r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DESCRIPTION_MAX = 140


def _one_line(text, limit=300):
    """`text` as a single printable line: every control character, including a
    newline, becomes a space, so an API-supplied string can never forge a second
    REVIEW_GATE line."""
    return re.sub(r"[\x00-\x1f\x7f\u0085\u2028\u2029]+", " ", str(text)).strip()[:limit]


def _tree_dirty(root):
    """True / False, or None when git cannot say. A published status covers a
    committed sha only; edits in the working tree are not in it."""
    code, out, _ = _run(["git", "status", "--porcelain", "--untracked-files=normal"], root)
    if code != 0:
        return None
    return bool(out.strip())


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


def head_of(root):
    """The checked-out commit, or None."""
    code, out, _ = _run(["git", "rev-parse", "HEAD"], root)
    sha = out.strip()
    return sha if code == 0 and _SHA_RE.fullmatch(sha) else None


def repo_slug(root, override=None):
    """(OWNER/NAME, why): from --repo, else origin's URL. Never guessed."""
    if override:
        return (override, "") if _REPO_RE.match(override) else (None, f"--repo {override!r} is not OWNER/NAME")
    code, out, err = _run(["git", "remote", "get-url", "origin"], root)
    if code != 0:
        return None, f"could not read origin: {(err or out).strip()}"
    match = _SLUG_RE.match(out.strip())
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
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return None, f"PR #{number}: head sha {sha!r} is not a 40-hex commit"
    return sha, ""


def lookup(root, repo, sha):
    """(verdict, why) from the published `crew/review` status of `sha`."""
    if not _SHA_RE.fullmatch(sha or ""):
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
        return BLOCK, f"{CONTEXT} is {state} on {sha[:12]}: {_one_line(description)}"
    if state != "success":
        return UNKNOWN, f"{CONTEXT} is {_one_line(state)!r} on {sha[:12]}, not success: {_one_line(description)}"
    found = _BLOCKS_RE.findall(description)
    if len(found) != 1:
        return UNKNOWN, (f"{CONTEXT} success on {sha[:12]} must report blocks=<n> exactly once "
                         f"({_one_line(description)!r}): could not tell")
    if int(found[0]) != 0:
        return BLOCK, (f"{CONTEXT} success on {sha[:12]} reports {found[0]} BLOCK: "
                       f"{_one_line(description)}")
    return ALLOW, f"{CONTEXT} success on {sha[:12]}: {_one_line(description)}"


def _counts(latest):
    """(blocks, fix, nit) as ints, or None when the round's counts are unreadable."""
    if not isinstance(latest, dict):
        return None
    counts = latest.get("counts")
    if not isinstance(counts, dict):
        return None
    if latest.get("verdict") == "CLEAN" and not counts:
        return 0, 0, 0
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
    data, state = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
    receipt = data.get("receipt") if state == "ok" else None
    rounds = data.get("rounds") if state == "ok" else None
    if (not isinstance(receipt, dict) or not receipt.get("bundle_sha256")
            or not isinstance(rounds, list) or not rounds or not isinstance(rounds[-1], dict)
            or rounds[-1].get("round") != receipt.get("round")):
        return False, ("the ledger changed or could not be read again after the receipt check: "
                       "could not tell")
    latest = rounds[-1]
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
    dirty = _tree_dirty(root)
    if dirty is not False:
        return EXIT_REFUSED, [f"{CONTEXT} not posted for {head[:12]}: the working tree "
                              + ("has uncommitted changes" if dirty else "could not be read")
                              + "; a status covers the committed sha only (commit, then post)"]
    ok, text = describe(root, ticket)
    if not ok:
        return EXIT_REFUSED, [f"{CONTEXT} not posted for {head[:12]}: {text}"]
    if head_of(root) != head:
        return EXIT_REFUSED, [f"{CONTEXT} not posted: HEAD moved from {head[:12]} while the "
                              "receipt was checked; run post again"]
    code, out, err = _run(["gh", "api", "-X", "POST", f"repos/{slug}/statuses/{head}",
                           "-f", "state=success", "-f", f"context={CONTEXT}",
                           "-f", f"description={text}"], root)
    if code != 0:
        return EXIT_POST_FAILED, [f"{CONTEXT} could not be posted for {head[:12]}: "
                                  f"{_one_line((err or out), 200)}"]
    try:
        reply = json.loads(out)
    except ValueError:
        reply = None
    url = reply.get("url") if isinstance(reply, dict) else None
    if (not isinstance(reply, dict) or reply.get("state") != "success"
            or reply.get("context") != CONTEXT
            or not isinstance(url, str) or not url.endswith(f"/statuses/{head}")):
        return EXIT_POST_FAILED, [f"{CONTEXT} post for {head[:12]} exited 0 but GitHub did not "
                                  "return the created success status; not reported as posted"]
    return 0, [f"{CONTEXT} success posted on {head} ({slug}): {text}"]


def _local_tickets(root, head):
    """(tickets, problem): every ticket whose local ledger names `head` in a
    round. A ledger directory or file that cannot be read is a problem, never
    "no ledger"."""
    directory = os.path.dirname(review_ledger.ledger_path(root, "X"))
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return [], ""
    except OSError as exc:
        return [], f"the ledger directory could not be read ({exc.__class__.__name__})"
    found = []
    for name in names:
        if not name.endswith(".json"):
            continue
        data, state = review_ledger._load(os.path.join(directory, name))  # pylint: disable=protected-access
        if state != "ok":
            return [], f"the local ledger {name} is unreadable: could not rule it out"
        rounds = data.get("rounds")
        if not isinstance(rounds, list):
            return [], f"the local ledger {name} has no readable rounds: could not rule it out"
        for row in rounds:
            if not isinstance(row, dict) or not isinstance(row.get("head"), str):
                return [], (f"the local ledger {name} has a round with no readable head: "
                            "could not rule it out")
        if any(row["head"] == head for row in rounds):
            found.append(name[:-5])
    return found, ""


def verdict_for(root, head, ticket=None, repo=None):
    """(verdict, why) for `head`: the local ledger when it covers this head,
    else the published status. Every unknown stays COULD_NOT_TELL."""
    note = ""
    if ticket:
        _, state = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
        local = head_of(root)
        if state == "corrupt":
            return UNKNOWN, f"the local review ledger for {ticket} is unreadable: could not tell"
        if state == "ok" and local is None:
            return UNKNOWN, "a local ledger exists but git could not read HEAD: could not tell"
        if state == "ok" and local == head:
            ok, text = describe(root, ticket)
            return (ALLOW, f"local receipt: {text}") if ok else (BLOCK, f"local ledger: {text}")
        note = ("no review ledger for " + ticket + " on this host (ledgers are host-local)"
                if state == "absent" else
                f"HEAD {str(local)[:12]} is not the head asked about")
    if not ticket:
        names, problem = _local_tickets(root, head)
        if problem:
            return UNKNOWN, problem
        if names:
            local = head_of(root)
            if local != head:
                return UNKNOWN, (f"a local ledger ({', '.join(names)}) names this head but HEAD is "
                                 f"{str(local)[:12]}: run check --ticket there")
            for name in names:
                ok, text = describe(root, name)
                if not ok:
                    return BLOCK, f"local ledger {name}: {text}"
            return ALLOW, f"local receipt {', '.join(names)}: {text}"
    if not ticket and head_of(root) == head and _tree_dirty(root) is not False:
        return UNKNOWN, ("no --ticket, and this working tree has uncommitted changes (or git could "
                         "not say): a published status covers the committed sha only, so a local "
                         "ledger might disagree; pass --ticket where the ledger lives, or commit")
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
    return EXIT[verdict], [f"REVIEW_GATE {verdict} head={head} {_one_line(why, 600)}"]


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
    if args.head is not None and not _SHA_RE.fullmatch(args.head):
        print("review_status: --head must be a full 40-hex commit sha", file=sys.stderr)
        return 2
    if args.action == "post" and (args.head is not None or args.pr is not None):
        print("review_status: post publishes on HEAD only; --head and --pr are for check",
              file=sys.stderr)
        return 2
    if args.ticket:
        try:
            review_ledger.check_ticket(args.ticket)
        except review_ledger.LedgerError as exc:
            print(f"review_status: {exc}", file=sys.stderr)
            return 2
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
