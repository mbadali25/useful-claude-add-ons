"""The L-0888 mutations: the verify trust store and the gate's use of it.
Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace,
test) -- and appended to it there. Run `sabotage.py`, not this file.

verify-gate.sh runs a repo's verify map (or its smoke script) only for a repo
this machine trusts. Each mutation reintroduces one way that guard could go
wrong: a check dropped, a failure read as trusted, an unknown collapsed into a
pass, a lookalike remote accepted, an ownership or pin test skipped, the test
seam honoured where it must not be, the model allowed to approve. Every target
is a case in `test_verify_trust.py`, `test_verify_gate_trust.py` or
`test_scope_guard_trust.py`.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
TRUST = os.path.join(_S, "verify_trust.py")
GATE = os.path.join(_S, "verify-gate.sh")
GUARD = os.path.join(_S, "scope_guard.py")

_T = "tests/test_verify_trust.py::"
_G = "tests/test_verify_gate_trust.py::"
_S_ = "tests/test_scope_guard_trust.py::"
_FIRST = ('  gate_trust_check "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0\n')

TRUST_MUTATIONS = (
    ("trust gate: the first check is dropped, so an unapproved smoke script runs (L-0888)", GATE,
     _FIRST, "  :\n",
     _G + "test_gate_a_smoke_script_nobody_approved_runs_nothing"),
    ("trust gate: the second check is dropped, so a verify.json swapped after the first "
     "check runs (L-0888)", GATE,
     '  gate_trust_check "$FP_DIR" || exit 0\n', "  :\n",
     _G + "test_gate_a_verify_json_rewritten_between_the_two_checks_runs_nothing"),
    ("trust gate: any answer from the check reads as trusted (L-0888)", GATE,
     '  [ "$_trc" -eq 0 ] && return 0\n', "  return 0\n",
     _G + "test_gate_one_byte_changed_after_approval_runs_nothing"),
    ("trust gate: --price skips the trust check (L-0888)", GATE,
     '  gate_trust_check "$PRICE_DIR" || exit 1\n', "",
     _G + "test_gate_price_on_an_untrusted_repo_runs_nothing"),
    ("trust store: any approved hash trusts any bytes (L-0888)", TRUST,
     "    if current in hashes:\n", "    if hashes:\n",
     _T + "test_evaluate_one_byte_changed_in_verify_json_is_changed"),
    ("trust store: the file bytes are left out of the digest (L-0888)", TRUST,
     '+ len(data).to_bytes(8, "big") + data)', '+ len(data).to_bytes(8, "big"))',
     _T + "test_evaluate_one_byte_changed_in_the_smoke_script_is_changed"),
    ("trust store: a smoke script hashes as the verify.json (L-0888)", TRUST,
     '[("smoke:" + cand, path)]', '[("verify.json", path)]',
     _T + "test_evaluate_same_bytes_in_a_smoke_script_are_not_the_verify_json"),
    ("trust store: an unreadable store reads as trusted (L-0888)", TRUST,
     "        return Verdict(EXIT_UNKNOWN, f\"VERIFY GATE: UNKNOWN",
     "        return Verdict(EXIT_TRUSTED, f\"VERIFY GATE: UNKNOWN",
     _T + "test_evaluate_a_corrupt_store_is_unknown"),
    ("trust store: the test seam is honoured for a store the environment did not name (L-0888)",
     TRUST,
     '    if os.environ.get(ENV_STORE) and store.get("testTrustAll") is True:\n',
     '    if store.get("testTrustAll") is True:\n',
     _T + "test_evaluate_the_test_seam_is_ignored_for_a_store_not_named_by_the_environment"),
    ("trust store: a userinfo URL parses as the owner's (L-0888)", TRUST,
     '_HTTPS = re.compile(r"https://([^/@:\\s]+)/',
     '_HTTPS = re.compile(r"https://(?:[^/]*@)?([^/@:\\s]+)/',
     _T + "test_evaluate_a_lookalike_remote_is_untrusted[https://mbadali25@github.com/mbadali25/x]"),
    ("trust store: an owner is matched by substring (L-0888)", TRUST,
     "            if owner is None or owner not in owners:\n",
     "            if owner is None or not any(o in owner for o in owners):\n",
     _T + "test_evaluate_a_lookalike_remote_is_untrusted[https://github.com/mbadali25x/x]"),
    ("trust store: only the first remote is judged (L-0888)", TRUST,
     "    for name, raw in urls.items():\n",
     "    for name, raw in list(urls.items())[:1]:\n",
     _T + "test_evaluate_an_allowlisted_remote_beside_a_foreign_one_is_untrusted"),
    ("trust store: a pushurl is not judged (L-0888)", TRUST,
     "        for url in raw + pushes.get(name, []):\n",
     "        for url in raw:\n",
     _T + "test_evaluate_a_foreign_pushurl_is_untrusted"),
    ("trust store: a local insteadOf rewrite is ignored (L-0888)", TRUST,
     "    if rewrites:\n", "    if False:\n",
     _T + "test_evaluate_a_local_rewrite_is_untrusted_even_when_it_changes_nothing"),
    ("trust store: the raw and the resolved remote may disagree (L-0888)", TRUST,
     '                or sorted(pushed.split("\\n")[:-1]) != sorted(pushes.get(name, raw)):\n',
     '                and False and sorted(pushed.split("\\n")[:-1]) != sorted(pushes.get(name, raw)):\n',
     _T + "test_evaluate_a_rewrite_outside_the_local_config_is_untrusted"),
    ("trust store: the ownership check is skipped (L-0888)", TRUST,
     "                if os.stat(path).st_uid != uid:\n", "                if False:\n",
     _T + "test_evaluate_a_top_level_owned_by_another_user_is_untrusted"),
    ("trust store: the --under restriction is ignored (L-0888)", TRUST,
     "        if under and not _under(identity, under):\n", "        if False:\n",
     _T + "test_evaluate_an_owner_restricted_to_a_directory_trusts_only_below_it"),
    ("trust store: a changed remote set is not compared with the pin (L-0888)", TRUST,
     "        if pin is not None and pin != remotes:\n", "        if False:\n",
     _T + "test_evaluate_a_remote_changed_after_the_pin_is_remote_changed"),
    ("trust store: a pin that cannot be written still trusts (L-0888)", TRUST,
     "            except TrustError as exc:\n                return Verdict(EXIT_UNTRUSTED,",
     "            except TrustError as exc:\n                return Verdict(EXIT_TRUSTED,",
     _T + "test_evaluate_a_pin_that_cannot_be_written_is_untrusted"),
    ("trust store: approve confirms itself (L-0888)", TRUST,
     "    if yes:\n        return True\n    if not sys.stdin.isatty():",
     "    return True\n    if not sys.stdin.isatty():",
     _T + "test_approve_without_a_terminal_and_without_yes_changes_nothing"),
    ("scope guard: a model-run verify_trust approve is allowed (L-0888)", GUARD,
     "    if _TRUST_RE.search(command):\n", "    if False:\n",
     _S_ + "test_a_trust_store_change_is_refused[approve-module]"),
    ("scope guard: a Write of the trust store is allowed (L-0888)", GUARD,
     "        if os.path.basename(path).lower() in (TRUST_STORE_NAME, TRUST_STORE_NAME + \".lock\") \\\n",
     "        if False and os.path.basename(path).lower() in (TRUST_STORE_NAME, TRUST_STORE_NAME + \".lock\") \\\n",
     _S_ + "test_a_write_or_edit_of_the_store_is_refused[Write-module]"),
)
