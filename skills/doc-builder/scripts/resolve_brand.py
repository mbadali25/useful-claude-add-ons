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
import ntpath
import os
import posixpath
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(SCRIPTS_DIR, os.pardir))
NEUTRAL_JSON = os.path.join(SKILL_ROOT, "assets", "brands", "neutral", "brand.json")
THEMES_DIR = os.path.join(SKILL_ROOT, "assets", "themes")
DENSITIES_DIR = os.path.join(SKILL_ROOT, "assets", "densities")
THEME_ENV = "DOC_BUILDER_THEME"
DENSITY_ENV = "DOC_BUILDER_DENSITY"

# A theme or density overlay may set colours and sizes, never identity. These
# stay with the brand pack whatever theme is picked: the logo, the fonts, the
# organisation, the SOP footer and help contact, and every path.
_OVERLAY_SECTIONS = ("report", "sop")
_IDENTITY_SOP_KEYS = frozenset((
    "template", "masters_dir", "assets_dir", "specs_dir", "footer", "help_contact"))
_IDENTITY_REPORT_KEYS = frozenset(("output_dir",))

# The directory holding every installed skill in a checkout. Overridable so the
# discovery rules can be tested against a scratch tree with zero, one and two packs.
SKILLS_DIR_ENV = "DOC_BUILDER_SKILLS_DIR"
BRAND_ENV = "DOC_BUILDER_BRAND"
MASTERS_DIR_ENV = "DOC_BUILDER_MASTERS_DIR"

# How many ancestors of doc-builder's own directory the plugin-cache search
# climbs. Four reaches `cache/` from `cache/<marketplace>/doc-builder/<version>/`
# with one to spare; a drive root is never searched.
CACHE_CLIMB = 4

# A brand pack is authored on whoever's machine measured the values (see
# solomon-doc-builder/assets/brand.json's own _comment) and then committed, so
# a Windows contributor's `C:\repos\...` has to resolve correctly when the
# same pack is read on Linux, and vice versa. `os.path.isabs()` only
# recognises the CURRENT OS's own absolute form, so without this a
# Windows-authored drive path read on POSIX is neither absolute nor relative
# to anything sensible - `_rel()` used to join it onto `assets/` and produce
# a nonsense path that `os.path.isdir()` then correctly, but misleadingly,
# reported as simply "not found".
_WINDOWS_DRIVE_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")

# A rooted, drive-RELATIVE Windows path: `\\bare\\path`, one leading
# backslash, no drive. Matched by its own regex and NOT by `ntpath.isabs()`,
# because Python 3.13 changed `ntpath.isabs()` to return False for exactly
# this shape (gh-44626), so a predicate built on it gives one answer on 3.11
# and 3.12 and the opposite on 3.13+. Same input, same result on every
# version is the whole point of the helper.
_WINDOWS_ROOTED_RE = re.compile(r"^\\")


def abs_or_join(value, base):
    """Resolve `value` against `base` treating "absolute" as OS-independent.

    `os.path.isabs()` only recognises the CURRENT OS's own absolute form, so on
    POSIX a Windows-authored `C:\\repos\\x` is neither absolute nor meaningfully
    relative: `os.path.join(base, value)` appends it as a single path SEGMENT
    and yields `<base>/C:\\repos\\x` - one filename containing a drive letter, a
    colon and backslashes. Nothing raises, so every caller that only stats or
    writes the result reports success on a path nobody will ever look at.

    Per this repo's convention (CLAUDE.md), a Windows drive root and the Linux
    root are the same machine, different OS, so the drive letter is dropped and
    the rest read as POSIX-absolute: `C:\\repos\\x` -> `/repos/x`.

    This is the predicate `Brand._rel()` was fixed with at `67f6fdb5`. It lives
    here, at module level, because three sibling call sites
    (`build_sop.resolve_output`, `build_sop.build_from_spec`'s image branch, and
    `check_conformance._load_spec_map`) were still using the bare
    `os.path.isabs()` form the fix replaced. A fourth copy of the predicate is
    how a fifth call site gets written; there is one copy, and it is this one.

    `value` is assumed non-empty and already expanded - `_rel()` does its own
    `expandvars`/`expanduser` first, and a spec's paths are deliberately NOT
    expanded, so that step stays with the caller that wants it.
    """
    if _WINDOWS_DRIVE_ABS_RE.match(value):
        if os.name == "nt":
            return os.path.normpath(value)
        return posixpath.normpath("/" + ntpath.splitdrive(value)[1].replace("\\", "/").lstrip("/"))
    if os.name != "nt" and _WINDOWS_ROOTED_RE.match(value):
        # A bare `\like\this` (rooted, no drive) - still absolute, not
        # relative to `base`. Covers the `\\server\share` UNC form too.
        return posixpath.normpath(value.replace("\\", "/"))
    return value if os.path.isabs(value) else os.path.normpath(os.path.join(base, value))


class BrandError(SystemExit):
    """Raised as SystemExit so a CLI caller exits non-zero with the message."""


class BrandAmbiguous(BrandError):
    def __init__(self, names, where):
        self.names = list(names)
        super().__init__(
            f"More than one brand pack is installed ({where}): {', '.join(self.names)}.\n"
            f"Pass --brand <name> (or set {BRAND_ENV}) to say which one this document is for.")


class BrandNotFound(BrandError):
    def __init__(self, wanted, names):
        installed = ", ".join(names) if names else "(none - only 'neutral')"
        super().__init__(f"No brand pack named {wanted!r}. "
                         f"Installed: {installed}.")


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
    locs = [(f"sibling skill directories under {skills_dir()}",
             [j(skills_dir(), "*", "assets", "brand.json")])]
    if os.environ.get(SKILLS_DIR_ENV):
        return locs  # a test tree: do not also wander the real machine
    ancestor = SKILL_ROOT
    for _ in range(CACHE_CLIMB):
        parent = os.path.dirname(ancestor)
        if not parent or parent == ancestor or os.path.dirname(parent) == parent:
            break  # reached a drive root; never search that
        ancestor = parent
        locs.append((f"plugin cache beneath {ancestor}", [
            j(ancestor, "*", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "skills", "*", "assets", "brand.json"),
            j(ancestor, "*", "*", "*", "skills", "*", "assets", "brand.json"),
        ]))
    home = os.path.join(os.path.expanduser("~"), ".claude")
    locs.append((f"user skills under {j(home, 'skills')}",
                 [j(home, "skills", "*", "assets", "brand.json")]))
    cache = j(home, "plugins", "cache")
    locs.append((f"user plugin cache under {cache}", [
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
            keep, _drop = sorted([by_name[name], p],
                                 key=os.path.getmtime, reverse=True)
            by_name[name] = keep
            notes.append(f"{name} found in more than one version; using the most recently "
                         f"modified copy ({keep})")
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

    theme = None
    density = None

    def __init__(self, path, reason):
        self.path = os.path.normpath(path)
        self.root = os.path.dirname(self.path)          # .../assets
        self.reason = reason
        neutral = _load(NEUTRAL_JSON)
        pack = neutral if os.path.normcase(self.path) == os.path.normcase(NEUTRAL_JSON) else _load(self.path)
        self.data = _merge(neutral, pack)
        self._notes = []
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
        """A relative path in brand.json is relative to the assets/ directory.

        An absolute path is absolute on whichever OS authored it, not just the
        one resolve_brand.py happens to be running on. A Windows drive path
        (`C:\\repos\\...`) is absolute even when read on Linux; treating it as
        relative here - which `os.path.isabs()` alone would do, since it only
        knows POSIX absolute paths - silently joined it onto `assets/` and
        produced a path that looked plausible but pointed nowhere real.
        Per this repo's own convention (CLAUDE.md), a Windows drive root and
        the Linux root are the same machine, different OS, so the drive
        letter is dropped and the rest read as POSIX-absolute:
        `C:\\repos\\x` -> `/repos/x`.
        """
        if not value:
            return None
        value = os.path.expandvars(os.path.expanduser(str(value)))
        return abs_or_join(value, self.root)

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
                f"The {self.name} brand pack has no masters directory. Pass an explicit path, "
                f"or set {MASTERS_DIR_ENV}.")
        if not os.path.isdir(d):
            raise BrandError(
                f"Masters directory not found: {d}\nSet {MASTERS_DIR_ENV} to point at it, or pass "
                "an explicit path.")
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

    @property
    def logo(self) -> dict:
        return self.data.get("logo") or {}

    def logo_path(self, variant: str):
        """Absolute path for one logo variant key (`on_light`, `on_dark`,
        `icon_on_light` or `icon_on_dark`), or None when the pack does not
        supply it - the neutral pack supplies none, and every caller must
        render correctly with None. Resolved through `_rel()`, so a pack's
        logo path is subject to the exact same relative/absolute rules as
        `template`, `masters_dir` and `assets_dir` - including the Windows
        drive-path fix, since a logo path is authored and committed the same
        way those are."""
        return self._rel(self.logo.get(variant))

    def logo_for(self, background: str):
        """The wordmark logo that reads correctly on `background`, or None.

        `background` is `"light"` (a white or pale page) or `"dark"` (a navy
        or otherwise dark band) - never the logo's own colour, which is the
        opposite of the page it sits on: the `-on-dark` file is the wordmark
        recoloured to read on a DARK background, so a caller rendering a navy
        band must ask for `logo_for("dark")` to get it. Getting this backwards
        is invisible in the way a broken image reference is not - the logo is
        simply the same colour as the page it sits on.
        """
        if background not in ("light", "dark"):
            raise ValueError(f"background must be 'light' or 'dark', got {background!r}")
        return self.logo_path(f"on_{background}")

    def icon_for(self, background: str):
        """The mark-alone icon for `background` - see `logo_for`."""
        if background not in ("light", "dark"):
            raise ValueError(f"background must be 'light' or 'dark', got {background!r}")
        return self.logo_path(f"icon_on_{background}")

    def apply_overlay(self, kind, name, overlay):
        """Merge a theme or density over the resolved brand: colours and sizes
        only (see `_OVERLAY_SECTIONS`), identity untouched."""
        for section in _OVERLAY_SECTIONS:
            values = dict(overlay.get(section) or {})
            banned = _IDENTITY_SOP_KEYS if section == "sop" else _IDENTITY_REPORT_KEYS
            for k in banned & set(values):
                values.pop(k)
            self.data[section] = _merge(self.data[section], values)
        setattr(self, kind, name)

    def describe(self) -> str:
        extra = "".join(f", {k} {getattr(self, k)}" for k in ("theme", "density")
                        if getattr(self, k, None))
        return f"brand: {self.name} -- {self.reason} ({self.path}){extra}"

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
            return path, f"--brand {wanted} given"
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


class OverlayNotFound(Exception):
    def __init__(self, kind, wanted, names):
        super().__init__(f"unknown {kind} {wanted!r} - available: {', '.join(names) or '(none)'}")


def _overlays(directory):
    """{name: path} for every *.json in `directory`, sorted by name."""
    out = {}
    for p in sorted(glob.glob(os.path.join(directory, "*.json"))):
        out[os.path.splitext(os.path.basename(p))[0].lower()] = p
    return out


def list_themes():
    """[(name, label, description)] for every built-in theme."""
    rows = []
    for name, path in _overlays(THEMES_DIR).items():
        data = _load(path)
        rows.append((name, data.get("label") or name, data.get("description") or ""))
    return rows


def list_densities():
    return [(n, _load(p).get("description") or "") for n, p in _overlays(DENSITIES_DIR).items()]


def load_overlay(kind, wanted):
    """The theme or density JSON named `wanted` (case-insensitive; spaces and
    underscores read as hyphens, so "High Contrast" finds high-contrast)."""
    directory = THEMES_DIR if kind == "theme" else DENSITIES_DIR
    found = _overlays(directory)
    key = re.sub(r"[\s_]+", "-", wanted.strip().lower())
    if key not in found:
        raise OverlayNotFound(kind, wanted, sorted(found))
    return key, _load(found[key])


def resolve(explicit=None, root=None, announce=True, theme=None, density=None) -> Brand:
    """Apply the five steps, then the theme and density overlays. Prints the
    outcome to stderr unless told not to.

    Merge order: neutral -> brand pack -> theme -> density. A theme wins on
    colours because it was asked for explicitly; the brand keeps its identity
    (logo, fonts, footer, template, paths) because a theme never carries one."""
    brand = _resolve_pack(explicit, root, announce=False)
    for kind, value, env in (("theme", theme, THEME_ENV), ("density", density, DENSITY_ENV)):
        wanted = value or os.environ.get(env)
        if wanted:
            name, overlay = load_overlay(kind, wanted)
            brand.apply_overlay(kind, name, overlay)
    if announce:
        brand.announce()
        for n in brand._notes:  # pylint: disable=protected-access
            print("brand: note: " + n, file=sys.stderr)
    return brand


def _resolve_pack(explicit=None, root=None, announce=True) -> Brand:
    """Apply the five steps. Prints the outcome to stderr unless told not to."""
    if root:
        os.environ[SKILLS_DIR_ENV] = root
    wanted = explicit or os.environ.get(BRAND_ENV)
    notes = []
    if wanted:
        path, reason = _match_explicit(wanted, _all_packs())
        if not explicit:
            reason = f"{BRAND_ENV}={wanted} set in the environment"
    else:
        packs, label, searched = discover()
        if packs:
            by_name, notes = _dedupe_versions(packs)
            if len(by_name) > 1:
                raise BrandAmbiguous(sorted(by_name), label)
            # Single-element unpack, not `next(iter(...))`: the guard
            # above rules out more than one, and this keeps a loud
            # ValueError if the count is ever neither 1 nor >1.
            # pylint infers `by_name` as possibly empty because it is
            # built in a loop, and cannot see that `if packs:` makes
            # it non-empty -- so the warning is about its inference,
            # not about this line. Dropping the unpack to satisfy it
            # would drop the check it cannot see.
            path, = by_name.values()  # pylint: disable=unbalanced-dict-unpacking
            reason = f"the only brand pack found in {label}"
        else:
            path = NEUTRAL_JSON
            reason = ("no brand pack found - using neutral. Searched: "
                      + "; ".join(searched))
    brand = Brand(path, reason)
    brand._notes.extend(notes)  # pylint: disable=protected-access
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


def add_theme_arguments(parser: argparse.ArgumentParser) -> None:
    """--theme and --density, for the scripts that BUILD a document. The
    checkers and extractors do not take them: they measure a pack's masters."""
    themes = ", ".join(n for n, _, _ in list_themes())
    parser.add_argument(
        "--theme", default=None,
        help=f"built-in colour theme over the brand ({themes}); default: the brand's own "
             f"colours, or {THEME_ENV}")
    parser.add_argument(
        "--density", default=None,
        help=f"spacing and type size ({', '.join(n for n, _ in list_densities())}); "
             f"default: comfortable, or {DENSITY_ENV}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_brand_argument(ap)
    ap.add_argument("--list", action="store_true", help="list every visible brand pack, by location, and exit")
    ap.add_argument("--json", action="store_true", help="print the merged brand values")
    ap.add_argument("--list-themes", action="store_true",
                    help="list the built-in themes and densities, and exit")
    add_theme_arguments(ap)
    args = ap.parse_args(argv)

    if args.list_themes:
        print("themes (--theme):")
        for name, label, desc in list_themes():
            print(f"  {name:<14} {label:<16} {desc}")
        print("\ndensities (--density):")
        for name, desc in list_densities():
            print(f"  {name:<14} {desc}")
        print(f"\ngallery: {os.path.join(THEMES_DIR, 'gallery', 'index.html')}")
        return 0

    if args.list:
        print(f"neutral  {NEUTRAL_JSON}  (built in)")
        for label, patterns in search_locations():
            packs = _glob_many(patterns)
            print(f"\n{label}:")
            for p in packs:
                print(f"  {_pack_name(p)!s:<8} {p}")
            if not packs:
                print("  (none)")
        return 0

    brand = resolve(args.brand, announce=not args.json, theme=args.theme,
                    density=args.density)
    if args.json:
        print(json.dumps(brand.data, indent=2))
    else:
        print(f"template    : {(brand.template or '(synthesised from brand.json)')}")
        masters = brand.masters_dir
        state = "" if not masters else ("" if os.path.isdir(masters) else "  (NOT FOUND on this machine)")
        print(f"masters_dir : {masters or '(none - pass an output path)'}{state}")
        assets = brand.assets_dir
        astate = "" if not assets else ("" if os.path.isdir(assets) else "  (NOT FOUND on this machine)")
        print(f"assets_dir  : {assets or '(none)'}{astate}")
        print(f"specs_dir   : {(brand.specs_dir or '(none)')}")
        print(f"reports     : {brand.report_output_dir}/")
        logo_dark = brand.logo_for("dark")
        lstate = "" if not logo_dark else ("" if os.path.isfile(logo_dark) else "  (NOT FOUND on this machine)")
        print(f"logo (dark) : {logo_dark or '(none)'}{lstate}")
        logo_light = brand.logo_for("light")
        lstate = "" if not logo_light else ("" if os.path.isfile(logo_light) else "  (NOT FOUND on this machine)")
        print(f"logo (light): {logo_light or '(none)'}{lstate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
