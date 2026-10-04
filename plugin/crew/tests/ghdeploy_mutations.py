"""T-0045 `crew_ghdeploy.py check` mutations, in `sabotage.py`'s tuple shape.

NOT yet wired into `sabotage.py`: `scripts/check-tooling-pr.py` (owner rule,
T-0087) makes `plugin/crew/tests/sabotage*.py` harness, and a harness change
may not ride in a feature PR. L-0650, a tooling-only PR, appends
`GHDEPLOY_MUTATIONS` to `sabotage.py`'s MUTATIONS. Until then run them with
sabotage.py's own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, ghdeploy_mutations as m; \
        sabotage.MUTATIONS = m.GHDEPLOY_MUTATIONS; raise SystemExit(sabotage.main())"

One entry per refusing branch of `check` (exit 2 and exit 3), each naming the
must-block case that has to go red, then the must-allow non-vacuity entries:
an allow path broken in a way the must-allow cases have to catch.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = os.path.join(CREW, "hooks", "scripts", "crew_ghdeploy.py")
_T = "tests/test_crew_ghdeploy.py::"
_P = _T + "test_entry_problem[{}]"

GHDEPLOY_MUTATIONS = (
    # --- exit 2: entry problems -------------------------------------------
    ("ghdeploy: `github` may be an empty list", GH,
     "isinstance(github, list) and github and all(",
     "isinstance(github, list) and all(",
     _P.format("github empty list")),
    ("ghdeploy: a `github` list may hold a non-object", GH,
     "and all(isinstance(e, dict) for e in github):",
     "and True:",
     _P.format("github list holding a string")),
    ("ghdeploy: a `github` string reads as an entry", GH,
     '    raise Refused("github-shape", ',
     '    return [github]\n    raise Refused("github-shape", ',
     _P.format("github a string")),
    ("ghdeploy: an unknown key is ignored", GH,
     "    if unknown:\n", "    if False:\n",
     _P.format("unknown key")),
    ("ghdeploy: a missing workflow is not named", GH,
     '    if "workflow" not in entry:\n', "    if False:\n",
     _P.format("workflow missing")),
    ("ghdeploy: a workflow display name is accepted", GH,
     "WORKFLOW.fullmatch(workflow) is None:", "False:",
     _P.format("workflow display name")),
    ("ghdeploy: a missing ref is not named", GH,
     '    if "ref" not in entry:\n', "    if False:\n",
     _P.format("ref missing")),
    ("ghdeploy: a ref starting with - is accepted", GH,
     '    if ref.startswith("-"):\n', "    if False:\n",
     _P.format("ref leading dash")),
    ("ghdeploy: a ref holding .. is accepted", GH,
     '    if ".." in ref:\n', "    if False:\n",
     _P.format("ref dotdot")),
    ("ghdeploy: a tag ref is accepted", GH,
     '    if ref.startswith("refs/tags/"):\n', "    if False:\n",
     _P.format("ref tag")),
    ("ghdeploy: a ref outside the value grammar is accepted", GH,
     "    if not _fits(ref):\n", "    if False:\n",
     _P.format("ref space")),
    ("ghdeploy: `inputs` that is not an object is not named", GH,
     "    if not isinstance(inputs, dict):\n", "    if False:\n",
     _P.format("inputs not object")),
    ("ghdeploy: an input name outside the grammar is accepted", GH,
     "        if NAME.fullmatch(name) is None:\n", "        if False:\n",
     _P.format("input name bad")),
    ("ghdeploy: a non-string input value is not named", GH,
     "        if not isinstance(value, str):\n", "        if False:\n",
     _P.format("input value not string")),
    ("ghdeploy: an input value with $( is accepted", GH,
     "        if not _fits(value):\n", "        if False:\n",
     _P.format("input value with $(")),
    ("ghdeploy: shaInput may also be a fixed input", GH,
     "    if sha is not None and sha in inputs:\n", "    if False:\n",
     _P.format("shaInput also in inputs")),
    ("ghdeploy: shaInput may equal correlationInput", GH,
     "    if corr is not None and corr == sha:\n", "    if False:\n",
     _P.format("shaInput equals correlationInput")),
    ("ghdeploy: correlationInput may also be a fixed input", GH,
     "    if corr is not None and corr in inputs:\n", "    if False:\n",
     _P.format("correlationInput also in inputs")),
    ("ghdeploy: a deployJob with a control character is accepted", GH,
     "any(ord(c) < 32 for c in job)", "False",
     _P.format("deployJob control char")),
    ("ghdeploy: the upper bound of a range is dropped", GH,
     "or not low <= value <= high:", "or not low <= value:",
     _P.format("watchMinutes 361")),
    ("ghdeploy: the lower bound of a range is dropped", GH,
     "or not low <= value <= high:", "or not value <= high:",
     _P.format("watchMinutes 0")),
    ("ghdeploy: a bool reads as an integer", GH,
     "if isinstance(value, bool) or not isinstance(value, int)",
     "if not isinstance(value, int)",
     _P.format("watchMinutes bool")),
    ("ghdeploy: an env name outside the grammar goes into the correlation id", GH,
     "and not _fits(env):", "and False:",
     _T + "test_correlation_needs_an_env_name_in_the_value_grammar"),
    ("ghdeploy: `deploy` may carry a string that is no entry's prefix", GH,
     "or set(declared) != wanted:", "or not wanted <= set(declared):",
     _T + "test_check_refuses_deploy_prefix_mismatch"),
    ("ghdeploy: `deploy` may miss an entry's prefix", GH,
     "or set(declared) != wanted:", "or not set(declared) <= wanted:",
     _T + "test_check_refuses_deploy_prefix_mismatch"),
    # --- exit 3: could-not-tell -------------------------------------------
    ("ghdeploy: an absent map is not named as absent", GH,
     "    if not os.path.lexists(path):\n", "    if False:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: an unparseable map crashes instead of could-not-tell", GH,
     "    except (OSError, ValueError) as exc:\n", "    except OSError as exc:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: `environments` that is not an object is not named", GH,
     "    if not isinstance(envs, dict):\n", "    if False:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: a missing environment is not named", GH,
     "    if env not in envs:\n", "    if False:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: an environment that is not an object is not named", GH,
     "    if not isinstance(envs[env], dict):\n", "    if False:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: an unreadable HEAD prints a dispatch anyway", GH,
     '    if proc.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", sha) is None:\n',
     "    if False:\n",
     _T + "test_check_unreadable_map_is_could_not_tell"),
    ("ghdeploy: check runs gh", GH,
     "    sha = _head(root)\n",
     '    subprocess.run(["gh", "api", "user"], check=False, capture_output=True)\n'
     "    sha = _head(root)\n",
     _T + "test_check_calls_no_gh"),
    # --- must-allow non-vacuity -------------------------------------------
    ("ghdeploy: the prefix sorts inputs instead of keeping their order", GH,
     'for name, value in entry.get("inputs", {}).items():',
     'for name, value in sorted(entry.get("inputs", {}).items()):',
     _T + "test_prefix_is_listed_order"),
    ("ghdeploy: the correlation id goes before the sha", GH,
     "    if entry.get(\"shaInput\"):\n        line +=",
     "    if entry.get(\"correlationInput\"):\n        line += ' -f c=x'\n"
     "    if entry.get(\"shaInput\"):\n        line +=",
     _T + "test_dispatch_appends_sha_then_correlation"),
    ("ghdeploy: the printed dispatch no longer carries the deploy prefix", GH,
     "    line = prefix(entry)\n",
     '    line = prefix(entry).replace(" --ref ", " -r ")\n',
     _T + "test_dispatch_matches_promote_gate"),
)
