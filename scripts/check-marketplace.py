#!/usr/bin/env python3
"""Verify that this repo's marketplace is internally consistent.

Every skill under ``skills/`` and every plugin under ``plugin/`` has to be registered in
several places at once, and the install scripts carry their own copies of the catalog.
The rules are written out in CLAUDE.md; this checks them, so a missed registration fails
CI instead of shipping.

The one that is not a bookkeeping rule is ``check_versions``. ``claude plugin update``
decides whether to re-copy a plugin by comparing declared versions, so editing a skill
without bumping its ``version`` leaves every already-installed copy silently stale - the
CLI reports "already at the latest version" and copies nothing. That is not visible from
the repo, only from a machine that installed the older copy, which is exactly the kind of
bug that survives review.

Run it with no arguments from anywhere in the repo. Exit status is 0 when clean, 1 when
anything is wrong.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKETPLACE = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
SH = os.path.join(ROOT, "scripts", "install-prerequisites.sh")
PS1 = os.path.join(ROOT, "scripts", "install-prerequisites.ps1")

REQUIRED_FIELDS = ("name", "source", "description", "version")


def git(*args: str) -> str:
    """Run git in the repo and return stdout, or '' if it failed."""
    done = subprocess.run(
        ["git", "-C", ROOT, *args], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def read(path: str) -> str:
    """Read a repo file as text."""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def load_entries() -> list[dict]:
    """Return the marketplace's plugin entries."""
    return json.loads(read(MARKETPLACE))["plugins"]


def on_disk() -> dict[str, str]:
    """Map directory name -> repo-relative path for every skill and plugin directory."""
    found = {}
    for parent in ("skills", "plugin"):
        base = os.path.join(ROOT, parent)
        for name in sorted(os.listdir(base)):
            if os.path.isdir(os.path.join(base, name)):
                found[name] = f"{parent}/{name}"
    return found


def bash_array(text: str, name: str) -> list[str] | None:
    r"""Read a bash array literal, whether it is written on one line or many.

    Anchoring the close on ``^\)`` only works for the multi-line form; ``TEAM_KEYS=("a"
    "b")`` closes on the same line and would otherwise run on to the next array.
    """
    block = re.search(rf"^{name}=\((.*?)\)\s*$", text, re.S | re.M)
    if not block:
        return None
    return [x.strip('"') for x in block.group(1).split()]


def ps_keys(text: str, name: str) -> list[str] | None:
    """Read the Key values out of a PowerShell catalog literal.

    Comment lines are dropped first: a row that has been commented out is not in the
    catalog, but its ``Key = '...'`` still matches, which would hide exactly the kind of
    half-finished edit this is here to catch.
    """
    block = re.search(rf"\$script:{name}\s*=\s*@\((.*?)^\)", text, re.S | re.M)
    if not block:
        return None
    live = "\n".join(
        line for line in block.group(1).splitlines() if not line.lstrip().startswith("#")
    )
    return re.findall(r"Key\s*=\s*'([^']+)'", live)


def check_registration(entries, disk, fail):
    """Every directory is registered, every entry exists, and sources point at it."""
    names = {e["name"] for e in entries}
    for name in sorted(set(disk) - names):
        fail(f"{disk[name]}/ exists but is not registered in marketplace.json")
    for name in sorted(names - set(disk)):
        fail(f"marketplace.json registers '{name}' but no such directory exists")

    for entry in entries:
        name = entry.get("name", "?")
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                fail(f"{name}: marketplace entry is missing '{field}'")
        source = entry.get("source", "")
        if name in disk and source != f"./{disk[name]}":
            fail(f"{name}: source is '{source}', expected './{disk[name]}'")
        if not os.path.isdir(os.path.join(ROOT, source.lstrip("./"))):
            fail(f"{name}: source '{source}' is not a directory")

    for name, path in sorted(disk.items()):
        nested = os.path.join(ROOT, path, ".claude-plugin", "marketplace.json")
        if os.path.isfile(nested):
            fail(
                f"{name}: {path}/.claude-plugin/marketplace.json makes this directory "
                "look like a second marketplace - the repo root's is the only one"
            )


def check_skill_manifests(entries, fail):
    """Each skill has a SKILL.md whose frontmatter name matches its directory."""
    for entry in entries:
        source = entry["source"].lstrip("./")
        if not source.startswith("skills/"):
            continue
        name = entry["name"]
        skill_md = os.path.join(ROOT, source, "SKILL.md")
        if not os.path.isfile(skill_md):
            fail(f"{name}: {source}/SKILL.md is missing")
            continue
        matter = re.match(r"^---\n(.*?)\n---", read(skill_md), re.S)
        if not matter:
            fail(f"{name}: SKILL.md has no YAML frontmatter")
            continue
        body = matter.group(1)
        declared = re.search(r"^name:\s*(.+?)\s*$", body, re.M)
        if not declared:
            fail(f"{name}: SKILL.md frontmatter has no 'name'")
        elif declared.group(1).strip().strip("\"'") != name:
            fail(
                f"{name}: SKILL.md frontmatter name is "
                f"'{declared.group(1).strip()}', directory is '{name}'"
            )
        if not re.search(r"^description:\s*\S", body, re.M):
            fail(f"{name}: SKILL.md frontmatter has no 'description'")


def check_plugin_manifests(entries, fail):
    """A plugin's own plugin.json agrees with the version the marketplace declares."""
    for entry in entries:
        manifest = os.path.join(
            ROOT, entry["source"].lstrip("./"), ".claude-plugin", "plugin.json"
        )
        if not os.path.isfile(manifest):
            continue
        declared = json.loads(read(manifest)).get("version")
        if declared != entry["version"]:
            fail(
                f"{entry['name']}: plugin.json says version {declared}, "
                f"marketplace.json says {entry['version']}"
            )


def check_catalogs(entries, fail):
    """Both install scripts list the same keys, in the same order, as the marketplace."""
    skills = [e["name"] for e in entries if e["source"].startswith("./skills/")]
    plugins = [e["name"] for e in entries if e["source"].startswith("./plugin/")]

    shell = read(SH)
    pwsh = read(PS1)

    def keys(var):
        return bash_array(shell, var) or []

    def ps_catalog(var):
        return ps_keys(pwsh, var) or []

    for label, actual, expected in (
        ("SKILL_KEYS (.sh)", keys("SKILL_KEYS"), skills),
        ("PLUGIN_KEYS (.sh)", keys("PLUGIN_KEYS"), plugins),
        ("SkillCatalog (.ps1)", ps_catalog("SkillCatalog"), skills),
        ("PluginCatalog (.ps1)", ps_catalog("PluginCatalog"), plugins),
    ):
        if actual != expected:
            fail(
                f"{label} does not match marketplace.json\n"
                f"      has:      {actual}\n"
                f"      expected: {expected}"
            )


def check_menu_parity(fail):
    """The two install scripts must offer the same menu, in the same order.

    ``--select 3,7`` is positional, so a row present in one script and not the other
    silently means something different on Windows and Linux, and every doc that names an
    item by number is wrong for half the users.
    """
    shell = read(SH)
    pwsh = read(PS1)

    sh_keys = bash_array(shell, "MENU_KEYS") or []
    sh_defaults = re.search(r"^MENU_DEFAULT=\((.*?)\)", shell, re.S | re.M).group(1).split()
    catalog = re.search(r"\$script:Catalog\s*=\s*@\((.*?)^\)", pwsh, re.S | re.M).group(1)
    catalog = "\n".join(
        line for line in catalog.splitlines() if not line.lstrip().startswith("#")
    )
    ps_rows = re.findall(
        r"Key\s*=\s*'([^']+)'\s*;\s*Default\s*=\s*\$(true|false)", catalog
    )
    ps_menu = [k for k, _ in ps_rows]
    ps_defaults = ["1" if d == "true" else "0" for _, d in ps_rows]

    if sh_keys != ps_menu:
        fail(
            "the two install scripts do not offer the same menu\n"
            f"      .sh:  {sh_keys}\n"
            f"      .ps1: {ps_menu}"
        )
    if len(sh_defaults) != len(sh_keys):
        fail("MENU_DEFAULT has a different length from MENU_KEYS in the .sh")
    elif sh_defaults != ps_defaults:
        differing = [
            f"{k} (.sh {a}, .ps1 {b})"
            for k, a, b in zip(sh_keys, sh_defaults, ps_defaults)
            if a != b
        ]
        fail(f"menu rows are ticked by default in one script and not the other: {differing}")


def check_group_parity(fail):
    """Every sub-picker group has to hold the same entries, in order, in both scripts."""
    shell = read(SH)
    pwsh = read(PS1)

    groups = (
        ("own-skills", "SKILL_KEYS", "SkillCatalog"),
        ("team", "TEAM_KEYS", "TeamCatalog"),
        ("community", "COMMUNITY_KEYS", "CommunityCatalog"),
        ("voltagent", "VOLTAGENT_KEYS", "VoltAgentCatalog"),
        ("repo-plugins", "PLUGIN_KEYS", "PluginCatalog"),
    )
    for menu_key, bash_var, ps_var in groups:
        sh_keys = bash_array(shell, bash_var)
        if sh_keys is None:
            fail(f"{menu_key}: the .sh has no {bash_var} array")
            continue
        ps_entries = ps_keys(pwsh, ps_var)
        if ps_entries is None:
            fail(f"{menu_key}: the .ps1 has no ${ps_var}")
            continue
        if sh_keys != ps_entries:
            fail(
                f"{menu_key}: {bash_var} and ${ps_var} do not match\n"
                f"      .sh:  {sh_keys}\n"
                f"      .ps1: {ps_entries}"
            )
        if not sh_keys:
            fail(f"{menu_key}: the group is empty, so its sub-picker would show nothing")


def check_docs(entries, fail):
    """The catalog tables list every entry."""
    skills = [e["name"] for e in entries if e["source"].startswith("./skills/")]
    plugins = [e["name"] for e in entries if e["source"].startswith("./plugin/")]

    for doc, wanted, link in (
        ("skills/README.md", skills, "{name}"),
        ("plugin/README.md", plugins, "{name}"),
        ("README.md", skills, "skills/{name}"),
        ("README.md", plugins, "plugin/{name}"),
    ):
        text = read(os.path.join(ROOT, doc))
        for name in wanted:
            if f"[`{name}`]({link.format(name=name)})" not in text:
                fail(f"{doc}: no table row linking to '{name}'")


def version_set_at(name: str, version: str, history: list[str]) -> str | None:
    """The oldest commit at which this entry already declared its current version."""
    found = None
    for commit in history:  # newest first
        blob = git("show", f"{commit}:.claude-plugin/marketplace.json")
        if not blob:
            break
        try:
            entries = json.loads(blob)["plugins"]
        except (ValueError, KeyError):
            break
        current = next((e["version"] for e in entries if e["name"] == name), None)
        if current != version:
            break
        found = commit
    return found


def check_versions(entries, fail):
    """A plugin whose files changed since its version was last set is stale for users.

    'claude plugin update' compares declared versions, so an edit without a bump never
    reaches a machine that already installed the older copy.
    """
    if not git("rev-parse", "--git-dir"):
        print("  note: not a git checkout - skipping the version-drift check")
        return
    history = git("log", "--format=%H", "--", ".claude-plugin/marketplace.json").split()
    if not history:
        print("  note: no history for marketplace.json - skipping the version-drift check")
        return

    for entry in entries:
        name, version = entry["name"], entry["version"]
        source = entry["source"].lstrip("./")
        bump = version_set_at(name, version, history)
        if bump is None:
            continue  # never committed yet: nothing to compare against
        changed = subprocess.run(
            ["git", "-C", ROOT, "diff", "--quiet", bump, "HEAD", "--", source],
            check=False,
        )
        if changed.returncode == 1:
            fail(
                f"{name}: {source}/ has changed since version {version} was set "
                f"({git('log', '-1', '--format=%h %cs', bump)}), but the version was "
                "not bumped - 'claude plugin update' compares versions, so every "
                "already-installed copy stays stale. Bump it in marketplace.json."
            )


def main() -> int:
    """Run every check and report."""
    problems: list[str] = []
    entries = load_entries()
    disk = on_disk()

    def fail(message: str) -> None:
        problems.append(message)

    check_registration(entries, disk, fail)
    check_skill_manifests(entries, fail)
    check_plugin_manifests(entries, fail)
    check_catalogs(entries, fail)
    check_menu_parity(fail)
    check_group_parity(fail)
    check_docs(entries, fail)
    check_versions(entries, fail)

    skills = sum(1 for e in entries if e["source"].startswith("./skills/"))
    plugins = len(entries) - skills
    print(f"marketplace: {skills} skills, {plugins} plugins")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
