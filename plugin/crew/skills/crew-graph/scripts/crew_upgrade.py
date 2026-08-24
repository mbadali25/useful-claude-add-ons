"""Upgrades a v1 crew setup (no `schema` key) to v2.

Order matters and is not negotiable: back up, then upgrade config, then
reconcile, then report. The backup exists so that every later step can be
non-destructive in practice as well as in intent.

Two rules this module exists to enforce:

  * A codemap `anchor:` is bumped only on a file this run actually re-verified.
    A false freshness claim is worse than an honest stale one, because the
    entire freshness rule depends on the anchor being true.
  * A conflict between the map and the graph is written to the report, never
    applied to the map.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import graph_reconcile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, os.pardir, "hooks", "scripts",
))
import crew_state  # pylint: disable=wrong-import-position

# Not a second copy of the PM defaults. crew_state owns them because the hook
# reads config on every session start; if an upgrade wrote defaults the hook
# disagreed with, a freshly upgraded repo would behave differently from a
# freshly created one and nothing would say so.
PM_BLOCK = crew_state.PM_DEFAULTS

GRAPH_BLOCK = {
    "enabled": True,
    "tool": "graphify",
    # crew_state owns this default too -- it has to resolve the same directory
    # when no config exists at all.
    "out": crew_state.GRAPH_OUT_DEFAULT,
    "mode": "code-only",
    "commitHook": False,
    "obsidian": {"enabled": False, "dir": None, "confirmed": False},
}

_ANCHOR_LINE_RE = re.compile(r"^(anchor:\s*\S*@?)([0-9a-f]{7,40})",
                             re.MULTILINE | re.IGNORECASE)


def _merged(defaults, supplied):
    """defaults, overlaid with anything already present. Recurses one level."""
    out = dict(defaults)
    if not isinstance(supplied, dict):
        return out
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merged(out[key], value)
        else:
            out[key] = value
    return out


def upgrade_config(cfg):
    """v1 config -> v2. Pure. Preserves every key it does not know about."""
    out = dict(cfg)
    out["pm"] = _merged(PM_BLOCK, cfg.get("pm"))
    out["graph"] = _merged(GRAPH_BLOCK, cfg.get("graph"))
    # obsidian.confirmed is a consent flag, not a setting. An upgrade must
    # never grant it -- only the user, in session, can.
    out["graph"]["obsidian"]["confirmed"] = (
        crew_state.dict_or_empty(
            crew_state.dict_or_empty(cfg.get("graph")).get("obsidian")
        ).get("confirmed") is True
    )
    out["schema"] = crew_state.SCHEMA_CURRENT
    return out


def backup_codemap(root):
    """Copy .crew/codemap/ aside. Returns the path, or None if there is none."""
    src = os.path.join(root, ".crew", "codemap")
    if not os.path.isdir(src):
        return None
    dst = os.path.join(root, ".crew", "codemap.v1.bak")
    if os.path.exists(dst):
        return dst          # a previous run already took one; do not overwrite
    shutil.copytree(src, dst)
    return dst


def _head(root):
    try:
        done = subprocess.run(
            ("git", "rev-parse", "--short=7", "HEAD"), cwd=root,
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _bump_anchor(text, head):
    if not head:
        return text
    return _ANCHOR_LINE_RE.sub(lambda m: m.group(1) + head, text, count=1)


def _report(status, head, results):
    lines = [
        "# Upgrade report",
        f"from schema: 1 -> {crew_state.SCHEMA_CURRENT}",
        f"graph anchor: {head or 'unknown'}",
        "",
        "Nothing below was applied automatically. Conflicts are the map and",
        "the graph disagreeing, and either can be wrong: the graph misses",
        "generated call sites, reflection, and dynamic dispatch.",
        "",
    ]
    conflicts = [c for r in results.values() for c in r["conflicts"]]
    lines.append("## Contradictions — kept in the map, verify by hand")
    lines.extend(f"- {c}" for c in conflicts or ["- none"])
    lines.append("")
    lines.append("## Added by the graph")
    added = [f"- {name}: {len(r['added'])} new line(s)"
             for name, r in sorted(results.items()) if r["added"]]
    lines.extend(added or ["- none"])
    lines.append("")
    lines.append("## Anchors left stale on purpose")
    stale = [f"- {name} — not re-verified this run"
             for name, r in sorted(results.items()) if not r["touched"]]
    lines.extend(stale or ["- none"])
    lines.append("")
    return "\n".join(lines) + "\n"


def run(root, derived, force=False):
    """Upgrade the repo at `root`. `derived` maps subsystem -> graph sections."""
    cfg_path = os.path.join(root, ".crew", "config.json")
    if not os.path.exists(cfg_path):
        return {"status": "not a crew repo", "report": "", "conflicts": []}

    cfg = crew_state.load_config(root)
    if cfg.get("schema", 1) >= crew_state.SCHEMA_CURRENT and not force:
        return {"status": "already current", "report": "", "conflicts": []}

    backup_codemap(root)

    with open(cfg_path, "w", encoding="utf-8") as handle:
        json.dump(upgrade_config(cfg), handle, indent=2, sort_keys=True)
        handle.write("\n")

    head = _head(root)
    mapdir = os.path.join(root, ".crew", "codemap")
    results = {}
    for name, sections in (derived or {}).items():
        path = os.path.join(mapdir, f"{name}.md")
        text = crew_state.read_text(path)
        if text is None:
            continue
        out = graph_reconcile.reconcile(text, sections)
        body = _bump_anchor(out["body"], head) if out["touched"] else out["body"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        results[name] = out

    report = _report("upgraded", head, results)
    if os.path.isdir(mapdir):
        with open(os.path.join(mapdir, "UPGRADE.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(report)

    return {
        "status": "upgraded",
        "report": report,
        "conflicts": [c for r in results.values() for c in r["conflicts"]],
    }


def main(argv=None):
    """CLI entry point. `derived` arrives as a JSON file written by the skill."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--derived", help="path to a JSON file of graph facts")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    derived = {}
    if args.derived:
        text = crew_state.read_text(args.derived)
        if text:
            try:
                derived = json.loads(text)
            except ValueError:
                derived = {}

    out = run(args.root, derived, force=args.force)
    print(out["status"])
    if out["conflicts"]:
        print(f"{len(out['conflicts'])} conflict(s) - see .crew/codemap/UPGRADE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
