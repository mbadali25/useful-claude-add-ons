---
description: Install security-scan pipelines (GitHub Actions / Bitbucket Pipelines) into a repo - code scans plus staging endpoint scans, baseline diff, fail on new Critical/High
argument-hint: <github|bitbucket|both> <staging-url> [repo-path]
---
Using the `gizmoduck` skill, install gizmoduck CI pipelines into the repository at `${3:-.}` for
platform `$1`, scanning the staging URL `$2`.

1. **Confirm authorisation first.** Ask the user who authorised security scanning of `$2` and pass
   that as `--authorized-by`. Never guess it. If `$2` does not look like a staging host of theirs,
   stop and ask.
2. **Dry run - always first.** Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck_ci.py render --platform $1 --staging-url $2 --repo ${3:-.} --authorized-by "<who>"`
   and show the user every file it prints, plus any `GIZMODUCK_CI_REFUSED` line verbatim. Ask
   whether to add `--enable nikto,nmap,sqlmap` (all off by default; sqlmap sends attack traffic),
   `--production-url <prod>` (so a staging URL that is really production is refused), and
   `--deploy-workflow <name>` (GitHub: also scan after that workflow succeeds).
3. **Write only after the user approves the dry run**: the same command plus `--apply`. An
   existing workflow or `bitbucket-pipelines.yml` is refused unless the user asks for `--force`;
   for Bitbucket, offer `--bitbucket-out <path>` to write beside the existing file for a manual
   merge instead of overwriting it.
4. Tell the user which repository variables and secrets the pipeline reads (the rendered file's
   header lists them) and that production is only ever scanned when BOTH
   `GIZMODUCK_ALLOWED_PROD_ORIGINS` lists the origin AND `GIZMODUCK_ALLOW_PROD_SCAN=true`. SDP
   tickets are off unless `GIZMODUCK_SDP_TICKETS=true` and the SDP secrets exist.

Never run a scan from this command, and never contact the staging URL yourself - the pipeline does
that, behind its runtime guard.
