"""Which agents `.crew/verify.json` names that are not installed on this machine.

    python3 verify_agents.py --root . --check [--json]

Read-only. `/crew:status` shows the result as one `agents` line, and
`/crew:verify` and `/crew:review` run the same check instead of resolving
names by hand (T-0065, item 3: a rule naming `php-developer`, which was not
installed, went unnoticed until a review reported the gap).

WHAT COUNTS AS INSTALLED. A name resolves when one of these supplies it:

  - crew's own roles (`crew_state.ROLE_TIERS`) and the files in crew's own
    `agents/`, bare and as `crew:<name>`;
  - user agents, `${CLAUDE_CONFIG_DIR:-~/.claude}/agents/*.md`, bare;
  - project agents, `<root>/.claude/agents/*.md`, bare;
  - the agents of every plugin in `<config>/plugins/installed_plugins.json`
    whose `<plugin>@<marketplace>` key the settings scopes enable, as
    `<plugin>:<name>` and bare `<name>`.

An agent's name is its frontmatter `name:`, else its file stem. Enabled is
read in `crew_endpoints.gizmoduck_installed`'s scope order: project
`settings.local.json`, project `settings.json`, then `<config>`'s two; the
first scope holding a real JSON boolean for the key decides. A scope that is
absent, or holds no boolean for the key, defers to the next. A key no scope
names is not enabled.

NOT CHECKED: managed-policy agents and agents passed with `--agents` on the
command line. Both are listed in the output's `notChecked`.

AN UNKNOWN IS NEVER A PASS (root CLAUDE.md, Lessons). A source that will not
parse makes every name it could have supplied `unknown`, never `installed`
and never `missing`: an unparseable registry, an unparseable settings scope
read before a decision for a plugin's key, an unreadable agent file. A name
is `missing` only when every source it could come from was read cleanly.
Crew's own roles never depend on those files, so they still resolve.

Exit 0: every named agent resolves (or none is named). Exit 1: at least one
is missing. Exit 2: none missing, at least one unknown, or verify.json
itself will not parse.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

import crew_state  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CREW_AGENTS = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir, "agents"))
NOT_CHECKED = ["managed-policy agents", "agents passed with --agents"]


def config_dir():
    """`CLAUDE_CONFIG_DIR`, or `~/.claude` when that is unset."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _read(path):
    """(text, None), (None, None) when absent, or (None, reason) when unreadable."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.read(), None
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{path}: {exc.__class__.__name__}"


def _load_json(path):
    """(value, None), (None, None) when absent, or (None, reason) when it will not parse."""
    text, problem = _read(path)
    if text is None:
        return None, problem
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, f"{path} does not parse ({exc.msg})"


def named(root):
    """`({name: [rule paths...]}, problem)` from `.crew/verify.json`."""
    path = os.path.join(root, ".crew", "verify.json")
    data, problem = _load_json(path)
    if problem:
        return {}, problem
    out = {}
    rules = data.get("rules") if isinstance(data, dict) else None
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict) or not isinstance(rule.get("agents"), list):
            continue
        paths = [str(p) for p in rule.get("paths") or [] if isinstance(p, str)]
        for name in rule["agents"]:
            if isinstance(name, str) and name.strip():
                bucket = out.setdefault(name.strip(), [])
                bucket.extend(p for p in paths if p not in bucket)
    return out, None


def agent_name(path):
    """(name, None) from the frontmatter `name:`, else the file stem; or (None, reason)."""
    text, problem = _read(path)
    if text is None:
        return None, problem or f"{path} vanished while being read"
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, sep, value = line.partition(":")
            if sep and key.strip() == "name":
                value = value.strip().strip("\"'")
                if value:
                    return value, None
    return os.path.splitext(os.path.basename(path))[0], None


def _agents_in(directory):
    """(names, problems) for every `*.md` directly in `directory`."""
    try:
        entries = sorted(os.listdir(directory))
    except FileNotFoundError:
        return set(), []
    except OSError as exc:
        return set(), [f"{directory}: {exc.__class__.__name__}"]
    names, problems = set(), []
    for entry in entries:
        if not entry.endswith(".md"):
            continue
        name, problem = agent_name(os.path.join(directory, entry))
        if problem:
            problems.append(problem)
        else:
            names.add(name)
    return names, problems


def _scopes(root):
    config = config_dir()
    return [os.path.join(root, ".claude", "settings.local.json"),
            os.path.join(root, ".claude", "settings.json"),
            os.path.join(config, "settings.local.json"),
            os.path.join(config, "settings.json")]


def plugin_enabled(root, key, scopes=None):
    """True, False, or a reason string when it could not tell."""
    unreadable = []
    for path, data, problem in scopes if scopes is not None else _read_scopes(root):
        if problem:
            unreadable.append(problem)
            continue
        enabled = data.get("enabledPlugins") if isinstance(data, dict) else None
        value = enabled.get(key) if isinstance(enabled, dict) else None
        if isinstance(value, bool):
            # A narrower scope that would not parse could have said otherwise.
            return f"{unreadable[0]}, read before {path}" if unreadable else value
    return unreadable[0] if unreadable else False


def _read_scopes(root):
    out = []
    for path in _scopes(root):
        data, problem = _load_json(path)
        out.append((path, data, problem))
    return out


def installed(root):
    """What resolves on this machine, and what could not be told.

    Returns `(names, maybe, everywhere)`: `names` is every resolvable spelling;
    `maybe` maps a spelling to the reason it could not be told (its plugin's
    enabled state is unknown); `everywhere` lists reasons that leave ANY
    unresolved name unknown (unreadable registry or agent files). The plugin
    name `crew` is never in doubt: it is resolved from crew's own code."""
    names, maybe, everywhere = set(), {}, []
    for role in crew_state.ROLE_TIERS:
        names.update((role, f"crew:{role}"))
    crew_own, problems = _agents_in(CREW_AGENTS)
    everywhere += problems
    for name in crew_own:
        names.update((name, f"crew:{name}"))
    for directory in (os.path.join(config_dir(), "agents"), os.path.join(root, ".claude", "agents")):
        found, problems = _agents_in(directory)
        names |= found
        everywhere += problems

    registry_path = os.path.join(config_dir(), "plugins", "installed_plugins.json")
    registry, problem = _load_json(registry_path)
    if problem:
        everywhere.append(f"plugin registry {problem}")
        return names, maybe, everywhere
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    if registry is not None and not isinstance(plugins, dict):
        everywhere.append(f"plugin registry {registry_path} has no `plugins` object")
        return names, maybe, everywhere
    scopes = _read_scopes(root)
    for key, installs in sorted((plugins or {}).items()):
        plugin = str(key).split("@", 1)[0]
        state = plugin_enabled(root, key, scopes)
        if state is False:
            continue
        spelled = set()
        for install in installs if isinstance(installs, list) else []:
            path = install.get("installPath") if isinstance(install, dict) else None
            if not path:
                continue
            found, problems = _agents_in(os.path.join(str(path), "agents"))
            everywhere += problems
            for name in found:
                spelled.update((name, f"{plugin}:{name}"))
        if state is True:
            names |= spelled
        else:
            for spelling in spelled:
                maybe.setdefault(spelling, f"whether {key} is enabled: {state}")
    return names, maybe, everywhere


def check(root):
    """The result as a dict; `status` is `ok`, `missing` or `unknown`."""
    root = os.path.abspath(root)
    result = {"status": "ok", "named": 0, "missing": {}, "unknown": [], "notChecked": NOT_CHECKED}
    wanted, problem = named(root)
    if problem:
        result.update(status="unknown", unknown=[{"name": None, "reason": problem, "paths": []}])
        return result
    result["named"] = len(wanted)
    if not wanted:
        return result
    names, maybe, everywhere = installed(root)
    for name, paths in sorted(wanted.items()):
        if name in names:
            continue
        plugin = name.split(":", 1)[0] if ":" in name else None
        reason = maybe.get(name)
        if reason is None and plugin != "crew" and everywhere:
            reason = everywhere[0]
        if reason:
            result["unknown"].append({"name": name, "reason": reason, "paths": paths})
        else:
            result["missing"][name] = paths
    if result["missing"]:
        result["status"] = "missing"
    elif result["unknown"]:
        result["status"] = "unknown"
    return result


def render(result):
    """Human-readable lines for `--check`."""
    if result["status"] == "ok":
        head = (f"ok - {result['named']} agent(s) named in .crew/verify.json, all installed"
                if result["named"] else "ok - no agents named in .crew/verify.json")
        lines = [head]
    else:
        lines = [f"{result['status']}:"]
    for name, paths in result["missing"].items():
        lines.append(f"  MISSING {name} (verify.json rule: {', '.join(paths) or 'no paths'})")
    for item in result["unknown"]:
        label = item["name"] or ".crew/verify.json"
        lines.append(f"  UNKNOWN {label} - {item['reason']}")
    lines.append("not checked: " + ", ".join(result["notChecked"]))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="exit 0 ok, 1 missing, 2 unknown")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    result = check(args.root)
    print(json.dumps(result, indent=2) if args.json else "\n".join(render(result)))
    if not args.check:
        return 0
    return {"ok": 0, "missing": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
