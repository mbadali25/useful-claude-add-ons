"""Fixture vault builder for the Obsidian recall evaluation (scripts/recall-eval.py).

Builds two throwaway vaults ("main" primary, "ref" recall role) and a config file
under a directory the caller owns, so an evaluation never reads the owner's real
vault or config and never installs anything. The notes are synthetic and
deterministic: concept, decision, session and daily notes, a superseded decision
beside its replacement, a note with `files:` globs, an archived note, notes that
truncate (a 900-character line; a note past the 256 KB read bound), a lone-term
note below the relevance floor, a CamelCase-only note, and wikilinks between
notes. `bulk` adds filler notes (disjoint vocabulary) for latency runs.
"""
import json
import os

MAIN = "main"
REF = "ref"
BIG_PAD_BYTES = 270 * 1024  # past vault_recall.MAX_BYTES (256 KB)
FILLER_WORDS = ("amber basalt cobalt dune ember fjord garnet harbor indigo jasper kelp "
                "lagoon marble nectar onyx pebble quartz ridge saffron tundra umber "
                "velvet willow yarrow zephyr").split()


def _fm(**fields):
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def main_notes():
    """{relative path: text} for the curated primary vault."""
    long_line = ("A snippet is cut at 240 characters around the first matching word, so a long "
                 "line keeps the part that matters. " * 8).strip()
    return {
        "wiki/concepts/Port collisions break the bridge.md":
            _fm(title="Port collisions break the bridge", project="crew", type="concept",
                status="established")
            + "# Port collision\nTwo vaults on one port collision: the loser never binds the "
              "REST bridge.\nSee [[Hook timeouts and spawn cost]] and [[D-004 One multiplexed "
              "bridge]].\n",
        "wiki/concepts/Hook timeouts and spawn cost.md":
            _fm(title="Hook timeouts and spawn cost", project="crew", type="concept")
            + "# Hook spawn cost\nEach hook spawn costs about 0.3 seconds, so a slow recall "
              "hits the hook deadline.\nLinks: [[Port collisions break the bridge]].\n",
        "wiki/concepts/Graph dependents sidecar.md":
            _fm(title="Graph dependents sidecar", project="crew", type="concept")
            + "# Dependents\nThe sidecar lists the callers of a module, built from the code "
              "graph.\n[[Hook timeouts and spawn cost]]\n",
        "wiki/concepts/Recall file triggers.md":
            _fm(title="Recall file triggers", project="crew", type="concept",
                files=["plugin/crew/hooks/scripts/crew_recall.py", "plugin/obsidian-vault/**"])
            + "# Triggers\nA note that lists globs resurfaces when a matching path is touched."
              "\n",
        "wiki/decisions/D-001 Bridge per vault.md":
            _fm(title="D-001 Bridge per vault", project="crew", type="decision",
                decision_status="superseded", superseded_by=["D-004"])
            + "# Decision\nDecision: run one REST bridge per vault on its own port.\n",
        "wiki/decisions/D-004 One multiplexed bridge.md":
            _fm(title="D-004 One multiplexed bridge for every vault", project="crew",
                type="decision", decision_status="accepted", supersedes=["D-001"])
            + "# Decision\nDecision: one multiplexed bridge serves every vault; replaces the "
              "bridge per vault design.\n",
        "wiki/concepts/Releases.md":
            _fm(title="Releases", project="crew", type="concept")
            + "# Release checklist\nBump the version, then release.\n",
        "wiki/concepts/Long note on recall snippets.md":
            _fm(title="Long note on recall snippets", project="crew", type="concept")
            + "# Snippets\n" + long_line + "\n",
        "wiki/concepts/Other project bridge notes.md":
            _fm(title="Other project bridge notes", project="billing", type="concept")
            + "# Bridge port collision\nA port collision on the billing bridge.\n",
        "wiki/concepts/Lonely bridge mention.md":
            _fm(title="Lonely mention", project="crew") + "# Note\nthe bridge\n",
        "wiki/concepts/CamelCase only.md":
            _fm(title="CamelCase only", project="crew")
            + "# Names\nThe SprocketWidget class is private.\n",
        "wiki/concepts/Enormous log.md":
            _fm(title="Enormous log", project="crew") + "# Log\n"
            + ("filler line of no interest\n" * (BIG_PAD_BYTES // 27)) + "zeppelin\n",
        "wiki/sessions/2026-11-01 Session - bridge debugging.md":
            _fm(title="Session - bridge debugging", project="crew", type="session")
            + "# Debugging\nbridge port debugging, spawn timing and the hook deadline.\n",
        "wiki/sessions/archive/2026-01/Session - old bridge port.md":
            _fm(title="Port collisions break the bridge", project="crew", type="session")
            + "# Port collision\nbridge port collision, archived.\n",
        "daily/2026-11-02.md":
            _fm(title="2026-11-02", type="daily")
            + "# Daily\nMeasured hook spawn cost again; the recall deadline is the problem.\n",
    }


def ref_notes():
    return {
        "notes/Bridge port collision runbook.md":
            _fm(title="Bridge port collision runbook", type="concept")
            + "# Runbook\nPort collision on the bridge: stop the second vault first.\n",
    }


def bulk_notes(count):
    """`count` filler session notes of about 1.5 KB, deterministic, query-disjoint."""
    notes = {}
    for i in range(count):
        words = [FILLER_WORDS[(i * 7 + j * 3) % len(FILLER_WORDS)] for j in range(220)]
        body = "\n".join(" ".join(words[k:k + 11]) for k in range(0, 220, 11))
        notes[f"wiki/sessions/bulk/{i // 100:03d}/Bulk {i:05d}.md"] = \
            _fm(title=f"Bulk {i:05d}", type="session") + "# Filler\n" + body + "\n"
    return notes


def write_notes(root, notes):
    for rel, text in notes.items():
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def build(root, bulk=0):
    """Create the vaults and config under `root`; return the config path."""
    main_dir, ref_dir = os.path.join(root, MAIN), os.path.join(root, REF)
    write_notes(main_dir, {**main_notes(), **bulk_notes(bulk)})
    write_notes(ref_dir, ref_notes())
    config = os.path.join(root, "config.json")
    text = json.dumps({"vaults": {
        MAIN: {"path": main_dir, "role": "primary", "default": True},
        REF: {"path": ref_dir, "role": "recall"}}}, indent=2) + "\n"
    with open(config, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return config
