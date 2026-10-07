# T-0502 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` (base `origin/release/1.2.0`).

1. `plugin/crew/tests/test_setup_verify_templates.py`: the acceptance list's tests, each copying the
   templates into a throwaway repo with a fake `mmdc` first on PATH (records its arguments and the
   `-p` config; modes ok / empty / root), plus the LF-and-parse check.
2. `templates/cases/diagrams-render.sh` (new, outside `templates/_verify/` so setup copies it only
   into a repo with `.mmd` files): `--no-sandbox` puppeteer config always, `cygpath -w` when present,
   one render per source into a temp directory, the last 5 mmdc lines under a `FAIL`, empty render
   is a FAIL, exit 77 without `mmdc`, `trap` clean-up, `# readonly: yes`.
3. `templates/_verify/smoke.sh` `check()` and `run-all.sh` `run()`: capture output; PASS / SKIP on 77
   / FAIL with the indented tail; `smoke.sh`'s count line adds the skips and keeps its `SMOKE: `
   prefix. Every line setup-walkthrough.sh greps stays byte-compatible.
4. Docs: phases.md Phase 3, the template README, crew-diagrams SKILL.md, crew README section 6 and
   the `mmdc` troubleshooting row, the troubleshooting guide source (rebuilt). `verify.md` stays as is
   (over its line budget). BUDGETS re-measured.
5. `.crew/verify.json` rule for the templates and the test; the handoff note and its README row go;
   CHANGELOG; the crew version is set in the branch's last commit (coordinator placeholder).
