<!-- <repo>/CLAUDE.md — target 30-40 lines. Routing table, not documentation.
     Loads into every subagent on every delegation. Every line is paid for. -->

# <repo-name>

**Stack:** <...>   **Runs:** <one line to start locally>
**Platform:** <linux | wsl2/Ubuntu | macos | windows>   **Shell:** <bash | powershell>
**Talks to:** <db, upstream services, consumers>

## Commands
| build | `<...>` |
| test  | `<...>` |
| smoke | `./scripts/smoke.sh` |
| lint  | `<...>` |
| migrate | `<...>` |

## Where things are
- entrypoint: `<path>`
- logic: `<path>`
- data access: `<path>`
- DO NOT TOUCH: `<vendor/, generated/, legacy/>`

## Rules
- <repo-specific constraint>
- <repo-specific constraint>

## Known landmines
- <the thing that breaks every time>

## Memory
Code map: `.crew/codemap/INDEX.md`. Read the index, then one subsystem file.
Before trusting a note, check its anchor sha against HEAD. Code wins over notes.
