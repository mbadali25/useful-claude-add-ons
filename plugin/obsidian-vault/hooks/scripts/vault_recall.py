"""Read-only recall over configured vaults - the contract crew's context hook calls.

    recall --query TEXT [--vaults A,B] [--project NAME[,NAME]] [--min-terms N]
           [--include-excluded] [--max-chars N] [--timeout-ms MS] [--json]

Pure read: no network, no REST bridge, no writes, no cache. Plain-text scoring
over each note's title (frontmatter `title`, else filename), its headings and
its body, per query term:

    title hit  6      heading hit  3 per heading (max 3)      body hit  1 per line (max 5)

Relevance (T-0083). Query terms are the words of three or more characters that
are not in STOP_WORDS, first MAX_TERMS kept. Terms match whole words only
(`port` is not found in `support`); a note's words are each word and its parts
split on `-`, `.` and `_` (`crew-context.sh` holds `crew`, `context`, `sh` and
the whole word), so `context` finds `crew-context.sh`. A joined query word
(`t-0083`, `vault_recall.py`) is ONE term: it matches the whole joined word or
its parts as one contiguous in-order run (`port-collision` finds `port
collision` and `port-collisions`; never `port ... collision` apart, and
`t-0083` never finds `l-0083`). Plurals: `es` is added or stripped only after
s, x, z, ch or sh, a plain `s` is stripped only when four characters remain
(`news` is not `new`; `bugs` does not find `bug`), and no form is a stop word
(`notes` never finds `not`). CamelCase is not split: `PortCollision` holds no
`port`. A note is a hit only when it holds at least `need` distinct terms: 1
for a query of one or two terms, 2 for three to five, 3 for six or more;
`--min-terms N` sets it (capped at the term count).
`wiki/sessions/archive/` (any letter case) is never read, and a symlinked note
whose real path lies inside it is skipped too; `--include-excluded` turns that
off. A symlinked note whose real path lies outside the vault, or inside a
skipped or dot folder (`.trash`, `.git`, `node_modules`), is always skipped.
Hard links cannot be told from ordinary files, so a hard link into the archive
is read like any other note; Windows junctions are unverified (directory links
are not followed by the walk, but no junction case was run on Windows).
The vault's `.obsidian/app.json` `userIgnoreFilters` are NOT read: their shape
was never checked against a real app.json (spec Unknowns #3, review FIX6).

Ordering is vault priority first: `--vaults a,b` means every hit in `a` ranks
above every hit in `b`, so when the budget runs out it is the lower-priority
vault that loses. Without --vaults the order is the primary vault, then every
`recall`-role vault in config order; when no roles are set at all, the default
vault alone. Inside a vault: project (`match` - frontmatter `project:` or a
path folder equals a `--project` name - then `none`, then `other`, a note whose
`project:` names another project; ranked last, never dropped), then kind
(concept and decision notes, then other notes, then session notes; folder
names compared in any letter case), then score, then path. A folder match can
be a coincidence (a topic folder named like the project); accepted, because it
only promotes a note, never hides one.

Budget: each result carries a `line` - `[vault] path: snippet` - and the sum
of `len(line) + 1` over the returned results never exceeds --max-chars. The
last result may be cut short to fit; `truncated` says whether anything was
dropped or cut.

Bounded time: the walk stops at --timeout-ms (default 1500) or MAX_FILES notes
per vault, and `truncated` is set when either bound was hit. Every vault that
was asked for and could not be read is named in `errors` - an unknown or
ignored vault is never silently skipped.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2

SKIP_DIRS = {".obsidian", ".git", ".trash", "node_modules", ".claude"}
MAX_FILES = 20000
MAX_BYTES = 256 * 1024
MAX_TERMS = 12
SNIPPET_CHARS = 240
MIN_CUT = 40
TERM_RE = re.compile(r"[\w][\w\-.]*", re.UNICODE)
TITLE_RE = re.compile(r"^title:\s*[\"']?(.*?)[\"']?\s*$", re.MULTILINE)
PROJECT_RE = re.compile(r"^project:[ \t]*[\"']?(.*?)[\"']?[ \t]*$", re.MULTILINE)
MIN_TERM_CHARS = 3
STOP_WORDS = frozenset("""
    about after all also and any are because been before both but can could did does each
    for from had has have here how into its just more most not now only other our out over
    should some such than that the their them then there these they this those was were what
    when where which while who why will with would you your
""".split())
ARCHIVE_PREFIX = "wiki/sessions/archive/"
KIND_PREFIXES = (("wiki/concepts/", "concept"), ("wiki/decisions/", "decision"),
                 ("wiki/sessions/", "session"))
KIND_RANK = {"concept": 0, "decision": 0, "other": 1, "session": 2}
PROJECT_RANK = {"match": 0, "none": 1, "other": 2}


PART_RE = re.compile(r"[-._]+")


ES_ENDINGS = ("s", "x", "z", "ch", "sh")
MIN_S_STEM = 4


def parts_of(word):
    return [p for p in PART_RE.split(word) if p]


def terms_of(query):
    """Query terms, in order, first MAX_TERMS kept. A plain word counts when it has
    MIN_TERM_CHARS or more and is not a stop word. A joined word (`t-0083`,
    `vault_recall.py`) stays ONE term, kept when any of its parts would count."""
    seen = []
    for word in TERM_RE.findall(query.lower()):
        word = word.strip(".-")
        if any(len(p) >= MIN_TERM_CHARS and p not in STOP_WORDS for p in parts_of(word)) \
                and word not in seen:
            seen.append(word)
    return seen[:MAX_TERMS]


def variants(term):
    """The words a term matches: itself, its plural (+es only after s, x, z, ch or
    sh, else +s) and, for a plural, its singular (-es by the same rule; -s only
    when MIN_S_STEM characters are left, so `news` never becomes `new`). A form
    that is a stop word is never produced (`notes` never matches `not`)."""
    forms = {term + "es" if term.endswith(ES_ENDINGS) else term + "s"}
    if term.endswith("es") and term[:-2].endswith(ES_ENDINGS):
        forms.add(term[:-2])
    elif term.endswith("s") and not term.endswith("ss") and len(term) - 1 >= MIN_S_STEM:
        forms.add(term[:-1])
    return frozenset({term} | {f for f in forms if f not in STOP_WORDS})


def matcher(term):
    """A test over a text index (words, part sequence). A plain term matches any
    word or word part in one of its variants. A joined term matches the whole
    joined word, or its parts as one contiguous in-order run of the text's part
    sequence (`port-collision` matches `port collision` prose and
    `port-collisions`, never `port ... collision` apart); the last part takes
    plural variants."""
    parts = parts_of(term)
    if len(parts) == 1:
        forms = variants(term)
        return lambda index: not forms.isdisjoint(index[0])
    steps = [frozenset({p}) for p in parts[:-1]] + [variants(parts[-1])]
    width = len(steps)

    def test(index):
        words, seq = index
        if term in words:
            return True
        return any(all(seq[i + k] in steps[k] for k in range(width))
                   for i in range(len(seq) - width + 1))
    return test


def need_for(terms, min_terms=None):
    """Distinct terms a note must hold: 1 for 1-2 terms, 2 for 3-5, 3 for 6+."""
    if not terms:
        return 0
    if min_terms is not None:
        return max(1, min(min_terms, len(terms)))
    return 1 if len(terms) <= 2 else 2 if len(terms) <= 5 else 3


def split_note(text):
    """(title from frontmatter or None, project from frontmatter or "", headings, body)."""
    title, project = None, ""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            found = TITLE_RE.search(text[4:end])
            if found:
                title = found.group(1).strip() or None
            found = PROJECT_RE.search(text[4:end])
            if found:
                project = found.group(1).strip()
            text = text[end + 4:]
    headings, body = [], []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and stripped.lstrip("#").startswith(" "):
            headings.append(stripped.lstrip("#").strip())
        else:
            body.append(stripped)
    return title, project, headings, body


def words_of(text):
    """(words, part sequence) of a text: every whole word and each word's parts
    split on - . _ as a set, and the parts in reading order as a list. CamelCase
    is not split (`PortCollision` holds no `port`)."""
    words, seq = set(), []
    for word in TERM_RE.findall(text.lower()):
        word = word.strip(".-")
        parts = parts_of(word)
        words.add(word)
        words.update(parts)
        seq.extend(parts)
    return words, seq


def score_note(terms, title, headings, body):
    """(score, best body line or None, distinct terms matched). Whole words only."""
    score, matched = 0, 0
    title_w = words_of(title)
    heads_w = [words_of(h) for h in headings]
    body_w = [words_of(b) for b in body]
    tests = [matcher(t) for t in terms]
    for test in tests:
        gained = 6 if test(title_w) else 0
        gained += 3 * min(3, sum(1 for h in heads_w if test(h)))
        gained += min(5, sum(1 for b in body_w if test(b)))
        score += gained
        matched += 1 if gained else 0
    best, best_hits = None, 0
    for raw, index in zip(body, body_w):
        hits = sum(1 for test in tests if test(index))
        if hits > best_hits:
            best, best_hits = raw, hits
    return score, best, matched


def snippet_for(terms, best, headings, title):
    text = best or (headings[0] if headings else title)
    if len(text) <= SNIPPET_CHARS:
        return text
    low = text.lower()
    found = []
    for term in terms:
        parts = parts_of(term)
        forms = variants(term) if len(parts) == 1 else \
            {r"[-._\s]+".join(re.escape(p) for p in parts)}
        for form in forms:  # the first whole-word hit, not a substring
            pattern = form if len(parts) > 1 else re.escape(form)
            hit = re.search(r"(?<![^\W_])" + pattern + r"(?![^\W_])", low)
            if hit:
                found.append(hit.start())
    first = min(found, default=0)
    start = max(0, first - SNIPPET_CHARS // 3)
    return ("..." if start else "") + text[start:start + SNIPPET_CHARS - 3] + "..."


def is_excluded(rel, prefixes):
    """True when a vault-relative path lies under one of the (lowercase) prefixes."""
    low = rel.lower()
    return any(low.startswith(p) for p in prefixes)


def iter_notes(vault_path, prefixes=(), pruned=None):
    """Every .md note, sorted. A directory whose vault-relative path (with a
    trailing /) starts with one of the lowercase `prefixes`, in any letter case,
    is not entered; it is appended to `pruned` when that is a list. Directory
    symlinks are not followed (os.walk's default)."""
    for root, dirs, files in os.walk(vault_path):
        rel_root = os.path.relpath(root, vault_path).replace(os.sep, "/")
        rel_root = "" if rel_root == "." else rel_root + "/"
        keep = []
        for d in sorted(dirs):
            if d in SKIP_DIRS or d.startswith("."):
                continue
            if is_excluded(rel_root + d + "/", prefixes):
                if pruned is not None:
                    pruned.append(rel_root + d)
                continue
            keep.append(d)
        dirs[:] = keep
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield os.path.join(root, name)


def kind_of(rel):
    low = rel.lower()
    for prefix, kind in KIND_PREFIXES:
        if low.startswith(prefix):
            return kind
    return "other"


def project_of(rel, fm_project, projects):
    """match / none / other for one note against the --project names (lowercased)."""
    if not projects:
        return "none"
    value = fm_project.strip().lower()
    if value in projects:
        return "match"
    if any(part.lower() in projects for part in rel.split("/")[:-1]):
        return "match"
    return "other" if value else "none"


def link_target(full, vault_real):
    """For a symlinked note: its real path relative to the vault, or None when it
    resolves outside the vault, into a SKIP_DIRS or dot folder, or cannot be
    resolved. "" for a plain file."""
    if not os.path.islink(full):
        return ""
    try:
        rel = os.path.relpath(os.path.realpath(full), vault_real).replace(os.sep, "/")
    except (OSError, ValueError):  # ValueError: another drive on Windows
        return None
    if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
        return None
    if any(d in SKIP_DIRS or (d.startswith(".") and d != "..") for d in rel.split("/")[:-1]):
        return None
    return rel


def search_vault(name, vault_path, terms, deadline, opts=None):  # pylint: disable=too-many-locals
    """(hits, truncated, stats). Each hit: {vault, path, title, score, snippet,
    kind, project, matched}. stats: {below_floor, excluded_dirs, skipped_links}.
    opts: {need, projects (lowercased), include_excluded}."""
    opts = opts or {}
    need = opts.get("need", 1)
    projects = opts.get("projects") or []
    stats = {"below_floor": 0, "excluded_dirs": 0, "skipped_links": 0}
    prefixes = () if opts.get("include_excluded") else (ARCHIVE_PREFIX,)
    pruned, vault_real = [], os.path.realpath(vault_path)
    hits, truncated, seen = [], False, 0
    for full in iter_notes(vault_path, prefixes, pruned):
        if time.monotonic() > deadline or seen >= MAX_FILES:
            truncated = True
            break
        seen += 1
        target = link_target(full, vault_real)
        if target is None or (target and is_excluded(target, prefixes)):
            stats["skipped_links"] += 1
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_BYTES)
        except OSError:
            continue
        rel = os.path.relpath(full, vault_path).replace(os.sep, "/")
        fm_title, fm_project, headings, body = split_note(text.replace("\r\n", "\n"))
        title = fm_title or os.path.splitext(os.path.basename(full))[0]
        score, best, matched = score_note(terms, title, headings, body)
        if score <= 0:
            continue
        if matched < need:
            stats["below_floor"] += 1
            continue
        hits.append({"vault": name, "path": rel, "title": title, "score": score,
                     "snippet": snippet_for(terms, best, headings, title),
                     "kind": kind_of(rel), "project": project_of(rel, fm_project, projects),
                     "matched": matched})
    hits.sort(key=lambda h: (PROJECT_RANK[h["project"]], KIND_RANK[h["kind"]], -h["score"],
                             h["path"]))
    stats["excluded_dirs"] = len(pruned)
    return hits, truncated, stats


def default_order(vaults):
    """Primary first, then recall-role vaults in config order; default alone if no roles."""
    if not any(e.get("role") for e in vaults.values()):
        name = obsidian_common.default_vault_name()
        return [name] if name else []
    order = [n for n, e in vaults.items() if e.get("role") == "primary"]
    order += [n for n, e in vaults.items() if e.get("role") == "recall"]
    return order


def recall(query, names=None, max_chars=4000, timeout_ms=1500,  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
           projects=None, min_terms=None, include_excluded=False):
    """The recall result as a dict. Never writes, never raises on a bad vault."""
    vaults = obsidian_common.list_vaults()
    terms = terms_of(query)
    projects = list(projects or [])
    opts = {"need": need_for(terms, min_terms), "include_excluded": include_excluded,
            "projects": [p.lower() for p in projects]}
    totals = {"below_floor": 0, "excluded_dirs": 0, "skipped_links": 0}
    errors = []
    order = list(names) if names else default_order(vaults)
    deadline = time.monotonic() + max(timeout_ms, 1) / 1000.0
    ranked, truncated, searched = [], False, []
    for name in order:
        entry = vaults.get(name)
        if entry is None:
            errors.append({"vault": name, "error": "not a configured vault (or its path is "
                                                   "not on disk)"})
            continue
        if entry.get("role") == "ignore":
            errors.append({"vault": name, "error": "role is ignore - not read"})
            continue
        if not terms:
            searched.append(name)
            continue
        hits, cut, stats = search_vault(name, entry["path"], terms, deadline, opts)
        for key, value in stats.items():
            totals[key] += value
        searched.append(name)
        truncated = truncated or cut
        ranked.extend(hits)
    results, used = [], 0
    for hit in ranked:
        line = f"[{hit['vault']}] {hit['path']}: {hit['snippet']}"
        room = max_chars - used - 1
        if len(line) > room:
            truncated = True
            if room >= MIN_CUT:
                keep = room - 3
                hit = dict(hit)
                cut_snip = len(line) - keep
                hit["snippet"] = hit["snippet"][:max(0, len(hit["snippet"]) - cut_snip)] + "..."
                line = f"[{hit['vault']}] {hit['path']}: {hit['snippet']}"
                if len(line) <= room:
                    hit["line"] = line
                    results.append(hit)
                    used += len(line) + 1
            break
        hit = dict(hit, line=line)
        results.append(hit)
        used += len(line) + 1
    return {"query": query, "terms": terms, "vaults": searched, "results": results,
            "chars": used, "max_chars": max_chars, "truncated": truncated,
            "errors": errors, "project": projects, "need": opts["need"], **totals}


def cmd_recall(args, prober):  # pylint: disable=unused-argument
    if args.max_chars < 1:
        print("--max-chars must be positive", file=sys.stderr)
        return EXIT_USAGE
    names = []
    for chunk in args.vaults or []:
        names.extend(n.strip() for n in chunk.split(",") if n.strip())
    if args.min_terms is not None and args.min_terms < 1:
        print("--min-terms must be positive", file=sys.stderr)
        return EXIT_USAGE
    projects = []
    for chunk in args.project or []:
        projects.extend(n.strip() for n in chunk.split(",") if n.strip())
    result = recall(args.query, names or None, args.max_chars, args.timeout_ms,
                    projects=projects, min_terms=args.min_terms,
                    include_excluded=args.include_excluded)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for hit in result["results"]:
            print(hit["line"])
        for err in result["errors"]:
            print(f"[{err['vault']}] ERROR {err['error']}", file=sys.stderr)
        if result["truncated"]:
            print("(truncated)", file=sys.stderr)
    return EXIT_PROBLEMS if result["errors"] else EXIT_OK


def add_parsers(sub):
    s = sub.add_parser("recall", help="read-only ranked snippets from configured vaults "
                                      "(the context-hook contract)")
    s.add_argument("--query", required=True)
    s.add_argument("--vaults", action="append", metavar="A,B",
                   help="vault names in priority order (comma-separated, repeatable)")
    s.add_argument("--project", action="append", metavar="NAME[,NAME]",
                   help="rank notes of this project first (frontmatter project: or a path "
                        "folder; case-insensitive; comma-separated, repeatable)")
    s.add_argument("--min-terms", type=int, default=None, metavar="N",
                   help="distinct query terms a note must hold (default 1/2/3 for "
                        "1-2/3-5/6+ terms; 1 restores the pre-T-0083 floor)")
    s.add_argument("--include-excluded", action="store_true",
                   help="also read wiki/sessions/archive/ (a link out of the vault is "
                        "still skipped)")
    s.add_argument("--max-chars", type=int, default=4000)
    s.add_argument("--timeout-ms", type=int, default=1500)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_recall)
