"""The owner's opt-out of crew's two human-only rules (crew 1.3.7).

`humanOnly.approve` covers `/crew:approve` (a plan approval the user types);
`humanOnly.promoteMarker` covers the production promote marker
`.crew/.approved-<env>-<sha>`. Each key is `null` (silent), `true` (human-only)
or `false` (the owner opts out). The default is human-only.

**What this module is, and is not.** It holds the rules for WHEN an opt-out is
in force (`resolve`) and the receipts store the double confirmation writes
(`crew_confirm_config`). Nothing in crew's hooks reads `resolve` yet: the hooks
that would accept an agent-written approval or promote marker once a key is
`false` are review harness (`scripts/check-tooling-pr.py` `HARNESS`), so they
land alone in a later change. Until then every key's value changes nothing,
and the human-only rules hold exactly as they did before 1.3.7.

The owner's decisions (2026-11-06), each enforced here:

- **Where an opt-out may live.** The machine-global file
  (`~/.claude/crew/config.json`) and an UNTRACKED repo file. A repo
  `.crew/config.json` that git tracks can never opt out: a cloned repository
  must not lift a human step on someone else's machine. "Could not tell"
  (no git, not a work tree, git failed) is never "untracked".
- **Stricter wins.** A `true` in either layer vetoes a `false` in the other.
  A layer that is silent (absent or `null`) imposes nothing.
- **A double confirmation.** A `false` counts only when an applied receipt
  in the store backs it (`receipt_backs`): the owner proposed the change and
  typed `/crew:confirm-config <change_id>` twice, in two prompts. A `false`
  written into a file any other way (a hand edit, an agent's Edit) is read
  as human-only.
- **Unknown is strict.** A value that is not `null`, `true` or `false`, an
  unreadable store or a receipt that does not parse reads as human-only.

Standard library only; imports nothing that imports `crew_config`, so
`crew_config` may import it.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import time

import crew_common
import crew_config_files
import crew_state

KEYS = ("approve", "promoteMarker")
PATHS = tuple(f"humanOnly.{key}" for key in KEYS)
# The values each key takes, the tuple both config writers refuse against.
VALUES = (None, True, False)

TRACKED, UNTRACKED, UNKNOWN = "tracked", "untracked", "could not tell"

# A proposal must be confirmed twice within this many seconds of being made.
PROPOSAL_TTL_SECONDS = 15 * 60
# The only `via` a confirmation may carry: the UserPromptSubmit hook's, for a
# prompt the user typed. Nothing in this plugin passes it yet (see the module
# docstring), so no confirmation can be recorded until that hook lands.
USER_PROMPT = "user-prompt"

PENDING, APPLIED = "pending", "applied"
FINAL_STATES = ("applied", "expired", "cancelled", "stale", "refused", "revoked")

SENSITIVE_REFUSAL = (
    "removes a human step, so it needs the owner's double confirmation: "
    "`crew_confirm_config.py propose` records it and prints a change id, and "
    "the owner types /crew:confirm-config <change_id> twice. (In crew 1.3.7 "
    "nothing records that confirmation yet, so the change cannot complete.)")
REPO_UNVETO_REFUSAL = (
    "removing a repo's human-only veto lifts a human step; the owner edits "
    ".crew/config.json by hand")


# --- what a write may do --------------------------------------------------------

def is_path(dotted):
    return dotted in PATHS


def write_refusal(dotted, layer, value):
    """Why a crew WRITER may not set `dotted` to `value` at `layer`, or None.

    Only a change that cannot lift a human step is a plain write: `true`
    anywhere, and `null` or a removal at the machine layer (silent there is
    the human-only default). A `false` anywhere, or a repo `null` or removal
    (which drops a veto), is refused here; the first goes through
    `crew_confirm_config`, the second is a hand edit. A value outside
    `VALUES` is left to the enum check, which names the values."""
    if not is_path(dotted):
        return None
    if value is True:
        return None
    if value is None:
        return None if layer == "machine" else REPO_UNVETO_REFUSAL
    if value is False:
        return SENSITIVE_REFUSAL
    return None


# --- is the repo file tracked ---------------------------------------------------

def tracking(config_path, runner=None):
    """`TRACKED`, `UNTRACKED` or `UNKNOWN` for the file at `config_path`.

    `git ls-files --error-unmatch` exits 0 for a file in the index (tracked or
    staged) and 1 for one it does not know. Anything else -- git missing, not
    a work tree, a timeout -- is `UNKNOWN`, never untracked."""
    run = runner or subprocess.run
    directory, name = os.path.split(os.path.abspath(config_path))
    try:
        proc = run(["git", "-C", directory, "ls-files", "--error-unmatch", "--", name],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    if proc.returncode == 0:
        return TRACKED
    if proc.returncode == 1:
        return UNTRACKED
    return UNKNOWN


# --- the receipts store -----------------------------------------------------------

def store_dir(global_path=None):
    """`<dir of the machine config>/confirm-config`: beside the file the owner
    owns, never inside a repository."""
    path = global_path or crew_state.GLOBAL_CONFIG_PATH
    return os.path.join(os.path.dirname(os.path.abspath(path)), "confirm-config")


def target_key(path):
    """One spelling of a config file's path, so a receipt and a read agree."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def new_change_id():
    return "cc-" + secrets.token_hex(4)


def valid_change_id(change_id):
    return (isinstance(change_id, str) and len(change_id) == 11
            and change_id.startswith("cc-")
            and all(c in "0123456789abcdef" for c in change_id[3:]))


def record_path(store, change_id):
    if not valid_change_id(change_id):
        raise ValueError(f"not a change id: {change_id!r}")
    return os.path.join(store, change_id + ".json")


def write_record(store, record):
    """Write one record whole: a sibling temp file, then `os.replace`, so a
    reader never sees a half-written record."""
    os.makedirs(store, exist_ok=True)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    final = record_path(store, record["change_id"])
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=store)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_record(store, change_id):
    """The record, or None when there is none. Raises ValueError for one
    that is there and does not parse: a broken receipt is never "none"."""
    path = record_path(store, change_id)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: unreadable ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a record")
    return data


def all_records(store):
    """`(records, problems)`: every record that parses, and one line for each
    that does not. A missing store is `([], [])`."""
    try:
        names = sorted(os.listdir(store))
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"{store}: cannot be listed ({exc})"]
    records, problems = [], []
    for name in names:
        if not name.endswith(".json") or not valid_change_id(name[:-5]):
            continue
        try:
            record = read_record(store, name[:-5])
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if record is not None:
            records.append(record)
    return records, problems


def receipt_backs(store, layer, path, dotted):
    """`(backed, why)`: True only when the NEWEST settled record for this
    (layer, file, key) is an applied `false`. A later revocation, or a store
    that cannot be read whole, is not backed."""
    records, problems = all_records(store)
    if problems:
        return False, "the confirmation store could not be read: " + "; ".join(problems)
    key = target_key(path)
    settled = [r for r in records
               if r.get("layer") == layer and r.get("target") == key
               and r.get("key") == dotted and r.get("state") in (APPLIED, "revoked")
               and isinstance(r.get("settled"), (int, float))]
    if not settled:
        return False, "no double-confirmed change set it"
    newest = max(settled, key=lambda r: r["settled"])
    if newest.get("state") == APPLIED and newest.get("value") is False:
        return True, f"double-confirmed by {newest.get('change_id')}"
    return False, f"the last confirmed change ({newest.get('change_id')}) was revoked"


def revoke(layer, path, dotted, global_path=None, now=None, reason="a later crew write"):
    """Record that a crew writer set `dotted` back to human-only at this
    (layer, file), so an earlier receipt no longer backs a `false` there.
    Best effort: a store that cannot be written changes nothing, because a
    receipt only ever narrows on read (`receipt_backs` wants the newest)."""
    store = store_dir(global_path)
    stamp = time.time() if now is None else now
    record = {"change_id": new_change_id(), "layer": layer, "target": target_key(path),
              "key": dotted, "value": None, "state": "revoked", "created": stamp,
              "settled": stamp, "reason": reason, "confirmations": []}
    try:
        write_record(store, record)
    except OSError:
        return False
    return True


# --- what is in force -------------------------------------------------------------

def _layer_value(cfg, key):
    block = cfg.get("humanOnly") if isinstance(cfg, dict) else None
    if not isinstance(block, dict) or key not in block:
        return None
    return block[key]


def resolve(root, key, global_path=None, store=None, tracker=None):
    """`{"humanOnly", "reason", "layers"}` for `key` (`approve` or
    `promoteMarker`). `humanOnly` is False only when a layer's `false` is
    admitted (machine, or an untracked repo file) and double-confirmed, and
    no layer says `true` or something unreadable."""
    if key not in KEYS:
        raise KeyError(key)
    dotted = f"humanOnly.{key}"
    machine_path = global_path or crew_state.GLOBAL_CONFIG_PATH
    repo_path = crew_common.repo_config_file(root, "config.json")
    store = store or store_dir(global_path)
    layers = {}
    for layer, path in (("machine", machine_path), ("repo", repo_path)):
        cfg, _state = crew_config_files.read_tolerant(path)
        value = _layer_value(cfg, key)
        row = {"path": path, "value": value}
        if value is None:
            row["vote"], row["why"] = "silent", "not set"
        elif value is True:
            row["vote"], row["why"] = "strict", "true (human-only)"
        elif value is not False:
            row["vote"], row["why"] = "strict", f"{value!r} is not null, true or false"
        else:
            row["vote"], row["why"] = "opt-out", "false"
            if layer == "repo":
                state = (tracker or tracking)(path)
                row["tracking"] = state
                if state != UNTRACKED:
                    row["vote"] = "strict"
                    row["why"] = (f"false in a {state} .crew/config.json; only the machine "
                                  "file or an untracked repo file may opt out"
                                  if state == TRACKED else
                                  "false, but whether git tracks .crew/config.json could "
                                  "not be told, so it is read as human-only")
            if row["vote"] == "opt-out":
                backed, why = receipt_backs(store, layer, path, dotted)
                if not backed:
                    row["vote"], row["why"] = "strict", f"false, not honoured: {why}"
                else:
                    row["why"] = f"false, {why}"
        layers[layer] = row
    strict = [name for name, row in layers.items() if row["vote"] == "strict"]
    opt_out = [name for name, row in layers.items() if row["vote"] == "opt-out"]
    if opt_out and not strict:
        return {"humanOnly": False, "layers": layers,
                "reason": f"{dotted} opted out in the {' and '.join(opt_out)} file"}
    if strict:
        return {"humanOnly": True, "layers": layers,
                "reason": "; ".join(f"{name}: {layers[name]['why']}" for name in strict)}
    return {"humanOnly": True, "layers": layers, "reason": "the default (human-only)"}
