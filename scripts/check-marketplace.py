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
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKETPLACE = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
SH = os.path.join(ROOT, "scripts", "install-prerequisites.sh")
PS1 = os.path.join(ROOT, "scripts", "install-prerequisites.ps1")

REQUIRED_FIELDS = ("name", "source", "description", "version")

# Hard-coded, not parsed out of LICENSE - the file's own first line, "GNU
# GENERAL PUBLIC LICENSE" / "Version 2, June 1991", is the source of this
# identifier. Re-deriving it from license text is the kind of parsing that
# breaks quietly on a wording change nobody meant to be load-bearing; a
# licence change is rare and deliberate enough to warrant editing this
# constant by hand instead.
EXPECTED_LICENSE = "GPL-2.0-only"


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


def check_license_consistency(entries, fail):
    """Every plugin's declared licence matches the repository's own LICENSE.

    Root `LICENSE` is GNU GPL v2; two plugins shipped `"license": "MIT"` and
    three shipped no `license` key at all, so a consumer reading `plugin.json`
    and a consumer reading `LICENSE` reached different conclusions about the
    same code - MIT into GPL-2 is a lawful direction of copy, so nothing
    upstream was broken, but the plugin's own claim about itself was wrong
    either way: silently permissive where the repo is copyleft, or silently
    unstated where the repo picked a licence on purpose.

    `EXPECTED_LICENSE` is hard-coded rather than parsed out of LICENSE's text -
    licence text is not the kind of thing a checker should be inferring an
    SPDX id from, and a wording change in the file (a typo fix, added boilerplate)
    is not a signal that the project's declared licence changed. Both sides
    only ever move on a human editing them.
    """
    for entry in entries:
        if not entry["source"].startswith("./plugin/"):
            continue
        manifest = os.path.join(
            ROOT, entry["source"].lstrip("./"), ".claude-plugin", "plugin.json"
        )
        if not os.path.isfile(manifest):
            continue
        declared = json.loads(read(manifest)).get("license")
        if declared != EXPECTED_LICENSE:
            fail(
                f"{entry['name']}: plugin.json license is {declared!r}, "
                f"repository LICENSE requires {EXPECTED_LICENSE!r}"
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
    # MENU_NAME is one quoted label per line and its entries contain spaces, so
    # bash_array (which splits on whitespace) can only count it, not read it. Nothing
    # else checks this length: when obsidian-mcp was added to MENU_KEYS and not to
    # MENU_NAME, every label from that row on displayed the NEXT item's text and every
    # check stayed green.
    name_block = re.search(r"^MENU_NAME=\((.*?)^\)", shell, re.S | re.M)
    if not name_block:
        fail("the .sh has no MENU_NAME array")
    else:
        labels = len(re.findall(r'^\s*"', name_block.group(1), re.M))
        if labels != len(sh_keys):
            fail(
                f"MENU_NAME has {labels} labels but MENU_KEYS has {len(sh_keys)} rows "
                "in the .sh - every label from the gap on shows another item's text"
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


def is_ancestor(older: str, newer: str) -> bool:
    """True when `older` is an ancestor of `newer`, or the same commit."""
    done = subprocess.run(
        ["git", "-C", ROOT, "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0


_DECLARED: dict[tuple[str, str], dict[str, str] | None] = {}


def declared_at(commit: str) -> dict[str, str] | None:
    """{name: version} as the manifest declared it at `commit`, or None if unreadable.

    None ends the caller's walk, which narrows the window rather than widening
    it - the one direction that under-checks. It covers an unreadable blob and
    also a manifest whose entries are malformed, which before this was an
    uncaught raise and a loud crash. Both are quiet here. That is survivable
    only because the walk is over committed history, so a malformed manifest in
    it was already rejected by this script when it landed, and because CI sets
    `fetch-depth: 0` for this check by name. Neither is a guarantee; if a
    shallow clone ever reaches this code the walk goes short and silent.

    Cached: the two history walks cover mostly the same commits, and every
    marketplace entry walks them again, so the uncached form fetched and parsed
    the same few dozen blobs some eighty times over and cost three minutes.
    Keyed by ROOT as well as commit because the test suite repoints ROOT at
    throwaway fixtures whose commits can hash identically.
    """
    key = (ROOT, commit)
    if key not in _DECLARED:
        blob = git("show", f"{commit}:.claude-plugin/marketplace.json")
        try:
            _DECLARED[key] = {e["name"]: e["version"] for e in json.loads(blob)["plugins"]}
        except (ValueError, KeyError, TypeError):
            _DECLARED[key] = None
    return _DECLARED[key]


def version_set_at(name: str, version: str, history: list[str]) -> str | None:
    """The oldest commit at which this entry already declared its current version."""
    found = None
    for commit in history:  # newest first
        declared = declared_at(commit)
        if declared is None or declared.get(name) != version:
            break
        found = commit
    return found


def bump_candidates(name: str, version: str, histories: list[list[str]]) -> list[str]:
    """Where this version could have been set, taking the widest window available.

    ``version_set_at`` stops at the first commit whose manifest declares a
    different version, which is only the right answer when the versions along
    the walk are monotonic. They are not across a merge: ``git log -- <path>``
    is ordered by date, so a side branch that forked *before* the bump
    interleaves its still-old manifest in among the newer commits, the walk
    stops there, and the window shrinks to the merge itself - which then diffs
    against its own tree and reports nothing changed. That is how 0.19.29
    shipped a changed ``plugin/crew/`` under an unbumped version.

    So the walk runs over two orderings - by date and by ``--first-parent`` -
    and each answers a shape the other gets wrong. First-parent alone is *not*
    the fix: GitHub Actions checks out ``refs/pull/N/merge`` on a
    ``pull_request`` event, whose first parent is the base branch, so a
    first-parent walk follows ``main`` straight past the PR's own bump and goes
    blind on exactly the diff CI exists to judge.

    Both candidates are kept, then narrowed by ancestry: if one is an ancestor
    of the other it is the older, so it alone is kept and the window is the
    wider of the two. When neither is an ancestor of the other the ordering is
    genuinely unknown, and both are returned so the caller checks both windows.
    "Could not tell which is older" must not collapse into either branch -
    picking one would be a guess wearing the label of a check.
    """
    found = {version_set_at(name, version, h) for h in histories}
    found.discard(None)
    if len(found) < 2:
        return sorted(found)
    return sorted(
        c for c in found if not any(o != c and is_ancestor(o, c) for o in found)
    )


def check_versions(entries, fail):
    """A plugin whose files changed since its version was last set is stale for users.

    'claude plugin update' compares declared versions, so an edit without a bump never
    reaches a machine that already installed the older copy.
    """
    if not git("rev-parse", "--git-dir"):
        print("  note: not a git checkout - skipping the version-drift check")
        return
    manifest = ".claude-plugin/marketplace.json"
    history = git("log", "--format=%H", "--", manifest).split()
    if not history:
        print("  note: no history for marketplace.json - skipping the version-drift check")
        return
    # See bump_candidates: the date ordering and the first-parent ordering each
    # miss a commit shape the other catches, so both are walked.
    first_parent = git("log", "--first-parent", "--format=%H", "--", manifest).split()

    for entry in entries:
        name, version = entry["name"], entry["version"]
        source = entry["source"].lstrip("./")
        for bump in bump_candidates(name, version, [history, first_parent]):
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
                break  # one report per entry; the other window says the same thing


CLAIM_RE = re.compile(r"<!--\s*claim:\s*([a-z0-9-]+(?::[a-z0-9._-]+)?)\s*-->")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
SKILLS_RE = re.compile(r"(\d+)(?:\s+of\s+(\d+))?\s+skills\b")
PLUGIN_SKILLS_RE = re.compile(r"(\d+)\s+(?:bundled\s+)?skills?\b")
VERSION_ROW_RE = re.compile(r"^\|\s*\*\*Version\*\*\s*\|\s*([0-9][0-9.]*)")
BIND_WINDOW = 12


def count_plugin_skills(name: str) -> int:
    """How many bundled skills ``plugin/<name>/skills/`` actually holds.

    Counted the same way a person verifies it by eye - a subdirectory with its
    own ``SKILL.md`` - rather than a raw directory listing, so a stray file or
    an in-progress folder with no ``SKILL.md`` yet does not inflate the count.
    """
    skills_dir = os.path.join(ROOT, "plugin", name, "skills")
    if not os.path.isdir(skills_dir):
        return 0
    return sum(
        1
        for entry in os.listdir(skills_dir)
        if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md"))
    )


def check_self_claims(entries, fail):
    """Verify the numbers this repo states about itself, where they are marked.

    Prose drifts. `28 skills` in README and INSTALLATION stayed four days behind
    a marketplace that had reached 34, and `plugin/PLUGINS.md`'s crew row sat at
    0.16.22 through 37 releases, because no check compared either to the source
    of truth beside it.

    The check is keyed on an explicit marker and NOT on the shape of the text.
    A bare `N skills` regex cannot tell the marketplace total from a plugin's
    own bundle -- run across this repo it matched 32 places and was right about
    none of them, because `17 skills` (crew's), `3 skills` (obsidian-vault's)
    and `0 skills` are all true sentences about something else. A checker that
    cannot say WHICH thing a number describes has to either accept every number
    or reject correct ones, and both are worse than silence.

    `skills-count` only ever verified the marketplace total, which is why
    crew's own bundle count drifted (17 vs the 18 on disk) through two
    correction passes with nothing catching it -- there was no marker for "a
    plugin's own skills/ count" until `plugin-skills:<name>` was added
    alongside it. Mark a plugin's own figure with that type; `skills-count`
    still means the marketplace total and nothing else.

    So: an unmarked number is deliberately not checked, and that silence is the
    design rather than a gap. Marking a claim is how an author opts it in.

    A marker binds to the first line at or after it that matches its claim
    type, within BIND_WINDOW lines. Binding forward rather than requiring the
    same line is what lets a claim inside a fenced code block be marked -- an
    HTML comment inside the fence would render as literal text to every reader,
    so the marker goes above the fence and reaches in. A marker that binds to
    nothing is an error, not a skip: a claim whose target was edited away
    should say so rather than quietly passing forever.

    An unrecognised claim type is also an error. A marker naming a type this
    function does not implement would otherwise collapse into "checked" while
    nothing looked at it, which is the exact defect this check exists to catch.
    """
    skills = str(sum(1 for e in entries if e["source"].startswith("./skills/")))
    versions = {}
    for entry in entries:
        source = entry["source"].lstrip("./")
        manifest = os.path.join(ROOT, source, ".claude-plugin", "plugin.json")
        if os.path.isfile(manifest):
            try:
                versions[entry["name"]] = json.loads(read(manifest))["version"]
            except (ValueError, KeyError):
                pass

    for path in sorted(git("ls-files", "*.md").split()):
        lines = read(os.path.join(ROOT, path)).splitlines()
        fenced = False
        for index, line in enumerate(lines):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            # A marker only counts where it would really be an invisible HTML
            # comment. Inside a fence or a `code span` it renders as literal
            # text to every reader, so it is documentation of the convention --
            # CLAUDE.md describes the syntax -- and not a claim about anything.
            # Scanning it anyway made this checker fail on the very paragraph
            # explaining it, which is how this line came to exist.
            if fenced:
                continue
            for claim in CLAIM_RE.finditer(CODE_SPAN_RE.sub("", line)):
                kind = claim.group(1)
                window = lines[index : index + BIND_WINDOW]

                if kind == "skills-count":
                    found = next(
                        (m for m in (SKILLS_RE.search(w) for w in window) if m), None
                    )
                    if not found:
                        fail(
                            f"{path}:{index + 1}: claim 'skills-count' binds to nothing "
                            f"within {BIND_WINDOW} lines - the number it marked is gone, "
                            "so either restore it or delete the marker"
                        )
                        continue
                    stated = [g for g in found.groups() if g is not None]
                    if any(g != skills for g in stated):
                        fail(
                            f"{path}:{index + 1}: claims {'/'.join(stated)} skills, "
                            f"but marketplace.json registers {skills}"
                        )

                elif kind.startswith("plugin-skills:"):
                    name = kind.split(":", 1)[1]
                    plugin_names = {
                        e["name"] for e in entries if e["source"].startswith("./plugin/")
                    }
                    if name not in plugin_names:
                        fail(
                            f"{path}:{index + 1}: claim names plugin '{name}', which has "
                            "no entry with source ./plugin/ in marketplace.json"
                        )
                        continue
                    found = next(
                        (m for m in (PLUGIN_SKILLS_RE.search(w) for w in window) if m), None
                    )
                    if not found:
                        fail(
                            f"{path}:{index + 1}: claim 'plugin-skills:{name}' binds to "
                            f"nothing within {BIND_WINDOW} lines - the number it marked is "
                            "gone, so either restore it or delete the marker"
                        )
                        continue
                    actual = count_plugin_skills(name)
                    if int(found.group(1)) != actual:
                        fail(
                            f"{path}:{index + 1}: claims {found.group(1)} skills for plugin "
                            f"'{name}', but plugin/{name}/skills/ has {actual}"
                        )

                elif kind.startswith("plugin-version:"):
                    name = kind.split(":", 1)[1]
                    if name not in versions:
                        fail(
                            f"{path}:{index + 1}: claim names plugin '{name}', which has "
                            "no entry with a readable plugin.json in marketplace.json"
                        )
                        continue
                    found = next(
                        (m for m in (VERSION_ROW_RE.match(w) for w in window) if m), None
                    )
                    if not found:
                        fail(
                            f"{path}:{index + 1}: claim 'plugin-version:{name}' binds to "
                            f"no '| **Version** |' row within {BIND_WINDOW} lines"
                        )
                        continue
                    if found.group(1) != versions[name]:
                        fail(
                            f"{path}:{index + 1}: catalog says {name} is "
                            f"{found.group(1)}, but {name}/.claude-plugin/plugin.json "
                            f"says {versions[name]}"
                        )

                else:
                    fail(
                        f"{path}:{index + 1}: unknown claim type '{kind}'. A marker this "
                        "checker does not implement would otherwise read as verified "
                        "while nothing checked it. Implement it or remove the marker."
                    )


POLICY_MARKER = "crew-ignore-policy:list"
POLICY_GITIGNORE = ".gitignore"
# Forward slashes throughout: these are compared against `git ls-files`, which
# emits POSIX separators on every platform. os.path.join would produce
# backslashes here on Windows and the required-source check would report the
# shipped template as missing its marker on Windows only.
POLICY_TEMPLATE = "plugin/crew/skills/crew-setup/SKILL.md"
# The two files that IMPLEMENT the check necessarily contain the marker string
# and example paths, and scanning them makes the checker fail on its own
# docstring. Excluded by path rather than by a cleverer marker rule, because a
# rule that tried to tell a definition from a declaration is one more thing that
# can be wrong.
POLICY_SELF = ("scripts/check-marketplace.py", "scripts/_test/crew-ignore-policy.py")
# CHANGELOG.md is append-only history and must NOT be bound to the current
# policy. It became a marked source by accident - the 0.19.46 entry describes
# this check and names its marker - and it passed only because the policy it
# describes happens to be today's. The next entry to record a CHANGE to the list
# would state the OLD list, correctly, and fail a gate for being accurate about
# the past. History is not a declaration of present policy.
POLICY_HISTORY = ("CHANGELOG.md",)
_UNIGNORE_RE = re.compile(r"!\.crew/([A-Za-z0-9_.*-]+/?)")


def _unignored(text: str) -> set[str]:
    """The `!.crew/<path>` set a file declares, with trailing slashes normalised.

    `!.crew/codemap/` in a .gitignore and `!.crew/codemap` in prose are the same
    claim about the same directory, and a set comparison that failed on the
    slash would fail correct lines.
    """
    return {name.rstrip("/") for name in _UNIGNORE_RE.findall(text)}


def _active_rules(block: str) -> list[str]:
    """The lines of a gitignore block that git actually obeys.

    Comments and blank lines are not rules. Extracting over the raw block made
    three separate mutations invisible, each of which breaks the policy while
    leaving prose that still describes it: commenting out a negation, deleting a
    rule whose explanatory comment above it still names the path, and deleting
    the active `.crew/*` while its comment kept the substring alive. A checker
    that reads a comment as an effective rule is checking the documentation of
    the policy rather than the policy.

    Returned **verbatim**, not stripped. Leading whitespace is significant to
    git and this was got wrong once: `.strip()` made `!.crew/endpoints.json` and
    ` !.crew/endpoints.json` identical, so a genuinely broken exception was
    repaired by the checker and then verified in its repaired form. Measured -
    with the leading space, git leaves `.crew/endpoints.json` IGNORED while
    `.crew/verify.json` on the next line is correctly un-ignored.

    Only a line whose FIRST character is `#` is a comment, which is also
    measured rather than assumed: git treats `  # foo` as a pattern matching a
    file of that name, so stripping before the comment test would drop a line
    git obeys.
    """
    rules = []
    for line in block.replace("\r\n", "\n").split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        rules.append(line)
    return rules


def _git_canonical(rule: str) -> str:
    """A rule reduced to the form git compares, for PRESENCE checks only.

    The probe always sees the original line. This is for asking "is there a
    `.crew/*` rule here", where an exact string match is wrong in one direction
    and `.strip()` is wrong in the other - which is exactly how this check failed
    twice. Round 2: `.strip()` made a leading space vanish, a false PASS on a
    broken rule. Round 3: verbatim comparison rejected `.crew/* `, a false FAIL
    on a correct one. Git treats the two ends differently, so the fix is neither.

    Measured against git, not taken from the documentation:

    - a trailing SPACE is stripped (`.crew/* ` ignores `.crew/config.json`)
    - a trailing TAB is **not** - `.crew/*\\t` matched nothing. The docs say
      "trailing spaces", and they mean spaces. Stripping all trailing whitespace
      here would accept a rule git does not honour.
    - a backslash-escaped trailing space is literal, so `.crew/*\\ ` is a rule
      about a path ending in a space and matched nothing
    - a leading space is significant
    - a trailing `\\r` (a CRLF file) is removed
    """
    if rule.endswith("\r"):
        rule = rule[:-1]
    while rule.endswith(" "):
        backslashes = len(rule[:-1]) - len(rule[:-1].rstrip("\\"))
        if backslashes % 2:
            break        # escaped: the space is part of the pattern
        rule = rule[:-1]
    return rule


def _ignore_behaviour(rules: list[str], exceptions: set[str]) -> list[str]:
    """Ask git what these rules actually do, instead of reading them.

    Every textual assertion here has a mutation that satisfies the text and
    breaks the behaviour - ordering above all, since a `.crew/*` written BELOW
    the negations suppresses all of them while every "is the path present"
    check still passes. So the rules are written into a throwaway repo and
    `git check-ignore` is asked directly. That is the same program that will
    decide this in the real repo, which is the only opinion that counts.

    Returns a list of behaviour descriptions that are wrong, empty when right.

    **Every way this probe can fail to answer is its own finding.** An earlier
    version read any non-zero status as "not ignored", which merged git's 1
    ("checked, not ignored") with its 128 ("fatal, no answer"), and discarded
    the `git init` status entirely. Mocking either produced an empty finding
    list and a clean report - the recurring bug this repo names, an unknown
    wearing the label of a check that happened. `git check-ignore` documents
    0 = ignored, 1 = not ignored, 128 = error; anything that is not 0 or 1 is
    reported as UNVERIFIABLE rather than resolved either way.

    The probe repo is also isolated from this machine, and the two halves of
    that isolation were measured rather than assumed - they are not equally
    load-bearing, and saying so is the point.

    **The environment scrub is load-bearing, demonstrated.** With `GIT_WORK_TREE`
    inherited from the caller, `git init` in the temp directory exits 128
    (`GIT_WORK_TREE ... not allowed without specifying GIT_DIR`) and the probe
    can answer nothing. Stripping `GIT_*` fixes it; that exact pair was run both
    ways.

    **The `-c core.excludesFile=` flags are insurance, and no case was found
    where they change a verdict.** They were added for a global excludes file
    that ignores `.crew/verify.json`, and then the test showed the verdict is the
    same with and without them - because a repository `.gitignore` outranks both
    `core.excludesFile` and `info/exclude` in git's precedence order, so nothing
    at those layers can overturn a rule under test here. Kept because they cost
    nothing, documented as unproven because the alternative is a comment claiming
    a guarantee nobody checked.
    """
    probes = {".crew/config.json": True, ".crew/.approved-production-abc1234": True}
    for name in sorted(exceptions):
        probe = (f".crew/{name}INDEX.md" if name.endswith("/")
                 else f".crew/{name}")
        probes[probe] = False

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "XDG_"))}
    # An empty value is what git documents for "no file", and NOSYSTEM covers
    # /etc/gitconfig, which GIT_CONFIG_SYSTEM alone does not reliably suppress
    # on older git.
    env.update({"GIT_CONFIG_GLOBAL": "", "GIT_CONFIG_SYSTEM": "",
                "GIT_CONFIG_NOSYSTEM": "1", "HOME": "", "USERPROFILE": ""})
    base = ["git", "-c", "core.excludesFile=", "-c", "core.attributesFile="]

    with tempfile.TemporaryDirectory() as tmp:
        started = subprocess.run([*base, "-C", tmp, "init", "-q"],
                                 capture_output=True, text=True,
                                 check=False, env=env)
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "").strip().splitlines()
            return ["UNVERIFIABLE: could not create the probe repository "
                    f"(git init exited {started.returncode}"
                    + (f": {detail[-1]}" if detail else "")
                    + "). Nothing about these rules was checked."]
        with open(os.path.join(tmp, ".gitignore"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(rules) + "\n")
        wrong = []
        for probe, want_ignored in sorted(probes.items()):
            done = subprocess.run([*base, "-C", tmp, "check-ignore", "-q", "--", probe],
                                  capture_output=True, text=True,
                                  check=False, env=env)
            if done.returncode not in (0, 1):
                detail = (done.stderr or "").strip().splitlines()
                wrong.append(
                    f"UNVERIFIABLE: `git check-ignore` exited {done.returncode} for "
                    f"{probe}, which is neither 0 (ignored) nor 1 (not ignored)"
                    + (f" - {detail[-1]}" if detail else "")
                    + ". Whether this path is ignored is UNKNOWN, not clean"
                )
                continue
            is_ignored = done.returncode == 0
            if is_ignored != want_ignored:
                wrong.append(
                    f"{probe} is {'ignored' if is_ignored else 'NOT ignored'} "
                    f"but must be {'ignored' if want_ignored else 'tracked'}"
                )
        return wrong


def _policy_block(relative: str, text: str) -> str | None:
    """The region of a required source whose ORDER is load-bearing.

    `.gitignore` is that region entire: one stanza, read top to bottom by git.
    A markdown source is not - `crew-setup/SKILL.md` is five hundred lines of
    prose around a fenced block, and only the block is what a consuming repo
    copies. Searching the whole document for the last `!.crew/` would let one
    sentence written BELOW §3c - exactly the edit this policy invites - push the
    last negation past `.crew/.approved-*` and fail a correct template. Returns
    None when a markdown source ships no block at all, which is its own failure
    rather than a silent pass.
    """
    if not relative.endswith(".md"):
        return text
    fence = re.search(r"```gitignore\n(.*?)```", text, re.S)
    return fence.group(1) if fence else None


def check_crew_ignore_policy(fail):
    """The `.crew/` un-ignore list is one set, stated in several places at once.

    The policy: `.crew/*` is ignored and a NAMED list is un-ignored. The list
    lives in `.gitignore` (which is what git actually obeys, so it is the
    authority here), is shipped to consuming repos by `crew-setup/SKILL.md` §3c,
    and is restated in prose by several docs. Those had drifted into stating
    three different policies at once - `.gitignore` re-admitted two paths while a
    comment fifty lines below it asserted that "the whole of crew's state ... is
    local to each machine and never committed".

    **A file opts in with the `crew-ignore-policy:list` marker**, the same
    discipline `check_self_claims` uses for numbers: a file that carries it must
    state the WHOLE list, and an unmarked file is deliberately not checked.
    `TODO.md` and `commands/review.md` each mention one or two paths in passing,
    and a checker that read "two mentions" as "a declaration" would fail them for
    being correctly narrow. That silence is asserted by
    `scripts/_test/crew-ignore-policy.py`.

    **Six files carry the marker today**, and naming them is the point - the
    scope of this check is exactly that set, not "every file that mentions
    `.crew/`": `.gitignore` and `crew-setup/SKILL.md` (required, below),
    `CLAUDE.md`, `plugin/crew/README.md`, `crew-setup/phases.md` and
    `crew-verification/SKILL.md`. The codemap under `.crew/codemap/` restates the
    list and is deliberately OUT of scope: it is a derived map with its own
    `anchor:` staleness mechanism, and a generated artefact that fails this gate
    would be fixed by regenerating it, not by editing it. So the list can still
    drift in an unmarked file. What cannot happen is the failure this was written
    for - the authority and the shipped template disagreeing with each other and
    with the docs, silently.

    The marker carries a colon because a bare hyphenated word is also a legal
    FILENAME, and `.github/workflows/marketplace.yml` names this check's own test
    file in a `run:` line. The first version flagged the workflow for declaring a
    policy it was only citing.

    Three ways this could pass while checking nothing, each made its own failure:

    1. **An empty extraction.** A doc that stops using the backticked `!.crew/x`
       form yields an empty set, and empty == empty is a pass. A marked file that
       declares nothing therefore fails.
    2. **Every marker deleted.** `.gitignore` and the shipped template are
       required to carry one, so the check cannot be silenced by removing them.
    3. **A trailing slash on `.crew/`.** `.crew/` stops git descending into the
       directory at all, and nothing can be re-included from a directory git
       never entered - every negation below it silently does nothing while the
       file still reads as though the policy were in force.
    """
    sources: dict[str, set[str]] = {}
    # Carrying the marker and successfully DECLARING a list are two different
    # facts, and collapsing them made the no-fenced-block case report "does not
    # carry the marker" about a file that plainly does - a wrong answer wearing
    # the label of a different check. Tracked separately so each failure says
    # the thing that is actually true.
    marked: set[str] = set()
    for relative in sorted(set(git("ls-files").splitlines()) | {POLICY_GITIGNORE}):
        relative = relative.replace("\\", "/")
        if relative in POLICY_SELF or relative in POLICY_HISTORY:
            continue
        path = os.path.join(ROOT, *relative.split("/"))
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        if POLICY_MARKER not in text:
            continue
        marked.add(relative)
        if relative not in (POLICY_GITIGNORE, POLICY_TEMPLATE):
            # A prose doc states the list in a sentence, so the whole file is
            # the declaration. Order is meaningless in prose and is not checked.
            sources[relative] = _unignored(text)
            continue

        body = _policy_block(relative, text)
        if body is None:
            fail(
                f"{relative}: carries the {POLICY_MARKER} marker but has no ```gitignore "
                "fenced block. The shipped template is the block, not the prose around "
                "it - without one there is nothing for a consuming repo to copy."
            )
            continue
        # ACTIVE rules only, everywhere below. A commented-out negation is not a
        # negation, and reading one as effective is how three mutations that each
        # break the policy produced zero failures.
        rules = _active_rules(body)
        # Presence is asked of the CANONICAL form (git strips a trailing
        # space, keeps a leading one); the probe below still sees the
        # originals, so a rule that is broken rather than merely untidy is
        # caught there instead of being normalised away.
        canonical = [_git_canonical(rule) for rule in rules]
        # Kept with the trailing slash for the behavioural probe (a directory
        # needs a path INSIDE it to probe), and without it for set comparison.
        declared_raw = {name for rule in rules for name in _UNIGNORE_RE.findall(rule)}
        declared = {name.rstrip("/") for name in declared_raw}
        sources[relative] = declared
        if ".crew/" in canonical:
            fail(
                f"{relative}: ignores `.crew/` with a trailing slash. Git refuses to "
                "descend into it, so every `!.crew/...` negation below is silently "
                "dead. Write `.crew/*`."
            )
        if ".crew/*" not in canonical:
            fail(
                f"{relative}: has no active `.crew/*` rule, so there is no base ignore "
                "for the un-ignore list to carve out of. A comment mentioning it is "
                "not a rule."
            )
        if ".crew/.approved-*" not in canonical:
            fail(
                f"{relative}: has no active `.crew/.approved-*` rule. `.crew/*` already "
                "covers the marker, so this is belt-and-braces - but it is the entry a "
                "consuming repo would have to keep if it ever narrowed the base ignore, "
                "and it documents WHY the marker must never be trackable."
            )
        # The behavioural check. It subsumes every ordering question - including
        # a `.crew/*` written BELOW the negations, which suppresses all three
        # while satisfying every "is this line present" assertion above.
        for wrong in _ignore_behaviour(rules, declared_raw):
            fail(f"{relative}: git disagrees with the stated policy - {wrong}.")

    for required in (POLICY_GITIGNORE, POLICY_TEMPLATE):
        if required not in marked:
            fail(
                f"{required} does not carry the `{POLICY_MARKER}` marker. It is a "
                "required source: without it this check has nothing to compare against "
                "and would pass by finding nothing."
            )

    canonical = sources.get(POLICY_GITIGNORE)
    if not canonical:
        fail(
            f"{POLICY_GITIGNORE} declares no `!.crew/...` paths. The un-ignore list "
            "cannot be read, so nothing below was compared - this is a failure, not a "
            "repo with an empty list."
        )
        return

    for relative, declared in sorted(sources.items()):
        if relative == POLICY_GITIGNORE:
            continue
        if not declared:
            fail(
                f"{relative}: carries the `{POLICY_MARKER}` marker but declares no "
                "`!.crew/...` path. An empty declaration compares equal to nothing and "
                "would pass silently."
            )
            continue
        if declared != canonical:
            missing = sorted(canonical - declared)
            extra = sorted(declared - canonical)
            detail = []
            if missing:
                detail.append("omits " + ", ".join(f"!.crew/{n}" for n in missing))
            if extra:
                detail.append("adds " + ", ".join(f"!.crew/{n}" for n in extra))
            fail(
                f"{relative}: states a different `.crew/` un-ignore list than "
                f"{POLICY_GITIGNORE} - {'; '.join(detail)}. The list is one set; change "
                "it in one place and every place that states it has to follow."
            )


def check_hook_commands(entries, fail):
    r"""Every shell-form hook command survives the shell that will actually run it.

    Two failures this catches, both of which shipped in crew and were invisible from the
    repo because they only reproduce on Windows:

    ``${CLAUDE_PLUGIN_ROOT}`` in a ``shell: powershell`` command is substituted as a
    PowerShell *environment reference*, not as a literal path. Inside single quotes
    PowerShell does not expand it, so ``&`` is handed the token verbatim and the hook dies
    with "is not recognized as a name of a cmdlet". The path has to be double-quoted.

    ``& script.ps1`` inside PowerShell's ``-Command`` does not propagate the script's exit
    code - a guard's ``exit 2`` arrives as 1, which Claude Code reports as a non-blocking
    error and lets the command through. Every PowerShell entry has to end by re-raising it
    with ``; exit $LASTEXITCODE``.

    Bash entries get the same double-quote rule, for paths with spaces.
    """
    for entry in entries:
        path = os.path.join(ROOT, entry["source"].lstrip("./"), "hooks", "hooks.json")
        if not os.path.isfile(path):
            continue
        where = f"{entry['name']}: hooks/hooks.json"
        for event, matchers in json.loads(read(path)).get("hooks", {}).items():
            for matcher in matchers:
                for hook in matcher.get("hooks", []):
                    command = hook.get("command", "")
                    if hook.get("type") != "command" or "args" in hook:
                        continue  # exec form: no shell re-parses it, so no quoting bug
                    if "${CLAUDE_PLUGIN_ROOT}" in command and (
                        "\"${CLAUDE_PLUGIN_ROOT}" not in command
                    ):
                        fail(
                            f"{where}: {event} hook does not double-quote "
                            f"${{CLAUDE_PLUGIN_ROOT}} - {command!r}"
                        )
                    if hook.get("shell") == "powershell" and not command.rstrip().endswith(
                        "exit $LASTEXITCODE"
                    ):
                        fail(
                            f"{where}: {event} PowerShell hook does not end with "
                            f"'; exit $LASTEXITCODE', so its exit code is swallowed and a "
                            f"blocking exit 2 blocks nothing - {command!r}"
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
    check_license_consistency(entries, fail)
    check_catalogs(entries, fail)
    check_menu_parity(fail)
    check_group_parity(fail)
    check_docs(entries, fail)
    check_hook_commands(entries, fail)
    check_versions(entries, fail)
    check_self_claims(entries, fail)
    check_crew_ignore_policy(fail)

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
