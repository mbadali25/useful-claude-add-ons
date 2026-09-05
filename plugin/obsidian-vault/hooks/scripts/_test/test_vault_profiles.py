#!/usr/bin/env python3
"""Regression suite for vault profiles: the sets, the detection, the 50k line.

    python3 hooks/scripts/_test/test_vault_profiles.py

Plain assertions, no pytest, same shape as test_vault_ops.py. Nothing here
opens a socket, launches Obsidian, or builds a 400,000-note fixture: the
classifier is a pure function of gathered evidence, so the measured numbers
below are fed to it directly.

The two cases that carry the most weight are the zero-diff invariants. The
profile sets were not composed from what a vault "should" want - they were read
off the reference machine's own `community-plugins.json` files:

    claude-memories          1,361 notes, 15 plugins  -> the authored set
    claude-anew-codegraph   22,027 notes,  2 plugins  -> the graph set

so the authored profile diffed against those 15 must come out empty in both
directions, and the graph profile against those 2 likewise. A transcription
error in either list - a wrong ID, a dropped entry, an invented extra - shows
up as a non-empty diff rather than as a list asserted against itself. That
matters here because Obsidian ignores an unknown plugin ID in silence: a
mistyped entry never turns anything on, and every tool downstream reports
success.

The remaining vaults on that machine are the detection fixtures:

    claude-memories-codegraphs   layout "org/repo" in config, 1 plugin
    claude-anew-thd-codegraph   26,146 notes, 0 plugins, <org>/<repo> on disk
    claude-anew-theselectsource 18,402 notes, 0 plugins, <org>/<repo> on disk

The last two are the interesting ones: no plugins at all means no REST API,
which means invisible to Claude, and it also means detection has to reach the
right answer with the plugin list empty.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_ops  # noqa: E402  pylint: disable=wrong-import-position
import vault_profiles  # noqa: E402  pylint: disable=wrong-import-position

FAILURES = []


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def check_in(desc, needle, haystack):
    if needle.lower() not in haystack.lower():
        FAILURES.append(f"{desc}: {needle!r} not found in {haystack!r}")


def check_not_in(desc, needle, haystack):
    if needle.lower() in haystack.lower():
        FAILURES.append(f"{desc}: {needle!r} should NOT appear in {haystack!r}")


# --- The measured sets, copied off disk, not composed ------------------------

MEASURED_AUTHORED = [
    "dataview", "obsidian-git", "obsidian-excalidraw-plugin", "omnisearch",
    "obsidian-kanban", "templater-obsidian", "auto-note-mover", "breadcrumbs",
    "obsidian-linter", "periodic-notes", "obsidian-local-rest-api",
    "obsidian-advanced-uri", "metadata-menu", "obsidian-charts", "text-extractor",
]
MEASURED_GRAPH = ["obsidian-local-rest-api", "code-graph"]
MEASURED_NOTES = {"memories": 1361, "anew-codegraph": 22027,
                  "anew-thd": 26146, "theselectsource": 18402}


# --- 1. The three sets, and the two zero-diff invariants ---------------------

def _t_sets():
    check("bridge is exactly the REST API plugin",
          vault_profiles.profile_plugins("bridge"), ["obsidian-local-rest-api"])
    check("graph is the bridge plus code-graph, in that order",
          vault_profiles.profile_plugins("graph"),
          ["obsidian-local-rest-api", "code-graph"])

    # The invariant: the graph profile IS what anew-codegraph runs.
    graph = set(vault_profiles.profile_plugins("graph"))
    check("graph profile lacks nothing anew-codegraph runs",
          sorted(set(MEASURED_GRAPH) - graph), [])
    check("graph profile invents nothing anew-codegraph does not run",
          sorted(graph - set(MEASURED_GRAPH)), [])

    # ...and the authored profile below 50k IS what memories runs.
    authored = set(vault_profiles.profile_plugins("authored", MEASURED_NOTES["memories"]))
    check("authored profile lacks nothing the memories vault runs",
          sorted(set(MEASURED_AUTHORED) - authored), [])
    check("authored profile invents nothing the memories vault does not run",
          sorted(authored - set(MEASURED_AUTHORED)), [])
    check("authored profile is 15 plugins at memories' size", len(authored), 15)

    # The index-building plugins are deliberately absent from graph. Nothing in
    # a vault only Claude greps ever reads the index they spend disk building.
    for costly in ("omnisearch", "text-extractor", "dataview", "breadcrumbs"):
        check(f"graph profile deliberately excludes {costly}", costly in graph, False)

    check("bridge is contained in graph",
          set(vault_profiles.profile_plugins("bridge")) <= graph, True)
    check("bridge is contained in authored",
          set(vault_profiles.profile_plugins("bridge")) <= authored, True)

    try:
        vault_profiles.profile_plugins("enormous")
        FAILURES.append("an unknown profile kind should raise, not return a set")
    except ValueError as e:
        check_in("the error names the kinds that do exist", "bridge, graph, authored", str(e))


_t_sets()


# --- 2. The 50,000-note boundary ---------------------------------------------
# Nothing on the reference machine sits anywhere near this line, so both sides
# of it are synthetic on purpose - the boundary is the thing under test.

def _t_threshold():
    check("the threshold is the ~50k figure the plugin's own docs already name",
          vault_profiles.OMNISEARCH_THRESHOLD, 50000)
    below = vault_profiles.profile_plugins("authored", 49999)
    at = vault_profiles.profile_plugins("authored", 50000)
    above = vault_profiles.profile_plugins("authored", 421901)
    check("49,999 notes keeps omnisearch", "omnisearch" in below, True)
    check("49,999 notes keeps text-extractor", "text-extractor" in below, True)
    check("exactly 50,000 notes drops omnisearch", "omnisearch" in at, False)
    check("exactly 50,000 notes drops text-extractor", "text-extractor" in at, False)
    check("a code-graph-sized authored vault drops both",
          [p for p in above if p in vault_profiles.AUTHORED_SEARCH_PLUGINS], [])
    check("only the two search plugins move across the boundary",
          sorted(set(below) - set(at)), ["omnisearch", "text-extractor"])
    check("an unknown count keeps them rather than proposing a removal",
          "omnisearch" in vault_profiles.profile_plugins("authored", None), True)

    check_in("the threshold note explains which way it went",
             "under the ~50,000 mark",
             vault_profiles.threshold_note("authored", 49999))
    check_in("the threshold note says what gets slow at size",
             "NOT in the set",
             vault_profiles.threshold_note("authored", 50000))
    check("no threshold note for a graph vault",
          vault_profiles.threshold_note("graph", 421901), "")


_t_threshold()


# --- Fixtures ----------------------------------------------------------------

def make_vault(root, name, plugins=None, plugin_dirs=(), notes=()):
    """A vault directory. `plugins` of None leaves community-plugins.json absent
    (Restricted Mode was never turned off), which is NOT the same as `[]`."""
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".obsidian"), exist_ok=True)
    if plugins is not None:
        with open(obsidian_common.community_plugins_path(path), "w", encoding="utf-8") as fh:
            json.dump(plugins, fh)
    for plugin_id in plugin_dirs:
        d = os.path.join(path, ".obsidian", "plugins", plugin_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "main.js"), "w", encoding="utf-8") as fh:
            fh.write("// plugin files, never loaded\n")
    for rel, body in notes:
        full = os.path.join(path, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(body)
    return path


CONTRACT_NOTE = """---
type: concept
title: "{name}"
created: 2026-08-20
updated: 2026-09-04
status: seed
tags:
  - concept
---
Body.
"""

GRAPH_NOTE = "# node\n\nA generated node with no frontmatter at all.\n"


class Sandbox:
    """A throwaway HOME with a config.json and an empty Obsidian registry."""

    def __init__(self, vaults_config):
        self.tmp = tempfile.mkdtemp(prefix="obsidian-profiles-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude", "obsidian"))
        with open(os.path.join(self.home, ".claude", "obsidian", "config.json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"vaults": vaults_config}, fh)
        self._old_home = None
        self._old_env_vault = None
        self._old_app_json = None

    def __enter__(self):
        self._old_home = os.environ.get("HOME")
        self._old_env_vault = os.environ.pop("OBSIDIAN_VAULT_PATH", None)
        os.environ["HOME"] = self.home
        app_json = os.path.join(self.tmp, "obsidian.json")
        with open(app_json, "w", encoding="utf-8") as fh:
            json.dump({"vaults": {}}, fh)
        self._old_app_json = obsidian_common.obsidian_app_json_path
        obsidian_common.obsidian_app_json_path = lambda: app_json
        return self

    def __exit__(self, *_exc):
        obsidian_common.obsidian_app_json_path = self._old_app_json
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_env_vault is not None:
            os.environ["OBSIDIAN_VAULT_PATH"] = self._old_env_vault
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def run_cli(argv):
    """(exit_code, stdout+stderr). The CLI's wording is itself under test."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = vault_ops.main(argv, prober=object())
    return code, out.getvalue()


# --- 3. Detection of all three kinds -----------------------------------------
# The note counts are the measured ones, injected rather than walked: a fixture
# with 26,146 files would make this suite slower than everything else in the
# repo combined, and the count is not what is being tested here - what is done
# with it is.

def _t_detection():
    tmp = tempfile.mkdtemp(prefix="obsidian-detect-test-")
    try:
        # memories: a human's vault. Frontmatter contract plus the authored set.
        memories = make_vault(
            tmp, "claude-memories", plugins=MEASURED_AUTHORED,
            notes=[(f"wiki/concepts/n{i}.md", CONTRACT_NOTE.format(name=f"n{i}"))
                   for i in range(6)])
        ev = vault_profiles.gather_evidence(memories,
                                            note_count=MEASURED_NOTES["memories"])
        verdict = vault_profiles.classify(ev)
        check("memories is authored", verdict["kind"], "authored")
        check("...confidently", verdict["confident"], True)
        check_in("...on the frontmatter contract", "memory contract",
                 " ".join(verdict["reasons"]))
        check_in("...and on the plugins already there", "authored-set plugins",
                 " ".join(verdict["reasons"]))

        # anew-codegraph: declares itself by running the code-graph plugin.
        anew = make_vault(tmp, "claude-anew-codegraph", plugins=MEASURED_GRAPH,
                          notes=[("anew/SRL/a.md", GRAPH_NOTE)])
        verdict = vault_profiles.classify(vault_profiles.gather_evidence(
            anew, note_count=MEASURED_NOTES["anew-codegraph"]))
        check("anew-codegraph is graph", verdict["kind"], "graph")
        check_in("...because the plugin says so", "code-graph plugin is enabled",
                 " ".join(verdict["reasons"]))

        # codegraphs: nearly empty on disk, but config declares the layout.
        codegraphs = make_vault(tmp, "claude-memories-codegraphs",
                                plugins=["obsidian-local-rest-api"],
                                notes=[("Welcome.md", "# hi\n")])
        verdict = vault_profiles.classify(vault_profiles.gather_evidence(
            codegraphs, layout="org/repo", note_count=2))
        check("a configured org/repo layout is a declaration", verdict["kind"], "graph")
        check_in("...and says so", "layout", " ".join(verdict["reasons"]))

        # anew-thd and theselectsource: ZERO plugins. No declaration to read, so
        # the verdict has to come from structure plus the absence of a contract.
        for name, org, repo, count in (
                ("claude-anew-thd-codegraph", "anew", "TheHomeDepot",
                 MEASURED_NOTES["anew-thd"]),
                ("claude-anew-theselectsource", "codegraphs", "ANEW-Warehouse",
                 MEASURED_NOTES["theselectsource"])):
            vault = make_vault(tmp, name, plugins=None,
                               notes=[(f"{org}/{repo}/n{i}.md", GRAPH_NOTE)
                                      for i in range(4)] + [("Welcome.md", "# hi\n")])
            ev = vault_profiles.gather_evidence(vault, note_count=count)
            check(f"{name}: no community-plugins.json means the list is UNKNOWN",
                  ev["plugins"], None)
            check(f"{name}: no bridge, so it is invisible to Claude",
                  ev["has_bridge"], False)
            verdict = vault_profiles.classify(ev)
            check(f"{name} is graph on structure alone", verdict["kind"], "graph")
            check_in(f"{name}: the structure is named as the evidence",
                     "<org>/<repo>", " ".join(verdict["reasons"]))
            check_in(f"{name}: the absent contract is named too", "frontmatter",
                     " ".join(verdict["reasons"]))
            check(f"{name}: the graph profile is two plugins, both missing",
                  vault_profiles.compare("graph", count, ev["plugins"])["missing"],
                  ["obsidian-local-rest-api", "code-graph"])
            check(f"{name}: nothing is proposed for removal from a list nobody read",
                  vault_profiles.compare("graph", count, ev["plugins"])["unwanted"], [])

        # A small vault with nothing to go on. It must NOT be upgraded to
        # authored: that would propose fourteen plugins the user never asked
        # for. Bridge is the floor and is contained in both other profiles, so
        # nothing proposed from it has to be undone later.
        plain = make_vault(tmp, "scratch", plugins=[],
                           notes=[("a.md", "# a\n"), ("b.md", "# b\n")])
        verdict = vault_profiles.classify(vault_profiles.gather_evidence(plain,
                                                                         note_count=2))
        check("an empty vault with no evidence falls back to bridge",
              verdict["kind"], "bridge")
        check("...and says it is not confident", verdict["confident"], False)
        check_in("...and says why it could not decide", "no declaration",
                 " ".join(verdict["reasons"]))
        check("bridge fallback wants only the REST API plugin",
              vault_profiles.compare("bridge", 2, [])["missing"],
              ["obsidian-local-rest-api"])

        # An authored vault whose folders happen to look like <org>/<repo>.
        # Boards/<board>/note.md is structurally identical to a one-repo
        # export; only the authored signals tell them apart, which is why they
        # are weighed first.
        lookalike = make_vault(
            tmp, "lookalike", plugins=["dataview", "templater-obsidian", "obsidian-git"],
            notes=[("Boards/q3/card.md", "# card\n"),
                   ("wiki/concepts/x.md", CONTRACT_NOTE.format(name="x"))])
        verdict = vault_profiles.classify(vault_profiles.gather_evidence(lookalike,
                                                                         note_count=1400))
        check("an <org>/<repo>-shaped authored vault stays authored",
              verdict["kind"], "authored")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_detection()


# --- 4. A split is the last resort, and the wikilinks it would break ---------

def _t_split():
    tmp = tempfile.mkdtemp(prefix="obsidian-split-test-")
    try:
        # 4 notes, 6 wikilinks, 3 of which cross the provenance seam. Counted
        # by hand here so the assertion is against a known number, not against
        # whatever the code happens to produce.
        vault = make_vault(tmp, "mixed", plugins=[], notes=[
            ("anew/TheHomeDepot/alpha.md", "Links [[beta]] and [[alpha]].\n"),
            ("anew/TheHomeDepot/beta.md", "Links [[gamma]].\n"),
            ("wiki/gamma.md", "Links [[alpha|the alpha node]] and [[gamma#head]].\n"),
            ("Welcome.md", "Embeds ![[beta]].\n"),
        ])
        seam = vault_profiles.split_seam(vault)
        check("the seam is provenance: the export org on one side",
              seam["generated"], ["anew"])
        check("...and everything hand-made on the other",
              seam["authored"], ["Welcome.md", "wiki"])

        analysis = vault_profiles.split_analysis(vault, min_notes=0)
        check("every wikilink form is counted ([[x]], [[x|y]], [[x#h]], ![[x]])",
              analysis["links"], 6)
        check("three of them cross the seam and would break", analysis["crossing"], 3)
        check("every note was read", analysis["notes"], 4)
        check_in("the count is stated as permanent breakage", "break permanently",
                 analysis["detail"])

        # A vault with no generated folders has no provenance seam at all, and
        # this refuses to invent one out of size.
        flat = make_vault(tmp, "flat", plugins=[], notes=[("a.md", "[[b]]\n"),
                                                          ("b.md", "[[a]]\n")])
        analysis = vault_profiles.split_analysis(flat, min_notes=0)
        check("no export folders means no seam", analysis["crossing"], 0)
        check_in("...and it says size alone is not one", "size alone is not one",
                 analysis["detail"])

        # Below the threshold the question does not arise. Raising a seam on a
        # 1,400-note vault is a proposal to break links for no reason.
        ev = vault_profiles.gather_evidence(vault, note_count=1400)
        lines = vault_profiles.split_recommendation(
            "graph", ev, vault_profiles.compare("graph", 1400, ev["plugins"]))
        check_in("a small vault is told a split is not on the table",
                 "not on the table", " ".join(lines))

        # A seam is only offered where the generated side is big enough to BE a
        # generated side. Two notes under anew/ is a folder, not an export -
        # and calling a human's folder generated is how a tool talks somebody
        # into moving files that were never generated.
        check("a two-note <org> is not a generated side",
              vault_profiles.split_seam(vault, min_notes=1000)["generated"], [])

        # Past the threshold, the plugin set is offered FIRST - the index is
        # the limit, not the note count, and turning it off breaks nothing
        # permanently. This fixture has a real export-sized generated side.
        bulk = make_vault(tmp, "bulk", plugins=[], notes=(
            [(f"anew/TheHomeDepot/n{i}.md", GRAPH_NOTE) for i in range(1000)]
            + [("wiki/hand-written.md", "[[n1]]\n")]))
        big = vault_profiles.gather_evidence(bulk, note_count=120000)
        big["plugins"] = ["obsidian-local-rest-api", "omnisearch", "text-extractor"]
        lines = " ".join(vault_profiles.split_recommendation(
            "graph", big, vault_profiles.compare("graph", 120000, big["plugins"])))
        check_in("the index is named as the real limit", "not the note count", lines)
        check_in("...and disabling it is offered as reversible", "reversible", lines)
        check_in("...and each one still needs its own confirmation",
                 "confirm each one separately", lines)
        check_in("the seam, if it comes to that, is provenance", "PROVENANCE", lines)
        check_in("...and nothing moves a file", "moves a file", lines)

        # The command that NAMES a seam and the command that counts the damage
        # on it must pick the same folders. They took different `min_notes`
        # defaults once, which meant `--split-analysis` could report a breakage
        # figure for a seam nobody had proposed.
        named = vault_profiles.split_seam(bulk,
                                          min_notes=vault_profiles.GRAPH_STRUCTURE_MIN_NOTES)
        counted = vault_profiles.split_analysis(bulk)["seam"]
        check("the named seam and the counted seam are the same seam", counted, named)
        check("...and it is the export folder, not the hand-written one",
              named["generated"], ["anew"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_split()


# --- 5. The CLI: `profile`, and the no-blanket-yes rule on install-plugin ----

def _t_cli():
    tmp = tempfile.mkdtemp(prefix="obsidian-profile-cli-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None
    try:
        # Every authored plugin's FILES are present, so the only thing standing
        # between `--apply` and fifteen enabled plugins is the rule under test.
        authored = make_vault(
            tmp, "memories", plugins=[],
            plugin_dirs=vault_profiles.profile_plugins("authored", 100),
            notes=[(f"wiki/concepts/n{i}.md", CONTRACT_NOTE.format(name=f"n{i}"))
                   for i in range(6)])
        # Declared by config rather than by size, which is how the real
        # claude-memories-codegraphs vault is classified: a nearly-empty export
        # target still has to come out `graph`.
        graphv = make_vault(tmp, "thd", plugins=None,
                            notes=[("anew/TheHomeDepot/a.md", GRAPH_NOTE)])
        cp_path = obsidian_common.community_plugins_path(authored)

        with Sandbox({"memories": {"path": authored, "default": True},
                      "thd": {"path": graphv, "layout": "org/repo"}}):
            code, out = run_cli(["profile", "--vault", "memories"])
            check("a vault missing most of its profile reports problems",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("profile names the kind", "authored", out)
            check_in("profile shows the evidence", "evidence", out)
            check_in("profile lists what the vault lacks", "lacks", out)
            check_in("profile lists what the vault carries", "carries", out)

            code, out = run_cli(["profile", "--vault", "thd", "--json"])
            data = json.loads(out)["vaults"][0]
            check("json carries the verdict", data["kind"], "graph")
            check("json carries the evidence behind it",
                  bool(data["reasons"]), True)
            check("json carries the install side",
                  data["comparison"]["missing"],
                  ["obsidian-local-rest-api", "code-graph"])

            # --profile overrides detection, and the disagreement stays visible.
            code, out = run_cli(["profile", "--vault", "thd", "--profile", "authored"])
            check_in("an override says detection disagreed", "detection said: graph", out)

            # THE RULE: a bare --apply must not enable a whole profile.
            code, out = run_cli(["install-plugin", "--vault", "memories", "--apply"])
            with open(cp_path, "r", encoding="utf-8") as fh:
                written = json.load(fh)
            check("bare --apply enables the bridge floor and NOTHING else",
                  written, ["obsidian-local-rest-api"])
            check("...and reports the rest as outstanding", code, vault_ops.EXIT_PROBLEMS)
            check_in("...naming the per-plugin command for each one",
                     "--plugin dataview --apply", out)
            check_in("...and saying a relaunch is what makes it real", "relaunch", out)
            check_in("...explicitly, that it is not running yet", "NOT running", out)

            # One named plugin, one write.
            code, out = run_cli(["install-plugin", "--vault", "memories",
                                 "--plugin", "dataview", "--apply"])
            with open(cp_path, "r", encoding="utf-8") as fh:
                written = json.load(fh)
            check("--plugin enables exactly what was named, and keeps the rest",
                  written, ["obsidian-local-rest-api", "dataview"])

            # A dry run writes nothing, even when named.
            code, out = run_cli(["install-plugin", "--vault", "memories",
                                 "--plugin", "obsidian-git"])
            with open(cp_path, "r", encoding="utf-8") as fh:
                check("a dry run writes nothing", json.load(fh),
                      ["obsidian-local-rest-api", "dataview"])
            check("a dry run reports a problem so nothing looks done",
                  code, vault_ops.EXIT_PROBLEMS)

            # A plugin the profile does not want is refused rather than written:
            # an ID Obsidian does not recognise is ignored in silence.
            code, out = run_cli(["install-plugin", "--vault", "memories",
                                 "--plugin", "omnisearchh", "--apply"])
            check("a typo'd plugin ID is refused", code, vault_ops.EXIT_PROBLEMS)
            check_in("...and the real set is printed", "obsidian-local-rest-api", out)
            with open(cp_path, "r", encoding="utf-8") as fh:
                check("...and nothing was written", json.load(fh),
                      ["obsidian-local-rest-api", "dataview"])

            # --set is a config write, so it is a dry run first like everything
            # else here, and it enables nothing on its own.
            code, out = run_cli(["profile", "--vault", "thd", "--set", "authored"])
            check("--set without --apply is a dry run", code, vault_ops.EXIT_PROBLEMS)
            check_in("...which names the disagreement with detection", "DISAGREES", out)
            check(".. and wrote nothing", vault_profiles.configured_profile("thd"), None)
            code, out = run_cli(["profile", "--vault", "thd", "--set", "authored",
                                 "--apply"])
            check("--set --apply stores the override", code, vault_ops.EXIT_OK)
            check("...in config", vault_profiles.configured_profile("thd"), "authored")
            code, out = run_cli(["profile", "--vault", "thd"])
            check_in("...and the stored override still shows what detection said",
                     "detection said: graph", out)
            code, _ = run_cli(["profile", "--vault", "thd", "--set", "auto", "--apply"])
            check("--set auto hands the vault back to detection",
                  vault_profiles.configured_profile("thd"), None)

            code, out = run_cli(["profile", "--set", "graph"])
            check("--set without --vault is a usage error", code, vault_ops.EXIT_USAGE)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_cli()


print(f"RESULT: {len(FAILURES)} failed")
for failure in FAILURES:
    print("FAIL:", failure)
sys.exit(1 if FAILURES else 0)
