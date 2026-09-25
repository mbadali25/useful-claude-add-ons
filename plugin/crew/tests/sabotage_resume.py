"""Mutations for T-0006's auto-resume decision -- kept in a module of its own,
same shape as sabotage_event_claim.py, a sibling of sabotage.py so that file
stays under `.pylintrc`'s max-module-lines rather than growing it again.

Each entry is (label, target, find, replace, pytest target): reintroduce one
way the guard could fail open, and the named test must go red with a real
test failure (pytest exit 1), not a collection error.

    python3 tests/sabotage_resume.py [--scratch DIR]

Restores by scratch copy and compares the restored bytes with it; a mismatch
stops the run at once.
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
RESUME = os.path.join(SCRIPTS, "crew_resume.py")
CONTEXT = os.path.join(SCRIPTS, "crew_context.py")
WRITE_SH = os.path.join(SCRIPTS, "handoff-write.sh")
WRITE_PS1 = os.path.join(SCRIPTS, "handoff-write.ps1")
_T = "tests/test_crew_resume.py::"
_H = "tests/test_crew_resume_hook.py::"
_OFF = "  # pylint: disable=using-constant-test\n"

RESUME_MUTATIONS = (
    ("/crew:approve is allowlisted and no longer excluded", RESUME,
     'EXCLUDED = (\n    "/crew:approve",\n',
     'RESUME_COMMANDS = RESUME_COMMANDS + (("/crew:approve", "ticket"),)\nEXCLUDED = (\n',
     _T + "test_approve_is_never_resumed"),
    ("a repo `true` arms auto-resume without the machine opt-in", RESUME,
     "    if _auto(machine) is not True:\n",
     "    if _auto(machine) is not True and not any(\n"
     '            _auto(_load(os.path.join(root, ".crew", n))) is True for n in ("crew.json", "config.json")):\n',
     _T + "test_repo_true_without_machine_opt_in_does_not_fire"),
    ("a repo `false` no longer vetoes the machine opt-in", RESUME,
     '        if _auto(_load(os.path.join(root, ".crew", name))) is False:\n',
     '        if False:' + _OFF,
     _T + "test_repo_false_in_crew_json_vetoes"),
    ("the handoff's head: line is no longer matched against HEAD", RESUME,
     "    if not head_line or not head or not head.lower().startswith(head_line.group(1).lower()):\n",
     "    if False:" + _OFF,
     _T + "test_head_mismatch_waits"),
    ("the handoff's branch: line is no longer matched against the checkout", RESUME,
     "    if not branch_line or not branch or branch_line.group(1) != branch:\n",
     "    if False:" + _OFF,
     _T + "test_branch_mismatch_waits"),
    ("a handoff already resumed can be resumed again (consumed-once dropped)", RESUME,
     "    if sha in consumed:\n",
     "    if False:" + _OFF,
     _T + "test_same_handoff_never_fires_twice"),
    ("the same command with no progress resumes again (loop guard dropped)", RESUME,
     '    if last.get("prompt") == prompt and last.get("fingerprint") == fingerprint:\n',
     "    if False:" + _OFF,
     _T + "test_same_command_no_progress_second_time_waits"),
    ("a fingerprint that cannot be computed counts as progress", RESUME,
     "    if fingerprint is None:\n"
     '        return _decision("wait", "the progress fingerprint could not be computed", prompt, sha)\n',
     "",
     _T + "test_unknown_fingerprint_waits"),
    ("startup is a resume source", RESUME,
     'RESUME_SOURCES = ("clear", "compact")\n',
     'RESUME_SOURCES = ("clear", "compact", "startup")\n',
     _T + "test_startup_never_fires"),
    ("an automatic compact counts as manual", RESUME,
     '    if record.get("trigger") != "manual" or',
     '    if record.get("trigger") not in ("manual", "auto") or',
     _H + "test_auto_compact_waits"),
    ("the prompt is rendered from the raw line (trailing text kept as the argument)", RESUME,
     "    if len(rest) > 1:\n"
     '        return _refuse("extra text after the command")\n'
     '    return {"ok": True, "command": command, "arg": rest[0], "kind": "ticket", "reason": ""}\n',
     '    return {"ok": True, "command": command, "arg": " ".join(rest), "kind": "ticket", "reason": ""}\n',
     _T + "test_trailing_text_refused"),
    ("record_run reports a failed state write as success", RESUME,
     '            return False, f"resume-state.json was not written: {exc.__class__.__name__}"\n',
     '            return True, ""\n',
     _T + "test_record_run_write_failure_reports"),
    ("the context hook emits initialUserMessage", CONTEXT,
     '        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": event,\n'
     '                                                            "additionalContext": text}}) + "\\n")\n',
     '        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": event,\n'
     '                                                            "initialUserMessage": text,\n'
     '                                                            "additionalContext": text}}) + "\\n")\n',
     _H + "test_never_emits_initial_user_message"),
    ("handoff-write.sh stops writing the PreCompact record", WRITE_SH,
     '  printf \'%s\' "$INPUT" | "$CLAIM_PY" "$(dirname "${BASH_SOURCE[0]}")/crew_resume.py" '
     "precompact --root . >/dev/null 2>&1\n",
     "  :\n",
     _H + "test_precompact_manual_compact_may_run"),
    ("handoff-write.ps1 stops writing the PreCompact record", WRITE_PS1,
     "$resumePy = Resolve-CrewPython\n",
     "$resumePy = ''\n",
     _H + "test_precompact_record_same_in_both_flavours"),
    # --- review round 1 ----------------------------------------------------
    # BLOCK: the reviewer's own mutation. An extra line on every UNARMED
    # /clear must fail the whole-output comparison with base f2bb919b.
    ("an unarmed /clear gains an extra line", CONTEXT,
     "        resume_text = resume_line(resume, bool(handoff and handoff.strip()))\n",
     "        resume_text = resume_line(resume, bool(handoff and handoff.strip()))\n"
     '        if resume["action"] == "off" and source in ("clear", "compact"):\n'
     '            items.append({"id": "", "text": "resume off: " + resume["reason"], '
     '"source": {"kind": "resume"}})\n',
     _H + "test_unarmed_output_is_byte_identical_to_base[clear-no-machine-file]"),
    ("an armed startup gains an extra line", CONTEXT,
     "        resume_text = resume_line(resume, bool(handoff and handoff.strip()))\n",
     "        resume_text = resume_line(resume, bool(handoff and handoff.strip()))\n"
     '        if source == "startup":\n'
     '            items.append({"id": "", "text": "resume: startup", "source": {"kind": "resume"}})\n',
     _H + "test_unarmed_output_is_byte_identical_to_base[startup-armed]"),
    ("handoff-write.sh no longer removes the old PreCompact record", WRITE_SH,
     '  rm -f "$PRECOMPACT_DIR/precompact-$PRECOMPACT_KEY.json" 2>/dev/null\n',
     "  :\n",
     _H + "test_a_later_precompact_with_no_python_leaves_no_manual_record[sh]"),
    ("handoff-write.ps1 no longer removes the old PreCompact record", WRITE_PS1,
     '  Remove-Item -LiteralPath (Join-Path $precompactDir "precompact-$precompactKey.json") '
     "-Force -ErrorAction SilentlyContinue\n",
     "  $null = $precompactDir\n",
     _H + "test_a_later_precompact_with_no_python_leaves_no_manual_record[ps1]"),
    ("write_precompact_record keeps the old record when its own write fails", RESUME,
     "    try:\n        os.unlink(path)\n    except FileNotFoundError:\n        pass\n"
     "    except OSError:\n        if not _blank(path):\n            return False\n",
     "",
     _T + "test_precompact_write_removes_the_old_record_even_when_the_new_write_fails"),
    ("a record that cannot be removed is left saying manual", RESUME,
     "    except OSError:\n        if not _blank(path):\n            return False\n",
     "    except OSError:\n        return False\n",
     _T + "test_precompact_record_that_cannot_be_removed_is_blanked_in_place"),
    ("an unreplaceable PreCompact record still counts as manual", RESUME,
     "    if not (os.access(path, os.W_OK) or os.access(os.path.dirname(path), os.W_OK)):\n"
     "        return False\n",
     "",
     _T + "test_precompact_record_nothing_could_replace_is_not_manual"),
    ("write_precompact_record leaves its tmp behind on a failed write", RESUME,
     "    except OSError:\n        try:\n            os.unlink(tmp)\n        except OSError:\n            pass\n"
     "        return False\n    return True\n\n\ndef _blank(path):\n",
     "    except OSError:\n        return False\n    return True\n\n\ndef _blank(path):\n",
     _T + "test_precompact_write_leaves_no_tmp_when_the_replace_fails"),
    ("orphaned precompact .tmp files are never pruned", CONTEXT,
     'name.endswith((".json", ".tmp"))',
     'name.endswith(".json")',
     _T + "test_precompact_tmp_files_older_than_a_day_are_pruned"),
    ("staleness is read only from whether archiving succeeded", CONTEXT,
     '    return archived, archived or bool(result.get("stale"))\n',
     "    return archived, archived\n",
     _H + "test_armed_with_a_stale_handoff_that_cannot_be_archived_waits[sh]"),
    ("a staleness rule that raises reads as fresh", CONTEXT,
     "        result = crew_state.archive_stale_handoff(root, cfg)\n"
     "    except Exception:  # pylint: disable=broad-except\n        return False, True\n",
     "        result = crew_state.archive_stale_handoff(root, cfg)\n"
     "    except Exception:  # pylint: disable=broad-except\n        return False, False\n",
     _H + "test_a_staleness_verdict_that_raises_counts_as_stale"),
    ("the hook drops the staleness verdict before decide", CONTEXT,
     "archived=archived, stale=stale)\n",
     "archived=archived)\n",
     _H + "test_armed_with_a_stale_handoff_that_cannot_be_archived_waits[sh]"),
    ("an unreadable INDEX.md fingerprints as no rows again", RESUME,
     "    except (OSError, ValueError):\n        return None\n    if not ticket:\n",
     '    except (OSError, ValueError):\n        return ""\n    if not ticket:\n',
     _T + "test_unreadable_index_is_an_unknown_not_progress"),
    ("os.walk silently skips a directory it cannot list", RESUME,
     "        for base, dirs, files in os.walk(tdir, onerror=unlisted.append):\n",
     "        for base, dirs, files in os.walk(tdir):\n",
     _T + "test_unlistable_ticket_subdirectory_is_an_unknown_not_progress"),
    ("an opt-in that cannot be confirmed becomes an internal-error wait", CONTEXT,
     "        if not crew_resume.settings(root)[\"armed\"]:\n            return off\n"
     "    except Exception:  # pylint: disable=broad-except\n        return off\n",
     "        if not crew_resume.settings(root)[\"armed\"]:\n            return off\n"
     "    except Exception:  # pylint: disable=broad-except\n"
     '        return {"action": "wait", "prompt": "", "reason": "internal error"}\n',
     _H + "test_an_unconfirmable_opt_in_is_off_not_an_internal_error[settings-raises]"),
    ("stale PreCompact records are never pruned", RESUME,
     "    crew_context.prune_precompact(root)\n",
     "",
     _T + "test_precompact_records_older_than_a_day_are_pruned"),
    ("SessionStart stops pruning stale PreCompact records", CONTEXT,
     "        prune_claims(root)\n        prune_precompact(root)\n",
     "        prune_claims(root)\n",
     _H + "test_session_start_prunes_precompact_records_older_than_a_day"),
    ("handoff-write.sh exits in a crew.json-only repo again", WRITE_SH,
     "[ -f .crew/config.json ] || [ -f .crew/crew.json ] || exit 0\n",
     "[ -f .crew/config.json ] || exit 0\n",
     _H + "test_a_crew_json_only_repo_still_records_a_manual_compact[sh]"),
    ("handoff-write.ps1 exits in a crew.json-only repo again", WRITE_PS1,
     'if (-not (Test-Path ".crew/config.json") -and -not (Test-Path ".crew/crew.json")) { exit 0 }\n',
     'if (-not (Test-Path ".crew/config.json")) { exit 0 }\n',
     _H + "test_a_crew_json_only_repo_still_records_a_manual_compact[ps1]"),
    ("the CLI decide skips the staleness rule", RESUME,
     "                         stale=_is_stale(root, cfg, rel, text))\n",
     "                         stale=False)\n",
     _T + "test_cli_decide_applies_the_staleness_rule"),
    ("a wait with no handoff still says to read the handoff", CONTEXT,
     '        tail = "Read the handoff and continue by hand." if has_handoff else "Continue by hand."\n',
     '        tail = "Read the handoff and continue by hand."\n',
     _H + "test_armed_with_no_handoff_says_why[sh]"),
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
    scratch = args.scratch or tempfile.mkdtemp(prefix="sabotage-resume-")
    os.makedirs(scratch, exist_ok=True)
    ok = True
    for index, (label, target, find, replace, test) in enumerate(RESUME_MUTATIONS):
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
        print(f"{verdict:32} {label}")
    print("\nRESUME SABOTAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
