---
description: Install tiered security-scan pipelines (GitHub Actions / Bitbucket Pipelines) into a repo - endpoint autodetection that asks instead of guessing, light PR checks, targeted full scans, a weekly sweep
argument-hint: "[--detect] <github|bitbucket|both> [repo-path]"
---
Using the `gizmoduck` skill, install gizmoduck CI pipelines into a repository. With `--detect` as `$1`,
run only steps 1-3 (re-detect and re-confirm endpoints - what a pipeline asks for when it fails with
"run /gizmoduck:ci --detect") against the repository at `${2:-.}`. Otherwise the platform is `$1` and
the repository is `${2:-.}`.

`CLI` below is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck_ci.py`.

1. **Detect - writes nothing.** Run `CLI detect --repo <repo>` and show the user its output
   verbatim: every finding with its source `path:line` and confidence (high / medium / low - the
   rules are in `scripts/ci_detect.py`'s docstring), then one `**Decision needed:**` block per
   unsettled question (staging base URL, auth for protected endpoints, include/exclude scope,
   which confidence to commit, and whether to fetch a live OpenAPI document).
2. **Ask every Decision needed block as printed.** Recommendation first; never answer one yourself
   and never fill in a staging URL the user did not give - a URL detection found is a candidate the
   owner confirms, not a default. If the repository names no staging URL, the block says so and
   offers none. Do not proceed past a block the user has not answered.
3. **Persist the answers.** Dry run first:
   `CLI setup --repo <repo> --staging-url <url|none> --auth <none|header|exclude-protected> --accept <high|medium|low> (--scope all | --include GLOB ... --exclude GLOB ...) [--openapi-path <path|none>]`.
   Show the `gizmoduck-ci.json` it prints and, when crew is present, the `.crew/endpoints.json`
   records it would append as `source: "declared"`. Only after the user approves, re-run with
   `--apply`. That is the only path that writes declared records; never edit the ledger by hand.
4. **Confirm authorisation.** Ask who authorised security scanning of the staging URL and pass it
   as `--authorized-by`. Never guess it.
5. **Render - dry run first.**
   `CLI render --platform <platform> --staging-url <url> --repo <repo> --authorized-by "<who>"`.
   Show every file it prints, plus any `GIZMODUCK_CI_REFUSED` or `# note:` line verbatim (a leftover
   pre-0.7.0 `gizmoduck-code.yml` must be deleted, or it keeps running an untiered scan). Ask about
   `--enable nikto,nmap,sqlmap` (off by default; sqlmap sends attack traffic), `--production-url`
   (so a staging URL that is really production is refused), and `--deploy-workflow` (GitHub: also
   scan after that workflow succeeds).
6. **Write only after approval**: the same command plus `--apply`. Existing files are refused
   unless the user asks for `--force`; for Bitbucket, offer `--bitbucket-out <path>` instead.
7. **Endpoints inventory.** Show `CLI inventory --repo <repo> --stdout` verbatim: one table per
   module, declared (`<module>/public-endpoint.md`) or autodetected, with `undetermined` wherever
   no staging URL could be read. Offer `--root`, `--exclude` and `--output` if the module list is
   wrong. Only after approval run it without `--stdout` so `endpoints-inventory.md` exists before
   the pipelines' `check` runs on the default branch.
8. Tell the user:
   - the tiers (README "CI pipelines"): tier 1 light PR check blocks on a new Critical only; tier
     2 (PRs into the default branch or `release/*`, the `security-scan` label, or Bitbucket's
     manual `custom: security-full`) blocks on a new Critical/High; the tier-3 weekly sweep never
     blocks; endpoint scans never run on a pull request;
   - Bitbucket only: the weekly sweep needs a one-time schedule in Repository settings ->
     Pipelines -> Schedules (branch: default, pipeline: `custom: security-weekly`), as the rendered
     file's header says;
   - the required checks: each PR workflow's `gate` job (GitHub); on Bitbucket, the one-time
     `gizmoduck-trusted` deployment environment holding every secret (`GIZMODUCK_BB_TOKEN`,
     `SDP_*`, `NVD_API_KEY`, `GIZMODUCK_AUTH_HEADER_VALUE`) as deployment variables, plus a
     read-only `GIZMODUCK_BB_READ_TOKEN` repository variable - the PR step, and a custom run on an
     untrusted branch, refuses to run while any of those secrets is visible to it;
   - which repository variables and secrets the pipelines read (the rendered headers list them),
     including `GIZMODUCK_AUTH_HEADER_VALUE` when auth is `header`, and that production is only
     ever scanned when BOTH `GIZMODUCK_ALLOWED_PROD_ORIGINS` lists the origin AND
     `GIZMODUCK_ALLOW_PROD_SCAN=true`;
   - that an endpoint run with no endpoints fails UNVERIFIED rather than passing, and endpoints
     seen for the first time are scanned and reported "new, confirm at next setup";
   - that `endpoints-inventory.md` and `security-scan-report.md` are committed on branches only
     (`[skip ci]`, never the default branch, which only runs `check`), and that a docs-only PR's
     tier-1 `gate` passes with "no scannable changes" (README "CI pipelines").

Never run a scan from this command, and never contact the staging URL yourself - the pipeline does
that, behind its runtime guard.
