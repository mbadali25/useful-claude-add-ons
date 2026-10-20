# A headless `routine` command for gizmoduck, with a dated results layout

Repository area: the `gizmoduck` plugin, `plugin/gizmoduck/` (Python, standard library
plus PyYAML for the new command). Its tests are in `plugin/gizmoduck/scripts/_test/`
and run with `python3 -m pytest plugin/gizmoduck/scripts/_test -q`. They need no
network and no scanner installed; they inject fake scanner adapters.

## The problem

`plugin/gizmoduck/scripts/routine.py` (`load_manifest`, `run_routine`) is the only path
to checkov, trivy, dependency-check, semgrep, ZAP, testssl, nmap, nikto and (gated)
sqlmap. It has no command line, and `gizmoduck.py`'s commands (`scan`, `summary`,
`parse`, `report`, `tickets`, `diff`, `doctor`, `update`) do not reach it, so only
Nuclei can be run headless. `report` already renders a combined per-target report with
a coverage table (the part that tells a partial run from a clean one) when it is handed
a run manifest, but the command line gives it no way to receive one. And nothing writes
a dated per-module results directory that a pipeline can read.

## What to build

1. **`gizmoduck.py routine <manifest.yaml>`**. It calls the existing
   `routine.load_manifest` and `routine.run_routine` (their gates stay exactly as they
   are: `authorized_by`, unique target names, sqlmap's two gates), then renders the
   combined report from the run's own `findings.jsonl` and `run-manifest.json`,
   coverage table included. `import routine` (which needs PyYAML) happens lazily inside
   this command, so every other command keeps working without PyYAML.
2. **Output location.** `--out <dir>` writes the files into that directory.
   `--scan-root <module-dir>` writes them into the dated layout
   `<module-dir>/docs/security-scans/<YYYY-MM-DD>/`. The file set is `findings.jsonl`,
   `run-manifest.json`, `scan-meta.json` (gizmoduck's own versioned schema), `report.md`,
   `report.html`, and `report.pdf` only when a PDF renderer is present. The date is
   today's UTC date unless `--date YYYY-MM-DD` is given. Each file the command itself
   authors is written complete and then renamed into place, never truncated first.
3. **`scan-meta.json`.** Valid JSON with at least: `schema` (1), `date`
   (`YYYY-MM-DD`), `authorized_by`, `targets` (a list of `{name, kind, location}`),
   `coverage` with `complete` (boolean) and `by_status` (a mapping from status family
   to a count; a cell status such as `error:timeout` counts under the family `error`,
   `skipped-missing` under `skipped-missing`, `skipped-active` under `skipped-active`,
   `ran` and `ran(...)` under `ran`), the finding counts by severity, UTC start and
   completion timestamps, and the names of the files written. Fields gizmoduck cannot
   know are not invented.
4. **Exit status.** 0 when every resolved (target, tool) cell ran. 4 when every output
   was written but at least one cell did not run (`skipped-missing`, `skipped-active`
   or `error:*`); in that case `coverage.complete` is false and the last line printed to
   stdout is `GIZMODUCK_ROUTINE_INCOMPLETE: <n> of <m> cells did not run`. 2 when the
   manifest or the usage is wrong and nothing was written. Findings being present never
   changes the status.
5. **sqlmap.** It fires only when `--confirm-active` is given by name (the option parser
   already refuses abbreviations: `--confirm` alone is an error). Without the flag a
   manifest that asks for sqlmap records `skipped-active`, as `run_routine` does today.
   The command adds no other way to fire sqlmap and removes neither existing gate.
6. **Re-running into a used directory.** If the output directory already holds a
   `scan-meta.json`, the run is refused with exit status 2 and nothing is written or
   run, unless `--replace` is given. The refusal message names the path of that
   `scan-meta.json` and mentions `--replace`. `--replace` re-runs into the directory:
   it removes the files an earlier run wrote there (including a stale `report.pdf`) and
   the per-target subdirectories the earlier `scan-meta.json` names as its targets, so a
   target dropped from the manifest leaves no stale output, and it removes nothing else
   (other directories in that location, such as a `.git`, are left alone).
7. **Manifest errors.** A manifest that cannot be loaded (missing file, bad YAML,
   missing `authorized_by`, duplicate target name, unknown kind, missing location) gives
   exit status 2 and a message on stderr containing `routine: manifest refused` followed
   by the underlying error text, with no output directory created and no scanner run.
8. **Usage errors**, each exit status 2 (via the argument parser's exit) with the text
   below on stderr and nothing written anywhere (no output directory, no default
   directory, no scan root):
   - `routine` with no manifest: `routine needs a manifest`
   - `--scan-root`, `--date`, `--replace` or `--confirm-active` given to any other
     command: `<flag> only applies to the 'routine' command`
   - `--run-manifest` given to any command other than `report`:
     `--run-manifest only applies to the 'report' command`
   - `--scan-root` together with `--out`: a message containing `--scan-root and --out`
   - `--date` without `--scan-root`: `--date only shapes the --scan-root layout`
   - an unparsable date: `--date must be YYYY-MM-DD, not '<value>'`
9. **`report --run-manifest <run-manifest.json>`** renders a routine run with its
   coverage table: the markdown has a `## Coverage` section naming the cell statuses
   and the HTML report has a `<table class='coverage'>`. Without the flag, output is
   byte-identical to today's. With flat (Nuclei-only) findings the manifest is ignored
   and the output is the existing flat report. A run manifest that is missing or is not
   JSON is a usage error: exit 2, a message beginning `--run-manifest:`, no report file
   written.

## Interface the checks use

The checks drive the command two ways, so these names are part of the contract.

- In `plugin/gizmoduck/scripts/gizmoduck.py`: a function
  `cmd_routine(manifest_path, out, *, scan_root=None, date=None, replace=False, confirm=False, title=None, min_sev=<report detail floor>, registry=None)`
  that returns the exit status as an int (0, 4 or 2) and prints the messages above to
  stderr/stdout itself. `out` may be `None` when `scan_root` is given; `date` is a
  `datetime.date` or `None`; `confirm` carries `--confirm-active`; `registry` is the
  scanner registry object `routine.run_routine` already accepts (the test seam, so no
  real scanner runs). Module constants `ROUTINE_INCOMPLETE_EXIT = 4`,
  `ROUTINE_MARKER = "GIZMODUCK_ROUTINE_INCOMPLETE"`, and `ROUTINE_FILES`, a tuple of the
  file names a routine run owns in its output directory (the five always-written files
  above plus `report.pdf`).
- `gizmoduck.py main()` with `sys.argv`, and the script run as a subprocess
  (`python3 gizmoduck.py routine <manifest> --out <dir>`), including with an empty
  `PATH` so that no scanner resolves (then every cell is `skipped-missing` and the
  status is 4).

## Out of scope

No change to `plugin/crew/`, to `routine.py`'s gates or its own writes, to the flat
report path, or to the behaviour of `scan`, `summary`, `parse`, `tickets`, `diff`,
`doctor` and `update`. No new slash command, no hook, no severity-threshold exit code,
no scheduling. Update the plugin's own README and skill text to describe the command
and the exit codes.
