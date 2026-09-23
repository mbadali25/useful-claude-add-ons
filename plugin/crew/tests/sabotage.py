"""Sabotage test: reintroduce each bug and confirm the suite goes red.

Run it directly: `python3 plugin/crew/tests/sabotage.py`. For each mutation it
patches one file, runs the test that should catch the change, and restores the
file whether or not the run succeeded.

A test that stays green with the behaviour deleted is not coverage. Three of
the tests in this directory did exactly that until a review named them, so the
claim "this is tested" is checked here rather than asserted.

A mutation whose anchor no longer matches is a FAILURE, not a skip: the anchor
drifting is how this suite would quietly stop testing anything.

WHAT A RED RESULT DOES NOT PROVE, and the blind spot of this whole technique:
a mutation going red proves the TEST failed. It never proves WHICH assertion
failed. So a test with several assertions, covered by one mutation, can hold a
vacuous assertion forever -- the mutation trips an earlier line, this file
prints RED, and the mutation's own label claims coverage the suite does not
have.

Measured here, not hypothetical. `test_the_two_config_keys_are_bound_to_
different_genres` was written to prove `docs.reportTheme` binds to the
findings-report genre. It found the line naming that key, asserted the line
existed, then asserted `"report"` was in it -- and `"docs.reportTheme"`
contains `"report"`, so the second assertion could not fail once the first
had. Its mutation deleted the key from the sentence, tripping the FIRST
assertion. Red every run, binding unchecked. Four other vacuous assertions on
that same branch were each caught by a mutation coming back green, which is the
normal way this file earns its keep; this one could not be, and it was the
assertion that had been specifically asked for.

So when you add a mutation for a multi-assertion test, write the one that
leaves every EARLIER assertion satisfied -- here, keep the key in the sentence
and only widen the genre -- and treat a label naming one assertion as a claim
about that assertion alone. Both entries are in MUTATIONS below, next to each
other, on purpose.

It edits real source in place, so putting the file back is as load-bearing as
the mutation. `d362a2bd` shipped `crew_state.py` with a live mutation still in
it -- a killed run had skipped the `finally`, the next run copied the mutated
file over the good backup, and nothing compared the restored bytes to anything,
so the suite reported PASS over a corrupted tree. Four things prevent that now:
`main` refuses to start when a `.bak` is present, `install_exit_handlers`
restores on SIGTERM and on interpreter exit rather than on `finally` alone,
`apply_mutation` writes its backup under a second name and renames it into
place so a `.bak` is never partial, and every restore -- on the loop's path,
the signal path and the atexit path alike -- is verified against a sha256
taken before the first mutation. SIGKILL is still uncatchable; the startup
refusal is what covers it, on the next run.

Which is why a mutation whose CODE is deliberately deleted must be deleted
here too, with the reason written down -- never re-anchored onto whatever line
is nearest. Five went when the dispatch record stopped being a single shared
file: they proved things about a lock, a retry loop and a self-verifying write
that an append-only directory cannot get wrong, and a suite still listing them
would have read as concurrency coverage while testing nothing.
"""
import atexit
import hashlib
import io
import os
import shutil
import signal
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CREW = os.path.join(ROOT, "plugin", "crew")
STATE = os.path.join(CREW, "hooks", "scripts", "crew_state.py")
# The endpoint ledger and the three shared readers left crew_state.py in
# 0.16.21. A mutation patches the file its anchor actually lives in --
# an anchor that no longer matches is a FAILURE here, not a skip, so a
# split that left these pointing at the old file would have been caught
# by this suite rather than by the absence of one.
ENDPOINTS = os.path.join(CREW, "hooks", "scripts", "crew_endpoints.py")
COMMON = os.path.join(CREW, "hooks", "scripts", "crew_common.py")
LADDER_DOC = os.path.join(CREW, "skills", "crew-scaling", "SKILL.md")
PLATFORM = os.path.join(CREW, "hooks", "scripts", "crew_platform.py")
CONFIG = os.path.join(CREW, "hooks", "scripts", "crew_config.py")
UPGRADE = os.path.join(
    CREW, "skills", "crew-graph", "scripts", "crew_upgrade.py")
CONFTEST = os.path.join(CREW, "tests", "conftest.py")
HOUSE_STYLE = os.path.join(
    CREW, "skills", "crew-house-style", "SKILL.md")

# Outside the crew plugin on purpose. The routing table makes a claim about
# ANOTHER marketplace entry's interface, and the only way to sabotage that
# claim is to break the interface it names.
BUILD_REPORT = os.path.join(
    ROOT, "skills", "doc-builder", "scripts", "build_report.py")
# Same reasoning, one file over: doc-builder's stylesheet was extracted out of
# build_report.py into house_style.py, and the print rules crew's HTML route
# cites now live here. The heading selector is a PARAMETER of `print_css`, so
# it cannot be sabotaged by editing a CSS literal -- the mutation below changes
# what `stylesheet()` passes, which is the only way that rule can break.
HOUSE_STYLE_PY = os.path.join(
    ROOT, "skills", "doc-builder", "scripts", "house_style.py")
# A shipped artefact of crew's HTML route, outside the plugin for a third
# reason again: the route is the one entry on the routing table with NO
# generator behind it, so the only place its rule can be observed holding is a
# document it produced. One guide is sabotaged rather than all four -- the
# assertion is parametrized per file, so breaking any one of them is what the
# suite has to catch, and mutating four would prove the same thing four times.
GUIDE_HTML = os.path.join(ROOT, "docs", "guides", "crew", "crew-overview.html")
PM_BRIEF = os.path.join(CREW, "hooks", "scripts", "pm_brief.py")
# The other half of the upgrade message. The brief NAMES the migration and
# this file SAYS WHAT IT DOES, deliberately one copy each -- so the only
# way to sabotage "the two agree" is to break one of them.
UPGRADE_DOC = os.path.join(CREW, "commands", "upgrade.md")
PROMOTE_DOC = os.path.join(CREW, "commands", "promote.md")
REVIEW_DOC = os.path.join(CREW, "commands", "review.md")
REVIEW_VERDICT = os.path.join(CREW, "hooks", "scripts", "review_verdict.py")
REVIEW_LEDGER = os.path.join(CREW, "hooks", "scripts", "review_ledger.py")
REVIEW_RUN = os.path.join(CREW, "hooks", "scripts", "review_run.py")
PROMOTE_SH = os.path.join(CREW, "hooks", "scripts", "promote-gate.sh")
# Outside the crew plugin, for the same reason BUILD_REPORT is: promote.md
# claims things about the `bitbucket` entry's script, and the only way to
# sabotage a claim about another entry's interface is to break that interface.
MERGE_GATE = os.path.join(
    ROOT, "skills", "bitbucket", "scripts", "merge_gate.sh")
# The PowerShell half of the deploy gate. Added with the mutation that proves
# its `-ErrorAction Stop` is load-bearing: PROMOTE_SH alone covered the bash
# flavour, and "one flavour stands down and nothing notices" is this plugin's
# recurring failure rather than a hypothetical one.
PROMOTE_PS1 = os.path.join(CREW, "hooks", "scripts", "promote-gate.ps1")
# The Stop gate and its matched PowerShell pair, plus the two setup scripts
# that read the same `.crew/verify.json`. Four files rather than one because
# "a `run` entry is one command" is a claim about the MAP, and a rule the gate
# refuses while setup happily resolves it is the disagreement the rejection
# exists to remove -- so each reader is sabotaged separately.
VERIFY_SH = os.path.join(CREW, "hooks", "scripts", "verify-gate.sh")
VERIFY_PS1 = os.path.join(CREW, "hooks", "scripts", "verify-gate.ps1")
# The digest BOTH gates skip on, in one file so the two flavours cannot
# disagree about whether a turn changed anything. Sabotaged here rather than
# through either gate because it is the WRITER of the digest: a test that
# pre-computes a hash and asserts on the comparison stays green against a
# function that hashes nothing, and that vacuous shape is this file's subject.
FINGERPRINT = os.path.join(CREW, "hooks", "scripts", "verify_fingerprint.py")
RESOLVE_TOOLS = os.path.join(
    CREW, "skills", "crew-setup", "scripts", "resolve-tools.sh")
MAP_AUDIT = os.path.join(
    CREW, "skills", "crew-setup", "scripts", "map-audit.sh")
# Split out of `crew_state.py` on 2026-09-13 -- see its docstring. Five
# mutations below moved here with the code they target; none was
# re-anchored onto a nearby line, which this file's own header forbids.
GUARDS = os.path.join(CREW, "hooks", "scripts", "crew_guards.py")
# Split out of `crew_state.py` on 2026-09-14 -- see its docstring. ONE mutation
# below moved here with the code it targets, the diagram-kind one, because one
# is all that was anchored in the moved lines; it was not re-anchored onto a
# nearby line, which this file's own header forbids. Counted by reading every
# mutation's anchor text against the moved block rather than by eye, and the
# count is a fact about that block, not a target -- re-derive it if the seam
# moves again.
FRESHNESS = os.path.join(CREW, "hooks", "scripts", "crew_freshness.py")
GATE_DOC = os.path.join(CREW, "commands", "gate.md")
# The ten-question gate, and the command that routes through it. The gate is
# the only MECHANICAL part of `/crew:change`; everything else about the feature
# is prose, which is why two of its three mutations below patch a `.md`.
CHANGE_PY = os.path.join(CREW, "hooks", "scripts", "crew_change.py")

# The ticket's scope base (T-0003, crew 0.19.95) and the three prose files
# that must state the narrowed commit rule in one form. Two of the five
# mutations below patch `.md`: the rule IS prose, and the only mechanical
# regression is the sentence changing under the developer.
SCOPE_BASE = os.path.join(CREW, "hooks", "scripts", "scope_base.py")
SCOPE_REPORT = os.path.join(CREW, "hooks", "scripts", "scope_report.py")
DEVELOPER_MD = os.path.join(CREW, "agents", "developer.md")
WORK_MD = os.path.join(CREW, "commands", "work.md")

GUARD = '    if out["family"] is not None and out["family"] in authors:'
ROLE_PIN = '    decided = resolve_role(cfg, "dev", "developer")'
BLOCK_ONLY = (
    '    decided = {"family": family((dict_or_empty('
    'dict_or_empty(cfg).get("dev")).get("provider") or "claude"), None)}'
)

MUTATIONS = (
    (
        # The ratchet stops ratcheting: `min` becomes `max`, so the effective
        # value is the MORE permissive of the two layers. A cloned repo then
        # grants itself force-push rights, or `install.policy: auto`, on the
        # machine of anyone who cloned it -- the single defect the whole
        # narrowing rule exists to prevent.
        #
        # One character, in the one function permitted to combine the layers.
        # That is the point of generalising it into a table: before schema 6
        # this mutation had to be applied twice to cover two keys, and a third
        # copy could have been wrong without either mutation noticing.
        "the layer ratchet takes the WIDER of the two layers",
        GUARDS,
        "    return tiers[min(rank(repo_value), rank(global_value))]",
        "    return tiers[max(rank(repo_value), rank(global_value))]",
        ("tests/test_guards.py::"
         "test_the_effective_value_is_the_lower_rank_of_the_two_layers"),
    ),
    (
        # Normalisation is dropped from the rank, so an unknown value no
        # longer collapses to `block` -- it raises instead, and a raise inside
        # `resolve_ratcheted` reaches `crew_config.py --guard` as a non-zero
        # exit, which both shells read as `block`. So the FAIL-CLOSED outcome
        # survives by luck, through a different path, while the property under
        # test is gone.
        #
        # Anchored on the rank rather than on `normalise_guard_policy` itself:
        # mutating the normaliser's fallback would trip the normalisation test
        # AND this one, and a mutation that trips two tests tells you nothing
        # about either. This one leaves the normaliser correct and removes its
        # only use in the comparison, which is where the ordering is decided.
        "an unknown guard value is ranked without being normalised first",
        GUARDS,
        "    return GUARD_POLICIES.index(normalise_guard_policy(value))",
        "    return GUARD_POLICIES.index(value)",
        ("tests/test_guards.py::"
         "test_guard_policy_rank_orders_block_below_ask_below_allow"),
    ),
    (
        # The guard reads the REPO's RAW value instead of the resolved one --
        # the single line where the ratchet is actually consumed. A cloned
        # repo's `guards.forcePush: allow` then wins outright on a machine
        # whose owner said `block`.
        #
        # An earlier draft of this entry mutated guard.sh instead, dropping the
        # global layer out of the resolution with a `--global-path` pointing at
        # nothing. It came back STILL GREEN, correctly: an absent global file
        # resolves to the FLOOR, so that mutation made the guard more
        # restrictive rather than less, and proved nothing at all. Recorded
        # rather than quietly replaced, because "my mutation went the safe
        # direction" is indistinguishable from "the test is vacuous" unless
        # somebody writes down which it was.
        #
        # Every unit test of `effective_ratcheted` still passes under this
        # mutation -- the function is untouched. Only a test that runs the HOOK
        # against two layers catches it.
        "the guard reads the repo's raw guard value, not the resolved one",
        CONFIG,
        '    policy = resolved["effective"]',
        '    policy = resolved["repo"]',
        "tests/test_guards.py::test_a_repo_cannot_widen_the_production_level",
    ),
    (
        # The identical mutation, run against the OTHER flavour's test. The
        # duplication is deliberate: `guard.sh` and `guard.ps1` drift
        # independently -- three of the bypasses fixed in #132 were open in
        # both -- so a suite that proved one flavour's ratchet test non-vacuous
        # would be reporting coverage for a pair while testing half of it.
        "the guard reads the repo's raw guard value, not the resolved one "
        "(PowerShell flavour)",
        CONFIG,
        '    policy = resolved["effective"]',
        '    policy = resolved["repo"]',
        "tests/test_guards.py::test_a_repo_cannot_widen_the_production_level",
    ),
    (
        # THE one the production levels rest on: unknown becomes a read. Every
        # command the classifier positively recognises is still classified the
        # same way, so every `read` test that uses a real SELECT or a real
        # `tail` keeps passing -- only the commands crew CANNOT read change
        # answer, from refused to permitted. That is `read` silently becoming
        # `full` for exactly the inputs nobody can predict: an interactive
        # `psql prod-db-1`, an unrecognised binary over ssh, a command with an
        # unbalanced quote. The replacement is also the natural one to write,
        # which is why it needs a test rather than a reviewer.
        "an unclassifiable command counts as a read, so `read` permits what "
        "crew cannot read",
        GUARDS,
        # Anchored on `_classify_segment`'s fall-through, which is where an
        # unrecognised program over `ssh` actually lands. The fall-through at
        # the bottom of `classify_access` looks like the same claim and is
        # not: every unclassifiable case in the suite reaches a tool-specific
        # branch first, so mutating that one came back STILL GREEN -- a
        # mutation of a line no input reaches proves nothing about the line
        # that decides.
        '    if head in PROD_READ_COMMANDS:\n        return "read"\n'
        '    return "write"',
        '    if head in PROD_READ_COMMANDS:\n        return "read"\n'
        '    return "read"',
        ("tests/test_guards.py::"
         "test_everything_else_is_a_write_including_what_it_cannot_read"),
    ),
    (
        # The patterns start falling back to the machine-global file, so a
        # global `production` block reaches every repo that declared none.
        # Nothing looks wrong: the guard still refuses and still names a
        # pattern, it just names one from a file this repo never wrote, about
        # an estate that is not this one.
        #
        # Two earlier attempts came back STILL GREEN and both are worth
        # recording, because each was vacuous for its own reason. Routing
        # through `resolve_config` changes nothing: `filter_global` prunes
        # `production` out of the global layer before the merge, so the claim
        # is protected twice and that mutation defeats neither guard. Then
        # `... or read_global_config()` never fires, because a repo config
        # carrying `schema` is truthy whether or not it declares `production`
        # -- a fallback on the wrong object. This one merges, which is the
        # shape a well-meaning "make it work globally too" edit takes.
        # RE-ANCHORED a third time, and the reason is worth having: the line it
        # used to patch -- `cfg = crew_state.load_config(root) or {}` -- was
        # DELETED when `production_declaration` took over the read, because that
        # helper answers `{}` for absent, unparseable and not-an-object alike
        # and building four states on it would have reimplemented the collapse.
        # So this mutation now patches the point where the repo layer is found
        # to hold no `production` block at all, which is the same place the
        # global fallback would be written by anyone adding one.
        "the production patterns fall back to the machine-global file, so a "
        "global block reaches every repo",
        CONFIG,
        "    if \"production\" not in cfg:\n"
        "        return ProductionDeclaration(PROD_DECL_ABSENT, [], \"\")\n"
        "    block = cfg[\"production\"]",
        "    if \"production\" not in cfg:\n"
        "        cfg = read_global_config()\n"
        "    block = cfg.get(\"production\")",
        ("tests/test_guards.py::"
         "test_production_patterns_never_read_the_global_layer"),
    ),
    (
        # The ratchet reads the production levels through the POLICY
        # vocabulary. `none`/`read`/`full` are not in `GUARD_POLICIES`, so
        # every one of them normalises to `block` -- and `block` is not a
        # value these two keys have. The guard then reports a tier nobody set,
        # which is the two-vocabularies-in-one-block failure this table exists
        # to prevent.
        "the production guards are ranked by the block/ask/allow table",
        GUARDS,
        "    if name in PROD_GUARD_NAMES:\n"
        "        return (PROD_LEVELS, normalise_prod_level, prod_level_rank)",
        "    if False:\n"
        "        return (PROD_LEVELS, normalise_prod_level, prod_level_rank)",
        ("tests/test_guards.py::"
         "test_the_ratchet_is_one_table_covering_install_policy_and_all_four_"
         "guards"),
    ),
    (
        # The approval stops expiring, and `ask` quietly becomes a permanent
        # per-command `allow`. This is the mutation with the least visible
        # symptom in the file: every decision is still correct the first time,
        # the marker is still keyed on the command, both flavours still print
        # the same lines, and nothing goes wrong until a marker from another
        # day is still sitting in a gitignored directory nothing prunes. The
        # replacement is the obvious, natural spelling -- `os.path.exists` is
        # what this line said before the bound was added -- which is why it
        # needs a test rather than a reviewer.
        "an `ask` approval never expires, so one yes covers that command "
        "forever",
        CONFIG,
        "        if _approval_is_live(marker):",
        "        if os.path.exists(marker):",
        ("tests/test_guards.py::"
         "test_an_ask_approval_outside_the_window_asks_again"),
    ),
    (
        # `allow` goes silent: the row stops being written, so there is no
        # record that crew force-pushed. The command still runs and the guard
        # still exits 0, so nothing else in the suite changes -- which is the
        # whole danger. A machine owner chooses `allow` precisely so they are
        # not asked at the time, and the log is then the only place the event
        # exists once the session is gone.
        #
        # The mutation excludes `allow` from the call and nothing else, so the
        # block and ask rows keep being written and the only claim it breaks
        # is the one it is labelled with. An earlier version read `if False
        # and ...`, which stopped EVERY row -- the same effect as emptying
        # `_log_guard`'s body, while this comment claimed it was narrower. A
        # comment that misdescribes its own mutation is exactly the failure
        # this file's header is about, so it is corrected here rather than
        # quietly rewritten.
        #
        # RE-ANCHORED, not re-aimed: the anchor used to include `_maybe_log`'s
        # `if decision == "block" and not os.path.isdir(...)` line, which was
        # DELETED when the "never create `.crew/`" rule moved to `_log_guard`
        # (see the two D5 mutations below). The mutation itself is unchanged --
        # same insertion, same claim, same test -- and the anchor now ends at
        # the comment that follows, which is the nearest line that still exists
        # in the same function. This file's header forbids re-anchoring a
        # mutation whose CODE was deleted onto whatever is nearest; the code
        # this one mutates was not deleted, only the line it was written next
        # to.
        "under `allow` the guard stops recording what it let through",
        CONFIG,
        "    if not record:\n        return\n"
        "    # Tabs and newlines in a command would forge a row.",
        "    if not record:\n        return\n"
        "    if decision == \"allow\":\n        return\n"
        "    # Tabs and newlines in a command would forge a row.",
        "tests/test_guards.py::test_under_allow_nothing_is_silent",
    ),
    (
        # D2. `malformed` stops being one of the states that cannot be
        # answered, so a `production.hosts` holding a STRING is handed to
        # `prod_decision` as an empty pattern list again -- which reads it as
        # "nothing declared, nothing matches, allow". The `unreadable` half is
        # left intact on purpose: this is the exact defect that shipped, the
        # wrong-SHAPED config rather than the unreadable file, and a mutation
        # that broke both would go red on either test and prove nothing about
        # which of them covers this one.
        "a wrong-shaped `production` block is treated as nothing declared",
        CONFIG,
        "        if declared.state in (PROD_DECL_MALFORMED, "
        "PROD_DECL_UNREADABLE):",
        "        if declared.state in (PROD_DECL_UNREADABLE,):",
        ("tests/test_malformed_production_never_permits.py::"
         "test_a_declaration_crew_cannot_read_blocks_a_write"),
    ),
    (
        # D2, the platform half. Drop `NotADirectoryError` and `.crew` being a
        # plain FILE goes back to `unreadable` on POSIX while staying `absent`
        # on Windows -- one repo state, two verdicts, and the blocking one lands
        # on a repo that never opted in. The forced-exception test is what makes
        # this red on either platform; a fixture can only raise whichever
        # exception the runner's own OS picks, which is how it shipped green.
        "a config that is not there blocks, on one platform only",
        CONFIG,
        "    except (FileNotFoundError, NotADirectoryError):",
        "    except FileNotFoundError:",
        ("tests/test_unmanaged_repo_is_left_untouched.py::"
         "test_a_config_that_is_not_there_reads_absent_on_every_platform"),
    ),
    (
        # D2, the half no in-process test can see. The refusal keeps every
        # word of its reason and loses only the TARGET, which is the field both
        # shells check first: `prod_guarded` in guard.sh and Invoke-ProdGuard
        # in guard.ps1 each `return` silently when it is empty, before looking
        # at the decision at all. So this mutation is invisible to
        # `guard_decision`'s callers in python and turns the hook back into
        # exit 0 with nothing printed. `""` is also the honest-looking value a
        # reviewer would suggest ("no pattern matched, so name none").
        "a refusal crew cannot back with a pattern is swallowed by the hooks",
        CONFIG,
        "            f\"<unread production.{PROD_DECL_KEYS[name]}>\", access)",
        "            \"\", access)",
        "tests/test_malformed_production_never_permits.py",
    ),
    (
        # D5. The `makedirs` goes back, which is the single line that adopted a
        # plain repo into crew: the next SessionStart resolves its root from
        # bare `.crew/` presence and heal_config writes a default config into
        # it. Every other assertion in the suite still passes -- the row is
        # still written, the decision is unchanged, and in a real crew repo the
        # directory already exists so nothing differs at all.
        "the guard log creates `.crew/` in a repo that never opted in",
        CONFIG,
        "        if not os.path.isdir(os.path.dirname(path)):\n            return",
        "        os.makedirs(os.path.dirname(path), exist_ok=True)",
        ("tests/test_unmanaged_repo_is_left_untouched.py::"
         "test_an_allowed_command_then_a_session_start_leaves_nothing_behind"),
    ),
    (
        # D3, bash. The exit-status check on the env-resolution step goes away,
        # so a verify.json that will not parse leaves ENVNAME empty and the
        # `[ -z "$ENVNAME" ] && exit 0` below reads that as "this command
        # deploys nothing". Mutated to `-eq 999` rather than deleted, for the
        # same reason the VERDICT_STATUS mutation above is: the surrounding
        # message and the empty-ENVNAME test still read correctly, so the file
        # looks complete.
        "the promote gate reads an unparseable map as `not a deployment`",
        PROMOTE_SH,
        'if [ "$ENV_STATUS" -ne 0 ]; then',
        'if [ "$ENV_STATUS" -eq 999 ]; then',
        ("tests/test_promote_gate_unreadable_map.py::"
         "test_sh_blocks_on_the_stray_comma_that_started_this"),
    ),
    (
        # D3, PowerShell. `-ErrorAction Stop` goes away and Get-Content's
        # failure becomes non-terminating again, so the catch never fires, $vm
        # stays null, and the `environments` test two lines down reads the
        # corruption as a map that declares nothing. The parse-error path is
        # untouched, so the mutation isolates UNREADABLE from UNPARSEABLE --
        # they are different facts and the .ps1 only ever covered one.
        "promote-gate.ps1 reads an unreadable map as one that gates nothing",
        PROMOTE_PS1,
        "Get-Content .crew/verify.json -Raw -ErrorAction Stop",
        "Get-Content .crew/verify.json -Raw",
        ("tests/test_promote_gate_unreadable_map.py::"
         "test_ps1_blocks_when_the_map_is_not_a_file_at_all"),
    ),
    (
        # `/crew:gate` stops reading `guards.mergeGate` before it acts. The
        # command still names the key elsewhere in the file, so a grep for
        # "guards.mergeGate" still finds it and the routing assertions still
        # pass -- only the ORDER is gone, and the order is the whole property:
        # a policy read after the provider is resolved is a policy read after
        # a real `export` API call has already happened against a live repo.
        "/crew:gate reads guards.mergeGate after resolving the provider",
        GATE_DOC,
        "## 0. Read `guards.mergeGate` first, before anything else",
        "## 0. Preflight",
        ("tests/test_gate_command.py::"
         "test_guards_merge_gate_is_read_first_and_by_name"),
    ),
    (
        # `--brand` stops existing on the findings-report script, so crew's
        # routing table names a flag the tool does not accept -- the ticket's
        # original defect (prose describing an interface nobody ran) one layer
        # out.
        #
        # Mutated at the CALL SITE rather than in the table, because that is
        # the half a grep cannot check: neither script spells "--brand"
        # literally, both get it from `resolve_brand.add_brand_argument`, and
        # both docstrings show `--brand neutral` in an example. So grepping
        # either file "confirms" the flag whether or not it is wired to
        # anything. The test asks argparse instead.
        #
        # build_report.py and not build_sop.py: build_report is stdlib (its
        # win32com import is lazy), so this mutation runs on any machine,
        # including a CI runner with neither python-docx nor pywin32.
        "the findings-report script stops accepting --brand",
        BUILD_REPORT,
        "    resolve_brand.add_brand_argument(ap)",
        "    pass  # resolve_brand.add_brand_argument(ap)",
        ("tests/test_docs_routing.py::"
         "test_every_routed_script_exists_and_accepts_brand"),
    ),
    (
        # The routing entry goes, which is the state this whole ticket was
        # opened for: `docs.theme` configuring a tool crew's own documented
        # generation path never mentions, so there is no call site for a
        # `--brand` to attach to and the setting quietly does nothing.
        #
        # Re-anchored 2026-09-22: the routing bullet grew an "as HTML, DOCX
        # or PDF" clause when the HTML route was added (commit 1741f233),
        # which split the old one-line anchor across two lines. Same bullet,
        # same key rename.
        "doc-builder is dropped from the routing table",
        HOUSE_STYLE,
        "- `doc-builder` — branded findings reports and screenshot SOPs, as HTML,\n"
        "  DOCX or PDF. Pass `--brand <docs.theme>`;",
        "- `doc-builder-removed` — branded findings reports and screenshot SOPs, as HTML,\n"
        "  DOCX or PDF. Pass `--brand <docs.theme>`;",
        "tests/test_docs_routing.py::"
        "test_the_routing_table_routes_doc_builder_and_names_both_keys",
    ),
    (
        # `docs.reportTheme` stops being bound to the report genre, so it
        # degrades into a synonym for `docs.theme`: two keys, one meaning, and
        # the client-deliverable case the second key exists for silently
        # stops being expressible. Nothing else in the suite notices, because
        # the key still merges and still resolves.
        #
        # Re-anchored 2026-09-22: the routing bullet's genre-binding sentence
        # moved onto its own line when the bullet was rewritten for the HTML
        # route (commit 1741f233); the anchor below is that line, verbatim.
        "reportTheme is no longer bound to the report genre",
        HOUSE_STYLE,
        "  for a findings report prefer `docs.reportTheme` when it is set.",
        "  the brand applies to every generated document when it is set.",
        "tests/test_docs_routing.py::"
        "test_the_two_config_keys_are_bound_to_different_genres",
    ),
    (
        # The sharper half of the same defect, and the one the first mutation
        # could not reach. The key STAYS in the sentence -- only the genre
        # widens -- so the test's "is reportTheme bound to anything" assertion
        # still passes and the binding assertion is the only thing that can
        # catch it. The original assertion here was `"report" in line`, which
        # `docs.reportTheme` satisfies by its own name; it went red on this
        # entry's sibling above for the WRONG assert and so read as covered.
        #
        # Re-anchored 2026-09-22 alongside its sibling above, same line, same
        # reason.
        "reportTheme widens to every document, not just the findings report",
        HOUSE_STYLE,
        "  for a findings report prefer `docs.reportTheme` when it is set.",
        "  for every document prefer `docs.reportTheme` when it is set.",
        "tests/test_docs_routing.py::"
        "test_the_two_config_keys_are_bound_to_different_genres",
    ),
    (
        # The defect the rule exists to forbid, written as the thing a helpful
        # person would actually write. An unresolvable theme is the one failure
        # here that is the CONFIG's fault rather than the machine's, and falling
        # back to unbranded is the worst outcome available: the user named a
        # brand, so an unbranded document is wrong in exactly the way they
        # configured against, and nothing in the artefact says so. The two
        # degraded paths above both leave a trace -- a different tool in the
        # handoff, or doc-builder's own message. This one leaves none.
        "an unresolvable theme falls back to unbranded instead of stopping",
        HOUSE_STYLE,
        "**Relay doc-builder's error and stop.**",
        "**Produce the document unbranded and note it in the handoff.**",
        "tests/test_docs_routing.py::"
        "test_an_unresolvable_theme_is_relayed_and_never_falls_back",
    ),
    (
        # The other half, and the one that looks like an improvement. Checking
        # the theme name before calling reads as defensive programming, and it
        # is the same mistake as crew probing for Word: a second copy of
        # doc-builder's check that goes stale on doc-builder's next release.
        # Worse here, because doc-builder accepts a skill directory name, a
        # path, a directory and `neutral` -- so an allowlist of installed pack
        # names rejects valid configuration and blocks work that would have
        # succeeded.
        "crew is allowed to validate the theme name itself",
        HOUSE_STYLE,
        "**Do not validate the theme name before calling.**",
        "**Check the theme name against the installed packs before calling.**",
        "tests/test_docs_routing.py::"
        "test_an_unresolvable_theme_is_relayed_and_never_falls_back",
    ),
    (
        # The justification, not the rule. A bare prohibition with its reason
        # removed is the shape that gets "simplified" away by the next reader,
        # who cannot see what it was protecting. This mutation leaves the rule
        # standing and deletes only why it is true.
        "the reason a crew-side allowlist is wrong is removed",
        HOUSE_STYLE,
        "would therefore fail closed on correct configuration, which is the expensive",
        "is therefore a reasonable belt-and-braces check, which is the safe",
        "tests/test_docs_routing.py::"
        "test_crew_is_not_told_to_allowlist_theme_names",
    ),
    (
        # The sentence that actually shipped. "HTML needs no skill; write the
        # file and apply the palette above" sent four hand-written guides out
        # with no print discipline at all -- the palette is colours, and the
        # route said nothing about a page boundary. The mutation puts the
        # markup half back the way it was: the header row is still there and
        # still styled, it is simply not a `<thead>`, which is precisely the
        # state a reader cannot see in a browser and only meets in a PDF.
        "the HTML route stops requiring a real thead element",
        HOUSE_STYLE,
        "1. **Every table gets a real `<thead>`** around its header row, and a",
        "1. **Style the header row** with the `th` rule in the palette, and a",
        "tests/test_docs_routing.py::"
        "test_the_html_route_requires_a_real_thead",
    ),
    (
        # The CSS half, deleted one declaration at a time rather than as a
        # block -- deleting the whole `@media print` rule trips the
        # `"@media print" in route` assertion first and would leave the
        # per-declaration assertions unproven, which is this file's documented
        # blind spot. `thead` is the declaration to take: it is the one that
        # looks redundant beside the markup rule and is not.
        "the print block loses the repeated-table-header declaration",
        HOUSE_STYLE,
        "     thead { display:table-header-group; }",
        "     /* header repeat is the browser's default */",
        "tests/test_docs_routing.py::"
        "test_the_html_route_carries_the_print_rules",
    ),
    (
        # The widening, taken back out. This is the mutation that looks like
        # tidying: doc-builder's block names `h2` alone, so narrowing crew's
        # copy to match reads as removing a divergence. It is not -- that
        # generator emits no `h3` and the house style allows one, so `h2` only
        # is exactly the state the first re-render was measured in, with `h3`
        # headings still ending a page ahead of their table.
        "the print block narrows back to h2, dropping h3",
        HOUSE_STYLE,
        "     h2, h3 { page-break-after:avoid; }",
        "     h2 { page-break-after:avoid; }",
        "tests/test_docs_routing.py::"
        "test_the_html_route_carries_the_print_rules",
    ),
    (
        # The cross-entry claim, sabotaged the only way a claim about another
        # marketplace entry can be: by breaking the interface it names. crew's
        # prose cites build_report.py by path and line for these three
        # declarations, and a citation into a separate entry goes stale with
        # nothing in crew changing.
        "the generator crew cites stops emitting a thead",
        BUILD_REPORT,
        '    out += ["  </tr></thead>", "  <tbody>"]',
        '    out += ["  </tr>", "  <tbody>"]',
        "tests/test_docs_routing.py::"
        "test_the_print_rules_match_the_generator_that_proves_them",
    ),
    (
        # The citation rots while every claim it supports stays true. This is
        # not hypothetical and not a mutation invented for the suite: it is
        # the exact state the tree was in. A doc-builder change inserted ten
        # lines, `155-157` became `165-167`, and every test in
        # test_docs_routing.py stayed green because all of them search the
        # whole file for the declarations and none of them read the lines
        # crew names.
        "the print-block citation points at the wrong lines",
        HOUSE_STYLE,
        "`skills/doc-builder/scripts/house_style.py:255-257` \u2014 the body of",
        "`skills/doc-builder/scripts/house_style.py:254-256` \u2014 the body of",
        "tests/test_docs_routing.py::"
        "test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold",
    ),
    (
        # The other half of the same rot, and the worse-looking one: `123` is
        # not merely off, it lands in the middle of the masthead CSS, so a
        # reader following the citation finds a rule about a coloured strip
        # and concludes the comment was deleted.
        #
        # Kept as its own mutation rather than folded into the one above
        # because the two citations are checked by different assertions -- a
        # range against the declarations it spans, a single line against the
        # text crew quotes from it -- and a mutation going red proves the TEST
        # failed, never which assertion did.
        "the report profile's table-comment citation points at the wrong line",
        HOUSE_STYLE,
        '`skills/doc-builder/scripts/house_style.py:357`, "Every table: real',
        '`skills/doc-builder/scripts/house_style.py:347`, "Every table: real',
        "tests/test_docs_routing.py::"
        "test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold",
    ),
    (
        # The citation goes back to the bare-filename form. It still resolves
        # by eye and still names the right line, so nothing a reader sees is
        # wrong -- which is why this needs a mutation of its own. What it
        # loses is the only mechanism that re-checks it: `build_report.py:133`
        # cannot be pasted into `git diff --name-only <anchor>..HEAD -- <path>`.
        "the citation drops its repo-relative path",
        HOUSE_STYLE,
        "at\n`skills/doc-builder/scripts/house_style.py:367`,",
        "at\n`house_style.py:367`,",
        "tests/test_docs_routing.py::"
        "test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold",
    ),
    (
        # The comment crew quotes occurs TWICE in house_style.py, once in each
        # profile branch of `stylesheet()`, so the route cites both lines. This
        # collapses the guide profile's citation onto the report profile's
        # line. Every character of it still resolves -- that line really does
        # hold that comment -- and the guide profile's copy is now pinned by
        # nothing at all, while the section reads as though both were checked.
        #
        # This is the mutation the duplicate comment made necessary. Before the
        # extraction there was one occurrence and this state could not exist.
        "both table-comment citations collapse onto one line",
        HOUSE_STYLE,
        '`skills/doc-builder/scripts/house_style.py:367`, "Every table: real',
        '`skills/doc-builder/scripts/house_style.py:357`, "Every table: real',
        "tests/test_docs_routing.py::"
        "test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold",
    ),
    (
        # The generated output, which is the only place a PARAMETERISED
        # selector can be checked. `print_css` takes `headings`; the report
        # profile passes "h2" and the guide profile "h2, h3". Nothing in
        # house_style.py's source text contains the rule crew cites, so every
        # source-reading assertion in the suite stays GREEN through this
        # mutation -- verified by running it, and only the generated-output
        # test goes red.
        #
        # That is the point of the mutation: it is the one defect in this
        # cluster that no amount of reading the file can catch, and without a
        # generated-output check it would ship.
        "the report profile stops emitting the heading page-break rule",
        HOUSE_STYLE_PY,
        'print_css("h2")',
        'print_css("h4")',
        "tests/test_docs_routing.py::"
        "test_the_generated_stylesheet_emits_the_print_rules",
    ),
    (
        # The shipped document loses a print declaration. The `thead` one
        # again, and for the same reason it was chosen in the route's own
        # mutation above: deleting the whole block trips the "no @media print
        # at all" assertion first and leaves the per-declaration check
        # unproven, which is this file's documented blind spot.
        "a shipped guide loses the repeated-table-header declaration",
        GUIDE_HTML,
        "  thead { display:table-header-group; }",
        "  thead { display:table-cell; }",
        "tests/test_docs_routing.py::"
        "test_every_shipped_guide_carries_the_print_block",
    ),
    (
        # And the markup half, in the artefact rather than in the prose: one
        # table goes back to a bare `<tr>` of `<th>`, which is what all
        # twenty-seven of them were. The other four tables in the file keep
        # their thead, so a count-based assertion -- 5 tables, 4 theads -- and
        # a per-table one both fail here; a count assertion would NOT fail if
        # some other table grew a second thead, which is why the test walks
        # each table on its own.
        "a table in a shipped guide goes back to a bare header row",
        GUIDE_HTML,
        "<thead><tr><th>Habit</th><th>What it costs</th>"
        "<th>What crew does about it</th></tr></thead>",
        "<tr><th>Habit</th><th>What it costs</th>"
        "<th>What crew does about it</th></tr>",
        "tests/test_docs_routing.py::"
        "test_every_table_in_every_shipped_guide_has_a_real_thead",
    ),
    (
        # The false sentence itself. `upgradeNeeded` shipped ONE fixed string
        # -- "config has no schema" -- and bumping SCHEMA_CURRENT to 4 aimed
        # it at every schema-2 and schema-3 repo in existence. It sorts third
        # in TRIGGERS, so it leads the brief: the first thing a user reads
        # after a mandatory migration described a situation they are not in.
        "every repo is told its config has no schema, whatever it declares",
        PM_BRIEF,
        "    if not key_present:",
        "    if True:",
        "tests/test_pm_brief.py::"
        "test_a_repo_with_a_schema_is_not_told_it_has_none",
    ),
    (
        # A schema `int_or` cannot read collapses to 1, and 1 reads as a
        # pre-PM config. The user then hunts a migration instead of the
        # character they mistyped. This repo's named recurring bug, in the
        # sentence that reports it.
        "an unparseable schema is reported as a pre-PM config",
        PM_BRIEF,
        "    elif crew_state.int_or(declared, None) is None:",
        "    elif False:",
        "tests/test_pm_brief.py::"
        "test_an_unparseable_schema_is_reported_as_a_typo_not_as_a_pre_pm_config",
    ),
    (
        # ABSENT and None collapsed into one, which is the same bug one level
        # up: every hand-built state -- the crew:pm agent's, a stale cache's
        # -- would be told its config declares no schema.
        "an absent schemaDeclared is read as an explicit null",
        PM_BRIEF,
        "        declared, key_present = schema, True",
        "        declared, key_present = None, False",
        "tests/test_pm_brief.py::"
        "test_a_hand_built_state_without_the_key_is_not_told_it_has_no_schema",
    ),
    (
        # collect() stops carrying the raw value, so the real SessionStart
        # path silently falls back to the hand-built branch. Every hand-built
        # test above keeps passing; only a test that drives the collector on a
        # real repo can see it.
        "collect() no longer carries the raw declared schema",
        STATE,
        '        "schemaDeclared": raw_cfg.get("schema") if raw_cfg else None,',
        '        "schemaDeclaredGone": None,',
        "tests/test_pm_brief.py::"
        "test_collect_carries_the_raw_schema_so_the_brief_can_tell_them_apart",
    ),
    (
        # The command's half. The brief names the hop and nothing explains
        # what that migration does -- a user reads a version number and is
        # told to run a command whose report walks past the entry for it.
        #
        # RE-PINNED to the CURRENT hop when schema 5 landed, and again at 7.
        # It targeted "Schema 3 -> 4", and the paired test asserts the entry
        # for SCHEMA_CURRENT, so once the current hop moved on this
        # mutation deleted an entry nothing checks and reported STILL
        # GREEN. That happened again at schema 7, and this suite said so
        # rather than the bump shipping with the mutation pointing at 5 -> 6.
        # Every schema bump has to move this string; that edit is
        # the point, not an inconvenience, and the suite says so out loud
        # when it is forgotten.
        "the current migration loses its entry in upgrade.md section 5",
        UPGRADE_DOC,
        "- **Schema 6 \u2192 7**",
        "- **The change-request migration**",
        "tests/test_pm_brief.py::"
        "test_the_brief_and_upgrade_md_agree_on_the_current_migration",
    ),
    (
        # Codex's finding, and the reason `schemaKeyPresent` exists at all.
        # `{"schema": null}` reads back from `.get()` as None, the same value
        # an ABSENT key gives -- so keying the "no schema" sentence on the
        # VALUE calls an explicit null a pre-PM config and sends the user
        # hunting a migration instead of the word they typed. The same
        # collapse the whole finding was rewritten to remove, one level down.
        "an explicit null schema is read as an absent one",
        PM_BRIEF,
        '        key_present = bool(state.get("schemaKeyPresent"))',
        "        key_present = declared is not None",
        "tests/test_pm_brief.py::"
        "test_an_explicit_null_schema_is_not_read_as_an_absent_one",
    ),
    (
        # The collector half. Every hand-built test keeps passing without
        # this flag because it supplies the flag itself; only a test driven
        # through collect() on a real repo can see it go missing.
        "collect() no longer records whether the schema key is present",
        STATE,
        '        "schemaKeyPresent": bool(raw_cfg) and "schema" in raw_cfg,',
        '        "schemaKeyPresentGone": False,',
        "tests/test_pm_brief.py::"
        "test_an_explicit_null_schema_is_not_read_as_an_absent_one",
    ),
    (
        # doc-builder takes DOCX and PDF over generally -- the "simplification"
        # that looks tidier and breaks crew's document path on Linux and macOS,
        # because doc-builder's converter runs through Microsoft Word via COM
        # and anthropic-office-skills needs neither.
        "doc-builder is given DOCX and PDF outright",
        HOUSE_STYLE,
        "- `anthropic-office-skills:docx` — DOCX\n"
        "- `anthropic-office-skills:pdf` — PDF",
        "- `doc-builder` — DOCX and PDF",
        "tests/test_docs_routing.py::"
        "test_anthropic_office_skills_keeps_docx_and_pdf",
    ),
    (
        # The two degraded paths collapse into one sentence. A missing Word is
        # then reported as a missing doc-builder, which sends the reader to
        # install something they already have while the actual cause -- an
        # absent Word COM pipeline -- goes unmentioned. Same misdiagnosis shape
        # as the PSModulePath trap.
        "the two degraded paths are conflated into one",
        HOUSE_STYLE,
        "  branded HTML report and, through `python-docx`, the branded SOP `.docx`. So",
        "  document unbranded via anthropic-office-skills, exactly as above. So",
        "tests/test_docs_routing.py::"
        "test_the_two_degraded_paths_are_stated_separately",
    ),
    (
        # Crew is told to probe for Word after all -- a second copy of
        # doc-builder's capability check living in a different repo entry,
        # which is what the table's own "Do not reimplement any of them" rule
        # exists to prevent, and which goes stale the moment doc-builder's
        # requirements change.
        "crew is told to detect Word itself",
        HOUSE_STYLE,
        "**Do not detect Word yourself.**",
        "**Check whether Word is available before routing.**",
        "tests/test_docs_routing.py::test_crew_is_told_not_to_detect_word_itself",
    ),
    (
        # The table names a script that does not exist. This is the ticket's
        # original defect one layer out: prose describing an interface nobody
        # ran. The check that catches it invokes the script's own argparse, so
        # a renamed or removed script fails here rather than at handoff time
        # in front of whoever the document was for.
        #
        # Re-anchored 2026-09-22: the sentence naming `build_report.py` now
        # ends in an em dash rather than a comma (the HTML route rewrite,
        # commit 1741f233, added "— its HTML is a finished deliverable..."
        # after it). Same script name, same bullet.
        "the routing table names a script that does not exist",
        HOUSE_STYLE,
        "`scripts/build_report.py` is the findings report —",
        "`scripts/build_findings.py` is the findings report —",
        "tests/test_docs_routing.py::"
        "test_the_routed_scripts_are_the_ones_the_table_names",
    ),
    (
        # The global warning stops checking whether the repo has an answer of
        # its own, and starts firing on repos the global can never reach. It
        # then states something false -- that a global neutral "is the value
        # this repo now resolves to" on a repo whose theme is `solomon` -- and
        # sends the reader to edit a machine-global file that would change
        # nothing there and something in every other repo on the machine.
        "the global warning fires even when the repo names its own theme",
        UPGRADE,
        '    if notes["docsThemeAfter"] is None and global_theme_defeats_migration():',
        '    if global_theme_defeats_migration():',
        ("tests/test_upgrade.py::"
         "test_the_global_warning_stays_quiet_when_the_repo_names_its_own_theme"),
    ),
    (
        # The rewrite stops being atomic with the schema stamp. A single
        # wrong-typed block anywhere then produces a config with a null theme
        # and schema still at 3 -- so repairing the block and setting neutral
        # back re-runs the rewrite and erases it a second time. Half a
        # migration that keeps re-applying its own half.
        "the theme rewrite is no longer atomic with the schema stamp",
        UPGRADE,
        '    if (notes["schemaStamped"]\n'
        '            and notes["schemaFrom"] < _DOCS_THEME_REWRITTEN_UNTIL_SCHEMA',
        '    if (notes["schemaFrom"] < _DOCS_THEME_REWRITTEN_UNTIL_SCHEMA',
        ("tests/test_upgrade.py::"
         "test_a_partly_failed_migration_does_not_rewrite_the_theme"),
    ),
    (
        # The global warning goes. The repo config comes out migrated and the
        # EFFECTIVE theme is unchanged, because repo null defers to the global
        # file that still says neutral. That is the worse of the two states --
        # it looks fixed -- and silence is what makes it so.
        "a global neutral that defeats the migration is not reported",
        UPGRADE,
        '    if notes["docsThemeAfter"] is None and global_theme_defeats_migration():',
        "    if False:",
        ("tests/test_upgrade.py::"
         "test_a_global_neutral_is_reported_because_it_defeats_the_migration"),
    ),
    (
        # The global read stops being best-effort. `global_theme_defeats_
        # migration` runs while BUILDING THE REPORT, which is after the repo
        # config has already been written -- so an unreadable global file
        # would take down a run whose real work had succeeded, and the caller
        # could not tell a failed upgrade from a failed report.
        "the global config read is no longer best-effort",
        UPGRADE,
        "    except (OSError, ValueError):\n        return False",
        "    except KeyError:\n        return False",
        ("tests/test_upgrade.py::"
         "test_an_unreadable_global_config_is_not_a_crash_or_a_warning"),
    ),
    (
        # conftest isolates only `crew_config`'s binding again. `crew_upgrade`
        # reads the path through `crew_state`, so the suite goes back to
        # reading the DEVELOPER'S REAL ~/.claude/crew/config.json -- the exact
        # thing that fixture exists to prevent. It fails loudly here and is
        # otherwise invisible: on a machine whose global config happens not to
        # set a theme, every test still passes.
        "the global-config isolation fixture patches only one of the two names",
        CONFTEST,
        '    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", unused)\n'
        '    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", unused)',
        '    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", unused)',
        ("tests/test_upgrade.py::"
         "test_the_suite_cannot_reach_the_real_machine_global_config"),
    ),
    (
        # The schema stays one behind -- the shape that shipped to Codex for
        # review as "3" and
        # what Codex caught by RUNNING it: status "already current", value
        # unchanged. The rewrite below is untouched and still perfect -- it
        # simply never executes, because run() returns before calling
        # upgrade_config for any config at or above SCHEMA_CURRENT, and every
        # existing config is already at the older number. Re-pinned to 4 -> 5
        # when install.policy cut schema 5; the mutation is "do not bump",
        # whatever the current pair of numbers happens to be.
        #
        # The mutation is pinned here because it is invisible to every unit
        # test of the transformation itself: `upgrade_config` is pure and goes
        # on passing. Only an end-to-end run through `run()` sees it, which is
        # exactly the gap that let it reach review.
        "the schema is not bumped, so the migration never runs",
        STATE,
        "SCHEMA_CURRENT = 7",
        "SCHEMA_CURRENT = 6",
        # Re-pinned AGAIN at schema 7, and the reason has not changed since the
        # first two re-pins: the test this entry names has to migrate a repo at
        # the IMMEDIATELY PREVIOUS schema, or reverting the bump leaves that
        # repo behind either way and the mutation comes back STILL GREEN. It
        # did exactly that, twice, and was caught by this suite rather than by
        # reading it. So the pair of numbers AND the test both move on every
        # bump; neither move is optional and neither is sufficient alone.
        "tests/test_change_command.py::"
        "test_the_schema_7_bump_reaches_a_repo_at_schema_6",
    ),
    (
        # The one-shot gate goes, so the rewrite matches on the VALUE forever.
        # A user who takes the upgrade report at its word -- "if you did mean
        # neutral, set it again and it will now be honoured" -- has it erased
        # by the next `--force`, and by every force after that. The report
        # then states something the code contradicts, which is worse than
        # having made no promise.
        "the theme rewrite is no longer one-shot",
        UPGRADE,
        '            and notes["schemaFrom"] < _DOCS_THEME_REWRITTEN_UNTIL_SCHEMA\n'
        '            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")',
        '            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")',
        ("tests/test_upgrade.py::"
         "test_a_deliberately_restored_neutral_survives_a_forced_rerun"),
    ),
    (
        # The pre-0.18.0 default, restored. This is the mutation that matters
        # on this change, because restoring it breaks NOTHING visible: the key
        # still has no consumer, so no document comes out differently and no
        # other test notices. It only becomes a de-branding bug later, when the
        # wiring lands and every upgraded repo starts passing an explicit
        # `--brand neutral` over an installed pack. A defect whose damage is
        # deferred to a future commit is exactly the kind a suite forgets to
        # hold, so it is pinned here rather than left to the templates.
        "docs.theme default goes back to the string neutral",
        UPGRADE,
        '    "theme": None,\n    "reportTheme": None,',
        '    "theme": "neutral",\n    "reportTheme": None,',
        ("tests/test_upgrade.py::"
         "test_upgrade_config_adds_the_docs_and_bitbucket_blocks"),
    ),
    (
        # The migration silently does nothing. The template change alone is
        # NOT the fix: `_merged` lets a supplied value win, so an existing
        # config carrying "neutral" keeps it forever and only NEW repos get
        # null. Deleting the rewrite leaves every already-installed machine in
        # the broken state while a fresh clone looks correct -- the "exists
        # only on other people's machines" shape this repo keeps paying for.
        "the neutral -> null migration is dropped",
        UPGRADE,
        '    if (notes["schemaStamped"]\n'
        '            and notes["schemaFrom"] < _DOCS_THEME_REWRITTEN_UNTIL_SCHEMA\n'
        '            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")\n'
        '            == _DOCS_THEME_REWRITTEN_FROM):\n'
        '        notes["rewrittenKeys"].append("docs.theme")\n'
        '        out["docs"]["theme"] = None',
        '    pass',
        ("tests/test_upgrade.py::"
         "test_upgrade_rewrites_the_old_neutral_theme_default_to_null"),
    ),
    (
        # The rewrite stops being announced. The value still changes under the
        # user; only the sentence explaining it disappears. That is the worse
        # half of the two: a config that differs from what someone wrote, with
        # the upgrade report silent about which value moved and why it was
        # allowed to.
        "a rewritten theme is no longer reported",
        UPGRADE,
        '    if "docs.theme" in notes["rewrittenKeys"]:',
        '    if False:',
        ("tests/test_upgrade.py::"
         "test_the_report_explains_a_rewritten_theme_and_stays_quiet_otherwise"),
    ),
    (
        # The rewrite over-reaches and catches every theme, not just the old
        # default. This is the fix performing the exact bug it exists to
        # prevent: a user who deliberately set `solomon` gets silently
        # de-branded BY THE MIGRATION. Cheap to write by accident -- it is one
        # comparison loosened to a truthiness check.
        "the migration rewrites any theme, not only the old default",
        UPGRADE,
        '            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")\n'
        '            == _DOCS_THEME_REWRITTEN_FROM):',
        '            and crew_state.dict_or_empty(cfg.get("docs")).get("theme")):',
        ("tests/test_upgrade.py::"
         "test_upgrade_rewrites_only_the_exact_old_default"),
    ),
    (
        # The pre-0.17.0 form, restored. It is wrong in BOTH directions once a
        # third tier exists: act -> autonomous reads as no widening (the widest
        # grant crew offers, shipped unannounced), and autonomous -> act reads
        # as a widening when it is a narrowing. The matrix test is what makes
        # the second half visible -- a suite carrying only the two transitions
        # that existed at two tiers stays green with this bug restored, which
        # is precisely why the matrix is enumerated as data.
        # Re-pinned when `install.policy` made the ratchet shared: the
        # comparison moved out of the change-entry literal and into `_widens`.
        # The mutation is unchanged in substance -- restore the pre-0.17.0
        # equality test -- and it is still the registry's single copy of the
        # rule that is being corrupted, which is the point of having one.
        "widening test compares authority by equality instead of rank",
        CONFIG,
        "    rank = spec[0]\n"
        "    return rank(after) > rank(None if before is _MISSING else before)",
        "    return (crew_state.normalise_authority(after) == \"act\"\n"
        "            and crew_state.normalise_authority(\n"
        "                None if before is _MISSING else before) != \"act\")",
        ("tests/test_crew_config.py::"
         "test_every_authority_transition_is_classified"),
    ),
    (
        # Codex's round-1 FIX on this branch, restored. The `!` line named a
        # hardcoded tier, so setting `autonomous` warned about `act` and
        # described only what `act` grants -- omitting the one thing the tier
        # adds. Same bug class as the rank fix two entries up: the warning
        # under-describes the grant it is there to announce.
        "the widening warning names a hardcoded tier",
        CONFIG,
        '                _, normalise, notes = _RATCHETED[change["path"]]\n'
        '                granted = normalise(change["after"])\n'
        '                print(f"  ! {change[\'path\']} widens to `{granted}`: "\n'
        '                      + notes[granted])',
        '                print("  ! pm.authority widens to `act`: the PM will '
        'dispatch "\n'
        '                      "roles itself and report after.")',
        ("tests/test_crew_config.py::"
         "test_the_widening_warning_names_the_tier_it_grants"),
    ),
    (
        # A capability gate that names a rung instead of a floor. Restoring it
        # makes `autonomous` -- the WIDER tier -- unable to act at all, which
        # presents as "the new tier does nothing" rather than as a guard bug.
        "can_act names a rung instead of a floor",
        STATE,
        '    return authority_rank(pm.get("authority")) >= authority_rank("act")',
        '    return normalise_authority(pm.get("authority")) == "act"',
        "tests/test_pm_brief.py::test_autonomous_can_act_too",
    ),
    (
        # An unknown authority collapsing UPWARD is the repo's named recurring
        # bug class, in the one field where it grants capability. `index` on a
        # raw value would raise, so the mutation returns the top rank instead:
        # the shape a "be permissive on bad input" fix would actually take.
        "an unreadable authority ranks highest instead of lowest",
        STATE,
        "    return AUTHORITIES.index(normalise_authority(value))",
        "    return (AUTHORITIES.index(value) if value in AUTHORITIES\n"
        "            else len(AUTHORITIES) - 1)",
        "tests/test_pm_brief.py::test_authority_rank_is_ordered_and_fails_closed",
    ),
    (
        "family guard deleted",
        STATE,
        GUARD,
        "    if False:",
        ("tests/test_provider_table.py"
         "::test_an_unknown_author_family_bars_nothing"),
    ),
    (
        "author_families ignores role pins",
        STATE,
        ROLE_PIN,
        BLOCK_ONLY,
        ("tests/test_provider_table.py::"
         "test_author_family_honours_a_per_role_dev_pin_over_the_block_default"),
    ),
    (
        # The half of the one-slot fix that a green suite could hide. Both
        # spellings are the same value in the proven path, so a suite that
        # only exercises that path stays green with the bug restored.
        "dispatch history filtered by the record instead of the checkout",
        STATE,
        '            and (keep_all or item.get("branch") == here)',
        '            and item.get("branch") == there',
        ("tests/test_provider_table.py::"
         "test_a_stale_record_does_not_forget_this_branch_history"),
    ),
    (
        # `here is None` has two causes and only one is evidence. Dropping
        # keep_all makes an unreadable branch discard every named-branch
        # record, which is the Critical half of Codex's round-1 review.
        "an unreadable branch discards the named-branch history",
        STATE,
        "        keep_all = here is None and in_repo is not False",
        "        keep_all = False",
        ("tests/test_provider_table.py::"
         "test_an_unreadable_branch_keeps_the_named_branch_history"),
    ),
    (
        # Ten slots keyed on the model instead of the family means one
        # provider's model churn evicts the family that wrote the diff.
        "the history bound is spent per model instead of per family",
        STATE,
        '        fam = family(entry.get("provider"), entry.get("model"))',
        "        fam = None",
        ("tests/test_provider_table.py::"
         "test_model_churn_collapses_to_one_entry_per_family"),
    ),
    (
        # Round 3, Critical. Every dispatch writing the same name is the old
        # shared-file design wearing a directory: writers overwrite each
        # other and the lost one may be the family that wrote the diff.
        "every dispatch writes the same entry file",
        STATE,
        '    base = os.path.join(directory, f"{kind}-{stamp}-'
        '{uuid.uuid4().hex[:12]}")',
        '    base = os.path.join(directory, f"{kind}-entry")',
        ("tests/test_provider_table.py::"
         "test_three_concurrent_dispatches_all_survive"),
    ),
    (
        # Round 3, Critical. One malformed file must cost one entry. Failing
        # the whole read is the single-file design's worst property -- the
        # guard falls back to the config and looks like it checked.
        "one malformed entry file discards the whole directory",
        STATE,
        "        except ValueError:\n            _note_lost(lost, name)\n"
        "            continue\n"
        "        if not isinstance(entry, dict) or not entry.get(\"kind\"):",
        "        except ValueError:\n            _note_lost(lost, name)\n"
        "            return []\n"
        "        if not isinstance(entry, dict) or not entry.get(\"kind\"):",
        ("tests/test_provider_table.py::"
         "test_a_malformed_entry_costs_one_entry_and_not_the_record"),
    ),
    (
        # Round 3. A wall-clock value inside the legacy file must not be able
        # to outrank the store, or a stepped clock evicts the dispatch that
        # just happened -- the write-time hazard, relocated to read time.
        "the legacy file can outrank the store",
        STATE,
        '    return (0 if entry.get("adopted") else 1, key)',
        "    return (0, key)",
        ("tests/test_provider_table.py::"
         "test_a_backward_clock_does_not_evict_the_dispatch_that_just"
         "_happened"),
    ),
    (
        # Round 3. A repo upgraded mid-branch has its only record in the slot
        # about to be overwritten. Losing it clears the family that wrote the
        # branch to review its own diff.
        "a pre-store record is overwritten instead of adopted",
        STATE,
        "    return _append_dispatch(root, kind, dict(slot, adopted=True))",
        "    return True",
        ("tests/test_provider_table.py::"
         "test_a_dispatch_recorded_before_the_store_existed_is_not_lost"),
    ),
    (
        # Round 3, Critical. An empty author set labelled as proven
        # provenance -- an unknown collapsing into the safe-looking value,
        # wearing the label of a check that happened.
        #
        # Same anchor as round 7's below, on purpose. Round 3's `if not
        # known` was subsumed by `unnamed` rather than deleted, so one line
        # now carries both guarantees -- and turning it off has to be caught
        # by the empty case AND the mixed one. An entry running only one of
        # them would leave the other's claim unchecked.
        "an unknown author family is reported as proven",
        STATE,
        "        unnamed = None in recorded_families",
        "        unnamed = False",
        ("tests/test_provider_table.py::"
         "test_a_proven_dispatch_with_an_unknown_family_is_not_called"
         "_proven"),
    ),
    (
        # And the teeth: `eligible` means only "not struck", so with nothing
        # struck every candidate certified a review it had no basis for.
        "an unknown author still certifies an independent review",
        CONFIG,
        '        "independentReviewer": (author_source != "unknown"\n'
        '                                and any(c["eligible"] '
        'for c in candidates)),',
        '        "independentReviewer": any(c["eligible"] for c in '
        'candidates),',
        ("tests/test_provider_table.py::"
         "test_an_unknown_author_cannot_certify_an_independent_review"),
    ),
    (
        # Skipping the backup when the name is taken destroys the newer
        # original and then reports that it was saved.
        "a second corruption is rewritten without its own backup",
        PLATFORM,
        "                if os.path.exists(candidate):\n                    continue",
        ("                if os.path.exists(candidate):\n"
         "                    saved_to = candidate\n"
         "                    break"),
        ("tests/test_platform_sync.py::"
         "test_a_second_corruption_gets_its_own_backup"),
    ),
    (
        "an empty config is adopted instead of healed",
        PLATFORM,
        "        if isinstance(parsed, dict) and parsed:",
        "        if isinstance(parsed, dict):",
        ("tests/test_platform_sync.py::"
         "test_heal_config_recreates_an_empty_object"),
    ),
    (
        # Round 4, Critical. An entry naming no author cannot BE the
        # author, so it must not displace one that can.
        "an entry with no provider still spends a slot",
        STATE,
        '        if not entry.get("provider"):',
        "        if False:",
        ("tests/test_provider_table.py::"
         "test_an_entry_with_no_provider_cannot_evict_one_that_has_one"),
    ),
    (
        # Round 5, Critical. ANY cap on families within a branch evicts the
        # one that wrote the diff, given enough later dispatches.
        "families within a branch are capped",
        STATE,
        "        seen.add(key)\n        kept.setdefault(branch, [])"
        ".append((rank, entry))",
        "        seen.add(key)\n"
        "        if len(kept.setdefault(branch, [])) < "
        "DISPATCH_HISTORY_MAX:\n"
        "            kept[branch].append((rank, entry))",
        ("tests/test_provider_table.py::"
         "test_no_number_of_later_families_evicts_the_one_that_wrote_the"
         "_diff"),
    ),
    (
        # Round 5. The cap has to fall on something and it must not fall on
        # the checkout the reviewer is standing on.
        "the branch cap can evict the branch under review",
        STATE,
        "        if here is not None and here in kept and here not in live:\n"
        "            live = live[:DISPATCH_BRANCHES_MAX - 1] + [here]",
        "        live = live",
        ("tests/test_provider_table.py::"
         "test_the_branch_cap_never_evicts_the_branch_under_review"),
    ),
    (
        # Round 5, Medium. `read_dispatch` runs at session start, so an
        # unbounded live set is unbounded startup cost.
        "the branch cap does not bound the store",
        STATE,
        "        live = ranked[:DISPATCH_BRANCHES_MAX]",
        "        live = ranked",
        ("tests/test_provider_table.py::"
         "test_the_branch_cap_bounds_the_store"),
    ),
    (
        # Round 4, Critical. A hygiene cap that can delete the record
        # under review is the cap deciding which family is remembered.
        "pruning ignores what the reader still keeps",
        STATE,
        "        if name in protected:\n            continue",
        "        if False:\n            continue",
        ("tests/test_provider_table.py::"
         "test_pruning_never_removes_an_entry_the_reader_still_keeps"),
    ),
    (
        # Round 4, Critical. Overwriting the slot before its contents are
        # in the store makes the retry read from a record that is gone.
        "the slot is overwritten whether or not the adoption landed",
        STATE,
        "    if _adopt_slot(root, kind):\n"
        "        _write_slot(root, kind, entry)",
        "    _adopt_slot(root, kind)\n"
        "    _write_slot(root, kind, entry)",
        ("tests/test_provider_table.py::"
         "test_a_failed_adoption_is_retried_on_the_next_dispatch"),
    ),
    (
        # Round 7, Critical. Capturing the unnamed family AFTER the
        # discard is the same as not capturing it: the mixed set then
        # reads as proven provenance.
        "an unnamed family beside a named one still says proven",
        STATE,
        "        unnamed = None in recorded_families",
        "        unnamed = False",
        ("tests/test_provider_table.py::"
         "test_one_unnamed_family_makes_the_whole_provenance_unproven"),
    ),
    (
        # Round 7, Critical. A dispatch the store refused, reported as
        # one it took.
        "a lost entry write is reported as a recorded dispatch",
        STATE,
        '        record["unrecorded"] = True',
        '        record["unrecorded"] = False',
        ("tests/test_provider_table.py::"
         "test_a_dispatch_the_store_refused_is_not_silent"),
    ),
    (
        # Round 7, Critical. The CLI swallowing it is the other half:
        # the dispatch path is what the caller reads.
        "the dispatch CLI exits 0 on a store that refused the entry",
        STATE,
        '        if record.get("unrecorded"):',
        "        if False:",
        ("tests/test_provider_table.py::"
         "test_the_dispatch_cli_exits_non_zero_when_nothing_was_recorded"),
    ),
    (
        # Round 8, Critical. A record that would not parse, reported as
        # a record that was never there.
        "unreadable evidence reads as absent evidence",
        STATE,
        '        return known, ("unknown" if unnamed or unread '
        'else "dispatch")',
        '        return known, ("unknown" if unnamed else "dispatch")',
        ("tests/test_provider_table.py::test_a_later_dispatch_cannot_"
         "certify_over_an_unreadable_legacy_record"),
    ),
    (
        # And the half with no store entry at all: `config` asserts that
        # nothing was recorded, which an unopenable file cannot support.
        "an unopenable record still claims nothing was recorded",
        STATE,
        '            "unknown" if unread else "config")',
        '            "config")',
        ("tests/test_provider_table.py::test_a_malformed_dispatch_file_"
         "reads_as_unknown_not_as_no_dispatch"),
    ),
    (
        # The reader has to NOTICE. Silence here makes both of the
        # above unreachable while they still read as covered.
        "a skipped entry file is not reported as lost",
        STATE,
        "    if lost:",
        "    if False:",
        ("tests/test_provider_table.py::"
         "test_a_malformed_entry_costs_one_entry_and_not_the_record"),
    ),
    (
        # Round 8, edge. An unparseable slot that may be overwritten is
        # a signal the next dispatch erases.
        "an unreadable record may be overwritten",
        STATE,
        "        return False                    # unreadable; "
        "overwriting loses the",
        "        return True                     # unreadable; "
        "overwriting loses the",
        ("tests/test_provider_table.py::"
         "test_the_next_dispatch_does_not_erase_an_unreadable_record"),
    ),
    (
        # Round 8, edge. A repo-wide, permanent condition reported
        # without the file that causes it.
        "the unreadable report does not name its file",
        STATE,
        '        record["unreadable"] = sorted(set(lost))',
        '        record["unreadable"] = True',
        ("tests/test_provider_table.py::test_a_malformed_dispatch_file_"
         "reads_as_unknown_not_as_no_dispatch"),
    ),
    (
        # Round 9, High. A reader that fails closed over a file it
        # could not read is undone by a pruner that deletes it.
        "the pruner deletes the evidence that evidence was lost",
        STATE,
        "    protected.update(lost)",
        "    protected.update([])",
        ("tests/test_provider_table.py::test_the_pruner_does_not_delete_"
         "the_evidence_that_evidence_was_lost"),
    ),
    (
        # Round 10, High. Skipping a record that names no author is
        # right; skipping it in SILENCE lets the next dispatch on the
        # branch answer `dispatch` over a record nobody could read.
        "a record naming no author is dropped in silence",
        STATE,
        '            _note_lost(lost, entry.get("_file") or '
        'DISPATCH_PATH[-1])',
        "            pass",
        ("tests/test_provider_table.py::test_a_legacy_history_entry_"
         "naming_no_author_is_not_silently_dropped"),
    ),
    (
        # Round 11, High. A `.tmp` left by a crash between the write
        # and the rename is a dispatch that may have landed. The suffix
        # filter ran before the reader learned to distrust it.
        "an interrupted write is skipped without a word",
        STATE,
        '            _note_lost(lost, name)\n            continue'
        "\n        path = os.path.join(directory, name)",
        "            continue\n        path = os.path.join(directory, name)",
        ("tests/test_provider_table.py::test_an_interrupted_write_in_"
         "the_store_is_not_an_empty_directory"),
    ),
    (
        # Round 11, High. A filter upstream of the funnel empties the
        # pipe before the funnel can report anything.
        "a mangled legacy history member is filtered out in silence",
        STATE,
        "            else:\n                # A history whose members "
        "are not records is a mangled file,",
        "            elif False:\n                # A history whose "
        "members are not records is a mangled file,",
        ("tests/test_provider_table.py::test_a_mangled_legacy_history_"
         "member_is_not_silently_dropped"),
    ),
    (
        # Round 11, High, and a regression on round 10: the legacy slot
        # was the one record shape that never reached the funnel.
        "the legacy slot is filtered before it reaches the funnel",
        STATE,
        "        if isinstance(slot, dict):",
        # Reproduces the SILENCE, not just the filter: a provider-less dict
        # slot falls through with no report, exactly as it did before, while
        # a non-dict still reaches the `else` that reports it. Mutating the
        # condition alone was vacuous -- it rerouted the slot into the new
        # `else` branch, which reports it by another road.
        '        if isinstance(slot, dict) and not slot.get("provider"):\n'
        "            pass\n"
        "        elif isinstance(slot, dict):",
        ("tests/test_provider_table.py::test_a_legacy_slot_that_names_"
         "no_author_reaches_the_funnel"),
    ),
    (
        # The non-dict half: a key present holding nothing is a record
        # that was written and lost.
        "a slot holding nothing reads as a slot never written",
        STATE,
        "    if kind in record:",
        "    if record.get(kind) is not None:",
        ("tests/test_provider_table.py::test_a_legacy_slot_holding_"
         "nothing_is_a_record_that_was_lost"),
    ),
    (
        "bogus documented role",
        LADDER_DOC,
        "| 1 | + security",
        "| 1 | + ghost-reviewer, + security",
        "tests/test_role_ladder.py",
    ),
    # --- The endpoint ledger and endpointUnscanned (BLOCK 1, BLOCK 2, findings
    # 2-11 of this round). ---------------------------------------------------
    (
        # This repo SHIPS plugin/gizmoduck/ as source; that must never read
        # as installation on its own.
        "in-repo plugin/gizmoduck/ counts as installed",
        ENDPOINTS,
        '    scopes = []\n    if root:\n        scopes.append(os.path.join('
        'root, ".claude", "settings.local.json"))',
        '    if root and os.path.isdir(os.path.join(root, "plugin", '
        '"gizmoduck")):\n        return True\n    scopes = []\n    if root:'
        '\n        scopes.append(os.path.join(root, ".claude", '
        '"settings.local.json"))',
        ("tests/test_endpoints.py::"
         "test_in_repo_source_directory_is_not_installation"),
    ),
    (
        # `"false"` (a JSON string) is truthy in Python -- only a real
        # boolean may decide this.
        "a truthy non-bool value counts as installed",
        ENDPOINTS,
        '        if not isinstance(value, bool):\n            continue\n'
        '        return value\n    return False',
        '        if value:\n            return True\n    return False',
        "tests/test_endpoints.py::test_string_false_does_not_count_as_installed",
    ),
    (
        # Project scope must win over global; reordering the scope list
        # undoes that.
        "global scope is consulted before project scope",
        ENDPOINTS,
        '    scopes = []\n    if root:\n        scopes.append(os.path.join('
        'root, ".claude", "settings.local.json"))\n        scopes.append('
        'os.path.join(root, ".claude", "settings.json"))\n    home = '
        'os.path.expanduser("~")\n    scopes.append(os.path.join(home, '
        '".claude", "settings.local.json"))\n    scopes.append(os.path.join('
        'home, ".claude", "settings.json"))',
        '    scopes = []\n    home = os.path.expanduser("~")\n    scopes.'
        'append(os.path.join(home, ".claude", "settings.local.json"))\n'
        '    scopes.append(os.path.join(home, ".claude", "settings.json"))'
        '\n    if root:\n        scopes.append(os.path.join(root, '
        '".claude", "settings.local.json"))\n        scopes.append(os.path.'
        'join(root, ".claude", "settings.json"))',
        ("tests/test_endpoints.py::"
         "test_project_explicit_false_wins_over_global_true"),
    ),
    (
        # More than one manifest anywhere below root must flip _is_monorepo;
        # `hits > 0` fires on the FIRST one instead.
        "a single manifest counts as a monorepo",
        ENDPOINTS,
        "            if hits > 1:\n                return True",
        "            if hits > 0:\n                return True",
        ("tests/test_endpoints.py::"
         "test_single_go_mod_at_root_is_not_a_monorepo"),
    ),
    (
        # scan_artifact_path must reject an id it cannot safely use in a
        # path, not merely at mint time.
        "an unsafe id is not rejected at read time",
        ENDPOINTS,
        '    record_id = record.get("id")\n    if not _valid_endpoint_id('
        'record_id):\n        return None',
        '    record_id = record.get("id")',
        ("tests/test_endpoints.py::"
         "test_scan_artifact_path_rejects_a_traversal_id"),
    ),
    (
        # declare_endpoint must refuse an unsafe caller-supplied id, not
        # only scan_artifact_path reading one back later.
        "an unsafe id is not rejected at mint time",
        ENDPOINTS,
        '    if endpoint_id is not None and not _valid_endpoint_id('
        'endpoint_id):\n        return {"error": f"refusing to declare an '
        'unsafe endpoint id: {endpoint_id!r}"}',
        "    pass",
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_rejects_an_unsafe_endpoint_id"),
    ),
    (
        # A record that already landed a scan must keep ITS OWN frozen
        # path; recomputing ignores finding 6 entirely.
        "a frozen scan-artifact path is recomputed instead of kept",
        ENDPOINTS,
        '    frozen = record.get("artifactPath")\n    if isinstance(frozen, '
        'str):\n        frozen = frozen.replace("\\\\", "/")\n    if frozen '
        'is not None:\n        return _relative_safe(root, frozen, '
        'default)\n    return default',
        "    return default",
        ("tests/test_endpoints.py::"
         "test_frozen_artifact_path_survives_a_later_monorepo_flip"),
    ),
    (
        # BLOCK 5: a hand-edited artifactPath that escapes the repo must
        # fall back to the computed default, never be trusted as-is.
        "the traversal guard on a frozen artifact path is deleted",
        ENDPOINTS,
        "    return value if inside else default",
        "    return value",
        ("tests/test_endpoints.py::"
         "test_frozen_artifact_path_traversal_falls_back_to_the_computed_"
         "default"),
    ),
    (
        # BLOCK 12: a frozen path must resolve on ANY OS, not just the one
        # that froze it -- a legacy/hand-edited native-separator value must
        # be normalised before use.
        "a frozen artifact path is not normalised to POSIX on read",
        ENDPOINTS,
        '    if isinstance(frozen, str):\n        frozen = frozen.replace('
        '"\\\\", "/")',
        "    if False:\n        frozen = frozen",
        ("tests/test_endpoints.py::"
         "test_scan_artifact_path_normalises_backslashes_in_a_frozen_path"),
    ),
    (
        # `len(records) + 1` collides the moment any record is removed from
        # the committed, hand-editable ledger.
        "declared endpoint ids are minted from record count, not a sequence",
        ENDPOINTS,
        "        else:\n            doc[\"nextSeq\"] += 1\n            "
        "new_id = f\"ep-{doc['nextSeq']:04d}\"",
        '        else:\n            new_id = f"ep-{len(records) + 1:04d}"',
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_ids_do_not_collide_after_a_deletion"),
    ),
    (
        # Write-then-rename is what makes a failed write leave the original
        # untouched; write-in-place already clobbers it before any failure
        # can be detected.
        "the ledger write is not atomic",
        ENDPOINTS,
        '        # newline="\\n": this file is JSON, not one of the `.sh` '
        'scripts the\n        # CRLF landmine names, but pinning it costs '
        'nothing and keeps every\n        # file this module writes '
        'consistent on Windows.\n        with open(tmp_path, "w", '
        'encoding="utf-8", newline="\\n") as handle:\n            json.dump'
        '(doc, handle, indent=2, sort_keys=True)\n            handle.write'
        '("\\n")\n            handle.flush()\n            os.fsync(handle.'
        'fileno())\n        os.replace(tmp_path, path)',
        '        with open(path, "w", encoding="utf-8", newline="\\n") as '
        'handle:\n            json.dump(doc, handle, indent=2, '
        'sort_keys=True)\n            handle.write("\\n")\n            '
        'handle.flush()\n            os.fsync(handle.fileno())',
        ("tests/test_endpoints.py::"
         "test_write_endpoints_leaves_the_original_intact_if_replace_fails"),
    ),
    (
        # A gate that stops running still has to be REMOVABLE -- a mutation
        # that deletes the early return must be caught, not just trusted.
        "the gizmoduck gate is removed from read_endpoints",
        ENDPOINTS,
        '    if not gizmoduck_installed(root):\n        return {"installed"'
        ': False, "unscanned": []}',
        '    if False:\n        return {"installed": False, "unscanned": []}',
        ("tests/test_endpoints.py::"
         "test_trigger_does_not_fire_when_gizmoduck_absent"),
    ),
    (
        "closed records are still counted as unscanned",
        ENDPOINTS,
        '        if record.get("status") not in ("open", "candidate"):\n'
        '            continue',
        '        if False:\n            continue',
        "tests/test_endpoints.py::test_closed_records_never_count_as_unscanned",
    ),
    (
        # Non-empty is necessary but not sufficient -- the text must
        # actually reference the endpoint it claims to cover.
        "a scan artifact for a different endpoint still confirms this one",
        ENDPOINTS,
        "    needle = _endpoint_needle(record.get(\"endpoint\"))\n    if "
        "needle is None:\n        return record.get(\"source\") != "
        '"declared"\n    return needle.lower() in text.lower()',
        "    return True",
        ("tests/test_endpoints.py::"
         "test_artifact_for_a_different_endpoint_does_not_confirm_this_one"),
    ),
    (
        # BLOCK 4: the scan marker itself -- without it, a hand-typed note
        # that merely mentions the URL passes for free.
        "the scan marker is not required to confirm a scan",
        ENDPOINTS,
        '    if not _SCAN_MARKER_RE.search(text):\n        return False',
        "    if False:\n        return False",
        "tests/test_endpoints.py::test_todo_note_does_not_confirm_a_scan",
    ),
    (
        # BLOCK 3: a declared record with no matchable needle must fail
        # CLOSED, not pass on the marker alone.
        "a declared record with no needle fails open instead of closed",
        ENDPOINTS,
        '    if needle is None:\n        return record.get("source") != '
        '"declared"',
        "    if needle is None:\n        return True",
        ("tests/test_endpoints.py::"
         "test_declared_bare_description_endpoint_fails_closed_with_no_"
         "needle"),
    ),
    (
        # BLOCK 3: the needle derivation must cover a bare hostname, not
        # only a URL or an absolute path.
        "the needle derivation does not cover a bare hostname",
        ENDPOINTS,
        '    if stripped.startswith("/") or _HOSTNAME_RE.match(stripped):\n'
        "        return stripped",
        '    if stripped.startswith("/"):\n        return stripped',
        "tests/test_endpoints.py::test_endpoint_needle_covers_a_bare_hostname",
    ),
    (
        # Finding 4's related bug: a bare "/" would match almost any
        # markdown file that contains a slash anywhere.
        "a bare slash is treated as a specific needle",
        ENDPOINTS,
        '    if stripped == "/":\n        return None',
        "    if False:\n        return None",
        "tests/test_endpoints.py::test_endpoint_needle_rejects_a_bare_slash",
    ),
    (
        # Attribution to the owning package is the whole point of the
        # mono-repo path rule; ignoring it silently falls back to root.
        "mono-repo scan artifacts ignore package attribution",
        ENDPOINTS,
        '        package_dir = _owning_package_dir(root, record.get('
        '"location"))',
        '        package_dir = ""',
        ("tests/test_endpoints.py::"
         "test_monorepo_path_rule_attributes_to_owning_package"),
    ),
    (
        # BLOCK 1: candidates are computed, never persisted as declared.
        "an ephemeral candidate is built as a declared record",
        ENDPOINTS,
        '        "id": f"cand-{digest}",\n        "endpoint": candidate.get'
        '("label") or "unidentified endpoint candidate",\n        "source":'
        ' "inferred", "status": "candidate",',
        '        "id": f"cand-{digest}",\n        "endpoint": candidate.get'
        '("label") or "unidentified endpoint candidate",\n        "source":'
        ' "declared", "status": "open",',
        ("tests/test_endpoints.py::"
         "test_read_endpoints_surfaces_an_inferred_hit_as_an_ephemeral_"
         "candidate"),
    ),
    (
        # declare_endpoint is the ONLY function allowed to write
        # source="declared", status="open" -- a status downgrade here is
        # the whole guarantee failing at its one writer.
        "declare_endpoint writes status=candidate instead of open",
        ENDPOINTS,
        '        record = {\n            "id": new_id, "endpoint": '
        'endpoint, "source": "declared",\n            "status": "open", '
        '"location": location, "ticket": ticket,\n            "createdAt": '
        'now,\n        }\n        records.append(record)',
        '        record = {\n            "id": new_id, "endpoint": '
        'endpoint, "source": "declared",\n            "status": '
        '"candidate", "location": location, "ticket": ticket,\n            '
        '"createdAt": now,\n        }\n        records.append(record)',
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_writes_an_authoritative_open_record"),
    ),
    (
        # The dedup/id key for an ephemeral candidate must include location,
        # or two different diff lines sharing a signal collide onto one id
        # and one scan artifact silently discharges both.
        "an ephemeral candidate id ignores location",
        ENDPOINTS,
        "    digest = hashlib.sha1(\n        f\"{candidate.get('signal')}:"
        "{candidate.get('location')}\".encode(\"utf-8\")\n    ).hexdigest()"
        "[:8]",
        "    digest = hashlib.sha1(\n        f\"{candidate.get('signal')}\""
        ".encode(\"utf-8\")\n    ).hexdigest()[:8]",
        ("tests/test_endpoints.py::"
         "test_ephemeral_candidate_ids_differ_by_location"),
    ),
    (
        # A location already covered by a persisted record must not ALSO
        # surface as a fresh inferred candidate under a different id.
        "a promoted location still surfaces as a fresh candidate",
        ENDPOINTS,
        '        if candidate.get("location") in covered_locations:\n'
        '            continue',
        "        if False:\n            continue",
        ("tests/test_endpoints.py::"
         "test_a_promoted_location_no_longer_surfaces_as_a_fresh_candidate"),
    ),
    (
        # Finding 9: a comment describing the shape must not itself be read
        # as the shape.
        "inference does not skip comment lines",
        ENDPOINTS,
        '        stripped = added.strip()\n        if stripped.startswith('
        '_COMMENT_PREFIXES):\n            next_line += 1\n            '
        "continue",
        "        stripped = added.strip()",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_ignores_a_commented_out_example"),
    ),
    (
        "inference does not skip a match inside someone else's string",
        ENDPOINTS,
        'if match and not _inside_quoted_string(added, match.start()):',
        "if match:",
        ("tests/test_endpoints.py::test_infer_endpoints_ignores_a_match_"
         "inside_someone_elses_string"),
    ),
    (
        # crew's own source comments on the shapes it looks for; excluding
        # it is what stops the trigger crying wolf on every session opened
        # in this repo.
        "inference no longer excludes crew's own source",
        ENDPOINTS,
        "        if current_excluded:\n            next_line += 1\n"
        "            continue",
        "        if False:\n            next_line += 1\n            continue",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_excludes_crews_own_source_even_without_a_"
         "comment"),
    ),
    (
        "inference no longer gates openapi-path to spec-shaped files",
        ENDPOINTS,
        "            if extensions and current_ext not in extensions:\n"
        "                continue",
        "            if False:\n                continue",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_gates_openapi_path_to_spec_files"),
    ),
    (
        # Finding 10: `status`, not `source`, is authoritative -- a record
        # whose fields disagree must still render as a candidate.
        "the brief splits declared vs. candidate on source, not status",
        PM_BRIEF,
        'candidates = [hit for hit in hits if hit.get("status") == '
        '"candidate"]\n    declared = [hit for hit in hits if hit.get('
        '"status") != "candidate"]',
        'candidates = [hit for hit in hits if hit.get("source") != '
        '"declared"]\n    declared = [hit for hit in hits if hit.get('
        '"source") == "declared"]',
        ("tests/test_pm_brief.py::"
         "test_endpoint_finding_keys_on_status_not_source"),
    ),
    (
        # The hard requirement behind the whole feature: a candidate must
        # say, in its own text, that it is not confirmed.
        "the candidate finding text drops its NOT confirmed wording",
        PM_BRIEF,
        '"candidates are NOT confirmed endpoints until researched"',
        '""',
        ("tests/test_pm_brief.py::"
         "test_endpoint_finding_distinguishes_declared_from_candidate"),
    ),
    (
        # Finding 7: an unsafe-id hit must still carry location.
        "an unsafe-id unscanned hit drops location",
        ENDPOINTS,
        '            "status": record.get("status"),\n            '
        '"location": record.get("location"),\n            "path": None,',
        '            "status": record.get("status"),\n            '
        '"path": None,',
        "tests/test_endpoints.py::test_unsafe_id_hit_surfaces_location_too",
    ),
    (
        # Finding 7: an ordinary unscanned hit must carry location too.
        "an unscanned hit drops location",
        ENDPOINTS,
        '        "status": record.get("status"),\n        "location": '
        'record.get("location"),\n        "path": artifact,',
        '        "status": record.get("status"),\n        "path": '
        'artifact,',
        "tests/test_endpoints.py::test_unscanned_hit_surfaces_location",
    ),
    (
        # Finding 8: a confirmed-but-never-frozen scan must be surfaced,
        # not silently indistinguishable from a properly frozen one.
        "a confirmed but never-frozen scan is not surfaced",
        ENDPOINTS,
        '        elif (record.get("source") == "declared"\n              '
        'and record.get("artifactPath") is None):',
        "        elif False:",
        "tests/test_endpoints.py::test_unfrozen_confirmed_scan_is_surfaced",
    ),
    (
        # Finding 9: a closed record's location must ALSO stay excluded
        # from fresh inference, not just an open/candidate one.
        "a closed record's location re-surfaces as a fresh candidate",
        ENDPOINTS,
        'covered_locations = {record.get("location") for record in '
        'declared}',
        'covered_locations = {record.get("location") for record in '
        'declared if record.get("status") != "closed"}',
        ("tests/test_endpoints.py::"
         "test_a_closed_records_location_does_not_surface_as_a_fresh_"
         "candidate"),
    ),
    (
        # Finding 10: a vendored/generated tree with its own manifests must
        # not itself flip a repo into monorepo classification.
        "the monorepo skip-dirs list is emptied",
        ENDPOINTS,
        '_MONOREPO_SKIP_DIRS = frozenset({\n    "node_modules", '
        '"graphify-out", "vendor", ".venv", "venv", "dist", "build",\n})',
        "_MONOREPO_SKIP_DIRS = frozenset()",
        ("tests/test_endpoints.py::"
         "test_vendored_manifests_do_not_count_toward_monorepo_detection"),
    ),
    (
        # Finding 11: re-declaring an existing id must not silently reopen
        # a record a human deliberately closed.
        "re-declaring an existing id forces status back to open",
        ENDPOINTS,
        '                    record.update(endpoint=endpoint, '
        'source="declared",\n                                  '
        "location=location, ticket=ticket,\n                                  "
        "updatedAt=now)",
        '                    record.update(endpoint=endpoint, '
        'source="declared",\n                                  '
        'status="open", location=location, ticket=ticket,\n                                  '
        "updatedAt=now)",
        ("tests/test_endpoints.py::"
         "test_redeclare_does_not_reopen_a_closed_record"),
    ),
    (
        # Finding 12: record_scan_artifact must store POSIX separators
        # regardless of the OS this runs on.
        "the frozen artifact path is stored with native separators",
        ENDPOINTS,
        '                path = path.replace("\\\\", "/")',
        "                pass",
        ("tests/test_endpoints.py::"
         "test_record_scan_artifact_stores_posix_separators"),
    ),
    (
        # BLOCK 2: declare_endpoint must hold the ledger lock across its
        # whole read-modify-write cycle, or concurrent callers lose each
        # other's records with no error raised on either side.
        "declare_endpoint no longer holds the endpoints lock",
        ENDPOINTS,
        '    """\n    path = _endpoints_path(root) + ".lock"\n    deadline'
        " = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS",
        '    """\n    return None\n    path = _endpoints_path(root) + '
        '".lock"\n    deadline = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS',
        ("tests/test_endpoints.py::"
         "test_concurrent_threads_declaring_distinct_endpoints_all_survive"),
    ),
    (
        # Nit 15: `--declare-endpoint ""` is falsy and must not silently
        # fall through to printing full state and exiting 0.
        "an empty --declare-endpoint value is not rejected",
        STATE,
        "    if args.declare_endpoint is not None:\n        # `is not "
        'None`, not truthiness (nit 15): `--declare-endpoint ""`\n        '
        "# is falsy, and a bare-truthiness check let it fall through to "
        "the\n        # unconditional `print(json.dumps(collect(root), "
        "...))` below --\n        # printing full state and exiting 0 for "
        "a call that asked to\n        # declare an endpoint and got "
        "silently ignored, the same way a\n        # missing "
        "`--location` is not silently ignored.\n        if not "
        "args.declare_endpoint:\n            print(\"--declare-endpoint "
        'needs a non-empty value",\n                  file=sys.stderr)\n'
        "            return 2",
        "    if args.declare_endpoint:",
        "tests/test_endpoints.py::test_declare_endpoint_cli_rejects_an_empty_value",
    ),
    # --- The unguarded QA read path (the security hole). `validate_providers`
    # only ever ran on WRITE, and hand-editing `.crew/config.json` was always
    # the bypass -- `resolve_role` is what actually decides who reviews, so it
    # has to refuse an illegitimate provider on its own. Three mutations,
    # each reintroducing one half of the fix. -------------------------------
    (
        # `provider_problems` had zero callers before this round. Removing
        # the one added here is the reporter going back to being a reporter
        # nobody calls -- the read-side counterpart to `validate_providers`
        # existing in name only.
        "provider_problems is no longer called from the read path",
        CONFIG,
        "    provider_problems_found = provider_problems(cfg)",
        "    provider_problems_found = []",
        ("tests/test_provider_table.py::"
         "test_model_report_surfaces_provider_problems_from_a_hand_edited_"
         "config"),
    ),
    (
        # Without this, an unrecognised `qa` provider falls through to the
        # family guard alone -- which only fires on a NAMED match, so a
        # provider outside `QA_PROVIDERS` cleared review the moment its
        # family (real or absent) differed from the author's.
        "resolve_role no longer bars an unrecognised qa provider",
        STATE,
        '    if kind == "qa" and provider not in QA_PROVIDERS:',
        "    if False:",
        ("tests/test_provider_table.py::"
         "test_an_entirely_unknown_qa_provider_is_barred"),
    ),
    (
        # The narrower half: the bar survives for a NAMED family (a pinned
        # model) but a provider left unpinned -- `family() is None` -- slips
        # back through, which is the exact "unknown reads as no conflict"
        # bug the fix exists to close.
        "an unpinned provider's family of None skips the new guard too",
        STATE,
        '    if kind == "qa" and provider not in QA_PROVIDERS:',
        '    if kind == "qa" and provider not in QA_PROVIDERS '
        'and out["family"] is not None:',
        ("tests/test_provider_table.py::"
         "test_an_unpinned_localgpu_qa_reviewer_is_still_barred"),
    ),
    (
        # `enabled: false` -- the shipped default -- is rewritten to mean
        # "apply the disabled preset". That is not a weaker version of the
        # rule; it is the OPPOSITE action against a live repo. `disable`
        # deletes branch restrictions, so a promote reading the default this
        # way would strip protections from every repo that never asked crew
        # for a gate, on a config nobody edited.
        #
        # The headline sentence only, deliberately. The key stays named, so
        # the test's FIRST assertion ("`enabled: false`" is in the section)
        # still passes and the meaning assertion is the only thing that can
        # catch this -- the vacuous-assertion trap this file's header is
        # about. The paragraph below it, which forbids exactly this reading
        # in prose, is left standing too: prose is not what an agent obeys
        # when the headline says otherwise.
        #
        # The replacement deliberately does NOT contain the phrase "apply the
        # disabled preset". That string is what the test asserts in order to
        # prove the PROHIBITION is still in the file, so a mutation carrying
        # it would keep that assertion satisfied out of its own text -- the
        # mutation propping up an assertion about the document is exactly the
        # coupling this file's header warns against.
        "enabled: false is rewritten to mean run the disable subcommand",
        PROMOTE_DOC,
        "**`enabled: false` - the shipped default - means do nothing at all.**",
        "**`enabled: false` - the shipped default - means run the `disable` "
        "subcommand.**",
        ("tests/test_promote_merge_gate.py::"
         "test_enabled_false_means_do_nothing_at_all"),
    ),
    (
        # A `--preset` flag appears on `enable`, so `merge_gate.sh` starts
        # accepting the one thing CONFIG.md §8 says it cannot. That reason is
        # the whole basis for leaving `bitbucket.mergeGate.preset` unwired,
        # and this is what makes the reason get RE-EXAMINED rather than
        # inherited the day the flag lands.
        #
        # Anchored on the `--from-export` arm and not on the `*)` fallthrough,
        # which is byte-identical in `cmd_disable` and `cmd_enable` and so is
        # not a unique anchor. The mutation still reaches the test through the
        # `enable` parametrisation; `disable` keeps rejecting it, which is the
        # honest shape -- one of the two params goes red, and one red param is
        # a red test.
        "merge_gate.sh grows the --preset flag CONFIG.md says it lacks",
        MERGE_GATE,
        '      --from-export) from_export="${2:?--from-export needs a value}"; '
        'shift 2 ;;',
        '      --from-export) from_export="${2:?--from-export needs a value}"; '
        'shift 2 ;;\n      --preset) shift 2 ;;',
        ("tests/test_promote_merge_gate.py::"
         "test_merge_gate_sh_rejects_preset_which_is_why_the_key_stays_"
         "unwired"),
    ),
    (
        # install.policy, mutation 1: the narrowing ratchet becomes ordinary
        # precedence. This is the single most realistic wrong version, because
        # precedence is what EVERY other key in crew does -- a reader who
        # noticed this key resolving differently from its neighbours would
        # "fix" it to match them. It is also the whole attack: crew reads
        # config out of cloned repositories, so under precedence a repo
        # shipping `auto` overrides a machine owner who chose `manual` and crew
        # starts running commands because of a file the user never wrote.
        # RE-ANCHORED at schema 6, not deleted. `effective_install_policy` is
        # now a thin wrapper on `effective_ratcheted`, so the line this entry
        # named no longer exists -- but the CODE was not deleted, it moved, and
        # sabotage.py's header forbids re-anchoring onto whatever line is
        # nearest, not re-anchoring onto the line the code became.
        #
        # Kept as its own entry even though the guards entry above mutates the
        # identical line, and the duplication is the point: it proves the
        # generalisation did not ORPHAN install.policy's own coverage. The two
        # entries run the same mutation against two different tests, and if the
        # install-policy test had quietly stopped exercising the ratchet, this
        # one would come back STILL GREEN while the other stayed red.
        "install.policy resolves by precedence instead of narrowing",
        GUARDS,
        "    return tiers[min(rank(repo_value), rank(global_value))]",
        "    return tiers[max(rank(repo_value), rank(global_value))]",
        ("tests/test_install_policy.py::"
         "test_two_layers_can_only_narrow_never_widen"),
    ),
    (
        # install.policy, mutation 2: the policy is consulted before the
        # table. Reordering these two reads looks like a tidy-up and changes
        # nothing for any name crew actually ships -- every existing test that
        # installs doc-builder still passes. What it changes is the case
        # nobody types by hand: at `auto`, a name crew ships no command for
        # stops being inert. That is the difference between "auto runs one of
        # three commands in crew's source" and "auto runs what it was handed".
        "install_plan consults the policy before the shipped-command table",
        GUARDS,
        "    command = INSTALLABLE.get(name)\n    if command is None:",
        "    command = INSTALLABLE.get(name)\n    if command is None and "
        "resolved != \"auto\":",
        ("tests/test_install_policy.py::"
         "test_a_name_crew_does_not_ship_is_inert_at_every_policy"),
    ),
    (
        # install.policy, mutation 3: an unrecognised value falls back to the
        # DEFAULT rather than the floor. Here those are the same string, so
        # this mutation is invisible today -- it goes wrong the moment anybody
        # changes the default, which is exactly the kind of latent break a
        # sabotage entry is for. Written against `normalise_granularity`'s
        # rule, which IS "fall back to the documented default" and is correct
        # there because no granularity is more permissive than another.
        "an unknown install policy falls back to the default, not the floor",
        GUARDS,
        "        if cleaned in INSTALL_POLICIES:\n            return cleaned\n"
        "    return INSTALL_POLICY_DEFAULT",
        "        if cleaned in INSTALL_POLICIES:\n            return cleaned\n"
        "    return INSTALL_POLICIES[-1]",
        ("tests/test_install_policy.py::"
         "test_an_unknown_policy_collapses_to_the_floor_not_the_default"),
    ),
    (
        # install.policy, mutation 4: the narrowing happens but stops being
        # ANNOUNCED. The safe behaviour survives, so nothing breaks and no
        # command runs that should not. What breaks is the user's model: they
        # set `auto`, watch crew keep asking, and have nothing telling them
        # which layer refused. `default_global_config` already states the rule
        # this violates -- a value that quietly does nothing is worse than one
        # refused out loud.
        "the layer holding install.policy down is no longer named",
        CONFIG,
        '    held = None\n    if rank(repo_value) > rank(effective):',
        '    held = None\n    if False:',
        ("tests/test_install_policy.py::"
         "test_the_narrowing_layer_is_always_named"),
    ),
    (
        # install.policy, mutation 5: the mandatory migration stops being
        # behaviour-neutral. A schema bump makes every crew repo on every
        # machine report `upgradeNeeded`, so this migration runs on machines
        # whose owners did not ask for it. Landing anything but the floor means
        # upgrading crew is what granted the capability.
        "the schema 5 migration lands install.policy above the floor",
        GUARDS,
        'INSTALL_DEFAULTS = {"policy": INSTALL_POLICY_DEFAULT}',
        'INSTALL_DEFAULTS = {"policy": "auto"}',
        ("tests/test_install_policy.py::"
         "test_the_migration_is_behaviour_neutral"),
    ),
    (
        # Restore the prefix match in read_diagrams. This is the most likely
        # wrong version because it READS as the more generous, friendlier rule:
        # "count process-bitbucket-svg as a process diagram". What it actually
        # does is let one narrow diagram discharge the obligation for the
        # overview, so the repo with only the narrow one reports nothing
        # missing -- the unknown collapsing into the safe-looking value, in the
        # signal whose whole job is to say what is undocumented.
        "a specific diagram again satisfies its general kind",
        FRESHNESS,
        "        if not any(stem == kind for stem in stems)",
        "        if not any(stem == kind or stem.startswith(kind + \"-\")\n"
        "               for stem in stems)",
        ("tests/test_verify_absent_and_diagram_kind.py::"
         "test_a_specific_process_diagram_does_not_satisfy_process"),
    ),
    (
        # Collapse the absent map back into the no-match case. The replaced row
        # is the ONLY thing separating "I could not look" from "I looked and
        # found nothing", and `.crew/*` is ignored so the absent case is what
        # every fresh clone hits. Merging the two leaves a step 0b that still
        # runs, still reports, and silently reviews less.
        "an absent verification map is no longer its own outcome",
        REVIEW_DOC,
        "| `.crew/verify.json` does not exist | `no verification map",
        "| `.crew/verify.json` is missing or matches nothing | `no specialist",
        ("tests/test_verify_absent_and_diagram_kind.py::"
         "test_review_distinguishes_absent_from_matched_nothing"),
    ),
    (
        # Drop the exit-status check on the pre-deploy verdict. The remaining
        # `[ -n "$VERDICT" ]` tests still read correctly, so the file looks
        # complete -- and any error inside the check leaves VERDICT empty,
        # which every later test reads as "no unmet preconditions". An error
        # becomes permission to deploy, silently.
        "the promote gate stops failing closed when its own check errors",
        PROMOTE_SH,
        'if [ \"$VERDICT_STATUS\" -ne 0 ]; then',
        'if [ \"$VERDICT_STATUS\" -eq 999 ]; then',
        # Pointed at the test that exercises the fail-closed path ITSELF, not
        # at the malformed-date test. The suite reported STILL GREEN -- TEST IS
        # VACUOUS against that one, and it was right: the date is now handled
        # gracefully and never reaches the exit-status check, so the mutation
        # broke nothing the test could see. The belt was being tested while the
        # braces held.
        ("tests/test_promote_gate_fails_closed.py::"
         "test_the_gate_blocks_when_its_own_check_cannot_RUN"),
    ),
    (
        # An unanswered question is let through. `normalise_answer` never
        # returns None -- it returns `""` for anything it cannot read -- so
        # `cleaned is None` is never true and an empty box falls past the
        # UNANSWERED arm into the placeholder check, where `""` is not a
        # member. The request then files with a blank rollback plan.
        #
        # Chosen over `if False:` because it is the bug somebody would
        # actually write: `normalise_answer` is documented as total, and "it
        # returns nothing for an unreadable value" is one careless step from
        # "it returns None". The placeholder arm is left INTACT, so the
        # mutation isolates one of the two refusal kinds rather than deleting
        # the whole gate -- a mutation that broke both would go red on the
        # placeholder tests too and tell you nothing about this one.
        "an unanswered change-request question is let through",
        CHANGE_PY,
        "    cleaned = normalise_answer(value)\n    if not cleaned:",
        "    cleaned = normalise_answer(value)\n    if cleaned is None:",
        ("tests/test_change_validator.py::"
         "test_an_empty_or_unreadable_box_is_unanswered"),
    ),
    (
        # `close` stops requiring the post-change validation results: it gates
        # questions 1-9 instead of 10. A change then closes with nothing
        # proving it worked, and the record says it was fine.
        #
        # Anchored so that every EARLIER assertion in the target test still
        # holds -- `CLOSING_QUESTIONS == (10,)` is untouched, and the three
        # refusal assertions still refuse, because a close payload carries only
        # question 10 and so fails 1-9 as well. The only assertion this can
        # trip is the one that says a COMPLETE close passes. That is the
        # discipline this file's header asks for after the
        # `docs.reportTheme` case: a mutation for a multi-assertion test has to
        # be the one that leaves the earlier lines satisfied, or "it went red"
        # is not evidence about the assertion the label names.
        "`/crew:change close` no longer requires the validation results",
        CHANGE_PY,
        "    return validate(answers, CLOSING_QUESTIONS)",
        "    return validate(answers, FILING_QUESTIONS)",
        ("tests/test_change_validator.py::"
         "test_close_requires_ten_and_gates_nothing_else"),
    ),
    (
        # `change.requireForProduction` is satisfied from this session's memory
        # instead of from the backend. The config key still ratchets, the gate
        # still "runs", and a change a board rejected an hour ago still clears
        # a production promotion -- because what was read is a recollection of
        # an earlier look rather than the desk's current answer.
        #
        # A prose mutation, and it has to be: no hook reads this key, which
        # `promote.md`'s own "What is enforced, and what is not" section says
        # by name. The prose IS the mechanism here, so the prose is what there
        # is to sabotage.
        #
        # Earlier assertions in the target test are untouched -- the key, the
        # word APPROVED and "for THIS sha" all stay -- so only the
        # read-from-the-backend claim can trip.
        "promote reads the change state from memory instead of the backend",
        PROMOTE_DOC,
        "**Read the state from the backend, every time** - never from the "
        "local cache,",
        "**The state you read earlier in this session is fine** - the local "
        "cache is authoritative,",
        ("tests/test_change_command.py::"
         "test_promote_gate_one_requires_an_approved_change_for_this_sha"),
    ),
    (
        # A WRAPPER is read THROUGH, not treated as the thing that ran. This
        # inversion is the shape the bug had: `env` was a name on the read
        # list, so `env touch /tmp/x` was a read because `env` is. Every
        # command crew positively recognises still classifies the same way, so
        # only the wrapped ones change answer -- which is `read` becoming
        # `full` for anything anybody thinks to prefix.
        "a wrapper counts as the command, so `env <write>` is a read",
        GUARDS,
        "        if _head_name(tokens[0]) not in PROD_WRAPPERS:\n"
        "            return tokens",
        "        if _head_name(tokens[0]) in PROD_WRAPPERS:\n"
        "            return []",
        "tests/test_guards.py::test_a_subcommands_verb_decides_it_not_just_the_object",
    ),
    (
        # The original code, restored: the object is checked and the action
        # that decides is not. `ip link show` and `ip link set eth0 down` are
        # then the same answer, and the second one takes the interface down.
        "only `ip`'s object is checked, so `ip link set` is a read",
        GUARDS,
        "        actions = PROD_SUBCOMMAND_ACTIONS.get(head)\n"
        "        if (actions is not None and len(rest) > 1\n"
        "                and rest[1].lower() not in actions):\n"
        "            return \"write\"\n"
        "        return \"read\"",
        "        return \"read\"",
        "tests/test_guards.py::test_a_subcommands_verb_decides_it_not_just_the_object",
    ),
    (
        # Back to the first payload only. `-c 'select 1' -c '<write>'` reads
        # as a SELECT, and the statement crew inspects is the one an author
        # would put first.
        "only the first SQL payload is inspected",
        GUARDS,
        "        if all(_classify_sql(payload) == \"read\" "
        "for payload in payloads):\n"
        "            return \"read\"\n"
        "        return \"write\"",
        "        return _classify_sql(payloads[0])",
        "tests/test_guards.py::test_every_sql_payload_is_classified_not_only_the_first",
    ),
    (
        # The state the whole framing fix exists for. Without the rejection a
        # `run` entry carrying a newline is half a command: the matcher's
        # record boundary moves, and the rest of the rule is reported as an
        # unmapped PATH rather than run. Measured on a fixture whose rule was
        # ["echo first\necho second", "exit 1"]: with "unmapped": "warn" the
        # gate exited 0 while the rule contained `exit 1`.
        #
        # The paired test asserts the MESSAGE, not the status, and that is the
        # point of this entry. Under this mutation the fixture still exits 2 --
        # the \x1d separator keeps the entry whole and the read loop then evals
        # `exit 1` for real -- so a test pinned to the exit code alone would be
        # green with the defect restored, which is the vacuous shape this
        # file's own header is about.
        "the Stop gate stops rejecting a `run` entry it cannot represent",
        VERIFY_SH,
        'for ri, rule in enumerate(cfg.get("rules", []) or []):\n'
        "    if isinstance(rule, dict):\n"
        '        reject_unrepresentable(f"rules[{ri}].run", rule.get("run"))\n'
        'reject_unrepresentable("always", cfg.get("always"))\n'
        'reject_unrepresentable("default", cfg.get("default"))',
        "pass",
        ("tests/test_verify_gate_rule_framing.py::"
         "test_a_multiline_run_entry_is_refused_by_name"),
    ),
    (
        # The belt, restored to the newline it used to be. NO INPUT CAN REACH
        # IT once the rejection above is in place, which is exactly why the
        # test it is paired with reads the source rather than driving the
        # script: every behavioural case in that file stays green under this
        # mutation, because no command is allowed to contain a newline any
        # more. Written down rather than dropped -- the separator is what
        # holds if the rejection is ever narrowed, and a defence with no
        # mutation is a defence nobody notices going.
        # Grew from 5 fields to 6 in crew 0.19.93 (record 6, the JSON EXTRAS
        # blob the per-rule record and env pinning read) -- re-anchored to
        # the current statement rather than the pre-0.19.93 one so this
        # mutation keeps testing the CURRENT writer, not a shape the file no
        # longer has.
        "the matcher's record separator goes back to a newline",
        VERIFY_SH,
        'sys.stdout.write("\\x1e".join(cmds) + "\\x1d" + "\\x1e"'
        '.join(unmatched) + "\\x1d" + "\\x1e".join(notices)\n   '
        '              + "\\x1d" + str(acute_count)\n   '
        '              + "\\x1d" + str(int(max_cost))\n   '
        '              + "\\x1d" + extras + "\\n")',
        'print("\\x1e".join(cmds))\nprint("\\x1e".join(unmatched'
        '))\nprint("\\x1e".join(notices))\nprint(str(acute_count'
        '))\nprint(str(int(max_cost)))\nprint(extras)',
        ("tests/test_verify_gate_rule_framing.py::"
         "test_the_two_halves_of_the_framing_contract_agree"),
    ),
    (
        # "I could not create a lock" collapsing back into "someone holds the
        # lock" -- this repo's named recurring bug, in the one place where the
        # consequence is the entire gate silently off. `mkdir` fails for
        # ENOTDIR and EACCES exactly as it fails for EEXIST, and with `.crew`
        # present as a file the gate exited 0 in 0.65s on every turn, for
        # ever, with nothing on stderr.
        "a lock that could not be created reads as a lock someone holds",
        VERIFY_SH,
        '    echo "VERIFY GATE: could not create the lock at $LOCK and '
        "nothing is holding it (is .crew a file, read-only, or is the lock "
        "path not a directory?). No other gate can be waited for, so the "
        'checks are running WITHOUT the lock - at worst they run twice this '
        'turn." >&2\n'
        "    UNLOCKED=1\n"
        "  else\n",
        "    exit 0\n  else\n",
        ("tests/test_verify_gate_lock_sh.py::"
         "test_a_lock_path_that_is_a_file_does_not_stand_the_gate_down"),
    ),
    (
        # The matched pair's half. verify-gate.ps1 never had the framing bug
        # -- it reads objects, not text -- so this is not a duplicate of the
        # first entry: it is the claim that the PAIR agrees. With the refusal
        # gone the same map blocks the turn on bash and passes it here.
        #
        # The fixture still exits 2 under this mutation, because `bash -c`
        # runs both halves and the second rule is `exit 1`. The status
        # assertion therefore still passes and only the message assertion
        # catches it, which is the shape this file's header asks for.
        "the PowerShell gate stops rejecting a `run` entry it cannot "
        "represent",
        VERIFY_PS1,
        "if ($null -ne $bad) {\n  [Console]::Error.WriteLine($bad)",
        "if ($false) {\n  [Console]::Error.WriteLine($bad)",
        ("tests/test_verify_gate_rule_framing.py::"
         "test_the_powershell_gate_refuses_the_same_map_by_name"),
    ),
    (
        # Setup's half. resolve-tools.sh writes the table a user pastes back
        # into verify.json, and a multi-line entry tokenised into junk came
        # out as MISSING TOOLS -- names nobody wrote, beside real ones. The
        # python still exits 4 under this mutation; the shell just stops
        # acting on it, which is how a fail-closed check usually dies.
        "resolve-tools ignores the refusal and prints a table anyway",
        RESOLVE_TOOLS,
        '    if [ "$PY_STATUS" -eq 4 ]; then',
        "    if false; then",
        ("tests/test_verify_gate_rule_framing.py::"
         "test_resolve_tools_refuses_the_same_map_by_name"),
    ),
    (
        # The third reader. map-audit.sh's token scan reads half a multi-line
        # entry as a filename and files it under "rules pointing at files that
        # do not exist", so the reader goes hunting a file nobody named.
        "map-audit ignores the refusal and prints a drift report anyway",
        MAP_AUDIT,
        'if [ "$STATUS" -eq 4 ]; then',
        "if false; then",
        ("tests/test_verify_gate_rule_framing.py::"
         "test_map_audit_refuses_the_same_map_by_name"),
    ),
    (
        # The digest stops covering the INDEX. `git ls-files -s` is still
        # called and the mode is still hashed, so every earlier fingerprint
        # case -- including the staged chmod one -- stays green; only the
        # staged CONTENTS go uncovered. That narrowness is the point: the mode
        # and the blob id arrive in the same record, and reverting to the
        # mode alone is exactly the state the gate shipped in, where staging
        # failing contents behind a passing working tree made Stop exit 0 with
        # SKIPPED while --all exited 2.
        "the fingerprint goes back to hashing the mode but not the staged "
        "contents",
        FINGERPRINT,
        'entries.setdefault(path, []).append(" ".join(fields[:3]))',
        'entries.setdefault(path, []).append(" ".join(fields[:1]))',
        ("tests/test_verify_gate_fingerprint.py::"
         "test_staged_contents_move_the_digest"),
    ),
    (
        # The same defect through the GATE rather than the digest, and the
        # reason both entries are here: the one above proves the hash moved,
        # this one proves the skip did. A digest that changes while the gate
        # skips anyway would leave the first green and this red.
        "the gate skips a tree whose staged contents fail",
        FINGERPRINT,
        'entries.setdefault(path, []).append(" ".join(fields[:3]))',
        'entries.setdefault(path, []).append(" ".join(fields[:1]))',
        ("tests/test_verify_gate_fingerprint.py::"
         "test_a_failing_tree_is_never_skipped_whatever_moved"),
    ),
    (
        # Whitespace stripped back off each path, which hashed a DIFFERENT
        # file: a rule on " leading.txt" was verified against the digest of
        # "leading.txt", which does not exist and hashes as the absent
        # constant, so every later edit kept the passing fingerprint.
        #
        # Mutating main() and not fingerprint() deliberately. main() is the
        # seam both flavours pipe into, and it is the WRITER of the path list
        # -- a mutation of the reader would leave the parsing defect untested,
        # which is how this one survived review in the first place.
        "the fingerprint trims whitespace off the paths it is handed",
        FINGERPRINT,
        "changed = [l for l in sys.stdin.read().split(chr(10)) if l.strip()]",
        "changed = [l.strip() for l in sys.stdin.read().split(chr(10)) "
        "if l.strip()]",
        ("tests/test_verify_gate_fingerprint.py::"
         "test_the_path_list_is_not_trimmed"),
    ),
    (
        # The budget's UNIT, in the bash flavour. `seconds` prices the rule
        # and is charged once; this mutation charges it per command again, so
        # a 40s rule with two commands costs 80 under a 60s budget and is
        # split in half.
        #
        # Every stop-budget case that predates the fix stays green under it:
        # each of their rules has ONE command, so the two readings agree. That
        # is how the unit went unstated for a release, and it is why the
        # paired test maps a rule with two.
        #
        # The first attempt at this mutation only inflated `spent` AFTER the
        # decision, which changes nothing on a one-rule map -- it came back
        # green and is recorded here because a mutation that does not
        # reproduce the defect is a coverage claim nobody has earned. What
        # follows is the per-command selection verbatim as it shipped.
        # RE-ANCHORED in 0.19.95: the selection loop grew a mandatory
        # branch, so the old anchor stopped matching. Re-anchored rather than
        # dropped -- the defect it proves is still live, and an anchor that
        # silently stops matching is how this suite would stop testing
        # anything. (Caught by the whole-file anchor check, which is the only
        # reason it was not.)
        "the Stop budget charges each command the whole rule's cost again",
        VERIFY_SH,
        "        elif spent + rule_secs[ri] <= budget:\n"
        "            # WHOLE, in the rule's own `run` order. Half a rule is "
        "not a\n"
        "            # cheaper rule; it is a rule nobody can say ran.\n"
        "            keep.extend(fresh)\n"
        "            spent += rule_secs[ri]\n"
        "        else:\n"
        "            for c in fresh:\n"
        "                if c not in deferred: deferred.append(c)\n",
        "        else:\n"
        "            for c in fresh:\n"
        "                if spent + cost[c] <= budget:\n"
        "                    keep.append(c)\n"
        "                    spent += cost[c]\n"
        "                elif c not in deferred:\n"
        "                    deferred.append(c)\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_rule_that_fits_is_not_split_across_its_commands"),
    ),
    (
        # The matched pair's half, and not a duplicate. The arithmetic lives
        # in a python heredoc on one side and in PowerShell on the other, so a
        # fix applied to one flavour reads as done while the other still
        # splits the rule -- this plugin has shipped exactly that shape, and a
        # round of this branch left the bash half wrapped in `if false` with
        # every test still green.
        # RE-ANCHORED in 0.19.95, with its bash twin and for the same
        # reason. RE-ANCHORED AGAIN in 0.19.93 (the per-rule record): the
        # `else` branch grew a chronic-vs-acute classification block, so the
        # closing brace this find string ends on moved further down.
        # RE-ANCHORED AGAIN in round 3 (identity dedup case-sensitivity,
        # Codex BLOCK verify-gate.ps1:901): `-notcontains` on $deferred
        # became `-cnotcontains` everywhere in the identity/dedup path, this
        # line included, so PowerShell's default CASE-INSENSITIVE string
        # comparison could no longer collapse two commands whose identities
        # differ only in case (e.g. ENV=dev vs ENV=DEV) into one.
        "the PowerShell Stop budget charges each command the rule's cost",
        VERIFY_PS1,
        "    } elseif (($spent + $ruleSecs[$ri]) -le $budget) {\n"
        "      # WHOLE, in the rule's own `run` order. Half a rule is not a "
        "cheaper\n"
        "      # rule; it is a rule nobody can say ran.\n"
        "      foreach ($c in $fresh) { [void]$keep.Add($c) }\n"
        "      $spent += $ruleSecs[$ri]\n"
        "    } else {\n"
        "      foreach ($c in $fresh) { if ($deferred -cnotcontains $c) { "
        "[void]$deferred.Add($c) } }\n"
        "      # CHRONIC vs ACUTE -- the twin split in verify-gate.sh. A "
        "rule whose\n"
        "      # own cost exceeds the whole budget can never fit regardless "
        "of\n"
        "      # ordering (chronic); one that would fit alone but lost to "
        "this\n"
        "      # turn's contention is acute and still blocks the baseline, "
        "same as\n"
        "      # before this feature existed.\n"
        "      if (-not $chronicRules.Contains($ri) -and -not "
        "$acuteRules.Contains($ri)) {\n"
        "        if ($ruleSecs[$ri] -gt $budget) { "
        "[void]$chronicRules.Add($ri) }\n"
        "        else { [void]$acuteRules.Add($ri) }\n"
        "      }\n"
        "    }\n",
        "    } else {\n"
        "      foreach ($c in $fresh) {\n"
        "        if (($spent + $cost[$c]) -le $budget) { [void]$keep.Add($c); "
        "$spent += $cost[$c] }\n"
        "        elseif ($deferred -cnotcontains $c) { "
        "[void]$deferred.Add($c) }\n      }\n    }\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_both_flavours_charge_the_rule_once"),
    ),
    (
        # The deadline read goes back to DELETING what it cannot parse instead
        # of refusing it. `tr -dc "0-9"` turns -9999999999 into 9999999999 --
        # a deadline in the year 2286 -- so the gate backed off announcing
        # "may run for another 8210194761s" and verified nothing for ever.
        # This repository's recurring defect inverted: a malformed value
        # REPAIRED into a permissive one rather than an unknown collapsing
        # into one.
        "an unparseable deadline is coerced into a number again",
        VERIFY_SH,
        "      HOLD_DEADLINE=$(tr -d \'[:space:]\' < \"$LOCK/deadline\" "
        "2>/dev/null)\n"
        "      case \"$HOLD_DEADLINE\" in\n"
        "        \'\'|*[!0-9]*) HOLD_DEADLINE=\"\" ;;\n"
        "      esac\n",
        "      HOLD_DEADLINE=$(cat \"$LOCK/deadline\" 2>/dev/null | "
        "tr -dc \"0-9\")\n",
        ("tests/test_verify_gate_lock_window.py::"
         "test_an_unparseable_deadline_is_not_a_held_lock"),
    ),
    (
        # The PowerShell half, and NOT the same defect: this flavour never
        # coerced a sign, it silently overflowed. `[int]` on a deadline past
        # Int32 max throws, the catch produces 0, and the lock reads as
        # unheld -- measured, on an aged token with a deadline of 9999999999
        # bash backed off while PowerShell RAN. Every legitimate deadline
        # crosses that boundary on 2038-01-19, so the pair would have
        # disagreed about every live lock from that date.
        "the PowerShell deadline read overflows Int32 again",
        VERIFY_PS1,
        "      $holdDeadline = 0\n"
        "      try {\n"
        "        $raw = (Get-Content -Raw -ErrorAction Stop (Join-Path $lock "
        "\'deadline\')).Trim()\n"
        "        if ($raw -match \'^[0-9]+$\') { $holdDeadline = [long]$raw }"
        "\n      } catch { $holdDeadline = 0 }\n",
        "      $holdDeadline = try { [int]((Get-Content -Raw -ErrorAction "
        "Stop (Join-Path $lock \'deadline\')).Trim()) } catch { 0 }\n",
        ("tests/test_verify_gate_lock_window.py::"
         "test_both_flavours_read_the_same_deadline_the_same_way"),
    ),
    (
        # DEADLINE PUBLICATION REMOVED ENTIRELY, bash side. This is the
        # mutation the cross-flavour case could not be made to fail under
        # before it was rewritten: it fabricated the lock, the token and the
        # deadline itself, and the token it planted was fresh enough that the
        # AGE WINDOW forced the back-off it asserted -- so the test passed
        # with the whole feature deleted from both gates. It now runs a real
        # holder of the writer flavour and asserts the token is already past
        # the TTL, which is what makes the back-off attributable to the
        # deadline.
        "the bash gate stops publishing a deadline at all",
        VERIFY_SH,
        "lock_extend() {\n"
        "  [ \"$UNLOCKED\" -eq 0 ] || return 0\n"
        "  [ \"$(cat \"$LOCK/token\" 2>/dev/null)\" = "
        "\"${LOCK_TOKEN:-}\" ] || return 0\n"
        "  printf \'%s\\n\' \"$(( $(date +%s) + $(lock_window) ))\" > "
        "\"$LOCK/deadline\" 2>/dev/null || true\n"
        "}\n",
        "lock_extend() {\n  return 0\n}\n",
        ("tests/test_verify_gate_lock_window.py::"
         "test_each_flavour_honours_a_deadline_the_other_published"),
    ),
    (
        # The matched pair's half: deadline publication removed on the
        # PowerShell side. Separate entry because the cross-flavour case runs
        # BOTH directions, and one flavour still publishing would leave the
        # other direction green -- which is exactly how a one-flavour fix
        # reads as done in this plugin.
        "the PowerShell gate stops publishing a deadline at all",
        VERIFY_PS1,
        "      $deadline = $epoch + (Get-CrewLockWindow -Ttl $Ttl -MaxCost "
        "$MaxCost)\n      Set-Content -Path (Join-Path $LockPath "
        "\'deadline\') -Value $deadline -Encoding ascii -ErrorAction Stop\n",
        "      $deadline = $epoch + (Get-CrewLockWindow -Ttl $Ttl -MaxCost "
        "$MaxCost)\n      $null = $deadline\n",
        ("tests/test_verify_gate_lock_window.py::"
         "test_each_flavour_honours_a_deadline_the_other_published"),
    ),
    (
        # The TTL seam read as octal again. `08` is all digits, so it passes
        # the filter and then dies inside `$(( ))` -- measured, two
        # `value too great for base` lines and NO deadline published, while
        # the gate still exited 0. A test seam that silently disables the
        # mechanism it exists to exercise.
        "a zero-prefixed TTL is read as octal again",
        VERIFY_SH,
        "  *) ENV_TTL=$((10#$CREW_VERIFY_LOCK_TTL))",
        "  *) ENV_TTL=$CREW_VERIFY_LOCK_TTL",
        ("tests/test_verify_gate_lock_window.py::"
         "test_a_zero_prefixed_ttl_is_decimal_and_still_publishes_a_deadline"),
    ),
    (
        # Deduplication weakens the obligation again: the commands that carry
        # an unconditional obligation stop being scheduled ahead of the
        # budget, so a priced rule naming the same command can defer them.
        # Measured before the fix in BOTH flavours -- `"always"` beside a 90s
        # rule naming the same command deferred a FAILING mandatory check and
        # the gate exited 0.
        # RE-ANCHORED in 0.19.95: the obligation moved from the command
        # to the RULE that carries it, so `forced` no longer exists. The
        # mutation now drops the "any command of this rule is unconditional"
        # half of rule_is_mandatory, which is the same defect at the new seam.
        "an `always` command can be deferred by a priced rule naming it",
        VERIFY_SH,
        "    def rule_is_mandatory(ri):\n"
        "        return (ri not in rule_secs\n"
        "                or any(c in mandatory for c in rule_cmds[ri]))\n",
        "    def rule_is_mandatory(ri):\n"
        "        return ri not in rule_secs\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_an_always_command_is_not_deferred_by_a_priced_rule"),
    ),
    (
        # The matched pair's half. The budget arithmetic is a python heredoc
        # on one side and PowerShell on the other, and the report confirmed
        # the defect was present in both -- so one flavour fixed reads as
        # done while the other still defers the mandatory check.
        # RE-ANCHORED in 0.19.95 with its bash twin.
        "the PowerShell budget lets a priced rule defer an `always` command",
        VERIFY_PS1,
        "    foreach ($c in $ruleCmds[$ri]) { if ($mandatory.ContainsKey($c))"
        " { $isMust = $true } }\n",
        "    foreach ($c in $ruleCmds[$ri]) { }\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_an_always_command_is_not_deferred_by_a_priced_rule"),
    ),
    (
        # The FINER half, and a separate entry because `always` still works
        # under it: only the "unconditional-until-priced" level is deleted, so
        # a command named by an unpriced rule AND a priced one goes back to
        # being deferrable. That variant was in no report -- it came out of
        # writing the rule as a property over obligation levels instead of as
        # "exempt always", which is the whole argument for doing it that way.
        "a rule with no `seconds` stops making its commands unconditional",
        VERIFY_SH,
        "for ri in rule_order:\n    if ri not in rule_secs:\n"
        "        mandatory.update(rule_cmds[ri])\n",
        "for ri in rule_order:\n    pass\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_an_unpriced_rule_makes_its_commands_unconditional"),
    ),
    (
        # Its PowerShell twin.
        "the PowerShell gate stops making an unpriced rule unconditional",
        VERIFY_PS1,
        "foreach ($ri in $ruleOrder) {\n"
        "  if (-not $ruleSecs.ContainsKey($ri)) {\n"
        "    foreach ($c in $ruleCmds[$ri]) { $mandatory[$c] = $true }\n"
        "  }\n}\n",
        "foreach ($ri in $ruleOrder) { }\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_an_unpriced_rule_makes_its_commands_unconditional"),
    ),
    (
        # A gitlink goes back to being read as a file. `open()` on a directory
        # raises, so the submodule hashes to the same "absent" constant a
        # DELETED file gets -- which is why nothing about it looked wrong. A
        # check reading `sub/a.txt` was then skippable by editing
        # `sub/a.txt`, whose gitlink sha does not move.
        "a submodule hashes as absent again",
        FINGERPRINT,
        "        if any(e.startswith(\"160000\") for e in entry.split(\",\")):"
        "\n            digest.update(_submodule_digest(full, _depth)"
        ".encode(\"ascii\"))\n        else:\n            digest.update("
        "_file_digest(full).encode(\"ascii\"))\n",
        "        digest.update(_file_digest(full).encode(\"ascii\"))\n",
        ("tests/test_verify_gate_fingerprint.py::"
         "test_a_dirty_submodule_moves_the_digest"),
    ),
    (
        # The same mutation through the GATE rather than the digest, for the
        # reason the staged-contents pair gives: one proves the hash moved,
        # this proves the SKIP did. It is the submodule row of the invariant
        # table, so it also asserts --all and Stop agree on that tree.
        "the gate skips a tree whose submodule contents fail",
        FINGERPRINT,
        "        if any(e.startswith(\"160000\") for e in entry.split(\",\")):"
        "\n            digest.update(_submodule_digest(full, _depth)"
        ".encode(\"ascii\"))\n        else:\n            digest.update("
        "_file_digest(full).encode(\"ascii\"))\n",
        "        digest.update(_file_digest(full).encode(\"ascii\"))\n",
        ("tests/test_verify_gate_fingerprint.py::"
         "test_a_failing_tree_is_never_skipped_whatever_moved"),
    ),
    (
        # 0.19.94's hoist-and-charge, restored verbatim: each mandatory
        # COMMAND is pulled to the front of the list and charged there, and
        # its rule is then charged again for the rest. Measured -- a 40s rule
        # running [A, B] with A in `always` cost 40 + 40 against a 60s budget
        # and DEFERRED B, which is the per-command double-charge 0.19.92
        # removed, reintroduced from the other end.
        "a mandatory command is charged on its own and again with its rule",
        VERIFY_SH,
        "    spent, keep, overrun = 0, [], []\n",
        "    spent, keep, overrun = 0, [], []\n"
        "    for _c in [c for c in cmds if c in cost and c in mandatory]:\n"
        "        keep.append(_c)\n"
        "        spent += cost[_c]\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_mandatory_rule_is_charged_once_against_the_rest_of_the_budget"),
    ),
    (
        # The ORDER half ALONE -- the hoist without the charge. A separate
        # entry because it is the half that fails quietly: the charging case
        # above stays GREEN under it, so a suite carrying only that mutation
        # would report the ordering defect as covered while nothing tested
        # it. `run: [prepare, check]` states a dependency, and a hoisted
        # `check` fails for a reason that is not the user's.
        "a mandatory command is hoisted out of its rule's `run` order",
        VERIFY_SH,
        "    spent, keep, overrun = 0, [], []\n",
        "    spent, keep, overrun = 0, "
        "[c for c in cmds if c in cost and c in mandatory], []\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_mandatory_command_keeps_its_place_inside_its_rule"),
    ),
    (
        # The PowerShell half of the charge defect. Separate, because the
        # arithmetic is a python heredoc on one side and PowerShell on the
        # other and the report confirmed BOTH flavours carried it.
        "the PowerShell gate charges a mandatory command twice",
        VERIFY_PS1,
        "  $overrun = [System.Collections.ArrayList]@()\n",
        "  $overrun = [System.Collections.ArrayList]@()\n"
        "  foreach ($c in @($cmds | Where-Object { $cost.ContainsKey($_) -and "
        "$mandatory.ContainsKey($_) })) { [void]$keep.Add($c); "
        "$spent += $cost[$c] }\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_mandatory_rule_is_charged_once_against_the_rest_of_the_budget"),
    ),
    (
        # And the PowerShell half of the ORDER defect, hoist without charge.
        "the PowerShell gate hoists a mandatory command out of its rule",
        VERIFY_PS1,
        "  $overrun = [System.Collections.ArrayList]@()\n",
        "  $overrun = [System.Collections.ArrayList]@()\n"
        "  foreach ($c in @($cmds | Where-Object { $cost.ContainsKey($_) -and "
        "$mandatory.ContainsKey($_) })) { [void]$keep.Add($c) }\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_mandatory_command_keeps_its_place_inside_its_rule"),
    ),
    (
        # The blanket ban comes back onto developer.md while every brief
        # still says "commit on your branch" -- the exact contradiction
        # T-0003 closed. The heading AND the narrowed sentence go together,
        # since a real re-widening would rewrite both.
        "the blanket commit ban returns to developer.md",
        DEVELOPER_MD,
        "- **Commit anywhere but the ticket's own branch, or `git stash` at "
        "all.** The\n  developer may commit on the ticket's own branch and "
        "nowhere else — never a\n  shared branch, never `git stash`. That "
        "developer is you,",
        "- **Never `git commit`, `git stash`, or otherwise move work out of "
        "the working\n  tree.** The developer does not commit. That "
        "developer is you,",
        ("tests/test_scope_discipline.py::"
         "test_developer_commits_only_on_the_tickets_own_branch"),
    ),
    (
        # Only the LIMITS drift, in one file: the permission stays, so the
        # single-file rule test above is still satisfied, and only the
        # three-way agreement test can catch that developer.md now says less
        # than work.md and pm.md.
        "developer.md drops the stash half of the limits the briefs keep",
        DEVELOPER_MD,
        "never a\n  shared branch, never `git stash`. That developer is you,",
        "never a\n  shared branch. That developer is you,",
        ("tests/test_scope_discipline.py::"
         "test_every_file_that_briefs_a_developer_states_the_same_commit_rule"),
    ),
    (
        # work.md stops recording where the ticket starts. Everything else
        # still reads fine -- the evidence command still names scope_base.py
        # -- so every run falls back to the merge-base and the record that
        # makes the narrowed rule safe is never written.
        "work.md no longer records the ticket's start",
        WORK_MD,
        "   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . "
        "--record $1\n",
        "   true\n",
        ("tests/test_scope_discipline.py::"
         "test_work_records_the_ticket_base_before_printing_the_evidence"),
    ),
    (
        # The record advances on every call. A /crew:work re-run after a
        # /clear then moves the base to the current HEAD and every commit
        # before it leaves the evidence -- the original defect, one file
        # over.
        "the scope base moves on a re-record for the same ticket",
        SCOPE_BASE,
        "    if entry:\n"
        "        # NEVER overwritten, whatever state the commit is in -- and never\n",
        "    if entry and False:\n"
        "        # NEVER overwritten, whatever state the commit is in -- and never\n",
        ("tests/test_scope_base.py::"
         "test_recording_the_same_ticket_again_does_not_move_the_base"),
    ),
    (
        # Codex round 1, finding 1: a record whose commit is missing from
        # this clone is re-recorded at HEAD. The same-ticket re-record case
        # above stays green (its commit exists), so only the missing-commit
        # case can catch it.
        "a record whose commit is missing is silently replaced with HEAD",
        SCOPE_BASE,
        "    if entry:\n"
        "        # NEVER overwritten, whatever state the commit is in -- and never\n",
        '    if entry and _is_commit(root, entry["base"]):\n'
        "        # NEVER overwritten, whatever state the commit is in -- and never\n",
        ("tests/test_scope_base.py::"
         "test_a_record_whose_commit_is_missing_is_kept_not_replaced"),
    ),
    (
        # Codex round 1, finding 2: the mapping is rebuilt from scratch on
        # every write, so starting T-2 drops T-1's entry -- the single-value
        # record in a mapping's clothes.
        "starting a second ticket loses the first ticket's base",
        SCOPE_BASE,
        "    updated = dict(rec)\n",
        "    updated = {}\n",
        ("tests/test_scope_base.py::"
         "test_a_second_ticket_does_not_lose_the_firsts_base"),
    ),
    (
        # Codex round 2, finding 1: round 1's exemption comes back in its
        # widest form -- any prior entry at all suppresses the fallback, so
        # T-1 recorded on main makes T-2's start resolve to HEAD, unlabelled.
        "any earlier ticket's entry suppresses the merge-base fallback",
        SCOPE_BASE,
        "    if merge_base and merge_base != head:\n",
        "    if merge_base and merge_base != head and not rec:\n",
        ("tests/test_scope_base.py::"
         "test_another_tickets_entry_never_stands_in_for_this_tickets_start"),
    ),
    (
        # Codex round 2, finding 2: a fallback entry is re-read as a known
        # start. The base is still right, so every base assertion stays
        # green; only the provenance case sees "kept" without its caveat.
        "a re-record upgrades a fallback entry to a known start",
        SCOPE_BASE,
        '        if _is_fallback_entry(entry):\n'
        '            return entry["base"], "kept-fallback"\n',
        '        if _is_fallback_entry(entry):\n'
        '            return entry["base"], "kept"\n',
        ("tests/test_scope_base.py::"
         "test_re_recording_a_fallback_entry_keeps_saying_fallback"),
    ),
    (
        # Codex round 1, finding 3: the remote default is skipped, so a clone
        # with no local `main` falls through to HEAD -- the narrowest answer.
        # The fixture deletes origin/HEAD so only this candidate can answer.
        "the fallback never tries origin/main",
        SCOPE_BASE,
        '    candidates = [sym, "origin/main", "main"]\n',
        '    candidates = [sym, "main"]\n',
        ("tests/test_scope_base.py::"
         "test_the_fallback_uses_the_remote_default_when_there_is_no_local_main"),
    ),
    (
        # resolve() hands back the gate's verified marker whenever one
        # exists -- the conflation this module replaces, reintroduced at the
        # one line where the recorded base is returned. Every fallback case
        # still passes (no marker is read there), so only the bug's own
        # reproduction goes red.
        "the scope base collapses to the verified marker",
        SCOPE_BASE,
        '        return entry["base"], RECORDED, '
        '_REASON_RECORDED.format(ticket=ticket)\n',
        '        marker = crew_common.read_text(os.path.join(\n'
        '            root, ".crew", ".verify-verified-at"))\n'
        '        return ((marker or entry["base"]).strip(), RECORDED,\n'
        '                _REASON_RECORDED.format(ticket=ticket))\n',
        ("tests/test_scope_base.py::"
         "test_a_commit_the_gate_verified_stays_in_the_ticket_evidence"),
    ),
    (
        # Codex round 1, finding 4: the fallback marker is dropped from the
        # outside-scope line and lives only on the scope-base line under it.
        # The union still happens, so the "names a committed file" case
        # stays green; only the line-marker case catches it.
        "scope_report's outside-scope line hides that it came from a fallback",
        SCOPE_REPORT,
        '        suffix = "" if source == scope_base.RECORDED else '
        'f" (fallback: {note})"\n',
        '        suffix = ""\n',
        ("tests/test_scope_base.py::"
         "test_scope_report_marks_the_outside_scope_line_itself_on_a_fallback"),
    ),
    (
        # Codex round 1, finding 5: one word reversed in ONE file. The two
        # substrings the first agreement test looked for both survive
        # ("commit on the ticket's own branch and nowhere else" is still
        # there), so only a full-sentence comparison can catch it.
        "pm.md reverses the commit permission by one word",
        os.path.join(CREW, "agents", "pm.md"),
        "The developer may commit on the ticket's own branch and nowhere",
        "The developer never commit on the ticket's own branch and nowhere",
        ("tests/test_scope_discipline.py::"
         "test_every_file_that_briefs_a_developer_states_the_same_commit_rule"),
    ),
    (
        # scope_report resolves the base, prints its line, and then reports
        # only the gate's list anyway. The scope-base line still appears, so
        # a reader sees a ticket-wide report that is not one.
        "scope_report prints the ticket base and ignores it",
        SCOPE_REPORT,
        "        changed = sorted(set(changed) | set(ticket_wide))\n",
        "        changed = sorted(set(changed))\n",
        ("tests/test_scope_base.py::"
         "test_scope_report_names_a_committed_file_the_gate_no_longer_sees"),
    ),
    # The 0.20.16 review adapter (T1). Each of these was also run by hand
    # against the tracked file, restored with `cp` and confirmed with `diff`.
    (
        # A reviewer that exited non-zero but printed CLEAN reads as CLEAN --
        # the "auth succeeded, the call failed, nothing looks wrong" case.
        "the verdict maps a non-zero reviewer exit to CLEAN",
        REVIEW_VERDICT,
        "    elif exit_code != 0:\n"
        "        reasons.append(f\"the reviewer exited {exit_code}\")\n",
        "",
        ("tests/test_review_verdict.py::"
         "test_parse_clean_text_with_a_failed_exit_is_incomplete"),
    ),
    (
        # One character buys a third round, the loop the ledger exists to end.
        "the review budget is raised to three rounds",
        REVIEW_LEDGER,
        "BUDGET = 2\n",
        "BUDGET = 3\n",
        ("tests/test_review_ledger.py::"
         "test_reserve_third_round_is_refused_and_state_is_needs_replan"),
    ),
    (
        # The receipt check still runs and still finds a receipt, and passes
        # a tree edited after the review.
        "the receipt check ignores the bundle hash",
        REVIEW_LEDGER,
        "    if current != receipt[\"bundle_sha256\"]:\n",
        "    if False:\n",
        ("tests/test_review_receipt.py::"
         "test_check_receipt_fails_after_the_tree_is_edited"),
    ),    (
        # Launch first, reserve after: a reviewer that takes review_run.py
        # down with it leaves no round on the ledger, so crashes are free.
        "the review round is reserved after launch instead of before",
        REVIEW_RUN,
        "    ok, number, message = review_ledger.reserve(args.root, args.ticket, "
        "args.provider,\n",
        "    if args.provider in LAUNCHED:\n"
        "        stdout, stderr, code, timed_out = launch(command_for(\n"
        "            args.provider, exe, args.root, prompt, args.model, args.effort),\n"
        "            args.root, args.timeout)\n"
        "    ok, number, message = review_ledger.reserve(args.root, args.ticket, "
        "args.provider,\n",
        ("tests/test_review_ledger.py::"
         "test_run_reserves_before_launch_so_a_crash_still_spends_the_round"),
    ),
)


# pytest's own exit codes (documented, not this file's invention): 0 all
# passed; 1 at least one test FAILED (a real assertion, or an error raised
# during a test); 2 execution interrupted; 3 an internal pytest error; 4 a
# usage error, which is what a collection failure -- an import blowing up
# on a SyntaxError, say -- actually produces; 5 no tests were collected at
# all. Only 1 is evidence that the TARGET TEST caught the mutation. Finding
# 13: the previous version of this treated every non-zero code the same,
# so a mutation that broke the whole file's syntax (crashing collection
# for every test in the suite, this one included) reported "RED (good)"
# indistinguishably from a mutation the target test actually caught -- and
# only 4 of the round's 18 new mutations had been hand-verified as the real
# thing rather than this.
_REAL_TEST_FAILURE = 1


def run_test(target):
    """Run one pytest target from the crew directory; return
    (exit_code, combined_output).

    PYTHONDONTWRITEBYTECODE=1: two mutations back to back can produce a
    source file of the SAME byte length (many of these are single-character
    swaps, e.g. "hits > 1" -> "hits > 0"), written within the same mtime
    tick. Python's default (mtime, size) pyc-invalidation check cannot tell
    those two versions apart, so the SECOND mutation's subprocess can load a
    stale bytecode cache left by the FIRST -- observed here as an
    intermittent "STILL GREEN" for a mutation that goes red on every
    isolated re-run. Never writing bytecode removes the cache entirely
    rather than trying to invalidate it correctly.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x"],
        cwd=CREW, capture_output=True, text=True, check=False, env=env)
    return completed.returncode, completed.stdout + completed.stderr


def read(target):
    with io.open(target, encoding="utf-8") as handle:
        return handle.read()


def write(target, text):
    with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def digest(target):
    """sha256 of the bytes on disk.

    Taken once per target before the first mutation and compared after every
    restore. Without it `restore` is assumed rather than checked, and a restore
    that silently did nothing is indistinguishable from one that worked -- the
    suite still prints PASS because `ok` tracks only whether each mutation went
    red. That is this repo's recurring shape: the signal and its absence look
    identical.
    """
    sha = hashlib.sha256()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def stale_backups(targets):
    """Targets that already have a `.bak` beside them, before anything runs.

    A `.bak` present at startup means a previous run died between
    `apply_mutation` and `restore` -- so the file in the tree is MUTATED and
    the `.bak` is the only good copy. Running anyway would `shutil.copy` the
    mutated file over that backup and destroy the original permanently, which
    is the exact defect class this suite's own mutation table flags for the
    code under test.
    """
    return [t for t in sorted(set(targets)) if os.path.exists(t + ".bak")]


# Targets with a mutation applied RIGHT NOW. `finally` unwinds on an exception
# and on KeyboardInterrupt, but a SIGTERM from an external timeout -- how this
# script is actually killed in practice -- terminates without unwinding, so
# neither the `finally` nor anything after it runs. This set plus the handlers
# below are what put the file back on those paths. SIGKILL and a hard process
# kill still cannot be caught by anything; `stale_backups` above is what covers
# that case on the NEXT run, which is why it refuses to start rather than
# repairing silently.
_LIVE = set()

# target -> sha256 of its bytes before the first mutation. Module state rather
# than a local in `main` because the signal and atexit paths restore too, and a
# restore nobody verified is the defect this whole section exists to close --
# verifying only on the path that happens to be convenient would leave the
# claim "every restore is verified" true of one path and false of three.
_PRISTINE = {}


def _verify(target):
    """Print and return False when `target` is not what it was. Never raises.

    Called from signal and atexit context, where an exception would replace
    the reason the process is exiting with a traceback about the cleanup.
    """
    expected = _PRISTINE.get(target)
    if expected is None:
        return True  # Nothing was recorded for it, so there is nothing to claim.
    try:
        found = digest(target)
    except OSError as err:
        print(f"WARNING: could not verify {target}: {err}")
        return False
    if found != expected:
        print(f"RESTORE FAILED -- source left modified\n  {target}\n"
              f"  expected {expected}\n  found    {found}")
        return False
    return True


def _restore_all(*_args):
    """Restore every live target, verify each, and keep the ones that failed.

    `_LIVE` is NOT cleared wholesale. `restore` discards a target only after
    its move succeeded, so a failure leaves the name in the set and the atexit
    pass tries again -- which is what the comment in `restore` promises. An
    unconditional clear here would silently make that promise false, and the
    only symptom would be a file left mutated after a signal.
    """
    ok = True
    for target in sorted(_LIVE):
        try:
            restore(target)
        except OSError as err:
            print(f"WARNING: could not restore {target}: {err}")
            ok = False
            continue
        if not _verify(target):
            ok = False
    return ok


def _on_signal(signum, _frame):
    _restore_all()
    # SystemExit unwinds, so atexit still runs -- and every target restored
    # here is already out of `_LIVE`, which is why restoring twice is safe and
    # why one that FAILED here gets a second attempt there. Exiting 128+signum
    # is the shell convention for "killed by this signal" and keeps the
    # caller's timeout distinguishable from a suite failure.
    sys.exit(128 + signum)


def install_exit_handlers():
    """Restore on every exit path this process can observe.

    SIGBREAK exists only on Windows and SIGHUP only on POSIX, so both are
    looked up by name rather than referenced -- an unguarded `signal.SIGBREAK`
    is an AttributeError on Linux, which would take the whole suite down at
    import time on the platform CI runs.
    """
    atexit.register(_restore_all)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK", "SIGHUP"):
        num = getattr(signal, name, None)
        if num is None:
            continue
        try:
            signal.signal(num, _on_signal)
        except (ValueError, OSError, RuntimeError):
            # Not the main thread, or a platform that refuses this signal.
            # A handler crew could not install is not a reason to skip the run.
            pass


def apply_mutation(target, find, replace):
    """Patch `target`, backing it up. False when the anchor is not unique.

    The backup is taken BEFORE the write and restored here if the write
    itself fails -- a disk error or an interrupt between `shutil.copy` and
    the last byte would otherwise leave the caller with a truncated source
    file and a `.bak` beside it, which is a worse outcome than the bug this
    script exists to find.
    """
    text = read(target)
    if text.count(find) != 1:
        return False

    # Never copy over an existing backup. `main` refuses to start when one is
    # present, so reaching here means a restore failed mid-run; overwriting
    # would replace the last good copy with the already-mutated file.
    if os.path.exists(target + ".bak"):
        raise RuntimeError(
            f"{target}.bak already exists -- the previous mutation was not "
            f"restored. Refusing to overwrite the only good copy.")

    # The backup is built beside the target and RENAMED into place, so
    # `<target>.bak` never exists in a partial state. That matters because the
    # startup guard treats any `.bak` it finds as the only good copy and tells
    # the user to move it over the target: a half-written backup left by a
    # signal during a plain `shutil.copy` would make that instruction destroy
    # the intact source. `os.replace` is atomic on both platforms.
    #
    # The copy and the write still fail in ways that need opposite responses,
    # so they cannot share a handler. `shutil.copy` never modifies the SOURCE:
    # if it fails the original is intact and the partial copy is the damaged
    # one, so restoring from it is precisely what would corrupt the file this
    # is trying to protect. Discard the partial instead.
    partial = target + ".bak.partial"
    try:
        shutil.copy(target, partial)
        os.replace(partial, target + ".bak")
    except BaseException:
        try:
            if os.path.exists(partial):
                os.remove(partial)
        except OSError as cleanup_error:
            print(f"WARNING: stray partial backup at {partial}: {cleanup_error}")
        raise

    # Past this point the backup is known complete, so a failed write is the
    # case restoring exists for.
    # Registered BEFORE the write: a signal arriving mid-write must still find
    # this target in `_LIVE`, because the backup is already complete and the
    # file on disk is already the thing that needs putting back.
    _LIVE.add(target)
    try:
        write(target, text.replace(find, replace, 1))
    except BaseException:
        # Best-effort, and it must not replace the exception that explains
        # the failure: a restore blocked by a read-only target would
        # otherwise report the wrong cause.
        try:
            restore(target)
        except OSError as restore_error:
            print(f"WARNING: could not restore {target}: {restore_error}")
        raise
    return True


def restore(target):
    """Put `target` back if a backup is present. Safe to call twice."""
    backup = target + ".bak"
    if os.path.exists(backup):
        shutil.move(backup, target)
    # Discarded only after the move succeeded. A move that raised leaves the
    # target registered, so the atexit pass tries again rather than treating a
    # failed restore as a finished one.
    _LIVE.discard(target)


def main():
    """Run every mutation; return 0 only when all of them go red FOR REAL --
    a genuine assertion failure in the named test, not merely a non-zero
    exit code (finding 13)."""
    targets = [m[1] for m in MUTATIONS]

    # Before anything is touched. A stale `.bak` means the tree already holds
    # a mutation from a killed run, and the next `shutil.copy` would destroy
    # the only original. Refuse, name the files, and say how to recover.
    stale = stale_backups(targets)
    if stale:
        print("REFUSING TO RUN -- a previous run left a backup behind, so the "
              "file in the tree is the MUTATED one:")
        for target in stale:
            print(f"  {target}.bak")
        print("\nRecover by moving each backup over its target, which undoes "
              "the mutation:")
        for target in stale:
            print(f"  mv {target}.bak {target}")
        print("Then re-run. (`git checkout -- <target>` works too, and also "
              "discards any real edit you had in that file.)")
        return 2

    # A `.bak.partial` is a backup that was interrupted before it was renamed
    # into place. The target is intact in that case -- that is the point of
    # building it under a second name -- so it is litter, not evidence, and
    # removing it is safe where removing a `.bak` never is.
    for target in sorted(set(targets)):
        partial = target + ".bak.partial"
        if os.path.exists(partial):
            print(f"note: discarding an interrupted backup at {partial} "
                  f"(the target was never modified)")
            os.remove(partial)

    install_exit_handlers()
    # The answer key for every restore, on every path. Module state, because
    # the signal and atexit handlers verify too. Taken here, once, from files
    # known unmutated because of the guard above.
    _PRISTINE.clear()
    _PRISTINE.update({target: digest(target) for target in sorted(set(targets))})

    ok = True
    for label, target, find, replace, test in MUTATIONS:
        if not apply_mutation(target, find, replace):
            print(f"{'ANCHOR LOST -- suite is not testing this':40} {label}")
            ok = False
            continue
        try:
            # `output` is deliberately dropped: a mutation's job is to make
            # the suite go red, and the failure text is the suite's to report.
            code, _ = run_test(test)
        finally:
            restore(target)
            if not _verify(target):
                print(f"{'  ^ above, restoring for':40} {label}")
                ok = False
        if code == 0:
            print(f"{'STILL GREEN -- TEST IS VACUOUS':40} {label}")
            ok = False
        elif code != _REAL_TEST_FAILURE:
            # Went red, but not because the target test caught anything --
            # a collection/import error (SyntaxError, a bad import) crashed
            # the whole run before the test ever executed, or nothing
            # matching `test` was even collected. Reported separately, and
            # counted as a failure of THIS suite, because it proves nothing
            # about whether the mutation is real.
            print(f"{'RED BUT UNPROVEN -- exit ' + str(code) + ', not a test failure':40} "
                  f"{label}")
            ok = False
        else:
            print(f"{'RED (good)':40} {label}")

    print("\nSABOTAGE SUITE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
