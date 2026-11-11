#!/usr/bin/env python3
"""promote-gate's pre-deploy verdict (checks 1-3 of promote-gate.sh's header): the
upstream PASS rows, the rollback runbook and the human approval marker, for every
matched environment.

This is the heredoc promote-gate.sh used to run as a second `python -`, moved here
with its rules and messages unchanged so the one gate process (_promote_gate.py)
calls it without starting another python.

    verdict(tree, blob, deadline, sha, full, envs) -> [reason, ...]   (cwd: the project dir)

raises CouldNotTell(why) where the old step printed `why` and exited 5, and lets any
other exception through: the gate blocks on both, as it blocked on a non-zero exit.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import time


class CouldNotTell(Exception):
    """The map that is policy for this sha could not be read or parsed (old exit 5)."""


def verdict(tree, blob, deadline, sha, full, envs):
    deadline = float(deadline)
    full = full.lower()

    # Keys read ignoring case, case twins refused: the matcher's rule above (and
    # PowerShell's), repeated because this is a separate interpreter. A refusal
    # raises, which exits non-zero and blocks below as "could not be evaluated".
    def fold(text):
        return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)

    def no_case_twins(pairs):
        seen = set()
        for key, _ in pairs:
            if fold(key) in seen:
                raise ValueError(f"duplicate or case-differing key `{key}`")
            seen.add(fold(key))
        return {fold(k): v for k, v in pairs}

    # L-0768: the map committed in the deployed sha - its blob, listed by the
    # shell above - or, when the sha carries none, the project dir's map, which
    # the guard above found clean (a check, then this read: two moments, as
    # before L-0768; _promote_review.py's fallback hashes the bytes it reads). _promote_review.py's
    # policy_map_text reads the same map for requireReview. Could-not-tell prints
    # its reason and exits 5; the shell blocks on any non-zero status and shows
    # what was printed.
    source = "sha" if blob else "project"
    try:
        if blob:
            shown = subprocess.run([shutil.which("git") or "git", "--no-replace-objects", "-C", tree,
                                    "cat-file", "blob", blob],
                                   capture_output=True, check=False,
                                   timeout=max(deadline - time.time(), 0.5),
                                   stdin=subprocess.DEVNULL)
            if shown.returncode != 0:
                raise OSError(f"git cat-file exited {shown.returncode}")
            text = shown.stdout.decode("utf-8-sig")
        else:
            with open(".crew/verify.json", encoding="utf-8-sig") as fh:
                text = fh.read()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        raise CouldNotTell(f"the deployment map that is policy for this sha could not be read: {exc}") from exc
    try:
        doc = json.loads(text, object_pairs_hook=no_case_twins)
    except ValueError as exc:
        where = "the deployed sha's committed .crew/verify.json" if source == "sha" \
            else ".crew/verify.json"
        raise CouldNotTell(f"{where} does not parse as a deployment map: {exc}") from exc
    out = []

    rows = ""
    if os.path.exists(".work/PROMOTIONS.md"):
        with open(".work/PROMOTIONS.md", encoding="utf-8", errors="replace") as handle:
            rows = handle.read()

    # L-0703: a row is THIS commit's only when its sha cell is the full 40-hex
    # sha (case ignored). `startswith(sha[:7])` admitted a PASS row for any other
    # commit sharing the first 7 characters. A strict prefix of the full sha is a
    # short row: never counted (no back-compat - resolving it re-opens the hole
    # whenever the row's own commit is gone from the object store), but named, so
    # the block says what to fix.
    def row_sha(cell, full):
        cell = cell.strip().lower()
        if cell == full:
            return "full"
        if 0 < len(cell) < len(full) and full.startswith(cell):
            return "short"
        return None

    shorts = {}

    def passed(name, full):
        """The NEWEST row for `name` and THIS sha decides (L-0665): rows are appended,
        so file order is time order, and a later pass clears an earlier failure
        while a later failure revokes an earlier pass. Only a full-sha row is this
        sha's (L-0703); a short one is noted in `shorts` and never decides. True /
        False for that row all-pass or not; None when there is no full-sha row."""
        newest = None
        for line in rows.splitlines():
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            # when | env | sha | smoke | regression | verify | by
            kind = row_sha(cells[2], full) if cells[1] == name else None
            if kind == "short":
                shorts.setdefault(name, []).append(cells[2])
            if kind == "full":
                newest = all(c.lower() == "pass" for c in cells[3:6])
        return newest

    # The union rule: every matched environment's requirements, each in its own
    # terms (its upstreams, its runbook, its approval marker). With several, each
    # reason names the environment it comes from.
    for env in envs:
        declared = doc.get("ENVIRONMENTS", {})
        if source == "sha" and fold(env) not in declared:
            # Matched by the project dir's map, absent from the map that is
            # policy: its requirements cannot be told, so they are not "none".
            out.append(f"'{env}' is a deploy by the project dir's .crew/verify.json, but the map "
                       f"committed in the deployed sha {full} does not declare it, so its "
                       "requirements cannot be told. Deploy a sha whose committed map declares "
                       f"'{env}'.")
            if len(envs) > 1:
                out[-1] = f"[{env}] {out[-1]}"
            continue
        cfg = declared.get(fold(env), {})
        before = len(out)
        for upstream in cfg.get("REQUIRES", []):
            verdict = passed(upstream, full)
            if verdict is None:
                short = "".join(f" (.work/PROMOTIONS.md records the short sha {s} for '{upstream}': "
                                "a row counts only with the full 40-character sha - re-run the "
                                "promotion, or rewrite the row with the full sha after checking it)"
                                for s in shorts.get(upstream, [])[:1])
                out.append(f"'{upstream}' has no all-pass row for sha {full} in .work/PROMOTIONS.md"
                           f"{short}. Run /crew:promote {upstream} first, and let it record the "
                           "result.")
            elif not verdict:
                out.append(f"'{upstream}' has rows for sha {full} in .work/PROMOTIONS.md, but the "
                           "newest row is not all-pass: a later failure revokes an earlier pass. "
                           f"Run /crew:promote {upstream} again, and let it record the result.")

        # Fail CLOSED: an absent "rollback" key used to mean "no rollback needed".
        # It now means "nobody said". The only way to deploy with no rollback plan is
        # an explicit rollback: "none" plus a rollbackReason explaining why.
        if "ROLLBACK" not in cfg:
            out.append(f"'{env}' has no 'rollback' key in .crew/verify.json. Add rollback: "
                       f"\"<path to a runbook>\", or rollback: \"none\" plus a rollbackReason "
                       f"string explaining why {env} does not need one. Fix: edit the "
                       f"'{env}' block in .crew/verify.json.")
        else:
            rb = cfg.get("ROLLBACK")
            if rb == "none":
                reason = str(cfg.get("ROLLBACKREASON") or "").strip()
                if not reason:
                    out.append(f"'{env}' sets rollback: \"none\" but has no rollbackReason. "
                               f"State why {env} does not need a rollback plan. Fix: add a "
                               f"rollbackReason string next to rollback in .crew/verify.json.")
            elif not rb:
                out.append(f"'{env}' has rollback: {rb!r}, which is not a valid runbook path. "
                           f"Fix: set rollback to a runbook path, or to the literal string "
                           f"\"none\" plus a rollbackReason.")
            elif not os.path.exists(rb):
                out.append(f"the rollback runbook '{rb}' does not exist. No verified rollback, no deploy.")
            else:
                with open(rb, encoding="utf-8", errors="replace") as handle:
                    txt = handle.read()
                m = re.search(r"last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})", txt, re.I)
                if not m:
                    out.append(f"'{rb}' has no 'last verified: YYYY-MM-DD' line. "
                               "An unverified rollback is not a rollback.")
                else:
                    # A date-SHAPED string is not a date. The regex accepts \d{4}-\d{2}
                    # -\d{2}, so `2026-99-99` reaches fromisoformat and raises - which
                    # used to take the whole check down and, because the caller read an
                    # empty VERDICT as "nothing wrong", ALLOWED the deploy. Name it as
                    # its own unmet precondition instead: the reader needs to know the
                    # date is junk, not that a python traceback happened.
                    try:
                        verified = datetime.date.fromisoformat(m.group(1))
                    except ValueError:
                        out.append(f"'{rb}' has 'last verified: {m.group(1)}', which is date-shaped but "
                                   "not a real date. An unparseable verification date is not a "
                                   "verification.")
                    else:
                        age = (datetime.date.today() - verified).days
                        if age > 90:
                            out.append(f"'{rb}' was last verified {age} days ago (ceiling is 90). "
                                       "Re-run it against a real environment first.")

        if cfg.get("REQUIREHUMAN"):
            marker = f".crew/.approved-{env}-{sha}"
            if not os.path.exists(marker):
                out.append(f"this environment requires explicit human approval. Show the sha, the diff summary and the "
                           f"last promotion, get a yes, then: touch {marker}")
        if len(envs) > 1:
            out[before:] = [f"[{env}] {r}" for r in out[before:]]

    return out
