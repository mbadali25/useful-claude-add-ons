# T-0054 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` (base `origin/release/1.2.0`,
which already carries T-0048's `build.py --check` and the version-free guide names of C-0006 #512).

1. Re-read `AVAILABLE` / `ARRIVES` in `crew_autopilot.py` at this commit: `status`, `run`, `focus`,
   `sleep`, `wake` are available; `assign` (L-0611) and `goal` (T-0012) arrive later. `ship`
   (T-0011), the Telegram/Teams pings (T-0051), sleep mode (T-0053, L-0652), focus (T-0020),
   auto-resume (T-0013) and the plain-text phrases (T-0057) are on this base, so their rows move from
   "coming" to "landed" in the suite and get a section; goal, wave, split and `--goal` stay coming.
2. `scripts/_test/autopilot-guide.py` first: the example list (landed rows: phrases in the source
   and in the built HTML, tags stripped; coming rows: ids and phrase in the "What is coming" table),
   must-fail cases (phrase removed, stale HTML, coming id removed, id only elsewhere, source or HTML
   missing) and must-pass cases (committed pair, a phrase across a wrap, a phrase in a fence), on
   throwaway copies. It imports neither crew code nor `markdown`.
3. `docs/guides/crew/src/autopilot.md`, the ten sections of the spec. Every sample of script output
   is pasted from `crew_autopilot.py` run in a throwaway repo under a temp directory (settings,
   status, next for direction / ready / unapproved plan, approve refused and allowed, sleep refused,
   deploy-allowed for staging and prod), paths shortened to `/path/to/repo`.
4. `build.py`: one `GUIDES` entry (`crew-autopilot.{html,docx,pdf}`, version-free); build all three
   with LibreOffice; `build.py --check` exits 0. `src/README.md`: a row in both tables.
5. Wiring: a `marketplace.yml` step and a `gate-runner.py` row for the suite; the suite joins the
   `docs/**`-family and `scripts/**` rules in `.crew/verify.json`; `.crew/codemap/repo-docs.md`
   names the new source, and `.claude/rules/repo-docs.md` is regenerated from it.
