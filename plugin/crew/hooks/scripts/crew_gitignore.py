#!/usr/bin/env python3
"""Keep a repository's `.gitignore` right for the languages actually in it.

    python3 crew_gitignore.py check   [--root .] [--json]
    python3 crew_gitignore.py apply   [--root .]
    python3 crew_gitignore.py summary [--root .]

DETECT. The languages and build tools come from the files git lists -
`ls-files --cached --others --exclude-standard` - never a raw walk, so an
ignored `node_modules/` full of `setup.py` files is never evidence.

RECOMMEND. A curated table (`LANGUAGES`, `NOISE`, `SECRETS`), vendored from
github/gitignore (CC0-1.0; `PROVENANCE`) and never fetched at runtime. Each row
is ONE positive pattern (plus the negations that belong to it), a reason, a
probe path and the template it came from. Rows that belong to a manifest's
directory (`/<dir>/bin/`, `/<dir>/target/`, ...) emit one anchored pattern per
manifest directory. The table carries no `.crew` or `.work` pattern, and
`render` drops one if it ever reaches it: that block is the setup policy's
(`check-marketplace.py::check_crew_ignore_policy`), never this script's.

MEASURE, by git and never by string comparison:
- covered: each candidate's probe is tested with `git check-ignore --no-index`
  under a throwaway empty GIT_DIR and `core.excludesFile` pointed at the null
  device, so only the ignore files in the WORKING TREE count. A machine-global
  excludes file, the repo's local config and `.git/info/exclude` do not travel
  with a clone, so they never make a pattern "covered". Status 0/1 only; any
  other status is `unknown`, never "covered" and never "missing". A
  slash-free row (`.env`, `*.pem`) is probed at the root and one directory
  down, so a root-anchored `/.env` does not make it "covered".
- tracked: `git ls-files --cached --ignored --exclude-from=<row>` names the
  tracked files a row would match. Ignoring them does nothing, so they are
  named. A tracked file a SECRETS row matches is `needs-owner` (exit 3):
  rotation and history are the owner's decision, never crew's.
- conflict: a directory candidate that would exclude a path some human `!`
  line re-includes (git cannot re-include inside an excluded directory) is
  reported and not added; a basename `!keep.txt` counts where a file git
  lists carries that name. `summary` says `current except N conflict(s)`.
- overridden: a pattern already in the managed block that a rule below it
  re-includes is the human's decision; it is reported and never re-added.

APPLY writes ONLY the managed block of the root `.gitignore`:

    # crew:gitignore:managed - maintained by crew_gitignore.py; crew only ever adds here.
    # Put your own rules below this block; a rule below wins over one in it.
    # <lang>: <reason>
    <pattern>
    # crew:gitignore:end

It goes at the TOP on first write, so every human line below wins by git's
last-match rule. The previous block's lines are kept verbatim - crew never
drops an entry, even one whose language has left. The whole new text is
computed first, written to a temp file beside it and `os.replace`d (an open
in "w" mode truncates before the payload exists); CRLF and a UTF-8 BOM are
kept. Two start markers, a missing end, an end with no start, or a start
below a human rule is `unknown` (exit 4), never repaired. Never `git rm
--cached`, never an untrack, never a history rewrite.

REFUSALS (exit 5, nothing written): a `# crew:gitignore:off` line in the root
`.gitignore` (report only); a `.gitignore` that is not a regular file; an
active ticket whose Touch does not cover `.gitignore`, or a broken
active-ticket pointer. `.gitignore` is deliberately not a refresh artifact:
an ignore line written inside a ticket without Touch would let the ticket
hide its own files from the completion audit, which sees only what git sees.

Exit: 0 current (or written), 1 additions pending, 2 usage, 3 owner decision
needed (a tracked secret), 4 could not tell, 5 refused.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

GIT = "git"
TIMEOUT = 10
GITIGNORE = ".gitignore"
START = "# crew:gitignore:managed"
END = "# crew:gitignore:end"
OFF = "# crew:gitignore:off"
HEADER = (START + " - maintained by crew_gitignore.py; crew only ever adds here.",
          "# Put your own rules below this block; a rule below wins over one in it.")
FORBIDDEN = (".crew", ".work")

EXIT_CURRENT, EXIT_PENDING, EXIT_USAGE, EXIT_OWNER, EXIT_UNKNOWN, EXIT_REFUSED = 0, 1, 2, 3, 4, 5

PROVENANCE = {
    "repo": "github/gitignore",
    "license": "CC0-1.0",
    "sha": "0e5d690153ca3da8a4a1aef2d053406f408f531c",
    "read": "2026-10-04",
}


def _row(pattern, probe, reason, source, negations=()):
    return {"patterns": [pattern, *negations], "probe": probe, "reason": reason, "source": source}


# lang -> evidence and rows. `ext`: file extensions; `manifests`: basenames
# (fnmatch). A row whose pattern holds `{dir}` is anchored to each manifest's
# directory (`{dir}` is "" at the repo root, else "path/").
LANGUAGES = {
    "python": {
        "ext": (".py",), "manifests": ("pyproject.toml", "requirements*.txt", "setup.py", "Pipfile"),
        "rows": [
            _row("__pycache__/", "__pycache__/m.cpython-312.pyc",
                 "bytecode cache CPython writes beside imported modules", "Python.gitignore"),
            _row("*.py[cod]", "m.pyc", "compiled bytecode and extension leftovers", "Python.gitignore"),
            _row(".venv/", ".venv/pyvenv.cfg", "a local virtual environment", "Python.gitignore"),
            _row(".pytest_cache/", ".pytest_cache/README.md", "pytest's run cache", "Python.gitignore"),
            _row(".mypy_cache/", ".mypy_cache/CACHEDIR.TAG", "mypy's type cache", "Python.gitignore"),
            _row(".ruff_cache/", ".ruff_cache/CACHEDIR.TAG", "ruff's lint cache", "Python.gitignore"),
            _row(".tox/", ".tox/py312/log.txt", "tox environments", "Python.gitignore"),
            _row("*.egg-info/", "pkg.egg-info/PKG-INFO", "setuptools build metadata", "Python.gitignore"),
        ]},
    "node": {
        "ext": (), "manifests": ("package.json",),
        "rows": [
            _row("node_modules/", "node_modules/pkg/index.js", "installed dependencies", "Node.gitignore"),
            _row("npm-debug.log*", "npm-debug.log", "npm crash logs", "Node.gitignore"),
            _row("yarn-error.log*", "yarn-error.log", "yarn crash logs", "Node.gitignore"),
            _row(".pnpm-store/", ".pnpm-store/v3/x", "pnpm's content store", "Node.gitignore"),
        ]},
    "dotnet": {
        "ext": (), "manifests": ("*.csproj", "*.fsproj", "*.vbproj"),
        "rows": [
            _row("/{dir}bin/", "{dir}bin/Debug/app.dll", "build output of this project",
                 "VisualStudio.gitignore"),
            _row("/{dir}obj/", "{dir}obj/project.assets.json", "intermediate build output of this project",
                 "VisualStudio.gitignore"),
            _row(".vs/", ".vs/x/v17/.suo", "Visual Studio's per-machine state", "VisualStudio.gitignore"),
            _row("*.user", "App.csproj.user", "per-user project settings", "VisualStudio.gitignore"),
            _row("TestResults/", "TestResults/run.trx", "test run output", "VisualStudio.gitignore"),
        ]},
    "terraform": {
        "ext": (".tf",), "manifests": (),
        "rows": [
            _row(".terraform/", ".terraform/providers/x", "downloaded providers and modules",
                 "Terraform.gitignore"),
            dict(_row("*.tfstate", "terraform.tfstate", "local state, which holds secrets",
                      "Terraform.gitignore"), secret=True),
            dict(_row("*.tfstate.*", "terraform.tfstate.backup", "state backups", "Terraform.gitignore"),
                 secret=True),
            _row("crash.log", "crash.log", "terraform crash log", "Terraform.gitignore"),
            _row("crash.*.log", "crash.1.log", "terraform crash logs", "Terraform.gitignore"),
        ]},
    "rust": {
        "ext": (), "manifests": ("Cargo.toml",),
        "rows": [_row("/{dir}target/", "{dir}target/debug/app", "cargo build output", "Rust.gitignore")]},
    "maven": {
        "ext": (), "manifests": ("pom.xml",),
        "rows": [_row("/{dir}target/", "{dir}target/classes/A.class", "maven build output",
                      "Maven.gitignore")]},
    "gradle": {
        "ext": (), "manifests": ("build.gradle", "build.gradle.kts"),
        "rows": [
            _row(".gradle/", ".gradle/8.0/x", "gradle's project cache", "Gradle.gitignore"),
            _row("/{dir}build/", "{dir}build/libs/app.jar", "gradle build output", "Gradle.gitignore"),
        ]},
    "composer": {
        "ext": (), "manifests": ("composer.json",),
        "rows": [_row("/{dir}vendor/", "{dir}vendor/autoload.php", "installed composer dependencies",
                      "Composer.gitignore")]},
    "go": {
        "ext": (), "manifests": ("go.mod",),
        "rows": [_row("*.test", "pkg.test", "test binaries from go test -c", "Go.gitignore")]},
}

NOISE = [
    _row(".DS_Store", ".DS_Store", "macOS Finder metadata", "Global/macOS.gitignore"),
    _row("Thumbs.db", "Thumbs.db", "Windows thumbnail cache", "Global/Windows.gitignore"),
    _row("[Dd]esktop.ini", "desktop.ini", "Windows folder settings", "Global/Windows.gitignore"),
    _row("*.swp", "x.swp", "vim swap files", "Global/Vim.gitignore"),
    _row(".idea/", ".idea/workspace.xml", "JetBrains IDE state", "Global/JetBrains.gitignore"),
    _row(".vscode/*", ".vscode/c_cpp_properties.json", "VS Code state, except the shared settings",
         "Global/VisualStudioCode.gitignore",
         ("!.vscode/settings.json", "!.vscode/tasks.json", "!.vscode/launch.json",
          "!.vscode/extensions.json")),
]

SECRETS = [
    _row(".env", ".env", "local environment secrets", "Python.gitignore, Node.gitignore"),
    _row(".env.*", ".env.local", "local environment secrets, except the shared templates",
         "Node.gitignore", ("!.env.example", "!.env.sample", "!.env.template", "!.env.dist",
                            "!.env.defaults")),
    _row("*.pem", "server.pem", "certificates and private keys", "crew"),
    _row("*.key", "server.key", "private keys", "crew"),
    _row("*.p12", "cert.p12", "PKCS#12 key bundles", "crew"),
    _row("*.pfx", "cert.pfx", "PKCS#12 key bundles", "crew"),
    _row("id_rsa", "id_rsa", "an SSH private key", "crew"),
    _row("id_ed25519", "id_ed25519", "an SSH private key", "crew"),
]


def all_rows():
    """Every table row, with its group name as `lang`."""
    rows = []
    for lang, spec in LANGUAGES.items():
        rows += [dict(row, lang=lang) for row in spec["rows"]]
    rows += [dict(row, lang="os/editor") for row in NOISE]
    rows += [dict(row, lang="secrets") for row in SECRETS]
    return rows


def _forbidden(pattern):
    return pattern.lstrip("!").lstrip("/").startswith(FORBIDDEN)


class Unknown(Exception):
    """The measurement could not tell; the message is the reason."""


# --- git --------------------------------------------------------------------------------

def _env(extra=None):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    env.update(extra or {})
    return env


def _git(root, *args, extra_env=None, ok=(0,), stdin_text=None):
    """stdout of git; raises Unknown on a missing git, a timeout or an exit
    status outside `ok`. Returns (status, stdout)."""
    cmd = [GIT, "-c", "core.fsmonitor=false", *args]
    try:
        done = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8",
                              errors="surrogateescape", timeout=TIMEOUT, check=False,
                              env=_env(extra_env), **_feed(stdin_text))
    except FileNotFoundError as exc:
        raise Unknown(f"git not found ({exc.filename})") from exc
    except subprocess.TimeoutExpired as exc:
        raise Unknown(f"git {args[0]} timed out after {TIMEOUT}s") from exc
    except OSError as exc:
        raise Unknown(f"git could not run: {exc}") from exc
    if done.returncode not in ok:
        first = (done.stderr.strip().splitlines() or ["no stderr"])[0]
        raise Unknown(f"git {args[0]} exited {done.returncode}: {first[:120]}")
    return done.returncode, done.stdout


def _feed(text):
    return {"stdin": subprocess.DEVNULL} if text is None else {"input": text}


def toplevel(root):
    try:
        _status, out = _git(root, "rev-parse", "--show-toplevel")
    except Unknown as exc:
        if "not a git repository" in str(exc):
            raise Unknown("not a git repository") from exc
        if "exited" in str(exc):  # e.g. a safe.directory refusal: say what git said
            raise Unknown(f"could not run git rev-parse: {exc}") from exc
        raise
    return os.path.realpath(out.strip())


def list_files(root):
    """(top, files): every tracked or untracked-but-not-ignored path."""
    top = toplevel(root)
    _status, out = _git(top, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return top, sorted({p for p in out.split("\0") if p})


# --- detect and recommend ---------------------------------------------------------------

def _match_manifest(name, manifests):
    import fnmatch  # pylint: disable=import-outside-toplevel
    return any(fnmatch.fnmatchcase(name, m) for m in manifests)


def detect(files):
    """{lang: [evidence paths]} in table order."""
    found = {}
    for lang, spec in LANGUAGES.items():
        hits = [p for p in files
                if os.path.splitext(p)[1] in spec["ext"]
                or _match_manifest(p.rsplit("/", 1)[-1], spec["manifests"])]
        if hits:
            found[lang] = hits
    return found


def _dir_of(path):
    return path.rsplit("/", 1)[0] + "/" if "/" in path else ""


NESTED_PROBE_DIR = "crew-probe/"


def _probe_dirs(paths):
    # Every directory, uncapped: a cap would silently drop the anchored rows
    # of every project past it (and leave their dirs unprobed), so the 201st
    # `.csproj` would never get its `bin/` and the check would read current.
    return sorted({_dir_of(p) for p in paths}, key=lambda d: (d.count("/"), d))


def candidates(langs):
    """Every candidate: one per row, and one per manifest dir for an anchored
    row. Each carries its patterns, the probe paths that must all be ignored
    for it to count as covered, and its group."""
    out = []
    for lang, evidence in langs.items():
        spec = LANGUAGES[lang]
        manifest_dirs = _probe_dirs([p for p in evidence
                                     if _match_manifest(p.rsplit("/", 1)[-1], spec["manifests"])])
        for row in spec["rows"]:
            if "{dir}" in row["patterns"][0]:
                for d in manifest_dirs:
                    pats = [p.replace("{dir}", d) for p in row["patterns"]]
                    out.append(dict(row, lang=lang, patterns=pats, pattern=pats[0],
                                    probes=[row["probe"].replace("{dir}", d)]))
            else:
                out.append(dict(row, lang=lang, pattern=row["patterns"][0],
                                probes=[d + row["probe"] for d in _probe_dirs(evidence)]))
    for group, rows in (("os/editor", NOISE), ("secrets", SECRETS)):
        out += [dict(row, lang=group, pattern=row["patterns"][0], probes=_any_depth(row)) for row in rows]
    return [c for c in out if not any(_forbidden(p) for p in c["patterns"])]


def _any_depth(row):
    """A slash-free pattern matches at every depth, so it is probed at the root
    AND one directory down: `/.env` ignores `.env` but not `config/.env`, and
    must not make the row read as covered."""
    if "/" in row["patterns"][0].rstrip("/"):
        return [row["probe"]]
    return [row["probe"], NESTED_PROBE_DIR + row["probe"]]


# --- the root .gitignore ----------------------------------------------------------------

def _keep_lines(text):
    """Lines with their endings, split the way git splits an ignore file: on
    LF only (str.splitlines also splits on CR, VT, FF and U+2028)."""
    return re.findall(r"[^\n]*\n|[^\n]+\Z", text)


def _lines(text):
    """`_keep_lines` without the LF, and without a CR before it."""
    return [line[:-1].rstrip("\r") if line.endswith("\n") else line for line in _keep_lines(text)]


def _read_bytes(path, label):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise Unknown(f"{label} could not be read: {exc}") from exc

def read_gitignore(top):
    """{exists, regular, text, bom, newline} for the root `.gitignore`;
    raises Unknown when it cannot be decoded."""
    path = os.path.join(top, GITIGNORE)
    info = {"path": path, "exists": os.path.lexists(path), "regular": True, "text": "", "bom": False,
            "newline": "\n"}
    if not info["exists"]:
        return info
    if os.path.islink(path) or not os.path.isfile(path):
        info["regular"] = False
        return info
    raw = _read_bytes(path, GITIGNORE)
    if raw.startswith(b"\xef\xbb\xbf"):
        info["bom"], raw = True, raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Unknown(f".gitignore is not UTF-8 (byte {exc.start})") from exc
    first = text.find("\n")
    if first > 0 and text[first - 1] == "\r":
        info["newline"] = "\r\n"
    info["text"] = text
    return info


def block_span(text):
    """(start, end) line indexes of the managed block, or None; raises
    Unknown on a malformed one."""
    lines = _lines(text)
    starts = [i for i, line in enumerate(lines) if line.startswith(START)]
    ends = [i for i, line in enumerate(lines) if line.rstrip() == END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1:
        raise Unknown(f"the managed block has {len(starts)} start and {len(ends)} end marker(s); "
                      "fix .gitignore by hand")
    start, end = starts[0], ends[0]
    if end < start:
        raise Unknown("the managed block's end marker is above its start; fix .gitignore by hand")
    if any(line.strip() and not line.lstrip().startswith("#") for line in lines[:start]):
        raise Unknown("the managed block starts below a human rule, so its rules would override "
                      "that rule; move the block to the top by hand")
    return start, end


def block_patterns(text):
    span = block_span(text)
    if span is None:
        return set()
    lines = _lines(text)[span[0] + 1:span[1]]
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _negations(top, files, root_text):
    """[(path-or-glob relative to the repo, original line, where)] for every
    `!` line outside the managed block in every working-tree `.gitignore`."""
    out = []
    for rel in sorted({p for p in files if p.rsplit("/", 1)[-1] == GITIGNORE} | {GITIGNORE}):
        if rel == GITIGNORE:
            text = root_text
            skip = block_span(text)
        else:
            path = os.path.join(top, rel)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            raw = _read_bytes(path, rel)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise Unknown(f"{rel} is not UTF-8 (byte {exc.start})") from exc
            skip = None
        base = _dir_of(rel)
        for n, line in enumerate(_lines(text), start=1):
            if skip and skip[0] < n <= skip[1] + 1:
                continue
            body = line.rstrip(" ")
            if not body.startswith("!"):
                continue
            pat = body[1:].rstrip("/")
            if "/" not in pat:
                # A basename negation re-includes that name at any depth under
                # its file, so it is "under" a directory exactly where a file
                # git lists carries the name: `!keep.txt` with
                # `src/App/bin/keep.txt` present conflicts with `/src/App/bin/`.
                out += [(f, body, f"{rel}:{n}") for f in files
                        if f.startswith(base) and _glob_seg(pat, f.rsplit("/", 1)[-1])]
                continue
            out.append((base + pat.lstrip("/"), body, f"{rel}:{n}"))
    return out


def _conflict(candidate, negations):
    pattern = candidate["pattern"]
    if not pattern.endswith("/") or pattern.startswith("!"):
        return None
    anchored = pattern.startswith("/")
    name = pattern.strip("/")
    for path, line, where in negations:
        segs = path.split("/")
        if anchored:
            hit = _under(segs, name.split("/"))
        else:
            hit = any(seg == "**" or _overlap(name, seg) for seg in segs[:-1])
        if hit:
            return line, where
    return None


def _overlap(one, other):
    """Two path segments, either of which may be a glob, that can name the
    same directory. Erring towards True only withholds a pattern."""
    return one == other or _glob_seg(one, other) or _glob_seg(other, one)


def _under(segs, want):
    """True when a negation's segments can name a path strictly below the
    directory `want`: `src/*/bin/keep.txt` is under `src/App/bin`, and so is
    `src/**`. Each segment is compared as a glob, never truncated at one."""
    for i, part in enumerate(want):
        if i < len(segs) and segs[i] == "**":
            return True
        if i >= len(segs) - 1 or not _overlap(part, segs[i]):
            return False
    return True


def _glob_seg(pattern, segment):
    import fnmatch  # pylint: disable=import-outside-toplevel
    return fnmatch.fnmatchcase(segment, pattern)


# --- measure ----------------------------------------------------------------------------

def _covered(top, probes):
    """The set of probe paths the working tree's ignore files ignore."""
    with tempfile.TemporaryDirectory(prefix="crew-gitignore-") as tmp:
        gitdir = os.path.join(tmp, "g")
        _git(tmp, "init", "-q", "--bare", "--template=", gitdir)
        status, out = _git(top, "-c", f"core.excludesFile={os.devnull}", "check-ignore", "--no-index",
                           "--stdin", "-z", extra_env={"GIT_DIR": gitdir, "GIT_WORK_TREE": top},
                           ok=(0, 1), stdin_text="\0".join(probes) + "\0")
    return set() if status == 1 else {p for p in out.split("\0") if p}


def _tracked(top, patterns):
    fd, path = tempfile.mkstemp(prefix="crew-gitignore-", suffix=".exclude")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(patterns) + "\n")
        _status, out = _git(top, "ls-files", "-z", "--cached", "--ignored", f"--exclude-from={path}")
    finally:
        os.unlink(path)
    return sorted(p for p in out.split("\0") if p)


def measure(root):
    """Every finding, and `state` in current/pending/owner/unknown."""
    result = {"root": os.path.abspath(root), "state": "unknown", "reason": "", "detected": {},
              "candidates": [], "needs_owner": [], "off": False, "regular": True}
    try:
        top, files = list_files(root)
        result["root"] = top
        info = read_gitignore(top)
        result["regular"] = info["regular"]
        text = info["text"] if info["regular"] else ""
        block_span(text)
        result["off"] = any(line.strip() == OFF for line in _lines(text))
        in_block = block_patterns(text)
        langs = detect(files)
        result["detected"] = langs
        cands = candidates(langs)
        covered = _covered(top, [p for c in cands for p in c["probes"]])
        negs = _negations(top, files, text)
        for cand in cands:
            if all(p in covered for p in cand["probes"]):
                cand["status"] = "covered"
            elif all(p in in_block for p in cand["patterns"]):
                cand["status"] = "overridden"
            else:
                hit = _conflict(cand, negs)
                if hit:
                    cand["status"], cand["negation"], cand["where"] = "conflict", hit[0], hit[1]
                else:
                    cand["status"] = "missing"
            if cand["status"] == "missing" or _secret(cand):
                cand["tracked"] = _tracked(top, cand["patterns"])
                if _secret(cand):
                    result["needs_owner"] += cand["tracked"]
            result["candidates"].append(cand)
    except Unknown as exc:
        result["reason"] = str(exc)
        return result
    result["needs_owner"] = sorted(set(result["needs_owner"]))
    if result["needs_owner"]:
        result["state"] = "owner"
    elif any(c["status"] == "missing" for c in result["candidates"]):
        result["state"] = "pending"
    else:
        result["state"] = "current"
    return result


def _secret(cand):
    """A row whose tracked match is `needs-owner`: the SECRETS group, and a
    language row that holds secrets (Terraform state)."""
    return cand["lang"] == "secrets" or bool(cand.get("secret"))


def _missing(result):
    return [c for c in result["candidates"] if c["status"] == "missing"]


def report(result, applied=False):
    """The `check` lines; after `apply` wrote, a missing row reads `added`."""
    if result["state"] == "unknown":
        return [f"unknown {_shown(result['reason'])}", f"gitignore: {summarize(result)}"]
    lines = []
    for lang, evidence in result["detected"].items():
        more = f", +{len(evidence) - 2} more" if len(evidence) > 2 else ""
        lines.append(f"detected {lang} ({', '.join(map(_shown, evidence[:2]))}{more})")
    if result["off"]:
        lines.append(f"off .gitignore carries '{OFF}' - report only, apply never writes")
    if not result["regular"]:
        lines.append("refused .gitignore is not a regular file - apply will not write it")
    for cand in result["candidates"]:
        status, pattern = cand["status"], cand["pattern"]
        if status == "missing":
            verb = "added" if applied else "missing"
            lines.append(f"{verb} {pattern} - {cand['lang']}: {cand['reason']}")
        elif status == "covered":
            lines.append(f"covered {pattern}")
        elif status == "overridden":
            lines.append(f"overridden {pattern} - already in the managed block, re-included by a rule "
                         "below it (your decision; not re-added)")
        else:
            lines.append(f"conflict {pattern} would override {_shown(cand['negation'])} at "
                         f"{_shown(cand['where'])} "
                         "- not added")
        tracked = cand.get("tracked") or []
        if tracked and not _secret(cand):
            lines.append(f"tracked {pattern} matches {len(tracked)} tracked file(s): "
                         f"{', '.join(map(_shown, tracked[:4]))} - ignoring does not untrack them")
    for path in result["needs_owner"]:
        lines.append(f"needs-owner {_shown(path)} is tracked and secret-shaped - rotate and decide on history")
    if not applied:
        lines.append(f"gitignore: {summarize(result)}")
    return lines


def _shown(text):
    """`text` as it is when every character prints, else its `ascii()` form:
    a repository-supplied name (a tracked path, a `.gitignore` line) never
    reaches the terminal with a control character or a line break in it."""
    return text if text.isprintable() else ascii(text)


def summarize(result):
    """The one line `/crew:status` prints."""
    state = result["state"]
    if state == "unknown":
        return f"unknown ({_shown(result['reason'])})"
    if state == "owner":
        owner = result["needs_owner"]
        return f"owner: {len(owner)} tracked secret-shaped file(s) - {_shown(owner[0])}"
    if state == "pending":
        missing = _missing(result)
        langs = []
        for cand in missing:
            if cand["lang"] not in langs:
                langs.append(cand["lang"])
        tail = " - report only (crew:gitignore:off)" if result["off"] else ""
        return f"{len(missing)} missing ({', '.join(langs)}){tail}"
    conflicts = [c for c in result["candidates"] if c["status"] == "conflict"]
    if conflicts:
        # Not added on purpose (a human `!` line decides), so not "missing" and
        # not exit 1, but never a bare "current" while a wanted row is left out.
        return (f"current except {len(conflicts)} conflict(s) - {conflicts[0]['pattern']} would override "
                f"{_shown(conflicts[0]['negation'])}; your negation decides")
    return "current"


def summary(root):
    return summarize(measure(root))


# --- apply ------------------------------------------------------------------------------

def _render_impl(text, rows, newline="\n"):
    """`text` with `rows` added inside the managed block. Pure: every line
    outside the block keeps its bytes and order, and every line inside it is
    kept. A row carrying a `.crew` or `.work` pattern is dropped."""
    rows = [r for r in rows if not any(_forbidden(p) for p in r["patterns"])]
    added = []
    for row in rows:
        added.append(f"# {row['lang']}: {row['reason']}")
        added += row["patterns"]
    span = block_span(text)
    if span is None:
        if not added:
            return text
        block = list(HEADER) + added + [END]
        rendered = newline.join(block) + newline
        return rendered + (newline + text if text else "")
    if not added:
        return text
    lines = _keep_lines(text)
    insert = "".join(line + newline for line in added)
    return "".join(lines[:span[1]]) + insert + "".join(lines[span[1]:])


render = _render_impl


def _ticket_refusal(top):
    """A refusal reason when the active ticket's Touch does not cover
    `.gitignore` (or the pointer is broken), else None."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    ticket, source, broken = crew_ticket.resolve_active(top)
    if broken:
        return f"the active-ticket pointer is broken ({source}); nothing written"
    if not ticket:
        return None
    if crew_ticket.in_touch(GITIGNORE, crew_ticket.touch_for(top, ticket)):
        return None
    return (f"active ticket {ticket}'s Touch does not cover .gitignore; nothing written - the "
            "additions land at the next /crew:onboard or /crew:init run outside a ticket")


def _write_atomic(path, data, like):
    tmp = f"{path}.crew-tmp-{os.getpid()}"
    try:
        with open(tmp, "xb") as fh:
            fh.write(data)
        if like:
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)


def apply(root, out=print):
    """Exit code; prints the refusal or the diff, then the check report."""
    result = measure(root)
    if result["state"] == "unknown":
        for line in report(result):
            out(line)
        return EXIT_UNKNOWN
    top = result["root"]
    refusal = None
    if not result["regular"]:
        refusal = ".gitignore is not a regular file; nothing written"
    elif result["off"]:
        refusal = f".gitignore carries '{OFF}'; report only, nothing written"
    else:
        try:
            refusal = _ticket_refusal(top)
        except Exception as exc:  # pylint: disable=broad-except
            refusal = f"could not read the active ticket ({exc}); nothing written"
    if refusal:
        out(f"refused {refusal}")
        for line in report(result):
            out(line)
        return EXIT_REFUSED
    missing = _missing(result)
    if missing:
        try:
            info = read_gitignore(top)
        except Unknown as exc:
            out(f"unknown {exc}; nothing written")
            return EXIT_UNKNOWN
        new = render(info["text"], missing, info["newline"])
        if new != info["text"]:
            data = (b"\xef\xbb\xbf" if info["bom"] else b"") + new.encode("utf-8")
            try:
                _write_atomic(info["path"], data, info["exists"])
            except OSError as exc:
                out(f"unknown could not write .gitignore: {exc}; original left as it was")
                return EXIT_UNKNOWN
            for line in difflib.unified_diff(_lines(info["text"]), _lines(new),
                                             "a/.gitignore", "b/.gitignore", lineterm=""):
                out(line)
        # What was found and acted on, then the state measured AFTER the write:
        # the summary and the exit code come from git, not from the plan.
        for line in report(result, applied=True):
            out(line)
        result = measure(root)
        if result["state"] == "unknown":
            out(f"unknown {result['reason']}")
        out(f"gitignore: {summarize(result)}")
    else:
        for line in report(result):
            out(line)
    return EXITS[result["state"]]


EXITS = {"current": EXIT_CURRENT, "pending": EXIT_PENDING, "owner": EXIT_OWNER, "unknown": EXIT_UNKNOWN}


def main(argv=None):
    # A path git hands back is bytes; one that is not valid in the console's
    # encoding (cp1252, or a surrogate-escaped byte under UTF-8) must not turn
    # the report into a traceback and exit 1, which reads as "additions pending".
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("check", "apply", "summary"):
        one = sub.add_parser(name)
        one.add_argument("--root", default=".")
        if name == "check":
            one.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:  # pylint: disable=broad-except
        # Anything unforeseen is "could not tell" (exit 4), never a status a
        # caller acts on: 1 would read as "additions pending".
        print(f"unknown crew_gitignore.py failed: {type(exc).__name__}: {exc}")
        return EXIT_UNKNOWN


def _run(args):
    if args.action == "apply":
        return apply(args.root)
    result = measure(args.root)
    if args.action == "summary":
        print(summarize(result))
        return EXITS[result["state"]]
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("\n".join(report(result)))
    return EXITS[result["state"]]


if __name__ == "__main__":
    sys.exit(main())
