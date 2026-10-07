"""Mutations for crew_coord.py (T-0030: cross-session claims) -- a module of
its own, same tuple shape as sabotage_scope.py's SCOPE_MUTATIONS
(label, target, find, replace, test), appended to MUTATIONS by sabotage.py,
which sits at `.pylintrc`'s max-module-lines. Run `sabotage.py`, not this file.

The first eight are the spec's Acceptance list, in its order. The next two
cover the retry and the identity-file check, which the list does not name but
which the claim and recovery guarantees rest on. The rest are review round 1's
findings (T-0030-coord--r8XvAI), one per guard branch the fixes added: each
reintroduces the defect the finding reproduced, and names the test that
reproduces it. The next block does the same for review round 2's
(T-0030-coord--81NGuE), plus the three branches its NITs found untested, and
the next for review round 3's (T-0030-coord--fBUyjd): the heartbeat-stale
condition recovery now rests on, the namespace recorded only for a visible
pid, the holder lock keyed by worktree, the upper-cased ticket id, both Azure
DevOps URL forms, and a TTL that is not finite. The last block is review
round 4's (T-0030-coord--DKzIYN): origin read through insteadOf, the Azure
DevOps default-repository form, the key keeping host and full path, the TTL's
upper bound, and the three could-not-tell branches those fixes added (a URL the
key rule refuses, an Azure DevOps URL that fits no form, a get-url that
fails), none of which may fall back to the directory name. The last block is
review round 5's (T-0030-coord--FSkzCU): key parts written so a '.' in a name
never reads as a separator, Azure DevOps names kept distinct (not hyphenated,
not UTF-8-replaced), a local path's own marker, a relative path refused alone
and resolved against the worktree (symlinks too), a failing or empty origin
probe and an unknown main worktree read as could-not-tell, and a TTL bounded
before it is converted to float. The last block is review round 6's
(T-0030-coord--dtqJtS), fixed under the successor plan: a file:// origin read
as the local path it names (and refused for another host), Azure DevOps
markers compared after decoding, local keys keeping case and `.git`, git's own
suffix order, a network URL with no host, a failed push-config probe, and the
fake ssh never starting a `#!` script (a mutation of the test module itself).
The last block is review round 7's (T-0030-coord--0BhHm8): a `#!` program
handed to the fake ssh (the scanner's own failing control), a local segment
such as `.git` keyed rather than refused while one that is not UTF-8 is still
refused, the on-disk case on a case-insensitive volume and its unlistable
branch, a `~` origin expanded before it is joined onto the worktree, and a
local key over 128 characters refused (the temp-path tests skip there).

T-0030's feature half landed through rush G0 with reworked recovery and
identity code; this table came back with the 1.2.0 harness lane (H2a): four
anchors moved to the reworked lines (a stale claim, the PID check, the
holder's identity, the local-origin resolve) and one entry was retired (see
its comment below).
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COORD = os.path.join(CREW, "hooks", "scripts", "crew_coord.py")
_T = "tests/test_crew_coord.py::"
TEST_MODULE = os.path.join(CREW, "tests", "test_crew_coord.py")

COORD_MUTATIONS = (
    ("crew_coord pushes with --force-with-lease", COORD,
     '        return ["push", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     '        return ["push", "--force-with-lease", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     _T + "test_push_argv_never_forces"),
    # A stale claim still refuses a new claim (as held, not owner unknown), so
    # the label names the classification the mutation changes.
    ("crew_coord reads a stale working claim as a live holder", COORD,
     '    return claim["state"] == "working" and (age is None or age > ttl_minutes * 60)\n',
     "    return False\n",
     _T + "test_stale_working_claim_reads_owner_unknown_and_blocks_claim"),
    ("crew_coord status skips a corrupt claim", COORD,
     ("        if claim is None:\n"
      '            lines.append(f"{safe(key)} unknown (corrupt claim file: {why}) [peer-written]")\n'
      "            code = EXIT_UNKNOWN\n"),
     ("        if claim is None:\n"
      "            continue\n"),
     _T + "test_corrupt_claim_reads_unknown_not_skipped[{not json]"),
    ("crew_coord accepts a claim when the fetch failed", COORD,
     ('            if state == "failed":\n'
      '                return Result("unknown", f"unknown - could not fetch'),
     ("            if False:\n"
      '                return Result("unknown", f"unknown - could not fetch'),
     _T + "test_claim_when_fetch_failed_is_refused_unknown"),
    ("crew_coord lets a non-holder release", COORD,
     ('        if not same_holder(claim["holder"], me):\n'
      '            return "refused", peer(f"refused: only the holder may'),
     ("        if False:\n"
      '            return "refused", peer(f"refused: only the holder may'),
     _T + "test_release_done_heartbeat_by_non_holder_refused[release]"),
    ("crew_coord adopts a claim from another machine", COORD,
     '    if old["machine"] != machine():\n',
     "    if False:\n",
     _T + "test_recover_refuses_other_machine"),
    ("crew_coord adopts while the old PID is alive", COORD,
     ('    if probe.state == "alive":\n'
      '        return False, f"pid {pid} is alive, so the old session may still be running"\n'),
     ('    if probe.state == "alive":\n'
      '        probe = PidProbe("gone", probe.start, probe.measured)\n'),
     _T + "test_recover_refuses_live_pid"),
    ("crew_coord reads an unreadable PID check as dead", COORD,
     '    if probe.state == "gone" and probe.measured:\n',
     '    if probe.state != "alive":\n',
     _T + "test_recover_refuses_when_pid_check_cannot_tell"),
    ("crew_coord gives up on the first rejected push", COORD,
     "        for _ in range(1 + MAX_RETRIES):\n",
     "        for _ in range(1):\n",
     _T + "test_two_sessions_claim_different_tickets_concurrently"),
    ("crew_coord recovers without the identity file naming the holder", COORD,
     "    if not named:\n",
     "    if False:\n",
     _T + "test_recover_refuses_identity_file_naming_another_holder"),
    # --- review round 1 ---
    ("crew_coord reads a live pid whose /proc is unreadable as gone", COORD,
     ('        # hidepid hiding another user -- cannot tell: ALIVE, never gone.\n'
      '        return PidProbe("alive", None, True)\n'),
     ('        # hidepid hiding another user -- cannot tell: ALIVE, never gone.\n'
      '        return PidProbe("gone", None, True)\n'),
     _T + "test_linux_probe_live_pid_with_unreadable_proc_reads_alive"),
    ("crew_coord reads another user's pid as gone", COORD,
     "    except PermissionError:\n        pass\n",
     '    except PermissionError:\n        return PidProbe("gone", None, True)\n',
     _T + "test_linux_probe_another_users_pid_with_unreadable_proc_reads_alive"),
    ("crew_coord's fetch writes FETCH_HEAD", COORD,
     '"--no-write-fetch-head", ',
     "",
     _T + "test_fetch_writes_no_fetch_head"),
    ("crew_coord pushes to the remote's name (writes a tracking ref)", COORD,
     '        return ["push", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     '        return ["push", "--no-verify", "--", self.remote, f"{sha}:{self.ref}"]\n',
     _T + "test_commands_write_no_remote_tracking_ref"),
    ("crew_coord pushes to the URL, putting it in argv", COORD,
     "            pushed = run_git(self.root, self.push_argv(sha), env=push_env)\n",
     ('            pushed = run_git(self.root, ["push", "--no-verify", "--", push_env[max(\n'
      '                k for k in push_env if k.startswith("GIT_CONFIG_VALUE_"))], f"{sha}:{self.ref}"])\n'),
     _T + "test_push_argv_never_carries_the_remote_url"),
    ("crew_coord pushes into a configured remote of the same name", COORD,
     "        if remotes.code != 0 or PUSH_REMOTE in remotes.out.decode(\"utf-8\", \"replace\").split():\n",
     "        if remotes.code != 0:\n",
     _T + "test_push_refuses_when_the_push_remote_name_is_taken"),
    ("crew_coord drops the remote's receivepack from its push remote", COORD,
     '_PUSH_REMOTE_KEYS = ("url", "pushurl", "proxy", "proxyAuthMethod", "receivepack", "vcs")\n',
     '_PUSH_REMOTE_KEYS = ("url", "pushurl", "proxy", "proxyAuthMethod", "vcs")\n',
     _T + "test_push_carries_the_remotes_receivepack_but_never_mirror"),
    ("crew_coord copies the remote's mirror setting", COORD,
     '_PUSH_REMOTE_KEYS = ("url", "pushurl", "proxy", "proxyAuthMethod", "receivepack", "vcs")\n',
     '_PUSH_REMOTE_KEYS = ("url", "pushurl", "proxy", "proxyAuthMethod", "receivepack", "vcs", "mirror")\n',
     _T + "test_push_carries_the_remotes_receivepack_but_never_mirror"),
    ("crew_coord overwrites the caller's GIT_CONFIG entries", COORD,
     "        first = int(base) if base.isdigit() else 0\n",
     "        first = 0\n",
     _T + "test_push_keeps_a_callers_git_config_environment"),
    ("crew_coord's push runs the pre-push hook", COORD,
     '        return ["push", "--no-verify", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     '        return ["push", "--", PUSH_REMOTE, f"{sha}:{self.ref}"]\n',
     _T + "test_push_runs_no_pre_push_hook[hooks-dir]"),
    ("crew_coord pushes to a remote with several push URLs", COORD,
     "        if listed.code != 0 or len(urls) != 1:\n",
     "        if listed.code != 0 or not urls:\n",
     _T + "test_push_refuses_a_remote_with_several_push_urls"),
    ("crew_coord launches the heartbeat without --pid", COORD,
     '            "--pid", str(me["pid"]), "--interval", str(interval)]\n',
     '            "--interval", str(interval)]\n',
     _T + "test_claim_launches_the_heartbeat_with_its_pid_and_interval"),
    ("crew_coord hands the heartbeat the full environment", COORD,
     "env=child_env(), close_fds=True",
     "env=dict(os.environ), close_fds=True",
     _T + "test_heartbeat_launch_drops_the_token_even_when_the_process_holds_it"),
    ("crew_coord launches the heartbeat in the caller's session", COORD,
     '{"start_new_session": True} if os.name != "nt"',
     '{"start_new_session": False} if os.name != "nt"',
     _T + "test_claim_launches_the_heartbeat_detached_without_the_token"),
    ("crew_coord hands git the full environment", COORD,
     "    full_env = child_env()\n",
     "    full_env = dict(os.environ)\n",
     _T + "test_run_git_drops_the_messaging_token_on_its_own"),
    ("crew_coord keeps the token in its own environment", COORD,
     "        os.environ.pop(name, None)\n",
     "        pass\n",
     _T + "test_git_children_never_receive_the_messaging_token"),
    ("crew_coord prints URL credentials from git's stderr", COORD,
     '    return safe(_URL_CREDENTIALS_RE.sub(r"\\1***@", lines[-1])) if lines else "no message"\n',
     '    return safe(lines[-1]) if lines else "no message"\n',
     _T + "test_git_error_output_has_url_credentials_redacted"),
    ("crew_coord strips only C0/C1 from peer text", COORD,
     '    text = "".join("?" if unicodedata.category(ch) in _UNSAFE_CATEGORIES else ch for ch in str(value))\n',
     '    text = re.sub(r"[\\x00-\\x1f\\x7f-\\x9f]", "?", str(value))\n',
     _T + "test_peer_text_cannot_forge_an_unlabelled_line[U+2028]"),
    ("crew_coord's held refusal is unlabelled", COORD,
     '    return Result("refused", peer(f"refused: {key} is held working by {describe(claim)}"))\n',
     '    return Result("refused", f"refused: {key} is held working by {describe(claim)}")\n',
     _T + "test_refusals_label_peer_written_holder_fields[claim]"),
    ("crew_coord's recover refusal is unlabelled", COORD,
     '            return "refused", peer(f"{key} {body}")\n',
     '            return "refused", f"{key} {body}"\n',
     _T + "test_refusals_label_peer_written_holder_fields[recover]"),
    ("crew_coord rewrites the identity file without its lock", COORD,
     '        with _locked(path + ".lock"):\n',
     "        with contextlib.nullcontext():\n",
     _T + "test_identity_update_holds_the_lock_across_read_and_write"),
    ("crew_coord rewrites other channel files as 100644", COORD,
     "            return known[2], known[1]\n",
     '            return "100644", known[1]\n',
     _T + "test_other_files_on_the_channel_keep_their_mode"),
    ("crew_coord re-splits the recovered key", COORD,
     ('        _maybe_start_heartbeat(chan, top, key, repo, ticket, me, ttl, args)\n'
      '    if outcome.get("mine"):\n'),
     ('        repo, _, ticket = key.partition("__")\n'
      '        _maybe_start_heartbeat(chan, top, key, repo, ticket, me, ttl, args)\n'
      '    if outcome.get("mine"):\n'),
     _T + "test_recover_passes_the_parsed_ticket_to_the_heartbeat"),
    ("crew_coord skips the identity on an ambiguous adopt", COORD,
     '    if result.status == "ok" or outcome.get("mine"):\n',
     '    if result.status == "ok":\n',
     _T + "test_recover_retry_that_finds_itself_holding_records_the_identity"),
    ("crew_coord accepts a shared heartbeat directory", COORD,
     "    if uid is not None and (info.st_uid != uid or info.st_mode & 0o077):\n",
     "    if False:\n",
     _T + "test_heartbeat_refuses_a_shared_or_loose_directory[511]"),
    ("crew_coord follows a symlink at the heartbeat log", COORD,
     '    return os.open(path, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)\n',
     "    return os.open(path, flags | os.O_CREAT, 0o600)\n",
     _T + "test_heartbeat_log_never_follows_a_planted_symlink"),
    ("crew_coord opens the heartbeat log world-readable", COORD,
     '    return os.open(path, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)\n',
     '    return os.open(path, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)\n',
     _T + "test_heartbeat_log_is_private_to_this_user"),
    ("crew_coord runs a second heartbeat loop for one claim", COORD,
     "            _lock_fd(lock, wait=False)\n",
     "            pass\n",
     _T + "test_a_second_heartbeat_loop_for_the_same_claim_exits"),
    ("crew_coord reads any OpenProcess error as gone on Windows", COORD,
     "            if last_error() == _ERROR_INVALID_PARAMETER:\n",
     "            if True:\n",
     _T + "test_windows_probe_reads_the_measured_answers[err5-alive]"),
    ("crew_coord reads an unexpected OpenProcess error as gone", COORD,
     '            return PidProbe("alive", None, True)  # any other OpenProcess error cannot tell\n',
     '            return PidProbe("gone", None, True)  # any other OpenProcess error cannot tell\n',
     _T + "test_windows_probe_reads_the_measured_answers[err6-alive]"),
    ("crew_coord reads an opened Windows handle as gone", COORD,
     '            return PidProbe("alive", str(created) if created else None, True)\n',
     '            return PidProbe("gone", None, True)\n',
     _T + "test_windows_probe_reads_the_measured_answers[running-alive]"),
    ("crew_coord ignores the Windows exit FILETIME", COORD,
     "            if exited:\n",
     "            if False:\n",
     _T + "test_windows_probe_reads_the_measured_answers[exit-filetime-gone]"),
    ("crew_coord reads a failed GetProcessTimes as gone", COORD,
     ('                return PidProbe("alive", None, True)\n'
      "            created, exited = "),
     ('                return PidProbe("gone", None, True)\n'
      "            created, exited = "),
     _T + "test_windows_probe_reads_the_measured_answers[times-fail-alive]"),
    ("crew_coord ignores a reused pid's start time", COORD,
     '    if probe.state == "alive" and old.get("pid_start") and probe.start and probe.start != old["pid_start"]:\n',
     "    if False:\n",
     _T + "test_recover_on_windows_refuses_a_reused_pid"),
    # --- review round 2 ---
    ("crew_coord ignores the pid namespace", COORD,
     '        if here is None or here != holder.get("pidns"):\n',
     "        if False:\n",
     _T + "test_recover_refuses_a_gone_pid_whose_namespace_cannot_be_matched[differs]"),
    ("crew_coord reads an unreadable pid namespace as a match", COORD,
     '        if here is None or here != holder.get("pidns"):\n',
     '        if here is not None and here != holder.get("pidns"):\n',
     _T + "test_recover_refuses_a_gone_pid_whose_namespace_cannot_be_matched[unreadable-here]"),
    ("crew_coord keys the heartbeat lock without the holder", COORD,
     'heartbeat_path(chan.channel, key, f"-{holder_tag(me)}.lock")',
     'heartbeat_path(chan.channel, key, ".lock")',
     _T + "test_heartbeat_loop_of_a_new_holder_runs_while_the_old_holders_loop_sleeps"),
    ("crew_coord compares holders by session id only", COORD,
     "    if not (a and b):\n        return False\n",
     '    if not (a and b):\n        return False\n    return a["session"] == b["session"]\n',
     _T + "test_claim_by_the_same_session_from_another_live_process_is_refused[other-worktree]"),
    ("crew_coord ignores the pid in a holder's identity", COORD,
     ('    if a.get("pid") is None or b.get("pid") is None:\n'
      "        return False  # an unknown pid cannot establish identity: two processes would match\n"
      '    if (a["session"], a["machine"], a.get("pid")) != (b["session"], b["machine"], b.get("pid")):\n'
      "        return False\n"
      '    if os.path.normcase(a["worktree"]) != os.path.normcase(b["worktree"]):\n'
      "        return False\n"
      '    if bool(a.get("pid_start")) != bool(b.get("pid_start")):\n'
      "        return False  # one side's start time unknown: a reused pid cannot be told apart\n"
      '    return not (a.get("pid_start") and a["pid_start"] != b["pid_start"])\n'),
     ('    if (a["session"], a["machine"]) != (b["session"], b["machine"]):\n'
      "        return False\n"
      '    return os.path.normcase(a["worktree"]) == os.path.normcase(b["worktree"])\n'),
     _T + "test_claim_by_the_same_session_from_another_live_process_is_refused[same-worktree]"),
    ("crew_coord reads a one-sided start time as the same holder", COORD,
     ('    if bool(a.get("pid_start")) != bool(b.get("pid_start")):\n'
      "        return False  # one side's start time unknown: a reused pid cannot be told apart\n"
      '    return not (a.get("pid_start") and a["pid_start"] != b["pid_start"])\n'),
     '    return not (a.get("pid_start") and b.get("pid_start") and a["pid_start"] != b["pid_start"])\n',
     _T + "test_an_unknown_pid_or_start_time_is_not_the_same_holder"),
    ("crew_coord matches ls-remote by tail", COORD,
     "        tips = [row[0] for row in rows if len(row) == 2 and row[1] == self.ref]\n",
     "        tips = [row[0] for row in rows if len(row) == 2 and row[1].endswith(self.ref)][:1]\n",
     _T + "test_fetch_ignores_a_ref_that_only_ends_with_the_channel_ref"),
    ("crew_coord drops safe() on the recommended command", COORD,
     "    ticket = f\"{_command_part(claim['repo'], _REPO_RE)}:{_command_part(claim['ticket'], _PART_RE)}\"\n",
     "    ticket = f\"{claim['repo']}:{claim['ticket']}\"\n",
     _T + "test_recommended_command_withholds_unsafe_peer_values[shell]"),
    ("crew_coord takes the repo half per worktree", COORD,
     "        return name, None\n",
     "        return os.path.basename(top).lower(), None\n",
     _T + "test_two_worktrees_of_one_repo_share_the_claim_key"),
    ("crew_coord takes a given repo half as free text", COORD,
     "    if given is not None and given.lower() != repo:\n",
     "    if False:\n",
     _T + "test_ticket_repo_half_must_be_this_repositorys[uca:T-1-2]"),
    ("crew_coord skips the working claim's holder check", COORD,
     ('        if not _valid_holder(claim.get("holder")):\n'
      '            return None, "a working claim with no valid holder"\n'),
     "",
     _T + "test_corrupt_claim_reads_unknown_not_skipped[bad-holder]"),
    ("crew_coord's owner signal ignores CLAUDECODE", COORD,
     '    return "CLAUDECODE" not in os.environ and "CLAUDE_CODE_SESSION_ID" not in os.environ\n',
     '    return "CLAUDE_CODE_SESSION_ID" not in os.environ\n',
     _T + "test_break_is_refused_when_either_half_of_the_owner_signal_is_present[CLAUDECODE]"),
    ("crew_coord's owner signal ignores CLAUDE_CODE_SESSION_ID", COORD,
     '    return "CLAUDECODE" not in os.environ and "CLAUDE_CODE_SESSION_ID" not in os.environ\n',
     '    return "CLAUDECODE" not in os.environ\n',
     _T + "test_break_is_refused_when_either_half_of_the_owner_signal_is_present[CLAUDE_CODE_SESSION_ID]"),
    ("crew_coord's heartbeat ignores a reused pid", COORD,
     '        if probe.state == "gone" or (first.start and probe.start and probe.start != first.start):\n',
     '        if probe.state == "gone":\n',
     _T + "test_heartbeat_loop_exits_when_the_watched_pid_is_reused"),
    # --- review round 3 ---
    # Retired (H2a, C-0047's rule: a mutation whose rule was removed goes, with
    # the reason, never re-anchored onto a neighbour): "crew_coord adopts a
    # claim whose heartbeat is fresh". G0's reworked recovery adopts only on a
    # pid MEASURED gone, whatever the heartbeat
    # (test_recover_adopts_a_fresh_heartbeat_whose_pid_is_provably_gone), so
    # `is_stale` in `assess_recovery` now picks the refusal's wording and guards
    # nothing; its test is gone from test_crew_coord.py with the rule.
    ("crew_coord records the pid namespace when CLAUDE_PID is invisible", COORD,
     '    if probe_pid(pid).state != "alive":\n        return None\n    return pid_namespace()\n',
     "    return pid_namespace()\n",
     _T + "test_recover_refuses_a_stale_claim_whose_pid_was_invisible_at_claim_time"),
    ("crew_coord keys the heartbeat lock without the worktree", COORD,
     '    ident = [holder["session"], holder["machine"], os.path.normcase(holder["worktree"]), holder.get("pid"),\n',
     '    ident = [holder["session"], holder["machine"], holder.get("pid"),\n',
     _T + "test_heartbeat_loop_of_the_same_session_and_pid_in_another_worktree_is_not_stopped_by_the_old_loop"),
    ("crew_coord keeps the ticket id's case", COORD,
     "    ticket = ticket.upper()\n",
     "",
     _T + "test_ticket_id_is_one_key_whatever_its_case[t-0030]"),
    ("crew_coord reads Azure DevOps https's _git as the owner", COORD,
     '        if len(low) == 4 and low[2] == "_git":\n',
     "        if False:\n",
     _T + "test_azure_devops_https_and_ssh_clones_share_the_claim_key"),
    ("crew_coord reads Azure DevOps ssh v3 raw", COORD,
     '        return tuple(segments[1:]) if len(low) == 4 and low[0] == "v3" else None\n',
     "        return None\n",
     _T + "test_repo_key_is_one_for_every_azure_devops_form[ssh-encoded-space]"),
    ("crew_coord keeps an Azure DevOps name percent-encoded", COORD,
     '        return urllib.parse.unquote_to_bytes(part).decode("utf-8").lower()\n',
     '        return part.lower()\n',
     _T + "test_repo_key_is_one_for_every_azure_devops_form[https-encoded-space]"),
    ("crew_coord accepts a TTL that is not finite", COORD,
     "            or value <= 0 or value > MAX_TTL_MINUTES or not math.isfinite(value)):\n",
     "            or value <= 0 or value > MAX_TTL_MINUTES):\n",
     _T + "test_ttl_outside_0_to_10080_is_a_config_error_before_any_fetch[NaN]"),
    # --- review round 4 ---
    ("crew_coord reads remote.origin.url raw", COORD,
     '        got = run_git(top, ["remote", "get-url", "origin"])\n',
     '        got = run_git(top, ["config", "--get", "remote.origin.url"])\n',
     _T + "test_claim_applies_insteadof_to_origin"),
    ("crew_coord takes the segment before _git as the project of <org>/_git/<repo>", COORD,
     "            return segments[0], segments[2], segments[2]\n",
     "            return segments[0], segments[0], segments[2]\n",
     _T + "test_every_azure_devops_form_of_a_default_repository_is_one_claim"),
    ("crew_coord keys by the last two path segments", COORD,
     "        parts = [_key_part(p.lower()) for p in [host] + segments]\n",
     "        parts = [_key_part(p.lower()) for p in segments[-2:]]\n",
     _T + "test_repo_key_tells_different_repositories_apart[gitlab-groups]"),
    ("crew_coord drops the ttlMinutes upper bound", COORD,
     "            or value <= 0 or value > MAX_TTL_MINUTES or not math.isfinite(value)):\n",
     "            or value <= 0 or not math.isfinite(value)):\n",
     _T + "test_ttl_outside_0_to_10080_is_a_config_error_before_any_fetch[10081]"),
    ("crew_coord falls back to the directory name for an origin it cannot tell", COORD,
     '            raise UnknownKey(f"cannot derive this repository\'s key: {why}; nothing was read or written")\n',
     "            return _fallback_repo(top), why\n",
     _T + "test_claim_is_could_not_tell_and_never_the_directory_name_for_an_unusable_origin[encoded]"),
    ("crew_coord reads an Azure DevOps URL that fits no form generically", COORD,
     ('            return None, f"origin\'s URL has the shape {_url_shape(host, segments)}, '
      'which fits no Azure DevOps form"\n'),
     "            found = segments\n",
     _T + "test_claim_is_could_not_tell_and_never_the_directory_name_for_an_unusable_origin[azure-short-v3]"),
    ("crew_coord falls back when git cannot resolve origin", COORD,
     '            raise UnknownKey(f"cannot derive this repository\'s key: `git remote get-url origin` failed: "\n'
     '                             f"{_last_line(got.err)}")\n',
     "            return _fallback_repo(top), None\n",
     _T + "test_claim_is_could_not_tell_when_git_cannot_resolve_origin"),
    ("crew_coord keys a URL with no path by its host", COORD,
     "    if not segments:\n",
     "    if False:\n",
     _T + "test_repo_key_is_could_not_tell_for_a_segment_the_key_rule_refuses[no-path]"),
    # --- review round 5 ---
    ("crew_coord joins key parts that may hold '.' unescaped", COORD,
     '    return "".join(chr(b) if chr(b) in _KEY_LITERAL else f"_{b:02x}" for b in text.encode("utf-8"))\n',
     '    return "".join(chr(b) if chr(b) in _KEY_LITERAL | {".", "_"} else f"_{b:02x}" '
     'for b in text.encode("utf-8"))\n',
     _T + "test_a_claim_in_one_repository_never_blocks_a_ticket_in_another[dot-join]"),
    ("crew_coord normalises an Azure DevOps name to hyphens", COORD,
     '        return urllib.parse.unquote_to_bytes(part).decode("utf-8").lower()\n',
     '        return re.sub(r"[^a-z0-9]+", "-", urllib.parse.unquote(part).lower()).strip("-")\n',
     _T + "test_a_claim_in_one_repository_never_blocks_a_ticket_in_another[azure-normalised]"),
    ("crew_coord replaces an Azure DevOps name that is not UTF-8", COORD,
     '        return urllib.parse.unquote_to_bytes(part).decode("utf-8").lower()\n',
     '        return urllib.parse.unquote_to_bytes(part).decode("utf-8", "replace").lower()\n',
     _T + "test_repo_key_is_could_not_tell_for_a_segment_the_key_rule_refuses[azure-not-utf-8]"),
    ("crew_coord keys a local path like a host", COORD,
     "        parts = [_LOCAL_MARK] + [_key_part(p) for p in segments]\n",
     "        parts = [_key_part(p) for p in segments]\n",
     _T + "test_repo_key_tells_different_repositories_apart[local-path-named-like-a-host]"),
    ("crew_coord keys a relative path as it is", COORD,
     "    if local is not None and not _ABSOLUTE_RE.match(local):\n",
     "    if False:\n",
     _T + "test_a_relative_path_alone_is_could_not_tell"),
    ("crew_coord never resolves a local origin against the worktree", COORD,
     '        name, why = owner_name(_resolved(got.out.decode("utf-8", "replace").rstrip("\\r\\n"), top))\n',
     '        name, why = owner_name(got.out.decode("utf-8", "replace").rstrip("\\r\\n"))\n',
     _T + "test_every_spelling_of_a_local_origin_is_one_claim[relative]"),
    ("crew_coord leaves a local origin's symlinks unresolved", COORD,
     "    return _on_disk_case(os.path.realpath(_git_opens(",
     "    return _on_disk_case(os.path.abspath(_git_opens(",
     _T + "test_every_spelling_of_a_local_origin_is_one_claim[symlink]"),
    ("crew_coord reads a failed origin probe as no origin", COORD,
     "    if has_url.code != 1 or has_url.out.strip():\n",
     "    if False:\n",
     _T + "test_claim_is_could_not_tell_when_the_origin_probe_fails[128]"),
    ("crew_coord reads an empty origin URL as a path", COORD,
     "        if not has_url.out.strip():\n",
     "        if False:\n",
     _T + "test_claim_is_could_not_tell_for_an_origin_with_an_empty_url"),
    ("crew_coord names the worktree when git cannot name the main one", COORD,
     "    if not common:\n",
     "    common = common or top\n    if not common:\n",
     _T + "test_the_directory_fallback_is_could_not_tell_when_git_cannot_name_the_main_worktree"),
    ("crew_coord converts an oversized TTL to float before bounding it", COORD,
     "            or value <= 0 or value > MAX_TTL_MINUTES or not math.isfinite(value)):\n",
     "            or not math.isfinite(value) or value <= 0 or value > MAX_TTL_MINUTES):\n",
     _T + "test_ttl_outside_0_to_10080_is_a_config_error_before_any_fetch[10**400]"),
    # --- review round 6 (successor plan) ---
    ("crew_coord leaves a file:// origin unresolved", COORD,
     "    local, _ = _local_path(url)\n",
     '    local, _ = _local_path(url) if not url.lower().startswith("file:") else (None, None)\n',
     _T + "test_a_file_url_and_a_plain_path_to_one_remote_are_one_claim"),
    ("crew_coord reads a file:// URL on another host as a local path", COORD,
     '        if authority.lower() not in ("", "localhost"):\n',
     "        if False:\n",
     _T + "test_a_file_url_that_names_no_local_path_is_could_not_tell[remote-host]"),
    ("crew_coord compares Azure DevOps markers before decoding", COORD,
     "    low = [_azure_part(s) for s in segments]\n",
     "    low = [s.lower() for s in segments]\n",
     _T + "test_an_encoded_azure_devops_marker_is_one_claim[default-collection]"),
    ("crew_coord reads an undecodable Azure DevOps segment as a form mismatch", COORD,
     "        if None in [_azure_part(s) for s in segments]:\n",
     "        if False:\n",
     _T + "test_an_azure_devops_segment_that_does_not_decode_is_could_not_tell[marker-position]"),
    ("crew_coord lowercases a local key again", COORD,
     "        parts = [_LOCAL_MARK] + [_key_part(p) for p in segments]\n",
     "        parts = [_LOCAL_MARK] + [_key_part(p.lower()) for p in segments]\n",
     _T + "test_two_local_repositories_never_share_a_claim[case]"),
    ("crew_coord strips .git from a local key again", COORD,
     "        parts = [_LOCAL_MARK] + [_key_part(p) for p in segments]\n",
     "        parts = [_LOCAL_MARK] + [_key_part(re.sub(r\"\\.git$\", \"\", p)) for p in segments]\n",
     _T + "test_two_local_repositories_never_share_a_claim[dot-git]"),
    ("crew_coord keys a local path without git's suffix order", COORD,
     "    return _on_disk_case(os.path.realpath(_git_opens(os.path.join(top, os.path.expanduser(local)))))\n",
     "    return _on_disk_case(os.path.realpath(os.path.join(top, os.path.expanduser(local))))\n",
     _T + "test_git_itself_opens_the_suffix_the_key_resolves"),
    ("crew_coord reads a network URL with no host as a local path", COORD,
     "    if local is None and not host:\n",
     "    if False:\n",
     _T + "test_a_claim_under_a_network_origin_with_no_host_is_could_not_tell[https]"),
    ("crew_coord reads a failed push-config probe as the key absent", COORD,
     "            if got.code not in (0, 1):\n",
     "            if False:\n",
     _T + "test_a_failed_pushurl_probe_is_unknown_and_nothing_is_pushed[128]"),
    ("the fake ssh starts a receivepack script directly", TEST_MODULE,
     'elif program.endswith(".py"):\n',
     "elif False:\n",
     _T + "test_push_carries_the_remotes_receivepack_but_never_mirror"),
    # --- review round 7 (T-0030-coord--0BhHm8) ---
    ("a fixture hands the fake ssh a #! receivepack script", TEST_MODULE,
     '    wrapper.write_text("import pathlib, subprocess, sys\\n"\n',
     '    wrapper.write_text("#!/bin/sh\\n" "import pathlib, subprocess, sys\\n"\n',
     _T + "test_no_fixture_hands_the_fake_ssh_a_shebang_script"),
    ("crew_coord refuses a local segment the host rule refuses", COORD,
     "        if not all(_utf8(p) for p in segments):\n",
     "        if not all(_utf8(p) and _valid_part(p.lower(), _OWNER_NAME_PART_RE) for p in segments):\n",
     _T + "test_a_clone_of_a_non_bare_local_repository_can_claim"),
    ("crew_coord keys a local segment git decoded with replacement", COORD,
     '    if "\\ufffd" in name:\n        return False\n',
     "",
     _T + "test_a_local_segment_that_is_not_utf8_is_could_not_tell[replaced]"),
    ("crew_coord keeps a local path's case as typed", COORD,
     "        current = os.path.join(current, _listed_name(current, part))\n",
     "        current = os.path.join(current, part)\n",
     _T + "test_two_case_spellings_on_a_case_insensitive_volume_are_one_claim"),
    ("crew_coord keeps the typed case when the directory cannot be listed", COORD,
     "        names = None\n",
     "        return part\n",
     _T + "test_an_unlistable_directory_where_case_does_not_matter_is_could_not_tell"),
    ("crew_coord joins a ~ origin onto each worktree", COORD,
     "os.path.join(top, os.path.expanduser(local))",
     "os.path.join(top, local)",
     _T + "test_a_tilde_origin_is_one_claim_from_every_worktree"),
    ("crew_coord keys a local path whose key passes 128 characters", COORD,
     "    if not _valid_part(key, _REPO_RE):\n",
     "    if not _valid_part(key[:128], _REPO_RE):\n",
     _T + "test_a_local_key_over_128_characters_is_could_not_tell"),
)
