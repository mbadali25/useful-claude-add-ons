"""crew 1.3.36 one-process promote-gate mutations, in `sabotage.py`'s tuple shape.

Each puts back one way the rewrite could have lost a decision, the deadline, or
the shell's fail-closed hand-off, and names the must-block or must-allow case
that has to go red. `promote_tree_mutations.py` appends this family to its own
tuple, and `sabotage.py` imports that, so the full run and the
anchor-present-exactly-once test cover it without a change to the harness. To
run this family alone, with sabotage.py's own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, promote_gate_mutations as m; \
        sabotage.MUTATIONS = m.PROMOTE_GATE_MUTATIONS; raise SystemExit(sabotage.main())"
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
SH = os.path.join(_SCRIPTS, "promote-gate.sh")
GATE = os.path.join(_SCRIPTS, "_promote_gate.py")
VERDICT = os.path.join(_SCRIPTS, "_promote_verdict.py")
_P = "tests/test_promote_gate_one_process.py::"
_CORPUS = _P + "test_the_corpus_decides_as_the_old_gate_did[{}]"

PROMOTE_GATE_MUTATIONS = (
    # --- the deadline -----------------------------------------------------
    ("_promote_gate.py lets a configured deadline outlive the hook", GATE,
     "    return min(float(configured), ceiling)\n",
     "    return float(configured)\n",
     _P + "test_a_configured_deadline_is_used_and_clamped"),
    ("_promote_gate.py ignores the configured deadline", GATE,
     "self._deadline = self.start + deadline_seconds(None, configured_seconds())",
     "self._deadline = self.start + deadline_seconds(None, None)",
     _P + "test_the_configured_deadline_is_enforced_end_to_end"),
    ("_promote_gate.py keeps no margin under the hook timeout", GATE,
     "DEFAULT_MARGIN = 4 ",
     "DEFAULT_MARGIN = 0 ",
     _P + "test_the_default_deadline_is_the_hook_timeout_less_the_margin"),
    ("_promote_gate.py reads true as one second", GATE,
     "    if isinstance(value, bool) or not isinstance(value, (int, float)):\n",
     "    if not isinstance(value, (int, float)):\n",
     _P + "test_an_unusable_configured_deadline_reads_as_null"),
    ("_promote_gate.py reads a negative deadline as a deadline", GATE,
     '    return float(value) if math.isfinite(value) and value > 0 else None\n',
     '    return float(value) if math.isfinite(value) else None\n',
     _P + "test_an_unusable_configured_deadline_reads_as_null"),
    ("_promote_gate.py counts the deadline from python's start, not the shell's", GATE,
     '            self.start = float(raw) if raw else time.time()\n',
     '            self.start = time.time()\n',
     _P + "test_the_clock_counts_from_the_shells_start"),
    # --- the shell's hand-off ------------------------------------------------
    ("promote-gate.sh lets an unknown gate status through", SH,
     'Its reason is above." >&2\n  exit 2\n',
     'Its reason is above." >&2\n  exit 0\n',
     _P + "test_the_shell_maps_the_gates_exit_status"),
    ("promote-gate.sh stops writing the unreadable-map framing", SH,
     '  if [ "$GATE_STATUS" -ge 10 ] && [ "$GATE_STATUS" -lt 20 ]; then\n',
     '  if false; then\n',
     _P + "test_the_shell_maps_the_gates_exit_status"),
    ("promote-gate.sh lets a missing gate through", SH,
     'Reinstall crew." >&2\n    exit 2\n',
     'Reinstall crew." >&2\n    exit 0\n',
     _P + "test_a_missing_gate_blocks"),
    ("promote-gate.sh starts a helper for the payload again", SH,
     "IFS= read -r -d '' INPUT || :\n",
     'INPUT=$(cat)\n',
     "tests/test_guard_spawns.py::test_the_allow_path_starts_no_helper_programs[promote-gate.sh]"),
    # --- decisions the rewrite carries ---------------------------------------
    ("_promote_gate.py reads an unreadable map as a map that gates nothing", GATE,
     "        if status != 0:\n            if why:\n",
     "        if False:\n            if why:\n",
     _CORPUS.format("a-committed-map-that-is-not-json")),
    ("_promote_gate.py lets a failed pre-deploy check allow", GATE,
     "        raise Stop(VERDICT_BASE + status)\n",
     "        return []\n",
     "tests/test_promote_gate_fails_closed.py::test_the_gate_blocks_when_its_own_check_cannot_RUN"),
    ("_promote_gate.py checks only the first matched environment", GATE,
     "        self.envlist = names\n",
     "        self.envlist = names[:1]\n",
     _CORPUS.format("two-environments-name-each-unmet-precondition")),
    ("_promote_gate.py drops the environments a dispatch names", GATE,
     '            elif kind == "env" and tok not in names:\n',
     '            elif False:\n',
     _CORPUS.format("a-dispatch-only-the-dispatch-reader-can-see")),
    ("_promote_gate.py reads an expired incident as open", GATE,
     "    return expires > 0 and int(time.time()) < expires\n",
     "    return expires > 0\n",
     _CORPUS.format("an-expired-incident-blocks-again")),
    ("_promote_gate.py records no in-flight marker", GATE,
     '        with open(".crew/.deploy-in-flight", "w", encoding="utf-8", newline="\\n") as handle:\n',
     '        with open(os.devnull, "w", encoding="utf-8", newline="\\n") as handle:\n',
     _CORPUS.format("prod-with-every-precondition-met")),
    ("_promote_gate.py reads a map deleted from the working copy as the opt-out", GATE,
     '        self.map_dirty = "deleted, and committed at HEAD"\n        return False\n',
     "        return True\n",
     _CORPUS.format("the-map-deleted-from-the-working-copy")),
    ("_promote_gate.py reads an untracked file as a clean tree", GATE,
     "        if status:\n            self.block(f\"the tree this deploy runs from",
     "        if False:\n            self.block(f\"the tree this deploy runs from",
     _CORPUS.format("an-untracked-file-dirties-the-tree")),
    ("_promote_verdict.py asks for no human approval marker", VERDICT,
     "            if not os.path.exists(marker):\n",
     "            if False:\n",
     _CORPUS.format("prod-without-the-human-marker")),
    ("_promote_verdict.py accepts a runbook verified a year ago", VERDICT,
     "                        if age > 90:\n",
     "                        if age > 9000:\n",
     _CORPUS.format("prod-with-a-stale-runbook")),
    ("_promote_verdict.py accepts a runbook that does not exist", VERDICT,
     "            elif not os.path.exists(rb):\n",
     "            elif False:\n",
     _CORPUS.format("prod-with-a-missing-runbook")),
    ("_promote_gate.py resolves a cd to a directory that is not there", GATE,
     '    return real(path) if os.path.isdir(path) else ""\n',
     "    return real(path)\n",
     _CORPUS.format("a-cd-that-resolves-nowhere")),
    ("_promote_gate.py reads a helper that ends the interpreter as an allow", GATE,
     '        traceback.print_exc()\n        return 1\n',
     '        traceback.print_exc()\n        return 0\n',
     _P + "test_a_helper_that_ends_the_interpreter_is_never_an_allow"),
)
