#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's check_self_claims.

Every case here builds a throwaway git repo in a temp directory and points the
checker's ROOT at it. Nothing touches this repository's own files.

The suite exists because the check it covers is unusual: **most of its value is
in what it does NOT report.** A marker-keyed check that quietly started
flagging every unmarked number would be indistinguishable, in CI, from one that
was working - right up to the point where it failed a correct line and somebody
"fixed" the line. So the silence is asserted as hard as the failures.

The must-block cases are the ones the check was written for; the must-allow
cases are the ones that keep it honest.

Run: python3 scripts/_test/self-claims.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-marketplace.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()

ENTRIES = [
    {"name": f"skill-{n}", "source": f"./skills/skill-{n}", "version": "1.0.0"}
    for n in range(3)
] + [{"name": "widget", "source": "./plugin/widget", "version": "2.5.1"}]
SKILLS = 3  # three ./skills/ entries above


def build(
    tmp: str,
    docs: dict[str, str],
    plugin_version: str = "2.5.1",
    widget_skills: list[str] | None = None,
    widget_commands: list[str] | None = None,
    widget_agents: list[str] | None = None,
    init_git: bool = True,
) -> None:
    """Write a fixture repo: the docs under test plus one plugin manifest.

    ``widget_skills`` names the subdirectories of ``plugin/widget/skills/`` to
    create, each with its own ``SKILL.md`` -- mirroring how `plugin-skills:`
    counts a real plugin's bundle. ``None`` creates no ``skills/`` directory at
    all, which `count_plugin_skills` treats the same as zero.

    ``widget_commands`` names the files (without extension) to create directly
    under ``plugin/widget/commands/`` -- mirroring how `plugin-commands:` and
    `count_plugin_commands` count a real plugin's commands, one file each,
    unlike a skill's subdirectory. ``None`` creates no ``commands/`` directory,
    which `count_plugin_commands` treats the same as zero. Every file created
    this way is tracked (``git add -A`` runs after), which is the count
    `count_plugin_commands` reads -- a case that needs an UNTRACKED file to
    prove the tracked-only rule adds it after ``git add`` instead.

    ``widget_agents`` is the same shape as ``widget_commands``, one file per
    name directly under ``plugin/widget/agents/``, for `count_plugin_agents`.

    ``init_git=False`` skips ``git init``/``git add`` entirely, leaving a
    real directory with real files that git nonetheless cannot answer for -
    the fixture `count_plugin_commands`'s "could not verify" case needs:
    ``git -C <tmp> ls-files`` exits non-zero against a directory that is not
    inside any git working tree, and that must read as "could not count",
    never as a real zero.
    """
    manifest = os.path.join(tmp, "plugin", "widget", ".claude-plugin")
    os.makedirs(manifest, exist_ok=True)
    with open(os.path.join(manifest, "plugin.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": "widget", "version": plugin_version}, fh)

    if widget_skills is not None:
        for skill in widget_skills:
            skill_dir = os.path.join(tmp, "plugin", "widget", "skills", skill)
            os.makedirs(skill_dir, exist_ok=True)
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write(f"# {skill}\n")

    if widget_commands is not None:
        commands_dir = os.path.join(tmp, "plugin", "widget", "commands")
        os.makedirs(commands_dir, exist_ok=True)
        for command in widget_commands:
            command_path = os.path.join(commands_dir, f"{command}.md")
            with open(command_path, "w", encoding="utf-8") as fh:
                fh.write(f"# {command}\n")

    if widget_agents is not None:
        agents_dir = os.path.join(tmp, "plugin", "widget", "agents")
        os.makedirs(agents_dir, exist_ok=True)
        for agent in widget_agents:
            agent_path = os.path.join(agents_dir, f"{agent}.md")
            with open(agent_path, "w", encoding="utf-8") as fh:
                fh.write(f"# {agent}\n")

    for name, body in docs.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)

    if init_git:
        subprocess.run(["git", "-C", tmp, "init", "-q"], check=False, capture_output=True)
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=False, capture_output=True)


def run(
    docs: dict[str, str],
    plugin_version: str = "2.5.1",
    widget_skills: list[str] | None = None,
    widget_commands: list[str] | None = None,
    init_git: bool = True,
) -> list[str]:
    """Run check_self_claims against a fixture and return its failures."""
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, docs, plugin_version, widget_skills, widget_commands, init_git=init_git)
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            problems: list[str] = []
            CHECKER.check_self_claims(ENTRIES, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved


def run_markdown_lines(docs: dict[str, str], crew_files: dict[str, str]) -> list[str]:
    """Run check_self_claims against a fixture carrying `plugin/crew/*.md`
    files, for the `crew-markdown-lines` claim -- the one kind `run()`'s
    fixture (a `plugin/widget` with no `plugin/crew` at all) cannot exercise,
    since `count_crew_markdown_lines` reads `plugin/crew/*.md` by a hardcoded
    path rather than from `ENTRIES`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, docs)
        for rel, body in crew_files.items():
            path = os.path.join(tmp, "plugin", "crew", rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=False, capture_output=True)
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            problems: list[str] = []
            CHECKER.check_self_claims(ENTRIES, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved


def run_description(
    description: str,
    description_claims: dict,
    entries: list[dict] | None = None,
    widget_skills: list[str] | None = None,
    widget_commands: list[str] | None = None,
    init_git: bool = True,
) -> list[str]:
    """Run check_description_claims against a fixture and return its failures.

    ``entries`` defaults to a single ./plugin/widget entry carrying
    ``description``. Pass a custom list to exercise the "not a ./plugin/
    entry" and "no entry at all" cases. ``description_claims`` replaces
    ``CHECKER.DESCRIPTION_CLAIMS`` for the duration of the call -- the whole
    point of the table is that it is opt-in per test, not the repo's own.
    """
    if entries is None:
        entries = [
            {
                "name": "widget",
                "source": "./plugin/widget",
                "description": description,
                "version": "2.5.1",
            }
        ]
    with tempfile.TemporaryDirectory() as tmp:
        build(
            tmp,
            {},
            widget_skills=widget_skills,
            widget_commands=widget_commands,
            init_git=init_git,
        )
        saved_root = CHECKER.ROOT
        saved_claims = CHECKER.DESCRIPTION_CLAIMS
        CHECKER.ROOT = tmp
        CHECKER.DESCRIPTION_CLAIMS = description_claims
        try:
            problems: list[str] = []
            CHECKER.check_description_claims(entries, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved_root
            CHECKER.DESCRIPTION_CLAIMS = saved_claims


def run_count_plugin_commands(files: dict[str, str], tracked: list[str]) -> int:
    """Build plugin/widget/commands/<rel> for each key in ``files`` (content
    is irrelevant), ``git add`` only the paths named in ``tracked``, and
    return ``count_plugin_commands('widget')``.

    Direct unit coverage for the counter itself, separate from the marker and
    description tests above -- proving the three specific flaws named for the
    old ``os.listdir``-based version: it counted an untracked scratch file,
    it counted a non-command file regardless of extension (including a
    dotfile with no ``.md`` extension), and it never looked inside a
    subdirectory at all, so a namespaced command silently did not count.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "plugin", "widget", "commands")
        for rel in files:
            path = os.path.join(base, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("stub\n")
        subprocess.run(["git", "-C", tmp, "init", "-q"], check=False, capture_output=True)
        if tracked:
            targets = [os.path.join("plugin", "widget", "commands", rel) for rel in tracked]
            subprocess.run(
                ["git", "-C", tmp, "add", "--"] + targets, check=False, capture_output=True
            )
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            return CHECKER.count_plugin_commands("widget")
        finally:
            CHECKER.ROOT = saved


def run_count_plugin_commands_no_git() -> int | None:
    """Point ROOT at a REAL directory holding a real plugin/widget/commands/
    full of files, with no ``git init`` run at all, and return
    ``count_plugin_commands('widget')``.

    The FIX this proves: ``git -C <root> ls-files`` exits non-zero against a
    directory that is not inside any git working tree, and `_tracked_files`
    must read that as "could not count" (None), never as the same shape a
    real, checked, empty answer takes (0) - the recurring bug this repo is
    named for, an unknown collapsing into the safe-looking value. If this
    directory happened to sit inside some OUTER git repository (unlikely for
    a fresh tempdir, but not impossible), `git ls-files` would still succeed
    and this assertion would need re-deriving; it has not been an issue in
    practice here.
    """
    tmp = tempfile.mkdtemp()
    try:
        commands_dir = os.path.join(tmp, "plugin", "widget", "commands")
        os.makedirs(commands_dir, exist_ok=True)
        with open(os.path.join(commands_dir, "a.md"), "w", encoding="utf-8") as fh:
            fh.write("# a\n")
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            return CHECKER.count_plugin_commands("widget")
        finally:
            CHECKER.ROOT = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES_COUNT_PLUGIN_COMMANDS: list[tuple[str, dict[str, str], list[str], int]] = [
    (
        "an untracked scratch file is not counted",
        {"a.md": "", "b.md": "", "scratch.md": ""},
        ["a.md", "b.md"],  # scratch.md deliberately left untracked
        2,
    ),
    (
        "a tracked file with no .md extension does not inflate the count",
        {"a.md": "", "README.txt": ""},
        ["a.md", "README.txt"],
        1,
    ),
    (
        "a tracked dotfile with no .md extension is not counted either",
        {"a.md": "", ".DS_Store": ""},
        ["a.md", ".DS_Store"],
        1,
    ),
    (
        "a namespaced command in a subdirectory counts, recursively",
        {"a.md": "", "group/b.md": ""},
        ["a.md", "group/b.md"],
        2,
    ),
    (
        "no commands/ directory at all counts as zero",
        {},
        [],
        0,
    ),
    (
        "a tracked file with a non-ASCII name is still counted - "
        "core.quotepath defaults on, which makes git WRITE the name "
        "octal-quoted ('caf\\303\\251.md') in newline-separated output, and "
        "str.endswith('.md') on that quoted form is false; -z with "
        "core.quotepath=off sidesteps it",
        {"a.md": "", "café.md": ""},
        ["a.md", "café.md"],
        2,
    ),
]


def run_catalog(
    sh_label: str,
    ps1_label: str,
    kinds: tuple[str, ...],
    name: str = "widget",
    widget_commands: list[str] | None = None,
    widget_agents: list[str] | None = None,
    entries: list[dict] | None = None,
    init_git: bool = True,
) -> list[str]:
    """Run check_catalog_claims against a fixture pair of install-script-
    shaped files and return its failures.

    Each fixture file carries just enough real shape - a ``PLUGIN_NAME=(...)``
    bash array for the ``.sh`` side, a ``$script:PluginCatalog = @(...)``
    PowerShell array for the ``.ps1`` side - for `_catalog_name_text` to find
    the same label text it would find in the real scripts, without needing
    the whole multi-thousand-line file. ``CHECKER.SH``/``CHECKER.PS1`` are
    patched for the duration of the call, and ``CATALOG_CLAIMS`` is built
    fresh from the fixture's own paths - the repo's real table is never
    touched.
    """
    if entries is None:
        entries = [{"name": name, "source": f"./plugin/{name}", "version": "2.5.1"}]
    with tempfile.TemporaryDirectory() as tmp:
        build(
            tmp,
            {},
            widget_commands=widget_commands,
            widget_agents=widget_agents,
            init_git=init_git,
        )
        sh_path = os.path.join(tmp, "install.sh")
        ps1_path = os.path.join(tmp, "install.ps1")
        with open(sh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f'PLUGIN_NAME=(\n  "{sh_label}"\n)\n')
        with open(ps1_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(
                "$script:PluginCatalog = @(\n"
                f"    [pscustomobject]@{{ Name = '{ps1_label}' }}\n)\n"
            )
        saved_root = CHECKER.ROOT
        saved_sh = CHECKER.SH
        saved_ps1 = CHECKER.PS1
        saved_claims = CHECKER.CATALOG_CLAIMS
        CHECKER.ROOT = tmp
        CHECKER.SH = sh_path
        CHECKER.PS1 = ps1_path
        CHECKER.CATALOG_CLAIMS = (
            (sh_path, name, kinds),
            (ps1_path, name, kinds),
        )
        try:
            problems: list[str] = []
            CHECKER.check_catalog_claims(entries, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved_root
            CHECKER.SH = saved_sh
            CHECKER.PS1 = saved_ps1
            CHECKER.CATALOG_CLAIMS = saved_claims


def run_catalog_multi(
    sh_rows: list[str],
    ps1_rows: list[str],
    kinds: tuple[str, ...],
    name: str = "widget",
    widget_commands: list[str] | None = None,
    widget_agents: list[str] | None = None,
    entries: list[dict] | None = None,
) -> list[str]:
    """Same as run_catalog, but for a fixture with MORE THAN ONE catalog row
    per file.

    A single-row fixture cannot exercise the scoping bug this exists to
    catch: with only one row, "match the whole file" and "match just the
    requested row" produce identical text, so a regression that stops
    `_catalog_name_text` scoping to one row - e.g. replacing it with a
    function that just returns the whole file - goes completely unnoticed
    against a single-row fixture. `run_catalog`'s CASES_CATALOG cases are all
    single-row for that reason NOT to be a scoping proof; the multi-row cases
    below (CASES_CATALOG_SCOPING) are.
    """
    if entries is None:
        entries = [{"name": name, "source": f"./plugin/{name}", "version": "2.5.1"}]
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, {}, widget_commands=widget_commands, widget_agents=widget_agents)
        sh_path = os.path.join(tmp, "install.sh")
        ps1_path = os.path.join(tmp, "install.ps1")
        sh_body = "\n".join(f'  "{row}"' for row in sh_rows)
        with open(sh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"PLUGIN_NAME=(\n{sh_body}\n)\n")
        ps1_body = "\n".join(
            f"    [pscustomobject]@{{ Name = '{row}' }}" for row in ps1_rows
        )
        with open(ps1_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"$script:PluginCatalog = @(\n{ps1_body}\n)\n")
        saved_root = CHECKER.ROOT
        saved_sh = CHECKER.SH
        saved_ps1 = CHECKER.PS1
        saved_claims = CHECKER.CATALOG_CLAIMS
        CHECKER.ROOT = tmp
        CHECKER.SH = sh_path
        CHECKER.PS1 = ps1_path
        CHECKER.CATALOG_CLAIMS = ((sh_path, name, kinds), (ps1_path, name, kinds))
        try:
            problems: list[str] = []
            CHECKER.check_catalog_claims(entries, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved_root
            CHECKER.SH = saved_sh
            CHECKER.PS1 = saved_ps1
            CHECKER.CATALOG_CLAIMS = saved_claims


# Each row pair is (sh row text, ps1 row text) but kept identical throughout
# below, same convention as CASES_CATALOG. Every case here has MORE THAN ONE
# row in the fixture file - see run_catalog_multi's docstring for why that is
# the point. Expected counts are x2 for the same reason as CASES_CATALOG:
# both files carry the same rows, so a shared defect fails once per file.
CASES_CATALOG_SCOPING: list[tuple[str, dict, int, str]] = [
    (
        "two unrelated plugins in one file - the check must isolate widget's "
        "own row and not see alpha's count at all",
        {
            "sh_rows": [
                "alpha    - Something else: 7 commands",
                "widget    - Mine: 999 commands",
            ],
            "kinds": ("commands",),
            "widget_commands": ["x", "y", "z"],
        },
        2,
        "claims 999 commands, but plugin/widget/commands/ has 3",
    ),
    (
        "a name that is a suffix of another plugin's key (widget vs "
        "superwidget) - the reviewer's exact reproduction",
        {
            "sh_rows": [
                "superwidget    - Other: 3 commands",
                "widget    - Mine: 999 commands",
            ],
            "kinds": ("commands",),
            "widget_commands": ["x", "y", "z"],
        },
        2,
        "claims 999 commands, but plugin/widget/commands/ has 3",
    ),
    (
        "a duplicate label - the same key appears twice in one file, which "
        "must be reported as ambiguous rather than silently taking the first",
        {
            "sh_rows": [
                "widget    - First copy: 999 commands",
                "widget    - Second copy: 999 commands",
            ],
            "kinds": ("commands",),
            "widget_commands": ["x", "y", "z"],
        },
        2,
        "matches 2 catalog rows, expected exactly one",
    ),
]


# Deliberately unequal, mirroring the DESCRIPTION_CLAIMS lesson above: 4
# agents, 3 commands, so a kind swapped in CATALOG_CLAIM_KINDS disagrees
# rather than passing by coincidence.
CATALOG_AGENTS_4 = ["m1", "m2", "m3", "m4"]
CATALOG_COMMANDS_3 = ["x", "y", "z"]

# The .sh and .ps1 labels are IDENTICAL text below, deliberately, the same
# way the real crew rows are (CLAUDE.md: the two install scripts are a
# matched pair, same text). CATALOG_CLAIMS lists both files, so a defect
# present in both labels is reported ONCE PER FILE - two problems, not one -
# and every "must block" count below is 2 for that reason, not 1.
CASES_CATALOG: list[tuple[str, dict, int, str]] = [
    # --- must block ------------------------------------------------------
    (
        "a catalog label's commands count disagrees with the filesystem "
        "(fails in both files - identical label text, same as the real pair)",
        {
            "sh_label": "widget    - Does things: 4 agents, 9 commands, no hooks",
            "ps1_label": "widget    - Does things: 4 agents, 9 commands, no hooks",
            "kinds": ("agents", "commands"),
            "widget_agents": CATALOG_AGENTS_4,
            "widget_commands": CATALOG_COMMANDS_3,
        },
        2,
        "claims 9 commands",
    ),
    (
        "a catalog label's agents count disagrees with the filesystem "
        "(fails in both files)",
        {
            "sh_label": "widget    - Does things: 9 agents, 3 commands, no hooks",
            "ps1_label": "widget    - Does things: 9 agents, 3 commands, no hooks",
            "kinds": ("agents", "commands"),
            "widget_agents": CATALOG_AGENTS_4,
            "widget_commands": CATALOG_COMMANDS_3,
        },
        2,
        "claims 9 agents",
    ),
    (
        "a missing phrase for a listed kind (fails in both files)",
        {
            "sh_label": "widget    - Does things, no counts stated",
            "ps1_label": "widget    - Does things, no counts stated",
            "kinds": ("commands",),
            "widget_agents": None,
            "widget_commands": CATALOG_COMMANDS_3,
        },
        2,
        "no 'commands' phrase",
    ),
    (
        "the phrase appears more than once in a label (fails in both files)",
        {
            "sh_label": "widget    - 3 commands today, was 9 commands last week",
            "ps1_label": "widget    - 3 commands today, was 9 commands last week",
            "kinds": ("commands",),
            "widget_agents": None,
            "widget_commands": CATALOG_COMMANDS_3,
        },
        2,
        "2 'commands' phrases",
    ),
    (
        "an unknown kind in CATALOG_CLAIMS fails loudly, in both files - "
        "'hooks' is deliberately not in CATALOG_CLAIM_KINDS",
        {
            "sh_label": "widget    - 3 commands, no hooks",
            "ps1_label": "widget    - 3 commands, no hooks",
            "kinds": ("hooks",),
            "widget_agents": None,
            "widget_commands": None,
        },
        2,
        "unknown kind 'hooks'",
    ),
    (
        "CATALOG_CLAIMS naming a plugin with no marketplace entry at all "
        "(fails in both files)",
        {
            "sh_label": "ghost    - 3 commands",
            "ps1_label": "ghost    - 3 commands",
            "kinds": ("commands",),
            "widget_agents": None,
            "widget_commands": None,
            "name": "ghost",
            "entries": [{"name": "widget", "source": "./plugin/widget", "version": "1"}],
        },
        2,
        "no entry",
    ),
    (
        "CATALOG_CLAIMS naming an existing ./skills/ entry, not ./plugin/ "
        "(fails in both files)",
        {
            "sh_label": "widget    - 3 commands",
            "ps1_label": "widget    - 3 commands",
            "kinds": ("commands",),
            "widget_agents": None,
            "widget_commands": CATALOG_COMMANDS_3,
            "entries": [{"name": "widget", "source": "./skills/widget", "version": "1"}],
        },
        2,
        "not ./plugin/",
    ),
    # --- must allow ------------------------------------------------------
    (
        "a catalog label whose agents and commands counts both match disk "
        "(4 agents, 3 commands - deliberately unequal, see CATALOG_AGENTS_4)",
        {
            "sh_label": "widget    - Virtual dev team: 4 agents, 3 commands, no hooks",
            "ps1_label": "widget    - Virtual dev team: 4 agents, 3 commands, no hooks",
            "kinds": ("agents", "commands"),
            "widget_agents": CATALOG_AGENTS_4,
            "widget_commands": CATALOG_COMMANDS_3,
        },
        0,
        "",
    ),
]


# Every check function main() calls, read directly from its body -
# scripts/check-marketplace.py:main(). Kept as an explicit list rather than
# introspected so a reviewer sees at a glance that it is main()'s own call
# order, not a guess.
ALL_CHECK_FUNCS = [
    "check_registration",
    "check_skill_manifests",
    "check_plugin_manifests",
    "check_argument_hint_frontmatter",
    "check_license_consistency",
    "check_catalogs",
    "check_menu_parity",
    "check_group_parity",
    "check_docs",
    "check_hook_commands",
    "check_command_backtick_spans",
    "check_versions",
    "check_self_claims",
    "check_description_claims",
    "check_catalog_claims",
    "check_crew_ignore_policy",
]


def _stub_all_except(keep: str) -> dict:
    """Replace every check function in ALL_CHECK_FUNCS except ``keep`` with a
    no-op, and return the originals so the caller can restore them."""
    saved = {}
    for fname in ALL_CHECK_FUNCS:
        if fname != keep:
            saved[fname] = getattr(CHECKER, fname)
            setattr(CHECKER, fname, lambda *a, **k: None)
    return saved


def _unstub(saved: dict) -> None:
    for fname, func in saved.items():
        setattr(CHECKER, fname, func)


def run_main_description_wiring(correct: bool) -> int:
    """Call the real, unmodified CHECKER.main() against a minimal fixture,
    with every check EXCEPT check_description_claims stubbed to a no-op.

    A direct unit test that calls check_description_claims itself (the
    CASES_DESCRIPTION cases above) cannot detect main() simply not calling
    it any more - the function would still be correct, just unreachable.
    This calls main() itself, the same object ``python3
    scripts/check-marketplace.py`` runs, and checks its return code. With
    ``correct=False`` a wrong count must make main() return non-zero; with
    ``correct=True`` a right count must make it return zero - proving the
    non-zero result above is really coming from the check's own comparison
    and not from some unrelated always-fail state.
    """
    tmp = tempfile.mkdtemp()
    try:
        build(tmp, {}, widget_skills=WIDGET_SKILLS_2, widget_commands=WIDGET_COMMANDS_3)
        os.makedirs(os.path.join(tmp, "skills"), exist_ok=True)
        marketplace_dir = os.path.join(tmp, ".claude-plugin")
        os.makedirs(marketplace_dir, exist_ok=True)
        stated = 3 if correct else 999
        entries = [
            {
                "name": "widget",
                "source": "./plugin/widget",
                "description": f"30 agents, {stated} slash commands, 2 bundled skills",
                "version": "2.5.1",
            }
        ]
        with open(
            os.path.join(marketplace_dir, "marketplace.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump({"plugins": entries}, fh)

        saved_root = CHECKER.ROOT
        saved_marketplace = CHECKER.MARKETPLACE
        saved_claims = CHECKER.DESCRIPTION_CLAIMS
        saved_funcs = _stub_all_except("check_description_claims")
        CHECKER.ROOT = tmp
        CHECKER.MARKETPLACE = os.path.join(marketplace_dir, "marketplace.json")
        CHECKER.DESCRIPTION_CLAIMS = {"widget": ("commands", "skills")}
        try:
            return CHECKER.main()
        finally:
            CHECKER.ROOT = saved_root
            CHECKER.MARKETPLACE = saved_marketplace
            CHECKER.DESCRIPTION_CLAIMS = saved_claims
            _unstub(saved_funcs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_main_catalog_wiring(correct: bool) -> int:
    """The same proof as run_main_description_wiring, for check_catalog_claims
    - the other check added in this change, with the identical "main() might
    just stop calling it" risk.
    """
    tmp = tempfile.mkdtemp()
    try:
        build(tmp, {}, widget_commands=CATALOG_COMMANDS_3, widget_agents=CATALOG_AGENTS_4)
        os.makedirs(os.path.join(tmp, "skills"), exist_ok=True)
        marketplace_dir = os.path.join(tmp, ".claude-plugin")
        os.makedirs(marketplace_dir, exist_ok=True)
        entries = [{"name": "widget", "source": "./plugin/widget", "version": "2.5.1"}]
        with open(
            os.path.join(marketplace_dir, "marketplace.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump({"plugins": entries}, fh)

        stated = 3 if correct else 999
        label = f"widget    - Virtual dev team: 4 agents, {stated} commands, no hooks"
        sh_path = os.path.join(tmp, "install.sh")
        ps1_path = os.path.join(tmp, "install.ps1")
        with open(sh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f'PLUGIN_NAME=(\n  "{label}"\n)\n')
        with open(ps1_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(
                "$script:PluginCatalog = @(\n"
                f"    [pscustomobject]@{{ Name = '{label}' }}\n)\n"
            )

        saved_root = CHECKER.ROOT
        saved_marketplace = CHECKER.MARKETPLACE
        saved_sh = CHECKER.SH
        saved_ps1 = CHECKER.PS1
        saved_catalog_claims = CHECKER.CATALOG_CLAIMS
        saved_funcs = _stub_all_except("check_catalog_claims")
        CHECKER.ROOT = tmp
        CHECKER.MARKETPLACE = os.path.join(marketplace_dir, "marketplace.json")
        CHECKER.SH = sh_path
        CHECKER.PS1 = ps1_path
        CHECKER.CATALOG_CLAIMS = (
            (sh_path, "widget", ("agents", "commands")),
            (ps1_path, "widget", ("agents", "commands")),
        )
        try:
            return CHECKER.main()
        finally:
            CHECKER.ROOT = saved_root
            CHECKER.MARKETPLACE = saved_marketplace
            CHECKER.SH = saved_sh
            CHECKER.PS1 = saved_ps1
            CHECKER.CATALOG_CLAIMS = saved_catalog_claims
            _unstub(saved_funcs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES: list[tuple[str, dict, int, str]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked number that disagrees with marketplace.json",
        {"README.md": "The repo ships 9 skills<!-- claim: skills-count --> today.\n"},
        1,
        "registers 3",
    ),
    (
        "a marked 'N of N' where only one half was updated",
        {"README.md": "<!-- claim: skills-count -->\n```\n  [x] 3 of 9 skills\n```\n"},
        1,
        "registers 3",
    ),
    (
        "a marked catalog version that disagrees with plugin.json",
        {"P.md": "<!-- claim: plugin-version:widget -->\n| **Version** | 1.0.0 |\n"},
        1,
        "plugin.json",
    ),
    (
        "a claim type the checker does not implement",
        {"README.md": "<!-- claim: hook-count -->\nsomething\n"},
        1,
        "unknown claim type",
    ),
    (
        "a claim naming a plugin that is not registered",
        {"P.md": "<!-- claim: plugin-version:ghost -->\n| **Version** | 1.0.0 |\n"},
        1,
        "no entry",
    ),
    (
        "a marker whose target was edited away binds to nothing",
        {"README.md": "<!-- claim: skills-count -->\n" + "filler\n" * 20},
        1,
        "binds to nothing",
    ),
    (
        "a marker further from its target than the binding window",
        {
            "README.md": "<!-- claim: skills-count -->\n"
            + "filler\n" * 15
            + "3 skills\n"
        },
        1,
        "binds to nothing",
    ),
    # --- must allow ------------------------------------------------------
    (
        "a marked number that is correct",
        {"README.md": "The repo ships 3 skills<!-- claim: skills-count --> today.\n"},
        0,
        "",
    ),
    (
        "a marked 'N of N' where both halves are correct",
        {"README.md": "<!-- claim: skills-count -->\n```\n  [x] 3 of 3 skills\n```\n"},
        0,
        "",
    ),
    (
        "a marked catalog version that matches plugin.json",
        {"P.md": "<!-- claim: plugin-version:widget -->\n| **Version** | 2.5.1 |\n"},
        0,
        "",
    ),
    (
        "a marker reaching into a fenced block from above it",
        {"README.md": "intro\n\n<!-- claim: skills-count -->\n```\n  3 skills\n```\n"},
        0,
        "",
    ),
    # --- the silence, asserted ------------------------------------------
    # Each of these is a WRONG number with no marker. The check must say
    # nothing. If one of them ever fails, the check has started guessing which
    # numbers are claims, and it cannot do that correctly - `17 skills` is a
    # true sentence about crew's bundle and a false one about the marketplace.
    (
        "an unmarked wrong number is not the checker's business",
        {"README.md": "The repo ships 9 skills today.\n"},
        0,
        "",
    ),
    (
        "an unmarked wrong number beside a marked correct one",
        {
            "README.md": "crew bundles 17 skills.\n"
            "The repo ships 3 skills<!-- claim: skills-count --> today.\n"
        },
        0,
        "",
    ),
    (
        "an unmarked catalog version row is not checked",
        {"P.md": "| **Version** | 0.0.1 |\n"},
        0,
        "",
    ),
    (
        "a file with no markers at all produces nothing",
        {"README.md": "28 skills, 50 agents, 4 plugins, and 7 of 4 marketplaces.\n"},
        0,
        "",
    ),
    # --- documenting the convention is not making a claim -----------------
    # CLAUDE.md explains this syntax, and the first version of the check read
    # that explanation as nine live claims and failed on the paragraph
    # describing itself. A marker only counts where it would really be an
    # invisible HTML comment.
    (
        "a marker inside a code span is documentation, not a claim",
        {
            "CLAUDE.md": "Write `<!-- claim: skills-count -->` beside it. "
            "`17 skills` is true of crew's bundle and false of the marketplace.\n"
        },
        0,
        "",
    ),
    (
        "a marker inside a fenced block is not a claim either",
        {"README.md": "```\n<!-- claim: skills-count -->\n9 skills\n```\n"},
        0,
        "",
    ),
    (
        "a real marker still works on a line that also has a code span",
        {"README.md": "all 3 skills<!-- claim: skills-count --> in `skills/`\n"},
        0,
        "",
    ),
    (
        "a real marker on a line with a code span still catches a wrong number",
        {"README.md": "all 9 skills<!-- claim: skills-count --> in `skills/`\n"},
        1,
        "registers 3",
    ),
]

# `plugin-skills:<name>` -- a plugin's OWN bundled-skill count, as opposed to
# `skills-count`'s marketplace total. Each case names how many SKILL.md-bearing
# directories to create under plugin/widget/skills/, distinct from CASES above
# because this marker type reads the filesystem, not marketplace.json.
CASES_PLUGIN_SKILLS: list[tuple[str, dict, int, str, list[str] | None]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked plugin-skills count that disagrees with the filesystem",
        {"P.md": "widget bundles 5 skills<!-- claim: plugin-skills:widget -->.\n"},
        1,
        "plugin/widget/skills/ has 2",
        ["alpha", "beta"],
    ),
    (
        "a plugin-skills claim naming a plugin with no ./plugin/ entry",
        {"P.md": "<!-- claim: plugin-skills:ghost -->\n5 skills\n"},
        1,
        "no entry",
        None,
    ),
    (
        "a plugin-skills marker whose target was edited away binds to nothing",
        {"P.md": "<!-- claim: plugin-skills:widget -->\n" + "filler\n" * 20},
        1,
        "binds to nothing",
        ["alpha"],
    ),
    # --- must allow ------------------------------------------------------
    (
        "a marked plugin-skills count that matches the filesystem",
        {"P.md": "widget bundles 2 skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
    (
        "a marked plugin-skills count of zero, no skills/ directory at all",
        {"P.md": "widget bundles 0 skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        None,
    ),
    (
        "'bundled skills' phrasing, not just 'skills', still binds",
        {"P.md": "54 agents, 2 bundled skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
    (
        "singular 'skill' still binds",
        {"P.md": "1 skill<!-- claim: plugin-skills:widget -->, no agents.\n"},
        0,
        "",
        ["alpha"],
    ),
    # --- the silence, asserted ------------------------------------------
    (
        "an unmarked plugin skill count is not the checker's business",
        {"P.md": "widget bundles 5 skills, actually 2.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
]

# `plugin-commands:<name>` -- a plugin's OWN slash-command count, added
# alongside `plugin-skills:<name>` for symmetry. Each case names how many
# files to create directly under plugin/widget/commands/, mirroring
# `count_plugin_commands`.
CASES_PLUGIN_COMMANDS: list[tuple[str, dict, int, str, list[str] | None]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked plugin-commands count that disagrees with the filesystem",
        {"P.md": "widget bundles 5 commands<!-- claim: plugin-commands:widget -->.\n"},
        1,
        "plugin/widget/commands/ has 2",
        ["alpha", "beta"],
    ),
    (
        "a plugin-commands claim naming a plugin with no ./plugin/ entry",
        {"P.md": "<!-- claim: plugin-commands:ghost -->\n5 commands\n"},
        1,
        "no entry",
        None,
    ),
    (
        "a plugin-commands claim naming an existing ./skills/ entry, not a "
        "./plugin/ one - dropping the ./plugin/ source filter (e.g. checking "
        "against every entry's name instead of just plugin ones) would let "
        "this through, since 'skill-0' really is registered",
        {"P.md": "<!-- claim: plugin-commands:skill-0 -->\n5 commands\n"},
        1,
        "no entry",
        None,
    ),
    (
        "a plugin-commands marker whose target was edited away binds to nothing",
        {"P.md": "<!-- claim: plugin-commands:widget -->\n" + "filler\n" * 20},
        1,
        "binds to nothing",
        ["alpha"],
    ),
    # --- must allow ------------------------------------------------------
    (
        "a marked plugin-commands count that matches the filesystem",
        {"P.md": "widget bundles 2 commands<!-- claim: plugin-commands:widget -->.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
    (
        "a marked plugin-commands count of zero, no commands/ directory at all",
        {"P.md": "widget bundles 0 commands<!-- claim: plugin-commands:widget -->.\n"},
        0,
        "",
        None,
    ),
    (
        "'slash commands' phrasing, not just 'commands', still binds",
        {"P.md": "28 slash commands<!-- claim: plugin-commands:widget -->, no agents.\n"},
        0,
        "",
        [f"c{n}" for n in range(28)],
    ),
    (
        "singular 'command' still binds",
        {"P.md": "1 command<!-- claim: plugin-commands:widget -->, no agents.\n"},
        0,
        "",
        ["only"],
    ),
    # --- the silence, asserted ------------------------------------------
    (
        "an unmarked plugin command count is not the checker's business",
        {"P.md": "widget bundles 5 commands, actually 2.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
]

# check_description_claims -- the JSON `description` string counts, keyed on
# DESCRIPTION_CLAIMS rather than a marker, because a JSON string cannot carry
# an HTML comment. Each case supplies its own description_claims table so the
# repo's real table is never touched by these fixtures.

# Deliberately UNEQUAL disk counts throughout the pairs below - 3 commands,
# 2 skills - not the 2-and-2 this suite shipped with the first time. Equal
# counts on both sides of a pair mean swapping count_plugin_commands and
# count_plugin_skills in DESCRIPTION_CLAIM_KINDS, or replacing either with
# `lambda n: 2`, produces the same actual value either way and the suite
# cannot tell. Unequal counts make a swapped counter disagree with the
# stated number it is supposed to match. See the sabotage note in the
# provenance this suite's report carries.
WIDGET_COMMANDS_3 = ["a", "b", "c"]
WIDGET_SKILLS_2 = ["x", "y"]

CASES_DESCRIPTION: list[tuple[str, dict, int, str]] = [
    # --- must block ------------------------------------------------------
    (
        "a description command count that disagrees with the filesystem",
        {
            "description": "30 agents, 5 slash commands, 2 bundled skills",
            "description_claims": {"widget": ("commands", "skills")},
            "widget_commands": WIDGET_COMMANDS_3,
            "widget_skills": WIDGET_SKILLS_2,
        },
        1,
        "claims 5 slash commands",
    ),
    (
        "a description skills count that disagrees with the filesystem",
        {
            "description": "30 agents, 3 slash commands, 5 bundled skills",
            "description_claims": {"widget": ("commands", "skills")},
            "widget_commands": WIDGET_COMMANDS_3,
            "widget_skills": WIDGET_SKILLS_2,
        },
        1,
        "claims 5 bundled skills",
    ),
    (
        "a bare 'N commands' phrase (no 'slash', and no word between the "
        "number and 'commands') does not satisfy the commands claim, even "
        "though N happens to equal the disk count - DESCRIPTION_COMMANDS_RE "
        "is pinned to the literal phrase 'slash commands', not the looser "
        "'(?:slash )?commands' the .md marker regex uses, and this is what "
        "tells a real claim from a decoy. Loosening the regex to "
        "'(?:slash\\s+)?commands\\b' makes this pass (0 problems) instead "
        "of failing - sabotage-tested",
        {
            "description": "widget's setup runs 3 commands before startup",
            "description_claims": {"widget": ("commands",)},
            "widget_commands": WIDGET_COMMANDS_3,
            "widget_skills": None,
        },
        1,
        "no 'slash commands' phrase",
    ),
    (
        "a missing phrase for a listed kind",
        {
            "description": "30 agents, no command count stated here",
            "description_claims": {"widget": ("commands",)},
            "widget_commands": ["a", "b"],
            "widget_skills": None,
        },
        1,
        "no 'slash commands' phrase",
    ),
    (
        "the phrase appears more than once",
        {
            "description": "3 slash commands today, was 5 slash commands last week",
            "description_claims": {"widget": ("commands",)},
            "widget_commands": ["a", "b", "c"],
            "widget_skills": None,
        },
        1,
        "2 'slash commands' phrases",
    ),
    (
        "an unknown kind in the table fails loudly",
        {
            "description": "30 agents, 2 slash commands",
            "description_claims": {"widget": ("agents",)},
            "widget_commands": ["a", "b"],
            "widget_skills": None,
        },
        1,
        "unknown kind 'agents'",
    ),
    (
        "a listed plugin with no marketplace entry at all",
        {
            "description": "irrelevant",
            "description_claims": {"ghost": ("commands",)},
            "widget_commands": None,
            "widget_skills": None,
        },
        1,
        "no entry",
    ),
    (
        "a listed entry whose source is not ./plugin/",
        {
            "description": "irrelevant",
            "description_claims": {"widget": ("commands",)},
            "widget_commands": None,
            "widget_skills": None,
            "entries": [
                {
                    "name": "widget",
                    "source": "./skills/widget",
                    "description": "30 agents, 2 slash commands",
                    "version": "2.5.1",
                }
            ],
        },
        1,
        "not ./plugin/",
    ),
    # --- must allow ------------------------------------------------------
    (
        "a description count that matches the filesystem for both kinds "
        "(3 commands, 2 skills - deliberately unequal; see WIDGET_COMMANDS_3)",
        {
            "description": "30 agents, 3 slash commands, 2 bundled skills",
            "description_claims": {"widget": ("commands", "skills")},
            "widget_commands": WIDGET_COMMANDS_3,
            "widget_skills": WIDGET_SKILLS_2,
        },
        0,
        "",
    ),
    # --- the silence, asserted ------------------------------------------
    (
        "a plugin not listed in DESCRIPTION_CLAIMS is not checked, however "
        "wrong its description looks",
        {
            "description": "30 agents, 999 slash commands, 999 bundled skills",
            "description_claims": {},
            "widget_commands": WIDGET_COMMANDS_3,
            "widget_skills": WIDGET_SKILLS_2,
        },
        0,
        "",
    ),
]


# `crew-markdown-lines` -- the plugin/crew/*.md total, distinct from
# `skills-count` (marketplace.json) and `plugin-skills:`/`plugin-commands:`
# (filesystem counts scoped by ENTRIES): this one reads `plugin/crew/*.md`
# directly, so its fixture needs real files under that path, not `ENTRIES`.
CASES_MARKDOWN_LINES: list[tuple[str, dict, dict, int, str]] = [
    (
        "a marked total that disagrees with plugin/crew/*.md",
        {"README.md": "<!-- claim: crew-markdown-lines -->\n9 lines\n"},
        {"a.md": "one\ntwo\nthree\n"},
        1,
        "currently totals 3",
    ),
    (
        "a marked total that is correct",
        {"README.md": "<!-- claim: crew-markdown-lines -->\n3 lines\n"},
        {"a.md": "one\ntwo\nthree\n"},
        0,
        "",
    ),
    (
        "a file with no trailing newline is not undercounted by one",
        {"README.md": "<!-- claim: crew-markdown-lines -->\n2 lines\n"},
        {"a.md": "one\ntwo"},  # no trailing newline -- still 2 lines
        0,
        "",
    ),
    (
        "an unmarked wrong total is not the checker's business",
        {"README.md": "plugin/crew is 9 lines today.\n"},
        {"a.md": "one\ntwo\nthree\n"},
        0,
        "",
    ),
]


def main() -> int:
    passed = failed = 0
    for name, docs, expected, needle in CASES:
        problems = run(docs)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, docs, crew_files, expected, needle in CASES_MARKDOWN_LINES:
        problems = run_markdown_lines(docs, crew_files)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, docs, expected, needle, widget_skills in CASES_PLUGIN_SKILLS:
        problems = run(docs, widget_skills=widget_skills)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, docs, expected, needle, widget_commands in CASES_PLUGIN_COMMANDS:
        problems = run(docs, widget_commands=widget_commands)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, kwargs, expected, needle in CASES_DESCRIPTION:
        problems = run_description(
            kwargs["description"],
            kwargs["description_claims"],
            entries=kwargs.get("entries"),
            widget_skills=kwargs.get("widget_skills"),
            widget_commands=kwargs.get("widget_commands"),
        )
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, files, tracked, expected_count in CASES_COUNT_PLUGIN_COMMANDS:
        actual = run_count_plugin_commands(files, tracked)
        if actual == expected_count:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected count_plugin_commands == {expected_count}, got {actual}")

    for name, kwargs, expected, needle in CASES_CATALOG:
        problems = run_catalog(
            kwargs["sh_label"],
            kwargs["ps1_label"],
            kwargs["kinds"],
            name=kwargs.get("name", "widget"),
            widget_commands=kwargs.get("widget_commands"),
            widget_agents=kwargs.get("widget_agents"),
            entries=kwargs.get("entries"),
        )
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, kwargs, expected, needle in CASES_CATALOG_SCOPING:
        problems = run_catalog_multi(
            kwargs["sh_rows"],
            kwargs.get("ps1_rows", kwargs["sh_rows"]),
            kwargs["kinds"],
            name=kwargs.get("name", "widget"),
            widget_commands=kwargs.get("widget_commands"),
            widget_agents=kwargs.get("widget_agents"),
            entries=kwargs.get("entries"),
        )
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    # The FIX: "could not count" (git could not answer) must be its own
    # outcome, never silently read as 0. First a direct unit assertion on
    # the counter itself, then one proof per call site that the "could not
    # verify" FAIL actually surfaces through the check, not just the counter.
    no_git_actual = run_count_plugin_commands_no_git()
    if no_git_actual is None:
        passed += 1
        print("  ok   count_plugin_commands returns None, not 0, when ROOT is not a git working tree")
    else:
        failed += 1
        print("  FAIL count_plugin_commands returns None, not 0, when ROOT is not a git working tree")
        print(f"       got {no_git_actual!r}")

    # No propagation proof for the plugin-commands: .md marker specifically -
    # check_self_claims discovers WHICH .md files to scan with its own
    # `git("ls-files", "*.md")` call (scripts/check-marketplace.py, top of
    # check_self_claims), and that call goes through the shared `git()`
    # helper, which still collapses a git failure to '' rather than None.
    # In a non-git ROOT that earlier call finds zero files to scan at all,
    # so the plugin-commands: branch below it is never reached and a fixture
    # here would read as "0 problems" for a reason that has nothing to do
    # with count_plugin_commands's None-handling - a false pass on the test,
    # not a true one on the code. That earlier `git()` call has the same
    # "collapses failure to a safe-looking value" shape this FIX just
    # removed from count_plugin_commands/count_plugin_agents, but it was not
    # named in this round's findings, so it is filed (TODO.md) rather than
    # fixed here. check_description_claims and check_catalog_claims below do
    # NOT discover their input this way - they iterate DESCRIPTION_CLAIMS /
    # CATALOG_CLAIMS directly - so both are real, working propagation proofs.

    no_git_description_problems = run_description(
        "30 agents, 0 slash commands, 2 bundled skills",
        {"widget": ("commands",)},
        widget_commands=["a"],
        init_git=False,
    )
    ok = len(no_git_description_problems) == 1 and any(
        "could not verify" in p for p in no_git_description_problems
    )
    if ok:
        passed += 1
        print("  ok   check_description_claims reports 'could not verify' with no git, not a silent pass")
    else:
        failed += 1
        print("  FAIL check_description_claims reports 'could not verify' with no git, not a silent pass")
        print(f"       got {len(no_git_description_problems)}: {no_git_description_problems}")

    no_git_catalog_problems = run_catalog(
        "widget    - Mine: 0 commands",
        "widget    - Mine: 0 commands",
        ("commands",),
        widget_commands=["a"],
        init_git=False,
    )
    ok = len(no_git_catalog_problems) == 2 and all(
        "could not verify" in p for p in no_git_catalog_problems
    )
    if ok:
        passed += 1
        print("  ok   check_catalog_claims reports 'could not verify' with no git, not a silent pass")
    else:
        failed += 1
        print("  FAIL check_catalog_claims reports 'could not verify' with no git, not a silent pass")
        print(f"       got {len(no_git_catalog_problems)}: {no_git_catalog_problems}")

    # main()-wiring: proves main() actually calls check_description_claims
    # and check_catalog_claims, not just that the functions are individually
    # correct. See run_main_description_wiring / run_main_catalog_wiring.
    for label, correct, expect_nonzero in (
        ("main() wiring: check_description_claims catches a wrong count", False, True),
        ("main() wiring: check_description_claims allows a correct count", True, False),
        ("main() wiring: check_catalog_claims catches a wrong count", False, True),
        ("main() wiring: check_catalog_claims allows a correct count", True, False),
    ):
        if label.startswith("main() wiring: check_description_claims"):
            exit_code = run_main_description_wiring(correct)
        else:
            exit_code = run_main_catalog_wiring(correct)
        ok = (exit_code != 0) == expect_nonzero
        if ok:
            passed += 1
            print(f"  ok   {label}")
        else:
            failed += 1
            print(f"  FAIL {label}")
            print(f"       expected exit {'non-zero' if expect_nonzero else '0'}, got {exit_code}")

    print(f"\nself-claims: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
