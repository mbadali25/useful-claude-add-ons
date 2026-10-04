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
                   CREW_OBSIDIAN_CONFIG=str(self.config), PYTHONIOENCODING="utf-8")
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

    monkeypatch.setattr(crew_memory.os, "link", boom)
    monkeypatch.setattr(crew_memory.os, "replace", boom)
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
