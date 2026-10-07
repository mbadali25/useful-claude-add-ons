"""Tests for crew_config: the single source of truth for a fresh config.

Five things must never disagree: `default_config()`, the committed template
`templates/config.template.json` (what `/crew:init` writes), the inline JSON
copy in `skills/crew-setup/SKILL.md` (prose for a human reading the skill),
the `pm` / `qa` / `dev` / `graph` blocks owned by `crew_state` and
`crew_upgrade`, and -- since 0.16.0 -- `default_global_config()` against
`templates/global.template.json`. The drift tests are what actually protect
that; everything else here is ordinary unit coverage.

The rest of this file covers the three things the guided-config work added:
`explain_config` (the value AND the layer that decided it), `inspect_global`
(what `/crew:upgrade` reports, writing nothing), and the global writer, whose
three guarantees -- merge, refuse a repo key, mark a widening of
`pm.authority` -- are enforced in code and tested here rather than trusted to
prose.
"""
import copy
import errno
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_config
import crew_config_files
import crew_fixtures
import crew_platform
import crew_shell
import crew_state
import crew_upgrade

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "templates", "config.template.json",
)
_GLOBAL_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "templates", "global.template.json",
)
_SKILL_MD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "skills", "crew-setup", "SKILL.md",
)


def test_default_config_matches_the_committed_template():
    """Drift between this module and the file /crew:init copies must fail CI.

    A byte-for-byte comparison, not just a dict equality, so a formatting
    change (key order, indent width) that would still round-trip equal is
    also caught -- the template is meant to be exactly what a fresh
    `json.dumps(template_config(), indent=2) + "\\n"` produces. Since T-0050
    that is `default_config()` minus the personal keys, so a template default
    never shadows the owner's global value.
    """
    expected = json.dumps(crew_config.template_config(), indent=2) + "\n"
    with open(_TEMPLATE_PATH, encoding="utf-8") as handle:
        actual = handle.read()
    assert actual == expected


def test_default_global_config_matches_the_committed_template():
    """Same drift gate as the repo template, on the global one.

    `/crew:config` writes this file's keys into `~/.claude/crew/config.json`,
    so a template that disagrees with `default_global_config()` is a
    walkthrough offering a key the writer refuses, or refusing one the
    template advertises. Byte-for-byte for the same reason as above.
    """
    expected = json.dumps(crew_config.global_template_config(), indent=2) + "\n"
    with open(_GLOBAL_TEMPLATE_PATH, encoding="utf-8") as handle:
        actual = handle.read()
    assert actual == expected


def test_notify_new_keys_survive_filter_global():
    """crew_notify.py reads `notify.realertHours` and `notify.questionTypes` from
    the global layer too (T-0051); a key `filter_global` prunes takes effect
    nowhere."""
    kept, ignored = crew_config.filter_global(
        {"notify": {"realertHours": 2, "questionTypes": ["permission_prompt"]}})

    assert (kept["notify"], ignored) == (
        {"realertHours": 2, "questionTypes": ["permission_prompt"]}, [])


def test_repo_template_notify_provider_is_null():
    """A repo `"none"` is an explicit opt-out that beats the global provider, so
    the template /crew:init writes leaves it null and inherits instead."""
    with open(_TEMPLATE_PATH, encoding="utf-8") as handle:
        written = json.load(handle)

    assert written["notify"]["provider"] is None


def test_the_global_template_is_not_a_copy_of_the_repo_one():
    """`tracker`, `jira.project`, `obsidian.boardDir`, `graph.out` and
    `platform.*` are facts about one checkout. Shipping them globally invites
    a vault path set once that every repo on the machine then inherits."""
    keys = set(crew_config.default_global_config())
    for repo_only in ("tracker", "jira", "sdp", "obsidian", "graph",
                      "platform", "tier", "roles", "verifyGate",
                      "emergency"):
        assert repo_only not in keys, repo_only
    # `context` is the one shared block, and it is shared NARROWLY: 0.19.10
    # made `context.autoClear` globally settable because how a terminal is
    # driven to accept a keystroke is a fact about the machine, which
    # `crew_platform.py:384-393` already validates per platform. Nothing else
    # under `context` came with it. Asserting the shape here as well as in
    # `test_autoclear_is_global_and_its_siblings_are_not`, because THIS test
    # is the one that would otherwise have been "fixed" by deleting `context`
    # from the tuple above and calling the block shared.
    assert set(crew_config.default_global_config()["context"]) == {"autoClear"}


def test_the_global_template_carries_no_schema():
    """`resolve_config` exempts `schema` structurally so a global value can
    never make an unmigrated repo look current. Shipping it in the template
    would hand every user the exact value that exemption exists to ignore."""
    assert "schema" not in crew_config.default_global_config()


def test_every_global_key_is_a_real_repo_config_key():
    """A global key the repo shape has never heard of would resolve into
    every repo and be read by nothing.

    The one exception is a MACHINE-ONLY block (T-0044's `unattendedCloud`):
    it is read from the machine file alone by `crew_unattended.py`, so the
    repo shape must NOT carry it -- that is asserted, not just allowed."""
    repo = crew_config.default_config()
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        if path.split(".")[0] in crew_state.UNATTENDED_CLOUD_MACHINE_ONLY:
            assert path.split(".")[0] not in repo, path
            continue
        node = repo
        for part in path.split("."):
            assert isinstance(node, dict) and part in node, path
            node = node[part]


def test_shell_route_is_on_both_layers():
    """T-0040. Which shell is fast is a fact about the machine, and a repo may
    still override it, so `shellRoute` sits in both layers. It is a new block
    rather than a `platform.*` key because platform-sync rewrites `platform.*`
    every SessionStart, and it is not the old draft name `wslRouting`. The repo
    layer's `mode` is null so an untouched repo inherits the machine's (review
    round 2 FIX 1); the machine layer spells out `auto`."""
    assert crew_config.default_config()["shellRoute"] == {"mode": None, "distro": None}
    assert crew_config.default_global_config()["shellRoute"] == {"mode": "auto", "distro": None}
    for layer in (crew_config.default_config(), crew_config.default_global_config()):
        assert "wslRouting" not in layer


def test_default_global_config_returns_a_fresh_object_each_call():
    first = crew_config.default_global_config()
    first["pm"]["authority"] = "act"
    first["qa"]["codex"]["model"] = "mutated"
    assert crew_config.default_global_config()["pm"]["authority"] == "report-only"
    assert crew_config.default_global_config()["qa"]["codex"]["model"] is None


def test_default_config_matches_crew_setup_skill_md_inline_copy():
    """The inline JSON in crew-setup/SKILL.md is prose for a human reading
    the skill, not a second definition -- crew_config's own module docstring
    says so. Compared PARSED, not byte-wise: the doc renders every nested
    object on one line for readability, which `json.dumps(..., indent=2)`
    would not reproduce, and a formatting difference is not drift. A field
    added to `default_config()` and forgotten here is drift, and this is
    the test that catches it -- the template-drift test above only covers
    `templates/config.template.json`, a file most people editing the skill
    will never open.
    """
    with open(_SKILL_MD_PATH, encoding="utf-8") as handle:
        text = handle.read()
    fences = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert len(fences) == 1, (
        "expected exactly one ```json fence in crew-setup/SKILL.md (the "
        f"config.json copy) -- found {len(fences)}. If the skill now "
        "legitimately has more than one, make this test find the right one "
        "rather than deleting the check."
    )
    doc_config = json.loads(fences[0])
    assert doc_config == crew_config.template_config()


def test_default_config_pm_block_matches_crew_state():
    assert crew_config.default_config()["pm"] == crew_state.PM_DEFAULTS


def test_default_config_graph_block_matches_crew_upgrade():
    assert crew_config.default_config()["graph"] == crew_upgrade.GRAPH_BLOCK


def test_default_config_docs_and_bitbucket_blocks_match_crew_upgrade():
    """Same rule as the `graph` block above, and for the same reason: these
    two live in `crew_upgrade` because `CONFIG_BLOCKS` has to reference them,
    so a fresh repo and an upgraded one must be handed the identical shape."""
    got = crew_config.default_config()
    assert got["docs"] == crew_upgrade.DOCS_BLOCK
    assert got["bitbucket"] == crew_upgrade.BITBUCKET_BLOCK


def test_docs_and_bitbucket_are_carried_by_an_upgrade():
    """A top-level block absent from `CONFIG_BLOCKS` is never written into an
    already-initialised repo -- the whole of the 0.16.0 qa/dev bug. Asserted
    from `default_config()` rather than a literal list so a THIRD block added
    to the fresh-repo shape and forgotten in `crew_upgrade` fails here too.
    """
    carried = {key for key, _block in crew_upgrade.CONFIG_BLOCKS}
    for key in ("docs", "bitbucket"):
        assert key in carried, (
            f"{key} is in default_config() but not crew_upgrade.CONFIG_BLOCKS, "
            "so /crew:upgrade will never add it to an existing repo's config"
        )


def test_default_config_returns_a_fresh_docs_and_bitbucket_block():
    """`default_config`'s promise, on the two blocks it deepcopies out of
    another module -- a caller stamping a theme in must not edit the shared
    `crew_upgrade.DOCS_BLOCK` for every later caller in the process."""
    first = crew_config.default_config()
    first["docs"]["theme"] = "mutated"
    first["bitbucket"]["mergeGate"]["enabled"] = "mutated"
    assert crew_upgrade.DOCS_BLOCK["theme"] is None
    assert crew_upgrade.BITBUCKET_BLOCK["mergeGate"]["enabled"] is False
    assert crew_config.default_config()["docs"]["theme"] is None


def test_shape_readers_share_one_template_and_writers_still_get_fresh_copies():
    """`_shape` reads a cached `_default_template()` instead of deep-copying
    the whole default per lookup (that copy was 93% of a `/crew:config` menu
    build). The cache must agree with a fresh `default_config()` on every
    path, and a caller mutating `default_config()`'s result must not reach
    it."""
    assert crew_config._default_template() is crew_config._default_template()
    assert crew_config._default_template() == crew_config.default_config()

    fresh = crew_config.default_config()
    fresh["qa"]["order"] = "mutated"
    fresh["route"] = {}
    assert crew_config._default_template()["qa"]["order"] != "mutated"
    assert crew_config._shape("route") == "block"
    assert crew_config._shape("route.enabled") == "leaf"
    assert crew_config._shape("qa.roles") == "open"
    assert crew_config._shape("route.enabled.x") == "under"
    assert crew_config._shape("no.such.key") == "unknown"


def test_shape_lookups_build_no_default_config(monkeypatch):
    """The cost guard: once the template exists, a shape lookup builds no new
    default. Reverting any `_shape` / `_is_open_table` / `value_allowed`
    read to `default_config()` makes this raise. `pm.authority` at the
    machine layer reaches `value_allowed`'s lookup; `qa.order` there returns
    early through `null_means` and never does."""
    crew_config._default_template()

    def _built(*_a, **_k):
        raise AssertionError("a shape lookup deep-copied default_config()")
    monkeypatch.setattr(crew_config, "default_config", _built)
    crew_config._shape("route.enabled")
    crew_config._is_open_table("qa.roles")
    crew_config._content_problem("qa.order", "repo", None)
    crew_config.value_allowed("pm.authority", "machine", None)


def test_docs_and_bitbucket_are_settable_globally():
    """The criterion this feature dies silently on. A block absent from
    `default_global_config()` is pruned out of the global layer by
    `filter_global`, takes effect nowhere, and `inspect_global` reports it as
    a stray key -- so a theme set once per machine would do nothing at all."""
    global_cfg = {"docs": {"theme": "acme"},
                  "bitbucket": {"mergeGate": {"enabled": True}}}
    kept, ignored = crew_config.filter_global(global_cfg)
    assert ignored == []
    assert kept == global_cfg
    for path in ("docs.theme", "docs.reportTheme",
                 "bitbucket.mergeGate.enabled", "bitbucket.mergeGate.branch",
                 "bitbucket.mergeGate.preset"):
        assert crew_config.is_global_path(path), path


def test_a_globally_set_theme_and_merge_gate_reach_a_repo(
        tmp_path, monkeypatch):
    """The other half of `/crew:config --show`: the resolved table, not the
    findings. `filter_global` accepting the keys is necessary and not
    sufficient -- `explain_config` is a separate walk, and a key it credited
    to no layer would be a global setting that resolves nowhere while the
    findings list looks clean."""
    path = _global(tmp_path, monkeypatch, contents={
        "docs": {"theme": "acme", "reportTheme": "acme-client"},
        "bitbucket": {"mergeGate": {"enabled": True, "preset": "strict"}},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    rows = {r["path"]: r for r in crew_config.explain_config(str(root),
                                                             str(path))}

    for dotted, value in (("docs.theme", "acme"),
                          ("docs.reportTheme", "acme-client"),
                          ("bitbucket.mergeGate.enabled", True),
                          ("bitbucket.mergeGate.preset", "strict")):
        assert rows[dotted]["value"] == value, dotted
        assert rows[dotted]["source"] == "global", dotted
    # Unset globally, so the built-in default still decides it -- the null
    # that means "resolve the repo's main branch from the API".
    assert rows["bitbucket.mergeGate.branch"]["value"] is None


def test_the_ten_keys_crew_read_but_never_declared_are_declared():
    """Until 0.19.10 these ten were in use and in no default.

    Nine were read by a hook script and `jira.cloudId` was written by
    `/crew:jira-sync` and read back by nothing. An undeclared key still works,
    because `merge_defaults` carries a repo-layer key it has never heard of
    straight through -- which is exactly why this went unnoticed. What it cost
    was visibility: `leaf_paths` could not see them, so they appeared in no key
    listing, and `is_global_path` refuses any path absent from the global
    template, so they were silently un-settable in the global layer.

    Asserting the COUNT as well as the membership on purpose. A tenth key
    arriving undeclared is the same bug again, and a membership-only test would
    pass while it happened."""
    declared = set(crew_config.leaf_paths(crew_config.default_config()))
    for dotted in ("context.autoClear.enabled", "context.autoClear.method",
                   "context.autoClear.windowTitle", "context.autoClear.command",
                   "context.autoClear.delaySeconds",
                   "context.autoClear.minHandoffLines",
                   "context.autoClear.unsafeFocus",
                   "context.autoWrapUp", "context.autoResume",
                   "jira.cloudId"):
        assert dotted in declared, dotted
    # 96 at schema 6, which added six `guards` keys, the two `github.mergeGate`
    # ones and the repo-only `production.databases`/`production.hosts`, on top
    # of schema 5's `install.policy`. An empty list is a LEAF here -- see
    # `leaf_paths` -- so the two `production` keys count as two, not zero.
    # 102 at schema 7: the six `change` keys.
    # 103 since crew 0.19.92: `guards.roleWrites`, the role-write PreToolUse
    # guard's config key.
    # 106 since crew 0.20.19: the context hook's `memory.inject`,
    # `memory.recall.vaults` and `memory.recall.maxChars`.
    # 112 with the cloud guard: `guards.cloudDestructive`,
    # `guards.sqlDestructive`, the `guards.cloudGuard` switch, and the three
    # repo-only `cloud.*` identity-pin lists.
    # 114 with crew 1.0 T3: `scope.mode`, the scope guard's key, and
    # `scope.allowCliApproval` from the T3 fix round.
    # 116 with the Windows burn-in's autoClear narrowing:
    # `context.autoClear.onlyRepos` and `context.autoClear.onlySessions`.
    # 117 with T-0006's `resume.auto`, the auto-resume machine switch.
    assert "resume.auto" in declared
    # 119 with /crew:autopilot (T-0004): `autopilot.mode` and
    # `autopilot.maxPhases`, re-measured after rebasing onto T-0006.
    # 121 with T-0005: the repo-only `environments.nonProd` glob list and the
    # ratcheted `environments.prodUnattended`; 122 with plain-text routing
    # (T-0023): `route.enabled`. Re-measured after merging main.
    # 123 with T-0072: the repo-only `autopilot.deploy`, re-measured after
    # merging main's T-0023. 125 with T-0010's `autopilot.approval` and
    # `autopilot.questions`, re-measured after merging main's T-0072.
    # 127 with T-0040: `shellRoute.mode` and `shellRoute.distro`,
    # measured by running this test after merging main 6a8c60b1.
    assert "route.enabled" in declared
    assert "autopilot.deploy" in declared
    assert {"autopilot.approval", "autopilot.questions"} <= declared
    assert "shellRoute.mode" in declared and "shellRoute.distro" in declared
    # 127 with T-0028: `qa.kimi.model` and `dev.kimi.model`, measured after
    # merging main's 125. 129 with T-0040's two and T-0028's two, measured
    # by running this test on T-0040-land after merging main 844bfc36.
    assert "qa.kimi.model" in declared
    assert "dev.kimi.model" in declared
    # 131 with T-0013: `resume.typeDelaySeconds` and
    # `resume.readyTimeoutSeconds`, measured by running this test after
    # merging main 4f6ef540 for crew 1.0.186.
    assert {"resume.typeDelaySeconds", "resume.readyTimeoutSeconds"} <= declared
    # 130 with T-0061: the repo-only `tickets.baseBranch`, measured after
    # merging main 34d9f267.
    assert "tickets.baseBranch" in declared
    # 132 with T-0013's two machine keys (`resume.typeDelaySeconds`,
    # `resume.readyTimeoutSeconds`), measured after merging main into T-0013.
    # 133 with T-0066: `git.forbiddenTrailers` on top of those 132, measured
    # by running this test after merging main edb2b8ff.
    # 136 with T-0053's repo-only `autopilot.sleep.schedule`,
    # `autopilot.sleep.approval` and `autopilot.sleep.questions` on top of
    # those 133, measured by running this test after merging main 86d96fa1.
    assert "git.forbiddenTrailers" in declared
    assert {"autopilot.sleep.schedule", "autopilot.sleep.approval",
            "autopilot.sleep.questions"} <= declared
    # 137 with T-0017's `context.autoClear.wrapUp` on top of those 136,
    # measured by running this test on T-0017-build after merging main
    # a27c5e38 through T-0016-build.
    assert "context.autoClear.wrapUp" in declared
    # 138 with T-0074's repo-only `autopilot.maxAutoReplans` on top of those
    # 137, measured by running this test on T-0074-build after merging main
    # 8c0843ca.
    assert "autopilot.maxAutoReplans" in declared
    # Still 138 with T-0050 (batch 6): the personal `autopilot` keys stay
    # declared here (this is the defaults layer); only `template_config()`
    # omits them.
    # 141 with T-0011's repo-only ship phase (batch 7): `autopilot.ship`,
    # `autopilot.knownFailures` (an empty list, so one leaf) and
    # `autopilot.ciTimeoutMinutes` on top of those 138.
    assert {"autopilot.ship", "autopilot.knownFailures",
            "autopilot.ciTimeoutMinutes"} <= declared
    # 143 with T-0051's `notify.realertHours` and `notify.questionTypes` on
    # top of those 141, both layers, measured by running this test on
    # T-0051-build after merging main abddc302.
    assert {"notify.realertHours", "notify.questionTypes"} <= declared
    # 145 with L-0541's repo-only goal caps, `autopilot.maxTicketsPerRun` and
    # `autopilot.maxTokensPerSession`, on top of those 143, measured by running
    # this test on rush/g6b-goals-sleep.
    assert {"autopilot.maxTicketsPerRun", "autopilot.maxTokensPerSession"} <= declared
    # 146 with L-0654's `autopilot.sleep.deploy`, measured the same way.
    assert "autopilot.sleep.deploy" in declared
    # 147 with L-0656's `autopilot.sleep.notifyHold`, measured the same way.
    assert "autopilot.sleep.notifyHold" in declared
    assert len(declared) == 147


def test_forbidden_trailers_is_global_settable_and_defaults_empty():
    """T-0066: `git.forbiddenTrailers` is in BOTH layers, default `[]` (the
    list is the switch; empty means off). Global-settable because the owner
    who forbids a trailer forbids it on every repo of the machine, and
    `is_global_path` requires a global key to be a repo key too."""
    assert crew_config.is_global_path("git.forbiddenTrailers")
    assert crew_config.default_config()["git"] == {"forbiddenTrailers": []}
    assert crew_config.default_global_config()["git"] == {"forbiddenTrailers": []}


def test_tickets_base_branch_is_repo_only_and_null_by_default():
    """T-0061. Which branch ticket branches are cut from is a fact about one
    repository, so a machine-global file may not set it, and `null` keeps
    today's origin/HEAD default for every repo that never names it."""
    assert crew_config.default_config()["tickets"] == {"baseBranch": None}
    assert "tickets.baseBranch" not in set(
        crew_config.leaf_paths(crew_config.default_global_config()))
    assert not crew_config.is_global_path("tickets.baseBranch")


def test_autoclear_is_global_and_its_siblings_are_not():
    """The permissions half. `context.autoClear` is settable machine-wide;
    every other key under `context` is not.

    Naming `context` in `default_global_config()` could have widened the whole
    block -- `warnAt`, `reserveTokens`, `handoffPath` and the rest are facts
    about one repository, and a machine-wide value for them would be wrong
    everywhere at once. It does not, because `_prune` and `is_global_path` both
    descend structurally. This test is that claim measured rather than reasoned
    about, which is the distinction the block's own comment rests on."""
    supplied = {"context": {"autoClear": {"method": "tmux",
                                          "windowTitle": "Claude"}}}
    kept, ignored = crew_config.filter_global(supplied)
    assert ignored == []
    assert kept == supplied
    for dotted in ("context.autoClear.enabled", "context.autoClear.method",
                   "context.autoClear.windowTitle", "context.autoClear.command",
                   "context.autoClear.delaySeconds",
                   "context.autoClear.minHandoffLines",
                   "context.autoClear.onlyRepos",
                   "context.autoClear.onlySessions"):
        assert crew_config.is_global_path(dotted), dotted

    # The siblings, refused -- and refused BY NAME, not by the block name.
    # `_prune` reports the first absent segment with its full path prefix, so
    # a reader is told which key did nothing rather than that `context` is
    # unsupported, which would point at a bigger problem than exists.
    for dotted in ("context.enabled", "context.warnAt", "context.budgetTokens",
                   "context.reserveTokens", "context.handoffPath",
                   "context.keepTranscripts", "context.autoWrapUp",
                   "context.autoResume",
                   "context.staleHandoff.maxAgeHours",
                   "context.staleHandoff.maxCommitsBehind"):
        assert not crew_config.is_global_path(dotted), dotted
    _, stray = crew_config.filter_global(
        {"context": {"warnAt": 0.5, "autoWrapUp": True}})
    assert stray == ["context.warnAt", "context.autoWrapUp"]

    # `unsafeFocus` is declared but NOT granted -- consent, not capability.
    # It sits inside an otherwise-global block, so this is the one key whose
    # refusal is a deliberate hole in that block rather than a consequence of
    # the block's shape, and it is the one most likely to be "fixed" by
    # someone tidying the comprehension in `default_global_config()`.
    assert not crew_config.is_global_path("context.autoClear.unsafeFocus")
    _, refused = crew_config.filter_global(
        {"context": {"autoClear": {"unsafeFocus": True}}})
    assert refused == ["context.autoClear.unsafeFocus"]


def test_resume_auto_is_global_settable_and_defaults_to_null():
    """T-0006: `resume.auto` is armed from the machine file only
    (`crew_resume.settings`), so it must be a path the global layer may set --
    otherwise `filter_global` prunes it and `/crew:config` refuses to write
    the one place it can be switched on. Null, not false, in both defaults so
    the /crew:init template (which writes every key) never vetoes a machine
    opt-in. T-0013's two typing keys sit beside it, settable globally too
    (the machine file is the only one their reader opens)."""
    kept, ignored = crew_config.filter_global({"resume": {"auto": True, "typeDelaySeconds": 4,
                                                          "readyTimeoutSeconds": 30}})
    block = {"auto": None, "typeDelaySeconds": 2, "readyTimeoutSeconds": 15}

    assert (kept, ignored, crew_config.is_global_path("resume.auto"),
            crew_config.is_global_path("resume.typeDelaySeconds"),
            crew_config.is_global_path("resume.readyTimeoutSeconds"),
            crew_config.default_config()["resume"], crew_config.default_global_config()["resume"],
            crew_state.RESUME_DEFAULTS) == \
        ({"resume": {"auto": True, "typeDelaySeconds": 4, "readyTimeoutSeconds": 30}}, [], True, True, True,
         block, block, block)


def test_a_globally_set_autoclear_reaches_a_repo(tmp_path, monkeypatch):
    """`filter_global` accepting the keys is necessary and NOT sufficient.

    This is the `docs.theme` lesson applied before the fact rather than after:
    that key was settable for four releases with nothing reading it, so
    "declared" and "works" came apart and nobody noticed. `explain_config` is a
    separate walk from `filter_global`, and a key credited to no layer would be
    a machine-wide setting that resolves nowhere while the findings list looks
    clean."""
    path = _global(tmp_path, monkeypatch, contents={
        "context": {"autoClear": {"enabled": True, "method": "tmux",
                                  "delaySeconds": 9}},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    rows = {r["path"]: r for r in crew_config.explain_config(str(root),
                                                             str(path))}
    for dotted, value in (("context.autoClear.enabled", True),
                          ("context.autoClear.method", "tmux"),
                          ("context.autoClear.delaySeconds", 9)):
        assert rows[dotted]["value"] == value, dotted
        assert rows[dotted]["source"] == "global", dotted
    # Unset globally, so the built-in default still decides it.
    assert rows["context.autoClear.command"]["value"] == "/clear"
    # And the resolved config the run actually uses agrees with the report.
    resolved = crew_config.resolve_config(str(root))
    assert resolved["context"]["autoClear"]["method"] == "tmux"
    assert resolved["context"]["autoClear"]["command"] == "/clear"


def test_declaring_those_keys_costs_no_migration(tmp_path):
    """Declaring keys must not make every crew repo report `upgradeNeeded`.

    `upgradeNeeded` is `schema < SCHEMA_CURRENT` (`crew_state.py:2665`) and
    nothing else -- it does not compare key sets -- so an additive change to
    the defaults reaches existing repos through the merge at read time and
    needs no schema bump and no prompt. That is a property of the trigger
    rather than of this change, so it is asserted here where the change is: a
    later edit that bumped the schema to "make the new keys land" would be
    doing nothing except costing every repo on every machine a mandatory
    upgrade."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)
    state = crew_state.collect(str(root))
    assert "upgradeNeeded" not in state["triggers"]
    # A repo that has never heard of the new keys still resolves them.
    resolved = crew_config.resolve_config(str(root))
    assert resolved["context"]["autoClear"]["command"] == "/clear"
    assert resolved["context"]["autoWrapUp"] is True
    assert resolved["context"]["autoResume"] is True
    assert resolved["jira"]["cloudId"] is None


def test_default_config_schema_matches_crew_state():
    assert crew_config.default_config()["schema"] == crew_state.SCHEMA_CURRENT


def test_default_config_is_a_dict():
    assert isinstance(crew_config.default_config(), dict)


def test_default_config_platform_block_is_all_null():
    # platform-sync fills this in; a hand-written value here is only ever
    # overwritten on the next session start.
    platform_block = crew_config.default_config()["platform"]
    assert all(value is None for value in platform_block.values())


def test_default_config_returns_a_fresh_object_each_call():
    """Mutating one call's result must not affect the next call's."""
    first = crew_config.default_config()
    first["pm"]["authority"] = "act"
    first["graph"]["mode"] = "mutated"
    first["qa"]["codex"]["model"] = "mutated"
    second = crew_config.default_config()
    assert second["pm"]["authority"] == "report-only"
    assert second["graph"]["mode"] == "code-only"
    # A nested dict too: a shallow copy would pass the two above and still
    # let one caller mutate every later caller's `qa.codex`.
    assert second["qa"]["codex"]["model"] is None


def test_default_config_json_round_trips():
    text = json.dumps(crew_config.default_config())
    assert json.loads(text) == crew_config.default_config()


def test_mutating_pm_defaults_copy_does_not_leak_into_a_new_call():
    """copy.deepcopy, not a shared reference -- crew_upgrade.GRAPH_BLOCK's own
    docstring warns about exactly this failure one level down (obsidian)."""
    borrowed = copy.deepcopy(crew_state.PM_DEFAULTS)
    borrowed["maxDispatches"] = 999
    assert crew_config.default_config()["pm"]["maxDispatches"] == 3


# --- Global + repo layering (resolve_config) -------------------------------


def _global(tmp_path, monkeypatch, contents=None):
    """Point GLOBAL_CONFIG_PATH at a scratch file for this test only."""
    path = tmp_path / "global-config.json"
    if contents is not None:
        path.write_text(json.dumps(contents), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    return path


def test_resolve_config_with_neither_layer_is_just_defaults(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)  # no global file at all
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    resolved = crew_config.resolve_config(str(root))

    # Every key except `schema` matches the built-in default exactly.
    expected = crew_config.default_config()
    del expected["schema"]
    assert {k: v for k, v in resolved.items() if k != "schema"} == expected
    # No repo config at all means no repo `schema` key either -- absent, not
    # the built-in default's current value. See test_resolve_config_schema_*
    # below for the structural guarantee this protects.
    assert "schema" not in resolved


def test_resolve_config_global_only(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "pm": {"maxDispatches": 9}, "qa": {"provider": "codex"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    resolved = crew_config.resolve_config(str(root))

    # The WHOLE pm block layers globally, not just `authority`. How many
    # roles one pass may dispatch is a property of the machine doing the
    # dispatching; 0.16.0 briefly filtered it out and the user ruled it back.
    assert resolved["pm"]["maxDispatches"] == 9
    assert resolved["qa"]["provider"] == "codex"
    # Everything else in pm still comes from the built-in default.
    assert resolved["pm"]["quietLines"] == crew_state.PM_DEFAULTS["quietLines"]


def test_resolve_config_repo_only(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(
        tmp_path, config={"tracker": "obsidian"}, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["tracker"] == "obsidian"
    assert resolved["pm"] == crew_state.PM_DEFAULTS


def test_resolve_config_repo_overrides_global(tmp_path, monkeypatch):
    """Global is the DEFAULT, not a lock -- one repo may legitimately want a
    different reviewer from the rest of the machine."""
    _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex", "fallback": "claude-haiku-9"},
        "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config={
        "qa": {"provider": "copilot"}}, git=False)

    resolved = crew_config.resolve_config(str(root))

    # Repo wins where both set it.
    assert resolved["qa"]["provider"] == "copilot"
    # Global still wins over the built-in default where repo said nothing.
    assert resolved["qa"]["fallback"] == "claude-haiku-9"
    assert resolved["pm"]["authority"] == "act"


def test_an_upgraded_repo_still_lets_a_later_global_authority_through(
        tmp_path, monkeypatch):
    """THE MEASURED DEFECT, reproduced end to end. Before this fix,
    `crew_upgrade.upgrade_config({"schema": 2, "pm": {"enabled": True}})`
    wrote `pm.authority: "report-only"` -- the built-in default, but written
    -- into the repo file, and `resolve_config` resolves an ordinary key by
    PRECEDENCE, so that literal value outranked anything set in
    `~/.claude/crew/config.json` afterward, forever: a global `pm.authority`
    set AFTER the upgrade could never reach this repo again.

    Order matters here and is the point: the global file is written AFTER
    the repo is upgraded, exactly as it would be for an operator who
    upgrades first and only later decides the PM should run autonomously."""
    root = crew_fixtures.make_repo(tmp_path, config={"schema": 2, "tier": 0,
                                                      "pm": {"enabled": True}})
    crew_upgrade.run(str(root), {})
    upgraded = json.loads((root / ".crew" / "config.json")
                          .read_text(encoding="utf-8"))
    assert upgraded["schema"] == crew_state.SCHEMA_CURRENT
    # THE FIX, on the file itself: the built-in default is not written where
    # the repo never asked for it.
    assert "authority" not in upgraded.get("pm", {})

    _global(tmp_path, monkeypatch, contents={"pm": {"authority": "autonomous"}})
    resolved = crew_config.resolve_config(str(root))
    assert resolved["pm"]["authority"] == "autonomous"


def test_an_upgraded_repo_with_no_global_file_still_resolves_the_default(
        tmp_path, monkeypatch):
    """The other half: no global answer at all still resolves cleanly to the
    built-in default, and the repo is not left reporting `upgradeNeeded` for
    a key `upgrade_config` chose not to write. `upgradeNeeded` is `schema <
    SCHEMA_CURRENT` and never compares key sets, so this is a fact about
    `upgrade_config`'s own stamp, checked directly."""
    _global(tmp_path, monkeypatch, contents=None)  # no global file at all
    root = crew_fixtures.make_repo(tmp_path, config={"schema": 2, "tier": 0})
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "upgraded"
    upgraded = json.loads((root / ".crew" / "config.json")
                          .read_text(encoding="utf-8"))
    assert upgraded["schema"] == crew_state.SCHEMA_CURRENT

    resolved = crew_config.resolve_config(str(root))
    assert resolved["pm"]["authority"] == crew_state.AUTHORITY_DEFAULT
    assert resolved["qa"]["order"] == crew_state.QA_DEFAULTS["order"]
    assert resolved["dev"]["provider"] == crew_state.DEV_DEFAULTS["provider"]

    # And the trigger that would send someone back to `/crew:upgrade` does
    # not fire on a config this migration already brought current --
    # `upgradeNeeded` is `schema < SCHEMA_CURRENT` alone, never a key-set
    # comparison, so a globally-settable leaf this run chose not to write
    # cannot make an already-upgraded repo look unmigrated.
    state = crew_config.layered_state(str(root))
    fired = crew_state.evaluate_triggers(state)
    assert "upgradeNeeded" not in fired


def test_resolve_config_malformed_global_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "global-config.json"
    path.write_text("{ not json, half-edited", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(
        tmp_path, config={"tracker": "sdp"}, git=False)

    # Must not raise, and must resolve exactly as if the global file were
    # absent -- crew_upgrade._read_config_strict's reasoning applied to the
    # global layer instead of the repo one.
    resolved = crew_config.resolve_config(str(root))
    assert resolved["tracker"] == "sdp"
    assert resolved["pm"] == crew_state.PM_DEFAULTS
    # The broken file itself is left alone -- nothing in this module writes
    # the global layer, ever.
    assert path.read_text(encoding="utf-8") == "{ not json, half-edited"


def test_resolve_config_global_that_is_a_json_array_is_ignored(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)
    path = tmp_path / "global-config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    resolved = crew_config.resolve_config(str(root))
    expected = crew_config.default_config()
    del expected["schema"]
    assert {k: v for k, v in resolved.items() if k != "schema"} == expected
    assert "schema" not in resolved


# --- the global/repo split: a repo-only key takes effect NOWHERE -----------
#
# The 2026-09-05 rule, in tests. Before it, a global `tracker` or
# `graph.obsidian.dir` was inherited by every repo that did not override it,
# so setting a vault path once quietly gave every repository on the machine a
# board that did not describe it -- a reasonable-looking mistake that failed
# silently, which is the worst combination available.


def test_a_repo_only_key_in_the_global_file_takes_effect_nowhere(
        tmp_path, monkeypatch):
    """Every repo-only key at once, against a repo that overrides none of
    them. Each must resolve to the BUILT-IN default, not the global value."""
    _global(tmp_path, monkeypatch, contents={
        "tracker": "jira",
        "jira": {"project": "NOPE"},
        "tier": 3,
        "roles": ["explorer", "dba"],
        "verifyGate": False,
        "graph": {"out": "somewhere-else",
                  "obsidian": {"enabled": True, "dir": "/someone/vault"}},
        "platform": {"os": "linux"},
        "obsidian": {"boardDir": "Boards/wrong"},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    resolved = crew_config.resolve_config(str(root))
    built_in = crew_config.default_config()

    for key in ("tracker", "jira", "tier", "roles", "verifyGate", "graph",
                "platform", "obsidian"):
        assert resolved[key] == built_in[key], key


def test_a_globally_ignored_key_is_reported_rather_than_failing_silently(
        tmp_path, monkeypatch):
    """A key that quietly does nothing is worse than one refused out loud, so
    the drop is a finding rather than an implementation detail."""
    path = _global(tmp_path, monkeypatch, contents={
        "graph": {"obsidian": {"dir": "/someone/vault"}},
        "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    detail = {f["kind"]: f["detail"]
              for f in crew_config.inspect_global(str(root), str(path))
              ["findings"]}["repo-keys"]

    assert "graph" in detail
    assert "IGNORED" in detail, "the wording must not still say `inherits`"
    assert "inherit" not in detail


def test_the_filter_reports_a_nested_stray_a_top_level_diff_cannot_see(
        tmp_path, monkeypatch):
    """`graph.obsidian.dir` under an otherwise-plausible block is the exact
    mistake this finding exists to name."""
    kept, ignored = crew_config.filter_global({
        "qa": {"provider": "codex", "boardDir": "Boards/x"},
        "pm": {"authority": "act", "maxDispatches": 9},
    })
    # `pm` is admitted as a WHOLE block: maxDispatches is a fact about the
    # machine doing the dispatching. `qa.boardDir` is the stray -- a tracker
    # path is a fact about one checkout and cannot be set for every repo.
    assert kept == {"qa": {"provider": "codex"},
                    "pm": {"authority": "act", "maxDispatches": 9}}
    assert ignored == ["qa.boardDir"]


def test_the_model_table_still_layers_globally(tmp_path, monkeypatch):
    """The filter drops repo facts, not the model table -- which reviewer is
    installed here is exactly the kind of thing a global file is FOR."""
    _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex", "fallback": "claude-opus-9",
               "roles": {"review": {"provider": "codex",
                                    "model": "gpt-5.6-luna"}}},
        "dev": {"roles": {"developer": {"provider": "codex",
                                        "model": "gpt-6-astra"}}},
        "memory": {"mode": "vault", "vaultPath": "/home/me/vault"},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["qa"]["provider"] == "codex"
    assert resolved["qa"]["fallback"] == "claude-opus-9"
    assert resolved["qa"]["roles"]["review"]["model"] == "gpt-5.6-luna"
    assert resolved["dev"]["roles"]["developer"]["model"] == "gpt-6-astra"
    # BOTH memory keys are global as of 0.16.0 -- one vault per person, and a
    # person who keeps their memory in a vault keeps it there everywhere.
    # The context hook's keys beside them come from the repo defaults.
    assert resolved["memory"] == {"mode": "vault",
                                  "vaultPath": "/home/me/vault",
                                  "inject": True,
                                  "recall": {"vaults": [], "maxChars": 800}}


@pytest.mark.parametrize("dotted", ["memory.inject", "memory.recall.vaults",
                                    "memory.recall.maxChars"])
def test_the_context_hook_memory_keys_are_repo_only(dotted):
    """crew_context.py reads the repo's file and no other layer, so a global
    value for these would be accepted and then do nothing."""
    assert crew_config.is_global_path(dotted) is False


def test_memory_mode_is_globally_settable_and_the_template_ships_it():
    assert "mode" in crew_config.default_global_config()["memory"]
    assert crew_config.is_global_path("memory.mode") is True


def test_graph_obsidian_never_reaches_a_resolved_config(tmp_path, monkeypatch):
    """0.16.13 removed the Obsidian export outright. The key was previously
    consent-gated rather than absent, so an old global config on a real
    machine can still carry it -- including with `confirmed: true`, which
    used to mean something. It must not survive into a resolved config under
    any spelling, and it must still be refused on the write path.

    Asserting absence rather than a false-y value is the point. A key that
    resolves to `{"enabled": false}` reads as a feature switched off, and the
    next person to look turns it on."""
    path = _global(tmp_path, monkeypatch, contents={
        "graph": {"obsidian": {"enabled": True, "dir": "/v",
                               "confirmed": True}}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    # Read path: hand-written into the global file by any means at all.
    resolved = crew_config.resolve_config(str(root))
    assert "obsidian" not in resolved["graph"]
    # The rest of the graph block is unharmed by the drop.
    assert resolved["graph"]["mode"] == "code-only"

    # Write path: still refused by name, and the file is left exactly as it
    # was. `graph.*` is repo scope entirely, so this holds for a key that no
    # longer exists just as it did for one that did.
    before = path.read_bytes()
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config(
            {"graph.obsidian.confirmed": True}, str(path))
    assert path.read_bytes() == before
    assert crew_config.is_global_path("graph.obsidian.confirmed") is False


def test_write_and_read_admit_exactly_the_same_paths():
    """What the global file may WRITE is exactly what the global layer may
    SUPPLY. Two rules with one definition, or they drift and the drift is
    silent -- a walkthrough offering a key the resolver discards."""
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        assert crew_config.is_global_path(path) is True, path
    for path in ("tracker", "jira.project", "graph.out", "tier", "roles",
                 "schema", "platform.os", "verify", "codemap.dir",
                 "graph.obsidian.confirmed"):
        assert crew_config.is_global_path(path) is False, path
    # The whole `pm` block is global, siblings included -- see the
    # default_global_config docstring for why each one is a machine or
    # person fact rather than a checkout fact.
    assert crew_config.is_global_path("pm.maxDispatches") is True


def test_a_pin_for_a_role_this_release_does_not_name_survives_the_filter():
    """`dev.roles` is an open table. A filter that only admitted four
    hardcoded role names would silently drop the fifth."""
    kept, ignored = crew_config.filter_global(
        {"dev": {"roles": {"house-style-cop": {"provider": "codex"}}}})
    assert kept["dev"]["roles"]["house-style-cop"] == {"provider": "codex"}
    assert ignored == []  # pylint: disable=use-implicit-booleaness-not-comparison
    assert crew_config.is_global_path("dev.roles.house-style-cop.model")


def test_explain_credits_no_layer_for_a_value_the_filter_dropped(
        tmp_path, monkeypatch):
    """Explaining an effective value from a layer the resolver would have
    discarded is how a source column comes to name a key that does nothing."""
    path = _global(tmp_path, monkeypatch, contents={"qa": {"boardDir": "B/x"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    rows = crew_config.explain_config(str(root), str(path))
    assert all(row["source"] != "global" for row in rows)


def test_an_empty_dict_in_the_repo_does_not_claim_a_global_value(
        tmp_path, monkeypatch):
    """The live defect. `/crew:upgrade` writes `dev.roles: {}` into every
    repo it migrates, so the repo MENTIONS the key while supplying nothing:
    `merge_defaults` iterates `supplied.items()`, and an empty dict
    contributes no keys, so the global value survives untouched.

    Crediting `repo` there is the same class of wrong answer the source
    column was built to prevent -- it understates what the machine-wide file
    is deciding, which is exactly how the `pm.authority` incident went
    unnoticed.
    """
    pins = {"developer": {"provider": "codex", "model": "gpt-6-astra"}}
    path = _global(tmp_path, monkeypatch, contents={"dev": {"roles": pins}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT,
                          "dev": {"roles": {}}}, git=False)

    rows = {r["path"]: r for r in crew_config.explain_config(str(root),
                                                             str(path))}

    assert rows["dev.roles"]["value"] == pins, "the global pins must survive"
    assert rows["dev.roles"]["source"] == "global"


def test_a_dict_both_layers_contribute_to_names_both(tmp_path, monkeypatch):
    """The other half of the same lie. Merging two dicts is not a contest one
    of them wins -- the keys combine -- so naming a single layer hides that
    the other is supplying part of the effective value."""
    path = _global(tmp_path, monkeypatch, contents={
        "dev": {"roles": {"security": {"provider": "codex"}}}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT,
                          "dev": {"roles": {"developer": {"provider": "codex"}}}},
        git=False)

    rows = {r["path"]: r for r in crew_config.explain_config(str(root),
                                                             str(path))}

    assert set(rows["dev.roles"]["value"]) == {"developer", "security"}
    assert rows["dev.roles"]["source"] == "repo+global"


def test_a_populated_repo_dict_over_an_absent_global_is_still_repo(
        tmp_path, monkeypatch):
    """The control. Fixing the empty-dict case must not stop crediting a repo
    that genuinely did supply the value."""
    pins = {"developer": {"provider": "codex", "model": "gpt-6-astra"}}
    path = _global(tmp_path, monkeypatch, contents={})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT,
                          "dev": {"roles": pins}}, git=False)

    rows = {r["path"]: r for r in crew_config.explain_config(str(root),
                                                             str(path))}

    assert rows["dev.roles"]["source"] == "repo"


def test_explain_credits_the_global_layer_for_a_value_it_really_supplied(
        tmp_path, monkeypatch):
    """The other half, and the one the incident was about: a key the filter
    ADMITS has to be credited to `global`, or the source column understates
    what the machine-wide file is deciding."""
    path = _global(tmp_path, monkeypatch,
                   contents={"pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    rows = crew_config.explain_config(str(root), str(path))
    row = next(r for r in rows if r["path"] == "pm.maxDispatches")
    assert row["source"] == "global"
    assert row["value"] == 9


# --- resolve_config's structural schema exemption --------------------------


def test_resolve_config_schema_never_comes_from_the_global_layer(
        tmp_path, monkeypatch):
    """The exact case CI caught: a global config carrying `schema` must not
    leak into a repo that does not have its own -- an unmigrated v1 repo
    must not read as current just because someone's global file says 2."""
    _global(tmp_path, monkeypatch, contents={"schema": 1})
    root = crew_fixtures.make_repo(
        tmp_path, config={"tier": 0, "roles": []}, git=False)  # no schema key

    resolved = crew_config.resolve_config(str(root))

    assert "schema" not in resolved
    assert resolved.get("schema") != 1


def test_resolve_config_schema_comes_from_the_repo_file_when_present(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2}, git=False)
    # 2, not SCHEMA_CURRENT: the point is that the REPO FILE's own number is
    # what comes back, whatever this release's current one happens to be.
    assert crew_config.resolve_config(str(root))["schema"] == 2


def test_heal_writes_the_repo_file_not_the_global_one(tmp_path, monkeypatch):
    """heal_config recreates .crew/config.json only -- the global layer is
    never read for the decision and never written, regardless of whether it
    exists, is missing, or is broken."""
    global_path = _global(tmp_path, monkeypatch,
                          contents={"tracker": "jira"})
    before = global_path.read_bytes()
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.template_config()
    assert "missing" in message
    assert global_path.read_bytes() == before
    written = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    # The repo file gets built-in defaults, NOT the global tracker override --
    # heal_config calls template_config() (T-0050), never resolve_config().
    assert written["tracker"] == "files"


# --- layered_state: the collect() + resolve_config composition point ------
#
# crew_state.collect takes a plain cfg_override argument rather than
# importing this module itself -- crew_config already imports crew_state,
# so the reverse would be a real cyclic import. layered_state is where the
# two are actually wired together; these tests exercise that end to end,
# the way pm_brief.py's SessionStart brief does.


def test_layered_state_applies_a_global_override_for_a_crew_repo(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch,
            contents={"pm": {"authority": "act", "maxDispatches": 9}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT,
                          "tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["isCrew"] is True
    assert got["pm"]["authority"] == "act"
    assert got["pm"]["maxDispatches"] == 9


def test_layered_state_never_lets_a_global_file_make_a_plain_repo_crew(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch,
           contents={"tracker": "jira", "pm": {"maxDispatches": 9}})
    plain = tmp_path / "plain"
    plain.mkdir()

    got = crew_config.layered_state(str(plain))

    assert got["isCrew"] is False
    assert got["tracker"] is None
    assert got["triggers"] == []


def test_layered_state_schema_is_not_masked_by_the_global_layer(tmp_path, monkeypatch):
    """resolve_config's built-in-defaults layer always supplies
    SCHEMA_CURRENT, so schema must come from the raw repo file regardless --
    an unmigrated v1 repo must not read as current just because a global
    file exists on the machine."""
    _global(tmp_path, monkeypatch, contents={"pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["schema"] == 1
    assert "upgradeNeeded" in got["triggers"]


def test_layered_state_survives_a_malformed_global_file(tmp_path, monkeypatch):
    path = tmp_path / "global-config.json"
    path.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT, "tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["isCrew"] is True
    assert got["pm"]["maxDispatches"] == 3  # built-in default, global ignored


def test_layered_state_fills_in_a_built_in_default_the_raw_repo_file_omits(
        tmp_path):
    """With no global file, layered_state still differs from plain
    crew_state.collect for a repo config that omits a key -- resolve_config
    fills it from the built-in default, where raw collect() would report
    None. That is the layering working, not a bug to reconcile away."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT, "tier": 0, "roles": []})  # no tracker

    assert crew_state.collect(str(root))["tracker"] is None
    assert crew_config.layered_state(str(root))["tracker"] == "files"


# --- explain_config: the source column -------------------------------------


def _sources(rows):
    return {row["path"]: (row["value"], row["source"]) for row in rows}


def test_explain_names_the_layer_that_decided_each_value(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex"}, "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"qa": {"provider": "copilot"}}, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))

    assert got["qa.provider"] == ("copilot", "repo")
    assert got["pm.authority"] == ("act", "global")
    assert got["dev.provider"] == ("claude", "default")


def test_explain_reports_the_pm_regression_out_loud(tmp_path, monkeypatch):
    """The incident: a global file with tier, roles, qa and sdp but NO pm
    block resolved every repo to report-only while the user believed the PM
    was autonomous. Nothing surfaced it, because every file was valid."""
    path = _global(tmp_path, monkeypatch, contents={
        "tier": 2, "roles": ["explorer"], "qa": {"provider": "codex"},
        "sdp": {"closeOnDone": True}})
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 2}, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))
    assert got["pm.authority"] == ("report-only", "default")

    report = crew_config.inspect_global(str(root), str(path))
    kinds = {f["kind"]: f["detail"] for f in report["findings"]}
    assert "pm.authority" in kinds["missing-keys"]
    assert "report-only" in kinds["authority"] and "default" in kinds["authority"]


def test_explain_ignores_a_scalar_where_a_block_belongs(tmp_path, monkeypatch):
    """merge_defaults discards it, so the layer did NOT supply the value --
    and a source column that said otherwise would be worse than none."""
    path = _global(tmp_path, monkeypatch, contents={"pm": "act"})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))
    assert got["pm.authority"] == ("report-only", "default")


def test_explain_works_with_no_repo_at_all(tmp_path, monkeypatch):
    """/crew:config is reachable standalone, for a user with no repo in mind."""
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    got = _sources(crew_config.explain_config(str(tmp_path / "nowhere"), str(path)))
    assert got["pm.authority"] == ("act", "global")


# --- inspect_global: what /crew:upgrade reports -----------------------------


def _kinds(root, path):
    return [f["kind"] for f in crew_config.inspect_global(root, path)["findings"]]


def test_inspect_reports_an_absent_global_file(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert "absent" in _kinds(str(root), str(path))


def test_inspect_reports_a_global_file_that_does_not_parse(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents=None)
    path.write_text("{ half-edited", encoding="utf-8")
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert "unreadable" in _kinds(str(root), str(path))


def test_inspect_reports_repo_keys_and_an_inert_schema(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "schema": 2, "tracker": "jira", "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    kinds = {f["kind"]: f["detail"]
             for f in crew_config.inspect_global(str(root), str(path))["findings"]}
    assert "tracker" in kinds["repo-keys"]
    assert "inert-schema" in kinds


def test_inspect_never_writes_anything(tmp_path, monkeypatch):
    """upgrade.md's step 5 is "Report - do not resolve", and this is the
    strongest version of that rule: the file is outside the repo."""
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    before = path.read_bytes()
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    crew_config.inspect_global(str(root), str(path))
    assert path.read_bytes() == before


# --- writing the global file -----------------------------------------------


def test_a_write_merges_and_preserves_unknown_keys(tmp_path, monkeypatch):
    """A walkthrough that asks about six settings must not cost the seventh."""
    path = _global(tmp_path, monkeypatch, contents={
        "tracker": "jira", "somethingNobodyHereKnows": {"a": 1},
        "pm": {"authority": "report-only", "quietLines": 3}})

    merged, changes = crew_config.write_global_config(
        {"pm.authority": "act"}, str(path))

    assert merged["tracker"] == "jira"
    assert merged["somethingNobodyHereKnows"] == {"a": 1}
    assert merged["pm"]["quietLines"] == 3
    assert merged["pm"]["authority"] == "act"
    assert json.loads(path.read_text(encoding="utf-8")) == merged
    assert [c["path"] for c in changes] == ["pm.authority"]


def test_a_write_refuses_a_key_that_describes_a_repository(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    before = path.read_bytes()
    for repo_key in ("tracker", "jira.project", "graph.out", "tier", "roles"):
        with pytest.raises(crew_config.GlobalWriteRefused) as caught:
            crew_config.write_global_config({repo_key: "x"}, str(path))
        assert repo_key in str(caught.value)
    assert path.read_bytes() == before


def test_obsidian_confirmed_is_not_settable_from_a_guided_flow(tmp_path, monkeypatch):
    """Consent to write into the user's own notes outside the repo, not a
    capability. Un-grantable here by construction, not by remembering."""
    path = _global(tmp_path, monkeypatch, contents={})
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config(
            {"graph.obsidian.confirmed": True}, str(path))


def test_a_widening_of_authority_is_always_marked(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "pm": {"authority": "report-only"}})
    _, changes = crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert changes[0]["widens"] is True

    # Narrowing is not a widening, and neither is a no-op.
    path.write_text(json.dumps({"pm": {"authority": "act"}}), encoding="utf-8")
    _, narrowing = crew_config.plan_global_write(
        {"pm.authority": "report-only"}, str(path))
    assert narrowing[0]["widens"] is False
    _, nothing = crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert not nothing


def test_every_authority_transition_is_classified(tmp_path, monkeypatch):
    """The full matrix, not the two transitions that existed at two tiers.

    Both new rows caught a real defect in the `== "act"` form this replaced:
    `act -> autonomous` computed False (the widest grant crew offers, shipping
    unannounced) and `autonomous -> act` computed True (a NARROWING reported as
    a widening, which is how a warning becomes noise). Enumerated as data so a
    fourth tier cannot be added without this failing until the row is written.
    """
    path = _global(tmp_path, monkeypatch, contents={})
    cases = [
        ("report-only", "act", True),
        ("report-only", "autonomous", True),
        ("act", "autonomous", True),
        ("autonomous", "act", False),
        ("autonomous", "report-only", False),
        ("act", "report-only", False),
    ]
    for before, after, expected in cases:
        path.write_text(json.dumps({"pm": {"authority": before}}),
                        encoding="utf-8")
        _, changes = crew_config.plan_global_write(
            {"pm.authority": after}, str(path))
        assert changes[0]["widens"] is expected, (
            f"{before} -> {after} should be "
            f"{'a widening' if expected else 'no widening'}")


def test_an_unreadable_authority_widens_into_anything(tmp_path, monkeypatch):
    """Fail-safe direction. A `before` crew cannot parse ranks lowest, so every
    real tier above it reports as a widening rather than as a quiet no-op."""
    path = _global(tmp_path, monkeypatch, contents={
        "pm": {"authority": "ACT-ish typo"}})
    for after in ("act", "autonomous"):
        _, changes = crew_config.plan_global_write(
            {"pm.authority": after}, str(path))
        assert changes[0]["widens"] is True


def test_the_widening_warning_names_the_tier_it_grants(tmp_path, monkeypatch,
                                                       capsys):
    """Codex round 1 on this branch, and the same bug class as the one the
    branch fixes: the `!` line said "widens to `act`" whatever the target was.
    Setting `autonomous` therefore warned about the wrong tier AND omitted the
    only thing that tier adds - that the PM stops asking you to choose. A
    warning that under-describes the grant is what this marker exists to
    prevent."""
    path = _global(tmp_path, monkeypatch, contents={
        "pm": {"authority": "report-only"}})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'pm.authority="autonomous"']) == 0
    out = capsys.readouterr().out
    assert "widens to `autonomous`" in out
    assert "widens to `act`" not in out
    assert "stop asking you to choose" in out

    assert crew_config.main(
        ["--global-path", str(path), "--set", 'pm.authority="act"']) == 0
    act_out = capsys.readouterr().out
    assert "widens to `act`" in act_out
    assert "stop asking you to choose" not in act_out


def test_every_authority_has_a_widening_note():
    """Total by construction. A tier added without a note must be a KeyError at
    the point of use, never a warning that describes a different tier."""
    assert set(crew_config._WIDENING_NOTES) == set(crew_state.AUTHORITIES)


def test_ticket_granularity_is_settable_in_both_layers(tmp_path, monkeypatch):
    """It rides in on `pm`, the block already admitted whole -- so this is the
    check that the invariant actually held, rather than that it was intended."""
    assert crew_config.is_global_path("pm.ticketGranularity") is True
    path = _global(tmp_path, monkeypatch, contents={})
    merged, changes = crew_config.plan_global_write(
        {"pm.ticketGranularity": "session"}, str(path))
    assert merged["pm"]["ticketGranularity"] == "session"
    assert changes[0]["widens"] is False
    kept, ignored = crew_config.filter_global(
        {"pm": {"ticketGranularity": "change"}})
    assert kept == {"pm": {"ticketGranularity": "change"}}
    assert ignored == []


def test_a_plan_writes_nothing(tmp_path, monkeypatch):
    """Dry run is the default, and it is what the user says yes to."""
    path = _global(tmp_path, monkeypatch, contents=None)
    crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert not path.exists()


def test_a_write_creates_the_directory_when_there_is_no_global_file(
        tmp_path, monkeypatch):
    path = tmp_path / "fresh" / "crew" / "config.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    merged, changes = crew_config.write_global_config({"pm.authority": "act"})
    assert merged == {"pm": {"authority": "act"}}
    assert changes[0]["before"] is None
    assert json.loads(path.read_text(encoding="utf-8")) == merged


def test_a_written_global_file_does_not_leak_a_repo_key(tmp_path, monkeypatch):
    """Every key the walkthrough can write is a machine fact, so a global file
    it produced cannot carry a repo one into a repo that did not ask."""
    path = tmp_path / "written.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    # Null where the machine layer gives null a meaning (an open key), the
    # first value of its tuple where it does not (T-0075: null is refused for
    # an enum key at the machine layer).
    updates = {p: None if crew_config.enum_values(p) is None
               else crew_config.enum_values(p)[0] for p in
               crew_config.leaf_paths(crew_config.default_global_config())}
    merged, _ = crew_config.write_global_config(updates)
    root = crew_fixtures.make_repo(tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)
    resolved = crew_config.resolve_config(str(root))
    assert resolved["tracker"] == "files"
    assert resolved["graph"]["out"] == crew_state.GRAPH_OUT_DEFAULT
    assert "schema" not in merged


# --- the CLI ---------------------------------------------------------------


def test_cli_set_is_a_dry_run_without_apply(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'pm.authority="act"']) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "pm.authority" in out
    assert "! pm.authority widens" in out
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_cli_apply_writes(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'qa.provider="codex"',
         "--apply"]) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "qa": {"provider": "codex"}}
    assert "wrote" in capsys.readouterr().out


def test_cli_refuses_a_repo_key_with_exit_two(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'tracker="jira"', "--apply"]) == 2
    assert "tracker" in capsys.readouterr().err


def test_cli_reporting_exits_zero_even_with_findings(tmp_path, monkeypatch, capsys):
    """A machine with no global config is a normal machine. /crew:upgrade
    reads this output, not its status."""
    path = _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert crew_config.main(
        ["--root", str(root), "--global-path", str(path), "--check-global"]) == 0
    assert "absent" in capsys.readouterr().out


def test_cli_explain_prints_a_source_column(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert crew_config.main(
        ["--root", str(root), "--global-path", str(path), "--explain"]) == 0
    out = capsys.readouterr().out
    assert "source" in out
    assert "pm.authority" in out and "global" in out


# --- _layer_supplies agrees with merge_defaults, by construction -----------
#
# `_layer_supplies` is a second implementation of `merge_defaults`' policy:
# it answers "which layer decided this value", which the merged result cannot
# be asked. Two implementations of one rule drift, and the drift is silent --
# the source column would name the wrong layer and nothing would fail. These
# tests pin them to each other by running both, rather than by asserting the
# mirror in a docstring.


_SENTINEL = "___layer_value___"


def _dig_or_missing(node, parts):
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return crew_config._MISSING  # pylint: disable=protected-access
        node = node[part]
    return node


def _layer_carrying(parts, value):
    """A config whose only content is `value` at the dotted path `parts`."""
    out = {}
    node = out
    for part in parts[:-1]:
        node[part] = {}
        node = node[part]
    node[parts[-1]] = value
    return out


def _decided_by_layer(defaults, layer, parts):
    """Ground truth: did the layer's value survive the real merge?"""
    merged = crew_state.merge_defaults(copy.deepcopy(defaults), layer)
    return _dig_or_missing(merged, parts) == _SENTINEL


@pytest.mark.parametrize(
    "path", sorted(crew_config.leaf_paths(crew_config.default_global_config())))
def test_layer_supplies_agrees_with_merge_defaults_on_every_global_leaf(path):
    """Every key the walkthrough can set, set by a layer, is credited to it."""
    defaults = crew_config.default_config()
    parts = tuple(path.split("."))
    layer = _layer_carrying(parts, _SENTINEL)
    # pylint: disable=protected-access
    assert (crew_config._layer_supplies(layer, parts, defaults)
            is _decided_by_layer(defaults, layer, parts))


def test_layer_supplies_agrees_when_the_layer_is_silent():
    """A layer that says nothing decides nothing, at every depth."""
    defaults = crew_config.default_config()
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        parts = tuple(path.split("."))
        # pylint: disable=protected-access
        assert crew_config._layer_supplies({}, parts, defaults) is False


def test_layer_supplies_agrees_on_the_scalar_over_dict_discard():
    """merge_defaults throws a scalar-over-dict away; so must the credit.

    This is the one rule of the two that is easy to get wrong, and getting it
    wrong reads as "global set qa" when the global file's `"qa": "codex"` was
    discarded and the built-in default is what actually applies.
    """
    defaults = crew_config.default_config()
    # `qa` holds a dict by default, so a scalar there is discarded whole.
    layer = {"qa": _SENTINEL}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa", "provider"),
                                       defaults) is False
    merged = crew_state.merge_defaults(copy.deepcopy(defaults), layer)
    assert merged["qa"] == defaults["qa"], "merge_defaults kept the scalar"


def test_layer_supplies_credits_a_whole_subtree_replacement():
    """Where the default holds no dict, the layer replaces the subtree.

    `merge_defaults` only recurses where BOTH sides hold a dict, so a layer
    supplying a block the defaults do not model wins outright -- and the
    credit has to follow, or a user-invented key would read as `default`.
    """
    defaults = {"pm": {"authority": "report-only"}}
    layer = {"custom": {"nested": _SENTINEL}}
    parts = ("custom", "nested")
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, parts, defaults) is True
    assert _decided_by_layer(defaults, layer, parts) is True


def test_layer_supplies_discards_a_scalar_named_at_a_block_path():
    """A layer naming a whole block with a scalar decides nothing there.

    The path here is `qa` itself, not a leaf under it. `leaf_paths` never
    yields such a path, so nothing else in this file exercises the last hop
    of `_layer_supplies` -- and an unexercised branch is how the mirror
    drifts from `merge_defaults` without a test noticing.
    """
    defaults = crew_config.default_config()
    layer = {"qa": _SENTINEL}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa",), defaults) is False
    assert _decided_by_layer(defaults, layer, ("qa",)) is False


def test_layer_supplies_credits_a_block_replaced_by_a_block():
    """A dict over a dict default is a real override, at the block path too."""
    defaults = crew_config.default_config()
    layer = {"qa": {"provider": _SENTINEL}}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa", "provider"),
                                       defaults) is True
    assert _decided_by_layer(defaults, layer, ("qa", "provider")) is True


# --- a per-role pin, layered ------------------------------------------------
#
# `/crew:model` tells a user to put a project's pin in the repo file and a
# person's in the global one, which only works if the two layer sensibly at
# the ROLE level. `merge_defaults` recurses to whatever depth both sides hold
# a dict, so they merge per key rather than the repo's object replacing the
# global's wholesale -- documented behaviour deserves a test, whichever way it
# turns out to go.


def test_a_repo_pin_merges_into_a_global_one_rather_than_replacing_it(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "dev": {"roles": {"developer": {"provider": "codex",
                                        "model": "gpt-5.6-sol"}}},
    })
    root = crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "dev": {"roles": {"developer": {"model": "gpt-6-astra"}}},
    }, git=False)

    resolved = crew_config.resolve_config(str(root))
    pin = resolved["dev"]["roles"]["developer"]

    assert pin["model"] == "gpt-6-astra"     # the repo decided the model
    assert pin["provider"] == "codex"        # and the global provider survived
    assert crew_state.resolve_role(resolved, "dev", "developer")["family"] \
        == "gpt"


def test_a_global_pin_reaches_a_role_the_repo_never_mentions(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "qa": {"roles": {"review": {"provider": "copilot",
                                    "model": "kimi-k2.7-code"}}},
    })
    root = crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT}, git=False)

    got = crew_state.resolve_role(crew_config.resolve_config(str(root)),
                                  "qa", "review")

    assert got["provider"] == "copilot"
    assert got["family"] == "kimi"
    assert got["source"] == "role-pin"


# --- a repo null must not shadow a global value ------------------------------
# `/crew:init` writes templates/config.template.json, which spells out EVERY
# key including the ones whose default is null. merge_defaults treated that
# null as a supplied value, so it beat the machine-global layer and the global
# file did nothing for any repo crew had ever initialised. Found by the Codex
# review of the `worktree.root` change; it affected five keys, not one.

_NULLABLE_GLOBAL_KEYS = (
    ("memory", "vaultPath"),
    ("worktree", "root"),
    ("qa", "codex", "model"),
    ("notify", "chatId"),
    ("secondOpinion", "model"),
    # T-0040 review round 2 FIX 1: the template pinned `auto` here.
    ("shellRoute", "mode"),
)


def _nest(parts, value):
    """{'a': {'b': value}} from ('a','b')."""
    out = value
    for part in reversed(parts):
        out = {part: out}
    return out


def _dig_plain(node, parts):
    for part in parts:
        node = node[part]
    return node


def _committed_template():
    with open(_TEMPLATE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def test_a_repo_null_does_not_shadow_a_global_value():
    """The bug, on every nullable key the global layer is allowed to carry.

    Parameterised over the real committed template rather than a hand-built
    dict, because the template IS the repo layer for every managed repo -- a
    test that built its own `{}` would pass while every real repo failed.
    """
    defaults = crew_config.default_config()
    template = _committed_template()
    for parts in _NULLABLE_GLOBAL_KEYS:
        assert _dig_plain(template, parts) is None, (
            f"{'.'.join(parts)} stopped being null in the template; this test's premise is "
            "gone and it needs rewriting, not deleting")
        wanted = "SET-BY-GLOBAL"
        global_cfg = _nest(parts, wanted)
        pruned = crew_config.without_null_shadows(template, global_cfg, defaults)
        merged = crew_state.merge_defaults(
            crew_state.merge_defaults(defaults, global_cfg), pruned)
        assert _dig_plain(merged, parts) == wanted, ".".join(parts)


def test_a_template_repo_inherits_the_machine_shell_route(tmp_path, monkeypatch):
    """T-0040 review round 2 FIX 1, its repro: set the machine-global
    `shellRoute.mode` to `wsl`, initialise a repo from the template, and read
    `resolve_config`. It returned `auto`: the template pinned it, so a repo
    owner who chose nothing overrode the machine owner who did."""
    _global(tmp_path, monkeypatch, contents={"shellRoute": {"mode": "wsl", "distro": "Debian"}})
    root = crew_fixtures.make_repo(tmp_path, config=_committed_template(), git=False)
    assert crew_config.resolve_config(str(root))["shellRoute"] == {"mode": "wsl", "distro": "Debian"}

    # A choice the repo owner did make still wins.
    chosen = copy.deepcopy(_committed_template())
    chosen["shellRoute"]["mode"] = "gitbash"
    other = crew_fixtures.make_repo(tmp_path / "other", config=chosen, git=False)
    assert crew_config.resolve_config(str(other))["shellRoute"]["mode"] == "gitbash"


def test_with_no_layer_setting_it_the_shell_route_reads_as_auto(tmp_path, monkeypatch):
    """Null in the repo layer and no machine file: `crew_shell.mode` reads the
    unset mode as `auto`, the behaviour the template used to spell out."""
    _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(tmp_path, config=_committed_template(), git=False)
    resolved = crew_config.resolve_config(str(root))
    assert crew_shell.mode(resolved) == ("auto", None)


def test_a_real_repo_value_still_beats_the_global():
    """The prune must not turn the layering upside down. `null` is the only
    thing that stops deciding; a value the repo actually set still wins."""
    defaults = crew_config.default_config()
    for parts in _NULLABLE_GLOBAL_KEYS:
        repo_cfg = _nest(parts, "SET-BY-REPO")
        global_cfg = _nest(parts, "SET-BY-GLOBAL")
        pruned = crew_config.without_null_shadows(repo_cfg, global_cfg, defaults)
        merged = crew_state.merge_defaults(
            crew_state.merge_defaults(defaults, global_cfg), pruned)
        assert _dig_plain(merged, parts) == "SET-BY-REPO", ".".join(parts)


def test_a_repo_null_survives_when_no_global_supplies_that_key():
    """The narrowing that keeps `null` meaningful.

    A blanket "null means unset" would break `context.reserveTokens: null`,
    which the README documents as the way to turn the headroom floor OFF -- it
    would silently become the 100000 default. The prune only fires where the
    global layer actually supplies something, so with no global file nothing
    is touched at all.
    """
    template = _committed_template()
    pruned = crew_config.without_null_shadows(template, {})
    assert pruned == template
    assert pruned["context"]["reserveTokens"] ==         template["context"]["reserveTokens"]


def test_without_null_shadows_does_not_mutate_its_input():
    """It is handed `crew_state.load_config`'s dict, which callers reuse."""
    defaults = crew_config.default_config()
    repo_cfg = {"worktree": {"root": None}, "tracker": "files"}
    before = copy.deepcopy(repo_cfg)
    crew_config.without_null_shadows(
        repo_cfg, {"worktree": {"root": "G:"}}, defaults)
    assert repo_cfg == before


def test_only_autoclear_is_in_scope_for_null_shadowing_under_context():
    """`null_shadows` walks `default_global_config()` leaves only, so a
    repo-only path can never be pruned however null it is. Asserted rather
    than assumed, because the narrowing above depends on it.

    This test used to assert that NO `context.` leaf was global. 0.19.10 made
    `context.autoClear` global deliberately, so the blanket claim is now false
    -- and the honest replacement is the narrower one, not a deleted test. The
    case the narrowing exists to protect is `context.reserveTokens: null`,
    which means "off" and must survive; it is repo-only, so it is untouched,
    and that is now asserted directly rather than implied by the blanket.

    `context.autoClear.windowTitle: null` in a repo IS now shadowable, and
    that is the intent: `/crew:init` writes every key including the null ones,
    so without this a machine-wide window title would be silently overridden
    by a template value in every initialised repo -- which is the exact bug
    `null_shadows` was written for, arriving at a new key."""
    leaves = crew_config.leaf_paths(crew_config.default_global_config())
    context_leaves = [p for p in leaves if p.startswith("context.")]
    assert context_leaves == ["context.autoClear.enabled",
                              "context.autoClear.method",
                              "context.autoClear.windowTitle",
                              "context.autoClear.command",
                              "context.autoClear.delaySeconds",
                              "context.autoClear.minHandoffLines",
                              "context.autoClear.onlyRepos",
                              "context.autoClear.onlySessions",
                              "context.autoClear.wrapUp"]
    assert "context.autoClear.unsafeFocus" not in leaves
    assert not [p for p in leaves if p.startswith("emergency.")]

    # The protected case, directly: a repo null over a repo-only path is left
    # alone even with a global file present, so `reserveTokens: null` still
    # means "off" rather than silently becoming the 100000 default.
    repo_cfg = {"context": {"reserveTokens": None, "autoClear":
                            {"windowTitle": None}}}
    global_cfg = {"context": {"autoClear": {"windowTitle": "Claude"}}}
    shadows = crew_config.null_shadows(repo_cfg, global_cfg)
    assert shadows == ["context.autoClear.windowTitle"]
    pruned = crew_config.without_null_shadows(repo_cfg, global_cfg)
    assert "reserveTokens" in pruned["context"]
    assert pruned["context"]["reserveTokens"] is None
    assert "windowTitle" not in pruned["context"]["autoClear"]


def test_resolve_config_inherits_a_global_through_the_init_template(
        tmp_path, monkeypatch):
    """END TO END, through `resolve_config`, with the REAL /crew:init template
    as the repo file. The helper tests above pass with the prune deleted from
    `resolve_config` -- they exercise `without_null_shadows` directly and never
    touch the wiring. This is the test that fails when the call site goes.

    That gap is the point: the first version of this suite tested the helper
    and called the bug fixed, and a sabotage run (remove the call from
    `resolve_config`, re-run) came back green.
    """
    _global(tmp_path, monkeypatch, contents={
        "worktree": {"root": "G:" + os.sep + "shared"},
        "memory": {"vaultPath": "V:" + os.sep + "vault"},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config=_committed_template(), git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["worktree"]["root"] == "G:" + os.sep + "shared"
    assert resolved["memory"]["vaultPath"] == "V:" + os.sep + "vault"


def test_resolve_config_lets_the_repo_override_the_global_it_now_inherits(
        tmp_path, monkeypatch):
    """The other side of the same wiring: the prune must not make the repo
    layer unable to win. A repo that names a real value still decides."""
    _global(tmp_path, monkeypatch, contents={
        "worktree": {"root": "G:" + os.sep + "shared"}})
    cfg = _committed_template()
    cfg["worktree"]["root"] = "R:" + os.sep + "mine"
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["worktree"]["root"] == "R:" + os.sep + "mine"


def test_explain_config_credits_global_not_repo_for_an_inherited_null(
        tmp_path, monkeypatch):
    """The report has to apply the same rule as the run.

    `/crew:config`'s source column is built from `_layer_supplies` against the
    repo layer. If only `resolve_config` pruned, the column would say `repo`
    for a value the run took from `global` -- the precise failure this
    module's own scar tissue is about ("mentioning a key is not deciding its
    value").
    """
    path = _global(tmp_path, monkeypatch, contents={
        "worktree": {"root": "G:" + os.sep + "shared"}})
    root = crew_fixtures.make_repo(
        tmp_path, config=_committed_template(), git=False)

    rows = crew_config.explain_config(str(root), path=str(path))
    row = next(r for r in rows if r["path"] == "worktree.root")

    assert row["value"] == "G:" + os.sep + "shared"
    assert row["source"] == "global", row


def test_explain_config_reports_autoclear_only_repos_from_the_global_layer_only(
        tmp_path):
    """Review round 2 (crew-1.0-r3-autocycle, lane fix4 finding 4).

    `crew_autocycle.settings` and `auto-clear.ps1` read onlyRepos /
    onlySessions from the machine-global file ONLY -- a repo's own copy is
    never consulted. `explain_config` applied the same repo-over-global
    precedence as every other key, so a repo that listed itself was
    credited `source: repo`, and `/crew:config --show` could claim
    auto-clear was restricted to that repo while the hooks left it armed
    everywhere the machine opt-in reaches. The report must agree with the
    run: source is never `repo`, the value is the global one, and a
    repo-level value is flagged rather than folded in."""
    global_path = tmp_path / "global-config.json"
    global_path.write_text(
        json.dumps({"context": {"autoClear": {"enabled": True}}}), encoding="utf-8")
    root = tmp_path / "repo"
    root_cfg = {"schema": crew_state.SCHEMA_CURRENT,
                "context": {"autoClear": {"onlyRepos": [str(root)]}}}
    crew_fixtures.make_repo(tmp_path, config=root_cfg, git=False)

    rows = {r["path"]: r for r in
            crew_config.explain_config(str(root), path=str(global_path))}
    row = rows["context.autoClear.onlyRepos"]

    assert row["source"] != "repo" and row["source"] != "repo+global"
    assert row["value"] is None
    assert row["repoIgnored"] == [str(root)]

    settings = crew_autocycle.settings(str(root), global_path=str(global_path))
    assert settings["onlyRepos"] is None
    assert settings["onlyRepos"] == row["value"]


# --- T-0005: the `environments` block ----------------------------------------
#
# `environments.nonProd` is REPO ONLY (what counts as non-production is a fact
# about the checkout, as `production.*` is); `environments.prodUnattended`
# ratchets across both layers and is true only when BOTH say the JSON literal
# `true`. Anything else -- absent, `false`, the string "true", `1`, `null` --
# is false, so upgrading grants nothing and a cloned repo cannot grant itself
# unattended production on a stranger's machine.

_PU_ABSENT = object()
_PU_VALUES = [_PU_ABSENT, False, True, "true", 1, None]
_PU_IDS = ["absent", "false", "true", "str-true", "one", "null"]


def _environments_layer(value):
    if value is _PU_ABSENT:
        return {}
    return {"environments": {"prodUnattended": value}}


def test_environments_defaults_grant_nothing(tmp_path):
    assert crew_config.default_config()["environments"] == {
        "nonProd": [], "prodUnattended": False}
    assert crew_config.default_global_config()["environments"] == {
        "prodUnattended": False}
    assert crew_state.ENVIRONMENTS_DEFAULTS == {
        "nonProd": [], "prodUnattended": False}
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "environments": crew_config.default_config()["environments"]},
        git=False)
    global_path = tmp_path / "global.json"
    global_path.write_text(json.dumps(
        {"environments": crew_config.default_global_config()["environments"]}),
        encoding="utf-8")
    row = crew_config.resolve_ratcheted(
        str(root), "environments.prodUnattended", str(global_path))
    assert row["effective"] is False


@pytest.mark.parametrize("global_value", _PU_VALUES, ids=_PU_IDS)
@pytest.mark.parametrize("repo_value", _PU_VALUES, ids=_PU_IDS)
def test_prod_unattended_ratchets(tmp_path, repo_value, global_value):
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config=dict(
        {"schema": crew_state.SCHEMA_CURRENT},
        **_environments_layer(repo_value)), git=False)
    global_path = tmp_path / "global.json"
    global_path.write_text(json.dumps(_environments_layer(global_value)),
                           encoding="utf-8")
    row = crew_config.resolve_ratcheted(
        str(root), "environments.prodUnattended", str(global_path))
    want = repo_value is True and global_value is True
    assert row["effective"] is want, (repo_value, global_value, row)


def test_global_non_prod_is_pruned_and_reported():
    kept, ignored = crew_config.filter_global(
        {"environments": {"nonProd": ["dev"], "prodUnattended": True}})
    assert kept == {"environments": {"prodUnattended": True}}
    assert ignored == ["environments.nonProd"]
    assert crew_config.is_global_path("environments.prodUnattended")
    assert not crew_config.is_global_path("environments.nonProd")


@pytest.mark.parametrize("block", [
    {"nonProd": "dev"}, {"nonProd": [""]}, {"nonProd": [1]},
    {"nonProd": None}, {"prodUnattended": "yes"}, [], None, "dev"],
    ids=["nonprod-string", "nonprod-blank", "nonprod-int", "nonprod-null",
         "prod-unattended-string", "list", "null", "string"])
def test_environments_block_problem(block):
    assert crew_config.environments_block_problem(block)


@pytest.mark.parametrize("block", [
    {}, {"nonProd": []}, {"nonProd": ["dev", "*-staging"]},
    {"prodUnattended": False}, {"nonProd": ["qa"], "prodUnattended": True}])
def test_environments_block_problem_accepts_a_real_block(block):
    assert crew_config.environments_block_problem(block) == ""


def test_layer_state_classifies_a_malformed_environments_block(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"environments": {"nonProd": "dev"}}),
                    encoding="utf-8")
    assert crew_config.layer_state(str(path), environments=True) == "corrupt"
    assert crew_config.layer_state(str(path)) == "ok"
    path.write_text(json.dumps({"environments": {"nonProd": ["dev"]}}),
                    encoding="utf-8")
    assert crew_config.layer_state(str(path), environments=True) == "ok"


def test_check_warns_when_non_prod_covers_a_require_human_environment(
        tmp_path, capsys):
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "environments": {"nonProd": ["stag*"]}}, git=False)
    (root / ".crew" / "verify.json").write_text(json.dumps({"environments": {
        "staging": {"requireHuman": True},
        "uat": {"requireHuman": True},
        "production": {"requireHuman": True}}}), encoding="utf-8")
    code = crew_config.main(["--root", str(root), "--check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "staging" in out and "requireHuman" in out, out
    assert "production" not in out, out
    assert "uat" not in out, out


def test_check_is_quiet_without_a_contradiction(tmp_path, capsys):
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "environments": {"nonProd": ["dev"]}}, git=False)
    (root / ".crew" / "verify.json").write_text(json.dumps({"environments": {
        "production": {"requireHuman": True}}}), encoding="utf-8")
    assert crew_config.main(["--root", str(root), "--check"]) == 0
    assert "requireHuman" not in capsys.readouterr().out


# --- T-0075: enum validation shared by both writers -------------------------

_BAD_ENUM_VALUES = [
    ("pm.authority", "bogus"),
    ("guards.forcePush", "yes"),
    ("install.policy", "always"),
    ("guards.prodDatabase", "write"),
    ("pm.ticketGranularity", "ticket"),
    ("qa.provider", "gpt"),
]


@pytest.mark.parametrize("dotted,value", _BAD_ENUM_VALUES)
def test_enum_key_outside_its_values_is_refused(tmp_path, dotted, value):
    path = tmp_path / "global.json"

    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.plan_global_write({dotted: value}, str(path))

    message = str(caught.value)
    assert dotted in message and repr(value) in message
    assert all(str(allowed) in message
               for allowed in crew_config.enum_values(dotted))


def _every_enum_value():
    keys = ["pm.authority", "pm.ticketGranularity", "qa.provider",
            "dev.provider"]
    keys += [k for k in crew_config.leaf_paths(crew_config.default_global_config())
             if crew_state.ratchet_spec(k) is not None]
    return [(key, value) for key in keys
            for value in crew_config.enum_values(key)]


@pytest.mark.parametrize("dotted,value", _every_enum_value())
def test_enum_key_inside_its_values_is_accepted(tmp_path, dotted, value):
    _, changes = crew_config.plan_global_write(
        {dotted: value}, str(tmp_path / "global.json"))

    assert [c["after"] for c in changes] in ([value], [])


def test_non_enum_key_keeps_accepting_any_json(tmp_path):
    _, changes = crew_config.plan_global_write(
        {"notify.chatId": "12345",
         "qa.roles": {"anything": {"provider": "codex", "x": [1]}}},
        str(tmp_path / "global.json"))

    # Review round 3: a role table is written entry by entry, so the other
    # pins in it survive; the entry itself is the unit.
    assert {c["path"] for c in changes} == {"notify.chatId", "qa.roles.anything"}


# --- T-0075: the one repo write path ----------------------------------------


def _repo(tmp_path, config=None, *, crlf=False):
    """A repo whose `.crew/config.json` holds `config` (defaults when None)."""
    cfg = crew_config.default_config() if config is None else config
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    text = json.dumps(cfg, indent=2) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    (root / ".crew" / "config.json").write_bytes(text.encode("utf-8"))
    return root


def _repo_bytes(root):
    return (root / ".crew" / "config.json").read_bytes()


@pytest.mark.parametrize("dotted,value", [
    ("platform.os", "linux"),
    ("schema", 3),
    ("scope.mode", "block"),
    ("scope.allowCliApproval", True),
    ("context.autoClear.onlyRepos", ["x"]),
    ("context.autoClear.onlySessions", ["y"]),
    ("autopilot.frobnicate", 1),
    ("context.autoClear.enabled", True),
    ("context.autoClear.wrapUp", True),
    ("resume.auto", True),
    # `0 == False` in Python; the readers test `is False`, so 0 vetoes nothing.
    ("context.autoClear.enabled", 0),
    ("resume.auto", 0),
    ("resume.auto", 0.0),
])
def test_repo_writer_refuses(tmp_path, dotted, value):
    root = _repo(tmp_path)
    before = _repo_bytes(root)

    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.write_repo_config(str(root), {dotted: value},
                                      str(tmp_path / "g.json"))

    assert dotted in str(caught.value) and " - " in str(caught.value)
    assert _repo_bytes(root) == before


@pytest.mark.parametrize("dotted", ["scope", "context", "context.autoClear",
                                    "platform", "guards"])
def test_repo_writer_refuses_a_whole_block(tmp_path, dotted):
    root = _repo(tmp_path)
    before = _repo_bytes(root)

    with pytest.raises(crew_config.RepoWriteRefused):
        crew_config.write_repo_config(str(root), {dotted: {}},
                                      str(tmp_path / "g.json"))

    assert _repo_bytes(root) == before


def test_repo_writer_accepts_a_veto(tmp_path):
    root = _repo(tmp_path)

    crew_config.write_repo_config(
        str(root), {"context.autoClear.enabled": False, "resume.auto": False},
        str(tmp_path / "g.json"))

    written = json.loads(_repo_bytes(root))
    assert (written["context"]["autoClear"]["enabled"],
            written["resume"]["auto"]) == (False, False)


@pytest.mark.parametrize("value,veto", [(False, True), (None, True), (0, False),
                                        (0.0, False), ("", False), ([], False)])
def test_is_repo_veto_is_identity_not_equality(value, veto):
    assert crew_config.is_repo_veto(value) is veto


def test_repo_write_merges_and_keeps_unknown_keys(tmp_path):
    cfg = crew_config.default_config()
    cfg["x-local"] = 1
    root = _repo(tmp_path, cfg)

    crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                  str(tmp_path / "g.json"))

    written = json.loads(_repo_bytes(root))
    assert (written["x-local"], written["tracker"]) == (1, "jira")


@pytest.mark.parametrize("make_crew_dir", [False, True])
def test_repo_write_refuses_without_a_config(tmp_path, capsys, make_crew_dir):
    root = tmp_path / "bare"
    root.mkdir()
    if make_crew_dir:
        (root / ".crew").mkdir()
    before = sorted(p.name for p in root.rglob("*"))

    code = crew_config.main(["--root", str(root), "--repo", "--apply",
                             "--global-path", str(tmp_path / "g.json"),
                             "--set", 'tracker="jira"'])

    err = capsys.readouterr().err
    assert code == 2
    assert "/crew:init" in err and "platform-sync" in err
    assert sorted(p.name for p in root.rglob("*")) == before


def test_repo_write_refuses_a_malformed_config(tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    (root / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    before = _repo_bytes(root)

    code = crew_config.main(["--root", str(root), "--repo", "--apply",
                             "--global-path", str(tmp_path / "g.json"),
                             "--set", 'tracker="jira"'])

    assert code == 2
    assert "heal" in capsys.readouterr().err
    assert _repo_bytes(root) == before


def test_repo_write_is_atomic(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    before = _repo_bytes(root)

    def _boom(_fd):
        raise OSError("disk full")
    monkeypatch.setattr(crew_config.os, "fsync", _boom)
    with pytest.raises(crew_config.RepoWriteRefused, match="disk full"):
        crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                      str(tmp_path / "g.json"))

    assert _repo_bytes(root) == before
    assert not list((root / ".crew").glob("config.json.*.tmp"))


def test_repo_write_preserves_crlf(tmp_path):
    root = _repo(tmp_path, crlf=True)

    crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                  str(tmp_path / "g.json"))

    raw = _repo_bytes(root)
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def _repo_with_global(tmp_path, repo_cfg_updates, global_cfg):
    cfg = crew_config.default_config()
    for dotted, value in repo_cfg_updates.items():
        crew_config._set_path(cfg, dotted.split("."), value)  # pylint: disable=protected-access
    root = _repo(tmp_path, cfg)
    gpath = tmp_path / "g.json"
    gpath.write_text(json.dumps(global_cfg), encoding="utf-8")
    return root, str(gpath)


def test_repo_ratchet_widening_is_marked(tmp_path, capsys):
    root, gpath = _repo_with_global(
        tmp_path, {"guards.forcePush": "block"}, {"guards": {"forcePush": "allow"}})

    _, changes = crew_config.plan_repo_write(
        str(root), {"guards.forcePush": "allow"}, gpath)
    code = crew_config.main(["--root", str(root), "--repo", "--global-path",
                             gpath, "--set", 'guards.forcePush="allow"'])

    out = capsys.readouterr().out
    assert (code, [c["widens"] for c in changes]) == (0, [True])
    assert "! guards.forcePush widens to" in out
    assert crew_config._RATCHETED["guards.forcePush"][2]["allow"] in out  # pylint: disable=protected-access


def test_repo_value_held_down_by_machine_is_named(tmp_path, capsys):
    root, gpath = _repo_with_global(
        tmp_path, {"guards.forcePush": "ask"}, {"guards": {"forcePush": "block"}})

    _, changes = crew_config.plan_repo_write(
        str(root), {"guards.forcePush": "allow"}, gpath)
    crew_config.main(["--root", str(root), "--repo", "--global-path", gpath,
                      "--set", 'guards.forcePush="allow"'])

    out = capsys.readouterr().out
    assert [(c["widens"], c["heldDownBy"]) for c in changes] == [(False, "global")]
    assert "held down by the machine-global layer at block" in out
    assert "! guards.forcePush widens" not in out


_CONSENT_WIDENINGS = [
    ("context.autoClear.unsafeFocus", False, True),
    ("autopilot.mode", "off", "plan"),
    ("verifyGate", True, False),
]


@pytest.mark.parametrize("dotted,narrow,wide", _CONSENT_WIDENINGS)
def test_repo_consent_widening_is_marked(tmp_path, capsys, dotted, narrow, wide):
    root, gpath = _repo_with_global(tmp_path, {dotted: narrow}, {})

    _, changes = crew_config.plan_repo_write(str(root), {dotted: wide}, gpath)
    crew_config.main(["--root", str(root), "--repo", "--global-path", gpath,
                      "--set", f"{dotted}={json.dumps(wide)}"])

    assert [c["widens"] for c in changes] == [True]
    assert f"! {dotted} widens to" in capsys.readouterr().out


@pytest.mark.parametrize("dotted,narrow,wide", _CONSENT_WIDENINGS + [
    ("guards.forcePush", "block", "allow")])
def test_narrowing_is_never_marked(tmp_path, capsys, dotted, narrow, wide):
    root, gpath = _repo_with_global(
        tmp_path, {dotted: wide}, {"guards": {"forcePush": "allow"}})

    _, changes = crew_config.plan_repo_write(str(root), {dotted: narrow}, gpath)
    crew_config.main(["--root", str(root), "--repo", "--global-path", gpath,
                      "--set", f"{dotted}={json.dumps(narrow)}"])

    assert [c["widens"] for c in changes] == [False]
    assert "!" not in capsys.readouterr().out


@pytest.mark.parametrize("dotted,value", _BAD_ENUM_VALUES)
def test_repo_enum_validation(tmp_path, dotted, value):
    root = _repo(tmp_path)

    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.plan_repo_write(str(root), {dotted: value},
                                    str(tmp_path / "g.json"))

    assert dotted in str(caught.value)


@pytest.mark.parametrize("dotted", [
    "context.autoClear.unsafeFocus", "tracker", "jira.project",
    "scope.allowCliApproval", "platform.os"])
def test_global_writer_still_refuses_consent_and_repo_keys(tmp_path, dotted):
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.plan_global_write({dotted: "x"}, str(tmp_path / "g.json"))


def test_crew_json_presence_is_named(tmp_path, capsys):
    root = _repo(tmp_path)
    (root / ".crew" / "crew.json").write_text("{}", encoding="utf-8")

    crew_config.main(["--root", str(root), "--repo", "--global-path",
                      str(tmp_path / "g.json"), "--set", 'tracker="jira"'])

    assert ".crew/crew.json" in capsys.readouterr().out


# --- T-0075 successor: per-leaf judgement, the null rule, the merged file ----


def _global_file(tmp_path, cfg):
    path = tmp_path / "g.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("dotted,value,leaf", [
    ("context", {"autoClear": {"unsafeFocus": True}},
     "context.autoClear.unsafeFocus"),
    ("graph", {"obsidian": {"confirmed": True}}, "graph.obsidian.confirmed"),
    ("context", {"autoClear": {"enabled": True, "unsafeFocus": True}},
     "context.autoClear.unsafeFocus"),
    ("qa", {"roles": {"review": {"provider": "gpt"}}},
     "qa.roles.review.provider"),
])
def test_global_writer_judges_each_leaf_of_a_block(tmp_path, dotted, value, leaf):
    path = _global_file(tmp_path, {"pm": {"authority": "act"}})
    before = path.read_bytes()

    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.write_global_config({dotted: value}, str(path))

    assert leaf in str(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("dotted,value,leaf", [
    ("context", {"autoClear": {"enabled": True}}, "context.autoClear.enabled"),
    ("scope", {"mode": "off"}, "scope.mode"),
    ("guards", {"forcePush": "yes"}, "guards.forcePush"),
])
def test_repo_writer_judges_each_leaf_of_a_block(tmp_path, dotted, value, leaf):
    root = _repo(tmp_path)
    before = _repo_bytes(root)

    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.write_repo_config(str(root), {dotted: value},
                                      str(tmp_path / "g.json"))

    assert leaf in str(caught.value)
    assert _repo_bytes(root) == before


def test_leaf_expansion_is_recursive(tmp_path):
    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.plan_global_write({"guards": {"x": {"y": {"z": 1}}}},
                                      str(tmp_path / "g.json"))

    assert "guards.x.y.z" in str(caught.value)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_block_set_to_nothing_is_refused_off_an_open_table(tmp_path, layer):
    root = _repo(tmp_path)
    gpath = str(tmp_path / "g.json")

    def _plan(updates):
        if layer == "machine":
            return crew_config.plan_global_write(updates, gpath)
        return crew_config.plan_repo_write(str(root), updates, gpath)

    with pytest.raises((crew_config.GlobalWriteRefused,
                        crew_config.RepoWriteRefused)) as caught:
        _plan({"guards": {}})
    accepted = [_plan({"qa.roles.review": {}}), _plan({"qa.roles": {}})]

    assert "guards" in str(caught.value)
    assert len(accepted) == 2


@pytest.mark.parametrize("value", [None, "x", 1, ["a"]])
def test_a_scalar_where_a_block_belongs_is_refused(tmp_path, value):
    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.plan_global_write({"guards": value}, str(tmp_path / "g.json"))

    assert "guards" in str(caught.value)


def _set_at(root, gpath, layer, assignment, apply=True):
    return crew_config.main(
        ["--root", str(root), "--global-path", str(gpath), "--set", assignment]
        + (["--repo"] if layer == "repo" else [])
        + (["--apply"] if apply else []))


_OBJECTS_AT_LEAVES = [
    ("pm.authority", {"a": 1}), ("guards.forcePush", {"x": "allow"}),
    ("install.policy", {"a": 1}), ("pm.ticketGranularity", {"a": 1}),
    ("dev.provider", {"a": 1}), ("notify.chatId", {"a": 1}),
    ("notify.chatId", {}), ("qa.order", {"a": 1})]


@pytest.mark.parametrize("dotted,value", _OBJECTS_AT_LEAVES,
                         ids=[f"{d}-{json.dumps(v)}" for d, v in _OBJECTS_AT_LEAVES])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_an_object_at_a_leaf_is_refused(tmp_path, capsys, layer, dotted, value):
    root, gpath = _two_layers(tmp_path, global_cfg={})
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, f"{dotted}={json.dumps(value)}")

    err = capsys.readouterr().err
    assert (code, dotted in err) == (2, True)
    assert layer == "repo" or "takes a value" in err
    assert _both_bytes(root, gpath) == before


@pytest.mark.parametrize("assignment,dotted", [
    ("pm.authority.a=1", "pm.authority"), ('notify.chatId.a="x"', "notify.chatId"),
    ("qa.order.0=1", "qa.order")], ids=["pm.authority.a", "notify.chatId.a",
                                        "qa.order.0"])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_path_through_a_leaf_is_refused(tmp_path, capsys, layer, assignment,
                                          dotted):
    root, gpath = _two_layers(tmp_path, global_cfg={})
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, assignment)

    assert (code, dotted in capsys.readouterr().err) == (2, True)
    assert _both_bytes(root, gpath) == before


@pytest.mark.parametrize("assignment,leaf", [
    ('pm={"authority": {"a": 1}}', "pm.authority"),
    ('notify={"chatId": {}}', "notify.chatId")], ids=["pm", "notify"])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_block_holding_an_object_at_a_leaf_is_refused(tmp_path, capsys, layer,
                                                        assignment, leaf):
    root, gpath = _two_layers(tmp_path, global_cfg={})
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, assignment)

    assert (code, leaf in capsys.readouterr().err) == (2, True)
    assert _both_bytes(root, gpath) == before


@pytest.mark.parametrize("value", ["[1]", "[]", '["act"]'])
@pytest.mark.parametrize("dotted", ["pm.authority", "guards.forcePush"])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_an_array_at_an_enum_key_is_refused_at_both_layers(tmp_path, capsys, layer,
                                                           dotted, value):
    root, gpath = _two_layers(tmp_path, global_cfg={})

    code = _set_at(root, gpath, layer, f"{dotted}={value}")

    assert (code, "not one of its values" in capsys.readouterr().err) == (2, True)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated(tmp_path, capsys,
                                                                layer):
    if layer == "machine":
        root, gpath = _two_layers(tmp_path, global_cfg={"pm": {"authority": {"a": 1}}})
        assignment, key = 'notify.chatId="1"', "pm.authority"
    else:
        root, gpath = _two_layers(tmp_path, {"notify.chatId": {}}, global_cfg={})
        assignment, key = 'tracker="jira"', "notify.chatId"
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, assignment)

    err = capsys.readouterr().err
    assert (code, "pre-existing" in err, key in err) == (2, True, True)
    assert _both_bytes(root, gpath) == before


def test_fixing_the_object_at_a_leaf_in_the_same_write_is_accepted(tmp_path, capsys):
    root, gpath = _two_layers(tmp_path, global_cfg={"pm": {"authority": {"a": 1}}})

    code = _set_at(root, gpath, "machine", 'pm.authority="act"', apply=False)

    assert (code, 'pm.authority: {"a": 1} -> "act"' in capsys.readouterr().out) == (
        0, True)


@pytest.mark.parametrize("dotted", ["pm.authority", "guards.forcePush",
                                    "install.policy", "qa.provider"])
def test_null_is_refused_for_an_enum_key_at_the_machine_layer(tmp_path, dotted):
    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.plan_global_write({dotted: None}, str(tmp_path / "g.json"))

    message = str(caught.value)
    assert dotted in message and "null" in message and "default" in message


def test_null_at_the_repo_layer_means_inherit_or_clear(tmp_path):
    cfg = crew_config.default_config()
    cfg["context"]["autoClear"]["enabled"] = False
    root = _repo(tmp_path, cfg)
    gpath = str(tmp_path / "g.json")

    _, changes = crew_config.plan_repo_write(
        str(root), {"guards.forcePush": None, "pm.authority": None,
                    "context.autoClear.enabled": None, "autopilot.mode": None},
        gpath)
    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.plan_repo_write(str(root), {"scope.mode": None}, gpath)

    assert {c["path"]: c.get("null") for c in changes} == {
        "guards.forcePush": "inherits the machine-global value",
        "pm.authority": "inherits the machine-global value",
        "context.autoClear.enabled": "clears the veto",
        # T-0050: personal, so global-settable; a repo null is silent.
        "autopilot.mode": "inherits the machine-global value"}
    assert "scope.mode" in str(caught.value)


def test_a_legacy_null_already_in_the_file_does_not_block_an_unrelated_write(
        tmp_path):
    path = _global_file(tmp_path, {"pm": {"authority": None}})

    _, changes = crew_config.write_global_config({"notify.chatId": "123"},
                                                 str(path))

    assert [c["path"] for c in changes] == ["notify.chatId"]
    assert json.loads(path.read_text(encoding="utf-8"))["pm"]["authority"] is None


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_write_refuses_when_the_merged_file_holds_a_bad_enum_elsewhere(
        tmp_path, layer):
    if layer == "machine":
        path = _global_file(tmp_path, {"guards": {"forcePush": "yes"}})
        with pytest.raises(crew_config.GlobalWriteRefused) as caught:
            crew_config.plan_global_write({"notify.chatId": "1"}, str(path))
        bad = "guards.forcePush"
    else:
        cfg = crew_config.default_config()
        cfg["pm"]["authority"] = "bogus"
        root = _repo(tmp_path, cfg)
        with pytest.raises(crew_config.RepoWriteRefused) as caught:
            crew_config.plan_repo_write(str(root), {"tracker": "jira"},
                                        str(tmp_path / "g.json"))
        bad = "pm.authority"

    message = str(caught.value)
    assert "pre-existing" in message and bad in message and "first" in message


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_merged_file_provider_check_holds_at_both_layers(tmp_path, layer):
    if layer == "machine":
        path = _global_file(tmp_path, {"qa": {"provider": "gpt"}})
        with pytest.raises(crew_config.GlobalWriteRefused) as caught:
            crew_config.plan_global_write({"notify.chatId": "1"}, str(path))
    else:
        cfg = crew_config.default_config()
        cfg["qa"]["provider"] = "gpt"
        root = _repo(tmp_path, cfg)
        with pytest.raises(crew_config.RepoWriteRefused) as caught:
            crew_config.plan_repo_write(str(root), {"tracker": "jira"},
                                        str(tmp_path / "g.json"))

    assert "qa.provider" in str(caught.value)


# --- Review round 4 (T-0075): qa.order has one shape -----------------------

_NOT_LISTS = [("1", "1"), ("true", "true"), ("1.5", "1.5"),
              ("codex", '"codex"'), ("object", '{"a": 1}')]


def _two_layers(tmp_path, repo_updates=None, global_cfg=None):
    cfg = crew_config.default_config()
    for dotted, value in (repo_updates or {}).items():
        crew_config._set_path(cfg, dotted.split("."), value)  # pylint: disable=protected-access
    root = _repo(tmp_path, cfg)
    gpath = _global_file(tmp_path, global_cfg if global_cfg is not None
                         else {"pm": {"authority": "act"}})
    return root, gpath


def _both_bytes(root, gpath):
    return _repo_bytes(root), gpath.read_bytes()


_NOT_OBJECTS = [("qa.roles", 1), ("qa.roles", True), ("qa.roles", "codex"),
                ("qa.roles", []), ("dev.roles", 1), ("dev.roles", []),
                ("qa.roles.review", "codex"), ("qa.roles.review", 1),
                ("qa.roles.review", []), ("qa.roles.review", True),
                ("dev.roles.developer", "claude"), ("dev.roles.developer", [])]


def _pinned(tmp_path, pin=None):
    return _two_layers(tmp_path, {"qa.roles.review": pin or {"provider": "codex"}},
                       global_cfg={})


@pytest.mark.parametrize("dotted,value", _NOT_OBJECTS,
                         ids=[f"{d}-{v}" for d, v in _NOT_OBJECTS])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_an_open_table_must_be_an_object(tmp_path, capsys, layer, dotted, value):
    root, gpath = _pinned(tmp_path)
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, f"{dotted}={json.dumps(value)}")

    err = capsys.readouterr().err
    assert (code, dotted in err, "object" in err) == (2, True, True)
    assert _both_bytes(root, gpath) == before


_OPEN_OK = ["qa.roles=null", "qa.roles.review=null", "qa.roles={}",
            "qa.roles.review={}",
            'qa.roles.review={"provider": "codex", "model": "gpt-5.6-luna"}',
            'dev.roles.developer={"provider": "claude"}']


@pytest.mark.parametrize("assignment", _OPEN_OK)
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_open_table_null_and_objects_still_accepted(tmp_path, capsys, layer,
                                                    assignment):
    root, gpath = _pinned(tmp_path)

    code = _set_at(root, gpath, layer, assignment, apply=False)

    assert code == 0, capsys.readouterr().err


def test_validate_providers_names_a_non_object_table():
    with pytest.raises(crew_config.ProviderError) as table:
        crew_config.validate_providers({"qa": {"roles": 1}})
    with pytest.raises(crew_config.ProviderError) as entry:
        crew_config.validate_providers({"dev": {"roles": {"developer": []}}})
    nulls = [crew_config.validate_providers({"qa": {"roles": None}}),
             crew_config.validate_providers({"qa": {"roles": {"review": None}}})]
    listed = crew_config.provider_problems({"qa": {"roles": 1}})

    assert "qa.roles" in str(table.value)
    assert "dev.roles.developer" in str(entry.value)
    assert nulls == [{"qa": {"roles": None}}, {"qa": {"roles": {"review": None}}}]
    assert (len(listed), "qa.roles" in listed[0]) == (1, True)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_pre_existing_non_object_in_an_open_table_is_named(tmp_path, capsys,
                                                            layer):
    if layer == "machine":
        root, gpath = _two_layers(tmp_path, global_cfg={"qa": {"roles": 1}})
        assignment, key = 'notify.chatId="1"', "qa.roles"
    else:
        root, gpath = _two_layers(tmp_path, {"qa.roles.review": "codex"},
                                  global_cfg={})
        assignment, key = 'tracker="jira"', "qa.roles.review"
    before = _both_bytes(root, gpath)

    code = _set_at(root, gpath, layer, assignment)

    assert (code, key in capsys.readouterr().err) == (2, True)
    assert _both_bytes(root, gpath) == before


def test_fixing_the_open_table_in_the_same_write_is_accepted(tmp_path, capsys):
    root, gpath = _two_layers(tmp_path, {"qa.roles.review": "codex"}, global_cfg={})

    code = _set_at(root, gpath, "repo", 'qa.roles.review={"provider": "codex"}',
                   apply=False)

    assert code == 0, capsys.readouterr().err


def test_a_wiped_pin_table_never_reaches_the_file(tmp_path, capsys):
    root, gpath = _pinned(tmp_path)
    before = _repo_bytes(root)

    code = _set_at(root, gpath, "repo", "qa.roles=1")
    capsys.readouterr()
    crew_config.main(["--root", str(root), "--global-path", str(gpath), "--models"])
    review = [line for line in capsys.readouterr().out.splitlines()
              if line.startswith("review ")]

    assert (code, _repo_bytes(root) == before) == (2, True)
    assert "role-pin" in review[0]


@pytest.mark.parametrize("value", [v for _, v in _NOT_LISTS],
                         ids=[i for i, _ in _NOT_LISTS])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_qa_order_must_be_a_list(tmp_path, capsys, layer, value):
    root, gpath = _two_layers(tmp_path)
    before = _both_bytes(root, gpath)

    code = crew_config.main(
        ["--root", str(root), "--global-path", str(gpath), "--set",
         f"qa.order={value}"] + (["--repo"] if layer == "repo" else []))

    err = capsys.readouterr().err
    # An object is refused by the leaf rule before the list check (round 5).
    reason = {("repo", '{"a": 1}'): "settable leaf",
              ("machine", '{"a": 1}'): "takes a value"}.get((layer, value), "list")
    assert (code, "qa.order" in err, reason in err) == (2, True, True)
    assert _both_bytes(root, gpath) == before


@pytest.mark.parametrize("value", ['["codex", "claude"]', "null"],
                         ids=["list", "null"])
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_qa_order_list_and_null_still_accepted(tmp_path, capsys, layer, value):
    root, gpath = _two_layers(tmp_path)

    code = crew_config.main(
        ["--root", str(root), "--global-path", str(gpath), "--set",
         f"qa.order={value}"] + (["--repo"] if layer == "repo" else []))

    capsys.readouterr()
    assert code == 0


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_pre_existing_non_list_qa_order_is_named_not_a_traceback(
        tmp_path, capsys, layer):
    if layer == "machine":
        root, gpath = _two_layers(tmp_path, global_cfg={"qa": {"order": True}})
        argv = ["--set", 'notify.chatId="1"']
    else:
        root, gpath = _two_layers(tmp_path, {"qa.order": 1})
        argv = ["--set", 'tracker="jira"', "--repo"]

    code = crew_config.main(["--root", str(root), "--global-path", str(gpath)]
                            + argv)

    assert code == 2
    assert "qa.order" in capsys.readouterr().err


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_set_cli_subprocess_prints_no_traceback_for_qa_order(tmp_path, layer):
    root, gpath = _two_layers(tmp_path)
    script = os.path.join(os.path.dirname(os.path.abspath(crew_config.__file__)),
                          "crew_config.py")

    done = subprocess.run(
        [sys.executable, script, "--root", str(root), "--global-path",
         str(gpath), "--set", "qa.order=1"]
        + (["--repo"] if layer == "repo" else []),
        capture_output=True, text=True, check=False)

    assert (done.returncode, "Traceback" in done.stderr) == (2, False)


def test_fixing_the_bad_key_in_the_same_write_is_accepted(tmp_path):
    cfg = crew_config.default_config()
    cfg["pm"]["authority"] = "bogus"
    root = _repo(tmp_path, cfg)

    _, changes = crew_config.plan_repo_write(
        str(root), {"pm.authority": "act", "tracker": "jira"},
        str(tmp_path / "g.json"))

    assert {c["path"] for c in changes} == {"pm.authority", "tracker"}


# --- T-0075 successor: both writers compare-and-swap under a lock ------------


@pytest.fixture
def _short_lock(monkeypatch):
    monkeypatch.setattr(crew_config_files, "LOCK_WAIT_SECONDS", 0.1)


def _rewrite_with(path, key, value):
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_repo_write_conflict_keeps_the_other_writers_key(tmp_path):
    root = _repo(tmp_path)
    gpath = str(tmp_path / "g.json")
    _parsed, _raw, digest = crew_config.repo_snapshot(str(root))
    crew_config.plan_repo_write(str(root), {"tracker": "jira"}, gpath)
    _rewrite_with(root / ".crew" / "config.json", "x-other", 1)

    with pytest.raises(crew_config.RepoWriteConflict) as caught:
        crew_config.write_repo_config(str(root), {"tracker": "jira"}, gpath,
                                      expect=digest)

    written = json.loads(_repo_bytes(root))
    assert (written["x-other"], written["tracker"]) == (1, "files")
    assert "changed since it was read" in str(caught.value)


def test_repo_write_without_expect_merges_onto_the_latest_file(tmp_path):
    root = _repo(tmp_path)
    gpath = str(tmp_path / "g.json")
    crew_config.plan_repo_write(str(root), {"tracker": "jira"}, gpath)
    _rewrite_with(root / ".crew" / "config.json", "x-other", 1)

    crew_config.write_repo_config(str(root), {"tracker": "jira"}, gpath)

    written = json.loads(_repo_bytes(root))
    assert (written["x-other"], written["tracker"]) == (1, "jira")


@pytest.mark.parametrize("expect_stale", [True, False])
def test_global_write_conflict_and_merge(tmp_path, expect_stale):
    path = _global_file(tmp_path, {"pm": {"authority": "act"}})
    _parsed, _raw, digest = crew_config.global_snapshot(str(path))
    _rewrite_with(path, "x-other", 1)

    if expect_stale:
        with pytest.raises(crew_config.GlobalWriteConflict):
            crew_config.write_global_config({"notify.chatId": "1"}, str(path),
                                            expect=digest)
    else:
        crew_config.write_global_config({"notify.chatId": "1"}, str(path))

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["x-other"] == 1
    assert ("notify" in written) is (not expect_stale)


def test_global_write_refuses_a_malformed_file(tmp_path):
    path = tmp_path / "g.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config({"notify.chatId": "1"}, str(path))

    assert path.read_text(encoding="utf-8") == "{ not json"


def test_repo_write_refuses_while_the_lock_is_held(tmp_path, _short_lock):
    root = _repo(tmp_path)
    before = _repo_bytes(root)
    (root / ".crew" / "config.json.lock").write_text("31337", encoding="utf-8")

    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                      str(tmp_path / "g.json"))

    assert "config.json.lock" in str(caught.value) and "31337" in str(caught.value)
    assert _repo_bytes(root) == before


def test_global_write_refuses_while_the_lock_is_held(tmp_path, _short_lock):
    path = _global_file(tmp_path, {"pm": {"authority": "act"}})
    before = path.read_bytes()
    (tmp_path / "g.json.lock").write_text("31337", encoding="utf-8")

    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.write_global_config({"notify.chatId": "1"}, str(path))

    assert "g.json.lock" in str(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_set_cli_prints_the_digest_and_takes_expect(tmp_path, capsys, layer):
    root = _repo(tmp_path)
    gpath = _global_file(tmp_path, {"pm": {"authority": "act"}})
    base = ["--root", str(root), "--global-path", str(gpath)]
    base += ["--repo", "--set", 'tracker="jira"'] if layer == "repo" else [
        "--set", 'notify.chatId="1"']
    target = (root / ".crew" / "config.json") if layer == "repo" else gpath

    dry = crew_config.main(base)
    digest = re.search(r"digest: ([0-9a-f]{64})", capsys.readouterr().out)
    before = target.read_bytes()
    stale = crew_config.main(base + ["--apply", "--expect", "0" * 64])
    stale_err = capsys.readouterr().err
    usage = crew_config.main(base + ["--apply", "--expect", "zz"])
    usage_err = capsys.readouterr().err
    unchanged = target.read_bytes() == before
    good = crew_config.main(base + ["--apply", "--expect", digest.group(1)])

    assert (dry, stale, usage, good) == (0, 2, 2, 0)
    assert "changed since it was read" in stale_err
    assert "--expect" in usage_err
    assert unchanged and target.read_bytes() != before


@pytest.mark.parametrize("argv", [
    ["--set", "a..b=1"], ["--set", "=1"], ["--set", "x"],
    ["--set", ".a=1"], ["--set", "pm.authority=act"],
    ["--set", 'notify.chatId="1"', "--expect", "zz"],
], ids=["double-dot", "empty-key", "no-equals", "leading-dot", "not-json",
        "bad-digest"])
def test_set_cli_refuses_malformed_shapes(tmp_path, capsys, argv):
    path = _global_file(tmp_path, {"pm": {"authority": "report-only"}})
    before = path.read_bytes()

    code = crew_config.main(["--global-path", str(path), "--apply"] + argv)

    err = capsys.readouterr().err
    assert (code, "Traceback" in err, path.read_bytes() == before) == (2, False, True)
    assert err.strip()


# --- Review round 3 (T-0075): assign exactly what was judged ----------------


def _machine_and_repo(tmp_path, global_cfg, repo_updates=None):
    cfg = crew_config.default_config()
    for dotted, value in (repo_updates or {}).items():
        crew_config._set_path(cfg, dotted.split("."), value)  # pylint: disable=protected-access
    root = _repo(tmp_path, cfg)
    return root, _global_file(tmp_path, global_cfg)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_block_write_keeps_its_untouched_siblings(tmp_path, layer):
    root, gpath = _machine_and_repo(
        tmp_path, {"context": {"autoClear": {"method": "tmux"}, "x-local": 1}},
        {"context.x-local": 1, "context.autoClear.method": "tmux"})
    update = {"context": {"autoClear": {"enabled": False}}}

    if layer == "machine":
        merged, changes = crew_config.write_global_config(update, str(gpath))
    else:
        merged, changes = crew_config.write_repo_config(str(root), update,
                                                        str(gpath))

    assert [c["path"] for c in changes] == ["context.autoClear.enabled"]
    assert (merged["context"]["x-local"],
            merged["context"]["autoClear"]["method"],
            merged["context"]["autoClear"]["enabled"]) == (1, "tmux", False)


def test_a_machine_block_write_marks_its_leaf_widening(tmp_path):
    gpath = _global_file(tmp_path, {"pm": {"authority": "report-only"}})

    _, changes = crew_config.plan_global_write({"pm": {"authority": "act"}},
                                               str(gpath))

    assert [(c["path"], c["widens"]) for c in changes] == [("pm.authority", True)]


def test_a_repo_block_write_marks_its_leaf_widening(tmp_path):
    root, gpath = _machine_and_repo(tmp_path, {"guards": {"forcePush": "allow"}},
                                    {"guards.forcePush": "block"})

    _, changes = crew_config.plan_repo_write(
        str(root), {"guards": {"forcePush": "allow"}}, str(gpath))

    assert [(c["path"], c["widens"]) for c in changes] == [
        ("guards.forcePush", True)]


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_a_role_table_write_keeps_the_other_pins(tmp_path, layer):
    pins = {"phase1": {"provider": "codex", "model": "gpt-5.6-sol"},
            "review": {"provider": "codex", "model": "gpt-5.6-luna"}}
    root, gpath = _machine_and_repo(tmp_path, {"qa": {"roles": pins}},
                                    {"qa.roles": pins})
    update = {"qa.roles": {"review": {"provider": "claude"}}}

    if layer == "machine":
        merged, changes = crew_config.write_global_config(update, str(gpath))
    else:
        merged, changes = crew_config.write_repo_config(str(root), update,
                                                        str(gpath))

    assert [c["path"] for c in changes] == ["qa.roles.review"]
    assert merged["qa"]["roles"] == {"phase1": pins["phase1"],
                                     "review": {"provider": "claude"}}


def test_repo_writer_takes_a_block_leaf_by_leaf(tmp_path):
    root = _repo(tmp_path)

    _, changes = crew_config.write_repo_config(
        str(root), {"guards": {"forcePush": "ask"}}, str(tmp_path / "g.json"))

    written = json.loads(_repo_bytes(root))
    assert ([c["path"] for c in changes], written["guards"]["forcePush"]) == (
        ["guards.forcePush"], "ask")
    assert written["guards"]["mergeGate"] == crew_config.default_config()[
        "guards"]["mergeGate"]


@pytest.mark.parametrize("layer,held,leaf", [
    ("machine", {"context": {"autoClear": {"unsafeFocus": True}}},
     "context.autoClear.unsafeFocus"),
    ("machine", {"graph": {"obsidian": {"confirmed": True}}},
     "graph.obsidian.confirmed"),
    ("repo", {"context.autoClear.enabled": True}, "context.autoClear.enabled"),
    ("repo", {"resume.auto": 0}, "resume.auto"),
], ids=["machine-unsafeFocus", "machine-obsidian", "repo-armed-autoclear",
        "repo-zero-veto"])
def test_merged_file_refuses_a_pre_existing_leaf_forbidden_at_its_layer(
        tmp_path, layer, held, leaf):
    if layer == "machine":
        gpath = _global_file(tmp_path, held)
        before = gpath.read_bytes()
        with pytest.raises(crew_config.GlobalWriteRefused) as caught:
            crew_config.write_global_config({"notify.chatId": "1"}, str(gpath))
        after = gpath.read_bytes()
    else:
        root, gpath = _machine_and_repo(tmp_path, {}, held)
        before = _repo_bytes(root)
        with pytest.raises(crew_config.RepoWriteRefused) as caught:
            crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                          str(gpath))
        after = _repo_bytes(root)

    message = str(caught.value)
    assert "pre-existing" in message and leaf in message and "by hand" in message
    assert after == before


def test_a_repo_only_key_in_the_machine_file_does_not_block_a_write(tmp_path):
    # JUDGEMENT (review round 3): a repo-only key in the machine file is
    # pruned by `filter_global` on every read, so it cannot take effect. The
    # owner's machine file held `autopilot.mode` ahead of T-0070; T-0050 made
    # that key personal (global-settable), so `tracker` stands in for it.
    gpath = _global_file(tmp_path, {"tracker": "jira"})

    merged, _ = crew_config.write_global_config({"notify.chatId": "1"},
                                                str(gpath))

    assert merged["tracker"] == "jira"
    assert crew_config.filter_global(merged)[0].get("tracker") is None


def test_repo_write_refuses_when_the_machine_file_changed(tmp_path):
    root, gpath = _machine_and_repo(tmp_path, {"guards": {"forcePush": "block"}},
                                    {"guards.forcePush": "block"})
    machine = crew_config.global_snapshot(str(gpath))[2]
    before = _repo_bytes(root)
    _rewrite_with(gpath, "guards", {"forcePush": "allow"})

    with pytest.raises(crew_config.RepoWriteConflict) as caught:
        crew_config.write_repo_config(str(root), {"guards.forcePush": "allow"},
                                      str(gpath), expect_global=machine)

    assert "machine-global" in str(caught.value)
    assert _repo_bytes(root) == before


def test_repo_write_takes_the_machine_lock_when_its_directory_is_absent(
        tmp_path, monkeypatch):
    root = _repo(tmp_path)
    gpath = str(tmp_path / "no-such-dir" / "config.json")
    taken = []
    real_enter = crew_config_files.Lock.__enter__

    def _enter(self):
        taken.append(self.path)
        return real_enter(self)
    monkeypatch.setattr(crew_config_files.Lock, "__enter__", _enter)

    crew_config.write_repo_config(str(root), {"tracker": "jira"}, gpath,
                                  expect_global=crew_config_files.ABSENT)

    repo_lock = str(root / ".crew" / "config.json") + ".lock"
    assert taken[:2] == [gpath + ".lock", repo_lock]


def _unmakeable(tmp_path, monkeypatch, kind):
    """A machine path whose directory cannot be made: `os.makedirs` denied
    (patched after every fixture directory exists), or a file in its way."""
    if kind == "permission":
        def _deny(path, *_args, **_kwargs):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        monkeypatch.setattr(crew_config_files.os, "makedirs", _deny)
        return str(tmp_path / "nodir" / "config.json")
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    return str(tmp_path / "afile" / "config.json")


def _stray_locks(root, gpath):
    crew_dir = root / ".crew"
    beside = os.path.dirname(gpath)
    return ([n for n in os.listdir(crew_dir) if n.endswith(".lock")]
            + ([n for n in os.listdir(beside) if n.endswith(".lock")]
               if os.path.isdir(beside) else []))


@pytest.mark.parametrize("kind", ["permission", "file"])
def test_repo_write_refuses_when_the_machine_directory_cannot_be_made(
        tmp_path, capsys, monkeypatch, kind):
    root = _repo(tmp_path)
    before = _repo_bytes(root)
    gpath = _unmakeable(tmp_path, monkeypatch, kind)

    code = _set_at(root, gpath, "repo", 'tracker="jira"')

    err = capsys.readouterr().err
    assert (code, "nothing written" in err, os.path.dirname(gpath) in err) == (
        2, True, True)
    assert (_repo_bytes(root), _stray_locks(root, gpath)) == (before, [])


@pytest.mark.parametrize("kind", ["permission", "file"])
def test_global_write_refuses_when_its_directory_cannot_be_made(
        tmp_path, capsys, monkeypatch, kind):
    root = _repo(tmp_path)
    gpath = _unmakeable(tmp_path, monkeypatch, kind)

    code = _set_at(root, gpath, "machine", 'pm.authority="act"')

    assert (code, os.path.dirname(gpath) in capsys.readouterr().err) == (2, True)


def _deny_lock_files(monkeypatch):
    real_open = crew_config_files.os.open

    def _open(path, *args, **kwargs):
        if str(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(crew_config_files.os, "open", _open)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_both_writers_refuse_when_the_lock_cannot_be_created(
        tmp_path, capsys, monkeypatch, layer):
    root = _repo(tmp_path)
    gdir = tmp_path / "machine"
    gdir.mkdir()
    gpath = _global_file(gdir, {})
    gpath = gpath.rename(gdir / "config.json")
    before = _both_bytes(root, gpath)
    _deny_lock_files(monkeypatch)

    code = _set_at(root, gpath, layer,
                   'pm.authority="act"' if layer == "machine" else 'tracker="jira"')

    err = capsys.readouterr().err
    assert (code, "config.json.lock" in err, "nothing written" in err) == (
        2, True, True)
    assert _both_bytes(root, gpath) == before


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_set_cli_subprocess_prints_no_traceback_when_the_machine_directory_is_a_file(
        tmp_path, layer):
    root = _repo(tmp_path)
    gpath = _unmakeable(tmp_path, None, "file")
    script = os.path.join(os.path.dirname(os.path.abspath(crew_config.__file__)),
                          "crew_config.py")

    done = subprocess.run(
        [sys.executable, script, "--root", str(root), "--global-path", gpath,
         "--set", 'pm.authority="act"' if layer == "machine" else 'tracker="jira"',
         "--apply"] + (["--repo"] if layer == "repo" else []),
        capture_output=True, text=True, check=False)

    assert (done.returncode, "Traceback" in done.stderr) == (2, False)


@pytest.mark.parametrize("create,conflict", [(False, False), (True, True)])
def test_repo_write_compares_the_machine_file_against_absence(tmp_path, create,
                                                              conflict):
    root = _repo(tmp_path)
    gpath = tmp_path / "g.json"
    if create:
        gpath.write_text('{"pm": {"authority": "act"}}', encoding="utf-8")

    def _write():
        return crew_config.write_repo_config(str(root), {"tracker": "jira"},
                                             str(gpath), expect_global="absent")
    if conflict:
        with pytest.raises(crew_config.RepoWriteConflict):
            _write()
    else:
        _write()

    assert json.loads(_repo_bytes(root))["tracker"] == ("files" if conflict
                                                        else "jira")


def test_set_repo_cli_prints_and_takes_the_machine_digest(tmp_path, capsys):
    root = _repo(tmp_path)
    gpath = _global_file(tmp_path, {"pm": {"authority": "act"}})
    base = ["--root", str(root), "--global-path", str(gpath), "--repo",
            "--set", 'tracker="jira"']

    crew_config.main(base)
    out = capsys.readouterr().out
    machine = re.search(r"machine digest: ([0-9a-f]{64})", out)
    _rewrite_with(gpath, "x-other", 1)
    stale = crew_config.main(base + ["--apply", "--expect-global",
                                     machine.group(1)])
    err = capsys.readouterr().err

    assert stale == 2 and "changed since it was read" in err
    assert json.loads(_repo_bytes(root))["tracker"] == "files"


def test_set_cli_takes_absent_for_a_first_machine_write(tmp_path, capsys):
    gpath = tmp_path / "g.json"

    crew_config.main(["--global-path", str(gpath), "--set", 'notify.chatId="1"'])
    out = capsys.readouterr().out
    gpath.write_text('{"x-other": 1}', encoding="utf-8")
    stale = crew_config.main(["--global-path", str(gpath), "--set",
                              'notify.chatId="1"', "--apply", "--expect",
                              "absent"])
    err = capsys.readouterr().err

    assert "digest: absent" in out
    assert stale == 2 and "changed since it was read" in err
    assert json.loads(gpath.read_text(encoding="utf-8")) == {"x-other": 1}

_CONFIG_MD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "CONFIG.md",
)


def _config_md_row(text, key):
    rows = [line for line in text.splitlines()
            if line.startswith(f"| `{key}` |")]
    assert len(rows) == 1, (key, rows)
    return rows[0]


def test_config_md_and_setup_template_state_the_kimi_defaults():
    """T-0028: CONFIG.md's global-key table carries `qa.kimi.model` and
    `dev.kimi.model`, the new `qa.order` default, and `kimi` in both provider
    enumerations -- the same values `default_config()` holds. The setup
    template is compared in full by the test above."""
    with open(_CONFIG_MD_PATH, encoding="utf-8") as handle:
        text = handle.read()
    defaults = crew_config.default_config()
    order = json.dumps(defaults["qa"]["order"]).replace('","', '", "')

    assert order in _config_md_row(text, "qa.order")
    assert _config_md_row(text, "qa.kimi.model").endswith("| `null` |")
    assert _config_md_row(text, "dev.kimi.model").endswith("| `null` |")
    assert "`kimi`" in _config_md_row(text, "qa.provider")
    assert "`kimi`" in _config_md_row(text, "dev.provider")
    assert json.dumps(list(crew_config.QA_PROVIDERS)).replace('","', '", "') in text


def test_config_md_global_key_count_is_measured():
    """CONFIG.md §10 states the global-settable key count, the total, and
    lists the global keys in a table. Since T-0048 that table and its count
    line are generated (`config_reference.py`); all three are re-measured here
    against the code: N is `len(leaf_paths(default_global_config()))`, M every
    declared leaf, and the table holds exactly the N global keys."""
    with open(_CONFIG_MD_PATH, encoding="utf-8") as handle:
        text = handle.read()
    section = text[text.index("## 10. Global-settable keys"):text.index("## 11. ")]
    match = re.search(r"(\d+) of (\d+) keys are settable in the machine-global file",
                      section)
    stated_global, stated_total = int(match.group(1)), int(match.group(2))
    tabled = [key for line in section.splitlines() if line.startswith("| `")
              for key in re.findall(r"`([^`]+)`", line.split("|")[1])]
    global_leaves = crew_config.leaf_paths(crew_config.default_global_config())
    total = set(crew_config.leaf_paths(crew_config.default_config())) | set(global_leaves)

    assert stated_global == len(global_leaves) == len(tabled)
    assert stated_total == len(total)
    assert set(tabled) == set(global_leaves)


# --- T-0044: the machine-only `unattendedCloud` block -----------------------
#
# Which cloud identity an unattended run holds is the machine owner's answer
# and nobody else's: a repo travels inside a clone written by someone else, so
# a repo copy is IGNORED (not merged, not ratcheted) and reported as such. The
# defaults name no identity, and `crew_unattended.py` refuses every launch
# until the owner names one.

def test_unattended_cloud_defaults_grant_nothing():
    block = crew_config.default_global_config()["unattendedCloud"]
    assert block == {"aws": {
        "readOnly": {"profile": None, "identity": None, "region": None},
        "nonProd": {}}}
    assert crew_state.UNATTENDED_CLOUD_DEFAULTS == block
    assert crew_state.UNATTENDED_CLOUD_MACHINE_ONLY == ("unattendedCloud",)
    leaves = crew_config.leaf_paths(crew_config.default_global_config())
    # `nonProd` is an open table, so it is one leaf, like `dev.roles`.
    assert [p for p in leaves if p.startswith("unattendedCloud.")] == [
        "unattendedCloud.aws.readOnly.profile",
        "unattendedCloud.aws.readOnly.identity",
        "unattendedCloud.aws.readOnly.region",
        "unattendedCloud.aws.nonProd"]


def test_unattended_cloud_is_global_only():
    assert "unattendedCloud" in crew_config.default_global_config()
    assert "unattendedCloud" not in crew_config.default_config()
    assert crew_config.is_global_path("unattendedCloud.aws.readOnly.identity")


def test_repo_unattended_cloud_is_ignored(tmp_path):
    """A repo naming its own identity must change nothing: not the resolved
    config, not the explain table's value, and never `source: repo`."""
    machine = "arn:aws:sts::111111111111:assumed-role/ReadOnly/"
    forged = "arn:aws:sts::111111111111:assumed-role/AdministratorAccess/"
    global_path = tmp_path / "global-config.json"
    global_path.write_text(json.dumps({"unattendedCloud": {"aws": {
        "readOnly": {"profile": "ro", "identity": machine}}}}),
        encoding="utf-8")
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "unattendedCloud": {"aws": {"readOnly": {
            "profile": "admin", "identity": forged, "region": "us-east-1"}}}},
        git=False)

    rows = {r["path"]: r for r in
            crew_config.explain_config(str(root), path=str(global_path))}
    ident = rows["unattendedCloud.aws.readOnly.identity"]
    assert ident["value"] == machine and ident["source"] == "global"
    assert ident["repoIgnored"] == forged
    region = rows["unattendedCloud.aws.readOnly.region"]
    assert region["value"] is None and region["source"] == "default"
    assert region["repoIgnored"] == "us-east-1"
    assert all(r["source"] not in ("repo", "repo+global") for p, r in
               rows.items() if p.startswith("unattendedCloud."))


def test_resolve_config_drops_a_repo_unattended_cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(tmp_path / "absent.json"))
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "unattendedCloud": {"aws": {"readOnly": {"identity": "x/"}}}},
        git=False)
    assert "unattendedCloud" not in crew_config.resolve_config(str(root))


@pytest.mark.parametrize("block,needle", [
    ({"aws": {"readOnly": {"identity": "arn:aws:sts::1:assumed-role/RO"}}},
     "end in `/`"),
    # T-0044 port review r6 BLOCK: one named role, never every role.
    ({"aws": {"readOnly": {"identity": "arn:aws:sts::111111111111:assumed-role/"}}},
     "must name one role"),
    ({"aws": {"nonProd": []}}, "nonProd"),
    ({"aws": {"readOnly": {"profile": 7}}}, "profile"),
    ({"aws": {}, "azure": {}}, "azure"),
    ({"aws": {"nonProd": {"dev": {"profile": "d"}}}}, "identity"),
    ({"aws": {"readOnly": []}}, "readOnly"),
    ("aws", "not an object"),
    ({"aws": None}, "aws"),
])
def test_unattended_cloud_block_problem(block, needle):
    problem = crew_config.unattended_cloud_block_problem(block)
    assert problem and needle in problem, problem


def test_unattended_cloud_block_problem_accepts_the_shapes_it_must():
    ident = "arn:aws:sts::111111111111:assumed-role/ReadOnly/"
    for block in (crew_state.UNATTENDED_CLOUD_DEFAULTS,
                  {"aws": {"readOnly": {"profile": "ro", "identity": ident,
                                        "region": "eu-west-1"}}},
                  {"aws": {"nonProd": {"dev": {"profile": "d",
                                               "identity": ident}}}}):
        assert crew_config.unattended_cloud_block_problem(block) == ""
