"""Vault recall for the context hook: find obsidian-vault's CLI, ask it, label
what comes back.

crew does not search vaults itself. `obsidian-vault` owns capture and
retrieval (docs/review/04-redesign.md, "Memory and Obsidian"), so this module
calls that plugin's read-only contract and nothing else:

    python3 <obsidian-vault root>/scripts/vault_ops.py recall \
        --query <text> --vaults <a,b,c> --max-chars N --json

Four rules hold everywhere below, and each has a test:

- **Never block, never raise.** A missing plugin, a CLI that exits non-zero,
  times out, or prints something that is not JSON is a MISS with a named
  reason. The hook logs it and injects nothing from recall. A session must
  never fail to start because a vault is unreachable.
- **Every snippet names its vault.** An item the CLI returns without a vault
  label is dropped, not injected unlabelled -- a recall line nobody can trace
  to a source is a line nobody can check or correct.
- **Only the vaults asked for.** A snippet naming a vault outside the list
  this module passed to `--vaults` is dropped, as is one whose vault or note
  name carries a control character or line break.
- **Priority is the repo's.** `memory.recall.vaults` in the crew config is an
  ordered list; snippets are ordered by that list first and the CLI's own rank
  second. With no list, vaults come from `~/.claude/obsidian/config.json`:
  role `primary` first, then `recall`; role `ignore` is never asked.

Standard library only. Read-only: this module writes nothing anywhere.
"""

import glob
import json
import os
import re
import subprocess
import sys

DEFAULT_MAX_CHARS = 800
CLI_TIMEOUT_SECONDS = 4
# The contract is Lane A's. `scripts/` is what it names; `hooks/scripts/` is
# where vault_ops.py lived before that contract, so a plugin that predates it
# is still found -- and then answers `recall` with an argparse error, which is
# a logged miss, not a crash.
_CLI_RELATIVE = (("scripts", "vault_ops.py"), ("hooks", "scripts", "vault_ops.py"))
_ROLE_ORDER = {"primary": 0, "recall": 1}


def obsidian_config_path():
    override = os.environ.get("CREW_OBSIDIAN_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "obsidian", "config.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data


def _version_key(path):
    parts = []
    for piece in os.path.basename(path.rstrip("/\\")).split("."):
        parts.append(int(piece) if piece.isdigit() else -1)
    return parts


def _candidate_roots(crew_root):
    """Where an obsidian-vault plugin might be, most specific first."""
    roots = []
    env_root = os.environ.get("OBSIDIAN_VAULT_PLUGIN_ROOT")
    if env_root:
        roots.append(env_root)
    registry = _read_json(os.path.join(
        os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"))
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    if isinstance(plugins, dict):
        for key, installs in plugins.items():
            if not str(key).startswith("obsidian-vault@") or not isinstance(installs, list):
                continue
            for install in installs:
                if isinstance(install, dict) and install.get("installPath"):
                    roots.append(str(install["installPath"]))
    if crew_root:
        parent = os.path.dirname(os.path.abspath(crew_root))
        # Cache layout: <cache>/<marketplace>/crew/<version>/ beside
        # <cache>/<marketplace>/obsidian-vault/<version>/.
        versions = glob.glob(os.path.join(os.path.dirname(parent), "obsidian-vault", "*"))
        roots.extend(sorted(versions, key=_version_key, reverse=True))
        # A marketplace checkout: plugin/crew beside plugin/obsidian-vault.
        roots.append(os.path.join(parent, "obsidian-vault"))
    return roots


def find_cli(crew_root=None):
    """Absolute path to vault_ops.py, or None. `CREW_VAULT_OPS` wins outright."""
    explicit = os.environ.get("CREW_VAULT_OPS")
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for root in _candidate_roots(crew_root):
        for rel in _CLI_RELATIVE:
            path = os.path.join(root, *rel)
            if os.path.isfile(path):
                return path
    return None


def vault_order(crew_cfg, obsidian_cfg=None):
    """The ordered vault names to ask. Never includes a vault whose role is
    `ignore`, whatever the repo list says -- the machine's owner decided that
    vault is not for recall, and a cloned repo does not get to override it.
    """
    if obsidian_cfg is None:
        obsidian_cfg = _read_json(obsidian_config_path())
    vaults = obsidian_cfg.get("vaults") if isinstance(obsidian_cfg, dict) else None
    vaults = vaults if isinstance(vaults, dict) else {}

    def role(name):
        entry = vaults.get(name)
        if not isinstance(entry, dict):
            return None
        value = entry.get("role")
        if isinstance(value, str) and value:
            return value
        # No role recorded: the default vault is the primary, any other is
        # a recall vault. Lane A's config gains `role`; older files lack it.
        return "primary" if entry.get("default") is True else "recall"

    recall = (crew_cfg or {}).get("memory", {})
    recall = recall.get("recall", {}) if isinstance(recall, dict) else {}
    listed = recall.get("vaults") if isinstance(recall, dict) else None
    if isinstance(listed, list) and listed:
        names = [n for n in listed if isinstance(n, str) and n]
        return [n for n in dict.fromkeys(names) if role(n) != "ignore"]
    known = [(name, role(name)) for name in vaults]
    ranked = [(n, r) for n, r in known if r in _ROLE_ORDER]
    ranked.sort(key=lambda pair: _ROLE_ORDER[pair[1]])
    return [n for n, _ in ranked]


def max_chars(crew_cfg):
    recall = (crew_cfg or {}).get("memory", {})
    recall = recall.get("recall", {}) if isinstance(recall, dict) else {}
    value = recall.get("maxChars") if isinstance(recall, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return DEFAULT_MAX_CHARS


def _items(parsed):
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("results", "snippets", "hits", "items"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
    return None


def _field(item, *names):
    for name in names:
        value = item.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# C0/C1 controls and the Unicode line/paragraph separators: any of them in a
# vault or note name could start a new injected line with no vault label.
_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def parse(stdout, order):
    """(snippets, dropped) from the CLI's JSON. Each snippet is a dict with
    vault, note, text, rank. Counted in `dropped`, never injected: an item
    with no vault label, a vault or note name carrying a control character
    or line break, and an item from a vault the repo did not ask for -- the
    CLI's answer does not get to widen `memory.recall.vaults`."""
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return None, 0
    items = _items(parsed)
    if items is None:
        return None, 0
    priority = {name: i for i, name in enumerate(order)}
    snippets, dropped = [], 0
    for rank, item in enumerate(items):
        if not isinstance(item, dict):
            dropped += 1
            continue
        vault = _field(item, "vault", "vaultName")
        note = _field(item, "note", "path", "notePath", "file")
        text = _field(item, "text", "snippet", "excerpt", "content")
        if not vault or not note or not text:
            dropped += 1
            continue
        if _CONTROL_RE.search(vault) or _CONTROL_RE.search(note) or vault not in priority:
            dropped += 1
            continue
        text = " ".join(_CONTROL_RE.sub(" ", text).split())
        if not text:
            dropped += 1
            continue
        snippets.append({"vault": vault, "note": note, "text": text, "rank": rank})
    snippets.sort(key=lambda s: (priority.get(s["vault"], len(priority)), s["rank"]))
    return snippets, dropped


def label(snippet):
    """The one line injected per snippet. The vault name leads, always."""
    return f"- [vault:{snippet['vault']}] {snippet['note']}: {snippet['text']}"


def recall(query, crew_cfg, crew_root=None, budget=None, runner=None):
    """Ask the vault CLI. Returns a dict that never raises:

    {"status": "hit"|"miss"|"skipped", "reason": str, "snippets": [...],
     "dropped": int, "vaults": [...]}
    """
    result = {"status": "skipped", "reason": "", "snippets": [], "dropped": 0, "vaults": []}
    query = " ".join((query or "").split())
    if len(query) < 3:
        result["reason"] = "no-query"
        return result
    order = vault_order(crew_cfg)
    result["vaults"] = order
    if not order:
        result.update(status="miss", reason="no-vaults")
        return result
    cli = find_cli(crew_root)
    if not cli:
        result.update(status="miss", reason="cli-missing")
        return result
    limit = max_chars(crew_cfg)
    if budget is not None:
        limit = max(0, min(limit, budget))
    if limit < 80:
        result.update(status="skipped", reason="no-budget")
        return result
    argv = [sys.executable, cli, "recall", "--query", query[:500],
            "--vaults", ",".join(order), "--max-chars", str(limit), "--json"]
    run = runner or subprocess.run
    try:
        done = run(argv, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=CLI_TIMEOUT_SECONDS, check=False,
                   stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        result.update(status="miss", reason="cli-timeout")
        return result
    except (OSError, subprocess.SubprocessError):
        result.update(status="miss", reason="cli-unrunnable")
        return result
    if done.returncode != 0:
        result.update(status="miss", reason=f"cli-exit-{done.returncode}")
        return result
    snippets, dropped = parse(done.stdout or "", order)
    if snippets is None:
        result.update(status="miss", reason="cli-bad-json")
        return result
    result["dropped"] = dropped
    if not snippets:
        result.update(status="miss", reason="no-hits")
        return result
    result.update(status="hit", reason="", snippets=snippets)
    return result
