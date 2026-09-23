"""Throwaway repositories, vaults and a stub vault CLI for the context-hook
tests. Everything is built under pytest's tmp_path; nothing here reads or
writes the real `~/.claude`, a real vault, or `~/.codex`."""
import json
import os
import subprocess
import textwrap

STUB_CLI = textwrap.dedent('''\
    """Stub of obsidian-vault's `vault_ops.py recall` contract."""
    import json, os, sys
    args = sys.argv[1:]
    out = os.environ.get("STUB_ARGS_OUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(args) + "\\n")
    mode = os.environ.get("STUB_MODE", "ok")
    if mode == "exit":
        print("usage: vault_ops.py: invalid choice: 'recall'", file=sys.stderr)
        sys.exit(2)
    if mode == "badjson":
        print("not json at all")
        sys.exit(0)
    if not args or args[0] != "recall":
        sys.exit(2)
    print(os.environ.get("STUB_JSON", "[]"))
''')


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=root, check=True, capture_output=True)


def note(name, cited, landmines, anchor=None, paths_line=None):
    lines = [f"# {name}"]
    if anchor:
        lines.insert(0, f"anchor: repo@{anchor}")
    if paths_line:
        lines.append(f"paths: {paths_line}")
    lines += ["", "## Entry points", ""]
    lines += [f"- `{c}:1` - an entry point in {name}." for c in cited]
    lines += ["", "## Landmines", ""]
    lines += [f"- {m}. More prose after the first sentence." for m in landmines]
    return "\n".join(lines) + "\n"


def make_repo(tmp_path, subsystems=None, config=None, handoff=None):
    """A git repo with `.crew/codemap/` notes whose citations exist.

    `subsystems` maps name -> (list of files to create and cite, landmines).
    """
    root = tmp_path / "repo"
    root.mkdir()
    subsystems = subsystems or {
        "alpha": (["src/alpha/core.py", "src/alpha/util.py", "src/alpha/io.py"],
                  ["ALPHA-LANDMINE the cache is never invalidated"]),
        "beta": (["src/beta/main.py", "src/beta/api.py", "src/beta/db.py"],
                 ["BETA-LANDMINE the api retries forever"]),
    }
    mapdir = root / ".crew" / "codemap"
    mapdir.mkdir(parents=True)
    rows = []
    for name, (files, marks) in subsystems.items():
        for rel in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n", encoding="utf-8")
        rows.append(f"| [`{name}.md`]({name}.md) | `x` | new | The {name} subsystem. |")
    (mapdir / "INDEX.md").write_text(
        "# Code map\n\n| File | Anchor | Last pass | Covers |\n|---|---|---|---|\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    head = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=root,
                          capture_output=True, text=True, check=True).stdout.strip()
    for name, (files, marks) in subsystems.items():
        (mapdir / f"{name}.md").write_text(note(name, files, marks, anchor=head), encoding="utf-8")
    if config is not None:
        (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    if handoff is not None:
        (root / ".work").mkdir(exist_ok=True)
        (root / ".work" / "HANDOFF.md").write_text(handoff, encoding="utf-8")
    return root


def make_stub_cli(tmp_path):
    path = tmp_path / "stub_vault_ops.py"
    path.write_text(STUB_CLI, encoding="utf-8")
    return path


def make_obsidian_config(tmp_path, vaults):
    path = tmp_path / "obsidian-config.json"
    path.write_text(json.dumps({"vaults": vaults}), encoding="utf-8")
    return path


def payload(event, root, **extra):
    data = {"hook_event_name": event, "session_id": "sess-1", "cwd": str(root),
            "transcript_path": str(root / "no-transcript.jsonl")}
    data.update(extra)
    return data


def log_records(root):
    path = os.path.join(str(root), ".git", "crew", "context-log.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
