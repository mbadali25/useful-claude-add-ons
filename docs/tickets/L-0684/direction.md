# L-0684 direction - gizmoduck tool lookup: one tool home, and an explicit override beats PATH (external report item 10)

Split from T-0108 on 2026-10-04. Filed as L-0684. Status: seed with a recommendation, taken under the owner's standing authority because the owner was not available. Checked against origin/main `155fe6d8` (gizmoduck 0.5.6).

## Ask
The parent's ask, from a cross-session report against gizmoduck 0.5.3: "ZAP/nikto look up Windows LOCALAPPDATA first (override GIZMODUCK_ZAP_HOME / GIZMODUCK_NIKTO_PL)."

## What the code does today
The report's wording is not what the code does, but there is a real defect behind it.
- ZAP: a `zap.bat` or `zap.sh` on PATH wins (`plugin/gizmoduck/scripts/scanners/zap.py:57-58`, `:102-104`), then `GIZMODUCK_ZAP_HOME`, then `%LOCALAPPDATA%\Programs\zap` (`:70-77`). The override directory is searched for a `zap-*.jar` only (`:87-92`), never for a `zap.sh` or `zap.bat` sitting in it.
- Nikto: a `nikto` on PATH wins (`scanners/nikto.py:112-114`), then `GIZMODUCK_NIKTO_PL`, then `LOCALAPPDATA` (`:89-95`). The candidates are built when the module is imported.
- testssl has the same shape (`scanners/testssl.py:64-70`, `:95-102`).
- The other seven adapters resolve through `base.which`, which is `shutil.which` and nothing else (`scanners/base.py:37-38`). `find_nuclei` adds `~/go/bin/nuclei` (`gizmoduck.py:141-148`).
- None of the `GIZMODUCK_*` lookup variables is documented outside the code.

So: an operator's explicit override silently loses to PATH; an override that points at nothing silently falls through to another install; and on Linux a tool is found only if it is on PATH, which is why `bootstrap.sh` needs root to write `/usr/local/bin`.

## Options
1. **Recommended: one lookup rule for every adapter.** Order: the tool's own override variable, then a gizmoduck tool home (`GIZMODUCK_HOME`, default `~/.local/share/gizmoduck` on Linux and macOS), then PATH, then the platform's well-known location (`LOCALAPPDATA` on Windows, as today). An override that is set but does not resolve makes the tool unavailable and `doctor` says which variable is wrong; it never falls through. Environment is read at call time.
2. Only swap the order in ZAP and nikto. Smaller, but leaves Linux with no tool home, so the no-sudo bootstrap (L-0685) has nowhere to install to.
3. Docs only: document the variables and the current order. Leaves the silent fall-through.

## Recommendation
Option 1. It is the smallest change that makes L-0685 possible and makes the override mean what its name says.

## Depends on / blocks
- After T-0107 (done) and L-0599 (done).
- Blocks L-0685, which installs into the tool home this ticket defines.
- Independent of T-0108 itself (safe Nuclei defaults), but both edit `gizmoduck.py` and the README; land one at a time.
