"""`crew_memory.py save`: write the vault note, then turn the native memory into a pointer.

The order is the whole point. The vault note is written and read back first;
only then is the native memory's body replaced by the pointer line. Every
refusal, and every failure at any step, leaves the native file byte-identical,
and a dangling pointer is never written. Each failure ordering has a test:

- the note write fails -> no note, native unchanged;
- the read-back fails -> native unchanged;
- the pointer write fails (temp write or the replace) -> the note exists, the
  native file is unchanged and no temp file is left beside it.

Every fixture is under `tmp_path`: `HOME`, `USERPROFILE`,
`CREW_OBSIDIAN_CONFIG` and the crew repo root point at it, and the date comes
from `crew_memory.today`, which the tests replace.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_memory  # noqa: E402  pylint: disable=wrong-import-position

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(crew_memory.__file__)), "crew_memory.py")
DAY1, DAY2 = "2026-10-01", "2026-10-03"
FRONTMATTER = (
    "---\n"
    "name: Example fact\n"
    "description: One sentence that stays useful with no vault.\n"
    "metadata:\n"
    "  type: project\n"
    "---\n"
    "\n"
)
BODY = "The example fact, in full.\n\nA second paragraph.\n"
NOTE = "memories/repo/Example fact.md"
POINTER = "vault: work | note: " + NOTE


class Host:
    """One fixture machine: a home, an Obsidian config, a crew repo root."""

    def __init__(self, base, monkeypatch):
        self.base = base
        self.home = base / "home"
        self.root = base / "repo"
        self.mem = base / "home" / "memory dir"
        for path in (self.home, self.root, self.mem):
            path.mkdir(parents=True, exist_ok=True)
        self.config = self.home / "obsidian-config.json"
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("USERPROFILE", str(self.home))
        monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(self.config))
        # The save's kernel lock files live in a per-user cache, outside `base`
        # so a tree hash of the fixture never sees them: conftest's per-test
        # XDG_CACHE_HOME (which a pwsh spawn must use, L-0557), also given as
        # LOCALAPPDATA, the Windows base.
        self.cache = pathlib.Path(os.environ.get("XDG_CACHE_HOME")
                                  or base.parent / f"{base.name}-cache")
        monkeypatch.setenv("XDG_CACHE_HOME", str(self.cache))
        monkeypatch.setenv("LOCALAPPDATA", str(self.cache))
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        monkeypatch.setattr(crew_memory, "today", lambda: DAY1)

    def vault(self, name, obsidian=True):
        path = self.base / "vaults" / name
        path.mkdir(parents=True, exist_ok=True)
        if obsidian:
            (path / ".obsidian").mkdir(exist_ok=True)
        return path

    def obsidian(self, data):
        self.config.write_text(json.dumps(data), encoding="utf-8", newline="\n")

    def work(self, **extra):
        """The common shape: one primary vault named `work`."""
        vault = self.vault("work")
        self.obsidian(dict({"vaults": {"work": {"path": str(vault), "role": "primary"}}},
                           **extra))
        return vault

    def crew_vault_path(self, value):
        crew = self.root / ".crew"
        crew.mkdir(exist_ok=True)
        (crew / "config.json").write_text(
            json.dumps({"memory": {"vaultPath": value}}), encoding="utf-8", newline="\n")

    def memory(self, body=BODY, name="fact.md", frontmatter=FRONTMATTER, newline="\n"):
        path = self.mem / name
        path.write_bytes((frontmatter + body).replace("\n", newline).encode("utf-8"))
        return path

    def env(self):
        env = dict(os.environ)
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   CREW_OBSIDIAN_CONFIG=str(self.config), PYTHONIOENCODING="utf-8",
                   XDG_CACHE_HOME=str(self.cache), LOCALAPPDATA=str(self.cache))
        env.pop("OBSIDIAN_VAULT_PATH", None)
        return env


@pytest.fixture(name="host")
def _host(tmp_path, monkeypatch):
    return Host(tmp_path / "a", monkeypatch)


def save(host, mem, capsys, *extra, tags=("memory",), apply=True):
    argv = ["save", "--file", str(mem), "--root", str(host.root)]
    for tag in tags:
        argv += ["--tag", tag]
    argv += list(extra)
    if apply:
        argv.append("--apply")
    code = crew_memory.main(argv)
    return code, capsys.readouterr().out


def tree(base):
    """`{relative path: sha256 or 'dir'}` for everything under `base`."""
    found = {}
    for top, dirs, files in os.walk(base):
        for name in dirs:
            found[os.path.relpath(os.path.join(top, name), base)] = "dir"
        for name in files:
            full = os.path.join(top, name)
            with open(full, "rb") as handle:
                found[os.path.relpath(full, base)] = hashlib.sha256(handle.read()).hexdigest()
    return found


def state_line(out):
    return next((line for line in out.splitlines() if line.startswith("state: ")), "")


def expected_note(body=BODY, title="Example fact", tags=("memory",), day=DAY1,
                  project="repo", memory_id="fact", kind="concept"):
    tag_lines = "".join(f"  - {t}\n" for t in tags)
    return (f"---\ntype: {kind}\ntitle: {json.dumps(title)}\ncreated: {day}\nupdated: {day}\n"
            f"status: seed\ntags:\n{tag_lines}project: {json.dumps(project)}\n"
            f"memory_id: {json.dumps(memory_id)}\n---\n\n{body.strip(chr(10))}\n")


# --- dry run and the happy path ---------------------------------------------

def test_save_dry_run_writes_nothing(host, capsys):
    host.work()
    mem = host.memory()
    before = tree(host.base)
    code, out = save(host, mem, capsys, apply=False)
    assert code == 1, out
    assert tree(host.base) == before
    assert "vault: work" in out
    assert f"note: {NOTE}" in out
    assert "action: create" in out
    assert f"pointer: {POINTER}" in out


def test_save_apply_writes_note_then_pointer(host, capsys):
    vault = host.work()
    mem = host.memory()
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert state_line(out) == "state: pointer-written"
    note = vault / "memories" / "repo" / "Example fact.md"
    assert note.read_bytes().decode("utf-8") == expected_note()
    # The blank line after `---` was body; the frontmatter bytes are kept.
    assert mem.read_bytes() == (FRONTMATTER[:-1] + POINTER + "\n").encode("utf-8")
    row = crew_memory.resolve_file(str(mem), str(host.root))
    assert row["state"] == "resolved"
    assert row["path"] == os.path.realpath(str(note))


def test_frontmatter_bytes_are_kept_exactly(host, capsys):
    host.work()
    odd = "---\nname: Example fact\nx:   'keep  me'  \n---\n"
    mem = host.memory(body="\n\n" + BODY, frontmatter=odd)
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert mem.read_bytes() == (odd + POINTER + "\n").encode("utf-8")


def test_pointer_and_note_hold_no_absolute_path(host, capsys):
    vault = host.work()
    mem = host.memory()
    assert save(host, mem, capsys)[0] == 0
    note = (vault / "memories" / "repo" / "Example fact.md").read_text(encoding="utf-8")
    for text in (mem.read_text(encoding="utf-8"), note):
        assert str(vault) not in text
        assert str(host.home) not in text
        assert str(host.base) not in text


def test_outputs_are_lf_only(host, capsys):
    vault = host.work()
    mem = host.memory(newline="\r\n")
    assert save(host, mem, capsys)[0] == 0
    assert b"\r" not in (vault / "memories" / "repo" / "Example fact.md").read_bytes()
    # The frontmatter bytes are kept as they were; the pointer line adds no CR.
    assert mem.read_bytes().endswith(("\r\n---\r\n" + POINTER + "\n").encode("utf-8"))
    assert (vault / "memories" / "repo" / "Example fact.md").read_bytes().decode(
        "utf-8") == expected_note()


def test_options_shape_the_note(host, capsys):
    vault = host.work()
    mem = host.memory()
    code, out = save(host, mem, capsys, "--title", "Other title", "--type", "decision",
                     "--project", "proj", tags=("a/b", "c_d-1"))
    assert code == 0, out
    note = vault / "memories" / "proj" / "Other title.md"
    assert note.read_text(encoding="utf-8") == expected_note(
        title="Other title", tags=("a/b", "c_d-1"), project="proj", kind="decision")


def test_explicit_note_path_sets_the_title(host, capsys):
    vault = host.work()
    mem = host.memory()
    code, out = save(host, mem, capsys, "--note", "deep/dir/Named.md")
    assert code == 0, out
    text = (vault / "deep" / "dir" / "Named.md").read_text(encoding="utf-8")
    assert 'title: "Named"\n' in text
    assert mem.read_text(encoding="utf-8").endswith("vault: work | note: deep/dir/Named.md\n")


def test_quoted_name_line_gives_the_title(host, capsys):
    vault = host.work()
    mem = host.memory(frontmatter="---\nname: \"Quoted fact\"\n---\n")
    assert save(host, mem, capsys)[0] == 0
    assert (vault / "memories" / "repo" / "Quoted fact.md").is_file()


def test_native_file_mode_is_kept(host, capsys):
    if os.name == "nt":
        pytest.skip("POSIX modes only")
    host.work()
    mem = host.memory()
    os.chmod(mem, 0o640)
    assert save(host, mem, capsys)[0] == 0
    assert (os.stat(mem).st_mode & 0o777) == 0o640


# --- the writable vault -------------------------------------------------------

def test_no_roles_takes_the_default_vault(host, capsys):
    first, second = host.vault("first"), host.vault("second")
    host.obsidian({"vaults": {"first": {"path": str(first)},
                              "second": {"path": str(second), "default": True}}})
    mem = host.memory()
    assert save(host, mem, capsys)[0] == 0
    assert (second / NOTE).is_file()
    assert not (first / "memories").exists()
    assert "vault: second | note: " in mem.read_text(encoding="utf-8")


def test_no_roles_no_default_takes_the_first(host, capsys):
    first, second = host.vault("first"), host.vault("second")
    host.obsidian({"vaults": {"first": {"path": str(first)},
                              "second": {"path": str(second)}}})
    assert save(host, host.memory(), capsys)[0] == 0
    assert (first / NOTE).is_file()
    assert not (second / "memories").exists()


def test_no_obsidian_config_uses_crew_memory_vault_path(host, capsys):
    vault = host.vault("mem")
    host.crew_vault_path(str(vault))
    mem = host.memory()
    assert save(host, mem, capsys)[0] == 0
    assert (vault / NOTE).is_file()
    assert "vault: memory | note: " in mem.read_text(encoding="utf-8")
    assert crew_memory.resolve_file(str(mem), str(host.root))["state"] == "resolved"


def test_legacy_top_level_vault_path(host, capsys):
    vault = host.vault("legacy")
    host.obsidian({"vaultPath": str(vault)})
    mem = host.memory()
    assert save(host, mem, capsys)[0] == 0
    assert (vault / NOTE).is_file()
    assert crew_memory.resolve_file(str(mem), str(host.root))["state"] == "resolved"


# --- must keep the full text ------------------------------------------------------

def kept(host, mem, capsys, code, reason, *extra, tags=("memory",)):
    """Run save --apply; assert the native file and every other file is
    byte-identical, the reason is printed and the exit code is `code`."""
    before_mem = mem.read_bytes()
    before = tree(host.base)
    got, out = save(host, mem, capsys, *extra, tags=tags)
    assert mem.read_bytes() == before_mem
    assert tree(host.base) == before
    assert state_line(out).startswith("state: kept-full-text: "), out
    assert reason in out, out
    assert got == code, out
    return out


def test_no_vault_configured_keeps_full_text_exit_0(host, capsys):
    kept(host, host.memory(), capsys, 0, "kept-full-text: no vault configured")


def test_empty_obsidian_config_is_no_vault_configured(host, capsys):
    host.obsidian({})
    kept(host, host.memory(), capsys, 0, "kept-full-text: no vault configured")


def test_primary_not_on_disk_never_falls_back_to_recall(host, capsys):
    recall = host.vault("recall")
    host.obsidian({"vaults": {
        "work": {"path": str(host.base / "vaults" / "gone"), "role": "primary"},
        "recall": {"path": str(recall), "role": "recall"}}})
    kept(host, host.memory(), capsys, 1, "vault unavailable")
    assert os.listdir(recall) == [".obsidian"]


def test_two_primaries_are_refused(host, capsys):
    one, two = host.vault("one"), host.vault("two")
    host.obsidian({"vaults": {"one": {"path": str(one), "role": "primary"},
                              "two": {"path": str(two), "role": "primary"}}})
    kept(host, host.memory(), capsys, 1, "several primaries")


def test_no_primary_among_roles_is_refused(host, capsys):
    recall = host.vault("recall")
    host.obsidian({"vaults": {"recall": {"path": str(recall), "role": "recall"},
                              "skip": {"path": str(host.vault("skip")), "role": "ignore"}}})
    kept(host, host.memory(), capsys, 1, "no primary")


def test_directory_without_obsidian_is_not_a_vault(host, capsys):
    plain = host.vault("plain", obsidian=False)
    host.obsidian({"vaults": {"plain": {"path": str(plain), "role": "primary"}}})
    kept(host, host.memory(), capsys, 1, "not a vault")


def test_unreadable_obsidian_config_is_refused(host, capsys):
    host.config.write_text("{not json", encoding="utf-8")
    kept(host, host.memory(), capsys, 1, "config unreadable")


def test_malformed_guard_block_is_refused(host, capsys):
    host.work(guard="yes")
    kept(host, host.memory(), capsys, 1, "config unreadable")


def _existing(vault, text):
    note = vault / "memories" / "repo" / "Example fact.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_bytes(text.encode("utf-8"))
    return note


@pytest.mark.parametrize("memory_id_line", ['memory_id: "other"\n', ""],
                         ids=["other-memory-id", "no-memory-id"])
def test_existing_note_of_another_memory_is_a_collision(host, capsys, memory_id_line):
    vault = host.work()
    _existing(vault, f"---\ntype: concept\ntitle: \"Example fact\"\n{memory_id_line}---\n\nx\n")
    kept(host, host.memory(), capsys, 1, "collision")


@pytest.mark.parametrize("note", ["a/../b.md", "/abs/b.md", "a\\b.md", "a/b.txt", "c:/b.md"],
                         ids=["dotdot", "absolute", "backslash", "not-md", "drive"])
def test_bad_note_path_is_refused(host, capsys, note):
    host.work()
    kept(host, host.memory(), capsys, 1, "bad-note-path", "--note", note)


def test_title_with_a_slash_is_a_bad_note_path(host, capsys):
    host.work()
    kept(host, host.memory(), capsys, 1, "bad-note-path", "--title", "a/b")


def test_symlinked_directory_in_the_vault_is_outside_vault(host, capsys):
    vault = host.work()
    elsewhere = host.base / "elsewhere"
    elsewhere.mkdir()
    (vault / "memories").mkdir()
    try:
        os.symlink(str(elsewhere), str(vault / "memories" / "repo"), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks cannot be made here: {exc}")
    kept(host, host.memory(), capsys, 1, "outside-vault")
    assert not os.listdir(elsewhere)


def test_symlink_to_a_folder_inside_the_vault_is_still_outside_vault(host, capsys):
    """The link is refused even when its target stays in the vault: the
    resolver refuses every symlink, so a note reached through one would be a
    pointer that never resolves."""
    vault = host.work()
    (vault / "memories").mkdir()
    (vault / "other").mkdir()
    try:
        os.symlink(str(vault / "other"), str(vault / "memories" / "repo"),
                   target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks cannot be made here: {exc}")
    out = kept(host, host.memory(), capsys, 1, "outside-vault")
    assert "passes a symlink" in out
    assert not os.listdir(vault / "other")


def test_ascii_only_vault_refuses_a_non_ascii_body(host, capsys):
    host.work(guard={"asciiOnly": True})
    kept(host, host.memory(body="Caf\u00e9 notes.\n"), capsys, 1, "ascii-required")


def test_ascii_only_vault_accepts_an_ascii_body(host, capsys):
    host.work(guard={"asciiOnly": True})
    assert save(host, host.memory(), capsys)[0] == 0


# --- failure orderings ------------------------------------------------------------

def test_note_write_failure_leaves_native_unchanged(host, capsys, monkeypatch):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(crew_memory, "_write_temp", boom)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: note write failed" in out
    assert mem.read_bytes() == original
    assert not (vault / NOTE).exists()
    assert sorted(os.listdir(host.mem)) == ["fact.md"]


def test_note_link_failure_leaves_native_unchanged_and_no_temp(host, capsys, monkeypatch):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(crew_memory, "_create_exclusive", boom)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: note write failed" in out
    assert mem.read_bytes() == original
    assert os.listdir(vault / "memories" / "repo") == []


def test_read_back_failure_writes_no_pointer(host, capsys, monkeypatch):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()
    monkeypatch.setattr(crew_memory, "resolve_pointer",
                        lambda *_a: ("note-missing", "simulated", None))
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: note not readable after write" in out
    assert mem.read_bytes() == original
    assert (vault / NOTE).is_file()


def test_read_back_content_mismatch_writes_no_pointer(host, capsys, monkeypatch):
    host.work()
    mem = host.memory()
    original = mem.read_bytes()
    real = crew_memory._read_bytes  # pylint: disable=protected-access

    def lying(path):
        data = real(path)
        return data + b"tampered" if path.endswith("Example fact.md") else data

    monkeypatch.setattr(crew_memory, "_read_bytes", lying)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: note not readable after write" in out
    assert mem.read_bytes() == original


@pytest.mark.parametrize("stage", ["temp", "replace"])
def test_pointer_write_failure_keeps_note_and_native(host, capsys, monkeypatch, stage):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()
    real_temp, real_replace = crew_memory._write_temp, os.replace  # pylint: disable=protected-access

    def temp(directory, data, *rest):
        if os.path.samefile(directory, host.mem):
            raise OSError(28, "No space left on device")
        return real_temp(directory, data, *rest)

    def replace(src, dst):
        if os.path.dirname(os.path.abspath(dst)) == str(host.mem):
            raise OSError(13, "Permission denied")
        return real_replace(src, dst)

    if stage == "temp":
        monkeypatch.setattr(crew_memory, "_write_temp", temp)
    else:
        monkeypatch.setattr(crew_memory.os, "replace", replace)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: pointer write failed" in out
    assert mem.read_bytes() == original
    assert (vault / NOTE).read_text(encoding="utf-8") == expected_note()
    assert sorted(os.listdir(host.mem)) == ["fact.md"]


def test_native_changed_during_save_is_not_overwritten(host, capsys, monkeypatch):
    host.work()
    mem = host.memory()
    real = crew_memory.apply_note

    def edit_then_write(plan):
        real(plan)
        mem.write_bytes(mem.read_bytes() + b"edited meanwhile\n")

    monkeypatch.setattr(crew_memory, "apply_note", edit_then_write)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: the memory file changed during save" in out
    assert mem.read_bytes().endswith(b"edited meanwhile\n")


# --- append and idempotence -----------------------------------------------------

def test_save_again_appends_a_dated_update(host, capsys, monkeypatch):
    vault = host.work()
    assert save(host, host.memory(), capsys)[0] == 0
    monkeypatch.setattr(crew_memory, "today", lambda: DAY2)
    other = host.base / "other memory dir"
    other.mkdir()
    second = other / "fact.md"
    second.write_bytes((FRONTMATTER + "A newer statement of the fact.\n").encode("utf-8"))
    code, out = save(host, second, capsys)
    assert code == 0, out
    assert "action: append" in out
    text = (vault / NOTE).read_text(encoding="utf-8")
    assert f"created: {DAY1}\n" in text
    assert f"updated: {DAY2}\n" in text
    assert f"updated: {DAY1}\n" not in text
    assert "The example fact, in full." in text
    assert text.endswith(f"\n\n## Update {DAY2}\n\nA newer statement of the fact.\n")
    assert second.read_text(encoding="utf-8").endswith(POINTER + "\n")


def test_save_on_a_pointer_is_a_no_op(host, capsys):
    host.work()
    mem = host.memory()
    assert save(host, mem, capsys)[0] == 0
    before = tree(host.base)
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert state_line(out) == "state: already-pointer"
    assert tree(host.base) == before


def test_same_body_twice_is_unchanged(host, capsys):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()
    assert save(host, mem, capsys)[0] == 0
    after_first = tree(host.base)
    note_bytes = (vault / NOTE).read_bytes()
    mem.write_bytes(original)  # the harness wrote the same full text back
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert "action: unchanged" in out
    assert (vault / NOTE).read_bytes() == note_bytes
    assert tree(host.base) == after_first


def test_save_on_a_dangling_pointer_reports_its_state(host, capsys):
    host.work()
    mem = host.memory(body="vault: work | note: memories/repo/Missing.md\n")
    before = tree(host.base)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert state_line(out) == "state: note-missing"
    assert tree(host.base) == before


def test_save_on_a_malformed_pointer_reports_malformed(host, capsys):
    host.work()
    mem = host.memory(body="vault: work | note: /abs.md\n")
    before = tree(host.base)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert state_line(out) == "state: malformed"
    assert tree(host.base) == before


# --- usage ------------------------------------------------------------------------

@pytest.mark.parametrize("tags,extra,frontmatter", [
    ((), (), FRONTMATTER),
    (("has space",), (), FRONTMATTER),
    (("Upper",), (), FRONTMATTER),
    (("memory",), ("--type", "daily"), FRONTMATTER),
    (("memory",), (), "---\ndescription: no name line\n---\n"),
], ids=["no-tag", "tag-with-space", "tag-upper-case", "unknown-type", "no-name-no-title"])
def test_save_usage_errors_exit_2(host, capsys, tags, extra, frontmatter):
    host.work()
    mem = host.memory(frontmatter=frontmatter)
    before = tree(host.base)
    with pytest.raises(SystemExit) as raised:
        code, _out = save(host, mem, capsys, *extra, tags=tags)
        raise SystemExit(code)
    assert raised.value.code == 2
    assert tree(host.base) == before


def test_missing_memory_file_exits_2(host, capsys):
    code, _out = save(host, host.mem / "absent.md", capsys)
    assert code == 2


def test_json_output(host, capsys):
    host.work()
    code, out = save(host, host.memory(), capsys, "--json")
    assert code == 0
    row = json.loads(out)
    assert row["state"] == "pointer-written"
    assert row["pointer"] == POINTER
    assert row["action"] == "create"


# --- both shells ------------------------------------------------------------------

def _ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


def _shell_argv(shell, mem, host):
    args = [sys.executable, SCRIPT, "save", "--file", str(mem), "--root", str(host.root),
            "--tag", "memory", "--apply"]
    if shell == "bash":
        bash = crew_fixtures.resolve_bash()
        if not bash:
            pytest.skip("no bash on this machine - the bash flavour is SKIPPED")
        return [bash, "-c", '"$@"', "save", *args]
    pwsh = crew_fixtures.resolve_pwsh()
    if not pwsh:
        pytest.skip("no pwsh 7 on this machine - the pwsh flavour is SKIPPED")
    command = "& " + " ".join(_ps_quote(a) for a in args) + "; exit $LASTEXITCODE"
    return [pwsh, "-NoProfile", "-NonInteractive", "-Command", command]


@pytest.mark.parametrize("shell", ["bash", "pwsh"])
def test_save_from_bash_and_pwsh(tmp_path, monkeypatch, shell):
    """Each shell is its own case and skips on its own. The vault path holds a
    space; the note and native file must match what the in-process run
    writes, byte for byte (the date is the real one in both)."""
    results = []
    for label in ("direct", shell):
        host = Host(tmp_path / label, monkeypatch)
        vault = host.vault("work vault")
        host.obsidian({"vaults": {"work": {"path": str(vault), "role": "primary"}}})
        mem = host.memory()
        if label == "direct":
            argv = [sys.executable, SCRIPT, "save", "--file", str(mem), "--root",
                    str(host.root), "--tag", "memory", "--apply"]
        else:
            argv = _shell_argv(shell, mem, host)
        proc = subprocess.run(argv, capture_output=True, check=False, env=host.env(),
                              timeout=120)
        out = proc.stdout.decode("utf-8")
        assert proc.returncode == 0, out + proc.stderr.decode("utf-8")
        results.append(((vault / NOTE).read_bytes(), mem.read_bytes()))
    assert results[0] == results[1]


# --- review round 1: concurrency, locks and edge cases ----------------------------
#
# The invariant every test below asserts: no byte of a memory is lost. Each
# native file either still holds its full text, or its body is in the note.

def _keeps_every_byte(native, body, note_path):
    text = native.read_text(encoding="utf-8")
    note = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    assert body.strip() in text or body.strip() in note, (text, note)


def _locks(base):
    """Lock files beside the vault or memory files: there must never be one."""
    return [p for p in tree(base) if p.endswith(".lock")]


def _held(path):
    """Whether some save holds the lock for `path` right now: a fresh take,
    through a new open file, is refused."""
    handles = crew_memory._take_lock(path)  # pylint: disable=protected-access
    if handles is None:
        return True
    crew_memory._release(handles)  # pylint: disable=protected-access
    return False


def test_native_edit_while_the_pointer_temp_is_written_is_kept(host, capsys, monkeypatch):
    """Reviewer race A: another session appends to the memory after the
    first compare, while the pointer's temp file is being written."""
    host.work()
    mem = host.memory(body="v1 text\n")
    real = crew_memory._write_temp  # pylint: disable=protected-access

    def temp(directory, data, *rest):
        if b"vault: work" in data and data.startswith(b"---"):
            with open(mem, "ab") as handle:
                handle.write(b"v2 added by another session\n")
        return real(directory, data, *rest)

    monkeypatch.setattr(crew_memory, "_write_temp", temp)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "the memory file changed during save" in out
    assert mem.read_bytes().endswith(b"v1 text\nv2 added by another session\n")


def _second_memory(host, label, body):
    directory = host.base / label
    directory.mkdir()
    path = directory / "fact.md"
    path.write_bytes((FRONTMATTER + body).encode("utf-8"))
    return path


def test_two_saves_appending_to_one_note_keep_every_byte(host, capsys, monkeypatch):
    """Reviewer race B, on real threads: save S2 is inside its note write
    when save S1 of another memory with the same stem runs. S1 must not
    write a pointer whose body S2's replace then drops."""
    import threading  # pylint: disable=import-outside-toplevel
    vault = host.work()
    assert save(host, host.memory(body="base\n"), capsys)[0] == 0
    one = _second_memory(host, "m1", "text ONE\n")
    two = _second_memory(host, "m2", "text TWO\n")
    plan_one = crew_memory.plan_save(str(one), str(host.root), ["memory"])
    plan_two = crew_memory.plan_save(str(two), str(host.root), ["memory"])
    inside, done, results = threading.Event(), threading.Event(), {}
    real = crew_memory._write_temp  # pylint: disable=protected-access

    def temp(directory, data, *rest):
        if b"text TWO" in data and not inside.is_set():
            inside.set()
            done.wait(20)
        return real(directory, data, *rest)

    monkeypatch.setattr(crew_memory, "_write_temp", temp)
    worker = threading.Thread(target=lambda: results.update(two=crew_memory.apply_save(plan_two)))
    worker.start()
    assert inside.wait(20)
    results["one"] = crew_memory.apply_save(plan_one)
    done.set()
    worker.join(20)
    note = vault / NOTE
    _keeps_every_byte(one, "text ONE", note)
    _keeps_every_byte(two, "text TWO", note)
    assert "base" in note.read_text(encoding="utf-8")
    assert results["one"]["state"].startswith("kept-full-text: another save is running now")
    assert not _locks(host.base)


def test_a_plan_made_before_another_save_is_refused(host, capsys):
    vault = host.work()
    assert save(host, host.memory(body="base\n"), capsys)[0] == 0
    one = _second_memory(host, "m1", "text ONE\n")
    two = _second_memory(host, "m2", "text TWO\n")
    plan_one = crew_memory.plan_save(str(one), str(host.root), ["memory"])
    assert crew_memory.apply_save(
        crew_memory.plan_save(str(two), str(host.root), ["memory"]))["exit"] == 0
    row = crew_memory.apply_save(plan_one)
    assert row["exit"] == 1
    assert "the note changed during save" in row["state"]
    _keeps_every_byte(one, "text ONE", vault / NOTE)
    _keeps_every_byte(two, "text TWO", vault / NOTE)


@pytest.mark.parametrize("which", ["note", "native"])
def test_a_held_lock_refuses_and_writes_nothing(host, capsys, which):
    """A save holding either lock right now: the second save writes nothing
    and says another save is running now."""
    vault = host.work()
    mem = host.memory()
    target = str(vault / NOTE) if which == "note" else str(mem)
    held = crew_memory._take_lock(target)  # pylint: disable=protected-access
    assert held is not None
    try:
        out = kept(host, mem, capsys, 1, "another save is running now")
    finally:
        crew_memory._release(held)  # pylint: disable=protected-access
    assert f"(it holds a lock on {target})" in out
    assert save(host, mem, capsys)[0] == 0


def test_locks_are_released_after_a_failed_save(host, capsys, monkeypatch):
    vault = host.work()
    mem = host.memory()
    monkeypatch.setattr(crew_memory, "resolve_pointer",
                        lambda *_a: ("note-missing", "simulated", None))
    assert save(host, mem, capsys)[0] == 1
    assert not _locks(host.base)
    assert not _held(str(vault / NOTE)) and not _held(str(mem))


def test_no_hard_links_never_replaces_over_a_note(host, capsys, monkeypatch):
    """FIX3: `os.link` refused (EPERM, a file system without hard links):
    the note is created with O_EXCL, never `os.replace`d into place."""
    vault = host.work()
    mem = host.memory()
    replaced = []
    real_replace = os.replace

    def no_link(*_args, **_kwargs):
        raise OSError(1, "Operation not permitted")

    def replace(src, dst):
        replaced.append(os.path.abspath(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(crew_memory.os, "link", no_link)
    monkeypatch.setattr(crew_memory.os, "replace", replace)
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert os.path.abspath(str(vault / NOTE)) not in replaced
    assert (vault / NOTE).read_text(encoding="utf-8") == expected_note()
    assert sorted(os.listdir(vault / "memories" / "repo")) == ["Example fact.md"]


def test_no_hard_links_and_a_note_appearing_is_refused(host, capsys, monkeypatch):
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()

    def no_link(_src, dst):
        with open(dst, "wb") as handle:
            handle.write(b"someone else's note\n")
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(crew_memory.os, "link", no_link)
    code, out = save(host, mem, capsys)
    assert code == 1, out
    assert "kept-full-text: note write failed" in out
    assert (vault / NOTE).read_bytes() == b"someone else's note\n"
    assert mem.read_bytes() == original


def test_an_existing_note_that_is_not_utf8_is_refused(host, capsys):
    vault = host.work()
    note = _existing(vault, "---\ntitle: \"Example fact\"\nupdated: 2026-01-01\n"
                            "memory_id: \"fact\"\n---\n\nold\n")
    note.write_bytes(note.read_bytes() + b"\xff\xfe latin-1 \xe9\n")
    before = note.read_bytes()
    kept(host, host.memory(), capsys, 1, "not UTF-8")
    assert note.read_bytes() == before


def test_an_append_keeps_every_existing_byte_bom_and_crlf_included(host, capsys):
    vault = host.work()
    old = ("﻿---\r\ntitle: \"Example fact\"\r\ncreated: 2026-01-01\r\nupdated: 2026-01-01"
           "\r\nmemory_id: \"fact\"\r\n---\r\n\r\nold body\r\n\r\n\r\n")
    note = _existing(vault, old)
    assert save(host, host.memory(), capsys)[0] == 0
    want = old.replace("updated: 2026-01-01", f"updated: {DAY1}") + (
        f"\n## Update {DAY1}\n\n{BODY.strip()}\n")
    assert note.read_bytes() == want.encode("utf-8")


def test_memory_md_is_refused(host, capsys):
    """FIX5 / round-2 NIT 1: the index is refused as the documented
    kept-full-text line, exit 1, in text and in --json."""
    host.work()
    mem = host.memory(name="MEMORY.md")
    out = kept(host, mem, capsys, 1, "kept-full-text: MEMORY.md is the index")
    assert "Traceback" not in out
    code, out = save(host, mem, capsys, "--json")
    assert code == 1
    row = json.loads(out)
    assert row["state"].startswith("kept-full-text: MEMORY.md is the index")
    assert row["reason"].startswith("MEMORY.md is the index")
    row = crew_memory.plan_save(str(mem), str(host.root), ["memory"])
    assert row["state"].startswith("kept-full-text: ") and "index" in row["state"]


def _case_sensitive(folder):
    probe = folder / "case-probe.tmp"
    probe.write_text("x", encoding="utf-8")
    try:
        return not (folder / "CASE-PROBE.TMP").exists()
    finally:
        probe.unlink()


def test_a_lower_case_memory_md_is_the_index_only_where_case_folds(host, capsys):
    """Round-2 NIT 5: on a case-sensitive file system a real `memory.md` is
    an ordinary memory, never the index; where case folds (macOS default,
    Windows) it IS the index file and is refused."""
    vault = host.work()
    mem = host.memory(name="memory.md")
    if _case_sensitive(host.mem):
        code, out = save(host, mem, capsys, "--title", "Example fact")
        assert code == 0, out
        assert (vault / NOTE).is_file()
        index = host.memory(name="MEMORY.md")
        kept(host, index, capsys, 1, "MEMORY.md is the index")
    else:
        kept(host, mem, capsys, 1, "MEMORY.md is the index")


def test_the_note_folder_is_fsynced_before_the_pointer(host, capsys, monkeypatch):
    """N1: the note's directory entry is on disk before the pointer is."""
    if os.name == "nt":
        pytest.skip("directories cannot be fsynced on Windows")
    host.work()
    mem = host.memory()
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        if os.path.isdir(f"/proc/self/fd/{fd}") or os.fstat(fd).st_mode & 0o040000:
            events.append("dir")
        return real_fsync(fd)

    def replace(src, dst):
        events.append("replace:" + os.path.basename(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(crew_memory.os, "fsync", fsync)
    monkeypatch.setattr(crew_memory.os, "replace", replace)
    assert save(host, mem, capsys)[0] == 0
    assert "dir" in events
    assert events.index("dir") < events.index("replace:fact.md")


def test_note_modes(host, capsys, monkeypatch):
    """N2: a new note is 0644 less the umask; an appended note keeps its mode."""
    if os.name == "nt":
        pytest.skip("POSIX modes only")
    vault = host.work()
    old_umask = os.umask(0o027)
    try:
        assert save(host, host.memory(), capsys)[0] == 0
    finally:
        os.umask(old_umask)
    note = vault / NOTE
    assert (os.stat(note).st_mode & 0o777) == 0o640
    os.chmod(note, 0o604)
    monkeypatch.setattr(crew_memory, "today", lambda: DAY2)
    assert save(host, _second_memory(host, "m1", "newer\n"), capsys)[0] == 0
    assert (os.stat(note).st_mode & 0o777) == 0o604


def test_a_symlinked_memory_is_refused(host, capsys):
    """N3: replacing a link would leave the link and its target out of step."""
    host.work()
    target = host.memory(name="real.md")
    link = host.mem / "fact.md"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks cannot be made here: {exc}")
    kept(host, link, capsys, 1, "symlink")
    assert os.path.islink(link)


def test_a_double_save_of_one_memory_reports_already_pointer(host, capsys):
    """N4: the second of two saves of the same memory finds it a pointer."""
    host.work()
    mem = host.memory()
    first = crew_memory.plan_save(str(mem), str(host.root), ["memory"])
    second = crew_memory.plan_save(str(mem), str(host.root), ["memory"])
    assert crew_memory.apply_save(first)["state"] == "pointer-written"
    row = crew_memory.apply_save(second)
    assert row["state"] == "already-pointer"
    assert row["exit"] == 0


@pytest.mark.parametrize("title", [".hidden", ".obsidian"])
def test_a_title_starting_with_a_dot_is_refused(host, capsys, title):
    host.work()
    kept(host, host.memory(), capsys, 1, "bad-note-path", "--title", title)


def test_a_note_path_into_a_dot_folder_is_refused(host, capsys):
    host.work()
    kept(host, host.memory(), capsys, 1, "bad-note-path", "--note", ".obsidian/x.md")


def test_memory_id_is_json_decoded_when_compared(host, capsys, monkeypatch):
    """N6: a stem holding a quote is written JSON-escaped and must match
    itself on the next save, not read as a collision."""
    vault = host.work()
    assert save(host, host.memory(name='fact "x".md'), capsys)[0] == 0
    monkeypatch.setattr(crew_memory, "today", lambda: DAY2)
    other = host.base / "m1"
    other.mkdir()
    again = other / 'fact "x".md'
    again.write_bytes((FRONTMATTER + "newer\n").encode("utf-8"))
    code, out = save(host, again, capsys)
    assert code == 0, out
    assert "action: append" in out
    assert (vault / NOTE).read_text(encoding="utf-8").endswith("\n\nnewer\n")


# --- review round 2: kernel locks in the user cache, lock errors --------------------
#
# A save's two locks are `flock` (POSIX) / `msvcrt.locking` (Windows) locks on
# files in a per-user cache, named by the sha256 of the guarded file's real
# path. The OS drops them when the holder exits or is killed, so there is no
# stale lock to judge and no takeover to race.

def _lock_dir(host):
    return host.cache / "crew" / "memory-locks"


def test_lock_files_live_in_the_user_cache_never_beside_the_files(host, capsys):
    vault = host.work()
    mem = host.memory()
    want = {os.path.basename(lock) for p in (str(vault / NOTE), str(mem))
            for lock in crew_memory._lock_paths(p)}  # pylint: disable=protected-access
    assert len(want) == 3  # the note's path; the memory's path and inode
    assert save(host, mem, capsys)[0] == 0
    assert set(os.listdir(_lock_dir(host))) == want
    assert all(len(name) == 64 + len(".lock") for name in want)
    assert sorted(os.listdir(host.mem)) == ["fact.md"]
    assert sorted(os.listdir(vault / "memories" / "repo")) == ["Example fact.md"]
    assert not _locks(host.base)


def test_a_user_file_with_the_old_lock_name_is_never_touched(host, capsys):
    """Round 1 removed any `.<name>.crew-save.lock` older than its TTL, a
    real user file included. Nothing beside the files is a lock now."""
    host.work()
    mem = host.memory()
    user = host.mem / ".fact.md.crew-save.lock"
    user.write_text("user data\n", encoding="utf-8")
    os.utime(user, (1_000_000_000, 1_000_000_000))
    assert save(host, mem, capsys)[0] == 0
    assert user.read_text(encoding="utf-8") == "user data\n"


def test_the_forced_takeover_race_leaves_one_holder(host, monkeypatch):
    """Reviewer q4: saver B runs its whole take in the middle of saver A's.
    Exactly one of them may hold the lock."""
    vault = host.work()
    note = str(vault / NOTE)
    real = crew_memory._os_try_lock  # pylint: disable=protected-access
    got = {}

    def try_lock(handle):
        if "b" not in got:
            got["b"] = None
            got["b"] = crew_memory._take_lock(note)  # pylint: disable=protected-access
        return real(handle)

    monkeypatch.setattr(crew_memory, "_os_try_lock", try_lock)
    got["a"] = crew_memory._take_lock(note)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_memory, "_os_try_lock", real)
    holders = [h for h in (got["a"], got["b"]) if h is not None]
    try:
        assert len(holders) == 1, got
    finally:
        for handles in holders:
            crew_memory._release(handles)  # pylint: disable=protected-access


_CHILD = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import crew_memory
real = crew_memory._write_temp
def temp(directory, data, *rest):
    print("inside", flush=True)
    time.sleep(120)
    return real(directory, data, *rest)
crew_memory._write_temp = temp
sys.exit(crew_memory.main(sys.argv[2:]))
"""


def test_a_save_killed_while_holding_the_lock_does_not_block_the_next(host, capsys):
    """A real save in another process holds both locks inside its note
    write: this save is refused while it runs. Killed (SIGKILL on POSIX,
    TerminateProcess on Windows), it leaves nothing that blocks the next."""
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()
    child = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", _CHILD, os.path.dirname(SCRIPT), "save", "--file", str(mem),
         "--root", str(host.root), "--tag", "memory", "--apply"],
        stdout=subprocess.PIPE, env=host.env())
    try:
        assert child.stdout.readline().strip() == b"inside"
        out = kept(host, mem, capsys, 1, "another save is running now")
        assert f"(it holds a lock on {vault / NOTE})" in out
    finally:
        child.kill()
        child.wait(30)
        child.stdout.close()
    assert mem.read_bytes() == original
    code, out = save(host, mem, capsys)
    assert code == 0, out
    assert mem.read_text(encoding="utf-8").endswith(POINTER + "\n")


@pytest.mark.parametrize("which", ["note", "native"])
def test_a_lock_that_cannot_be_opened_keeps_full_text(host, capsys, monkeypatch, which):
    """FIX 1: any OSError taking a lock (the cache unwritable, a full disk, a
    read-only file system) is a clean kept-full-text, exit 1, and every lock
    already taken is released - the note's, when the memory's fails."""
    vault = host.work()
    mem = host.memory()
    target = str(vault / NOTE) if which == "note" else str(mem)
    locks = crew_memory._lock_paths(target)  # pylint: disable=protected-access
    real = os.open

    def refuse(path, *rest, **kwargs):
        if os.fspath(path) in locks:
            raise PermissionError(13, "Permission denied", path)
        return real(path, *rest, **kwargs)

    monkeypatch.setattr(crew_memory.os, "open", refuse)
    out = kept(host, mem, capsys, 1, "kept-full-text: lock failed")
    assert "Permission denied" in out
    code, out = save(host, mem, capsys, "--json")
    assert code == 1
    row = json.loads(out)
    assert row["state"].startswith("kept-full-text: lock failed")
    assert row["reason"].startswith("lock failed")
    monkeypatch.setattr(crew_memory.os, "open", real)
    assert not _held(str(vault / NOTE)) and not _held(str(mem))
    assert save(host, mem, capsys)[0] == 0


def _no_permissions():
    return os.name == "nt" or os.geteuid() == 0


@pytest.mark.skipif(_no_permissions(), reason="needs POSIX modes and a non-root user")
@pytest.mark.parametrize("folder", ["memory", "note", "cache"])
def test_an_unwritable_folder_keeps_full_text_and_blocks_nothing(host, capsys, folder):
    """FIX 1, with real modes: the memory folder, the note folder or the lock
    cache at 0555 gives a kept-full-text line, never a traceback, and the
    next save once the folder is writable again is not blocked."""
    vault = host.work()
    mem = host.memory()
    original = mem.read_bytes()
    path = {"memory": host.mem, "note": vault / "memories" / "repo",
            "cache": _lock_dir(host)}[folder]
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o555)
    try:
        code, out = save(host, mem, capsys)
    finally:
        os.chmod(path, 0o755)
    reason = {"memory": "pointer write failed", "note": "note write failed",
              "cache": "lock failed"}[folder]
    assert code == 1, out
    assert state_line(out).startswith(f"state: kept-full-text: {reason}"), out
    assert mem.read_bytes() == original
    code, out = save(host, mem, capsys)
    assert code == 0, out


# --- review round 3: no cache folder, one lock per file whatever its spelling --------

def test_no_absolute_cache_folder_keeps_full_text(host, capsys, monkeypatch, tmp_path):
    """FIX (round 3): HOME unset on a uid with no passwd entry makes `~` stay
    `~`. A relative cache folder would lock per working directory - no lock at
    all - and litter a `~` folder there. It is `lock failed: no cache folder`."""
    host.work()
    mem = host.memory()
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    for name in ("XDG_CACHE_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", "~")
    monkeypatch.setenv("USERPROFILE", "~")
    kept(host, mem, capsys, 1, "kept-full-text: lock failed: no cache folder")
    assert os.listdir(work) == []


def _spellings(host, vault):
    """Other names for the native memory and the note: through a symlinked
    folder, through `..`, a hard link, and a case variant."""
    mem = host.memory()
    note = vault / NOTE
    note.parent.mkdir(parents=True)
    note.write_bytes(b"note\n")
    names = {"dotdot": (str(mem), str(host.mem / ".." / host.mem.name / "fact.md")),
             "case": (str(note), str(note.parent / "example FACT.md"))}
    try:
        os.symlink(str(host.mem), str(host.base / "mem-link"))
        names["symlink"] = (str(mem), str(host.base / "mem-link" / "fact.md"))
    except (OSError, NotImplementedError):
        pass
    try:
        os.link(str(mem), str(host.base / "hard.md"))
        names["hardlink"] = (str(mem), str(host.base / "hard.md"))
    except (OSError, NotImplementedError):
        pass
    return names


@pytest.mark.parametrize("spelling", ["dotdot", "case", "symlink", "hardlink"])
def test_every_spelling_of_one_file_takes_the_same_lock(host, spelling):
    """NIT (round 3): normcase(realpath) is a no-op on POSIX and macOS, so a
    case variant on a case-folding volume and a hard link got a lock of their
    own. The lock is keyed on the case-folded real path and on the file's
    (st_dev, st_ino)."""
    names = _spellings(host, host.work())
    if spelling not in names:
        pytest.skip(f"{spelling} cannot be made here")
    first, other = names[spelling]
    held = crew_memory._take_lock(first)  # pylint: disable=protected-access
    assert held is not None
    try:
        assert _held(other)
    finally:
        crew_memory._release(held)  # pylint: disable=protected-access
    assert not _held(other)


def test_the_lock_survives_the_rename_that_replaces_the_file(host):
    """A save replaces the note and the memory with `os.replace`, a new inode.
    A save starting after that rename must still find the lock held."""
    vault = host.work()
    note = vault / NOTE
    note.parent.mkdir(parents=True)
    note.write_bytes(b"old\n")
    held = crew_memory._take_lock(str(note))  # pylint: disable=protected-access
    try:
        fresh = note.parent / "fresh.tmp"
        fresh.write_bytes(b"new\n")
        os.replace(fresh, note)
        assert _held(str(note))
    finally:
        crew_memory._release(held)  # pylint: disable=protected-access
