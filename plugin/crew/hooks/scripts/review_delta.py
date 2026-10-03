#!/usr/bin/env python3
"""The delta gate (L-0522): keep an accepted review receipt across a catch-up
merge that adds none of the ticket's own code.

`review_ledger.check_receipt` keeps a receipt when the bundle rebuilt now has
the hash the review accepted (the fast path). A `git merge` of the
integration branch moves that hash even when no ticket line moved, because the
bundle is diffed from the ticket's start. This module decides, only after the
fast path has failed, whether the ticket's OWN delta is unchanged. Every check
below either proves its condition or answers stale; "could not tell" is a
stale reason of its own and never a keep (root CLAUDE.md, Lessons).

CHECK E (`excluded_check`), run by `check_receipt` before EITHER success
return. The bundle leaves `.work/`, `graphify-out/` and `.crew/metrics.md` out
(`review_patch.EXCLUDED`), so a change there is invisible to its hash. Three
ranges are diffed on those paths alone: receipt base -> reviewed head (what
the reviewer was never shown), reviewed head -> HEAD (what lands) and reviewed
head -> the index (what the next commit lands; untracked files never do, and
crew writes some there itself, so not the `add -A` working state). Every entry must be
one of `EXCLUDED_EXCEPTIONS`, status M, mode 100644 both sides, not binary.

THE DELTA GATE (`judge`), in order:
 1. The reviewed head `H_r` is the latest round row's `head`: a full sha and a
    commit here.
 2. The reviewed bytes were exactly `H_r`'s tree: the bundle rebuilt from the
    receipt base to `H_r^{tree}` has the receipt's hash. A review of a dirty
    tree fails this - its bytes cannot be reconstructed.
 3. `H_r` is an ancestor of HEAD (no rebase, reset or amend since).
 4. The integration base is ONE commit `R`: the `base_sha` the caller pinned
    (`check_land` passes the sha it fetched), else this ticket's merge-train
    entry's ref, resolved once. `scope_base._default_ref` is never used: it is
    a guess, not the landing target. Exactly one merge base `M` of HEAD and
    `R`; the new base `B_c` is `M` when the receipt base is its ancestor, the
    receipt base when `M` is its ancestor (bump only), else stale.
 5. A clean checkout: `git status` empty, no skip-worktree or
    assume-unchanged entry, no unmerged entry, no gitlink in any tree judged.
    The guarantee is git tree bytes; HEAD's tree is what `check_land` lands.
 6. `D_r` = receipt base -> `H_r^{tree}`; `D_c` = `B_c` -> `HEAD^{tree}`.
 7. Check E has passed (above).
 8. Interdiff: every path not exempt is in both deltas with equal status,
    source path, modes and blob ids (byte identity of both ends).
 9. The allowlist (`EXEMPT_*`, constants, case-sensitive segment match with
    `fnmatch.fnmatchcase`): code maps, rules and diagrams compared with only
    their anchor sha normalised; four prose bookkeeping files exempt in full;
    manifests compared byte for byte outside the version tokens of the plugin
    being bumped.
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile

import crew_freshness
import review_patch

# Reason prefix for a code map, rules file or diagram whose bytes moved beyond
# its anchor sha. crew_autopilot routes on it (a refresh that did more than
# re-anchor stops for a human instead of spending a review round).
ANCHORED_BEYOND = "anchored artifact changed beyond its anchor"
COULD_NOT_TELL = "could not tell"

EXEMPT_ANCHORED = {
    "codemap": (".crew/codemap/**/*.md",),
    "rules": (".claude/rules/**/*.md",),
    "diagram": ("docs/diagrams/**/*.md", "docs/diagrams/**/*.mmd"),
}
EXEMPT_PROSE = ("CHANGELOG.md", "TODO.md", "plugin/PLUGINS.md", "plugin/*/BUDGETS.md")
EXEMPT_MANIFEST = (".claude-plugin/marketplace.json", "plugin/*/.claude-plugin/plugin.json",
                   "skills/*/.claude-plugin/plugin.json")
MARKETPLACE = ".claude-plugin/marketplace.json"
EXCLUDED_PATHS = (".work", "graphify-out", ".crew/metrics.md")
EXCLUDED_EXCEPTIONS = ("graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md")

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_NULL_ID = "0" * 40
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_RAW_VERSION_TOKEN = re.compile(rb'^"[0-9]+\.[0-9]+\.[0-9]+"$')
_VERSION_PLACEHOLDER = b'"\\u0000VERSION"'
_DIAGRAM_HEADER_FORMS = (
    re.compile(r"^%% anchor: \S+@[0-9a-f]{7,40}$"),
    re.compile(r"^%% Generated from \S+@[0-9a-f]{7,40} on \d{4}-\d{2}-\d{2}\. "
               r"Verify before trusting\.$"),
)
# crew_instructions.render_rule's two anchor-bearing lines.
_RULE_HEADER = re.compile(r"^<!-- crew:generated source=(\S+) sha256=([0-9a-f]+) -- do not "
                          r"hand-edit; regenerate with crew_instructions\.py rules -->$",
                          re.MULTILINE)
_RULE_ANCHOR = re.compile(r"^Code map anchor `([0-9a-f]{7,40})`; if it is behind HEAD, re-check "
                          r"with `git diff --name-only ([0-9a-f]{7,40})\.\.HEAD -- <cited "
                          r"paths>`\.$", re.MULTILINE)
_JSON_SCALAR = re.compile(rb"true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_EXEMPT_STATUS = ("A", "M")
_EXEMPT_OLD_MODES = ("100644", "000000")
_EXEMPT_NEW_MODE = "100644"


class Stale(Exception):
    """A check that did not hold; its message is the stale reason."""


# --------------------------------------------------------------------------
# git

def _git(root, args, env=None):
    """(exit code, stdout bytes, stderr text). Never raises for a nonzero
    exit; raises RuntimeError when git cannot run at all."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        done = subprocess.run(["git", "-C", root] + list(args), capture_output=True,
                              timeout=review_patch.GIT_TIMEOUT, env=full_env, check=False,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} could not run: {exc}") from exc
    return done.returncode, done.stdout, done.stderr.decode("utf-8", errors="replace").strip()


def _ok(root, args, env=None):
    """stdout text of a git call that must succeed (RuntimeError otherwise)."""
    return review_patch._run(root, args, env=env)  # pylint: disable=protected-access


def _commit(root, sha, what):
    """`sha` verified as a full commit id here, else Stale."""
    if not isinstance(sha, str) or not _FULL_SHA.match(sha):
        raise Stale(f"{what} {sha!r} is not a full commit sha")
    code, out, err = _git(root, ["rev-parse", "--verify", "--quiet", "--end-of-options",
                                 f"{sha}^{{commit}}"])
    if code != 0 or out.decode().strip() != sha:
        raise Stale(f"{what} {sha[:12]} is not a commit in this clone{(': ' + err) if err else ''}")
    return sha


def _tree(root, rev):
    return _ok(root, ["rev-parse", "--verify", f"{rev}^{{tree}}"]).strip()


def _is_ancestor(root, a, b):
    """True / False; RuntimeError when git cannot say."""
    code, _out, err = _git(root, ["merge-base", "--is-ancestor", a, b])
    if code in (0, 1):
        return code == 0
    raise RuntimeError(f"git merge-base --is-ancestor {a[:12]} {b[:12]} failed ({code}): {err}")


def _blob(root, blob_id):
    """The blob's bytes, or None for the null id (an absent side)."""
    if not blob_id or blob_id == _NULL_ID:
        return None
    return review_patch._run_raw(root, ["cat-file", "blob", blob_id])  # pylint: disable=protected-access


def working_tree(root):
    """The working state as a tree id: the temporary-index `add -A` +
    `write-tree` `review_patch.compute` builds, never touching the real index.
    Kept for the sabotage control that judges the working state instead of
    HEAD's tree; the gate itself never reads it."""
    real_index = _ok(root, ["rev-parse", "--git-path", "index"]).strip()
    if not os.path.isabs(real_index):
        real_index = os.path.join(root, real_index)
    tmp_dir = tempfile.mkdtemp(prefix="review-delta-")
    tmp_index = os.path.join(tmp_dir, "index")
    try:
        if os.path.exists(real_index):
            shutil.copy2(real_index, tmp_index)
        env = {"GIT_INDEX_FILE": tmp_index}
        _ok(root, ["add", "-A", "--", "."], env=env)
        return _ok(root, ["write-tree"], env=env).strip()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def index_tree(root):
    """The real index as a tree id (`git write-tree`, which reads the index
    and writes only tree objects): what the next commit would land. Check E
    judges this rather than the `add -A` working state, because crew itself
    writes untracked files under the excluded paths - `.crew/metrics.md` after
    every review, `.work/` ticket files - in a repository that does not
    gitignore them, and an untracked file never lands."""
    return _ok(root, ["write-tree"]).strip()


def tree_bundle_sha256(root, base, tree):
    """The bundle hash `review_patch.compute` would give `base -> tree`: the
    same diff flags, exclusions and part split, with no working state."""
    only = ["--", "."] + review_patch._EXCLUDE_SPEC  # pylint: disable=protected-access
    patch = review_patch._run_raw(root, ["diff"] + review_patch._DIFF_FLAGS  # pylint: disable=protected-access
                                  + [base, tree] + only)
    parts = review_patch.split_parts(patch, review_patch.DEFAULT_MAX_PART_BYTES)
    return review_patch.bundle_sha256(parts) if parts else None


# --------------------------------------------------------------------------
# check E: the excluded paths

def _numstat(raw):
    """`git diff --numstat -z --no-renames` -> {path: (added, deleted)}."""
    rows = {}
    for rec in raw.decode("utf-8", errors="surrogateescape").split("\0"):
        if not rec:
            continue
        added, deleted, path = rec.split("\t", 2)
        if path in rows:
            raise RuntimeError(f"numstat lists {path!r} twice")
        rows[path] = (added, deleted)
    return rows


def _excluded_problem(root, a, b, label):
    """Why the excluded paths changed unacceptably between trees `a` and `b`,
    or None."""
    spec = ["--"] + list(EXCLUDED_PATHS)
    flags = ["--no-renames", "--no-ext-diff", "--no-textconv", "--no-abbrev", "-z"]
    raw = review_patch._run_raw(root, ["diff", "--raw"] + flags + [a, b] + spec)  # pylint: disable=protected-access
    stat = review_patch._run_raw(root, ["diff", "--numstat"] + flags + [a, b] + spec)  # pylint: disable=protected-access
    entries = review_patch._parse_raw(raw)  # pylint: disable=protected-access
    rows = _numstat(stat)
    if {e["path"] for e in entries} != set(rows):
        return f"{COULD_NOT_TELL}: raw and numstat disagree on the excluded paths ({label})"
    for entry in entries:
        path = entry["path"]
        added, deleted = rows[path]
        binary = (added, deleted) == ("-", "-")
        if (path not in EXCLUDED_EXCEPTIONS or entry["status"] != "M"
                or entry["old_mode"] != "100644" or entry["new_mode"] != "100644" or binary):
            return f"excluded path changed: {path} ({label})"
    return None


def excluded_check(root, receipt, row):
    """(ok, reason). Check E: see the module docstring."""
    try:
        head = _commit(root, (row or {}).get("head"), "reviewed head")
        base = _commit(root, (receipt or {}).get("base"), "receipt base")
        head_tree = _tree(root, head)
        ranges = ((_tree(root, base), head_tree, "receipt base -> reviewed head"),
                  (head_tree, _tree(root, "HEAD"), "reviewed head -> HEAD"),
                  (head_tree, index_tree(root), "reviewed head -> index"))
        for a, b, label in ranges:
            problem = _excluded_problem(root, a, b, label)
            if problem:
                return False, problem
    except Stale as exc:
        return False, f"{COULD_NOT_TELL}: no reviewed head to check excluded paths against: {exc}"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Fail closed: whatever went wrong, an unproven check is stale.
        return False, f"{COULD_NOT_TELL}: excluded paths: {exc}"
    return True, "excluded paths unchanged"


def valid_base_sha(root, sha):
    """(ok, reason) for a pinned integration base."""
    try:
        _commit(root, sha, "base_sha")
    except Stale as exc:
        return False, str(exc)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return False, f"{COULD_NOT_TELL}: base_sha: {exc}"
    return True, "base_sha is a commit"


# --------------------------------------------------------------------------
# steps 4 and 5

def integration_ref(root, ticket):
    """The ref this ticket lands on: its merge-train entry's base, held from
    this worktree. Stale when the train cannot name exactly one."""
    import crew_train  # pylint: disable=import-outside-toplevel  # crew_train imports review_ledger
    top = os.path.realpath(_ok(root, ["rev-parse", "--show-toplevel"]).strip())
    state, where, why = crew_train.load(top)
    if where != "ok":
        raise Stale(f"{COULD_NOT_TELL}: no train entry binds the integration ref ({where}: {why})")
    mine = [e for e in state["entries"] if e.get("ticket") == ticket]
    if len(mine) != 1:
        raise Stale(f"{COULD_NOT_TELL}: no train entry binds the integration ref "
                    f"({len(mine)} entries for {ticket})")
    if os.path.realpath(mine[0].get("worktree") or "") != top:
        raise Stale(f"{COULD_NOT_TELL}: no train entry binds the integration ref ({ticket} is "
                    f"held from {mine[0].get('worktree')}, not this worktree)")
    return mine[0]["base"]


def _resolve(root, ref):
    code, out, err = _git(root, ["rev-parse", "--verify", "--quiet", "--end-of-options",
                                 f"{ref}^{{commit}}"])
    if code != 0:
        raise Stale(f"{COULD_NOT_TELL}: integration ref {ref!r} names no commit ({err or code})")
    return out.decode().strip()


def _clean_head_tree(root):
    """(HEAD's tree, problem): the ONE place the clean-checkout status check
    runs. The delta gate judges HEAD's tree only when the checkout is clean."""
    status = _ok(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",
                        "--ignore-submodules=none"])
    first = next((rec for rec in status.split("\0") if rec), None)
    if first:
        return None, f"the checkout is not clean ({first[3:]!r} {first[:2].strip()})"
    return _tree(root, "HEAD"), None


def checkout_problem(root, trees):
    """Why the working state cannot be proven equal to HEAD's tree (beyond
    `git status`), or None."""
    for rec in _ok(root, ["ls-files", "-v", "-z"]).split("\0"):
        if rec and (rec[0] == "S" or rec[0].islower()):
            return f"index entry {rec[2:]!r} is skip-worktree or assume-unchanged"
    if _ok(root, ["ls-files", "-u", "-z"]).strip("\0"):
        return "the index has unmerged entries"
    for tree in trees:
        for rec in _ok(root, ["ls-tree", "-r", "-z", tree]).split("\0"):
            if rec.startswith(review_patch.SUBMODULE_MODE + " "):
                return f"gitlink {rec.split(chr(9), 1)[-1]!r} in tree {tree[:12]}"
    return None


# --------------------------------------------------------------------------
# steps 6 and 8

def delta(root, a, b):
    """{path: entry} for `a -> b` with review_patch's flags and exclusions."""
    out = {}
    for entry in review_patch._entries(root, a, b):  # pylint: disable=protected-access
        if entry["path"] in out:
            raise RuntimeError(f"the diff lists {entry['path']!r} twice")
        out[entry["path"]] = entry
    return out


def _identity(entry):
    src = entry["old_path"] if entry["status"] in ("R", "C") else None
    return (entry["status"], src, entry["old_mode"], entry["new_mode"], entry["old_id"],
            entry["new_id"])


# --------------------------------------------------------------------------
# step 9: the allowlist

def _match(path, pattern):
    """Whole-segment, case-sensitive glob match: `*` within one segment, `**`
    zero or more whole segments. Never `fnmatch.fnmatch` (it folds case on
    Windows) and never `crew_ticket.glob_match` (which uses it)."""
    names, pat = path.split("/"), pattern.split("/")

    def walk(i, j):
        if i == len(pat):
            return j == len(names)
        if pat[i] == "**":
            return any(walk(i + 1, k) for k in range(j, len(names) + 1))
        return j < len(names) and fnmatch.fnmatchcase(names[j], pat[i]) and walk(i + 1, j + 1)

    return walk(0, 0)


def _exempt_class(path):
    for cls, patterns in EXEMPT_ANCHORED.items():
        if any(_match(path, p) for p in patterns):
            return cls
    if any(_match(path, p) for p in EXEMPT_PROSE):
        return "prose"
    if any(_match(path, p) for p in EXEMPT_MANIFEST):
        return "manifest"
    return None


def _shape_ok(entry):
    return (entry["status"] in _EXEMPT_STATUS and entry["old_mode"] in _EXEMPT_OLD_MODES
            and entry["new_mode"] == _EXEMPT_NEW_MODE and not entry["binary"]
            and not entry["submodule"])


def _replace_spans(text, spans):
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + "\0anchor\0" + text[end:]
    return text


def _anchor_normalised(cls, text):
    """`text` with only its anchor sha replaced, or None when the anchor
    metadata is missing, repeated or malformed (not-exempt)."""
    if cls == "codemap":
        found = list(crew_freshness._ANCHOR_RE.finditer(text))  # pylint: disable=protected-access
        return _replace_spans(text, [found[0].span(1)]) if len(found) == 1 else None
    if cls == "diagram":
        found = list(crew_freshness._DIAGRAM_ANCHOR_RE.finditer(text))  # pylint: disable=protected-access
        if len(found) != 1:
            return None
        start = text.rfind("\n", 0, found[0].start()) + 1
        end = text.find("\n", found[0].end())
        line = text[start:end if end >= 0 else len(text)]
        if not any(form.fullmatch(line) for form in _DIAGRAM_HEADER_FORMS):
            return None
        return _replace_spans(text, [found[0].span(1)])
    headers = list(_RULE_HEADER.finditer(text))
    anchors = list(_RULE_ANCHOR.finditer(text))
    if len(headers) != 1 or len(anchors) != 1 or anchors[0].group(1) != anchors[0].group(2):
        return None
    return _replace_spans(text, [headers[0].span(2), anchors[0].span(1), anchors[0].span(2)])


def _rule_source(text):
    found = list(_RULE_HEADER.finditer(text or ""))
    return found[0].group(1) if len(found) == 1 else None


def _decoded(root, blob_id):
    data = _blob(root, blob_id)
    return None if data is None else data.decode("utf-8")


def _anchored_ok(root, cls, er, ec):
    """True when the path's change is the reviewed one, modulo anchor shas:
    both sides with equal normalised (old, new), or one side whose normalised
    old equals its normalised new (an anchor-only change)."""
    def norm(entry):
        old, new = _decoded(root, entry["old_id"]), _decoded(root, entry["new_id"])
        return (None if old is None else _anchor_normalised(cls, old),
                None if new is None else _anchor_normalised(cls, new), old, new)

    sides = [norm(e) for e in (er, ec) if e is not None]
    if any(n_new is None or (n_old is None and old is not None) for n_old, n_new, old, _ in sides):
        return False
    if er is not None and ec is not None:
        if er["status"] != ec["status"]:
            return False
        return sides[0][:2] == sides[1][:2]
    n_old, n_new = sides[0][:2]
    return n_old is not None and n_old == n_new


# --- manifests -------------------------------------------------------------

def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key")
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f"non-JSON constant {name}")


def _json_spans(raw):
    """{key path: [(start, end), ...]} for every string value in the raw JSON
    bytes, offsets into `raw` itself (never str indices: a multibyte
    character before a version would displace them). Raises ValueError on
    anything that is not one JSON value."""
    spans, pos = {}, 0
    n = len(raw)

    def ws(i):
        while i < n and raw[i] in b" \t\r\n":
            i += 1
        return i

    def string(i):
        if raw[i:i + 1] != b'"':
            raise ValueError(f"expected a string at byte {i}")
        j = i + 1
        while j < n:
            ch = raw[j]
            if ch == 0x5C:
                j += 2
                continue
            if ch == 0x22:
                return j + 1
            j += 1
        raise ValueError("unterminated string")

    def value(i, path):
        i = ws(i)
        if i >= n:
            raise ValueError("unexpected end")
        ch = raw[i:i + 1]
        if ch == b'"':
            end = string(i)
            spans.setdefault(path, []).append((i, end))
            return end
        if ch == b"{":
            i = ws(i + 1)
            if raw[i:i + 1] == b"}":
                return i + 1
            while True:
                i = ws(i)
                key_end = string(i)
                key = json.loads(raw[i:key_end].decode("utf-8"))
                i = ws(key_end)
                if raw[i:i + 1] != b":":
                    raise ValueError(f"expected ':' at byte {i}")
                i = ws(value(i + 1, path + (key,)))
                if raw[i:i + 1] == b",":
                    i += 1
                    continue
                if raw[i:i + 1] == b"}":
                    return i + 1
                raise ValueError(f"expected ',' or '}}' at byte {i}")
        if ch == b"[":
            i = ws(i + 1)
            if raw[i:i + 1] == b"]":
                return i + 1
            index = 0
            while True:
                i = ws(value(i, path + (index,)))
                index += 1
                if raw[i:i + 1] == b",":
                    i += 1
                    continue
                if raw[i:i + 1] == b"]":
                    return i + 1
                raise ValueError(f"expected ',' or ']' at byte {i}")
        match = _JSON_SCALAR.match(raw, i)
        if not match:
            raise ValueError(f"unexpected byte at {i}")
        return match.end()

    pos = ws(value(0, ()))
    if pos != n:
        raise ValueError("trailing bytes after the JSON value")
    return spans


def _strip_spans(raw, spans):
    for start, end in sorted(spans, reverse=True):
        raw = raw[:start] + _VERSION_PLACEHOLDER + raw[end:]
    return raw


def _comparable(raw, spans):
    return _strip_spans(raw, spans)


def _parse(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dupes,
                      parse_constant=_reject_constant)


def _plugin_version(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("version"), str) \
            or not _SEMVER.match(doc["version"]):
        raise ValueError("no semver top-level version")
    return doc["version"]


def _manifest_name(path):
    parts = path.split("/")
    return parts[1] if len(parts) == 4 and parts[0] in ("plugin", "skills") else None


def _version_spans(raw, locations):
    """Byte spans of the allowed version tokens; ValueError when the scanner
    does not find each exactly once or the raw token is not a plain x.y.z."""
    spans = _json_spans(raw)
    found = []
    for loc in locations:
        hits = spans.get(loc, [])
        if len(hits) != 1:
            raise ValueError(f"version location {loc} found {len(hits)} times")
        start, end = hits[0]
        if not _RAW_VERSION_TOKEN.match(raw[start:end]):
            raise ValueError(f"version token at {loc} is not a plain x.y.z")
        found.append(hits[0])
    return found


def _manifest_version_only(root, path, entry, side):
    """True when this side's change to manifest `path` is version-only:
    `side` is that delta's {path: entry}, used for the marketplace binding."""
    old_raw, new_raw = _blob(root, entry["old_id"]), _blob(root, entry["new_id"])
    if old_raw is None or new_raw is None:
        return False
    try:
        old, new = _parse(old_raw), _parse(new_raw)
        if path != MARKETPLACE:
            _plugin_version(old)
            _plugin_version(new)
            locations = [("version",)]
        else:
            locations = _marketplace_locations(root, old, new, side)
        old_spans = _version_spans(old_raw, locations)
        new_spans = _version_spans(new_raw, locations)
    except (ValueError, UnicodeDecodeError, RuntimeError):
        return False
    return _comparable(old_raw, old_spans) == _comparable(new_raw, new_spans)


def _marketplace_locations(root, old, new, side):
    def names(doc):
        if not isinstance(doc, dict) or not isinstance(doc.get("plugins"), list) or not all(
                isinstance(p, dict) and isinstance(p.get("name"), str) for p in doc["plugins"]):
            raise ValueError("marketplace shape")
        return [p["name"] for p in doc["plugins"]]

    if names(old) != names(new):
        raise ValueError("marketplace plugins list changed")
    bumped = {}
    for other_path, other in side.items():
        name = _manifest_name(other_path)
        if name and any(_match(other_path, p) for p in EXEMPT_MANIFEST[1:]):
            if _shape_ok(other) and _manifest_version_only(root, other_path, other, side):
                bumped[name] = _plugin_version(_parse(_blob(root, other["new_id"])))
    locations = []
    for i, entry in enumerate(new["plugins"]):
        if entry["name"] in bumped:
            if entry.get("version") != bumped[entry["name"]]:
                raise ValueError(f"marketplace {entry['name']} version is not its plugin.json's")
            locations.append(("plugins", i, "version"))
    return locations


def _exempt(root, path, er, ec, d_r, d_c, judged):
    """(how, ok): `how` is 'anchor-only', 'exempt' or None (not on the
    allowlist, or failing its shape); `ok` is the class rule's answer."""
    cls = _exempt_class(path)
    present = [e for e in (er, ec) if e is not None]
    if cls is None or not all(_shape_ok(e) for e in present):
        return None, False
    if cls == "prose":
        return "exempt", True
    if cls == "manifest":
        ok = all(_manifest_version_only(root, path, e, side)
                 for e, side in ((er, d_r), (ec, d_c)) if e is not None)
        return ("exempt", True) if ok else (None, False)
    if not _anchored_ok(root, cls, er, ec):
        return "anchor-only", False
    if cls == "rules":
        sources = {_rule_source(_decoded(root, e[k])) for e in present
                   for k in ("old_id", "new_id") if e[k] != _NULL_ID}
        if len(sources) != 1:
            return "anchor-only", False
        source = sources.pop()
        if judged.get(source) is not True or _exempt_class(source or "") != "codemap":
            return "anchor-only", False
    return "anchor-only", True


# --------------------------------------------------------------------------
# the gate

def judge(root, ticket, receipt, row, base_sha=None):
    """(kept, reason, detail). See the module docstring; check E and the
    base_sha validation have already passed in `check_receipt`."""
    try:
        return _judge(root, ticket, receipt, row, base_sha)
    except Stale as exc:
        return False, str(exc), None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Fail closed: an unproven check is stale, never kept.
        return False, f"{COULD_NOT_TELL}: {exc}", None


def _judge(root, ticket, receipt, row, base_sha):  # pylint: disable=too-many-locals
    head = _commit(root, (row or {}).get("head"), "reviewed head")
    base = _commit(root, receipt.get("base"), "receipt base")
    head_tree = _tree(root, head)
    if tree_bundle_sha256(root, base, head_tree) != receipt.get("bundle_sha256"):
        raise Stale("the reviewed head's tree does not rebuild the reviewed bundle (a review "
                    "of uncommitted bytes cannot be reconstructed)")
    if not _is_ancestor(root, head, "HEAD"):
        raise Stale(f"reviewed head {head[:12]} is not an ancestor of HEAD (rebase, reset or "
                    "amend since the review)")
    ref = integration_ref(root, ticket)
    R = base_sha or _resolve(root, ref)  # pylint: disable=invalid-name
    merge_bases = _ok(root, ["merge-base", "--all", "HEAD", R]).split()
    if len(merge_bases) != 1:
        raise Stale(f"HEAD and {R[:12]} have {len(merge_bases)} merge bases, not one")
    mb = merge_bases[0]
    if _is_ancestor(root, base, mb):
        new_base = mb
    elif _is_ancestor(root, mb, base):
        new_base = base
    else:
        raise Stale(f"receipt base {base[:12]} and merge base {mb[:12]} are unrelated")
    tree, problem = _clean_head_tree(root)
    if problem:
        raise Stale(problem)
    problem = checkout_problem(root, [head_tree, _tree(root, R), tree])
    if problem:
        raise Stale(problem)
    d_r, d_c = delta(root, base, head_tree), delta(root, new_base, tree)
    identical, anchor_only, exempt, judged = [], [], [], {}
    keys = sorted(set(d_r) | set(d_c))
    # Code maps first, so a rules file can ask whether its source map passed.
    keys.sort(key=lambda k: _exempt_class(k) != "codemap")
    for path in keys:
        er, ec = d_r.get(path), d_c.get(path)
        how, ok = _exempt(root, path, er, ec, d_r, d_c, judged)
        judged[path] = ok
        if how == "anchor-only" and not ok:
            # Byte identity across both deltas still keeps it (a map with no
            # anchor line, such as INDEX.md, reviewed and unchanged since).
            if er is not None and ec is not None and _identity(er) == _identity(ec):
                identical.append(path)
                continue
            raise Stale(f"{ANCHORED_BEYOND}: {path}")
        if how is not None and ok:
            (anchor_only if how == "anchor-only" else exempt).append(path)
            continue
        if er is None or ec is None:
            where = ("not in the reviewed delta" if er is None
                     else "reviewed but gone from the current delta")
            raise Stale(f"{path} is {where}")
        if _identity(er) != _identity(ec):
            raise Stale(f"{path} differs from the reviewed change (status, modes or blob ids)")
        identical.append(path)
    return True, "kept", {"head": head, "base": new_base, "ref": ref, "identical": identical,
                          "anchor_only": anchor_only, "exempt": exempt}
