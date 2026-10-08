# L-0685 direction - gizmoduck bootstrap.sh without sudo, and a CI and containers guide (external report item 9)

Split from T-0108 on 2026-10-04. Filed as L-0685. Status: seed with a recommendation, taken under the owner's standing authority because the owner was not available. Checked against origin/main `155fe6d8` (gizmoduck 0.5.6).

## Ask
The parent's ask, from a cross-session report against gizmoduck 0.5.3: "bootstrap.sh needs apt/sudo; no guidance for CI/containers; ZAP adapter deliberately avoids Docker."

## What the code does today
- `plugin/gizmoduck/bootstrap.sh` calls `sudo` on almost every step (`:34-35`, `:64-71`, `:91`, `:95`, `:101-107`, `:114`, `:141-149`, `:158-167`, `:176`, `:197-202`) and writes to `/opt` and `/usr/local/bin`. A container that runs as root usually has no `sudo` binary, so each step fails with "command not found"; an unprivileged CI user has no root at all.
- With no TTY, `sudo` either fails or waits for a password.
- The script's last command is a `cat` (`:256-268`), so it exits 0 even when tools failed (`:246-251`). A CI step cannot gate on it.
- Three steps ask the GitHub API for the latest release without a token (`:48-49`, `:130-131`, `:185-186`); shared CI addresses hit the unauthenticated rate limit.
- The README's install section is two lines (`plugin/gizmoduck/README.md:23-28`).
- The no-Docker rule (`scanners/zap.py:3-8`, `bootstrap.sh:179-183`) is about the adapter not shelling out to `docker run`. It does not stop gizmoduck from running inside a container whose image already holds the tools. The docs do not say so.
- `bootstrap.ps1` already installs per user with no admin rights (`:15`, `:44`); nothing to change there.

## Options
1. **Recommended: a `--user` mode plus root detection, and a README section.** `--user` installs everything that can be installed without a package manager into the gizmoduck tool home (defined by L-0684) and lists what it had to skip. Without `--user`, the script uses no `sudo` when already root. A `--dry-run` prints the plan and changes nothing, which is also what makes the script testable without installing anything. The script exits 1 when any tool failed.
2. Docs only: a README section telling CI users which packages to add to their image. No code, but every user rewrites the same install steps by hand.
3. Publish a container image. Rejected: adds a registry and release process, and the report does not ask for it.

## Recommendation
Option 1.

## Depends on / blocks
- After L-0684 (the tool home and `base.which` looking in its `bin`). Without it, nothing installed by `--user` is found.
- After T-0107 (done) and L-0599 (done).
- Blocks nothing.
