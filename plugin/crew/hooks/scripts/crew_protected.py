#!/usr/bin/env python3
"""crew_protected.py: the protected-policy comparator (R-32, plan 4.3).

REPORT-ONLY. Nothing in the plugin imports this module, so it refuses
nothing; `test_crew_protected.py` holds that (no other plugin source names
it). It answers one question: "would this change, or this drift, widen a
protected key?", with the reason. R-32b wires it into the Write/Edit hook
and R-32c into crew's readers and writers, both report-only first.

What it compares is the EFFECTIVE value of every protected leaf, computed by
the reader that enforces that leaf (`READERS`), never the file text: a set,
a delete, a whole-file replacement, a write through a link and an alternate
writer are therefore all the same question. Each leaf has one direction
(`DIRECTIONS`) that says which way is wider.

Two entry points, one comparator:

  judge_change(before, after)  a write crew can see beforehand: the caller
      supplies the bytes of each layer before and after. Both sides are read
      in throwaway roots by the same readers, so it never confirms a receipt
      (a receipt is bound to the real file).
  judge_drift(root)  everything else: the current effective policy on the
      real paths against the last confirmed baseline
      (`<machine config dir>/protected-policy/baseline.json`).

Rules this file holds (each is a test):
  * Unknown is its own value and counts as widening: a layer that cannot be
    read, does not parse, repeats a key or is not an object; a layer reached
    through a link whose target is not the one the baseline recorded; a
    value outside its leaf's domain; a leaf with no row; a baseline that
    cannot be read. The readers' own collapse of these to a safe value is
    not inherited: `read_layer` runs first.
  * For the receipt-bound leaves (`humanOnly.*`, `guards.git.allow`) the raw
    per-layer value is compared as well, absent read as the reader's silent
    default, and the leaf's outcome is the WIDER of the two. A raw widening
    the reader did not honour is a hand edit: `change-guard-config-directly`.
  * A widening of any other leaf is confirmed only by a one-way
    `widen-policy` receipt binding both digests, and no such receipt exists
    until R-23 (`_policy_receipt`), so today it is always unconfirmed.
  * The baseline advances only when every change is a provable narrowing or
    a confirmed widening; `baseline --init` will not absorb a widening.

Outcomes are named after the operations of the deny-first table by string
only: `free`, `widen-policy`, `change-guard-config-directly`.

CLI: `crew_protected.py check|explain|keys [--root R] [--global-path P]`,
`crew_protected.py baseline --init [--root R]`. Exit 0 free, 1 would refuse
(nothing is refused), 2 usage.
"""
import contextlib
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

import crew_common
import crew_config
import crew_gitallow
import crew_guards
import crew_humanonly
import crew_state

REPORT_ONLY = True
STORE_DIR = os.path.join(os.path.dirname(crew_state.GLOBAL_CONFIG_PATH), "protected-policy")
BASELINE_NAME = "baseline.json"

FREE = "free"
WIDEN_POLICY = "widen-policy"
DIRECT = "change-guard-config-directly"

UNCHANGED, NARROWING, WIDENING, UNKNOWN = "unchanged", "narrowing", "widening", "unknown"
NO_BASELINE = "no-baseline"

# Plan 4.3's protected keys. A dotted entry protects that subtree only.
PROTECTED = ("guards", "approvals", "humanOnly", "environments", "production", "tiers",
             "cloud", "unattendedCloud", "worktrees.root", "autopilot.sleep", "scope", "mode",
             "decider", "serious", "accounts", "applications", "admin")
# Ratcheted keys outside plan 4.3: named, so a new one cannot be left out silently.
NOT_PROTECTED = ("install.policy", "change.requireForProduction")

GUARD_LEAVES = tuple(f"guards.{name}" for name in crew_guards.ALL_GUARD_NAMES)
RECEIPT_BOUND = ("humanOnly.approve", "humanOnly.promoteMarker", "guards.git.allow")
SLEEP_KEYS = ("approval", "questions", "deploy")
UNATTENDED_LEAVES = ("unattendedCloud.aws.nonProd", "unattendedCloud.aws.readOnly.profile",
                     "unattendedCloud.aws.readOnly.identity",
                     "unattendedCloud.aws.readOnly.region")
LEAVES = GUARD_LEAVES + (
    "guards.profile", "guards.overrides", "guards.git.allow",
    "environments.prodUnattended", "environments.nonProd", "environments.workflows",
    "environments.preProduction", "production.hosts", "production.databases",
    "cloud.awsProfiles", "cloud.awsRegions", "cloud.azureSubscriptions",
    "humanOnly.approve", "humanOnly.promoteMarker", "scope.mode", "scope.allowCliApproval",
    "autopilot.sleep.schedule", "autopilot.sleep.approval", "autopilot.sleep.questions",
    "autopilot.sleep.deploy") + UNATTENDED_LEAVES + ("worktrees.root",)

# leaf (or `guards.<name>` for the twelve guards) -> (enforcing reader, where, layers)
READERS = {
    "guards.<name>": ("crew_config.resolve_ratcheted", "crew_config.py:1007", "both"),
    "guards.profile": ("crew_guards.layer_guard_state", "crew_guards.py:654", "both"),
    "guards.overrides": ("crew_guards.layer_guard_state", "crew_guards.py:654", "both"),
    "guards.git.allow": ("crew_gitallow.settings", "crew_gitallow.py:841", "both"),
    "environments.prodUnattended": ("crew_config.resolve_ratcheted", "crew_config.py:1007",
                                    "both"),
    "environments.nonProd": ("cloud_guard.environments_config", "cloud_guard.py:2608", "repo"),
    "environments.workflows": ("cloud_guard.environments_config", "cloud_guard.py:2608", "repo"),
    "environments.preProduction": ("cloud_guard.environments_config", "cloud_guard.py:2608",
                                   "repo"),
    "production.hosts": ("crew_config.production_declaration", "crew_config.py:1547", "repo"),
    "production.databases": ("crew_config.production_declaration", "crew_config.py:1547",
                             "repo"),
    "cloud.awsProfiles": ("cloud_guard.cloud_pins", "cloud_guard.py:2578", "repo"),
    "cloud.awsRegions": ("cloud_guard.cloud_pins", "cloud_guard.py:2578", "repo"),
    "cloud.azureSubscriptions": ("cloud_guard.cloud_pins", "cloud_guard.py:2578", "repo"),
    "humanOnly.approve": ("crew_humanonly.resolve", "crew_humanonly.py:258", "both"),
    "humanOnly.promoteMarker": ("crew_humanonly.resolve", "crew_humanonly.py:258", "both"),
    "scope.mode": ("crew_ticket.configured_mode", "crew_ticket.py:1264", "repo"),
    "scope.allowCliApproval": ("crew_ticket.cli_approval_allowed", "crew_ticket.py:900", "both"),
    "autopilot.sleep.schedule": ("crew_autopilot._sleep_block", "crew_autopilot.py:1964", "repo"),
    "autopilot.sleep.approval": ("crew_autopilot._sleep_block", "crew_autopilot.py:1964", "both"),
    "autopilot.sleep.questions": ("crew_autopilot._sleep_block", "crew_autopilot.py:1964",
                                  "both"),
    "autopilot.sleep.deploy": ("crew_autopilot._sleep_block", "crew_autopilot.py:1964", "both"),
    "unattendedCloud.**": ("crew_config.unattended_cloud_block_problem", "crew_config.py:1268",
                           "machine"),
    "worktrees.root": ("crew_worktrees.resolve", "crew_worktrees.py:130", "both"),
}

_SLEEP_TIERS = {key: crew_guards.PERSONAL_KEYS[f"autopilot.{key}"][1] for key in SLEEP_KEYS}
# leaf (or row name) -> (kind, argument)
DIRECTIONS = {
    "guards.<name>": ("rank", "guard"),
    "environments.prodUnattended": ("rank", crew_guards.prod_unattended_rank),
    "guards.profile": ("derived", "guards"),
    "guards.overrides": ("derived", "guards"),
    "environments.nonProd": ("allow-set", None),
    "cloud.awsProfiles": ("allow-set", None),
    "cloud.awsRegions": ("allow-set", None),
    "cloud.azureSubscriptions": ("allow-set", None),
    "production.hosts": ("restrict-set", None),
    "production.databases": ("restrict-set", None),
    "humanOnly.approve": ("strict-bool", True),
    "humanOnly.promoteMarker": ("strict-bool", True),
    "scope.allowCliApproval": ("strict-bool", False),
    "guards.git.allow": ("git-allow", None),
    "scope.mode": ("enum-order", ("block", "auto", "report", "off")),
    "autopilot.sleep.approval": ("sleep-tier", _SLEEP_TIERS["approval"]),
    "autopilot.sleep.questions": ("sleep-tier", _SLEEP_TIERS["questions"]),
    "autopilot.sleep.deploy": ("sleep-tier", _SLEEP_TIERS["deploy"]),
    "autopilot.sleep.schedule": ("pinned", None),
    "worktrees.root": ("pinned", None),
    "environments.workflows": ("pinned", None),
    "environments.preProduction": ("pinned", None),
    "unattendedCloud.**": ("pinned", None),
}


def row_name(leaf):
    """The `READERS` / `DIRECTIONS` key that covers `leaf`, or None."""
    if leaf in GUARD_LEAVES:
        return "guards.<name>"
    if leaf.startswith("unattendedCloud."):
        return "unattendedCloud.**"
    return leaf if leaf in READERS else None


class Unknown:
    """A value that could not be told, with why. Never equal to a value."""

    def __init__(self, why):
        self.why = why

    def __eq__(self, other):
        return False

    def __hash__(self):
        return hash(("unknown", self.why))

    def __repr__(self):
        return f"Unknown({self.why!r})"


# --- the strict read of one layer -----------------------------------------------------------

_MISSING = object()


def read_layer(path, recorded_target=None):
    """`{"state", "cfg", "why", "target"}` for one config file. `state` is
    `absent`, `ok` or `unknown`. Strict: a file that cannot be read, is not
    UTF-8 JSON, repeats a key or is not an object is `unknown`, never absent;
    so is a path whose resolved target (`crew_humanonly.target_key`) is not
    `recorded_target` when one was recorded (a link added, retargeted or
    removed after the baseline). A leading BOM is accepted (utf-8-sig), as
    the enforcing readers accept it: `crew_common.read_text` and
    `crew_gitallow`'s strict read both decode utf-8-sig."""
    target = crew_humanonly.target_key(path)
    out = {"state": "ok", "cfg": {}, "why": "", "target": target}
    if recorded_target is not None and target != recorded_target:
        out.update(state=UNKNOWN, why=f"{path} now resolves to {target}, not the "
                                      f"{recorded_target} the baseline recorded")
        return out
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError:
        if os.path.lexists(path):
            out.update(state=UNKNOWN, why=f"{path} is a link that does not resolve")
        else:
            out["state"] = "absent"
        return out
    except OSError as exc:
        out.update(state=UNKNOWN, why=f"{path} cannot be read ({type(exc).__name__})")
        return out
    try:
        cfg = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=crew_gitallow.strict_pairs)
    except ValueError:
        out.update(state=UNKNOWN, why=f"{path} does not parse as UTF-8 JSON (or repeats a key)")
        return out
    if not isinstance(cfg, dict):
        out.update(state=UNKNOWN, why=f"{path} is not a JSON object")
        return out
    out["cfg"] = cfg
    return out


def _dig(cfg, dotted):
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _protected_leaves(cfg):
    """Every leaf path under a protected prefix in one layer's raw config."""
    out = {}

    def walk(node, here):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{here}.{key}")
        else:
            out[here] = node

    for top in PROTECTED:
        node = _dig(cfg, top)
        if node is not _MISSING:
            walk(node, top)
    return out


def _covered(path):
    """True when a raw path is an input some row reads."""
    if path.split(".")[0] == "unattendedCloud":
        return True
    for leaf in tuple(READERS) + GUARD_LEAVES:
        if leaf.startswith("guards.<") or leaf.endswith(".**"):
            continue
        if path == leaf or path.startswith(leaf + "."):
            return True
    return False


# --- the readers, called on the paths they are given ----------------------------------------

@contextlib.contextmanager
def _machine_at(path):
    """Point the readers that take only `root` at `path` for the machine
    layer: the same module attributes the suites patch (`GLOBAL_CONFIG_PATH`
    in `crew_state` and `crew_config`). Not thread-safe; restored on exit."""
    saved = crew_state.GLOBAL_CONFIG_PATH, crew_config.GLOBAL_CONFIG_PATH
    crew_state.GLOBAL_CONFIG_PATH = crew_config.GLOBAL_CONFIG_PATH = path
    try:
        yield
    finally:
        crew_state.GLOBAL_CONFIG_PATH, crew_config.GLOBAL_CONFIG_PATH = saved


def _canon(value):
    """A JSON-able, order-free spelling of a reader's value."""
    if isinstance(value, Unknown):
        return value
    if isinstance(value, (set, frozenset)):
        return sorted(_canon(v) for v in value)
    return json.loads(json.dumps(value, sort_keys=True))


def _git_allow_canon(setting):
    if setting is None:
        return Unknown("not null, \"off\", \"all\" or a list of git subcommand names")
    return sorted(setting) if isinstance(setting, frozenset) else setting


def _set_of(values):
    return sorted({json.dumps(v, sort_keys=True) for v in values})


def _guard_leaf(ctx, name):
    tiers = crew_guards.guard_tiers(name)[0]
    for layer in ("machine", "repo"):
        block = ctx["layers"][layer]["cfg"].get("guards")
        if isinstance(block, dict) and block.get(name) is not None:
            legacy = block[name]
            if not (isinstance(legacy, str) and legacy.strip().lower() in tiers):
                return Unknown(f"{layer} guards.{name} = {legacy!r} is not one of {tiers}")
    row = crew_config.resolve_ratcheted(ctx["root"], f"guards.{name}", ctx["machine"])
    return row["effective"]


def _guards_derived(ctx):
    """`ok`, or Unknown when a layer's profile or overrides cannot be read."""
    for layer in ("machine", "repo"):
        block = ctx["layers"][layer]["cfg"].get("guards", _MISSING)
        if block is _MISSING or block is None:
            continue
        if not isinstance(block, dict):
            return Unknown(f"{layer} guards is not an object")
        if "profile" in block and crew_guards.normalise_profile(block["profile"]) is None:
            return Unknown(f"{layer} guards.profile = {block['profile']!r} is not a profile")
        if "overrides" in block:
            overrides = block["overrides"]
            if not isinstance(overrides, dict):
                return Unknown(f"{layer} guards.overrides is not an object")
            for name, value in overrides.items():
                if name not in crew_guards.ALL_GUARD_NAMES:
                    return Unknown(f"{layer} guards.overrides.{name} is not a guard")
                tiers = crew_guards.guard_tiers(name)[0]
                if not (isinstance(value, str) and value.strip().lower() in tiers):
                    return Unknown(f"{layer} guards.overrides.{name} = {value!r} is not "
                                   f"one of {tiers}")
    return "ok"


def _raw_git_allow(path):
    state, value, _binding = crew_gitallow.read_layer(path)
    if state == crew_gitallow.UNREADABLE:
        return Unknown(f"{path} {value}")
    if state != crew_gitallow.SET:
        return crew_gitallow.OFF
    return _git_allow_canon(crew_gitallow.normalise(value))


def _raw_human_only(cfg, key):
    block = cfg.get("humanOnly", _MISSING)
    if block is _MISSING or block is None:
        return True
    if not isinstance(block, dict):
        return Unknown("humanOnly is not an object")
    value = block.get(key)
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return Unknown(f"humanOnly.{key} = {value!r} is not null, true or false")


def _bool_domain(ctx, dotted, layers=("machine", "repo")):
    for layer in layers:
        value = _dig(ctx["layers"][layer]["cfg"], dotted)
        if value is not _MISSING and value is not None and not isinstance(value, bool):
            return Unknown(f"{layer} {dotted} = {value!r} is not true or false")
    return None


def _compute(ctx):
    """`(policy, raw, honour)`: every leaf's effective value, the raw
    per-layer values of the receipt-bound leaves, and whether each layer's
    raw value is one the reader honoured (with its why)."""
    # pylint: disable=import-outside-toplevel,protected-access,too-many-locals
    import cloud_guard
    import crew_autopilot
    import crew_ticket
    import crew_worktrees
    root, machine, store = ctx["root"], ctx["machine"], ctx["store"]
    layers = ctx["layers"]
    policy, raw, honour = {}, {}, {}
    for name in crew_guards.ALL_GUARD_NAMES:
        policy[f"guards.{name}"] = _guard_leaf(ctx, name)
    derived = _guards_derived(ctx)
    policy["guards.profile"] = policy["guards.overrides"] = derived
    policy["environments.prodUnattended"] = _bool_domain(ctx, "environments.prodUnattended") \
        or crew_config.resolve_ratcheted(root, "environments.prodUnattended", machine)["effective"]

    setting = crew_gitallow.settings(root, global_path=machine, store=store)
    policy["guards.git.allow"] = _git_allow_canon(setting["allow"])
    backed = crew_gitallow.backing(machine, global_path=machine, store=store)
    raw["guards.git.allow"] = {"machine": _raw_git_allow(machine),
                               "repo": _raw_git_allow(ctx["repo_file"])}
    honour["guards.git.allow"] = {
        "machine": (backed is not None, setting["why"]),
        "repo": (False, "a repo file can never turn guards.git.allow on")}

    for key in crew_humanonly.KEYS:
        dotted = f"humanOnly.{key}"
        answer = crew_humanonly.resolve(root, key, global_path=machine, store=store,
                                        tracker=ctx["tracker"])
        policy[dotted] = answer["humanOnly"]
        raw[dotted] = {layer: _raw_human_only(layers[layer]["cfg"], key)
                       for layer in ("machine", "repo")}
        honour[dotted] = {layer: (row.get("vote") == "opt-out", row.get("why", ""))
                          for layer, row in answer["layers"].items()}

    mode = _dig(layers["repo"]["cfg"], "scope.mode")
    policy["scope.mode"] = Unknown(f"scope.mode = {mode!r} is not one of {crew_ticket.MODES}") \
        if mode not in (_MISSING, None) and mode not in crew_ticket.MODES \
        else crew_ticket.configured_mode(root)[0]
    policy["scope.allowCliApproval"] = _bool_domain(ctx, "scope.allowCliApproval", ("repo",)) \
        or crew_ticket.cli_approval_allowed(root)
    # The reader is also True when humanOnly.approve is opted out; whether the
    # repo itself says exactly true tells the two apart (`_judge`).
    raw["scope.allowCliApproval"] = {
        "repo": _dig(layers["repo"]["cfg"], "scope.allowCliApproval") is True}

    resolved = crew_config.resolve_config(root)
    block = resolved.get("autopilot") if isinstance(resolved.get("autopilot"), dict) else {}
    sleep = crew_autopilot._sleep_block(root, block)
    if not isinstance(sleep, dict):
        for key in ("schedule",) + SLEEP_KEYS:
            policy[f"autopilot.sleep.{key}"] = Unknown("autopilot.sleep is not an object")
    else:
        policy["autopilot.sleep.schedule"] = _canon(sleep.get("schedule"))
        for key in SLEEP_KEYS:
            value = sleep.get(key)
            value = block.get(key) if value is None else value
            policy[f"autopilot.sleep.{key}"] = value if value in _SLEEP_TIERS[key] and \
                isinstance(value, str) else Unknown(
                    f"the sleeping autopilot.{key} value {value!r} is not one of "
                    f"{_SLEEP_TIERS[key]}")

    cloud_block = layers["machine"]["cfg"].get("unattendedCloud", _MISSING)
    problem = "" if cloud_block in (_MISSING, None) else \
        crew_config.unattended_cloud_block_problem(cloud_block)
    for leaf in UNATTENDED_LEAVES:
        value = None if cloud_block in (_MISSING, None) else \
            _dig({"unattendedCloud": cloud_block}, leaf)
        policy[leaf] = Unknown(problem) if problem else \
            _canon(None if value is _MISSING else value)

    where = crew_worktrees.resolve(root)
    policy["worktrees.root"] = {"base": where["base"], "problem": bool(where["problem"])}

    envs = cloud_guard.environments_config(root)
    for key in ("nonProd", "workflows", "preProduction"):
        dotted = f"environments.{key}"
        if envs["problem"]:
            policy[dotted] = Unknown(envs["problem"])
        elif key == "nonProd":
            policy[dotted] = _set_of(envs[key])
        else:
            policy[dotted] = _canon(envs[key])

    for key, guard in (("hosts", "prodServer"), ("databases", "prodDatabase")):
        found = crew_config.production_declaration(root, guard)
        policy[f"production.{key}"] = Unknown(found.detail) if found.state in (
            crew_config.PROD_DECL_MALFORMED, crew_config.PROD_DECL_UNREADABLE) \
            else _set_of(found.patterns)

    pins, problem = cloud_guard.cloud_pins(root)
    for key in ("awsProfiles", "awsRegions", "azureSubscriptions"):
        policy[f"cloud.{key}"] = Unknown(problem) if problem else _set_of(pins[key])
    return policy, raw, honour


def _unrowed(layers):
    """Raw values of protected paths no row reads, per layer: any change to
    one is unknown (decision 5: no row, no direction)."""
    out = {}
    for layer in ("machine", "repo"):
        for path, value in _protected_leaves(layers[layer]["cfg"]).items():
            if not _covered(path):
                out.setdefault(path, {})[layer] = _canon(value)
    return out


def effective_protected(root, global_path=None, store=None, tracker=None, targets=None):
    """`{"policy", "raw", "honour", "unrowed", "targets", "layers"}` for the
    repo at `root` on the paths given (the real ones by default).

    Each layer is read strictly first (`read_layer`); a leaf that reads a
    layer that is `unknown` is Unknown whatever its reader would say."""
    machine = global_path or crew_state.GLOBAL_CONFIG_PATH
    repo_file = crew_common.repo_config_file(root, "config.json")
    targets = targets or {}
    layers = {"machine": read_layer(machine, targets.get("machine")),
              "repo": read_layer(repo_file, targets.get("repo"))}
    ctx = {"root": root, "machine": machine, "repo_file": repo_file, "layers": layers,
           "store": store or crew_humanonly.store_dir(machine), "tracker": tracker}
    with _machine_at(machine):
        policy, raw, honour = _compute(ctx)
    bad = {layer: row["why"] for layer, row in layers.items() if row["state"] == UNKNOWN}
    for leaf in LEAVES:
        uses = READERS[row_name(leaf)][2]
        hit = [why for layer, why in bad.items() if uses in ("both", layer)]
        if hit:
            policy[leaf] = Unknown("; ".join(hit))
            if leaf in raw:
                raw[leaf] = {layer: Unknown(bad[layer]) if layer in bad else value
                             for layer, value in raw[leaf].items()}
    return {"policy": policy, "raw": raw, "honour": honour, "unrowed": _unrowed(layers),
            "targets": {layer: row["target"] for layer, row in layers.items()},
            "layers": {layer: row["state"] for layer, row in layers.items()}}


# --- the comparator ---------------------------------------------------------------------------

def _rank_of(kind_arg, leaf, value):
    if kind_arg == "guard":
        return crew_guards.guard_tiers(leaf.split(".", 1)[1])[2](value)
    return kind_arg(value)


def _git_rank(value):
    if value == crew_gitallow.OFF:
        return 0, frozenset()
    if value == crew_gitallow.ALL:
        return 2, frozenset()
    return 1, frozenset(value)


def compare(leaf, before, after):
    """`unchanged`, `narrowing`, `widening` or `unknown` for one leaf."""
    if isinstance(before, Unknown) or isinstance(after, Unknown):
        return UNKNOWN
    name = row_name(leaf)
    if name is None or name not in DIRECTIONS:
        return UNCHANGED if before == after else UNKNOWN
    if before == after:
        return UNCHANGED
    kind, arg = DIRECTIONS[name]
    try:
        if kind == "rank":
            low, high = _rank_of(arg, leaf, before), _rank_of(arg, leaf, after)
            return WIDENING if high > low else NARROWING
        if kind in ("allow-set", "restrict-set"):
            old, new = set(before), set(after)
            grew = bool(new - old)
            shrank = bool(old - new)
            if kind == "restrict-set":
                grew, shrank = shrank, grew
            return WIDENING if grew else NARROWING
        if kind == "strict-bool":
            return WIDENING if before is arg else NARROWING
        if kind == "git-allow":
            (lo, old), (hi, new) = _git_rank(before), _git_rank(after)
            if hi != lo:
                return WIDENING if hi > lo else NARROWING
            return NARROWING if new <= old else WIDENING
        if kind in ("enum-order", "sleep-tier"):
            return WIDENING if arg.index(after) > arg.index(before) else NARROWING
        if kind == "derived":
            return UNCHANGED
    except (TypeError, ValueError, KeyError):
        return UNKNOWN
    return WIDENING  # pinned: no order, so any change needs confirming



_ORDER = {UNCHANGED: 0, NARROWING: 0, "confirmed": 1, WIDENING: 2, UNKNOWN: 3}


def _policy_receipt(before_digest, after_digest):
    """Decision 6(b): a one-way `widen-policy` receipt binding both digests.
    The R-22/R-23 store does not exist yet, so there is never one."""
    del before_digest, after_digest
    return None, "no widen-policy receipt route exists until R-23"


def _digest(snapshot):
    body = {"policy": _jsonable(snapshot["policy"]), "raw": _jsonable(snapshot["raw"]),
            "unrowed": _jsonable(snapshot["unrowed"]), "targets": snapshot["targets"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def _jsonable(node):
    if isinstance(node, Unknown):
        return {"unknown": node.why}
    if isinstance(node, dict):
        return {k: _jsonable(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_jsonable(v) for v in node]
    return node


def _judge(before, after, route):
    """Compare two snapshots leaf by leaf. `route` is `writer`, `edit` or
    `drift`; only `drift` reads on the real paths, so only it may treat a
    receipt-bound change the reader honoured as confirmed."""
    real = route == "drift"
    rows = []
    receipt, receipt_why = _policy_receipt(_digest(before), _digest(after))
    for leaf in LEAVES:
        old, new = before["policy"].get(leaf), after["policy"].get(leaf)
        change = compare(leaf, old, new)
        row = {"leaf": leaf, "before": _jsonable(old), "after": _jsonable(new),
               "change": change, "outcome": change, "reason": ""}
        if change == WIDENING:
            if leaf in RECEIPT_BOUND and real:
                row["outcome"], row["reason"] = "confirmed", "the enforcing reader honoured it"
            elif leaf == "scope.allowCliApproval" and real and _follows_opt_out(after):
                row["outcome"], row["reason"] = "confirmed", (
                    "it follows the humanOnly.approve opt-out the enforcing reader honoured")
            elif receipt is not None:
                row["outcome"], row["reason"] = "confirmed", "a widen-policy receipt binds it"
            else:
                row["reason"] = ("confirm through /crew:confirm-config" if leaf in RECEIPT_BOUND
                                 else receipt_why)
        elif change == UNKNOWN:
            row["reason"] = "; ".join(v.why for v in (old, new) if isinstance(v, Unknown)) \
                or "no direction row"
        if leaf in RECEIPT_BOUND:
            _raw_rows(row, leaf, before, after, real)
        rows.append(row)
    for path in sorted(set(before["unrowed"]) | set(after["unrowed"])):
        old, new = before["unrowed"].get(path), after["unrowed"].get(path)
        change = UNCHANGED if old == new else UNKNOWN
        rows.append({"leaf": path, "before": old, "after": new, "change": change,
                     "outcome": change, "reason": "" if old == new else
                     "a protected key with no direction row"})
    worst = max((_ORDER[r["outcome"]] for r in rows), default=0)
    status = FREE if worst <= 1 else ("would-refuse" if worst == 2 else UNKNOWN)
    return {"route": route, "status": status, "leaves": rows,
            "changed": [r for r in rows if r["change"] != UNCHANGED]}


def _follows_opt_out(snapshot):
    """True when `scope.allowCliApproval` reads true only because the reader
    honoured a `humanOnly.approve` opt-out (`crew_ticket.cli_approval_allowed`
    asks `human_only_approve_opted_out`), not because the repo says so."""
    return snapshot["policy"].get("humanOnly.approve") is False and \
        snapshot["raw"].get("scope.allowCliApproval", {}).get("repo") is False


def _raw_rows(row, leaf, before, after, real):
    """The raw per-layer comparison of a receipt-bound leaf; the row's
    outcome becomes the wider of the effective and the raw result."""
    raw_rows = []
    for layer in ("machine", "repo"):
        old = before["raw"].get(leaf, {}).get(layer)
        new = after["raw"].get(leaf, {}).get(layer)
        change = compare(leaf, old, new)
        outcome, reason = change, ""
        if change == WIDENING:
            honoured, why = after.get("honour", {}).get(leaf, {}).get(layer, (False, ""))
            if not real:
                reason = "confirm through /crew:confirm-config"
            elif honoured:
                outcome, reason = "confirmed", "the enforcing reader honoured it"
            else:
                reason = f"would refuse: hand edit not honoured ({why})"
        raw_rows.append({"layer": layer, "change": change, "outcome": outcome,
                         "reason": reason})
        if _ORDER[outcome] > _ORDER[row["outcome"]]:
            row["outcome"], row["reason"] = outcome, reason
            if change != UNCHANGED and row["change"] == UNCHANGED:
                row["change"] = change
    row["raw"] = raw_rows


def classify(result):
    """`free`, `widen-policy` (a crew writer proposed a widening) or
    `change-guard-config-directly` (drift, or a direct Write/Edit)."""
    if result.get("status") == FREE:
        return FREE
    return WIDEN_POLICY if result.get("route") == "writer" else DIRECT


# --- judge_change: a write crew can see ---------------------------------------------------

def _materialise(base, layers):
    """Write `{"machine": bytes|None, "repo": bytes|None}` under `base`;
    returns `(root, machine_path)`."""
    machine = os.path.join(base, "home", ".claude", "crew", "config.json")
    root = os.path.join(base, "repo")
    os.makedirs(os.path.dirname(machine))
    os.makedirs(os.path.join(root, ".crew"))
    for layer, path in (("machine", machine), ("repo", os.path.join(root, ".crew",
                                                                     "config.json"))):
        data = layers.get(layer)
        if data is not None:
            with open(path, "wb") as handle:
                handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return root, machine


def judge_change(before_layers, after_layers, tracked=crew_humanonly.UNKNOWN, route="writer"):
    """Judge a proposed write. Each argument is `{"machine": bytes|None,
    "repo": bytes|None}` (None: no file). Both sides are read by the same
    readers in two throwaway roots, with an empty receipt store, so nothing
    is ever confirmed here; `tracked` is the real repo file's git state,
    passed so the copy does not read as untracked. `route` is `writer` (a
    crew writer) or `edit` (a direct Write/Edit payload)."""
    scratch = tempfile.mkdtemp(prefix="crew-protected-")
    try:
        snaps = []
        for side, layers in (("before", before_layers), ("after", after_layers)):
            root, machine = _materialise(os.path.join(scratch, side), layers)
            snaps.append(effective_protected(root, global_path=machine,
                                             tracker=lambda _path: tracked))
        return _judge(snaps[0], snaps[1], route)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --- the baseline and judge_drift --------------------------------------------------------

def baseline_path(global_path=None):
    machine = global_path or crew_state.GLOBAL_CONFIG_PATH
    return os.path.join(os.path.dirname(os.path.abspath(machine)), "protected-policy",
                        BASELINE_NAME)


def repo_key(root):
    import crew_ticket  # pylint: disable=import-outside-toplevel
    return crew_humanonly.target_key(crew_ticket.toplevel(root) or os.path.abspath(root))


def read_baseline(path):
    """`(store, problem)`. A missing file is `({"repos": {}}, "")`; anything
    that cannot be read whole, or whose entry digests do not match, is a
    problem (unknown), never empty."""
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"),
                              object_pairs_hook=crew_gitallow.strict_pairs)
    except FileNotFoundError:
        if os.path.lexists(path):
            return None, f"{path} is a link that does not resolve"
        return {"repos": {}}, ""
    except (OSError, ValueError) as exc:
        return None, f"{path} cannot be read ({type(exc).__name__})"
    if not isinstance(data, dict) or not isinstance(data.get("repos"), dict):
        return None, f"{path} is not a baseline store"
    for key, entry in data["repos"].items():
        if not isinstance(entry, dict) or entry.get("sha256") != _digest_entry(entry):
            return None, f"{path}: the entry for {key} does not match its digest"
    return data, ""


def _digest_entry(entry):
    body = {k: entry.get(k) for k in ("policy", "raw", "unrowed", "targets")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def _snapshot_of(entry):
    return {k: copy.deepcopy(entry[k]) for k in ("policy", "raw", "unrowed", "targets")}


def _write_baseline(path, store):
    """The whole store to a sibling temp file, then `os.replace`."""
    text = json.dumps(store, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _entry(snapshot, now=None):
    entry = {"policy": _jsonable(snapshot["policy"]), "raw": _jsonable(snapshot["raw"]),
             "unrowed": _jsonable(snapshot["unrowed"]), "targets": dict(snapshot["targets"]),
             "time": time.time() if now is None else now}
    entry["sha256"] = _digest_entry(entry)
    return entry


def _has_unknown(snapshot):
    values = list(snapshot["policy"].values())
    for layers in snapshot["raw"].values():
        values.extend(layers.values())
    return [v for v in values if isinstance(v, Unknown)]


def judge_drift(root, global_path=None, store=None, tracker=None, path=None, advance=False):
    """The current effective protected policy on the real paths against the
    last confirmed baseline. With `advance`, the baseline moves to the
    current state only when the result is `free`."""
    path = path or baseline_path(global_path)
    data, problem = read_baseline(path)
    if problem:
        now = effective_protected(root, global_path, store, tracker)
        return {"route": "drift", "status": UNKNOWN, "leaves": [], "changed": [],
                "reason": f"the baseline store cannot be read: {problem}", "current": now}
    key = repo_key(root)
    entry = data["repos"].get(key)
    if entry is None:
        now = effective_protected(root, global_path, store, tracker)
        return {"route": "drift", "status": NO_BASELINE, "leaves": [], "changed": [],
                "reason": "no baseline for this repo yet (could not tell); run "
                          "`crew_protected.py baseline --init`", "current": now}
    before = _snapshot_of(entry)
    before["policy"] = {k: _revive(v) for k, v in before["policy"].items()}
    now = effective_protected(root, global_path, store, tracker, targets=before["targets"])
    result = _judge(before, now, "drift")
    result["advanced"] = False
    if advance and result["status"] == FREE and not _has_unknown(now):
        data["repos"][key] = _entry(now)
        _write_baseline(path, data)
        result["advanced"] = True
    return result


def _revive(value):
    if isinstance(value, dict) and set(value) == {"unknown"}:
        return Unknown(value["unknown"])
    return value


def init_baseline(root, global_path=None, store=None, tracker=None, path=None):
    """`(written, why)`. Writes the first baseline for this repo, or moves an
    existing one only when the change is free. Refused while any leaf is
    unknown or the store cannot be read."""
    path = path or baseline_path(global_path)
    data, problem = read_baseline(path)
    if problem:
        return False, f"refused: the baseline store cannot be read ({problem})"
    key = repo_key(root)
    if key in data["repos"]:
        result = judge_drift(root, global_path, store, tracker, path, advance=True)
        if result["advanced"]:
            return True, "the change since the baseline is free; baseline moved"
        return False, "refused: the current state is not a pure narrowing of the baseline"
    now = effective_protected(root, global_path, store, tracker)
    unknown = _has_unknown(now)
    if unknown:
        return False, "refused: " + "; ".join(v.why for v in unknown[:3])
    data["repos"][key] = _entry(now)
    _write_baseline(path, data)
    return True, f"baseline written to {path}"


# --- the CLI ---------------------------------------------------------------------------------

def _lines(result):
    out = [f"status: {result['status']} ({classify(result)})"]
    if result.get("reason"):
        out.append(f"  {result['reason']}")
    for row in result.get("changed", []):
        if row["outcome"] in (WIDENING, UNKNOWN):
            out.append(f"  would refuse {row['leaf']} ({row['reason'] or row['outcome']})")
        else:
            out.append(f"  {row['leaf']}: {row['change']} ({row['outcome']})")
    return out


def _main(argv):
    args = list(argv)
    opts = {"--root": os.getcwd(), "--global-path": None}
    words = []
    while args:
        word = args.pop(0)
        if word in opts and args:
            opts[word] = args.pop(0)
        else:
            words.append(word)
    root, gpath = opts["--root"], opts["--global-path"]
    if words == ["keys"]:
        for leaf in LEAVES:
            name = row_name(leaf)
            print(f"{leaf}\t{DIRECTIONS[name][0]}\t{READERS[name][0]} ({READERS[name][1]})")
        return 0
    if words == ["check"]:
        result = judge_drift(root, gpath, advance=True)
        print("\n".join(_lines(result)))
        return 0 if result["status"] == FREE else 1
    if words == ["explain"]:
        snap = effective_protected(root, gpath)
        for leaf in LEAVES:
            print(f"{leaf} = {json.dumps(_jsonable(snap['policy'][leaf]))}"
                  f"  [{READERS[row_name(leaf)][0]}]")
        return 0
    if words == ["baseline", "--init"]:
        written, why = init_baseline(root, gpath)
        print(why)
        return 0 if written else 1
    print("usage: crew_protected.py check|explain|keys|baseline --init "
          "[--root R] [--global-path P]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
