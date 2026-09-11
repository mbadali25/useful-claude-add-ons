"""routine.py - manifest parsing, the authorization gate, and orchestration
for the multi-tool scan routine (plan Tasks 14-15).

This module is what every one of the nine scanner adapters (`scripts/scanners/`)
was built to feed, so it is the single place that must honour the adapter
contract exactly as pinned by spec section 13.14 and the plan's Global
Constraints:

- `run(location, outdir, opts) -> (raw_path | None, base.ToolResult)` and
  `parse(raw_path, name) -> list[dict]` are always called with plain STRINGS,
  never a `Target` - `run()` gets the target's location (url/path/host),
  `parse()` gets the manifest `name` that is stamped onto every finding's
  `target` field (half of `dedupe()`'s key, spec 13.1). Passing a `Target`
  object into either would leave a Python repr sitting in that field.
- `result.returncode is None` means the adapter declined an active scan
  before firing anything (currently only sqlmap) - that is `skipped-active`,
  never `error`.
- `ACTIVE_OPTS` is read defensively (`getattr(mod, "ACTIVE_OPTS", [])`), never
  assumed present, so a future adapter that only implements the base four
  constants can't take the whole run down with an AttributeError.
- `parse_errors()` is optional (testssl uses it for WARN/FATAL, which are scan
  errors, never findings) and is folded into that cell's run-manifest entry,
  not lost.
- `sqlmap` and `depcheck` hand back directories, not files; `trivy` serves
  both `deps` and `iac` off one adapter and needs `kind` threaded through
  explicitly since a plain string `target` carries no `.kind` of its own.

No package structure exists under `scripts/` (plan 13.10) - this module relies
on pytest.ini's `pythonpath = scripts` / gizmoduck.py's own sys.path-heading
convention for `import scanners` and `import normalize` to resolve, exactly
like every adapter already does.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import scanners as default_registry


class AuthorizationError(Exception):
    """Raised when a manifest lacks a mandatory, non-empty `authorized_by`.

    Spec section 8: "manifest authorized_by is mandatory; routine aborts
    without it." An absent key and a present-but-blank one are refused the
    same way - a whitespace-only string is not an authorization statement.
    """


@dataclass
class Target:
    """One manifest entry. `options` is the per-target toggle dict spec
    section 5 describes (`zap_active`, `nmap_vuln`, `sqlmap`, ad hoc timeouts,
    ...); `tools`, when set, replaces the kind's default adapter list outright
    rather than adding to it.
    """
    name: str
    kind: str
    url: str = None
    path: str = None
    host: str = None
    tools: list = None
    options: dict = field(default_factory=dict)


@dataclass
class Manifest:
    authorized_by: str
    targets: list


def load_manifest(path, registry=None):
    """Parse and validate a targets manifest (spec section 5).

    Validates two things that must never silently degrade into "ran zero
    tools and reported a clean target": a missing/blank `authorized_by`
    (routine must never run undirected), and an unrecognized `kind` (an
    empty adapter list is indistinguishable from a clean scan - so an
    unknown kind raises instead of resolving to nothing).
    """
    reg = registry if registry is not None else default_registry

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    authorized_by = (data.get("authorized_by") or "").strip()
    if not authorized_by:
        raise AuthorizationError(
            "manifest is missing a non-empty 'authorized_by'; routine "
            "refuses to run without an explicit authorization statement "
            "(spec section 8)")

    targets = []
    for raw in data.get("targets") or []:
        kind = raw.get("kind")
        if kind not in reg.KIND_DEFAULTS:
            raise ValueError(
                "unknown target kind %r for target %r; known kinds: %s"
                % (kind, raw.get("name"), ", ".join(sorted(reg.KIND_DEFAULTS))))
        targets.append(Target(
            name=raw.get("name"),
            kind=kind,
            url=raw.get("url"),
            path=raw.get("path"),
            host=raw.get("host"),
            tools=list(raw["tools"]) if raw.get("tools") else None,
            options=dict(raw.get("options") or {}),
        ))

    return Manifest(authorized_by=authorized_by, targets=targets)


def resolve_adapters(target, registry=None):
    """kind default, then `tools` override, then `options` gates for tools
    that are active-only-when-opted-in (spec section 5 / plan Task 14).

    An explicit `target.tools` list replaces the kind default outright - spec
    section 5's "tools may override the default set". Absent that override,
    the kind default is extended with any adapter that (a) also declares this
    kind in its own `KINDS`, (b) is `DEFAULT_ENABLED = False` and fully
    `ACTIVE` (today, only sqlmap), and (c) is switched on for this specific
    target via `options[<tool name>]`. That is deliberately a *different*
    knob from `ACTIVE_OPTS` (`nmap_vuln`, `zap_active`): those two adapters
    are already in the kind default and always run in some mode, ACTIVE_OPTS
    only chooses which mode; sqlmap isn't in any kind default at all and
    needs a toggle to appear in the list in the first place.
    """
    reg = registry if registry is not None else default_registry

    if target.tools:
        return list(target.tools)

    adapters = list(reg.KIND_DEFAULTS[target.kind])
    for name, mod in reg.ADAPTERS.items():
        if name in adapters:
            continue
        if target.kind not in getattr(mod, "KINDS", []):
            continue
        if getattr(mod, "DEFAULT_ENABLED", True):
            continue
        if not getattr(mod, "ACTIVE", False):
            continue
        if target.options.get(name):
            adapters.append(name)
    return adapters


# ---------------------------------------------------------------------------
# Orchestration (Task 15)
# ---------------------------------------------------------------------------

# Mode vocabulary for the two adapters that are active only in one of their
# two modes (plan Global Constraints). A bare "ran" for either would imply
# coverage a safe/baseline-only scan never attempted.
_MODE_LABELS = {
    "nmap": {"base": "safe", "nmap_vuln": "vuln"},
    "zap": {"base": "baseline", "zap_active": "active"},
}


def _adapter(registry, name):
    getter = getattr(registry, "get", None)
    if callable(getter):
        return getter(name)
    return registry.ADAPTERS[name]


def _location(target):
    """The string `run()` receives - the target's *location*, never its
    manifest name and never the Target object itself (see module docstring).
    """
    if target.kind in ("iac", "deps"):
        if not target.path:
            raise ValueError(
                "target %r (kind=%s) has no 'path'" % (target.name, target.kind))
        return target.path
    if target.kind == "host":
        if not target.host:
            raise ValueError(
                "target %r (kind=host) has no 'host'" % target.name)
        return target.host
    if target.kind == "web":
        if not target.url:
            raise ValueError(
                "target %r (kind=web) has no 'url'" % target.name)
        return target.url
    raise ValueError("no location resolver for kind %r" % target.kind)


def _ran_status(name, mod, target):
    active_opts = getattr(mod, "ACTIVE_OPTS", [])
    if not active_opts:
        return "ran"

    labels = _MODE_LABELS.get(name)
    if labels:
        extras = [labels[k] for k in active_opts
                  if k in labels and target.options.get(k)]
        base = labels["base"]
    else:
        # An adapter with ACTIVE_OPTS but no entry in _MODE_LABELS yet -
        # still record *something* rather than a bare "ran", using the raw
        # option keys as the mode vocabulary.
        extras = [k for k in active_opts if target.options.get(k)]
        base = "default"

    if extras:
        return "ran(%s+%s)" % (base, "+".join(extras))
    return "ran(%s)" % base


class RunManifest:
    """Per-(target, tool) status/duration/count/errors, plus the
    authorization statement the report header restates (spec section 8).
    """

    def __init__(self, authorized_by):
        self.authorized_by = authorized_by
        self._cells = {}

    def record(self, target, tool, status, duration=0.0, count=0, errors=None):
        self._cells[(target, tool)] = {
            "status": status,
            "duration": round(duration, 3),
            "count": count,
            "errors": errors or [],
        }

    def status(self, target, tool):
        cell = self._cells.get((target, tool))
        return cell["status"] if cell else None

    def cell(self, target, tool):
        return self._cells.get((target, tool))

    def to_dict(self):
        return {
            "authorized_by": self.authorized_by,
            "cells": [
                dict(target=t, tool=tool, **data)
                for (t, tool), data in sorted(self._cells.items())
            ],
        }

    def write(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)


def run_routine(manifest, outdir, registry=None, confirm=None):
    """Run every resolved adapter for every manifest target (spec section 6).

    Writes native per-tool outputs under `<outdir>/<target-name>/`, one
    combined `<outdir>/findings.jsonl`, and `<outdir>/run-manifest.json`.
    Returns the `RunManifest` so callers (and tests) can inspect per-cell
    status without re-reading it back off disk.

    `registry` exists so tests inject fake adapters - no real scanner is ever
    invoked from this module's own test suite. `confirm` is the explicit
    approval token spec section 8 requires before sqlmap fires; it is
    threaded into `opts["confirm"]` for every adapter (harmless for the other
    eight, which never look at that key) rather than special-cased into the
    call, so a future second ACTIVE=True adapter needs no change here.

    One tool failing (a raised exception, a timeout, a missing binary) never
    aborts the target or the run: every adapter invocation is individually
    guarded, and a bad cell is recorded and skipped over.
    """
    reg = registry if registry is not None else default_registry
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rm = RunManifest(authorized_by=manifest.authorized_by)
    all_findings = []

    for target in manifest.targets:
        adapter_names = resolve_adapters(target, reg)
        target_outdir = outdir / target.name
        location = _location(target)

        for name in adapter_names:
            start = time.monotonic()
            try:
                mod = _adapter(reg, name)

                if not mod.is_available():
                    rm.record(target.name, name, "skipped-missing",
                              duration=time.monotonic() - start)
                    continue

                opts = dict(target.options)
                opts["confirm"] = bool(confirm)
                if name == "trivy":
                    opts["kind"] = target.kind

                raw_path, result = mod.run(location, str(target_outdir), opts)

                if result.returncode is None:
                    # An active tool declined before firing anything (only
                    # sqlmap today) - never an error (plan Tasks 5-13 /
                    # spec 13.14).
                    rm.record(target.name, name, "skipped-active",
                              duration=time.monotonic() - start)
                    continue

                if result.timed_out:
                    rm.record(target.name, name, "error:timeout",
                              duration=time.monotonic() - start)
                    continue

                if raw_path is None:
                    rm.record(target.name, name,
                              "error:returncode=%s" % result.returncode,
                              duration=time.monotonic() - start)
                    continue

                if name == "trivy":
                    findings = mod.parse(raw_path, target.name, kind=target.kind)
                else:
                    findings = mod.parse(raw_path, target.name)

                parse_errors = getattr(mod, "parse_errors", lambda *_a: [])(
                    raw_path, target.name)

                for f in findings:
                    # Defensive, not corrective: every adapter's parse()
                    # already sets these via normalize.make_finding, but the
                    # combined file is the single source the report and
                    # tickets consume (spec section 6), so it must be
                    # right even if one adapter ever drifts.
                    f["tool"] = name
                    f["target"] = target.name
                all_findings.extend(findings)

                rm.record(target.name, name, _ran_status(name, mod, target),
                          duration=time.monotonic() - start,
                          count=len(findings), errors=parse_errors)
            except Exception as exc:
                rm.record(target.name, name, "error:%s" % exc,
                          duration=time.monotonic() - start)
                continue

    with open(outdir / "findings.jsonl", "w", encoding="utf-8") as fh:
        for f in all_findings:
            fh.write(json.dumps(f) + "\n")

    rm.write(outdir / "run-manifest.json")
    return rm
