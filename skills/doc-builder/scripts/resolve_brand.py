#!/usr/bin/env python3
"""Decide which brand pack doc-builder renders with, and say why.

A brand pack is a skill directory carrying `assets/brand.json`
(`solomon-doc-builder/assets/brand.json`, for example). Brand is CONFIGURATION,
not a trigger: an installed pack is applied without anyone asking for it, so
the document an operator forgets to ask about is still styled correctly.

Resolution order, in full, and every script prints which step matched:

    1. `--brand <name>` always wins. `neutral` names the built-in pack; a path
       to a brand.json, or to a directory holding one, also works.
    2. DOC_BUILDER_BRAND in the environment, same values.
    3. Sibling skill directories of doc-builder - correct in a git checkout,
       where every skill sits under one `skills/`.
    4. The plugin cache. A marketplace install puts each plugin in its OWN
       versioned directory (`.../plugins/cache/<marketplace>/<plugin>/<version>/`),
       so doc-builder's "siblings" there are only its own other versions and
       step 3 finds nothing. This step walks up from doc-builder's own location
       and looks a bounded depth beneath each ancestor, then under the user's
       `~/.claude/skills` and `~/.claude/plugins/cache`. The layout is treated
       as undocumented: anything unexpected falls through, nothing raises.
    5. The neutral pack - announced LOUDLY, naming every location searched.
       A silent fallback to neutral is the defect this order exists to prevent;
       an announced one is a diagnosis.

Exactly one pack found at the first step that finds any -> that is the brand.
Several different packs -> stop and ask which, naming them; guessing here puts
one client's footer on another client's report. The same pack found in several
versions -> the most recently modified copy, and that choice is printed.

Every other script in scripts/ imports this module instead of computing paths
or colours itself, so the toolchain moves as a unit. Stdlib only.

Usage:
    resolve_brand.py                 # print what would be used, and why
    resolve_brand.py --list          # every pack visible from here, by location
    resolve_brand.py --brand solomon --json   # merged values, for inspection
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(SCRIPTS_DIR, os.pardir))
NEUTRAL_JSON = os.path.join(SKILL_ROOT, "assets", "brands", "neutral", "brand.json")

# The directory holding every installed skill in a checkout. Overridable so the
# discovery rules can be tested against a scratch tree with zero, one and two packs.
SKILLS_DIR_ENV = "DOC_BUILDER_SKILLS_DIR"
BRAND_ENV = "DOC_BUILDER_BRAND"
MASTERS_DIR_ENV = "DOC_BUILDER_MASTERS_DIR"

# How many ancestors of doc-builder's own directory the plugin-cache search
# climbs. Four reaches `cache/` from `cache/<marketplace>/doc-builder/<version>/`
# with one to spare; a drive root is never searched.
CACHE_CLIMB = 4


class BrandError(SystemExit):
    """Raised as SystemExit so a CLI caller exits non-zero with the message."""


class BrandAmbiguous(BrandError):
    def __init__(self, names, where):
        self.names = list(names)
        super().__init__(
            "More than one brand pack is installed (%s): %s.\n"
            "Pass --brand <name> (or set %s) to say which one this document is for."
            % (where, ", ".join(self.names), BRAND_ENV))


class BrandNotFound(BrandError):
    def __init__(self, wanted, names):
        super().__init__(
            "No brand pack named %r. Installed: %s."
            % (wanted, ", ".join(names) if names else "(none - only 'neutral')"))


def skills_dir() -> str:
    return os.path.normpath(os.environ.get(SKILLS_DIR_ENV) or os.path.join(SKILL_ROOT, os.pardir))


def _is_own(path) -> bool:
    """True when `path` is inside doc-builder itself (its neutral pack, or a
    copy of doc-builder in another version directory)."""
    p = os.path.normcase(os.path.normpath(path))
    return p.startswith(os.path.normcase(SKILL_ROOT) + os.sep) or \
        os.path.basename(os.path.dirname(os.path.dirname(path))).lower() == "doc-builder"


def _glob_many(patterns) -> list:
    found = []
    for pat in patterns:
        try:
            found.extend(glob.glob(pat))
        except (OSError, ValueError):
            continue
    out = []
    seen = set()
    for f in found:
        f = os.path.normpath(f)
        key = os.path.normcase(f)
        if key in seen or _is_own(f) or not os.path.isfile(f):
            continue
        seen.add(key)
        out.append(f)
    return sorted(out)


def search_locations() -> list:
    """Ordered [(label, [glob patterns])]. Step 3 first, then step 4's shapes."""
    j = os.path.join
    locs = [("sibling skill directories under %s" % skills_dir(),
             [j(skills_dir(), "*", "assets", "brand.json")])]
    if os.environ.get(SKILLS_DIR_ENV):
        return locs  # a test tree: do not also wander the real machine
    ancestor = SKILL_ROOT
    for _ in range(CACHE_CLIMB):
        parent = os.path.dirname(ancestor)
        if not parent or parent == ancestor or os.path.dirname(parent) == parent:
            break  # reached a drive root; never search that
        ancestor = parent
        locs.append(("plugin cache beneath %s" % ancestor, [
            j(ancestor, "*", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "skills", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "*", "skills", "*", "assets", "brand.json"),
        ]))
    home = os.path.join(os.path.expanduser("~"), ".claude")
    locs.append(("user skills under %s" % j(home, "skills"),
                 [j(home, "skills", "*", "assets", "brand.json")]))
    cache = j(home, "plugins", "cache")
    locs.append(("user plugin cache under %s" % cache, [
        j(cache, "*", "*", "*", "assets", "brand.json"),
        j(cache, "*", "*", "*", "skills", "*", "assets", "brand.json"),
    ]))
    return locs


def _load(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("_comment", None)
    return data


def _pack_name(path) -> str:
    skill_dir = os.path.basename(os.path.dirname(os.path.dirname(path)))
    try:
        return _load(path).get("name") or skill_dir
    except (OSError, ValueError):
        return skill_dir


def discover(root=None):
    """(packs, label, searched_labels): the packs at the FIRST location that
    holds any, that location's label, and every label searched up to it.
    `root` overrides the sibling directory (tests)."""
    if root:
        os.environ[SKILLS_DIR_ENV] = root
    searched = []
    for label, patterns in search_locations():
        searched.append(label)
        packs = _glob_many(patterns)
        if packs:
            return packs, label, searched
    return [], None, searched


def _dedupe_versions(packs):
    """Several copies of the SAME pack (versioned installs) -> newest by mtime.
    Returns ({name: path}, notes)."""
    by_name = {}
    notes = []
    for p in packs:
        name = _pack_name(p)
        if name in by_name:
            keep, drop = sorted([by_name[name], p], key=os.path.getmtime, reverse=True)
            by_name[name] = keep
            notes.append("%s found in more than one version; using the most recently "
                         "modified copy (%s)" % (name, keep))
        else:
            by_name[name] = p
    return by_name, notes


def _merge(base, over):
    """Deep merge: a pack supplies only what differs from neutral."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Brand:
    """The merged brand pack plus every path the toolchain derives from it."""

    def __init__(self, path, reason):
        self.path = os.path.normpath(path)
        self.root = os.path.dirname(self.path)          # .../assets
        self.reason = reason
        neutral = _load(NEUTRAL_JSON)
        pack = neutral if os.path.normcase(self.path) == os.path.normcase(NEUTRAL_JSON) else _load(self.path)
        self.data = _merge(neutral, pack)
        self.name = self.data.get("name") or os.path.basename(
            os.path.dirname(self.root))

    # -- convenience accessors -------------------------------------------------
    @property
    def organisation(self) -> str:
        return self.data.get("organisation") or ""

    @property
    def fonts(self) -> dict:
        return self.data["fonts"]

    @property
    def report(self) -> dict:
        return self.data["report"]

    @property
    def sop(self) -> dict:
        return self.data["sop"]

    def _rel(self, value):
        """A relative path in brand.json is relative to the assets/ directory."""
        if not value:
            return None
        value = os.path.expandvars(os.path.expanduser(str(value)))
        return value if os.path.isabs(value) else os.path.normpath(os.path.join(self.root, value))

    @property
    def template(self):
        """Absolute path of the .docx template, or None to synthesise one."""
        return self._rel(self.sop.get("template"))

    @property
    def masters_dir(self):
        """Where finished SOPs go. Environment override beats the pack, which
        beats nothing - the neutral pack has no masters directory and callers
        must then name an output path."""
        env = os.environ.get(MASTERS_DIR_ENV)
        if env:
            return os.path.normpath(env)
        return self._rel(self.sop.get("masters_dir"))

    def require_masters_dir(self) -> str:
        """masters_dir, or exit with the remedy. Never creates it: a missing
        production directory is a wrong machine or a wrong path, and silently
        making one hides that."""
        d = self.masters_dir
        if not d:
            raise BrandError(
                "The %s brand pack has no masters directory. Pass an explicit path, "
                "or set %s." % (self.name, MASTERS_DIR_ENV))
        if not os.path.isdir(d):
            raise BrandError(
                "Masters directory not found: %s\nSet %s to point at it, or pass "
                "an explicit path." % (d, MASTERS_DIR_ENV))
        return d

    @property
    def specs_dir(self):
        return self._rel(self.sop.get("specs_dir"))

    @property
    def assets_dir(self):
        """Where source screenshots live, so a SOP can be rebuilt without
        unpacking the .docx. Defaults to a sibling of the masters directory."""
        explicit = self._rel(self.sop.get("assets_dir"))
        if explicit:
            return explicit
        if self.masters_dir:
            return os.path.normpath(os.path.join(self.masters_dir, os.pardir, "assets"))
        return None

    @property
    def report_output_dir(self) -> str:
        return self.report.get("output_dir") or "reports"

    def describe(self) -> str:
        return "brand: %s -- %s (%s)" % (self.name, self.reason, self.path)

    def announce(self, stream=sys.stderr):
        print(self.describe(), file=stream)


def _match_explicit(wanted, packs):
    """`wanted` may be a pack name, a skill directory name, a path to a
    brand.json, or a directory containing one (directly or under assets/)."""
    if wanted.lower() == "neutral":
        return NEUTRAL_JSON, "--brand neutral given"
    if os.path.isfile(wanted):
        return wanted, "--brand given as a file path"
    if os.path.isdir(wanted):
        for cand in (os.path.join(wanted, "brand.json"),
                     os.path.join(wanted, "assets", "brand.json")):
            if os.path.isfile(cand):
                return cand, "--brand given as a directory"
    names = []
    for path in packs:
        skill_dir = os.path.basename(os.path.dirname(os.path.dirname(path)))
        name = _pack_name(path)
        names.append(name)
        if wanted.lower() in (name.lower(), skill_dir.lower()):
            return path, "--brand %s given" % wanted
    raise BrandNotFound(wanted, names)


def _all_packs():
    """Every pack at every location, for --brand <name> lookups and --list."""
    seen, out = set(), []
    for _, patterns in search_locations():
        for p in _glob_many(patterns):
            if os.path.normcase(p) not in seen:
                seen.add(os.path.normcase(p))
                out.append(p)
    return out


def resolve(explicit=None, root=None, announce=True) -> Brand:
    """Apply the five steps. Prints the outcome to stderr unless told not to."""
    if root:
        os.environ[SKILLS_DIR_ENV] = root
    wanted = explicit or os.environ.get(BRAND_ENV)
    notes = []
    if wanted:
        path, reason = _match_explicit(wanted, _all_packs())
        if not explicit:
            reason = "%s=%s set in the environment" % (BRAND_ENV, wanted)
    else:
        packs, label, searched = discover()
        if packs:
            by_name, notes = _dedupe_versions(packs)
            if len(by_name) > 1:
                raise BrandAmbiguous(sorted(by_name), label)
            (name, path), = by_name.items()
            reason = "the only brand pack found in %s" % label
        else:
            path = NEUTRAL_JSON
            reason = ("no brand pack found - using neutral. Searched: "
                      + "; ".join(searched))
    brand = Brand(path, reason)
    if announce:
        brand.announce()
        for n in notes:
            print("brand: note: " + n, file=sys.stderr)
    return brand


def add_brand_argument(parser: argparse.ArgumentParser) -> None:
    """The one --brand flag every script shares, so the help text cannot drift."""
    parser.add_argument(
        "--brand", default=None,
        help="brand pack name, or 'neutral' (default: the single installed pack, "
             "else neutral; ambiguous when several are installed - see resolve_brand.py)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_brand_argument(ap)
    ap.add_argument("--list", action="store_true", help="list every visible brand pack, by location, and exit")
    ap.add_argument("--json", action="store_true", help="print the merged brand values")
    args = ap.parse_args(argv)

    if args.list:
        print("neutral  %s  (built in)" % NEUTRAL_JSON)
        for label, patterns in search_locations():
            packs = _glob_many(patterns)
            print("\n%s:" % label)
            for p in packs:
                print("  %-8s %s" % (_pack_name(p), p))
            if not packs:
                print("  (none)")
        return 0

    brand = resolve(args.brand, announce=not args.json)
    if args.json:
        print(json.dumps(brand.data, indent=2))
    else:
        print("template    : %s" % (brand.template or "(synthesised from brand.json)"))
        masters = brand.masters_dir
        state = "" if not masters else ("" if os.path.isdir(masters) else "  (NOT FOUND on this machine)")
        print("masters_dir : %s%s" % (masters or "(none - pass an output path)", state))
        print("assets_dir  : %s" % (brand.assets_dir or "(none)"))
        print("specs_dir   : %s" % (brand.specs_dir or "(none)"))
        print("reports     : %s/" % brand.report_output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
