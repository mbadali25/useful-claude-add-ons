"""The T-0039 mutations: `crew_gitignore.py`, the only crew code that writes a
repo's `.gitignore`, and the `/crew:status` line that prints its summary. Same
tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace,
test) -- and appended to it there. Run `sabotage.py`, not this file.

T-0039 ran these nineteen by hand (`.crew/verify.json`'s T-0039 rule names
them); `sabotage*.py` is harness, so they could not ride with the feature
(T-0087) and are registered here (C-0025). Each is a way the managed block
could cover what git does not ignore, touch a line a human wrote, or report a
state the caller would act on when crew could not tell.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
GITIGNORE = os.path.join(SCRIPTS, "crew_gitignore.py")
STATUS = os.path.join(SCRIPTS, "crew_status.py")
_G = "tests/test_crew_gitignore.py::"

GITIGNORE_MUTATIONS = (
    ("gitignore: every candidate reads as covered", GITIGNORE,
     '            if all(p in covered for p in cand["probes"]):\n',
     "            if True:\n",
     _G + "test_check_reports_missing_and_exits_1"),
    ("gitignore: the user's global excludes file counts as coverage", GITIGNORE,
     '_git(top, "-c", f"core.excludesFile={os.devnull}", "check-ignore", "--no-index",',
     '_git(top, "check-ignore", "--no-index",',
     _G + "test_global_excludes_file_does_not_count_as_covered"),
    ("gitignore: the repo's own git dir (info/exclude) counts as coverage", GITIGNORE,
     'extra_env={"GIT_DIR": gitdir, "GIT_WORK_TREE": top},',
     "extra_env=None,",
     _G + "test_global_excludes_file_does_not_count_as_covered"),
    ("gitignore: apply rewrites a human line (a trailing tab dropped)", GITIGNORE,
     '        return rendered + (newline + text if text else "")\n',
     '        return rendered + (newline + text.replace("\\t", "") if text else "")\n',
     _G + "test_apply_adds_only_inside_the_managed_block"),
    ("gitignore: a new managed block goes at the bottom", GITIGNORE,
     '        return rendered + (newline + text if text else "")\n',
     '        return (text + newline if text else "") + rendered\n',
     _G + "test_apply_adds_only_inside_the_managed_block"),
    ("gitignore: a tracked secret no longer makes the state owner (exit 3)", GITIGNORE,
     '    if result["needs_owner"]:\n        result["state"] = "owner"\n',
     '    if False:\n        result["state"] = "owner"\n',
     _G + "test_tracked_secret_is_needs_owner_exit_3"),
    ("gitignore: check-ignore exit 128 reads as nothing ignored", GITIGNORE,
     "ok=(0, 1), stdin_text=",
     "ok=(0, 1, 128), stdin_text=",
     _G + "test_check_ignore_status_other_than_0_or_1_is_unknown"),
    ("gitignore: a git timeout reads as an empty listing", GITIGNORE,
     "    except subprocess.TimeoutExpired as exc:\n"
     '        raise Unknown(f"git {args[0]} timed out after {TIMEOUT}s") from exc\n',
     "    except subprocess.TimeoutExpired:\n"
     '        return 0, ""\n',
     _G + "test_git_failure_is_unknown_exit_4[timeout]"),
    ("gitignore: apply ignores the active ticket's Touch", GITIGNORE,
     "            refusal = _ticket_refusal(top)\n",
     "            refusal = None\n",
     _G + "test_apply_refuses_inside_a_ticket_whose_touch_lacks_gitignore"),
    ("gitignore: render lets a .crew pattern through", GITIGNORE,
     '    rows = [r for r in rows if not any(_forbidden(p) for p in r["patterns"])]\n',
     "",
     _G + "test_render_refuses_a_crew_pattern_even_if_one_reaches_it"),
    ("gitignore: the table gains a .crew row", GITIGNORE,
     '    rows += [dict(row, lang="secrets") for row in SECRETS]\n    return rows\n',
     '    rows += [dict(row, lang="secrets") for row in SECRETS]\n'
     '    rows += [dict(_row(".crew/", ".crew/x", "crew state", "crew"), lang="os/editor")]\n'
     "    return rows\n",
     _G + "test_never_emits_crew_or_work_patterns"),
    ("gitignore: apply writes .gitignore in place with a truncating open", GITIGNORE,
     '        with open(tmp, "xb") as fh:\n',
     '        with open(path, "wb") as fh:\n',
     _G + "test_write_is_atomic_and_leaves_original_on_failure"),
    ("gitignore: the anchored-directory conflict check is dropped", GITIGNORE,
     '            hit = _under(segs, name.split("/"))\n',
     "            hit = False\n",
     _G + "test_conflict_with_human_negation_is_not_added"),
    ("gitignore: the unanchored-directory conflict check is dropped", GITIGNORE,
     '            hit = any(seg == "**" or _overlap(name, seg) for seg in segs[:-1])\n',
     "            hit = False\n",
     _G + "test_unanchored_directory_conflicts_with_a_negation_inside_it"),
    ("gitignore: a pattern overridden below the block is re-added", GITIGNORE,
     '            elif all(p in in_block for p in cand["patterns"]):\n',
     "            elif False:\n",
     _G + "test_pattern_overridden_below_the_block_is_reported_not_re_added"),
    ("status: the gitignore line is blank when crew_gitignore cannot be imported", STATUS,
     '        return "gitignore unknown (crew_gitignore.py not importable)"\n',
     '        return ""\n',
     "tests/test_status.py::test_status_gitignore_line_unknown_when_git_fails"),
    # Review round 1 of T-0039 added these three. The reconfigure was proved at
    # the time on test_undecodable_tracked_name_still_reports_owner_exit_3;
    # since group review r4 every report line is escaped by `_shown`, so that
    # test stays green without it. The failure line is not escaped, and a test
    # for it (C-0025) now holds the reconfigure.
    ("gitignore: stdout is not reconfigured to replace what it cannot encode", GITIGNORE,
     '            stream.reconfigure(errors="replace")\n',
     "            pass\n",
     _G + "test_an_unencodable_failure_message_is_still_unknown_exit_4"),
    ("gitignore: an OSError reading .gitignore is not converted to unknown", GITIGNORE,
     "    except OSError as exc:\n"
     '        raise Unknown(f"{label} could not be read: {exc}") from exc\n',
     "    except FileNotFoundError as exc:\n"
     '        raise Unknown(f"{label} could not be read: {exc}") from exc\n',
     _G + "test_unreadable_gitignore_is_unknown_exit_4"),
    ("gitignore: the .env.example template negation is misspelt", GITIGNORE,
     '("!.env.example", "!.env.sample",',
     '("!.env.exampel", "!.env.sample",',
     _G + "test_tracked_env_template_is_not_a_secret"),
)
