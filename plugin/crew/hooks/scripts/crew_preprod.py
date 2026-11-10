"""`environments.preProduction`: an environment LABELLED production that is not
production yet, declared in the REPO layer with a written reason.

The owner's need: while a new environment is built, its name or its hosts
already say `prod`, and the production rules fire on work that touches nothing
live. The answer is not a switch. It is a short list of exact names, each with
a reason, that the production rules read as non-production -- and nothing else.

    "environments": {"preProduction": {
        "acme-new": {"reason": "stood up 2026-11, no customer traffic yet",
                     "targets": ["acme-new-prod-db", "acme-new-prod-web1"]}}}

What a listed name does, and only this:

  * terraform apply and `gh` workflow dispatches aimed at the environment
    `acme-new` are classified `nonProd` by `cloud_guard.evaluate` (a
    non-destroying one runs unattended under `ask`, and is logged);
  * a SQL client or ssh aimed at `acme-new`, or at one of its exact `targets`,
    is not refused by `guards.prodDatabase` / `guards.prodServer` -- but only
    when EVERY declared production target on the command line is covered.

What it never does: relax a destroy (still asks), `block` policies,
`cloudDestructive`, `sqlDestructive`, `forcePush`, the identity pins, the
promote gate, autopilot's deploy ladder or `crew_unattended`. An environment
not listed is judged exactly as before. Names and targets are EXACT: a
wildcard is a malformed entry, so a listing can never reach an environment
nobody named.

Every use is reported as a line on stderr and on screen, and written to
`.crew/guard.log` under the policy `env:preProduction:<name>`, so the
exemption is never silent and `grep preProduction .crew/guard.log` lists it.

REPO LAYER ONLY (the machine file is pruned of `environments.preProduction` by
`crew_config.filter_global`, as it is of `environments.nonProd`): which
environment is not live yet is a fact about one checkout, and a cloned repo
cannot ship the exemption into another person's machine through their own
global file. A malformed entry is never "nothing listed": the whole
`environments` block reads as unreadable (`crew_config.environments_block_
problem`), which classifies every environment unknown -- narrower, never
wider.
"""

import fnmatch
import re

# Characters that make a name a pattern. An exemption is by exact name.
_PATTERN_CHARS = re.compile(r"[*?\[\]\s]")
MIN_REASON = 10
POLICY_PREFIX = "env:preProduction:"


def _bad_name(name):
    return not isinstance(name, str) or not name.strip() \
        or bool(_PATTERN_CHARS.search(name))


def problem(block):
    """Why a PRESENT `environments.preProduction` value cannot be read, or
    `""`. `block` is the value itself (not the `environments` object)."""
    if not isinstance(block, dict):
        return "`environments.preProduction` is not an object"
    for name, entry in block.items():
        if _bad_name(name):
            return (f"`environments.preProduction` key {name!r} is not an "
                    "exact name (no wildcard, no whitespace)")
        if not isinstance(entry, dict) or set(entry) - {"reason", "targets"}:
            return (f"`environments.preProduction[{name!r}]` is not an object "
                    "with `reason` and optional `targets`")
        reason = entry.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
            return (f"`environments.preProduction[{name!r}].reason` must be "
                    f"a sentence of at least {MIN_REASON} characters saying "
                    "why this environment is not live yet")
        targets = entry.get("targets", [])
        if not isinstance(targets, list) or any(
                _bad_name(t) for t in targets):
            return (f"`environments.preProduction[{name!r}].targets` is not "
                    "a list of exact host or database names")
    return ""


def entries(block):
    """`{lowercase name: {"name", "reason", "targets"}}` for a block that
    `problem` accepted; `{}` for anything else, so a caller that skipped
    the check still gets "nothing listed" from a block it cannot read -- and
    `cloud_guard.environments_config` has already made the malformed case
    unknown, the narrower value."""
    if not isinstance(block, dict) or problem(block):
        return {}
    return {name.strip().lower(): {
        "name": name.strip(), "reason": entry["reason"].strip(),
        "targets": frozenset(t.strip().lower()
                             for t in entry.get("targets", []))}
            for name, entry in block.items()}


def owner_of(target, table):
    """The listed entry that names `target` exactly (its own name, or one of
    its `targets`), or None."""
    key = str(target).strip().lower()
    for lowered, entry in table.items():
        if key == lowered or key in entry["targets"]:
            return entry
    return None


def covers(matched, table):
    """`(names, reasons)` when EVERY production target in `matched` belongs to
    a listed entry, else None. `matched` empty is None: nothing to exempt."""
    if not matched or not table:
        return None
    owners = []
    for target in matched:
        entry = owner_of(target, table)
        if entry is None:
            return None
        owners.append(entry)
    names = sorted({e["name"] for e in owners})
    return names, sorted({e["reason"] for e in owners})


def matched_targets(targets, patterns):
    """Every extracted target that some declared production pattern matches
    (all of them, not the first: one unlisted match refuses the command)."""
    out = []
    for target in targets:
        for pattern in patterns or ():
            if isinstance(pattern, str) and pattern.strip() and \
                    fnmatch.fnmatch(target.lower(), pattern.strip().lower()):
                out.append(target)
                break
    return out


def audit_line(guard_or_what, names, reasons, detail=""):
    """The one line every use writes to stderr and shows on screen."""
    tail = f" ({detail})" if detail else ""
    return (f"crew PRE-PRODUCTION EXEMPTION: {guard_or_what} treated "
            f"{', '.join(names)} as NOT production because "
            f"environments.preProduction lists it -- "
            f"{'; '.join(reasons)}{tail}. Remove the entry when it goes live.")


def arm(envs):
    """`envs` (from `cloud_guard.environments_config`) with every listed name
    ALSO in `nonProd`, so terraform and dispatch classify it nonProd through
    the one code path that already exists. The list as declared is kept as
    `declaredNonProd`: `retag` only claims the names the glob list did not
    already cover."""
    table = envs.get("preProduction") or {}
    if table:
        envs["declaredNonProd"] = list(envs.get("nonProd", []))
        envs["nonProd"] = envs["declaredNonProd"] + [
            e["name"] for e in table.values()]  # exact: `problem` bars [*?[] and spaces
    return envs


def retag(policy, reason, decision, envs, what):
    """`(policy, reason)` for one finding's verdict. A non-destroying run that
    was allowed because its environment is nonProd, where the only reason it
    is nonProd is a `preProduction` entry, is relabelled
    `env:preProduction:<name>` and its reason becomes the audit line. Anything
    else comes back untouched."""
    table = envs.get("preProduction") or {}
    if decision != "allow" or not table or not policy.startswith("env:nonProd:"):
        return policy, reason
    value = policy.split(":", 2)[2]
    entry = table.get(value.strip().lower())
    declared = envs.get("declaredNonProd", [])
    if entry is None or any(fnmatch.fnmatch(value.lower(), g.lower())
                            for g in declared):
        return policy, reason
    return POLICY_PREFIX + entry["name"], audit_line(
        f"`{what}`", [entry["name"]], [entry["reason"]],
        "a non-destroying run, allowed unattended as nonProd")
