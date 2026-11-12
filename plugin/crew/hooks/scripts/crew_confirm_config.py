#!/usr/bin/env python3
"""The double confirmation behind a sensitive config change (crew 1.3.9).

A change that lifts a human step -- a `humanOnly.*` key set to `false`
(`crew_humanonly`), or since crew 1.3.61 a machine `guards.git.allow` set to
`"all"` or a list of git subcommands (`crew_gitallow`) -- is never written by
`crew_config.py --set` or the
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
This CLI has no `confirm` subcommand, and in crew 1.3.9 no hook calls
`confirm` yet: wiring it into the prompt hook is review harness
(`approval_hook.py` / `crew_hook.py`), which lands alone. Until then a
proposal can be made, listed and cancelled, and never applied, so an opt-out
cannot be switched on by any route crew offers.

CLI (no writes except `propose` and `cancel`, both into the store only):

    crew_confirm_config.py propose --layer machine|repo --key humanOnly.<k> [--root R]
    crew_confirm_config.py propose --layer machine --key guards.git.allow --value '"all"'
                                   (or --value '["commit","push"]'; crew 1.3.61)
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
import crew_gitallow
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


def propose(layer, dotted, root=None, global_path=None, now=None, tracker=None,
            value=False):
    """Record a pending change `dotted: value` at `layer`; returns the record.

    `dotted` is a humanOnly key (value `false`) or, crew 1.3.61,
    `guards.git.allow` (machine layer only; value `"all"` or a list of git
    subcommand names). Refused otherwise, and when the repo file is absent,
    tracked by git, or git cannot tell (a tracked file can never opt out, and
    could-not-tell is not untracked)."""
    if dotted == crew_gitallow.KEY:
        if layer != "machine":
            raise Refused(f"{dotted} lives in the machine file only; a repo file may only "
                          "veto it with \"off\"")
        if crew_gitallow.normalise(value) in (None, crew_gitallow.OFF):
            raise Refused(f"{dotted} = {json.dumps(value)} is not \"all\" or a non-empty list "
                          "of git subcommand names (turning it off needs no confirmation: "
                          "crew_config.py --set guards.git.allow='\"off\"' --apply)")
    elif not crew_humanonly.is_path(dotted):
        raise Refused(f"{dotted} is not a key that needs a double confirmation "
                      f"(those are: {', '.join(crew_humanonly.PATHS + (crew_gitallow.KEY,))})")
    elif value is not False:
        raise Refused(f"{dotted} is only ever confirmed to false")
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
        "layer": layer, "key": dotted, "value": value,
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
        # crew 1.3.61: a guards.git.allow change carries its value; a humanOnly
        # change is always `false` and the writer's default.
        extra = {"value": record.get("value")} if record["key"] == crew_gitallow.KEY else {}
        writer(record["layer"], record["key"], record["path"], record["targetDigest"],
               global_path=global_path, **extra)
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
    if record["key"] == crew_gitallow.KEY:
        return [
            f"proposed {record['change_id']}: {record['key']} = {json.dumps(record['value'])} "
            f"in the machine file {record['path']}",
            f"to apply it, the owner types /crew:confirm-config {record['change_id']} twice, "
            "in two separate prompts, within "
            f"{crew_humanonly.PROPOSAL_TTL_SECONDS // 60} minutes.",
            "once applied, crew's command guards stop blocking or asking on the git commands "
            "it covers; `crew_gitallow.py` shows what is in force.",
        ]
    return [
        f"proposed {record['change_id']}: {record['key']} = false in the {record['layer']} "
        f"file {record['path']}",
        f"to apply it, the owner types /crew:confirm-config {record['change_id']} twice, "
        "in two separate prompts, within "
        f"{crew_humanonly.PROPOSAL_TTL_SECONDS // 60} minutes.",
        "crew 1.3.9: no hook records that confirmation yet (the prompt-hook wiring lands "
        "separately), so this change stays pending and then expires; nothing acts on "
        "humanOnly until that wiring lands either.",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_confirm_config.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--layer", required=True, choices=("machine", "repo"))
    p.add_argument("--key", required=True)
    p.add_argument("--value", default=None,
                   help="JSON value; guards.git.allow only (\"all\" or a list of names)")
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
            value = False
            if args.value is not None:
                try:
                    value = json.loads(args.value)
                except ValueError as exc:
                    raise Refused(f"--value {args.value!r} is not JSON ({exc})") from exc
            record = propose(args.layer, args.key, root=args.root,
                             global_path=args.global_path, value=value)
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
