#!/usr/bin/env python3
"""The double confirmation behind a sensitive config change (crew 1.3.9).

A change that lifts a human step -- today, a `humanOnly.*` key set to `false`
(`crew_humanonly`) -- is never written by `crew_config.py --set` or the
`/crew:config` menu. It is PROPOSED here, which records a pending change in
the machine's confirmation store (`~/.claude/crew/confirm-config/`) and
prints a change id. The owner then types `/crew:confirm-config <change_id>`
twice, in two separate prompts, within `crew_humanonly.PROPOSAL_TTL_SECONDS`;
the second confirmation applies the write (`crew_config.apply_confirmed_optout`)
and leaves the applied record that `crew_humanonly.resolve` requires.

The state machine, one record per change id:

    pending --confirm (1st)--> pending (1 confirmation)
    pending --confirm (2nd, another prompt)--> applied
                                         \\--> stale    (the file changed since)
                                         \\--> refused  (the repo file became tracked,
                                                         or the write failed)
    pending --past its expiry--> expired
    pending --cancel--> cancelled

**User-only.** `confirm` accepts only `via="user-prompt"` with a prompt id,
the shape crew's UserPromptSubmit hook passes for a prompt the user typed.
This CLI has no `confirm` subcommand. Since crew 1.3.33 the prompt hook
(`approval_hook._confirm_config`) is the one caller of `confirm`; since crew
1.3.65 a `/crew:confirm-config` it refuses also lists the pending proposals.
`propose` prints the two lines the agent must relay to the owner (the change
and the exact command), because the owner never sees this CLI's output.

CLI (no writes except `propose` and `cancel`, both into the store only):

    crew_confirm_config.py propose --layer machine|repo --key humanOnly.<k> [--root R]
    crew_confirm_config.py status <change_id>
    crew_confirm_config.py list
    crew_confirm_config.py cancel <change_id>
    crew_confirm_config.py resolve [--root R] [--json]

Exit codes: 0 done, 2 refused (bad input, wrong layer, tracked repo file,
unknown or settled change), 3 could not tell (the store or a file cannot be
read).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import crew_common
import crew_config
import crew_config_files
import crew_humanonly
import crew_state


class Refused(Exception):
    """The request is not allowed; nothing changed (exit 2)."""


def _now(now):
    return time.time() if now is None else now


def _target(layer, root, global_path):
    if layer == "machine":
        return global_path or crew_state.GLOBAL_CONFIG_PATH
    if layer == "repo":
        if not root:
            raise Refused("--root is required for the repo layer")
        return crew_common.repo_config_file(root, "config.json")
    raise Refused(f"unknown layer {layer!r} (machine or repo)")


def propose(layer, dotted, root=None, global_path=None, now=None, tracker=None):
    """Record a pending change `dotted: false` at `layer`; returns the record.

    Refused when `dotted` is not a humanOnly key, or when the repo file is
    absent, tracked by git, or git cannot tell (a tracked file can never opt
    out, and could-not-tell is not untracked)."""
    if not crew_humanonly.is_path(dotted):
        raise Refused(f"{dotted} is not a key that needs a double confirmation "
                      f"(those are: {', '.join(crew_humanonly.PATHS)})")
    path = _target(layer, root, global_path)
    if layer == "repo":
        if not os.path.isfile(path):
            raise Refused(f"no {path}; a repo opt-out lives in an existing, untracked "
                          ".crew/config.json")
        state = (tracker or crew_humanonly.tracking)(path)
        if state != crew_humanonly.UNTRACKED:
            raise Refused(f"{path} is {state} in git; a tracked or committed repo config "
                          "can never opt out of a human-only rule (use the machine layer)")
    _parsed, digest = crew_config_files.read_tolerant(path)
    stamp = _now(now)
    record = {
        "change_id": crew_humanonly.new_change_id(),
        "layer": layer, "key": dotted, "value": False,
        "path": path, "target": crew_humanonly.target_key(path),
        "root": os.path.abspath(root) if root else None,
        "targetDigest": digest, "created": stamp,
        "expires": stamp + crew_humanonly.PROPOSAL_TTL_SECONDS,
        "confirmations": [], "state": crew_humanonly.PENDING,
        "settled": None, "reason": None,
    }
    crew_humanonly.write_record(crew_humanonly.store_dir(global_path), record)
    return record


def _load(store, change_id):
    if not crew_humanonly.valid_change_id(change_id):
        raise Refused(f"{change_id!r} is not a change id (cc- and 8 hex digits)")
    record = crew_humanonly.read_record(store, change_id)
    if record is None:
        raise Refused(f"no change {change_id}")
    return record


def _settle(store, record, state, reason, now):
    record["state"], record["reason"], record["settled"] = state, reason, now
    crew_humanonly.write_record(store, record)
    return record


def _expire_if_due(store, record, now):
    if record.get("state") == crew_humanonly.PENDING and now > record.get("expires", 0):
        _settle(store, record, "expired", "not confirmed twice before it expired", now)
    return record


def confirm(change_id, via, prompt_id, session_id=None, global_path=None, now=None,
            tracker=None, apply=None):
    """One confirmation of `change_id`, from one prompt the user typed.

    Returns the record. The first confirmation leaves it pending; a second
    from a DIFFERENT prompt applies the change. Refused (Refused raised,
    nothing recorded) when `via` is not `user-prompt`, the prompt id is
    missing or already used, or the change is not pending."""
    store = crew_humanonly.store_dir(global_path)
    stamp = _now(now)
    if via != crew_humanonly.USER_PROMPT:
        raise Refused("a confirmation counts only from a prompt the user typed "
                      "(/crew:confirm-config <change_id>); nothing recorded")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise Refused("a confirmation needs the prompt's id; nothing recorded")
    record = _expire_if_due(store, _load(store, change_id), stamp)
    if record.get("state") != crew_humanonly.PENDING:
        raise Refused(f"change {change_id} is {record.get('state')}, not pending")
    seen = [c.get("prompt") for c in record.get("confirmations", [])]
    if prompt_id in seen:
        raise Refused("one prompt confirms once; type /crew:confirm-config "
                      f"{change_id} again in a new prompt")
    record.setdefault("confirmations", []).append(
        {"at": stamp, "via": via, "prompt": prompt_id, "session": session_id})
    if len(record["confirmations"]) < 2:
        crew_humanonly.write_record(store, record)
        return record
    if record["layer"] == "repo":
        state = (tracker or crew_humanonly.tracking)(record["path"])
        if state != crew_humanonly.UNTRACKED:
            return _settle(store, record, "refused",
                           f"{record['path']} is {state} in git now", stamp)
    writer = apply or crew_config.apply_confirmed_optout
    try:
        writer(record["layer"], record["key"], record["path"], record["targetDigest"],
               global_path=global_path)
    except crew_config_files.Conflict as exc:
        return _settle(store, record, "stale",
                       f"the file changed since the proposal ({exc}); propose again", stamp)
    except (OSError, crew_config_files.Unreadable, crew_config_files.Busy,
            crew_config.GlobalWriteRefused, crew_config.RepoWriteRefused) as exc:
        return _settle(store, record, "refused", f"the write failed: {exc}", stamp)
    return _settle(store, record, crew_humanonly.APPLIED, "confirmed twice", stamp)


def cancel(change_id, global_path=None, now=None):
    store = crew_humanonly.store_dir(global_path)
    stamp = _now(now)
    record = _expire_if_due(store, _load(store, change_id), stamp)
    if record.get("state") != crew_humanonly.PENDING:
        raise Refused(f"change {change_id} is {record.get('state')}, not pending")
    return _settle(store, record, "cancelled", "cancelled", stamp)


def _line(record):
    count = len(record.get("confirmations") or [])
    return (f"{record.get('change_id')}  {record.get('state')}  {record.get('layer')}  "
            f"{record.get('key')} = {json.dumps(record.get('value'))}  "
            f"confirmations {count}/2  {record.get('path') or record.get('target')}")


def _instructions(record):
    minutes = crew_humanonly.PROPOSAL_TTL_SECONDS // 60
    return [
        f"proposed {record['change_id']}: {record['key']} = false in the {record['layer']} "
        f"file {record['path']}",
        "Only the owner can apply it. Relay the next two lines to the owner word for word; "
        "never type or confirm it yourself:",
        f"  crew proposes {record['key']}: false ({record['layer']} config, "
        f"{record['path']}), change {record['change_id']}.",
        f"  To apply it, type /crew:confirm-config {record['change_id']} as its own prompt, "
        f"twice, in two separate prompts, within {minutes} minutes. To refuse it, do nothing; "
        "it expires.",
        "The prompt hook records each confirmation (crew 1.3.33); typed with no id, "
        "/crew:confirm-config lists the pending proposals instead (crew 1.3.65).",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_confirm_config.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--layer", required=True, choices=("machine", "repo"))
    p.add_argument("--key", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--global-path", default=None)
    for name in ("status", "cancel"):
        q = sub.add_parser(name)
        q.add_argument("change_id")
        q.add_argument("--global-path", default=None)
    q = sub.add_parser("list")
    q.add_argument("--global-path", default=None)
    q = sub.add_parser("resolve")
    q.add_argument("--root", default=".")
    q.add_argument("--global-path", default=None)
    q.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    store = crew_humanonly.store_dir(args.global_path)
    try:
        if args.cmd == "propose":
            record = propose(args.layer, args.key, root=args.root,
                             global_path=args.global_path)
            print("\n".join(_instructions(record)))
        elif args.cmd == "status":
            record = _expire_if_due(store, _load(store, args.change_id), time.time())
            print(_line(record))
            if record.get("reason"):
                print(f"  {record['reason']}")
        elif args.cmd == "cancel":
            print(_line(cancel(args.change_id, global_path=args.global_path)))
        elif args.cmd == "list":
            records, problems = crew_humanonly.all_records(store)
            for record in sorted(records, key=lambda r: r.get("created") or 0):
                print(_line(record))
            for problem in problems:
                print(f"could not tell: {problem}", file=sys.stderr)
            if problems:
                return 3
        else:
            out = {key: crew_humanonly.resolve(args.root, key, global_path=args.global_path)
                   for key in crew_humanonly.KEYS}
            if args.json:
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                for key, got in out.items():
                    state = "human-only" if got["humanOnly"] else "opted out"
                    print(f"humanOnly.{key}: {state} - {got['reason']}")
                print("crew 1.3.27: humanOnly.approve is acted on "
                      "(crew_ticket.cli_approval_allowed); no hook reads "
                      "humanOnly.promoteMarker, which stays human-only whatever this says.")
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"could not tell: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
