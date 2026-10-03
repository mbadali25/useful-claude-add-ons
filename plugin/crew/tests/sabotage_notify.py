"""Mutations for crew_notify.py and its wrappers (T-0051) -- a module of its own,
same shape as sabotage_event_claim.py, a sibling of sabotage.py so that file
stays under `.pylintrc`'s max-module-lines.

One mutation per filter branch. Each must turn its named test red; one that
stays green is a test that checks nothing. NOTIFY_MUTATIONS is the list
T-0060 appends its blocker mutations to.

    python3 tests/sabotage_notify.py [--scratch DIR]
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
NOTIFY = os.path.join(SCRIPTS, "crew_notify.py")
NOTIFY_SH = os.path.join(SCRIPTS, "notify.sh")
CONFIG = os.path.join(SCRIPTS, "crew_config.py")
_T = "tests/test_crew_notify.py::"
_W = "tests/test_flavour_windows_direction.py::"

NOTIFY_MUTATIONS = (
    ("idle_prompt added to the question set",
     NOTIFY,
     'QUESTION_TYPES = ("permission_prompt", ',
     'QUESTION_TYPES = ("idle_prompt", "permission_prompt", ',
     _T + "test_quiet_types_send_nothing"),
    ("a missing notification_type classified as a question",
     NOTIFY,
     '        return ("unknown", None, None)\n',
     '        return ("question", None, "Needs permission")\n',
     _T + "test_missing_type_is_quiet_and_logged"),
    ("the provider none exit removed",
     NOTIFY,
     '    if not provider or provider == "none":\n',
     '    if not provider:\n',
     _T + "test_repo_none_opts_out_with_notice"),
    ("the notify.events filter bypassed",
     NOTIFY,
     '    if event not in cfg.get("events", ()):\n',
     '    if False:  # pylint: disable=using-constant-test\n',
     _T + "test_event_not_in_events_sends_nothing"),
    ("the dedupe window comparison inverted",
     NOTIFY,
     "now - at < window:",
     "now - at > window:",
     _T + "test_dedupe_inside_window_sends_once"),
    ("state advanced before the transport's result",
     NOTIFY,
     "        if not ok:\n"
     '            _say(f"send failed: {why}")\n'
     '            return f"failed:{why}"\n'
     "        if lock.held:\n",
     "        if lock.held:\n",
     _T + "test_failed_send_does_not_advance_state"),
    ("a 429's retry_after ignored",
     NOTIFY,
     "wait = float(retry_after) if retry_after is not None else PACE_SECONDS",
     "wait = PACE_SECONDS",
     _T + "test_429_retry_after_honoured"),
    ("HTML escaping removed",
     NOTIFY,
     '    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")\n',
     '    return text or ""\n',
     _T + "test_html_escaped"),
    ("the repo-over-global merge order swapped",
     CONFIG,
     "    merged = crew_state.merge_defaults(default_config(), global_cfg)\n"
     "    merged = crew_state.merge_defaults(merged, repo_cfg)\n",
     "    merged = crew_state.merge_defaults(default_config(), repo_cfg)\n"
     "    merged = crew_state.merge_defaults(merged, global_cfg)\n",
     _T + "test_repo_value_overrides_global"),
    ("the example-chat-id guard removed",
     NOTIFY,
     '    if cfg.get("chatId") is not None and str(cfg.get("chatId")) == EXAMPLE_CHAT_ID:\n',
     '    if False:  # pylint: disable=using-constant-test\n',
     _T + "test_example_chat_id_counts_as_unset"),
    ("the notify.sh claim bypassed",
     NOTIFY_SH,
     "[ $? -eq 10 ] && exit 0",
     ":",
     _W + "test_one_notification_sends_one_ping_across_both_flavours"),
    ("the subject dropped from the line",
     NOTIFY,
     "    parts = [_one_line(subject), head, ",
     "    parts = [head, ",
     _T + "test_subject_leads_every_line"),
    ("the reserved blocker check removed",
     NOTIFY,
     "    if event in RESERVED:\n",
     "    if False:  # pylint: disable=using-constant-test\n",
     _T + "test_reserved_blocker_sends_nothing_and_names_t0060"),
    ("the episode key ignored",
     NOTIFY,
     'seen.get("key") == episode[1]:',
     'seen.get("key") == episode[1] and False:',
     _T + "test_same_prompt_id_pings_once_new_prompt_id_pings_again"),
    ("redact made identity",
     NOTIFY,
     '    out = "" if text is None else str(text)\n',
     '    return "" if text is None else str(text)\n',
     _T + "test_redact_transcript_token_never_sent_or_stored"),
    ("the detached-HEAD branch prints HEAD",
     NOTIFY,
     '        place = ticket or "detached"\n',
     '        place = "HEAD"\n',
     _T + "test_detached_head_shows_ticket_not_HEAD"),
    ("the AskUserQuestion message check dropped",
     NOTIFY,
     '             or (isinstance(message, str) and "AskUserQuestion" in message)\n',
     "",
     _T + "test_askuserquestion_permission_prompt_is_a_question"),
)


def run_test(target):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x",
                           "-p", "no:cacheprovider", "--run-slow"],
                          cwd=CREW, capture_output=True, text=True, check=False, env=env)
    return done.returncode


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default=None)
    args = parser.parse_args(argv)
    scratch = args.scratch or tempfile.mkdtemp(prefix="sabotage-notify-")
    os.makedirs(scratch, exist_ok=True)
    ok = True
    for index, (label, target, find, replace, test) in enumerate(NOTIFY_MUTATIONS):
        with open(target, encoding="utf-8", newline="") as handle:
            text = handle.read()
        if text.count(find) != 1:
            print(f"{'ANCHOR LOST':32} {label}")
            ok = False
            continue
        copy = os.path.join(scratch, f"{index:02d}-{os.path.basename(target)}")
        shutil.copyfile(target, copy)
        mutated = text.replace(find, replace)
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(mutated)
            code = run_test(test)
        finally:
            shutil.copyfile(copy, target)
        if not filecmp.cmp(copy, target, shallow=False):
            print(f"RESTORE FAILED for {target} - the scratch copy is {copy}")
            return 3
        verdict = {0: "STILL GREEN - VACUOUS", 1: "RED (good)"}.get(code, f"RED BUT UNPROVEN - exit {code}")
        ok = ok and code == 1
        print(f"{verdict:32} {label}  [{test.split('::')[-1]}]")
    print("\nNOTIFY SABOTAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
