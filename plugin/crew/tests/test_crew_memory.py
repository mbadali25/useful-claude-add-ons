"""`crew_memory.py resolve` and `check`: native memories as vault pointers.

A native Claude Code memory file may hold one line in place of its body,
`vault: <name> | note: <vault-relative path>`. These tests pin the three
things that can go wrong with that line and must never go wrong silently:

- the GRAMMAR: a pointer that names an absolute path, a drive, a `..` or a
  second field is `malformed`, never resolved and never read as full text;
- the VAULT: a name maps to a path only through this host's own config, an
  unavailable vault is reported and never replaced by another one, and a
  config that does not parse is not "no vaults";
- the NOTE: it must exist under the vault's real path with no symlink on the
  way, or the state says why not.

Every fixture is under `tmp_path`: `HOME`, `USERPROFILE`,
`CREW_OBSIDIAN_CONFIG` and the crew repo root all point at it, so no real
vault or real memory directory is read. The module writes nothing, and one
test hashes every fixture file to prove it.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import crew_memory  # noqa: E402  pylint: disable=wrong-import-position

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(crew_memory.__file__)), "crew_memory.py")
FRONTMATTER = (
    "---\n"
    "name: Example fact\n"
    "description: One sentence that stays useful with no vault.\n"
    "metadata:\n"
    "  node_type: memory\n"
    "  type: project\n"
    "---\n"
    "\n"
)


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

    def vault(self, name, notes=("notes/fact.md",)):
        path = self.base / "vaults" / name
        path.mkdir(parents=True, exist_ok=True)
        for rel in notes:
            note = path.joinpath(*rel.split("/"))
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text("# note\n", encoding="utf-8", newline="\n")
        return path

    def obsidian(self, data):
        text = data if isinstance(data, str) else json.dumps(data)
        self.config.write_text(text, encoding="utf-8", newline="\n")

    def crew_vault_path(self, value):
        crew = self.root / ".crew"
        crew.mkdir(exist_ok=True)
        (crew / "config.json").write_text(
            json.dumps({"memory": {"vaultPath": value}}), encoding="utf-8", newline="\n")

    def memory(self, body, name="fact.md", frontmatter=FRONTMATTER, newline="\n"):
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


def run(argv, capsys):
    code = crew_memory.main(argv)
    out = capsys.readouterr().out
    return code, out


def resolve(host, path, capsys, *extra):
    return run(["resolve", "--file", str(path), "--root", str(host.root), *extra], capsys)


def state_of(out):
    for line in out.splitlines():
        if line.startswith("state: "):
            return line[len("state: "):]
    return None


def reason_of(out):
    for line in out.splitlines():
        if line.startswith("reason: "):
            return line[len("reason: "):]
    return None


def path_of(out):
    for line in out.splitlines():
        if line.startswith("path: "):
            return line[len("path: "):]
    return None


# --- grammar ---------------------------------------------------------------

@pytest.mark.parametrize("body,newline,note", [
    ("vault: work | note: notes/fact.md\n", "\n", "notes/fact.md"),
    ("vault: My vault.v2-x | note: notes/fact.md\n", "\n", "notes/fact.md"),
    ("vault: work | note: a/b/c/deep.md\n", "\n", "a/b/c/deep.md"),
    ("vault: work | note: notes/caf\u00e9 \u00fcber.md\n", "\n", "notes/caf\u00e9 \u00fcber.md"),
    ("vault: work | note: notes/fact.md\n\n\n  \n", "\n", "notes/fact.md"),
    ("vault: work | note: notes/fact.md\n", "\r\n", "notes/fact.md"),
], ids=["plain", "name-space-dot-dash", "nested", "non-ascii", "trailing-blank", "crlf"])
def test_pointer_grammar_accepts(host, capsys, body, newline, note):
    name = body.split("|")[0][len("vault: "):].strip()
    host.vault(name, notes=(note,))
    host.obsidian({"vaults": {name: {"path": str(host.base / "vaults" / name)}}})
    mem = host.memory(body, newline=newline)
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out
    expected = os.path.realpath(os.path.join(str(host.base / "vaults" / name), *note.split("/")))
    assert path_of(out) == expected


@pytest.mark.parametrize("body", [
    "vault: work | note: /x/y.md",
    "vault: work | note: C:/x/y.md",
    "vault: work | note: notes\\fact.md",
    "vault: work | note: notes/../fact.md",
    "vault: work | note: notes/./fact.md",
    "vault: work | note: a//b.md",
    "vault: work | note: notes/fact.txt",
    "vault:  | note: notes/fact.md",
    "vault: " + "w" * 65 + " | note: notes/fact.md",
    "vault: wo\x07rk | note: notes/fact.md",
    "vault: work | note: notes/fa\x01ct.md",
    "vault: work | note: notes/fact.md | extra: x.md",
    "vault: work | note: notes/ fact.md",
    "vault: work",
], ids=["abs-posix", "drive", "backslash", "dotdot", "dot", "empty-segment", "not-md",
        "empty-name", "long-name", "ctrl-name", "ctrl-path", "second-field",
        "segment-space", "no-note"])
def test_pointer_grammar_refuses(host, capsys, body):
    # A vault that WOULD hold the note, so only the grammar can stop it.
    host.vault("work", notes=("notes/fact.md", "x/y.md", "fact.md"))
    host.obsidian({"vaults": {"work": {"path": str(host.base / "vaults" / "work")}}})
    mem = host.memory(body + "\n")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (1, "malformed"), out
    assert reason_of(out)
    assert path_of(out) is None


@pytest.mark.parametrize("body,frontmatter", [
    ("A fact written out in prose.\nWith a second line.\n", FRONTMATTER),
    ("A fact in prose.\nvault: work | note: notes/fact.md\n", FRONTMATTER),
    ("", FRONTMATTER),
    ("Just prose, no frontmatter at all.\n", ""),
], ids=["prose", "pointer-on-line-two", "empty", "no-frontmatter"])
def test_full_text_bodies(host, capsys, body, frontmatter):
    host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(host.base / "vaults" / "work")}}})
    mem = host.memory(body, frontmatter=frontmatter)
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "full-text"), out
    assert path_of(out) is None


def test_frontmatter_is_split_on_dashes_not_parsed(host, capsys):
    """A frontmatter that is not valid YAML, and one holding a `vault:` key, do
    not change how the body classifies: the split is on the `---` lines only."""
    host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(host.base / "vaults" / "work")}}})
    odd = "---\nname: [unclosed\nvault: other | note: x.md\n---\n\n"
    mem = host.memory("vault: work | note: notes/fact.md\n", frontmatter=odd)
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out


# --- resolve ---------------------------------------------------------------

def test_resolve_prints_the_real_note_path(host, capsys):
    named = host.vault("work")
    legacy = host.vault("legacy")
    host.obsidian({"vaults": {"work": {"path": str(named), "role": "primary"}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    assert code == 0, out
    assert path_of(out) == os.path.realpath(str(named / "notes" / "fact.md"))

    # The name `memory`, from the crew config's memory.vaultPath.
    host.crew_vault_path(str(legacy))
    mem = host.memory("vault: memory | note: notes/fact.md\n", name="legacy.md")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out
    assert path_of(out) == os.path.realpath(str(legacy / "notes" / "fact.md"))


def test_memory_name_falls_back_to_the_legacy_top_level_vault_path(host, capsys):
    legacy = host.vault("legacy")
    host.obsidian({"vaultPath": str(legacy)})
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out
    assert path_of(out) == os.path.realpath(str(legacy / "notes" / "fact.md"))


def test_same_pointer_resolves_on_two_hosts(tmp_path, monkeypatch, capsys):
    body = "vault: work | note: notes/fact.md\n"
    seen = []
    for label in ("one", "two"):
        host = Host(tmp_path / label, monkeypatch)
        vault = host.vault("work")
        host.obsidian({"vaults": {"work": {"path": str(vault)}}})
        mem = host.memory(body)
        code, out = resolve(host, mem, capsys)
        assert (code, state_of(out)) == (0, "resolved"), out
        assert path_of(out) == os.path.realpath(str(vault / "notes" / "fact.md"))
        seen.append((path_of(out), mem.read_bytes()))
    assert seen[0][0] != seen[1][0]
    assert seen[0][1] == seen[1][1]


def _assert_degraded(code, out, state):
    assert (code, state_of(out)) == (1, state), out
    assert reason_of(out), out
    assert path_of(out) is None


def test_state_no_vault_config(host, capsys):
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "no-vault-config")
    mem = host.memory("vault: work | note: notes/fact.md\n", name="b.md")
    _assert_degraded(*resolve(host, mem, capsys), "no-vault-config")


def test_state_vault_unknown(host, capsys):
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory("vault: elsewhere | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unknown")
    # memory.vaultPath names the vault `memory` and nothing else.
    host.crew_vault_path(str(host.vault("legacy")))
    _assert_degraded(*resolve(host, mem, capsys), "vault-unknown")


def test_state_vault_ignored_is_unknown(host, capsys):
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work")), "role": "ignore"}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unknown")


def test_state_vault_unavailable(host, capsys):
    host.obsidian({"vaults": {"work": {"path": str(host.base / "not-mounted")}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unavailable")


def test_state_note_missing(host, capsys):
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory("vault: work | note: notes/other.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "note-missing")


def test_state_unreadable(host, capsys):
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.mem / "latin1.md"
    mem.write_bytes(b"---\nname: x\n---\n\ncaf\xe9\n")
    _assert_degraded(*resolve(host, mem, capsys), "unreadable")


def test_unparseable_config_is_not_no_vaults(host, capsys):
    legacy = host.vault("legacy")
    host.crew_vault_path(str(legacy))
    host.obsidian("{not json")
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")
    # A JSON value that is not an object is no better.
    host.obsidian("[1, 2]")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")


def test_unparseable_crew_config_is_not_no_vaults(host, capsys):
    """The `memory` fallback reads the crew config; a crew config that exists
    and does not parse is named, not taken for "memory.vaultPath unset"."""
    (host.root / ".crew").mkdir()
    (host.root / ".crew" / "config.json").write_text("{broken", encoding="utf-8")
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")


def test_unavailable_vault_is_not_substituted(host, capsys):
    other = host.vault("other")
    host.crew_vault_path(str(other))
    host.obsidian({"vaultPath": str(other), "vaults": {
        "memory": {"path": str(host.base / "unmounted"), "role": "primary"},
        "other": {"path": str(other), "role": "recall", "default": True},
    }})
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unavailable")


def _symlink(target, link):
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")


def test_symlinked_component_is_outside_vault(host, capsys):
    vault = host.vault("work")
    outside = host.base / "outside"
    (outside / "inner").mkdir(parents=True)
    (outside / "inner" / "fact.md").write_text("x\n", encoding="utf-8")
    _symlink(str(outside), str(vault / "linked"))
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: linked/inner/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "outside-vault")
    # A link that stays inside the vault is still a link, and still refused.
    _symlink(str(vault / "notes"), str(vault / "alias"))
    mem = host.memory("vault: work | note: alias/fact.md\n", name="b.md")
    _assert_degraded(*resolve(host, mem, capsys), "outside-vault")


def test_symlinked_vault_root_is_followed(host, capsys):
    """The configured vault path itself may be a link (a synced folder often
    is); only components BELOW it are refused."""
    vault = host.vault("work")
    _symlink(str(vault), str(host.base / "vault-link"))
    host.obsidian({"vaults": {"work": {"path": str(host.base / "vault-link")}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out


def test_resolve_json(host, capsys):
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys, "--json")
    data = json.loads(out)
    assert code == 0
    assert data["state"] == "resolved"
    assert data["vault"] == "work" and data["note"] == "notes/fact.md"
    assert data["path"] == os.path.realpath(str(vault / "notes" / "fact.md"))


# --- check -----------------------------------------------------------------

def test_check_lists_every_file_and_counts_states(host, capsys):
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    host.memory("- [Fact](fact.md) - summary\n", name="MEMORY.md", frontmatter="")
    host.memory("vault: work | note: notes/fact.md\n", name="b.md")
    host.memory("Prose body.\n", name="a.md")
    (host.mem / "notes.txt").write_text("not a memory\n", encoding="utf-8")
    argv = ["check", "--memory-dir", str(host.mem), "--root", str(host.root)]

    code, out = run(argv, capsys)
    assert code == 0, out
    rows = [line for line in out.splitlines() if line.startswith(("resolved", "full-text"))]
    assert [row.split()[1] for row in rows] == ["a.md", "b.md"]
    assert "MEMORY.md" not in out and "notes.txt" not in out
    assert "1 resolved" in out and "1 full-text" in out

    host.memory("vault: work | note: notes/gone.md\n", name="c.md")
    host.memory("vault: work | note: ../escape.md\n", name="0.md")
    code, out = run(argv, capsys)
    assert code == 1, out
    names = [line.split()[1] for line in out.splitlines()
             if line.split() and line.split()[0] in crew_memory.STATES]
    assert names == ["0.md", "a.md", "b.md", "c.md"]
    assert "1 note-missing" in out and "1 malformed" in out

    code, out = run(argv + ["--json"], capsys)
    assert code == 1
    data = json.loads(out)
    assert [(r["file"], r["state"]) for r in data["rows"]] == [
        ("0.md", "malformed"), ("a.md", "full-text"), ("b.md", "resolved"),
        ("c.md", "note-missing")]
    assert data["counts"] == {"resolved": 1, "full-text": 1, "malformed": 1,
                              "note-missing": 1}


def test_check_empty_dir_is_clean(host, capsys):
    code, out = run(["check", "--memory-dir", str(host.mem), "--root", str(host.root)], capsys)
    assert code == 0, out


# --- read-only, shells, usage ----------------------------------------------

def _tree_hash(*roots):
    digest = hashlib.sha256()
    for top in roots:
        for dirpath, dirnames, filenames in os.walk(str(top)):
            dirnames.sort()
            for name in sorted(filenames) + sorted(dirnames):
                full = os.path.join(dirpath, name)
                digest.update(full.encode("utf-8", "surrogateescape"))
                if os.path.isfile(full) and not os.path.islink(full):
                    with open(full, "rb") as handle:
                        digest.update(handle.read())
                    digest.update(str(os.stat(full).st_mtime_ns).encode())
    return digest.hexdigest()


def test_resolve_and_check_write_nothing(host, capsys):
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    host.crew_vault_path(str(vault))
    mem = host.memory("vault: work | note: notes/fact.md\n")
    host.memory("vault: work | note: notes/missing.md\n", name="b.md")
    host.memory("prose\n", name="c.md")
    before = _tree_hash(host.base)
    resolve(host, mem, capsys)
    resolve(host, mem, capsys, "--json")
    run(["check", "--memory-dir", str(host.mem), "--root", str(host.root)], capsys)
    run(["check", "--memory-dir", str(host.mem), "--root", str(host.root), "--json"], capsys)
    assert _tree_hash(host.base) == before


def _cli(host, argv):
    proc = subprocess.run([sys.executable, SCRIPT, *argv], capture_output=True, check=False,
                          env=host.env(), cwd=str(host.root), timeout=60)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def _ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


def _bash_argv(mem, host):
    bash = crew_fixtures.resolve_bash()
    if not bash:
        pytest.skip("no bash on this machine - the bash flavour is SKIPPED")
    return [bash, "-c", '"$0" "$1" resolve --file "$2" --root "$3"',
            sys.executable, SCRIPT, str(mem), str(host.root)]


def _pwsh_argv(mem, host):
    pwsh = crew_fixtures.resolve_pwsh()
    if not pwsh:
        pytest.skip("no pwsh 7 on this machine - the pwsh flavour is SKIPPED")
    exe, script, file, root = (_ps_quote(v) for v in
                               (sys.executable, SCRIPT, str(mem), str(host.root)))
    command = f"& {exe} {script} resolve --file {file} --root {root}; exit $LASTEXITCODE"
    return [pwsh, "-NoProfile", "-NonInteractive", "-Command", command]


@pytest.mark.parametrize("shell", ["bash", "pwsh"])
def test_cli_from_bash_and_pwsh(host, shell):
    """Each shell is its own case and skips on its own: one shell missing
    never lets the other's case pass for it."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n", name="a fact.md")
    argv = _bash_argv(mem, host) if shell == "bash" else _pwsh_argv(mem, host)
    proc = subprocess.run(argv, capture_output=True, check=False, env=host.env(), timeout=120)
    out = proc.stdout.decode("utf-8")
    assert proc.returncode == 0, out + proc.stderr.decode("utf-8")
    assert out.splitlines()[:2] == [
        "state: resolved", "path: " + os.path.realpath(str(vault / "notes" / "fact.md"))]


def test_cli_output_is_lf_only(host):
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    host.memory("vault: work | note: notes/fact.md\n")
    proc = subprocess.run(
        [sys.executable, SCRIPT, "check", "--memory-dir", str(host.mem), "--root", str(host.root)],
        capture_output=True, check=False, env=host.env(), timeout=60)
    assert proc.returncode == 0
    assert b"\r" not in proc.stdout


def test_usage_errors_exit_2(host):
    code, _out, err = _cli(host, [])
    assert code == 2 and err
    code, _out, err = _cli(host, ["resolve", "--file", str(host.mem / "absent.md")])
    assert code == 2 and "absent.md" in err
    code, _out, err = _cli(host, ["check", "--memory-dir", str(host.base / "no-such-dir")])
    assert code == 2 and "no-such-dir" in err
    code, _out, err = _cli(host, ["resolve"])
    assert code == 2 and err


def test_global_crew_config_is_isolated():
    """The autouse conftest fixture keeps the real global crew config out of
    reach; the `memory` fallback reads it through crew_config's attribute."""
    assert not os.path.exists(crew_config.GLOBAL_CONFIG_PATH)


# --- review round 1 (e5c17322) ---------------------------------------------

@pytest.mark.parametrize("config", [
    {"vaults": {"memory": "/somewhere"}},
    {"vaults": {"memory": None}},
    {"vaults": ["memory"]},
    {"vaults": "memory"},
], ids=["entry-string", "entry-null", "vaults-list", "vaults-string"])
def test_wrong_shape_vaults_is_config_unreadable(host, capsys, config):
    """B1: a `vaults` block or entry of the wrong shape is not "no entry": the
    crew config's memory.vaultPath must not answer for it."""
    host.crew_vault_path(str(host.vault("other")))
    host.obsidian(config)
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")


def _deny(monkeypatch, denied, contents_only=False):
    """Make the file calls raise EACCES for `denied` and everything under it,
    as a folder without read/search permission does (the suite runs as root
    here, where chmod would not deny anything). With `contents_only`, `denied`
    itself still stats - a folder with mode 0 does, from its parent - but it
    cannot be listed and nothing under it can be reached."""
    denied = os.path.abspath(str(denied))

    def blocked(path, listing=False):
        text = os.path.abspath(os.fspath(path))
        if text.startswith(denied + os.sep):
            return True
        return text == denied and (listing or not contents_only)

    def wrap(real, listing):
        def fake(*args, **kwargs):
            path = args[0] if args else kwargs.get("path", kwargs.get("file", "."))
            if not isinstance(path, int) and blocked(path, listing):
                raise PermissionError(13, "Permission denied", os.fspath(path))
            return real(*args, **kwargs)
        return fake
    for name, listing in (("stat", False), ("lstat", False), ("listdir", True),
                          ("scandir", True)):
        monkeypatch.setattr(os, name, wrap(getattr(os, name), listing))
    monkeypatch.setattr("builtins.open", wrap(open, True))


def test_unreadable_obsidian_config_folder_is_not_absent(host, capsys, monkeypatch):
    """F1: a config whose folder cannot be read is not "no config"; the
    `memory` name must not fall back to memory.vaultPath past it."""
    host.crew_vault_path(str(host.vault("other")))
    host.obsidian({"vaults": {"memory": {"path": str(host.base / "unmounted")}}})
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    _deny(monkeypatch, host.config)
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")


def test_unreadable_crew_config_is_not_unset(host, capsys, monkeypatch):
    """F1 for `.crew/`: memory.vaultPath behind a denied folder is not unset,
    so the legacy top-level vaultPath does not answer for it."""
    host.crew_vault_path(str(host.vault("crewvault")))
    host.obsidian({"vaultPath": str(host.vault("legacy"))})
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    _deny(monkeypatch, host.root / ".crew")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ")


@pytest.mark.parametrize("body", [
    "  vault: work | note: notes/fact.md\n",
    "Vault: work | note: notes/fact.md\n",
    "VAULT: work | note: notes/fact.md\n",
    "\tvault: work | note: notes/fact.md\n",
], ids=["indented", "capital", "upper", "tab"])
def test_near_pointer_is_malformed(host, capsys, body):
    """F2: a line that is a pointer but for case or indentation is malformed,
    never full text that exits 0."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body)
    _assert_degraded(*resolve(host, mem, capsys), "malformed")


def test_cr_only_line_breaks_are_line_breaks(host, capsys):
    """F2: a file with lone CR line breaks is read like an LF file, not as one
    line that classifies as full text."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n", newline="\r")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out
    bad = host.memory("vault: work | note: ../x.md\n", name="b.md", newline="\r")
    _assert_degraded(*resolve(host, bad, capsys), "malformed")


@pytest.mark.parametrize("note", ["notes/C:fact.md", "notes/fact.md:stream.md", "C:fact.md"],
                         ids=["drive-relative-inner", "ads", "drive-relative"])
def test_colon_in_any_segment_is_malformed(host, capsys, note):
    """F3: `:` is refused in every segment (drive-relative paths, NTFS
    alternate data streams), not only a leading `X:`."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(f"vault: work | note: {note}\n")
    _assert_degraded(*resolve(host, mem, capsys), "malformed")


def test_check_lists_a_dangling_symlink_as_unreadable(host, capsys):
    """F4: a dangling `*.md` link is a memory file nobody can read, not one
    to leave out of the list."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    host.memory("prose\n", name="a.md")
    try:
        os.symlink(str(host.base / "gone.md"), str(host.mem / "b.md"))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    code, out = run(["check", "--memory-dir", str(host.mem), "--root", str(host.root),
                     "--json"], capsys)
    data = json.loads(out)
    assert code == 1
    assert [(r["file"], r["state"]) for r in data["rows"]] == [
        ("a.md", "full-text"), ("b.md", "unreadable")]


def test_unreadable_vault_is_unavailable_not_note_missing(host, capsys, monkeypatch):
    """F5: a vault that cannot be read is vault-unavailable; note-missing is
    only for a vault that was read and has no such note."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    _deny(monkeypatch, vault, contents_only=True)
    _assert_degraded(*resolve(host, mem, capsys), "vault-unavailable")


def test_unreadable_notes_folder_is_unreadable_not_note_missing(host, capsys, monkeypatch):
    """F5: a folder inside the vault that cannot be read is `unreadable`."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    _deny(monkeypatch, vault / "notes", contents_only=True)
    _assert_degraded(*resolve(host, mem, capsys), "unreadable")


def test_legacy_vault_path_only_without_a_vaults_block(host, capsys):
    """F6: as obsidian_common.list_vaults / writer_vault read it, the legacy
    top-level vaultPath is the `memory` vault only when there is no `vaults`
    block at all."""
    host.obsidian({"vaultPath": str(host.vault("legacy")),
                   "vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unknown")


def test_relative_vault_path_reason_says_relative(host, capsys):
    """N1: a relative path is named as relative, not as "not a directory"."""
    host.obsidian({"vaults": {"work": {"path": "vaults/work"}}})
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "vault-unavailable")
    assert "absolute" in reason_of(out)


def test_unlistable_memory_dir_exits_2(host, capsys, monkeypatch):
    """N3: a memory folder that cannot be listed is a usage-level refusal with
    a message, not a traceback."""
    _deny(monkeypatch, host.mem, contents_only=True)
    code, _out = run(["check", "--memory-dir", str(host.mem), "--root", str(host.root)],
                     capsys)
    assert code == 2


@pytest.mark.parametrize("body", [
    "vault: work | note: notes/fa\u200bct.md",
    "vault: work | note: notes/\u202efact.md",
    "vault: wo\u200drk | note: notes/fact.md",
], ids=["zero-width-space", "rtl-override", "zwj-in-name"])
def test_format_characters_are_malformed(host, capsys, body):
    """N4: Unicode category Cf (invisible format characters) is refused like
    Cc: a pointer must say what it looks like it says."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body + "\n")
    _assert_degraded(*resolve(host, mem, capsys), "malformed")


def test_broken_crew_config_only_affects_the_memory_name(host, capsys):
    """N6: a broken crew config is no-vault-config for `memory`, the one name
    it could answer for; another unknown name is plain vault-unknown."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    (host.root / ".crew").mkdir()
    (host.root / ".crew" / "config.json").write_text("{broken", encoding="utf-8")
    mem = host.memory("vault: elsewhere | note: notes/fact.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "vault-unknown")
    mem = host.memory("vault: memory | note: notes/fact.md\n", name="b.md")
    _assert_degraded(*resolve(host, mem, capsys), "no-vault-config")


def test_bom_memory_and_bom_config(host, capsys):
    """N8: a UTF-8 BOM on the memory file or the config changes nothing."""
    vault = host.vault("work")
    host.config.write_bytes(b"\xef\xbb\xbf" + json.dumps(
        {"vaults": {"work": {"path": str(vault)}}}).encode("utf-8"))
    mem = host.mem / "bom.md"
    mem.write_bytes(b"\xef\xbb\xbf" + (FRONTMATTER + "vault: work | note: notes/fact.md\n")
                    .encode("utf-8"))
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out


def test_memory_md_is_skipped_exactly_and_md_suffix_any_case(host, capsys):
    """N2: only `MEMORY.md` itself is the index; `memory.md` is a memory file,
    and a `.MD` suffix is still a memory file."""
    host.memory("- index\n", name="MEMORY.md", frontmatter="")
    host.memory("prose\n", name="memory.md")
    host.memory("prose\n", name="upper.MD")
    code, out = run(["check", "--memory-dir", str(host.mem), "--root", str(host.root),
                     "--json"], capsys)
    data = json.loads(out)
    assert code == 0
    assert sorted(r["file"] for r in data["rows"]) == ["memory.md", "upper.MD"]


# --- review round 2 (da00137e): three structural rules ---------------------
# Real files throughout. Mocked, because the suite runs as root and root opens
# a mode-000 file: only `test_note_with_mode_000_is_unreadable`, and only when
# euid is 0 (it chmods the real file too, so a non-root run is real).

def _dangling(link):
    try:
        os.symlink(str(link.parent / "no-such-target.json"), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")


def test_dangling_obsidian_config_link_is_unreadable(host, capsys):
    """Rule 1: absent means lstat says FileNotFoundError. A dangling link is
    there, and does not parse, so `memory` must not fall back past it."""
    host.crew_vault_path(str(host.vault("other")))
    _dangling(host.config)
    for name in ("memory", "work"):
        mem = host.memory(f"vault: {name} | note: notes/fact.md\n", name=f"{name}.md")
        code, out = resolve(host, mem, capsys)
        _assert_degraded(code, out, "no-vault-config")
        assert reason_of(out).startswith("config unreadable: "), out


def test_dangling_crew_config_link_is_unreadable(host, capsys):
    host.obsidian({"vaultPath": str(host.vault("legacy"))})
    (host.root / ".crew").mkdir()
    _dangling(host.root / ".crew" / "config.json")
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: "), out


@pytest.mark.parametrize("config,field", [
    ({"vaults": {"work": "PATH", "junk": 5}}, "vaults.junk"),
    ({"vaults": {"work": {"path": 5}}}, "vaults.work.path"),
    ({"vaults": {"work": {"role": "primary"}}}, "vaults.work.path"),
    ({"vaults": {"work": "PATH"}, "vaultPath": 5}, "vaultPath"),
    ({"vaults": {"work": "PATH"}, "vaultPath": None}, "vaultPath"),
], ids=["other-entry-not-object", "path-not-string", "path-missing", "legacy-not-string",
        "legacy-null"])
def test_obsidian_config_schema_names_the_field(host, capsys, config, field):
    """Rule 2: the whole Obsidian config is checked before any resolution, so
    a wrong field anywhere is `config unreadable`, naming the field - even one
    that does not belong to the vault asked for."""
    vault = str(host.vault("work"))
    text = json.dumps(config).replace('"PATH"', json.dumps({"path": vault}))
    host.obsidian(text)
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ") and field in reason_of(out), out


@pytest.mark.parametrize("crew,field", [
    ({"memory": "x"}, "memory"),
    ({"memory": {"vaultPath": 5}}, "memory.vaultPath"),
    ({"memory": {"vaultPath": ["a"]}}, "memory.vaultPath"),
], ids=["memory-not-object", "vaultpath-number", "vaultpath-list"])
@pytest.mark.parametrize("layer", ["repo", "global"])
def test_crew_config_schema_names_the_field(host, capsys, monkeypatch, crew, field, layer):
    """Rule 2 for the crew config, both layers: a wrong-typed memory.vaultPath
    is not "unset", so the legacy vaultPath must not answer for `memory`."""
    host.obsidian({"vaultPath": str(host.vault("legacy"))})
    if layer == "repo":
        (host.root / ".crew").mkdir()
        (host.root / ".crew" / "config.json").write_text(json.dumps(crew), encoding="utf-8")
    else:
        path = host.home / "global-crew.json"
        path.write_text(json.dumps(crew), encoding="utf-8")
        monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ") and field in reason_of(out), out


@pytest.mark.parametrize("value", [None, ""], ids=["null", "empty"])
def test_crew_vault_path_null_or_empty_is_unset(host, capsys, value):
    """Must-allow: null and "" are the schema's two spellings of unset."""
    legacy = host.vault("legacy")
    host.obsidian({"vaultPath": str(legacy)})
    host.crew_vault_path(value)
    mem = host.memory("vault: memory | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "resolved"), out


def test_reason_text_is_right_per_name(host, capsys):
    """N5: memory.vaultPath can only ever name `memory`, so a reason for any
    other name does not offer it as the missing piece."""
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert "memory.vaultPath" not in reason_of(out) and "no Obsidian config" in reason_of(out)
    host.crew_vault_path(str(host.vault("legacy")))
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "vault-unknown")
    assert "no Obsidian config" in reason_of(out), out
    mem = host.memory("vault: memory | note: notes/fact.md\n", name="m.md")
    host.crew_vault_path(None)
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert "memory.vaultPath" in reason_of(out), out


def test_note_with_mode_000_is_unreadable(host, capsys, monkeypatch):
    """Rule 3: a resolved note must open. MOCKED when euid is 0 (root opens a
    mode-000 file); the file is chmod-ed 000 for real either way."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    note = vault / "notes" / "fact.md"
    os.chmod(str(note), 0)
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            real_open = os.open
            target = os.path.realpath(str(note))

            def fake_open(path, flags, *args, **kwargs):
                if os.path.realpath(os.fspath(path)) == target:
                    raise PermissionError(13, "Permission denied", os.fspath(path))
                return real_open(path, flags, *args, **kwargs)
            monkeypatch.setattr(os, "open", fake_open)
            real_builtin = open

            def fake_builtin(path, *args, **kwargs):
                if not isinstance(path, int) and os.path.realpath(os.fspath(path)) == target:
                    raise PermissionError(13, "Permission denied", os.fspath(path))
                return real_builtin(path, *args, **kwargs)
            monkeypatch.setattr("builtins.open", fake_builtin)
        mem = host.memory("vault: work | note: notes/fact.md\n")
        _assert_degraded(*resolve(host, mem, capsys), "unreadable")
    finally:
        os.chmod(str(note), 0o644)


def test_check_never_opens_a_fifo_device_or_directory(host):
    """Rule 3 / N4: `check` stats through links and opens only regular files.
    A link to a FIFO, a FIFO and a directory named *.md are listed
    `unreadable`. Run in a subprocess with a timeout, so a regression that
    opens the FIFO fails this test instead of hanging the suite."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    host.memory("prose\n", name="a.md")
    fifo = host.base / "pipe"
    os.mkfifo(str(fifo))
    os.mkfifo(str(host.mem / "c-fifo.md"))
    os.symlink(str(fifo), str(host.mem / "b-link.md"))
    (host.mem / "d-dir.md").mkdir()
    try:
        proc = subprocess.run(
            [sys.executable, SCRIPT, "check", "--memory-dir", str(host.mem),
             "--root", str(host.root), "--json"],
            capture_output=True, check=False, env=host.env(), timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("check hung on a FIFO: it opened a file that is not regular")
    data = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 1
    assert [(r["file"], r["state"]) for r in data["rows"]] == [
        ("a.md", "full-text"), ("b-link.md", "unreadable"), ("c-fifo.md", "unreadable"),
        ("d-dir.md", "unreadable")]


@pytest.mark.parametrize("body", [
    "vault : work | note: notes/fact.md",
    "vault\t: work | note: notes/fact.md",
    "\u200bvault: work | note: notes/fact.md",
    "\ufeff  Vault: work | note: notes/fact.md",
    "vault: work | note: notes/fa\rct.md",
    "vault: work | note: notes/fact.md\nand a line of prose",
    "vault: work | note: notes/fa\u2028ct.md",
    "vault: work | note: notes/fa\u2029ct.md",
], ids=["space-before-colon", "tab-before-colon", "leading-zwsp", "bom-indent-capital",
        "cr-inside", "pointer-then-prose", "line-separator", "paragraph-separator"])
def test_pointer_like_first_line_must_match_in_full(host, capsys, body):
    """N1-N3: the first non-blank line, Cf removed and stripped, that starts
    `vault` then optional whitespace then `:` is a pointer attempt: anything
    short of the full grammar, alone in the body, is `malformed`."""
    host.vault("work", notes=("notes/fact.md", "notes/fa\u2028ct.md", "notes/fa\u2029ct.md"))
    host.obsidian({"vaults": {"work": {"path": str(host.base / "vaults" / "work")}}})
    mem = host.memory(body + "\n")
    _assert_degraded(*resolve(host, mem, capsys), "malformed")


def test_check_stats_before_it_opens(host, capsys, monkeypatch):
    """Rule 3, the stat layer alone: `check` never hands a FIFO or directory
    to the opener. A spy stands in for the opener, so a regression records
    the path instead of blocking."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    os.mkfifo(str(host.mem / "fifo.md"))
    (host.mem / "dir.md").mkdir()
    host.memory("prose\n", name="a.md")
    opened = []
    real = crew_memory._open_regular  # pylint: disable=protected-access

    def spy(path):
        opened.append(os.path.basename(path))
        if os.path.basename(path) != "a.md":
            raise OSError("the spy refused a non-regular file")
        return real(path)
    monkeypatch.setattr(crew_memory, "_open_regular", spy)
    run(["check", "--memory-dir", str(host.mem), "--root", str(host.root)], capsys)
    assert opened == ["a.md"]


def test_open_regular_refuses_a_fifo_without_blocking(tmp_path):
    """Rule 3, the open layer alone: a FIFO that replaced a regular file after
    the stat is refused, never blocked on. Subprocess plus timeout, so a
    blocking open fails the test instead of hanging the suite."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    fifo = tmp_path / "pipe.md"
    os.mkfifo(str(fifo))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import crew_memory\n"
            "try:\n    crew_memory._open_regular(sys.argv[2])\nexcept OSError:\n"
            "    sys.exit(3)\nsys.exit(0)\n")
    try:
        proc = subprocess.run([sys.executable, "-c", code, os.path.dirname(SCRIPT), str(fifo)],
                              capture_output=True, check=False, timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("_open_regular blocked on a FIFO")
    assert proc.returncode == 3, proc.stderr.decode("utf-8")


# --- review round 3 (22271e7d) ---------------------------------------------

@pytest.mark.parametrize("body", [
    "Vault: keep client notes in the work vault, not personal.\n",
    "Vault: keep client notes in the work vault, not personal.\nA second line of prose.\n",
], ids=["vault-prose", "vault-prose-two-lines"])
def test_prose_starting_vault_is_full_text(host, capsys, body):
    """FIX1, must-allow: a real memory that happens to start `Vault:` is not a
    pointer attempt unless the line also carries `note:` or `|`."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body)
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "full-text"), out


@pytest.mark.parametrize("body", [
    "Vault : work | note: notes/x.md",
    "VAULT: work note : notes/x.md",
    "vault: work | notes/x.md",
], ids=["capital-v-space-before-colon", "upper-note-colon-no-bar", "bar-no-note"])
def test_near_pointer_with_note_or_bar_is_malformed(host, capsys, body):
    """FIX1, must-block: a `vault:` line that also has `note:` or `|` is a
    pointer attempt, and anything short of the grammar is malformed."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body + "\n")
    _assert_degraded(*resolve(host, mem, capsys), "malformed")


def test_duplicate_config_keys_are_unreadable(host, capsys):
    """N1: a key given twice is ambiguous (json keeps the last silently)."""
    good, other = str(host.vault("work")), str(host.vault("other"))
    host.obsidian('{"vaults": {"work": {"path": %s}, "work": {"path": %s}}}'
                  % (json.dumps(other), json.dumps(good)))
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: ") and "duplicate" in reason_of(out)


@pytest.mark.parametrize("kind", ["deep", "oversized"])
def test_hostile_config_is_unreadable_and_check_survives(host, capsys, kind):
    """N2: a config nested past the recursion limit, or larger than the read
    cap, is `config unreadable` - for resolve, and for check in a subprocess."""
    if kind == "deep":
        host.obsidian("[" * 100000)
    else:
        pad = " " * (crew_memory.CONFIG_CAP + 10)
        host.obsidian('{"vaults": {"work": {"path": %s}}}%s'
                      % (json.dumps(str(host.vault("work"))), pad))
    mem = host.memory("vault: work | note: notes/fact.md\n")
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "no-vault-config")
    assert reason_of(out).startswith("config unreadable: "), out
    proc = subprocess.run(
        [sys.executable, SCRIPT, "check", "--memory-dir", str(host.mem), "--root",
         str(host.root), "--json"],
        capture_output=True, check=False, env=host.env(), timeout=60)
    assert proc.returncode == 1, proc.stderr.decode("utf-8")
    rows = json.loads(proc.stdout.decode("utf-8"))["rows"]
    assert [r["state"] for r in rows] == ["no-vault-config"]


def test_non_regular_note_is_unreadable(host, capsys):
    """N4: a directory or FIFO where the note should be is there but cannot be
    read as a note: `unreadable`, never `note-missing` (which a writer may
    take as leave to create it)."""
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    (vault / "dir.md").mkdir()
    mem = host.memory("vault: work | note: dir.md\n")
    _assert_degraded(*resolve(host, mem, capsys), "unreadable")
    if hasattr(os, "mkfifo"):
        os.mkfifo(str(vault / "pipe.md"))
        mem = host.memory("vault: work | note: pipe.md\n", name="b.md")
        _assert_degraded(*resolve(host, mem, capsys), "unreadable")


# --- review round 4 (31c1e061) ---------------------------------------------

@pytest.mark.parametrize("body,newline", [
    ("vault: work\r| note: notes/fact.md\n", "\n"),
    ("vault: work\n| note: notes/fact.md\n", "\n"),
    ("vault: work\n| note: notes/fact.md\n", "\r\n"),
    ("vault: work\n", "\n"),
    ("Vault:  work\n", "\n"),
    ("vault: work (main)\nnote: notes/fact.md\n", "\n"),
], ids=["cr-before-bar", "lf-wrapped", "crlf-wrapped", "bare-name", "bare-name-capital",
        "mark-only-on-line-two"])
def test_broken_or_bare_pointer_is_malformed(host, capsys, body, newline):
    """FIX1: a first line `vault:` + a bare vault name, or a `vault:` first
    line with the `note:`/`|` mark anywhere in the body (a pointer broken
    before its `|`), is a pointer attempt - malformed, never full text."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body, newline=newline)
    code, out = resolve(host, mem, capsys)
    _assert_degraded(code, out, "malformed")
    assert "if this is prose, reword the first line" in reason_of(out), out


# --- review round 5 (9350f997) ---------------------------------------------

@pytest.mark.parametrize("body", [
    "Vault: the team one, synced via Obsidian Sync.\nIt holds the shared notes.\n\n"
    "| folder | use |\n|---|---|\n| inbox | triage |\n",
    "Vault: the team one, synced via Obsidian Sync.\nIt holds the shared notes.\n"
    "Note: never put secrets there.\n",
    "Vault: the team one, synced via Obsidian Sync. See the footnote: below.\n",
    "Vault: the team one, synced via Obsidian Sync.\nIts index has a note: and a | inside.\n",
], ids=["later-table", "later-note-line", "footnote-word", "line-two-mark-not-leading"])
def test_long_prose_starting_vault_is_full_text(host, capsys, body):
    """Round 5 FIX, must-allow: the mark counts only on line 1, or on line 2
    when that line starts with `|` or `note:` - a later table or `Note:` line,
    or `footnote:` (no word boundary), does not make prose a pointer."""
    host.obsidian({"vaults": {"work": {"path": str(host.vault("work"))}}})
    mem = host.memory(body)
    code, out = resolve(host, mem, capsys)
    assert (code, state_of(out)) == (0, "full-text"), out
