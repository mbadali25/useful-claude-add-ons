# 11. Native packages for AI-Connect: bundled CPython, per-user services, GitHub Releases

**Status:** proposed (DRAFT), 2026-11-08. Items 1-4 of the Decision are owner decisions of 2026-11-08; the
rest are recommendations awaiting the owner's review of this PR.
**Decided by:** the owner's picker answers of 2026-11-08 (build-file location and distribution, service
identity, signing, first scope). Items under "Recommended" were proposed by the planning pass and not yet
ruled on.

Labels used below, as in the plan this ADR comes from: **VERIFIED** (read in the repo or CI), **INFERRED**
(judgement or outside knowledge that could not be checked: the planning session had no web access),
**COULD NOT TELL** (looked, found no evidence either way).

## Context

AI-Connect (`plugin/ai-connect`) installs today from a checkout: `install.sh` / `install.ps1` / `deploy.py`
create a venv, write config, register services. Phase 1 (PR #710, CLI and join codes) adds the `ai-connect`
CLI. The owner wants native packages: `.deb`, `.rpm` and an MSI.

Facts the decision rests on (all VERIFIED unless marked):

- **Config path is hard-coded** to `~/.config/ai-connect/config.yaml` (`config_loader.py:20`), with the
  tokens beside it. There is no environment override.
- Both installers run the services **as the installing user**: systemd units `ai-connect.service` and
  `ai-connect-mcp.service` with `User=$USER`; scheduled tasks `AI-Connect Bridge` and `AI-Connect MCP HTTP`
  plus the firewall rule `AI-Connect Bridge`.
- `deploy.py` already has a relocatable runtime (`AI_CONNECT_HOME`, default `~/.local/share/ai-connect`,
  `app/` and `venv/` beneath it) and reports "already" when the plugin dir is the app dir. Its
  `service_state()` looks only at `/etc/systemd/system/ai-connect.service` and the task `AI-Connect Bridge`,
  so a package-installed unit under another name would read as absent and deploy would start a second
  Bridge on port 9999 (the code is VERIFIED; the double-bind is INFERRED).
- `installer.py claude` registers `claude mcp add ... <abs sys.executable> <REPO>/client/server.py`, so it
  needs a real interpreter path and `.py` files on disk.
- Pinned dependencies include compiled wheels via fastmcp (pydantic-core and others). The transitive set is
  INFERRED.
- `scripts/check-marketplace.py` scans only `skills/*` and `plugin/*` for registrations, and fails on a
  nested `marketplace.json` or on a changed plugin dir without a version bump. `scripts/gate-runner.py`
  fails on any workflow file that is in neither `INCLUDED_WORKFLOWS` nor `EXCLUDED_WORKFLOWS`.
- Join codes already carry a 32-byte TLS fingerprint; #710 refuses to redeem a TLS code until the TLS PR
  lands.

## Decision

### Owner decisions (2026-11-08)

1. **Build files live in the repo root, `packaging/ai-connect/`.** Releases are **GitHub Releases only**
   for now; an apt/dnf repository comes later.
2. **Services run per user; config stays in `~/.config/ai-connect`.** No `/etc`, no system user (the path
   is hard-coded). On Windows the MSI installs files only; `ai-connect setup` registers the same scheduled
   tasks as `install.ps1` (`AI-Connect Bridge`, `AI-Connect MCP HTTP`, firewall rule), asking for admin once.
3. **Signing.** Linux checksums and packages are GPG-signed with the existing key (ed25519, fingerprint
   `140DB29B7E4BD4ADA4171D731AB92BBC803AFC4C`) from a reviewer-gated CI environment. **This is not yet
   approved for use: uploading any CI secret needs the owner's separate OK, and this ADR does not grant it.**
   Windows: Azure Trusted Signing if the owner is eligible, otherwise an unsigned MSI with GPG-signed
   checksums for now.
4. **First scope.** Linux `.deb` (x86_64; Ubuntu 22.04 and 24.04, Debian 12) plus `.rpm` for RHEL 9+ built
   from the same bundled-CPython tree; then the Windows MSI; both after #710's security fixes. EL8 and
   arm64 later.

### Recommended (from the plan; not yet ruled on by the owner)

5. **Bundled standalone CPython with dependencies pre-installed** (python-build-standalone `install_only`,
   pinned version and sha256, `pip install --require-hashes` at build time). Not a frozen binary (breaks
   `installer.py claude` and the plugin `.py` hooks, and draws antivirus false positives while unsigned),
   not a venv on the system python (not relocatable, tied to the build host's minor version; RHEL 9's 3.9 is
   below the `>=3.10` check), not a postinst-built venv (needs python3-venv and ABI-matched wheels, and
   postinst failures leave dpkg half-configured). Expected package size 30-45 MB compressed (INFERRED;
   measure in P2).
6. **Linux layout** mirrors deploy's `APP_HOME`: `/opt/ai-connect/{app,venv,PACKAGED}` owned `root:root`,
   a 6-line `/usr/bin/ai-connect` wrapper that sets `AI_CONNECT_HOME`, and templated units
   `ai-connect@.service` and `ai-connect-mcp@.service` with `User=%i`. No conffiles, so dpkg/rpm can never
   touch config or tokens. Hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`,
   `ProtectHome=read-only` with `ReadWritePaths=%h/.config/ai-connect` (that log and db paths fall under the
   config dir is INFERRED from `config.yaml.example`).
7. **Maintainer scripts never touch `$HOME` and never enable anything on first install.** postinst runs
   `daemon-reload`, prints a migration notice if an `install.sh` unit exists, and on upgrade
   `try-restart`s running instances only. prerm disables on remove, not upgrade. Purge leaves every
   `~/.config/ai-connect` and says so. All scripts are idempotent.
8. **The `PACKAGED` marker.** When `$AI_CONNECT_HOME/PACKAGED` exists, `deploy.py` enables
   `ai-connect@$USER` instead of writing `/etc/systemd/system/ai-connect.service`. This closes the
   second-Bridge hazard and is the only deploy.py logic change. A new `ai-connect setup bridge|client`
   verb wraps the existing deploy/installer steps.
9. **nfpm** (pinned, sha256-verified) builds `.deb` and `.rpm` from one `nfpm.yaml`. fpm and dpkg-deb plus
   rpmbuild were rejected for toolchain weight and needing two definitions. nfpm's reproducibility flags
   at the pinned version are INFERRED; check them.
10. **Windows MSI: WiX v5 pinned**, per-machine, `ProgramFiles64Folder\AI-Connect`, `bin` on the system
    PATH, fixed `UpgradeCode` and `MajorUpgrade`. WiX v6's Open Source Maintenance Fee terms are INFERRED
    from memory and must be checked before moving off v5. MSIX (cannot register logon tasks or firewall
    rules), Inno/NSIS (not MSI) and Advanced Installer (paid) were rejected. Three custom actions only
    (stop our tasks before files change on upgrade and uninstall, restart them after upgrade, remove our
    tasks and rule on uninstall), each acting **only on tasks whose action path is under the install
    folder**, so a developer checkout's task survives. No custom action touches `%USERPROFILE%\.config`.
    A packaging-only Windows fix ships as a plugin version bump (one version everywhere).
11. **CI.** `.github/workflows/package-ai-connect.yml`: version check, Linux build and container install
    tests, MSI build and install tests, PR runs unsigned, tag `ai-connect-v*` builds, signs and attaches to
    a GitHub Release from a `release` environment with the owner as required reviewer. It is added to
    `EXCLUDED_WORKFLOWS` in `scripts/gate-runner.py` in the same PR (a lane has no Docker or WiX).
    `.crew/verify.json` gains a rule for `packaging/**`. Reproducible deb/rpm are a goal (pinned tools,
    hashed lock, `SOURCE_DATE_EPOCH`); the MSI will not be bit-identical.
12. **Why `packaging/ai-connect/` and not `plugin/ai-connect/packaging/`:** everything under the plugin dir
    ships to every Claude Code user through the plugin cache and would be copied by deploy's `app_files`;
    `check_versions` would force a plugin bump for every packaging-only edit; `on_disk()` does not scan a
    root `packaging/`, so no second-marketplace risk.
13. **Release signing.** `SHA256SUMS` plus detached `SHA256SUMS.asc`, public key published as a release
    asset, at `packaging/ai-connect/KEYS`, and by fingerprint in the README. Preferably a signing-only
    subkey exported with `--export-secret-subkeys`, so the primary stays offline. An embedded rpm signature
    for `rpm -K`; EdDSA rpm signatures need rpm 4.16 or later, which RHEL 8 lacks (INFERRED), hence EL9+.
    deb-embedded signatures are skipped (apt does not check them by default).
14. **Fix `bin/ai-connect.cmd` exit codes in P1.** It uses `exit /b %ERRORLEVEL%` inside parenthesised
    blocks, which cmd expands at parse time, so the CLI's exit code is probably lost (INFERRED, not run;
    needs `!ERRORLEVEL!` or `goto`). Unless #710's S1-S3 already cover it. The Windows install test asserts
    that `ai-connect bridge revoke --name nobody` yields exit code 1.

## Alternatives considered

Covered inline in items 5, 9, 10 and 12. Also rejected: a per-user MSI (cannot create the Bridge firewall
rule, and a second user would get a second copy), and a dedicated `ai-connect` system user with
`/etc/ai-connect` for phase 2 (needs an `AI_CONNECT_CONFIG` override in `config_loader.py`; a possible
later PR).

## Consequences

- No Python prerequisite on target machines; one bundled tree serves deb and rpm.
- Code under `/opt` or Program Files is not user-writable. Secrets never enter a package.
- Per-user services mean one `systemctl enable --now ai-connect@<user>` per user; uninstall leaves each
  user's config by design (`ai-connect uninstall --purge-config` is the opt-in).
- Packages version with the plugin; a Windows packaging-only fix costs a plugin bump.
- Until the TLS PR lands, packages ship `ws://` over the VPN exactly as today.
- Nothing here changes the repo's behaviour: this ADR is documentation only.

## Test plan (summary)

Unit tests in `packaging/ai-connect/tests/` (bundle list equals `deploy.app_files`, golden unit text,
maintainer scripts against a fake `systemctl`, custom-action logic against a fake `schtasks`, the PACKAGED
seam). Linux containers with systemd (22.04, 24.04, Debian 12, Rocky 9, Fedora): fresh install, setup,
**config preservation across upgrade** (sha256 of everything under `~/.config/ai-connect` unchanged),
remove and purge, reinstall idempotence, coexistence with an `install.sh` unit, lintian and rpmlint.
Windows VM: install and PATH in a new shell, exit-code propagation, setup registers tasks, upgrade while
running (no `1603`/`3010`), injected-failure rollback, downgrade refusal, uninstall leaving a decoy dev
task and the config. Each blocking check is sabotage-tested (add `config.yaml` to the bundle, purge
config in postrm, drop the INSTALLFOLDER check, restore `%ERRORLEVEL%`, remove the PACKAGED seam, drop
StopTasks, unpin a hash). Containers never run on a developer desktop and never touch real config.

## PR breakdown

| PR | Content | Depends on |
|----|---------|------------|
| P0 | This ADR (docs only) | none (0010, the supervisor draft in #705, is a different number) |
| P1 | Runtime seams in the plugin: PACKAGED marker in `deploy.py`, `bin/ai-connect` tries `$plugin/../venv`, `.cmd` exit-code fix, `ai-connect setup`, `service status`, `uninstall [--purge-config]`; plugin version bump | **#710 merged with its S1-S3 security fixes**; #712 (touches the same `User=` logic) |
| P2 | `packaging/ai-connect/` for Linux, `package-ai-connect.yml` (unsigned), gate-runner and verify.json entries | P1 |
| P3 | Windows: WiX, custom actions and tests, MSI jobs (test-signed with a CI-generated self-signed cert) | P1 (P2 for `build_bundle.py`) |
| P4 | Tag-triggered release job: GPG-signed SHA256SUMS, rpm signature, GitHub Release, `release` environment; README verify instructions | P2, P3, **the owner's separate OK before any CI secret is uploaded** (or the alternative of signing locally after CI builds) |
| P5 | TLS-aware packaging (bridge cert path, join over TLS) | **the TLS PR** (not pushed yet) |
| P6 (optional) | Authenticode via Azure Trusted Signing in the release job | owner choice and a validated account |
| P7 (later) | Signed apt/dnf repository, arm64, fleet MSI properties | open questions below |

TLS is not a blocker for P1-P4. Version numbers are taken "next free" at merge time; #709 and #710 both
claim 0.2.6, so whichever merges second re-bumps.

## Open questions

1. **What is 'AI-Connect Watchdog'?** SRL-DESKTOP has a scheduled task by that name. It is **not in the
   repo** (not on main, not in #710, not in any ai-connect, supervisor or tls remote branch; ADR 0010
   describes a supervisor wrapper but names no task). Where it comes from is COULD NOT TELL: ask
   SRL-DESKTOP. If it arrives with ADR 0010's supervisor it follows the setup-registers-it pattern.
2. **EL8 support.** Needs an RSA subkey for rpm verification or a drop; the recommendation is EL9+ only.
3. **apt/dnf repository timing.** Needs a hosting decision and the signing key in CI for every publish.
4. **Azure Trusted Signing eligibility.** Individual eligibility is country-limited and needs identity
   validation; price and eligibility are INFERRED and unchecked.
5. Also open: WiX v6 terms (item 10); arm64; whether #710's S1-S3 already include the `.cmd` exit-code fix
   (the plan could not read them); the ACL on `gpg-passphrase.txt` (a Git Bash listing does not show the
   Windows ACL; check with `icacls`).

## Not verified

No package was built and no size measured. No web checks were possible: the WiX terms, Trusted Signing
pricing and eligibility, OV/EV prices, rpm EdDSA on EL8, nfpm reproducibility flags, `pythonw.exe` in the
Windows python-build-standalone tree, hosted-runner support for systemd in containers, and the `.cmd`
parse-time expansion are all INFERRED.
