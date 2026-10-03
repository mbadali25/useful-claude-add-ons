# T-0044 plan            spec: .work/tickets/T-0044/spec.md

Anchors are checked against `origin/main` at 502cb137, which is the T-0005 merge. Implement cuts `T-0044-build` from `origin/main`. The optional second opinion was skipped because Codex is at its usage limit until 2026-10-01. This is a single-family opinion, and the review round has to be the independent check.

## Design (settled; the steps below implement it)

**Config.** The block is machine-only, in `~/.claude/crew/config.json`, and read from that file alone. A repo copy is ignored and reported, never merged:

```
"unattendedCloud": {
  "aws": {
    "readOnly": {"profile": null, "identity": null, "region": null},
    "nonProd": {}
  }
}
```

- `identity` is the assumed-role ARN prefix exactly as STS prints it, ending in `/`. For example: `arn:aws:sts::<acct>:assumed-role/<RoleName>/`.
- `nonProd` maps an environment name to `{"profile", "identity", "region"}`. A name is usable only when the repo's `environments.nonProd` (repo layer, `plugin/crew/hooks/scripts/cloud_guard.py:2526`) classifies it as nonProd. Both layers must agree, like T-0005's ratchet.
- There is no production entry, and none can be written: `launch --environment <name>` for a name the repo does not classify as nonProd refuses.
- Any key under `unattendedCloud` other than `aws` refuses as "provider not implemented". That is the provider seam.

**States.** Each check returns `(state, why)`, and `state` is one of `ready`, `refuse` or `unknown`. `unknown` refuses exactly like `refuse` but keeps its own label in the output, so "could not tell" is never printed as a verdict. The launch goes ahead only when every check says `ready`.

**`crew_unattended.py`**, pure core plus CLI:

- `check --root R [--environment NAME] [--json]` runs every check and prints one line per check. It exits 0 only when all are ready.
- `launch --root R [--environment NAME] -- claude [args...]` runs `check`, then on POSIX calls `os.execvpe("claude", ...)` with the sealed environment and `--settings <sealed settings>` prepended. It refuses any command whose basename is not `claude`.

Checks, in order. The first non-ready one stops the chain, and the reason is printed verbatim:

1. **platform.** `os.name == "nt"` is `unknown`: "sandbox probe not implemented for native Windows".
2. **config.** Read the machine file only. Refuse when no identity is named, when the provider is unknown, when the environment is not nonProd in the repo, or when the environment has no machine entry. A repo-layer `unattendedCloud` is reported as ignored.
3. **export.** Run `aws configure export-credentials --profile P --format process` with a 60s timeout and a stripped environment, and read the output into memory only.
   - It is `refuse` when `SessionToken` or `Expiration` is missing (static keys).
   - It is `refuse` when `Expiration` is less than 15 minutes away.
   - It is `unknown` on a non-zero exit, a timeout, or JSON that is not an object.
4. **identity.** Run `aws sts get-caller-identity --output json` in the sealed environment (below) with a 30s timeout. It is `ready` only when `Arn` starts with the configured `identity`. It is `refuse` for any other ARN, including `:user/`. It is `unknown` on failure, a timeout or malformed JSON.
5. **sandbox probe.** Run `claude -p --settings <sealed settings> --output-format stream-json --verbose --max-turns 2 --allowedTools Bash` in the sealed environment, from the repo root, with the repo's own settings loaded. The fixed prompt runs exactly one Bash command, the probe script:
   - For each store that exists: `head -c1 <file>` or `ls <dir>`, then `python3 -c "open(<file>).read(1)"`.
   - It prints `OPEN <store>` or `SHUT <store>`, then `NONCE <random>`.
   - Parse the `tool_result` blocks only. The probe is `ready` when the nonce is present, every existing store is reported `SHUT`, and there is no `OPEN`.
   - A missing nonce is `unknown` ("sandbox: unavailable"), quoting the tool result's first line. On this host that line is the seccomp error.
   - Any `OPEN` is `refuse`. A store not reported, or no tool call at all, is `unknown`.
   - The probe output never contains a credential, because the probe only tests whether a store opens and prints no contents.

**Sealed environment.**
- It starts from `os.environ` minus every `AWS_*` variable.
- It adds `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and `AWS_CREDENTIAL_EXPIRATION` from the export, plus `AWS_REGION`, `AWS_EC2_METADATA_DISABLED=true` and `CREW_UNATTENDED=1`.
- `AWS_CONFIG_FILE` points at `<sealed>/aws-config`, which holds `[default]` and `region = R` only.
- `AWS_SHARED_CREDENTIALS_FILE` points at `<sealed>/no-credentials`, a path that is never created.
- `<sealed>` is a `tempfile.mkdtemp(prefix="crew-sealed-")` directory with mode 0700. No credential is ever written to it.

**Stores.** These paths are denied: `~/.aws`, whole, which covers `credentials`, `config`, `sso/cache` and `cli/cache`; `~/.azure`; `~/.terraform.d/credentials.tfrc.json`; and `~/.claude/crew/config.json`, so the session cannot rename its own identity. Each path is expanded from the real home directory, and each appears in `sandbox.filesystem.denyRead` and as `Read(<path>)` plus `Read(<path>/**)` in `permissions.deny`.

**Sealed settings.**

```
{"sandbox": {"enabled": true, "failIfUnavailable": true, "autoAllowBashIfSandboxed": true,
             "allowUnsandboxedCommands": false, "filesystem": {"denyRead": [...]}},
 "permissions": {"deny": [...]}}
```

**Logging.** `launch` prints the checks and the identity ARN, and nothing else. It never prints the environment, the export, or argv values after `--settings`.

### Step 1: the machine-only `unattendedCloud` config block
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/global.template.json, plugin/crew/tests/test_crew_config.py, plugin/crew/tests/test_change_command.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_change_command.py -q
Risk: med. A repo-layer value that is honoured lets a cloned repo choose credentials on the owner's machine. Template drift fails `test_the_templates_carry_the_block_at_the_current_schema`.
- [ ] Write these tests first and watch them fail:
  - `test_unattended_cloud_defaults_grant_nothing`
  - `test_unattended_cloud_is_global_only`: the block is present in `default_global_config()` and absent from `default_config()`
  - `test_repo_unattended_cloud_is_ignored`: `explain_config` reports the global value alone and flags a repo copy, as `_AUTOCLEAR_MACHINE_ONLY_PATHS` does at `plugin/crew/hooks/scripts/crew_config.py:1610-1672`
  - `test_unattended_cloud_block_problem`: fails for `identity` without a trailing `/`, `nonProd: []`, a non-string profile, and `"azure": {}`
- [ ] Add `UNATTENDED_CLOUD_DEFAULTS` in `plugin/crew/hooks/scripts/crew_state.py`, beside `RESUME_DEFAULTS` (`:695`), with a comment giving the machine-only reason. Add `UNATTENDED_CLOUD_MACHINE_ONLY = ("unattendedCloud",)`.
- [ ] Add the block to `default_global_config` (`plugin/crew/hooks/scripts/crew_config.py:385`) only. `nonProd` is a map, so `leaf_paths` treats it as a leaf. Add `unattended_cloud_block_problem` beside `cloud_block_problem` (`:995`). In `explain_config`, a dotted path under `unattendedCloud.` reports the global layer only.
- [ ] Write the same block, with the same key order, into `plugin/crew/templates/global.template.json`. Re-measure the global leaf count asserted in `test_crew_config.py` and write the new number and its reason in the comment.

### Step 2: the pure core of `crew_unattended.py`
Files: plugin/crew/hooks/scripts/crew_unattended.py, plugin/crew/tests/test_crew_unattended.py
Test: python3 -m pytest plugin/crew/tests/test_crew_unattended.py -q -k "core"
Risk: high. This is where an unknown can become `ready`. Every rule gets a unit case here and a mutation in Step 5.
- [ ] Write the unit tables first: `CORE_CONFIG`, `CORE_EXPORT`, `CORE_IDENTITY`, `CORE_PROBE_PARSE`, `CORE_ENV`, `CORE_SETTINGS`. Every row names the value a bug would collapse to, and is built so that collapse would give `ready`.
- [ ] `resolve_target(machine_cfg, repo_envs, environment)` returns `(state, why, target)`. The rules: `readOnly` when no environment is given; a nonProd entry only when the repo classifies the name as nonProd (reuse `cloud_guard.environments_config` and its matcher, imported, not restated); a provider other than `aws` is `refuse`.
- [ ] `judge_export(obj, now)` returns `(state, why)`. It enforces SessionToken, Expiration, and the 15-minute floor. It is `unknown` for a non-dict, for a missing `Version`, and for an Expiration that will not parse.
- [ ] `judge_identity(obj, identity)` returns `(state, why)` using a prefix match on an `identity` ending in `/`. It is `refuse` on `:user/`.
- [ ] `judge_probe(stream_lines, nonce, stores)` returns `(state, why)`. It reads `tool_result` content from stream-json lines only, and applies the Design rules.
- [ ] `sealed_env(base, creds, region, sealed_dir)` and `sealed_settings(stores)` are pure. `stores(home)` lists the Design paths.

### Step 3: the probes, run against fake `aws` and `claude` shims
Files: plugin/crew/hooks/scripts/crew_unattended.py, plugin/crew/tests/test_crew_unattended.py
Test: python3 -m pytest plugin/crew/tests/test_crew_unattended.py -q -k "probe or export or identity"
Risk: high. A probe that swallows a failure turns `unknown` into `ready`. The shims print canned output and never reach AWS or a model.
- [ ] Fixture: `tmp_path/bin/aws` and `tmp_path/bin/claude` shims, driven by env vars that pick the canned output, exit code or sleep. `HOME` points at a `tmp_path` home with fake stores.
- [ ] Every subprocess runs with an argv list, a timeout, and `capture_output`, so a shell never sees the argv. A timeout or an `OSError` is `unknown`, and `why` says which.
- [ ] Tests: export exits non-zero, times out, prints non-JSON, or prints static keys; STS mismatch, `:user/`, timeout; probe nonce missing, which must quote the shim's `apply-seccomp: ...` line verbatim; probe `OPEN`; a store not reported; no tool call.

### Step 4: `launch` and `check`, and the end-to-end suites
Files: plugin/crew/hooks/scripts/crew_unattended.py, plugin/crew/tests/test_crew_unattended.py
Test: python3 -m pytest plugin/crew/tests/test_crew_unattended.py -q
Risk: high. This step is the boundary. A launch that reaches `exec` with any check not ready is the failure the whole ticket exists to prevent.
- [ ] `main(argv)` handles `check` and `launch`. `launch` runs `check`, and only when everything is ready does it create the sealed directory, write the region-only config and the settings file, and call `os.execvpe`. The tests monkeypatch `os.execvpe` to record `(file, argv, env)`, and a subprocess case uses a real fake `claude` that dumps its argv and env to a file.
- [ ] `MUST_REFUSE` covers every spec Acceptance case. Each asserts that `execvpe` was not called, that the exit is non-zero, and that the reason text is present.
- [ ] `MUST_LAUNCH` covers the read-only and nonProd happy paths, with the env and settings assertions from the spec.
- [ ] `test_no_credential_leaves_memory`: the sentinel values from the fake export are searched for in the captured stdout/stderr, every file under the sealed directory, `.crew/`, and the fake `~/.claude/crew/`. It runs on a refusal (the STS mismatch) and on a launch.

### Step 5: sabotage entries, each naming the test it turns red
Files: plugin/crew/tests/sabotage_unattended.py, plugin/crew/tests/sabotage.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0044 python3 plugin/crew/tests/sabotage.py --only unattended
Risk: med. A mutation whose collapsed value also refuses is vacuous (the lesson recorded at `plugin/crew/tests/sabotage_cloud.py:12-16`), so each entry names its red test and its neighbouring case.
- [ ] Add `UNATTENDED_MUTATIONS`, imported beside `RESUME_MUTATIONS` (`plugin/crew/tests/sabotage.py:76`) and added to `MUTATIONS` (`:3047-3049`). Each mutation, with the test it must turn red and its neighbour:
  - drop the SessionToken check: red `static-keys`; neighbour: a missing Expiration
  - drop the 15-minute floor: red `expiring-soon`
  - make the identity match a substring instead of a prefix: red `identity-other-role`; neighbour `identity-user-arn`
  - make a probe missing its nonce count as ready: red `probe-seccomp`; neighbour `probe-no-tool-call`
  - ignore `OPEN` lines: red `probe-open-store`; neighbour `probe-unreported-store`
  - read the repo layer: red `repo-only-identity`
  - drop the repo nonProd agreement: red `nonprod-not-in-repo`; neighbour `nonprod-no-machine-entry`
  - stop stripping `AWS_*`: red `launch-strips-aws-env`
  - drop `AWS_EC2_METADATA_DISABLED`: red `launch-disables-imds`
  - accept any command: red `refuses-non-claude`
- [ ] Run the harness and record each entry going red with its test name. Then restore the source (`git checkout --`) and confirm the suite is green again.

### Step 6: the verify rule
Files: .crew/verify.json
Test: python3 scripts/check-marketplace.py
Risk: low
- [ ] Add a rule whose paths are `plugin/crew/hooks/scripts/crew_unattended.py`, `plugin/crew/tests/test_crew_unattended.py` and `plugin/crew/tests/sabotage_unattended.py`, whose run is `python3 -m pytest plugin/crew/tests/test_crew_unattended.py -q`, with `reach: local` and a timed `seconds` value.

### Step 7: docs, the diagram, the codemap, the version bump
Files: plugin/crew/README.md, plugin/crew/CONFIG.md, plugin/crew/commands/autopilot.md, plugin/crew/skills/crew-cloud/SKILL.md, plugin/crew/skills/crew-setup/SKILL.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/crew-1.0-troubleshooting.html, docs/guides/crew/crew-1.0-troubleshooting.docx, docs/guides/crew/crew-1.0-troubleshooting.pdf, .crew/codemap/crew.md, docs/diagrams/data-flow-crew-config.mmd, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, CHANGELOG.md
Test: python3 scripts/check-marketplace.py && python3 docs/guides/crew/src/build.py (the build prints the renderer it used, and every guide must say "OK" for its fenced-block count)
Risk: med. A version bump that misses one of the two files ships nothing to installed machines, and the checker catches that. A doc that still says "T-0044" as a future ticket misleads.
- [ ] README:
  - a new "Unattended runs: sealed cloud credentials" section after "What the guard does not catch" (`plugin/crew/README.md:1143`), covering the launcher, the checks, the refusals, the host sandbox requirement quoting the seccomp error, and the accepted risks from the spec's Unknowns
  - `:1180` names `crew_unattended.py launch` in place of "That is T-0044"
- [ ] CONFIG.md: a new subsection documenting `unattendedCloud`, machine-only, with the example. Replace the T-0044 mention at `plugin/crew/CONFIG.md:1525`.
- [ ] `commands/autopilot.md` §0 says that an unattended run touching the cloud is started with `crew_unattended.py launch -- claude ...` and never from an already-running session. crew-cloud SKILL `:156`: same replacement as README. crew-setup SKILL: the global-template snippet gains the block.
- [ ] Troubleshooting guide: a new "Unattended launch refuses" entry under "Cloud guard false positives" (`docs/guides/crew/src/troubleshooting.md:200`) giving each refusal and what to do. Rebuild with `build.py` and commit the HTML/DOCX/PDF.
- [ ] `.crew/codemap/crew.md`: add DERIVED claims for the launcher with repo-relative anchors, and re-anchor. `docs/diagrams/data-flow-crew-config.mmd`: add the machine-only `unattendedCloud` read into `crew_unattended.py`.
- [ ] Bump crew to the next patch above whatever `origin/main` holds at implement time, in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, and update the `plugin/PLUGINS.md` claim line. The CHANGELOG entry notes the new launcher, the machine-only block, and that nothing existing changes behaviour.

### Step 8: the full gate
Files: .crew/verify.json
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0044 python3 -m pytest plugin/crew/tests/test_crew_unattended.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_change_command.py plugin/crew/tests/test_cloud_guard.py plugin/crew/tests/test_cloud_guard_environments.py -q && python3 scripts/check-marketplace.py
Risk: low
- [ ] Run the named suites and the checker serially under the heavy lock. Quote any failure verbatim. Say that `drift-detection.sh` was not run, and that a real sandbox launch was not exercised on this host because the host's sandbox cannot start (spec Evidence).
- [ ] Delete untracked `.crew/.verify-gate*.json` records before bundling for review, and keep `.crew/.scope-base` and `.crew/metrics.md` untracked (T-0068).
