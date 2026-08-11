#!/usr/bin/env python3
"""Audit a Claude Code installation for performance and context-budget problems.

Stdlib only, read-only. This script never deletes, disables, moves, or rewrites
anything - it reports. Every finding carries the exact command that would fix it,
for a human to run after reading it.

Usage:
  python cc_audit.py                    # ranked findings for the user scope + cwd
  python cc_audit.py --project DIR      # audit DIR's .claude/ instead of cwd
  python cc_audit.py --json             # machine-readable, same findings
  python cc_audit.py --min-severity med # drop the LOW noise

Exit code is always 0 - findings are not failures.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Rough bytes-per-token for English markdown. Good enough for budgeting; the point
# is relative cost between sources, not an exact count.
BYTES_PER_TOKEN = 4

SEV_ORDER = {"HIGH": 0, "MED": 1, "LOW": 2, "INFO": 3}


# --- helpers ------------------------------------------------------------------

def read_text(path):
    """Read a file as text, tolerating the cp1252/utf-8 mixups that settings files pick up."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(path):
    """Parse a JSON file, returning ({}, error-string) rather than raising."""
    if not path.is_file():
        return {}, None
    raw = read_text(path)
    if not raw.strip():
        return {}, None
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return {}, f"{path}: {exc}"


def dir_size(path):
    total = 0
    if not path.is_dir():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def human(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.0f}{unit}" if unit == "B" else f"{nbytes:.1f}{unit}"
        nbytes /= 1024.0
    return f"{nbytes:.0f}B"


def est_tokens(nbytes):
    return int(nbytes / BYTES_PER_TOKEN)


FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def skill_frontmatter(skill_md):
    """Return (name, description-bytes) for a SKILL.md without a YAML dependency."""
    raw = read_text(skill_md)
    match = FRONTMATTER.match(raw)
    block = match.group(1) if match else raw[:2000]
    name = ""
    name_match = re.search(r"^name:\s*(\S+)", block, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip("'\"")
    desc_match = re.search(r"^description:\s*(.*?)(?=^\w[\w-]*:|\Z)", block, re.DOTALL | re.MULTILINE)
    desc = desc_match.group(1) if desc_match else ""
    return name or skill_md.parent.name, len(desc.encode("utf-8"))


# --- inventory ----------------------------------------------------------------

class Inventory:
    def __init__(self, project_dir):
        self.config_root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
        self.project_dir = Path(project_dir).resolve()
        self.errors = []

        self.settings, err = read_json(self.config_root / "settings.json")
        if err:
            self.errors.append(err)
        self.settings_local, err = read_json(self.config_root / "settings.local.json")
        if err:
            self.errors.append(err)
        self.project_settings, err = read_json(self.project_dir / ".claude" / "settings.json")
        if err:
            self.errors.append(err)
        self.project_settings_local, err = read_json(self.project_dir / ".claude" / "settings.local.json")
        if err:
            self.errors.append(err)

        self.all_settings = [
            ("user settings.json", self.settings),
            ("user settings.local.json", self.settings_local),
            ("project settings.json", self.project_settings),
            ("project settings.local.json", self.project_settings_local),
        ]

        self.enabled_plugins = {}
        self.marketplaces = {}
        for _label, blob in self.all_settings:
            self.enabled_plugins.update(blob.get("enabledPlugins") or {})
            self.marketplaces.update(blob.get("extraKnownMarketplaces") or {})

        self.user_skills = self._user_skills()
        self.plugin_skills = self._plugin_skills()
        self.agents = self._agents()
        self.rules = sorted((self.config_root / "rules").glob("*.md"))
        self.memory_files = self._memory_files()
        self.mcp_servers = self._mcp_servers()
        self.hooks = self._hooks()

    def is_enabled(self, spec):
        """enabledPlugins is keyed 'plugin@marketplace'; absent means enabled by default."""
        return self.enabled_plugins.get(spec, True) is not False

    def _user_skills(self):
        out = {}
        for skill_md in sorted((self.config_root / "skills").glob("*/SKILL.md")):
            name, desc_bytes = skill_frontmatter(skill_md)
            out[skill_md.parent.name] = {
                "name": name,
                "path": str(skill_md.parent),
                "desc_bytes": desc_bytes,
                "bytes": dir_size(skill_md.parent),
            }
        return out

    def _plugin_skills(self):
        """Map skill dir name -> list of plugins providing it.

        Two layouts both occur in the cache: a plugin that bundles several skills keeps
        them under skills/<name>/SKILL.md, and a plugin that *is* one skill puts SKILL.md
        at its root (this repo's marketplace does that). Only the newest cached version of
        each plugin counts - older version dirs are stale cache, not a second copy in
        context.
        """
        out = {}
        for plugin_dir in self._newest_plugin_versions():
            spec = plugin_spec(plugin_dir)
            for skill_md in sorted(plugin_dir.glob("skills/*/SKILL.md")):
                name, desc_bytes = skill_frontmatter(skill_md)
                out.setdefault(skill_md.parent.name, []).append({
                    "plugin": spec,
                    "name": name,
                    "desc_bytes": desc_bytes,
                    "path": str(skill_md.parent),
                })
            root_skill = plugin_dir / "SKILL.md"
            if root_skill.is_file():
                name, desc_bytes = skill_frontmatter(root_skill)
                out.setdefault(plugin_dir.parent.name, []).append({
                    "plugin": spec,
                    "name": name,
                    "desc_bytes": desc_bytes,
                    "path": str(plugin_dir),
                })
        return out

    def _newest_plugin_versions(self):
        """The highest-numbered version dir per cached plugin, skipping orphans."""
        newest = []
        cache = self.config_root / "plugins" / "cache"
        if not cache.is_dir():
            return newest
        for owner in sorted(p for p in cache.iterdir() if p.is_dir()):
            for plugin in sorted(p for p in owner.iterdir() if p.is_dir()):
                versions = [v for v in plugin.iterdir()
                            if v.is_dir() and not (v / ".orphaned_at").exists()]
                if not versions:
                    continue
                versions.sort(key=lambda v: _version_key(v.name))
                newest.append(versions[-1])
        return newest

    def plugin_cache_versions(self):
        """plugin path -> list of cached version dir names (to spot stale copies)."""
        out = {}
        cache = self.config_root / "plugins" / "cache"
        if not cache.is_dir():
            return out
        for owner in sorted(p for p in cache.iterdir() if p.is_dir()):
            for plugin in sorted(p for p in owner.iterdir() if p.is_dir()):
                versions = sorted((v.name for v in plugin.iterdir() if v.is_dir()),
                                  key=_version_key)
                if versions:
                    out[f"{owner.name}/{plugin.name}"] = versions
        return out

    def _agents(self):
        out = {}
        for src in (self.config_root / "agents", self.project_dir / ".claude" / "agents"):
            for agent_md in sorted(src.glob("*.md")) if src.is_dir() else []:
                out[agent_md.stem] = {"path": str(agent_md), "bytes": agent_md.stat().st_size}
        for plugin_dir in self._newest_plugin_versions():
            for agent_md in sorted(plugin_dir.glob("agents/*.md")):
                out.setdefault(agent_md.stem, {"path": str(agent_md),
                                               "bytes": agent_md.stat().st_size})
        return out

    def _memory_files(self):
        """Every CLAUDE.md / rules file that loads into context at session start."""
        out = []
        for path in (self.config_root / "CLAUDE.md",
                     self.project_dir / "CLAUDE.md",
                     self.project_dir / ".claude" / "CLAUDE.md",
                     self.config_root / "RTK.md"):
            if path.is_file():
                out.append({"path": str(path), "bytes": path.stat().st_size,
                            "lines": read_text(path).count("\n") + 1})
        for path in self.rules:
            body = read_text(path)
            out.append({"path": str(path), "bytes": path.stat().st_size,
                        "lines": body.count("\n") + 1,
                        "scoped": bool(re.search(r"^paths:", body, re.MULTILINE))})
        return out

    def _mcp_servers(self):
        out = {}
        for label, blob in self.all_settings:
            for name in (blob.get("mcpServers") or {}):
                out.setdefault(name, label)
        project_mcp, err = read_json(self.project_dir / ".mcp.json")
        if err:
            self.errors.append(err)
        for name in (project_mcp.get("mcpServers") or {}):
            out.setdefault(name, ".mcp.json")
        legacy, err = read_json(Path.home() / ".claude.json")
        if err:
            self.errors.append(err)
        for name in (legacy.get("mcpServers") or {}):
            out.setdefault(name, "~/.claude.json")
        for proj_key, proj in (legacy.get("projects") or {}).items():
            if not isinstance(proj, dict):
                continue
            if Path(proj_key).resolve() != self.project_dir:
                continue
            for name in (proj.get("mcpServers") or {}):
                out.setdefault(name, "~/.claude.json (this project)")
        return out

    def _hooks(self):
        """Flatten every configured hook into one list of dicts."""
        out = []
        for label, blob in self.all_settings:
            for event, groups in (blob.get("hooks") or {}).items():
                for group in groups if isinstance(groups, list) else []:
                    matcher = group.get("matcher", "*")
                    for hook in group.get("hooks") or []:
                        out.append({
                            "source": label,
                            "event": event,
                            "matcher": matcher,
                            "command": hook.get("command", ""),
                            "type": hook.get("type", ""),
                            "timeout": hook.get("timeout"),
                        })
        for plugin_dir in self._newest_plugin_versions():
            blob, _err = read_json(plugin_dir / "hooks" / "hooks.json")
            for event, groups in (blob.get("hooks") or {}).items():
                for group in groups if isinstance(groups, list) else []:
                    for hook in group.get("hooks") or []:
                        out.append({
                            "source": f"plugin:{plugin_spec(plugin_dir)}",
                            "event": event,
                            "matcher": group.get("matcher", "*"),
                            "command": hook.get("command", ""),
                            "type": hook.get("type", ""),
                            "timeout": hook.get("timeout"),
                        })
        return out


def _version_key(name):
    parts = re.findall(r"\d+", name)
    return [int(p) for p in parts] or [0]


def plugin_spec(version_dir):
    """'bitbucket@useful-claude-add-ons' from .../cache/<marketplace>/<plugin>/<version>.

    The marketplace has to be in the label: the same plugin name published by two
    marketplaces is exactly the duplicate this audit exists to catch.
    """
    return f"{version_dir.parent.name}@{version_dir.parent.parent.name}"


# --- checks -------------------------------------------------------------------

def finding(sev, title, evidence, fix, cost=None):
    return {"severity": sev, "title": title, "evidence": evidence, "fix": fix, "cost": cost}


def check_duplicate_skills(inv):
    """The single most common context leak: the same skill loaded twice.

    A loose copy that shadows a *disabled* plugin is not a live duplicate, so the
    enabled state decides both the severity and whether deleting is safe.
    """
    out = []
    live, shadowing_disabled = [], []
    for dirname, meta in sorted(inv.user_skills.items()):
        providers = inv.plugin_skills.get(dirname)
        if not providers:
            continue
        if any(inv.is_enabled(p["plugin"]) for p in providers):
            live.append((dirname, meta, providers))
        else:
            shadowing_disabled.append((dirname, meta, providers))

    if live:
        wasted = sum(m["desc_bytes"] for _d, m, _p in live)
        out.append(finding(
            "HIGH",
            f"{len(live)} skills load twice - a loose copy and an enabled plugin",
            [f"{d} - loose copy at {m['path']}, also from "
             f"{', '.join(p['plugin'] for p in ps)}" for d, m, ps in live],
            "The plugin is the copy that updates itself. Delete the loose copies:\n"
            + "\n".join(f"  rm -rf {m['path']}" for _d, m, _p in live),
            f"~{est_tokens(wasted)} tokens of duplicated descriptions in every session",
        ))

    if shadowing_disabled:
        out.append(finding(
            "MED",
            f"{len(shadowing_disabled)} loose skills shadow a plugin you have disabled",
            [f"{d} (loose) vs {', '.join(p['plugin'] for p in ps)} (disabled)"
             for d, _m, ps in shadowing_disabled],
            "Decide which one you want. Keeping the loose copy means it never updates; "
            "enabling the plugin means you should delete the loose copy first.",
        ))

    multi = {}
    for dirname, providers in inv.plugin_skills.items():
        specs = sorted({p["plugin"] for p in providers})
        if len(specs) > 1:
            multi[dirname] = specs
    if multi:
        # HIGH only if some single skill name is served by two *enabled* plugins - that is
        # the case where two descriptions really do both sit in context.
        both_enabled = any(sum(1 for s in specs if inv.is_enabled(s)) > 1
                           for specs in multi.values())
        out.append(finding(
            "HIGH" if both_enabled else "LOW",
            f"{len(multi)} skill names come from more than one plugin",
            [f"{d} <- " + ", ".join(
                s if inv.is_enabled(s) else f"{s} (disabled)" for s in specs)
             for d, specs in sorted(multi.items())][:10],
            "Uninstall the duplicate publisher rather than disabling it, so its marketplace "
            "stops being refreshed:\n  claude plugin uninstall <plugin>@<marketplace>",
        ))
    return out


def check_disabled_plugins(inv):
    disabled = sorted(k for k, v in inv.enabled_plugins.items() if v is False)
    if not disabled:
        return []
    return [finding(
        "MED",
        f"{len(disabled)} plugins are installed but disabled",
        disabled,
        "Uninstall what you are not using - a disabled plugin is still fetched and "
        "refreshed:\n" + "\n".join(f"  claude plugin uninstall {p}" for p in disabled),
    )]


def check_marketplaces(inv):
    count = len(inv.marketplaces)
    if count <= 6:
        return []
    return [finding(
        "MED",
        f"{count} plugin marketplaces are registered",
        sorted(inv.marketplaces),
        "Each one is a git fetch on refresh. Remove the marketplaces whose plugins you "
        "have uninstalled: claude plugin marketplace remove <name>",
        "startup and refresh latency",
    )]


def check_stale_cache(inv):
    versions = inv.plugin_cache_versions()
    stale = {k: v for k, v in versions.items() if len(v) > 1}
    if not stale:
        return []
    cache_bytes = dir_size(inv.config_root / "plugins" / "cache")
    return [finding(
        "LOW",
        f"{len(stale)} plugins have more than one version in the cache",
        [f"{k}: {', '.join(v)}" for k, v in sorted(stale.items())],
        "Claude Code prunes these itself; delete the older version dirs by hand only if "
        "disk matters.",
        f"plugins/cache is {human(cache_bytes)}",
    )]


def check_hooks(inv):
    out = []
    per_event = {}
    for hook in inv.hooks:
        per_event.setdefault(hook["event"], []).append(hook)

    # A hook whose script is gone still spawns a process on every matching tool call.
    broken = []
    for hook in inv.hooks:
        for path in re.findall(r'"([A-Za-z]:[/\\][^"]+?|/[^"]+?)"', hook["command"]):
            candidate = Path(path)
            if candidate.suffix in (".sh", ".mjs", ".js", ".py", ".cjs", ".ps1") or "hooks" in path:
                if not candidate.exists():
                    broken.append(f"{hook['event']}/{hook['matcher']} -> missing {path}")
    if broken:
        out.append(finding(
            "HIGH",
            f"{len(broken)} hook commands reference a file that does not exist",
            sorted(set(broken)),
            "Fix the path or remove the hook entry from settings.json. A missing hook "
            "script costs a failed process spawn on every matching tool call.",
            "per-tool-call latency",
        ))

    pre_bash = [h for h in per_event.get("PreToolUse", []) if "Bash" in (h["matcher"] or "")]
    if len(pre_bash) >= 3:
        out.append(finding(
            "MED",
            f"{len(pre_bash)} PreToolUse hooks run before every Bash call",
            [f"{h['source']}: {h['command'][:110]}" for h in pre_bash],
            "Each is a serial process spawn in front of every shell command. Merge them "
            "into one dispatcher script, or drop the ones you no longer rely on.",
            "serial spawns per Bash call",
        ))

    session_start = per_event.get("SessionStart", [])
    if len(session_start) >= 2:
        out.append(finding(
            "MED",
            f"{len(session_start)} SessionStart hooks run at every session, clear, and compact",
            [f"{h['source']}: {h['command'][:110]}" for h in session_start],
            "SessionStart hooks that print context inject it into every session - the text "
            "counts against the window before you type anything. Keep the ones you read; "
            "drop the rest.",
            "startup latency + preloaded context",
        ))

    no_timeout = [h for h in inv.hooks if h["timeout"] is None and h["event"] in
                  ("PreToolUse", "PostToolUse", "SessionStart")]
    if len(no_timeout) >= 4:
        out.append(finding(
            "LOW",
            f"{len(no_timeout)} hooks have no timeout set",
            [f"{h['event']}/{h['matcher']} ({h['source']})" for h in no_timeout][:12],
            'Add "timeout": 10 (seconds) so a wedged hook cannot stall the session.',
        ))

    if sys.platform == "win32":
        bashers = [h for h in inv.hooks if "bash.exe" in h["command"].lower()]
        if bashers:
            out.append(finding(
                "MED",
                f"{len(bashers)} hooks shell out to Git Bash on Windows",
                sorted({f"{h['event']}/{h['matcher']}" for h in bashers}),
                "Each call pays Git Bash process startup (~100-300ms on Windows). Port the "
                "hot ones (PreToolUse/PostToolUse) to node or pwsh, or consolidate them.",
                "per-tool-call latency",
            ))
    return out


def check_context_budget(inv):
    """What is loaded before the user says anything."""
    out = []
    rows = []

    mem_bytes = sum(m["bytes"] for m in inv.memory_files)
    rows.append(("CLAUDE.md + rules files", len(inv.memory_files), mem_bytes))

    user_desc = sum(s["desc_bytes"] for s in inv.user_skills.values())
    rows.append(("loose skill descriptions", len(inv.user_skills), user_desc))

    plugin_desc = sum(p["desc_bytes"] for ps in inv.plugin_skills.values() for p in ps)
    plugin_count = sum(len(ps) for ps in inv.plugin_skills.values())
    rows.append(("plugin skill descriptions", plugin_count, plugin_desc))

    agent_bytes = sum(a["bytes"] for a in inv.agents.values())
    rows.append(("subagent definitions (frontmatter only in context)", len(inv.agents), agent_bytes))

    total = mem_bytes + user_desc + plugin_desc
    out.append(finding(
        "INFO",
        f"Context preloaded before your first message: ~{est_tokens(total)} tokens",
        [f"{label:<48} {n:>4} items  {human(b):>8}  ~{est_tokens(b)} tok"
         for label, n, b in rows],
        "Descriptions are what Claude reads to decide whether to invoke a skill, so they "
        "are always resident. Fewer installed skills is the only lever.",
    ))

    big = [m for m in inv.memory_files if m.get("lines", 0) > 200]
    if big:
        out.append(finding(
            "MED",
            f"{len(big)} always-loaded instruction files are over 200 lines",
            [f"{m['path']} ({m['lines']} lines, ~{est_tokens(m['bytes'])} tok)" for m in big],
            "Move the parts that only matter in some directories into .claude/rules/*.md "
            "with a paths: glob so they load conditionally.",
        ))

    unscoped = [m for m in inv.memory_files
                if "rules" in m["path"] and m.get("scoped") is False]
    if unscoped:
        out.append(finding(
            "LOW",
            f"{len(unscoped)} rules files have no paths: frontmatter",
            [m["path"] for m in unscoped],
            "Without paths: a rule loads in every project. Add a paths: glob so it only "
            "fires where it applies.",
        ))

    if len(inv.agents) >= 25:
        out.append(finding(
            "MED",
            f"{len(inv.agents)} subagents are registered",
            sorted(inv.agents)[:15] + (["..."] if len(inv.agents) > 15 else []),
            "Every agent's name and description is listed in the system prompt so the model "
            "can pick one. Uninstall the agent packs you never dispatch to.",
            f"~{est_tokens(sum(min(a['bytes'], 600) for a in inv.agents.values()))} "
            "tokens of agent listings",
        ))
    return out


def check_mcp(inv):
    out = []
    if len(inv.mcp_servers) >= 5:
        out.append(finding(
            "MED",
            f"{len(inv.mcp_servers)} MCP servers are configured",
            [f"{k} (from {v})" for k, v in sorted(inv.mcp_servers.items())],
            "Each server's tool schemas load into the system prompt unless the harness "
            "defers them. Remove the ones you do not use in this project, or scope them to "
            "the project's .mcp.json instead of user settings.",
            "tool-schema tokens + one process per server per session",
        ))
    return out


def check_settings_keys(inv):
    out = []
    env = {}
    for _label, blob in inv.all_settings:
        env.update(blob.get("env") or {})

    pct = env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if pct and pct.isdigit() and int(pct) < 70:
        out.append(finding(
            "MED",
            f"Autocompact fires at {pct}% of the window",
            [f"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE={pct}"],
            "A low value compacts often; each compaction is a summarisation round trip and "
            "loses detail. Raise it toward 85 unless you set it low deliberately.",
            f"one extra summarisation per {pct}% of window used",
        ))

    for key, ceiling in (("MAX_MCP_OUTPUT_TOKENS", 25000), ("BASH_MAX_OUTPUT_LENGTH", 50000)):
        val = env.get(key)
        if val and val.isdigit() and int(val) > ceiling:
            out.append(finding(
                "LOW",
                f"{key} is set to {val}",
                [f"{key}={val}"],
                f"A high cap means one noisy command can eat the window. {ceiling} is a "
                "saner ceiling.",
            ))

    for label, blob in inv.all_settings:
        if blob.get("verbose") is True:
            out.append(finding(
                "LOW",
                f"verbose is on in {label}",
                ['"verbose": true'],
                "Verbose output is a terminal setting, not a context one, but it makes long "
                "sessions harder to read. Turn it off if you did not set it on purpose.",
            ))

    if inv.errors:
        out.append(finding(
            "HIGH",
            f"{len(inv.errors)} config files could not be parsed",
            inv.errors,
            "Claude Code silently ignores a settings file it cannot parse, so everything in "
            "it is inert. Fix the JSON.",
        ))
    return out


def check_disk(inv):
    out = []
    projects = inv.config_root / "projects"
    size = dir_size(projects)
    if size > 2 * 1024 ** 3:
        out.append(finding(
            "LOW",
            f"Transcript history is {human(size)}",
            [str(projects)],
            "Old transcripts are only needed for --resume and history search. Delete the "
            "project subdirectories you will not resume.",
        ))
    return out


CHECKS = (
    check_duplicate_skills,
    check_hooks,
    check_settings_keys,
    check_context_budget,
    check_disabled_plugins,
    check_mcp,
    check_marketplaces,
    check_stale_cache,
    check_disk,
)


# --- output -------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=os.getcwd(),
                        help="project directory to audit alongside the user scope")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--min-severity", choices=("high", "med", "low", "info"),
                        default="info", help="hide findings below this severity")
    args = parser.parse_args(argv)

    inv = Inventory(args.project)
    findings = []
    for check in CHECKS:
        try:
            findings.extend(check(inv))
        except Exception as exc:  # a broken check must not lose the other findings
            findings.append(finding("LOW", f"check {check.__name__} failed", [repr(exc)],
                                    "Report this as a bug in the claude-code-tuneup skill."))

    floor = SEV_ORDER[args.min_severity.upper()]
    findings = [f for f in findings if SEV_ORDER[f["severity"]] <= floor]
    findings.sort(key=lambda f: SEV_ORDER[f["severity"]])

    if args.json:
        print(json.dumps({
            "config_root": str(inv.config_root),
            "project": str(inv.project_dir),
            "counts": {
                "user_skills": len(inv.user_skills),
                "plugin_skills": sum(len(v) for v in inv.plugin_skills.values()),
                "plugins_enabled": sum(1 for v in inv.enabled_plugins.values() if v),
                "plugins_disabled": sum(1 for v in inv.enabled_plugins.values() if v is False),
                "marketplaces": len(inv.marketplaces),
                "agents": len(inv.agents),
                "mcp_servers": len(inv.mcp_servers),
                "hooks": len(inv.hooks),
            },
            "findings": findings,
        }, indent=2))
        return 0

    print("Claude Code tune-up audit")
    print(f"  config root : {inv.config_root}")
    print(f"  project     : {inv.project_dir}")
    print(f"  inventory   : {sum(len(v) for v in inv.plugin_skills.values())} plugin skills, "
          f"{len(inv.user_skills)} loose skills, {len(inv.agents)} agents, "
          f"{len(inv.mcp_servers)} MCP servers, {len(inv.hooks)} hooks, "
          f"{len(inv.marketplaces)} marketplaces")
    print("")

    if not findings:
        print("No findings. Nothing worth changing.")
        return 0

    for i, f in enumerate(findings, 1):
        print(f"[{f['severity']}] {i}. {f['title']}")
        if f.get("cost"):
            print(f"     cost: {f['cost']}")
        for line in f["evidence"][:14]:
            print(f"       - {line}")
        if len(f["evidence"]) > 14:
            print(f"       - ... {len(f['evidence']) - 14} more")
        for line in f["fix"].splitlines():
            # Continuation lines in a fix are already indented as a command block; keep
            # them aligned under the "fix:" label rather than prefixing each one.
            print(f"         {line.strip()}" if line.startswith("  ") else f"     fix: {line}")
        print("")

    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print("Summary: " + ", ".join(f"{n} {s}" for s, n in
                                  sorted(counts.items(), key=lambda kv: SEV_ORDER[kv[0]])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
