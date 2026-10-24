# Safe Nuclei defaults for gizmoduck scans

Repository area: the `gizmoduck` plugin, `plugin/gizmoduck/`. Its tests are in
`plugin/gizmoduck/scripts/_test/` and run with
`python3 -m pytest plugin/gizmoduck/scripts/_test -q`. They need no network and no
scanner installed; they stub every scanner process.

## The problem

A Nuclei scan started through gizmoduck currently sends whatever the installed
template set holds, as fast as Nuclei goes. That includes templates tagged `dos`,
`intrusive` and `fuzz`, and an unlimited request rate. Two entry points build the
Nuclei command line, each with its own copy of the logic: the single-scanner
`gizmoduck.py scan` command (`cmd_scan`), and the Nuclei adapter used by the
multi-tool routine (`scanners/nuclei.py`, `run(target, outdir, opts)`). Neither adds
any safety option today.

## What to build

A Nuclei scan started through gizmoduck sends safe traffic unless the caller opts
out by name. Opting out is explicit and visible.

1. **One shared argv builder.** `gizmoduck.py` gains a function
   `nuclei_argv(exe, target, severity, extra, *, intrusive=False, rate_limit=None, strict=False)`
   that returns the Nuclei argument list as a list of strings. `cmd_scan` and
   `scanners/nuclei.run` both build their command through it; neither keeps an argv of
   its own, so for the same inputs they produce the same list.
   - Order: `-jsonl -silent -nc`, then `-l <target>` when the target is an existing
     file or `-u <target>` otherwise, then `-severity <value>` when a severity is
     given, then the tag exclusion, then the rate flag, then the `extra` tokens
     exactly as given and last (`extra` is a whitespace-separated string).
   - Tag exclusion: `-etags dos,intrusive,fuzz` is present unless `intrusive` is true.
   - Rate limit: `-rl 50` by default. An explicit `rate_limit` replaces the 50. If
     `rate_limit` is not given and `extra` already carries a rate flag, no default
     rate flag is added: the caller's value stands, in either direction. An explicit
     `rate_limit` together with a rate flag inside `extra` is a usage error, never a
     guess about which wins: `nuclei_argv` raises `ValueError` whose message
     mentions "rate".
   - A flag inside `extra` is recognised by token: strip leading dashes, split at the
     first `=`, compare the name. So `-rl 10`, `--rl 10` and `-rl=10` all count. Rate
     flag names are `rl`, `rate-limit`, `rlm`, `rate-limit-minute`. Tag flag names are
     `etags`, `exclude-tags`, `itags`, `include-tags`.
   - `strict=True` (used by the routine) raises `ValueError` when `extra` names any of
     those eight rate or tag flags; its message names both supported options,
     `nuclei_intrusive` and `nuclei_rate_limit`. With `strict=False` (the `scan`
     command) `extra` stays a raw passthrough: tag flags in it are passed through
     untouched.
2. **`scan` command options.** `scan` gains `--intrusive` (drops the tag exclusion)
   and `--rate-limit N` (replaces the default rate). `cmd_scan` accepts matching
   keyword arguments `intrusive` and `rate_limit`. `N` must be an integer of 1 or
   more; anything else exits 2. `scan --rate-limit N --extra "<a rate flag>"` exits 2
   with an error mentioning "rate", runs nothing and writes no output file.
3. **Routine manifest options.** In a routine manifest, a target's `options` may carry
   `nuclei_intrusive: true` and `nuclei_rate_limit: N` (an integer of 1 or more, not a
   boolean). `nuclei_intrusive` is an active-mode option of the Nuclei adapter:
   `scanners/nuclei.py` declares `ACTIVE_OPTS = ["nuclei_intrusive"]` (the adapter
   stays on by default and not itself marked active). The adapter reads
   `nuclei_intrusive`, `nuclei_rate_limit`, `severity` and `extra` from `opts`.
4. **The routine refuses to loosen the safety in `extra`.** The routine passes
   `strict=True`. When `extra` names a rate or tag flag, the adapter does not start
   Nuclei and does not create its output directory; it returns
   `(None, ToolResult(-1, "", <message naming nuclei_intrusive and nuclei_rate_limit>, False))`.
   So that a manifest author sees the reason before anything runs, manifest
   validation at parse time refuses the same manifest with exit status 2, the existing
   "routine: manifest refused" style of error, naming `nuclei_intrusive` and
   `nuclei_rate_limit`, with nothing written and no scanner run.
5. **The routine records the mode.** A Nuclei cell in the run manifest is recorded as
   `ran(safe)` when `nuclei_intrusive` is not set and `ran(safe+intrusive)` when it is,
   not as a bare `ran`. Coverage counts and the exit status are unchanged by the new
   label (it counts as `ran`).

## Acceptance, in behaviour terms

- `nuclei_argv("nuclei", "https://x.invalid/", "", "")` contains `-etags dos,intrusive,fuzz`
  once and exactly one rate flag, `-rl 50`.
- With `intrusive=True` there is no `-etags`, and the rate flag is still `-rl 50`.
- `rate_limit=7` gives `-rl 7`; `extra="-rlm 600"` gives no `-rl` and exactly that one
  rate flag; `extra` tokens are always the tail of the list, unchanged.
- `strict=True` refuses each of the eight names above in both the `-name value` and
  `--name=value` spellings, and allows other flags such as `-tags cve -timeout 5`.
- `scan` with no extra option runs with the defaults; with `--intrusive` it has no
  `-etags` and keeps `-rl 50`; with `--rate-limit 12` it has `-rl 12`.
- The routine records `ran(safe)` and `ran(safe+intrusive)` as described, and passes
  the manifest's `nuclei_rate_limit` through to the adapter's options.
- `cmd_scan` and the adapter yield the same argv for the same inputs
  (severity, extra, intrusive, rate limit).
- Existing behaviour of the other scanners, of `bootstrap.sh`/`bootstrap.ps1` and of
  anything outside `plugin/gizmoduck/` does not change, and the existing tests keep
  passing. Update the existing Nuclei argv-shape test so that it asserts the new
  defaults.

Behaviour change worth stating in the changelog: a default scan now runs fewer
templates and sends at most 50 requests per second, so it can find less and take
longer than before.
