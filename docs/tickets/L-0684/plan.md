# L-0684 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` (gizmoduck 0.5.8 there).

1. `_test/conftest.py`: autouse fixture pointing `GIZMODUCK_HOME` at an empty temp directory and
   removing the three override variables and `XDG_DATA_HOME`, so no test reads a real tool home.
2. `scanners/base.py`: `tool_home()`, `which()` (tool home `bin` first, executable files only,
   then `shutil.which`), `override(var, resolve)` returning `unset` / `ok` / `broken` with the
   value; an OSError while checking is `broken`, never `unset`. All read at call time.
3. zap, nikto, testssl: one resolver each in the spec's four-step order; a set override that does
   not resolve returns None and stops. nikto's `is_available` and `_resolve_argv` share
   `_resolve_prefix`. The `LOCALAPPDATA` step keeps its old helper names (`_zap_jar_dirs`,
   `_find_nikto_pl`, `_find_testssl_script`) but builds its candidates at call time; the two
   existing suites that patched the import-time tuples patch the new candidate functions.
   ZAP's directory search looks for a wrapper in the directory and one level below it
   (`ZAP_<version>/zap.sh`, as the Crossplatform zip extracts), then a `zap-*.jar` under it.
4. `gizmoduck.py`: `find_nuclei` through `scanners.base.which`; `cmd_doctor` prints the tool home
   and each set override (OK / `!!` naming the variable, value and tool), without touching `ok`.
5. `test_tool_lookup.py`, doctor and routine-cli tests by the spec's names; README section,
   SKILL.md and doctor.md lines, CHANGELOG with the two behaviour changes, TODO bullet for the
   guides, gizmoduck 0.5.8 -> 0.5.9 in its three places.
6. Sabotage by hand: broken override falling through; override and PATH swapped in zap.py.
