#!/usr/bin/env python3
"""Survey a repository to ground documentation generation.

Inventories directories, languages, entry points, manifests, config surfaces, existing
docs, work markers, and git state. Reads docs/.repo-docs.json (if present) to report what
changed since the last documentation run.

Usage:
    python repo_survey.py /path/to/repo                 # human-readable summary
    python repo_survey.py /path/to/repo --json          # machine-readable
    python repo_survey.py /path/to/repo --max-depth 3
    python repo_survey.py /path/to/repo --secrets-scan README.md docs/API.md

No third-party dependencies. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- config

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "__pycache__",
    ".venv", "venv", "env", ".env.d", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".vscode", ".next", ".nuxt", ".svelte-kit",
    ".terraform", ".serverless", ".parcel-cache", ".turbo", ".cache", "dist", "build",
    "out", "target", "bin", "obj", "coverage", "htmlcov", "site-packages", ".dart_tool",
    "Pods", "DerivedData", ".pnpm-store", "__snapshots__", ".angular",
}

LANG_BY_EXT = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".fs": "F#", ".swift": "Swift",
    ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".m": "Objective-C", ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".clj": "Clojure", ".hs": "Haskell", ".lua": "Lua",
    ".dart": "Dart", ".r": "R", ".jl": "Julia", ".pl": "Perl", ".sh": "Shell",
    ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".vue": "Vue", ".svelte": "Svelte",
    ".tf": "Terraform", ".proto": "Protobuf", ".graphql": "GraphQL", ".gql": "GraphQL",
    ".md": "Markdown", ".rst": "reStructuredText", ".yml": "YAML", ".yaml": "YAML",
    ".json": "JSON", ".toml": "TOML", ".ipynb": "Notebook",
}

MANIFESTS = {
    "package.json", "pnpm-workspace.yaml", "yarn.lock", "package-lock.json",
    "pnpm-lock.yaml", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "Pipfile", "poetry.lock", "environment.yml", "go.mod", "Cargo.toml", "pom.xml",
    "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "mix.exs",
    "pubspec.yaml", "Package.swift", "deno.json", "bun.lockb",
}

BUILD_FILES = {
    "Makefile", "makefile", "justfile", "Justfile", "Taskfile.yml", "Taskfile.yaml",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
    "Procfile", "Rakefile", "CMakeLists.txt", "meson.build", "BUILD", "BUILD.bazel",
}

CONFIG_HINTS = {
    ".env.example", ".env.sample", ".env.template", "config.yml", "config.yaml",
    "settings.py", "appsettings.json", "application.yml", "application.properties",
    "tsconfig.json", "vite.config.ts", "next.config.js", "nuxt.config.ts",
    "webpack.config.js", "tailwind.config.js", "serverless.yml", "netlify.toml",
    "vercel.json", "openapi.yaml", "openapi.json", "swagger.json", "mkdocs.yml",
    "typedoc.json", "sonar-project.properties",
}

ENTRY_NAMES = {
    "main.py", "app.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py", "cli.py",
    "server.py", "run.py", "index.js", "index.ts", "main.js", "main.ts", "server.js",
    "server.ts", "app.js", "app.ts", "main.go", "main.rs", "lib.rs", "Program.cs",
    "Application.java", "main.kt", "index.php", "config.ru",
}

DOC_ARTIFACTS = [
    "CLAUDE.md", ".claude/CLAUDE.md", "README.md", "TODO.md", "SECURITY.md",
    "CHANGELOG.md", "HISTORY.md", "docs/API.md", "docs/ARCHITECTURE.md",
    "docs/HANDOFF.md", "CONTRIBUTING.md", "LICENSE",
]

MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG|DEPRECATED)\b[:\s-]{0,3}(.{0,140})")
ENV_RE = re.compile(
    r"""(?:os\.getenv\(|os\.environ\.get\(|os\.environ\[|process\.env\.|
        import\.meta\.env\.|System\.getenv\(|std::env::var\(|ENV\[)\s*["']?
        ([A-Z][A-Z0-9_]{2,})""",
    re.VERBOSE,
)
ROUTE_RE = re.compile(
    r"""(@(?:app|router|bp|blueprint|api)\.(?:get|post|put|patch|delete|route)\s*\(|
        (?:app|router|r|e|mux|fastify)\.(?:get|post|put|patch|delete|route|use)\s*\(\s*["'`]/|
        @(?:Get|Post|Put|Patch|Delete|Request)Mapping|
        @(?:Get|Post|Put|Patch|Delete)\s*\(|
        \.(?:HandleFunc|MapGet|MapPost|MapPut|MapDelete)\s*\(|
        (?:urlpatterns|routes)\s*=|
        \bRoute::(?:get|post|put|patch|delete)\b)""",
    re.VERBOSE,
)

# Secrets: shaped to catch real credentials while tolerating placeholders.
SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jwt", re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("db_url_with_password", re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:[^\s:@/]+@")),
    ("assigned_secret", re.compile(
        r"""(?i)\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|
            private[_-]?key|client[_-]?secret)\b\s*[:=]\s*["'][^"'\s]{8,}["']""",
        re.VERBOSE)),
]

PLACEHOLDER_RE = re.compile(
    r"(?i)(x{4,}|\*{4,}|\.{3,}|<[^>]+>|\$\{?[A-Z_]+\}?|your[_-]?|example|placeholder|"
    r"changeme|dummy|redacted|sample|test[_-]?key|fake|todo|insert|\bnull\b|\bnone\b)"
)

TEXT_EXTS = set(LANG_BY_EXT) | {".txt", ".env", ".cfg", ".ini", ".conf", ".xml", ".lock", ""}
MAX_SCAN_BYTES = 400_000

# --------------------------------------------------------------------------- helpers


def run_git(repo: Path, *args: str):
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=25, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTS:
        return False
    try:
        return b"\x00" not in path.open("rb").read(2048)
    except OSError:
        return False


def read_text(path: Path, limit: int = MAX_SCAN_BYTES) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def walk(repo: Path, max_depth: int):
    """Yield (dirpath, filenames) for non-ignored directories."""
    for dirpath, dirnames, filenames in os.walk(repo):
        d = Path(dirpath)
        rel = d.relative_to(repo)
        depth = 0 if rel == Path(".") else len(rel.parts)
        dirnames[:] = sorted(
            n for n in dirnames
            if n not in SKIP_DIRS and not (n.startswith(".") and n not in {".github", ".claude"})
        )
        if depth >= max_depth:
            dirnames[:] = []
        yield d, sorted(filenames)


# --------------------------------------------------------------------------- survey


def survey(repo: Path, max_depth: int, marker_limit: int) -> dict:
    dirs, languages = [], Counter()
    entry_points, manifests, build_files, configs = [], [], [], []
    markers, env_vars, route_files = [], Counter(), []
    total_files = total_bytes = 0

    for d, filenames in walk(repo, max_depth):
        rel_dir = "." if d == repo else str(d.relative_to(repo))
        dir_langs = Counter()
        dir_bytes = 0
        for name in filenames:
            path = d / name
            rel = str(path.relative_to(repo))
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total_files += 1
            total_bytes += size
            dir_bytes += size
            ext = path.suffix.lower()
            lang = LANG_BY_EXT.get(ext)
            if lang:
                dir_langs[lang] += 1
                languages[lang] += 1
            if name in MANIFESTS:
                manifests.append(rel)
            if name in BUILD_FILES:
                build_files.append(rel)
            if name in CONFIG_HINTS or name.startswith(".env"):
                configs.append(rel)
            if name in ENTRY_NAMES:
                entry_points.append(rel)

            if not is_probably_text(path) or size > MAX_SCAN_BYTES:
                continue
            content = read_text(path)
            if ROUTE_RE.search(content):
                route_files.append(rel)
            for m in ENV_RE.finditer(content):
                env_vars[m.group(1)] += 1
            if len(markers) < marker_limit:
                for lineno, line in enumerate(content.splitlines(), 1):
                    if len(line) > 400:
                        continue
                    mm = MARKER_RE.search(line)
                    if mm:
                        markers.append({
                            "file": rel, "line": lineno,
                            "kind": mm.group(1), "text": mm.group(2).strip()[:140],
                        })
                        if len(markers) >= marker_limit:
                            break

        code_files = sum(dir_langs.values())
        if code_files or rel_dir == ".":
            dirs.append({
                "path": rel_dir,
                "depth": 0 if rel_dir == "." else len(Path(rel_dir).parts),
                "files": len(filenames),
                "code_files": code_files,
                "bytes": dir_bytes,
                "languages": dict(dir_langs.most_common(4)),
                "has_readme": any(f.lower() == "readme.md" for f in filenames),
            })

    docs = {a: (repo / a).exists() for a in DOC_ARTIFACTS}
    missing_readmes = [
        d["path"] for d in dirs
        if not d["has_readme"] and d["code_files"] >= 3 and d["path"] != "."
    ]

    return {
        "repo": str(repo.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "files": total_files,
            "bytes": total_bytes,
            "directories": len(dirs),
        },
        "languages": dict(languages.most_common()),
        "primary_language": (languages.most_common(1) or [(None, 0)])[0][0],
        "directories": sorted(dirs, key=lambda x: (-x["code_files"], x["path"]))[:200],
        "entry_points": sorted(set(entry_points)),
        "manifests": sorted(set(manifests)),
        "build_files": sorted(set(build_files)),
        "config_files": sorted(set(configs)),
        "route_candidates": sorted(set(route_files))[:60],
        "env_vars": [k for k, _ in env_vars.most_common(80)],
        "work_markers": markers,
        "work_marker_counts": dict(Counter(m["kind"] for m in markers)),
        "docs_present": docs,
        "docs_missing": [k for k, v in docs.items() if not v],
        "dirs_missing_readme": missing_readmes,
    }


def git_info(repo: Path) -> dict:
    if run_git(repo, "rev-parse", "--git-dir") is None:
        return {"is_repo": False}
    tag = run_git(repo, "describe", "--tags", "--abbrev=0")
    log_range = f"{tag}..HEAD" if tag else "HEAD"
    commits = run_git(repo, "log", log_range, "--oneline", "-n", "200") or ""
    status = run_git(repo, "status", "--porcelain") or ""
    return {
        "is_repo": True,
        "branch": run_git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": (run_git(repo, "rev-parse", "--short", "HEAD") or ""),
        "last_tag": tag,
        "commits_since_tag": len([c for c in commits.splitlines() if c.strip()]),
        "recent_commits": commits.splitlines()[:40],
        "uncommitted_files": [l[3:] for l in status.splitlines()][:60],
        "contributors": (run_git(repo, "shortlog", "-sne", "HEAD") or "").splitlines()[:10],
        "first_commit_date": run_git(
            repo, "log", "--reverse", "--format=%ad", "--date=short", "-n", "1"),
        "last_commit_date": run_git(repo, "log", "--format=%ad", "--date=short", "-n", "1"),
    }


def changes_since_manifest(repo: Path) -> dict:
    mpath = repo / "docs" / ".repo-docs.json"
    if not mpath.exists():
        return {"manifest_found": False}
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"manifest_found": True, "error": f"unreadable: {exc}"}
    commit = manifest.get("commit")
    result = {
        "manifest_found": True,
        "last_run": manifest.get("last_run"),
        "last_commit": commit,
        "artifacts": list((manifest.get("artifacts") or {}).keys()),
    }
    if commit:
        diff = run_git(repo, "diff", "--name-status", f"{commit}..HEAD")
        if diff is None:
            result["changed_files"] = None
            result["note"] = "commit not found in history (rebase/shallow clone?)"
        else:
            lines = [l for l in diff.splitlines() if l.strip()]
            result["changed_files"] = lines[:300]
            result["changed_count"] = len(lines)
    return result


def scan_secrets(paths) -> list:
    findings = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        for lineno, line in enumerate(read_text(path).splitlines(), 1):
            if len(line) > 1000:
                continue
            for label, pattern in SECRET_PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue
                snippet = m.group(0)
                if PLACEHOLDER_RE.search(snippet):
                    continue
                findings.append({
                    "file": str(path), "line": lineno, "kind": label,
                    "preview": snippet[:12] + "…[redacted]",
                })
                break
    return findings


# --------------------------------------------------------------------------- output


def human(data: dict) -> str:
    o = []
    a = o.append
    t = data["totals"]
    a(f"Repository: {data['repo']}")
    a(f"Surveyed:   {t['files']} files, {t['bytes']/1024:.0f} KB, {t['directories']} dirs")
    langs = ", ".join(f"{k} ({v})" for k, v in list(data["languages"].items())[:6])
    a(f"Languages:  {langs or 'none detected'}")

    g = data.get("git", {})
    if g.get("is_repo"):
        a("")
        a(f"Git:        branch {g['branch']} @ {g['head']}"
          f"{'  last tag ' + g['last_tag'] if g.get('last_tag') else '  (no tags)'}")
        a(f"            {g['commits_since_tag']} commits since tag, "
          f"{len(g['uncommitted_files'])} uncommitted files")
        a(f"            active {g.get('first_commit_date')} → {g.get('last_commit_date')}")
    else:
        a("Git:        not a git repository")

    def section(title, items, limit=12):
        if items:
            a("")
            a(f"{title}:")
            for i in items[:limit]:
                a(f"  - {i}")
            if len(items) > limit:
                a(f"  … {len(items)-limit} more")

    section("Entry points", data["entry_points"])
    section("Manifests", data["manifests"])
    section("Build / container", data["build_files"])
    section("Config surfaces", data["config_files"])
    section("Files with route-like patterns", data["route_candidates"], 15)
    section("Environment variables referenced", data["env_vars"], 20)

    a("")
    a("Largest code directories:")
    for d in data["directories"][:15]:
        flag = "" if d["has_readme"] else "   [no README]"
        langs = ", ".join(d["languages"]) or "-"
        a(f"  {d['path']:<40} {d['code_files']:>4} code files  {langs}{flag}")

    a("")
    a("Documentation status:")
    for name, present in data["docs_present"].items():
        a(f"  [{'x' if present else ' '}] {name}")
    if data["dirs_missing_readme"]:
        a(f"  {len(data['dirs_missing_readme'])} code directories lack a README")

    if data["work_markers"]:
        a("")
        counts = ", ".join(f"{k}={v}" for k, v in data["work_marker_counts"].items())
        a(f"Work markers ({counts}):")
        for m in data["work_markers"][:15]:
            a(f"  {m['file']}:{m['line']}  {m['kind']}: {m['text']}")
        if len(data["work_markers"]) > 15:
            a(f"  … {len(data['work_markers'])-15} more")

    c = data.get("since_last_docs_run", {})
    a("")
    if c.get("manifest_found"):
        a(f"Last docs run: {c.get('last_run')} at commit {c.get('last_commit')}")
        if c.get("changed_count") is not None:
            a(f"  {c['changed_count']} files changed since then")
            for line in (c.get("changed_files") or [])[:20]:
                a(f"    {line}")
        elif c.get("note"):
            a(f"  {c['note']}")
    else:
        a("Last docs run: none recorded (docs/.repo-docs.json absent) — bootstrap mode")

    return "\n".join(o)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=".", help="path to repository")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--max-depth", type=int, default=4, help="directory depth (default 4)")
    ap.add_argument("--marker-limit", type=int, default=300,
                    help="max TODO/FIXME markers to collect")
    ap.add_argument("--secrets-scan", nargs="+", metavar="FILE",
                    help="scan the given files for credential-shaped strings and exit")
    args = ap.parse_args()

    if args.secrets_scan:
        findings = scan_secrets(args.secrets_scan)
        if args.json:
            print(json.dumps({"findings": findings}, indent=2))
        elif findings:
            print(f"{len(findings)} possible secret(s):")
            for f in findings:
                print(f"  {f['file']}:{f['line']}  {f['kind']}  {f['preview']}")
        else:
            print("No credential-shaped strings found.")
        return 1 if findings else 0

    repo = Path(args.repo).expanduser()
    if not repo.is_dir():
        print(f"error: not a directory: {repo}", file=sys.stderr)
        return 2

    data = survey(repo, args.max_depth, args.marker_limit)
    data["git"] = git_info(repo)
    data["since_last_docs_run"] = changes_since_manifest(repo)
    print(json.dumps(data, indent=2) if args.json else human(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
