# L-0792 direction
Type: bug (test hermeticity), follow-up to L-0790. Priority: medium. Status: direction.
Filed by the L-0790 lane, 2026-10-11. L-0790 (PR for ai-connect 0.1.5) fixed sweep finding S1 only
(`plugin/ai-connect/tests/test_ops_firewall.py`); the lead scoped S2, S3 and S4 out. None of the three reaches a
real tool today; each is safe by per-test care or by accident, not by construction.

## FIRST ITEM (added 2026-10-11 15:00 CDT): L-0790's crew:security pass 2 - 1 FIX and 2 NIT, carried here

Owner decision, Matthew, 2026-10-11, through AskUserQuestion, relayed by the lead and then by the coordinator to the
L-0790 lane (which did not see the answer first-hand): #605 merges as reviewed at ee9b9c2c1 with no change to the
head, and security pass 2's FIX and both NITs go verbatim into this ticket as its first item, with the corrected
command.

The pass: crew:security subagent, model claude-opus-5-5, same family as the author (Claude), on ee9b9c2c1, read-only,
nothing executed. Verdict: FINDINGS - 0 BLOCK, 1 FIX, 2 NIT. The rows below are copied from
`.work/tickets/L-0790/security.md` ("Pass 2"), where the reviewer's text is shortened with its meaning kept.

| # | Sev | Where (at ee9b9c2c1) | Finding (shortened, meaning kept) |
| --- | --- | --- | --- |
| 1 | FIX | plugin/ai-connect/CHANGELOG.md:13 (pointed to by CHANGELOG.md:26-27) | The remediation command gives a false negative for the incident's own state: the root entry says the rule was stored "while ufw was inactive", and the plugin entry tells readers to check with `sudo ufw status`, which on an inactive ufw prints only `Status: inactive` and lists no rules (ufw 0.36.2 backend_iptables.py:262-277, read not run). A reader concludes clean and the stored allow goes live at the next `ufw enable`. Suggested: `sudo ufw show added`, or `grep -n 9999 /etc/ufw/user.rules /etc/ufw/user6.rules`, and say `ufw status` shows nothing when inactive. Measured for the text and the ufw source; inferred for runtime behaviour and for `ufw show added`. |
| 2 | NIT | test_ops_firewall.py:18, CHANGELOG.md:21-22, plugin/ai-connect/CHANGELOG.md:8 | "Every child first checks..." is overstated: the seven fake-sudo cases call run_bash without hermetic_preamble (:726, :740, :751), and must, since the preamble would refuse their canary ufw. No reach: their PATH (:715) is bin_dir, host_bin and the child_env PATH, all under tmp_path. Suggested: "every child that runs configure_firewall", or assert each PATH entry is under tmp_path in the helper. |
| 3 | NIT | test_ops_firewall.py:281-290 | The extraction guards cover identity spellings only: a second `configure_firewall() {` definition in install.sh, or a body that calls `/usr/sbin/ufw` or sets `PATH=`, would get past them. Not reachable with install.sh as it is; a real reach only for root with ALLOW_ROOT=1 and only for a call made without sudo. Suggested: assert one definition, no `PATH=`, no command word starting with `/`. Inferred. |

What to do for row 1, the one that matters to people who ran the suite before 0.1.5: in
`plugin/ai-connect/CHANGELOG.md`'s "If you ran the suite before 0.1.5" bullet, replace `sudo ufw status` with the
corrected command, `sudo ufw show added`, or `grep -n 9999 /etc/ufw/user.rules /etc/ufw/user6.rules`, and say that
`ufw status` lists nothing while ufw is inactive. The runtime behaviour was INFERRED from reading ufw's source, not
run: before writing the new sentence, confirm on a host what `ufw status` and `ufw show added` print for an inactive
ufw with a stored rule (read-only commands; no state change). Until this lands, ai-connect 0.1.5's changelog carries
the weaker instruction.

## The findings, quoted from .work/tickets/L-0790/direction.md ("Sweep", read on main a192c68e)

| # | Where | What it can reach | State |
| --- | --- | --- | --- |
| S2 | `plugin/ai-connect/vpn/tests/conftest.py:65` (`fake_ts` fixture) | same pattern: `PATH = <fake bin> + os.pathsep + <real PATH>`. The fake `tailscale` wins, but `tailscaled` is never faked. `vpn/tsadmin.py:397-410` `start_userspace_tailscaled` does `shutil.which("tailscaled")` and `subprocess.Popen` of it, detached. | PARTLY stubbed. Every test that reaches it today replaces it: `vpn/tests/test_tsadmin.py:388` replaces `start_userspace_tailscaled`, `:403` makes `which` return None for everything but `tailscale`. Safe by per-test care, not by construction: one new `vpn-up` test whose fake stderr matches `looks_like_no_tun` (`tsadmin.py:414`) starts a real daemon on a host that has one. State would land in tmp (`conftest.py:24`). This host has no `tailscale`/`tailscaled` on PATH. Fold into the fix or file a follow-up. |
| S3 | `plugin/ai-connect/vpn/tests/test_tsadmin.py:460` `test_probe_tcp_unresolvable_is_unknown` | a real DNS lookup of `no-such-host.invalid` through the host resolver (`tsadmin.py:333`) | NOT stubbed. Harmless (reserved TLD, no connection), but it is network I/O and contradicts `conftest.py:1` "no network". |
| S4 | `plugin/ai-connect/tests/test_client_tools.py:218-432` (the `peer_read` tests) with `client/tools.py:293-296` and `peer_name.py:13`, `:54-57` | `record_seen` writes `~/.config/ai-connect/sessions/<ppid>.seen` under the REAL home | NOT stubbed in this file (only `tests/test_e2e_bridge.py:56` replaces it). Not reached today only because the `_msg` helper (`test_client_tools.py:211-215`) carries no `"id"` key, so `from_bridge` is empty. `/root/.config/ai-connect` does not exist on this host, which agrees. Latent: add an `id` to a fixture message and the suite writes outside tmp_path. |

## Direction

- S2: build the `fake_ts` child PATH the way L-0790 built `child_env` (only directories the test creates, never the
  caller's PATH appended), or follow `vpn/tests/test_shims.py:50-59`, and add a must-not-reach case with a canary
  `tailscaled` on the caller's PATH. Sabotage: restore the prepend, the canary case goes red.
- S3: replace the resolver for `test_probe_tcp_unresolvable_is_unknown` so no DNS query leaves the host, or mark
  the test as network and say so in `conftest.py:1`.
- S4: an autouse fixture in `tests/test_client_tools.py` (or `tests/conftest.py`) that points `record_seen`'s
  directory at tmp_path, plus a test whose fixture message carries an `id` and asserts nothing is written under the
  real home.
- From L-0790's crew:security pass (NIT 11, not fixed there because L-0790's spec excluded `.crew/verify.json`): since
  L-0790, `tests/test_ops_firewall.py` skips as root unless `AI_CONNECT_TEST_ALLOW_ROOT=1`, and rules[28] runs
  `pytest -q`, which prints a skip count with no reason. A root gate run then reads green with the firewall tests not
  run. Add `-rs` to rules[28] (both pytest calls) so the reason is in the gate's output; that also names the 10
  skips `vpn/tests` reports on Linux, which L-0790 did not examine.
- A plugin content change: ai-connect version bump in both manifests, CHANGELOG.

## Acceptance checks (draft)

1. No ai-connect test hands a child a PATH that includes the caller's PATH unless it skips when the real tool is
   on it (the `test_shims.py` pattern).
2. A canary `tailscaled` on the caller's PATH is never started by `vpn/tests`.
3. `vpn/tests` makes no DNS query (or the one test that does is marked and documented).
4. A `peer_read` test with a message `id` writes nothing outside tmp_path.
5. Each new control is sabotage-tested and the red run recorded.

Line numbers above are as read on a192c68e; re-read them before the spec, L-0790 changed only
`tests/test_ops_firewall.py` in this plugin.

## Added 2026-10-11 14:48 CDT: two FIX lines from L-0790's Codex round 2 (owner accepted round 2; this ticket is the linked follow-up)

Status of this section: ACCEPTED. Round 2 of L-0790 (PR #605) returned FINDINGS, 0 BLOCK / 2 FIX / 0 NIT.
Owner decision, Matthew, 2026-10-11, through AskUserQuestion, relayed by the lead to the coordinator and
recorded here at 14:50 CDT: round 2 is accepted as edge-case-only, and both FIX lines are carried by this ticket.
#605 merges at the reviewed head ee9b9c2c1 with no code change. (This section was first written as "pending"
at 14:48, before his answer.)

Round: codex gpt-6-sol, family gpt, authors claude, head ee9b9c2c1, bundle 4366347ba666, gate.overridden true
(the owner allowed this one round to run with `--allow-unverified`, 2026-10-11), ran 14:40:08 to 14:44:22 CDT.
Receipt and reviewer output: `/repos/personal/uca-L-0790/.work/tickets/L-0790/review-r2.json` and
`review-r2-codex-out.txt`.

The reviewer's two lines, verbatim:

```
FIX|plugin/ai-connect/tests/test_ops_firewall.py:49|A relative `BASH` result can no longer launch after the child PATH is restricted, so the suite fails before testing the firewall|Put a `bash` executable in the working directory, put an empty entry first on the caller's PATH, and run the suite; `shutil.which` returns `bash`, which the child's PATH cannot resolve
FIX|plugin/ai-connect/tests/test_ops_firewall.py:262|Child output is decoded with the platform default encoding; Git Bash output containing a non-ASCII temp path can be misdecoded and fail the new environment test|On Windows with a non-ASCII temp path and a non-UTF-8 Python locale, run `test_child_sees_the_built_environment_not_the_callers`; its decoded `home` differs from the path passed to the child
```

The L-0790 lane's reading, not the reviewer's: neither line is a way to reach a real tool; both are ways the
suite could fail falsely in an unusual setup. Its suggested fixes, untested: `os.path.abspath` on the resolved
BASH; `encoding="utf-8"` on that one `subprocess.run`. Each needs its own test and a sabotage run.
