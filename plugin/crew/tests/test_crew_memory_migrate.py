"""`crew_memory.py migrate` and `restore` (L-0678).

`migrate` previews, and with `--apply` performs, `save` for every full-text
memory in one native memory directory. `restore` turns one pointer back into
full text from its note. Both are dry runs by default; neither writes a state
file; a failure on one file never stops or undoes the others.

Every fixture is under `tmp_path` through `test_crew_memory_save.Host`.
"""
import json
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_memory  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order
from test_crew_memory_save import (  # noqa: E402  pylint: disable=wrong-import-position
    BODY, FRONTMATTER, SCRIPT, Host, tree)


@pytest.fixture(name="host")
def _host(tmp_path, monkeypatch):
    return Host(tmp_path / "a", monkeypatch)


def fm(name):
    return FRONTMATTER.replace("name: Example fact", f"name: {name}")


def run(host, capsys, *extra, apply=False, tags=("memory",)):
    argv = ["migrate", "--memory-dir", str(host.mem), "--root", str(host.root)]
    for tag in tags:
        argv += ["--tag", tag]
    argv += list(extra)
    if apply:
        argv.append("--apply")
    code = crew_memory.main(argv)
    return code, capsys.readouterr().out


def rows(out):
    """`{file: action}` from the table's rows (`<action>  <file>  ...`)."""
    found = {}
    for line in out.splitlines():
        parts = line.split("  ")
        if len(parts) >= 3 and parts[1].endswith(".md"):
            found[parts[1]] = parts[0]
    return found


def three(host):
    for stem in ("one", "two", "three"):
        host.memory(body=f"The {stem} fact.\n", name=f"{stem}.md", frontmatter=fm(stem.title()))
    (host.mem / "MEMORY.md").write_text("- [One](one.md)\n", encoding="utf-8", newline="\n")


def test_migrate_preview_writes_nothing(host, capsys):
    host.work()
    three(host)
    before = tree(host.base)
    code, out = run(host, capsys)
    assert code == 1
    assert tree(host.base) == before
    assert list(rows(out)) == ["one.md", "three.md", "two.md"]
    assert set(rows(out).values()) == {"convert"}
    assert "MEMORY.md" not in rows(out)
    assert "MEMORY.md was not edited" in out
    assert "-> work/memories/repo/One.md" in out


def test_migrate_preview_actions(host, capsys):
    vault = host.work()
    host.memory(name="a-full.md", frontmatter=fm("Full"))
    (vault / "memories" / "repo").mkdir(parents=True)
    (vault / "memories" / "repo" / "Kept.md").write_text("---\n---\nkept\n", encoding="utf-8")
    host.memory(body="vault: work | note: memories/repo/Kept.md\n", name="b-pointer.md")
    host.memory(body="vault: work | note: memories/repo/Gone.md\n", name="c-dangling.md")
    host.memory(body="vault: work | note:\n", name="d-malformed.md")
    host.memory(name="e-noname.md", frontmatter="---\ndescription: x\n---\n\n")
    host.memory(name="f-twin1.md", frontmatter=fm("Twin"))
    host.memory(name="g-twin2.md", frontmatter=fm("Twin"))
    (vault / "memories" / "repo" / "Foreign.md").write_text(
        '---\nmemory_id: "other"\n---\n\nother\n', encoding="utf-8")
    host.memory(name="h-collide.md", frontmatter=fm("Foreign"))
    before = tree(host.base)
    code, out = run(host, capsys)
    assert code == 1 and tree(host.base) == before
    got = rows(out)
    assert got["a-full.md"] == "convert"
    assert got["b-pointer.md"] == "skip: already a pointer"
    assert got["c-dangling.md"] == "skip: note-missing"
    assert got["d-malformed.md"] == "skip: malformed"
    assert got["e-noname.md"].startswith("refuse: ")
    assert got["f-twin1.md"] == got["g-twin2.md"] == "refuse: duplicate note path"
    assert got["h-collide.md"].startswith("refuse: collision")


def test_migrate_preview_shows_append(host, capsys):
    vault = host.work()
    (vault / "memories" / "repo").mkdir(parents=True)
    (vault / "memories" / "repo" / "Mine.md").write_text(
        '---\nupdated: 2026-01-01\nproject: "repo"\nmemory_id: "mine"\n---\n\nolder\n', encoding="utf-8")
    host.memory(name="mine.md", frontmatter=fm("Mine"))
    code, out = run(host, capsys)
    assert code == 1 and rows(out) == {"mine.md": "append"}


def test_migrate_apply_matches_the_preview(host, capsys):
    vault = host.work()
    three(host)
    host.memory(body="vault: work | note: memories/repo/Gone.md\n", name="z-dangling.md")
    host.memory(name="y-noname.md", frontmatter="---\ndescription: x\n---\n\n")
    untouched = {n: (host.mem / n).read_bytes() for n in ("z-dangling.md", "y-noname.md",
                                                           "MEMORY.md")}
    _code, preview = run(host, capsys)
    code, out = run(host, capsys, apply=True)
    assert code == 1  # a refused row is not a clean run
    for name, action in rows(preview).items():
        if action == "convert":
            assert crew_memory.resolve_file(str(host.mem / name), str(host.root))["state"] \
                == "resolved"
            assert rows(out)[name] == "converted"
    for name, data in untouched.items():
        assert (host.mem / name).read_bytes() == data
    assert (vault / "memories" / "repo" / "Two.md").exists()


def test_migrate_continues_past_a_failed_file(host, capsys, monkeypatch):
    host.work()
    three(host)
    two = (host.mem / "two.md").read_bytes()
    three_before = (host.mem / "three.md").read_bytes()
    real, calls = crew_memory.apply_note, []

    def flaky(plan):
        calls.append(plan["file"])
        if len(calls) == 2:
            raise OSError("disk full")
        real(plan)

    monkeypatch.setattr(crew_memory, "apply_note", flaky)
    code, out = run(host, capsys, apply=True)
    assert code == 1
    assert (host.mem / "two.md").read_bytes() != two  # name order: one, three, two
    failed = [n for n, a in rows(out).items() if a == "failed"]
    assert failed == ["three.md"]
    assert (host.mem / "three.md").read_bytes() == three_before
    assert "kept-full-text: note write failed: disk full" in out
    for name in ("one.md", "two.md"):
        assert crew_memory.resolve_file(str(host.mem / name), str(host.root))["state"] \
            == "resolved"


def test_migrate_without_a_vault_changes_nothing(host, capsys):
    three(host)
    before = tree(host.mem)
    code, out = run(host, capsys)
    assert code == 0 and out.splitlines()[0] == "nothing to migrate: no vault configured"
    assert not rows(out)
    host.obsidian({"vaults": {"work": {"path": str(host.base / "gone"), "role": "primary"}}})
    code, out = run(host, capsys, apply=True)
    assert code == 1 and out.startswith("nothing to migrate: vault unavailable")
    assert tree(host.mem) == before


def test_migrate_twice_is_a_no_op(host, capsys):
    host.work()
    three(host)
    assert run(host, capsys, apply=True)[0] == 0
    before = tree(host.base)
    code, out = run(host, capsys, apply=True)
    assert code == 0 and tree(host.base) == before
    assert set(rows(out).values()) == {"skip: already a pointer"}
    assert run(host, capsys)[0] == 0


def test_migrate_only_limits_the_run(host, capsys):
    host.work()
    three(host)
    two = (host.mem / "two.md").read_bytes()
    code, out = run(host, capsys, "--only", "one.md", "--only", "three.md", apply=True)
    assert code == 0 and list(rows(out)) == ["one.md", "three.md"]
    assert (host.mem / "two.md").read_bytes() == two


def test_migrate_only_unknown_name_exits_2(host, capsys):
    host.work()
    three(host)
    before = tree(host.base)
    assert run(host, capsys, "--only", "nope.md", apply=True)[0] == 2
    assert run(host, capsys, "--only", "MEMORY.md")[0] == 2
    assert tree(host.base) == before


@pytest.mark.parametrize("title", ["a:b", "why?", "star*", "less<than", "pipe|d",
                                   "trailing.", "trailing ", "CON", "com1.notes", 'q"uote',
                                   "COM0", "lpt0", "COM\u00b9", "LPT\u00b3.x",
                                   "back\\slash"])
def test_migrate_refuses_unportable_titles(host, capsys, title):
    host.work()
    host.memory(name="odd.md", frontmatter=fm(json.dumps(title)))
    before = tree(host.base)
    code, out = run(host, capsys, apply=True)
    assert code == 1 and tree(host.base) == before
    assert rows(out)["odd.md"] == "refuse: title is not a portable file name"


@pytest.mark.parametrize("title", ["Plain", "with space", "con-tact", "dots.in.middle",
                                   "COM10"])
def test_migrate_accepts_portable_titles(host, capsys, title):
    host.work()
    host.memory(name="ok.md", frontmatter=fm(title))
    code, out = run(host, capsys)
    assert code == 1 and rows(out)["ok.md"] == "convert"


def test_migrate_options_shape_the_note(host, capsys):
    vault = host.work()
    host.memory(name="fact.md", frontmatter=fm("Shaped"))
    code, _out = run(host, capsys, "--note-dir", "facts/x", "--type", "decision",
                     "--project", "proj", apply=True, tags=("a", "b/c"))
    assert code == 0
    note = (vault / "facts" / "x" / "Shaped.md").read_text(encoding="utf-8")
    assert "type: decision" in note and "  - b/c\n" in note and 'project: "proj"' in note


def test_migrate_json(host, capsys):
    host.work()
    three(host)
    code, out = run(host, capsys, "--json")
    data = json.loads(out)
    assert code == 1 and [r["action"] for r in data["rows"]] == ["convert"] * 3
    assert data["counts"] == {"convert": 3}


def test_migrate_usage_errors_exit_2(host, capsys):
    assert crew_memory.main(["migrate", "--memory-dir", str(host.base / "none"),
                             "--tag", "x"]) == 2
    with pytest.raises(SystemExit) as caught:
        crew_memory.main(["migrate", "--memory-dir", str(host.mem)])
    assert caught.value.code == 2
    capsys.readouterr()


# --- restore -----------------------------------------------------------------------

def saved(host, capsys, body=BODY):
    vault = host.work()
    mem = host.memory(body=body)
    original = mem.read_bytes()
    assert crew_memory.main(["save", "--file", str(mem), "--root", str(host.root),
                             "--tag", "memory", "--apply"]) == 0
    capsys.readouterr()
    return vault, mem, original


def restore(host, mem, capsys, *extra, apply=True):
    argv = ["restore", "--file", str(mem), "--root", str(host.root), *extra]
    if apply:
        argv.append("--apply")
    code = crew_memory.main(argv)
    return code, capsys.readouterr().out


def test_restore_round_trips_the_body(host, capsys):
    vault, mem, original = saved(host, capsys)
    note = vault / "memories" / "repo" / "Example fact.md"
    note_bytes = note.read_bytes()
    code, out = restore(host, mem, capsys)
    assert code == 0, out
    assert mem.read_bytes() == original
    assert mem.read_bytes().startswith(FRONTMATTER.encode("utf-8"))
    assert b"\r" not in mem.read_bytes()
    assert note.read_bytes() == note_bytes
    assert crew_memory.resolve_file(str(mem), str(host.root))["state"] == "full-text"


def test_restore_keeps_crlf_frontmatter_bytes(host, capsys):
    vault = host.work()
    mem = host.memory(newline="\r\n")
    assert crew_memory.main(["save", "--file", str(mem), "--root", str(host.root),
                             "--tag", "memory", "--apply"]) == 0
    capsys.readouterr()
    assert vault.exists()
    code, _out = restore(host, mem, capsys)
    data = mem.read_bytes()
    assert code == 0
    assert data.startswith(FRONTMATTER.replace("\n", "\r\n")[:-2].encode("utf-8"))
    assert b"The example fact, in full.\n\nA second paragraph.\n" in data


@pytest.mark.parametrize("state", ["note-missing", "vault-unavailable", "vault-unknown",
                                   "malformed"])
def test_restore_refuses_what_does_not_resolve(host, capsys, state):
    vault, mem, _original = saved(host, capsys)
    if state == "note-missing":
        (vault / "memories" / "repo" / "Example fact.md").unlink()
    elif state == "vault-unavailable":
        host.obsidian({"vaults": {"work": {"path": str(host.base / "gone"),
                                           "role": "primary"}}})
    elif state == "vault-unknown":
        host.obsidian({"vaults": {"other": {"path": str(vault), "role": "primary"}}})
    else:
        mem.write_bytes(FRONTMATTER.encode("utf-8") + b"vault: work | note:\n")
    before = mem.read_bytes()
    code, out = restore(host, mem, capsys)
    assert code == 1 and f"state: {state}" in out
    assert mem.read_bytes() == before


def test_restore_full_text_is_nothing_to_do(host, capsys):
    host.work()
    mem = host.memory()
    before = mem.read_bytes()
    code, out = restore(host, mem, capsys)
    assert code == 0 and "state: full-text" in out and mem.read_bytes() == before


def test_restore_dry_run_writes_nothing(host, capsys):
    _vault, mem, _original = saved(host, capsys)
    before = tree(host.base)
    code, out = restore(host, mem, capsys, apply=False)
    assert code == 1 and tree(host.base) == before
    assert "first line: The example fact, in full." in out
    assert "lines: 3" in out


def test_restore_refuses_a_note_body_that_reads_as_a_pointer(host, capsys):
    vault, mem, _original = saved(host, capsys)
    note = vault / "memories" / "repo" / "Example fact.md"
    note.write_text("---\ntitle: x\n---\n\nvault: work | note: a.md\n", encoding="utf-8")
    before = mem.read_bytes()
    code, _out = restore(host, mem, capsys)
    assert code == 1 and mem.read_bytes() == before


def test_restore_json(host, capsys):
    _vault, mem, _original = saved(host, capsys)
    code, out = restore(host, mem, capsys, "--json")
    row = json.loads(out)
    assert code == 0 and row["state"] == "restored" and row["lines"] == 3


# --- both shells ------------------------------------------------------------------

def _ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


@pytest.mark.parametrize("shell", ["bash", "pwsh"])
def test_migrate_from_bash_and_pwsh(tmp_path, monkeypatch, shell):
    """The preview table is byte-identical from the shell and from a direct
    run. The memory folder and vault paths hold a space."""
    host = Host(tmp_path / "a", monkeypatch)
    vault = host.vault("work vault")
    host.obsidian({"vaults": {"work": {"path": str(vault), "role": "primary"}}})
    three(host)
    args = [sys.executable, SCRIPT, "migrate", "--memory-dir", str(host.mem), "--root",
            str(host.root), "--tag", "memory"]
    if shell == "bash":
        bash = crew_fixtures.resolve_bash()
        if not bash:
            pytest.skip("no bash on this machine - the bash flavour is SKIPPED")
        script = tmp_path / "migrate-from-bash.sh"
        script.write_text('exec "$@"\n', encoding="ascii", newline="\n")
        argv = [bash, str(script).replace("\\", "/"), *args]
    else:
        pwsh = crew_fixtures.resolve_pwsh()
        if not pwsh:
            pytest.skip("no pwsh 7 on this machine - the pwsh flavour is SKIPPED")
        command = "& " + " ".join(_ps_quote(a) for a in args) + "; exit $LASTEXITCODE"
        argv = [pwsh, "-NoProfile", "-NonInteractive", "-Command", command]
    outs = []
    for each in (args, argv):
        proc = subprocess.run(each, capture_output=True, check=False, env=host.env(),
                              timeout=120)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        outs.append(proc.stdout)
    assert outs[0] == outs[1] and b"convert" in outs[0]


# --- review round 1 ---------------------------------------------------------------

def test_default_project_is_the_memory_folders_project(tmp_path, monkeypatch, capsys):
    """`~/.claude/projects/<slug>/memory`: the project defaults to `<slug>`,
    not to the basename of --root."""
    host = Host(tmp_path / "a", monkeypatch)
    vault = host.work()
    folder = host.home / "projects" / "-home-me-alpha" / "memory"
    folder.mkdir(parents=True)
    host.mem = folder
    host.memory(name="role.md", frontmatter=fm("Role"))
    code, out = run(host, capsys, apply=True)
    assert code == 0, out
    assert (vault / "memories" / "-home-me-alpha" / "Role.md").exists()


def _project_folder(host, slug, body):
    folder = host.home / "projects" / slug / "memory"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "user_role.md").write_text(fm("User role") + body, encoding="utf-8",
                                         newline="\n")
    return folder


def _migrate(host, capsys, folder, *extra, apply=True):
    host.mem = folder
    return run(host, capsys, *extra, apply=apply)


def test_a_second_projects_folder_never_appends_to_the_first(host, capsys):
    """Must block: two projects, one memory name, one note path (forced by
    --project or --note-dir). The second is refused, its file untouched."""
    vault = host.work()
    first = _project_folder(host, "proj-a", "A's role.\n")
    second = _project_folder(host, "proj-b", "B's role.\n")
    assert _migrate(host, capsys, first, "--note-dir", "shared")[0] == 0
    note = (vault / "shared" / "User role.md").read_bytes()
    before = (second / "user_role.md").read_bytes()
    code, out = _migrate(host, capsys, second, "--note-dir", "shared")
    assert code == 1
    assert rows(out)["user_role.md"] == \
        "refuse: note belongs to another project (proj-a/user_role)"
    assert (second / "user_role.md").read_bytes() == before
    assert (vault / "shared" / "User role.md").read_bytes() == note


def test_the_same_projects_rerun_still_appends(host, capsys):
    """Must allow: a note this project wrote (crash recovery, or a pointer
    turned back into full text) is still `append`."""
    vault = host.work()
    folder = _project_folder(host, "proj-a", "A's role.\n")
    assert _migrate(host, capsys, folder)[0] == 0
    assert crew_memory.main(["restore", "--file", str(folder / "user_role.md"),
                             "--root", str(host.root), "--apply"]) == 0
    capsys.readouterr()
    (folder / "user_role.md").write_text(fm("User role") + "A's role, revised.\n",
                                         encoding="utf-8", newline="\n")
    code, out = _migrate(host, capsys, folder, apply=False)
    assert code == 1 and rows(out)["user_role.md"] == "append"
    assert _migrate(host, capsys, folder)[0] == 0
    assert "## Update" in (vault / "memories" / "proj-a" / "User role.md").read_text(
        encoding="utf-8")


def test_a_note_without_a_project_line_is_refused(host, capsys):
    vault = host.work()
    (vault / "memories" / "repo").mkdir(parents=True)
    (vault / "memories" / "repo" / "Mine.md").write_text(
        '---\nmemory_id: "mine"\n---\n\nolder\n', encoding="utf-8")
    host.memory(name="mine.md", frontmatter=fm("Mine"))
    code, out = run(host, capsys)
    assert code == 1
    assert rows(out)["mine.md"] == "refuse: note belongs to another project (unknown project/mine)"


def test_restore_refuses_a_memory_changed_before_the_replace(host, capsys, monkeypatch):
    """Must block: a write to the memory between the plan and the replace is
    kept; restore refuses and writes nothing, and leaves no temp file."""
    _vault, mem, _original = saved(host, capsys)
    real = crew_memory._write_temp  # pylint: disable=protected-access
    edited = FRONTMATTER.encode("utf-8") + b"Written by someone else meanwhile.\n"

    def racing(directory, data, mode=None):
        temp = real(directory, data, mode)
        mem.write_bytes(edited)
        return temp

    monkeypatch.setattr(crew_memory, "_write_temp", racing)
    code, out = restore(host, mem, capsys)
    assert code == 1 and "the memory file changed during restore" in out
    assert mem.read_bytes() == edited
    assert sorted(p.name for p in mem.parent.iterdir()) == [mem.name]


def test_migrate_refuses_a_directory_named_md(host, capsys):
    host.work()
    (host.mem / "folder.md").mkdir()
    host.memory(name="ok.md", frontmatter=fm("Ok"))
    code, out = run(host, capsys)
    assert code == 1 and rows(out)["folder.md"] == "refuse: not a file"
    assert rows(out)["ok.md"] == "convert"


def test_migrate_a_file_that_vanishes_is_a_refuse_row(host, capsys, monkeypatch):
    host.work()
    host.memory(name="gone.md", frontmatter=fm("Gone"))
    real = crew_memory._read_bytes  # pylint: disable=protected-access

    def vanish(path):
        if str(path).endswith("gone.md"):
            raise FileNotFoundError(2, "No such file or directory")
        return real(path)

    monkeypatch.setattr(crew_memory, "_read_bytes", vanish)
    code, out = run(host, capsys)
    assert code == 1 and rows(out)["gone.md"] == "refuse: unreadable"


def test_migrate_project_with_a_slash_exits_2(host, capsys):
    host.work()
    host.memory(name="ok.md", frontmatter=fm("Ok"))
    before = tree(host.base)
    with pytest.raises(SystemExit) as caught:
        run(host, capsys, "--project", "a/b", apply=True)
    assert caught.value.code == 2 and tree(host.base) == before
