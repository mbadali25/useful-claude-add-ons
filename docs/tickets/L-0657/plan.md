# L-0657 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform`, after T-0055 (same branch)
and with T-0048 already on the base (`docs/guides/crew/src/build.py --check`,
`config_reference.py --check`).

1. Re-read both `--check` commands: `build.py --check` exits 0 fresh, 1 naming the stale guide
   (`stale: crew-quickstart.html - rebuild with ...`), 2 when `markdown` does not import;
   `config_reference.py --check` imports only the standard library. Confirmed in a clean venv with
   `markdown==3.11` and `pyyaml` only: both exit 0; with `markdown` uninstalled `build.py --check`
   exits 2.
2. `marketplace.yml`: an install step `python -m pip install 'markdown==3.11'` (covered by
   `EXCLUDED_CI`'s install pattern) and two named check steps after T-0055's.
3. `scripts/gate-runner.py`: both commands in `TABLE` with their `ci=` pairs; a `module:<name>` need
   (SKIP when the module does not import) on the `build.py` step. One new case in
   `scripts/_test/gate-runner.py`.
4. `CLAUDE.md` clause in the crew-docs paragraph; `CHANGELOG.md`.
5. The must-fail proof in CI (one-line `quickstart.md` edit, then revert) needs a PR run, which this
   lane cannot open; it was shown locally (`build.py --check` exit 1 naming `crew-quickstart.html`)
   and is left for the coordinator's PR.
