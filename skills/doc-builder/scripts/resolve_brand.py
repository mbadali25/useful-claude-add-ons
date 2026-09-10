#!/usr/bin/env python3
"""Decide which brand pack doc-builder renders with, and say why.

A brand pack is a sibling skill directory carrying `assets/brand.json`
(`skills/solomon-doc-builder/assets/brand.json`, for example). Brand is
CONFIGURATION, not a trigger: an installed pack is applied without anyone
asking for it, so the document an operator forgets to ask about is still
styled correctly.

Resolution order, in full:

    1. `--brand <name>` (or DOC_BUILDER_BRAND in the environment) always wins.
       `neutral` names the built-in pack; a path to a brand.json also works.
    2. Otherwise scan the sibling skill directories for assets/brand.json.
       Exactly one found  -> that is the default for every document.
    3. More than one found -> stop and ask which, naming them. Guessing here
       would put one client's footer on another client's report.
    4. None found -> the neutral pack in assets/brands/neutral/.

Whatever the outcome, the resolved brand and the REASON are printed to stderr
so a surprising result is diagnosable rather than mysterious.

Every other script in scripts/ imports this module instead of computing paths
or colours itself, so the toolchain moves as a unit. Stdlib only.

Usage:
    resolve_brand.py                 # print what would be used, and why
    resolve_brand.py --list          # every pack visible from here
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

# The directory holding every installed skill. Overridable so the discovery
# rules can be tested against a scratch tree with zero, one and two packs.
SKILLS_DIR_ENV = "DOC_BUILDER_SKILLS_DIR"
BRAND_ENV = "DOC_BUILDER_BRAND"
MASTERS_DIR_ENV = "DOC_BUILDER_MASTERS_DIR"


class BrandError(SystemExit):
    """Raised as SystemExit so a CLI caller exits non-zero with the message."""


class BrandAmbiguous(BrandError):
    def __init__(self, names):
        self.names = list(names)
        super().__init__(
            "More than one brand pack is installed: %s.\n"
            "Pass --brand <name> (or set %s) to say which one this document is for."
            % (", ".join(self.names), BRAND_ENV))


class BrandNotFound(BrandError):
    def __init__(self, wanted, names):
        super().__init__(
            "No brand pack named %r. Installed: %s."
            % (wanted, ", ".join(names) if names else "(none - only 'neutral')"))


def skills_dir() -> str:
    return os.path.normpath(os.environ.get(SKILLS_DIR_ENV) or os.path.join(SKILL_ROOT, os.pardir))


def discover(root=None) -> list:
    """Every sibling skill's assets/brand.json, sorted. Never doc-builder's own."""
    root = root or skills_dir()
    found = []
    for path in sorted(glob.glob(os.path.join(root, "*", "assets", "brand.json"))):
        skill = os.path.normpath(os.path.join(path, os.pardir, os.pardir))
        if os.path.normcase(skill) == os.path.normcase(SKILL_ROOT):
            continue
        found.append(os.path.normpath(path))
    return found


def _load(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("_comment", None)
    return data


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
        try:
            name = _load(path).get("name") or skill_dir
        except (OSError, ValueError):
            name = skill_dir
        names.append(name)
        if wanted.lower() in (name.lower(), skill_dir.lower()):
            return path, "--brand %s given" % wanted
    raise BrandNotFound(wanted, names)


def resolve(explicit=None, root=None, announce=True) -> Brand:
    """Apply the four rules. Prints the outcome to stderr unless told not to."""
    packs = discover(root)
    wanted = explicit or os.environ.get(BRAND_ENV)
    if wanted:
        path, reason = _match_explicit(wanted, packs)
        if not explicit:
            reason = "%s=%s set in the environment" % (BRAND_ENV, wanted)
    elif len(packs) == 1:
        path, reason = packs[0], "the only brand pack installed under %s" % skills_dir()
    elif len(packs) > 1:
        names = []
        for p in packs:
            try:
                names.append(_load(p).get("name") or os.path.basename(os.path.dirname(os.path.dirname(p))))
            except (OSError, ValueError):
                names.append(os.path.basename(os.path.dirname(os.path.dirname(p))))
        raise BrandAmbiguous(names)
    else:
        path, reason = NEUTRAL_JSON, "no sibling skill under %s supplies assets/brand.json" % skills_dir()
    brand = Brand(path, reason)
    if announce:
        brand.announce()
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
    ap.add_argument("--list", action="store_true", help="list every visible brand pack and exit")
    ap.add_argument("--json", action="store_true", help="print the merged brand values")
    args = ap.parse_args(argv)

    if args.list:
        packs = discover()
        print("neutral  %s  (built in)" % NEUTRAL_JSON)
        for p in packs:
            try:
                name = _load(p).get("name") or "?"
            except (OSError, ValueError) as exc:
                name = "UNREADABLE (%s)" % exc
            print("%-8s %s" % (name, p))
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
