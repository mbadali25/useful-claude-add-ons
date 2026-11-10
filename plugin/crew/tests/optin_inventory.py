"""Generates `data/optin_inventory.json`, the inventory L-0724 moves files by.

Three sections, each derived by running code over the tree and never typed:

* `sabotage` - every mutation of `sabotage.MUTATIONS` whose target is a file L-0724
  moves into an opt-in plugin, or whose anchor text carries a moved name, with the
  exact anchor text, the number of times it occurs in its target, and the target's
  path in both layouts (the opt-in path first, the core path second). The anchor guard
  test holds the tree to this section exactly, so an anchored line is never edited.
* `refs` - every `${CLAUDE_PLUGIN_ROOT}/<path>` (and `$H/<script>` alias) in a Markdown
  file that moves, classified `exec` (a command runs it), `read` (the model reads it),
  `local` (it names a file that moves with the same skill) or `alias`. An opt-in
  reaches an `exec` target in core through a same-named shim; a `read` target is
  rewritten to the resolver form. A blank kind is a bug (`test_optin_inventory.py`).
* `names` - which files that stay in core still name a moved surface; slices 2-4 give
  each one an "if installed" alternative.

    python3 plugin/crew/tests/optin_inventory.py --write   regenerate the file
    python3 plugin/crew/tests/optin_inventory.py --check   exit 1 when it is stale
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CREW = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(CREW))
DATA = os.path.join(HERE, "data", "optin_inventory.json")

COMMAND_HOME = {
    "sdp-sync": "crew-trackers", "jira-sync": "crew-trackers", "obsidian-sync": "crew-trackers",
    "change": "crew-trackers", "autopilot": "crew-autopilot", "promote": "crew-promote",
    "emergency": "crew-promote", "gate": "crew-promote", "diagram": "crew-docs",
    "runbook": "crew-docs", "reference": "crew-docs", "survey": "crew-docs", "graph": "crew-docs",
}
SKILL_HOME = {
    "crew-change": "crew-trackers", "crew-notify": "crew-autopilot",
    "crew-cloud": "crew-cloud", "crew-terraform": "crew-cloud",
    "crew-diagrams": "crew-docs", "crew-runbooks": "crew-docs", "crew-house-style": "crew-docs",
}
for _stack in ("angular", "bash", "dotnet", "node", "php", "powershell", "python", "sql",
               "terraform", "web"):
    SKILL_HOME["stack-" + _stack] = "crew-stacks"

_COMMANDS = "|".join(sorted(COMMAND_HOME))
NAME_RE = re.compile(
    rf"/crew:({_COMMANDS})\b|\bcrew-(?:change|notify|cloud|terraform|diagrams|runbooks|house-style)\b"
    r"|\bstack-(?:angular|bash|dotnet|node|php|powershell|python|sql|terraform|web)\b")
# A name-carrying anchor on a file that stays in core is a line the mutation must find
# again. A multi-kilobyte block (sabotage_refresh.py builds one out of .crew/verify.json at
# import) is derived from its target, so editing the target moves the anchor with it.
MAX_NAME_ANCHOR = 4000
SLASH_RE = re.compile(rf"/crew:({_COMMANDS})\b")
REF_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`'\")]+)")
ALIAS_RE = re.compile(r"\$H/([A-Za-z0-9_.-]+\.py)")
BARE_RE = re.compile(r"\bcrew_[a-z_]+\.py\b")
EXEC_RE = re.compile(r"(python3|python|bash|sh|cp|source|&)\b[^`]*$")


OPTIN_HOMES = tuple(sorted(set(COMMAND_HOME.values()) | set(SKILL_HOME.values())))


def _plugin_rel(path):
    """`commands/x.md` for a file under `plugin/crew/` or any opt-in's directory, else None."""
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    for home in ("crew",) + OPTIN_HOMES:
        prefix = f"plugin/{home}/"
        if rel.startswith(prefix):
            return rel[len(prefix):]
    return None


def _first_existing(layouts):
    for rel in layouts:
        path = os.path.join(ROOT, *rel.split("/"))
        if os.path.isfile(path):
            return path
    return None


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def moved_layouts(path):
    """Both layouts of a moved target as repo-relative paths, opt-in first; else None."""
    rel = _plugin_rel(path)
    if rel is None:
        return None
    match = re.match(r"commands/([^/]+)\.md$", rel)
    if match and match.group(1) in COMMAND_HOME:
        home = COMMAND_HOME[match.group(1)]
    else:
        match = re.match(r"skills/([^/]+)/", rel)
        if not (match and match.group(1) in SKILL_HOME):
            return None
        home = SKILL_HOME[match.group(1)]
    return [f"plugin/{home}/{rel}", "plugin/crew/" + rel]


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def sabotage_section():
    import sabotage  # pylint: disable=import-outside-toplevel
    rows = []
    core = set()
    for mutation in sabotage.MUTATIONS:
        label, target, find, replace = mutation[0], mutation[1], mutation[2], mutation[3]
        layouts = moved_layouts(target)
        carries = len(find) <= MAX_NAME_ANCHOR and bool(SLASH_RE.search(find) or SLASH_RE.search(replace))
        if not layouts and not carries:
            core.add(_rel(target))
            continue
        row = {"label": label, "layouts": layouts or [_rel(target)], "find": find,
               "count": _read(target).count(find), "carries_moved_name": carries}
        rows.append(row)
    rows.sort(key=lambda r: (r["layouts"][0], r["label"], r["find"]))
    return {"mutations_total": len(sabotage.MUTATIONS), "anchors": rows,
            "stays_in_core": sorted(core)}


def _moved_markdown():
    """(path relative to its plugin, home, file): each moved Markdown file in whichever layout exists."""
    for name, home in sorted(COMMAND_HOME.items()):
        rel = f"commands/{name}.md"
        path = _first_existing([f"plugin/{home}/{rel}", f"plugin/crew/{rel}"])
        if path:
            yield rel, home, path
    for name, home in sorted(SKILL_HOME.items()):
        seen = set()
        for plugin in (home, "crew"):
            base = os.path.join(ROOT, "plugin", plugin, "skills", name)
            for dirpath, _dirs, files in os.walk(base):
                for fname in sorted(files):
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, os.path.join(ROOT, "plugin", plugin)).replace(os.sep, "/")
                    if fname.endswith(".md") and rel not in seen:
                        seen.add(rel)
                        yield rel, home, full


def refs_section():
    refs = []
    for rel, home, path in _moved_markdown():
        for number, line in enumerate(_read(path).splitlines(), 1):
            for match in REF_RE.finditer(line):
                target = match.group(1)
                owner = re.match(r"skills/([^/]+)/", target)
                if owner and SKILL_HOME.get(owner.group(1)) == home:
                    kind, where = "local", "own"
                elif EXEC_RE.search(line[:match.start()] + "x"):
                    kind, where = "exec", "core"
                elif "`$H`" in line or "is `python3" in line:
                    kind, where = "alias", "core"
                else:
                    kind, where = "read", "core"
                refs.append({"file": rel, "home": home, "line": number, "target": target,
                             "kind": kind, "in": where})
            if rel == "commands/autopilot.md":
                for match in ALIAS_RE.finditer(line):
                    refs.append({"file": rel, "home": home, "line": number,
                                 "target": "hooks/scripts/" + match.group(1),
                                 "kind": "alias", "in": "core"})
    return refs


def names_section():
    out = {}
    moved = {rel for rel, _h, _p in _moved_markdown()}
    for top in ("commands", "skills", "agents"):
        for dirpath, _dirs, files in os.walk(os.path.join(CREW, top)):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                path = os.path.join(dirpath, fname)
                rel = os.path.relpath(path, CREW).replace(os.sep, "/")
                if rel in moved:
                    continue
                skill = re.match(r"skills/([^/]+)/", rel)
                if skill and skill.group(1) in SKILL_HOME:
                    continue
                hits = sorted({m.group(0) for line in _read(path).splitlines()
                               for m in NAME_RE.finditer(line)})
                if hits:
                    out[rel] = hits
    return dict(sorted(out.items()))


def build():
    return {"version": 1, "sabotage": sabotage_section(), "refs": refs_section(),
            "names": names_section(),
            "shim_targets": sorted({r["target"] for r in refs_section()
                                    if r["kind"] in ("exec", "alias") and r["in"] == "core"
                                    and os.path.isfile(os.path.join(CREW, *r["target"].split("/")))})}


def render(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv):
    text = render(build())
    if "--write" in argv:
        with open(DATA, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return 0
    if "--check" in argv:
        return 0 if os.path.isfile(DATA) and _read(DATA) == text else 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
