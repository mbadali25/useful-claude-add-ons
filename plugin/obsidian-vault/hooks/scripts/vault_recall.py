"""Read-only recall over configured vaults - the contract crew's context hook calls.

    recall --query TEXT [--vaults A,B] [--max-chars N] [--timeout-ms MS] [--json]

Pure read: no network, no REST bridge, no writes, no cache. Plain-text scoring
over each note's title (frontmatter `title`, else filename), its headings and
its body, per query term:

    title hit  6      heading hit  3 per heading (max 3)      body hit  1 per line (max 5)

Ordering is vault priority first, then score: `--vaults a,b` means every hit in
`a` ranks above every hit in `b`, so when the budget runs out it is the
lower-priority vault that loses. Without --vaults the order is the primary
vault, then every `recall`-role vault in config order; when no roles are set at
all, the default vault alone.

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


def terms_of(query):
    seen = []
    for term in TERM_RE.findall(query.lower()):
        term = term.strip(".-")
        if len(term) >= 2 and term not in seen:
            seen.append(term)
    return seen[:MAX_TERMS]


def split_note(text):
    """(title from frontmatter or None, headings, body lines)."""
    title = None
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            found = TITLE_RE.search(text[4:end])
            if found:
                title = found.group(1).strip() or None
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
    return title, headings, body


def score_note(terms, title, headings, body):
    """(score, best body line or None)."""
    score = 0
    title_l = title.lower()
    heads_l = [h.lower() for h in headings]
    body_l = [b.lower() for b in body]
    for term in terms:
        if term in title_l:
            score += 6
        score += 3 * min(3, sum(1 for h in heads_l if term in h))
        score += min(5, sum(1 for b in body_l if term in b))
    best, best_hits = None, 0
    for raw, low in zip(body, body_l):
        hits = sum(1 for t in terms if t in low)
        if hits > best_hits:
            best, best_hits = raw, hits
    return score, best


def snippet_for(terms, best, headings, title):
    text = best or (headings[0] if headings else title)
    if len(text) <= SNIPPET_CHARS:
        return text
    low = text.lower()
    first = min((low.find(t) for t in terms if t in low), default=0)
    start = max(0, first - SNIPPET_CHARS // 3)
    return ("..." if start else "") + text[start:start + SNIPPET_CHARS - 3] + "..."


def iter_notes(vault_path):
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield os.path.join(root, name)


def search_vault(name, vault_path, terms, deadline):
    """(hits, truncated). Each hit: {vault, path, title, score, snippet}."""
    hits, truncated, seen = [], False, 0
    for full in iter_notes(vault_path):
        if time.monotonic() > deadline or seen >= MAX_FILES:
            truncated = True
            break
        seen += 1
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_BYTES)
        except OSError:
            continue
        rel = os.path.relpath(full, vault_path).replace(os.sep, "/")
        fm_title, headings, body = split_note(text.replace("\r\n", "\n"))
        title = fm_title or os.path.splitext(os.path.basename(full))[0]
        score, best = score_note(terms, title, headings, body)
        if score <= 0:
            continue
        hits.append({"vault": name, "path": rel, "title": title, "score": score,
                     "snippet": snippet_for(terms, best, headings, title)})
    hits.sort(key=lambda h: (-h["score"], h["path"]))
    return hits, truncated


def default_order(vaults):
    """Primary first, then recall-role vaults in config order; default alone if no roles."""
    if not any(e.get("role") for e in vaults.values()):
        name = obsidian_common.default_vault_name()
        return [name] if name else []
    order = [n for n, e in vaults.items() if e.get("role") == "primary"]
    order += [n for n, e in vaults.items() if e.get("role") == "recall"]
    return order


def recall(query, names=None, max_chars=4000, timeout_ms=1500):
    """The recall result as a dict. Never writes, never raises on a bad vault."""
    vaults = obsidian_common.list_vaults()
    terms = terms_of(query)
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
        hits, cut = search_vault(name, entry["path"], terms, deadline)
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
            "errors": errors}


def cmd_recall(args, prober):  # pylint: disable=unused-argument
    if args.max_chars < 1:
        print("--max-chars must be positive", file=sys.stderr)
        return EXIT_USAGE
    names = []
    for chunk in args.vaults or []:
        names.extend(n.strip() for n in chunk.split(",") if n.strip())
    result = recall(args.query, names or None, args.max_chars, args.timeout_ms)
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
    s.add_argument("--max-chars", type=int, default=4000)
    s.add_argument("--timeout-ms", type=int, default=1500)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_recall)
