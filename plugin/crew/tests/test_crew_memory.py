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
    # A directory where the note should be is not a note.
    (host.base / "vaults" / "work" / "dir.md").mkdir()
    mem = host.memory("vault: work | note: dir.md\n")
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


def test_cli_from_bash_and_pwsh(host):
    vault = host.vault("work")
    host.obsidian({"vaults": {"work": {"path": str(vault)}}})
    mem = host.memory("vault: work | note: notes/fact.md\n", name="a fact.md")
    lines = {}
    bash = crew_fixtures.resolve_bash()
    if bash:
        proc = subprocess.run(
            [bash, "-c", '"$0" "$1" resolve --file "$2" --root "$3"',
             sys.executable, SCRIPT, str(mem), str(host.root)],
            capture_output=True, check=False, env=host.env(), timeout=60)
        out = proc.stdout.decode("utf-8")
        assert proc.returncode == 0, out + proc.stderr.decode("utf-8")
        lines["bash"] = out.splitlines()[0]
    else:
        print("crew tests: no bash - the bash flavour is SKIPPED")
    pwsh = crew_fixtures.resolve_pwsh()
    if pwsh:
        exe, script, file, root = (_ps_quote(v) for v in
                                   (sys.executable, SCRIPT, str(mem), str(host.root)))
        command = f"& {exe} {script} resolve --file {file} --root {root}; exit $LASTEXITCODE"
        proc = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
                              capture_output=True, check=False, env=host.env(), timeout=120)
        out = proc.stdout.decode("utf-8")
        assert proc.returncode == 0, out + proc.stderr.decode("utf-8")
        lines["pwsh"] = out.splitlines()[0]
    else:
        print("crew tests: no pwsh - the pwsh flavour is SKIPPED")
    if not lines:
        pytest.skip("neither bash nor pwsh is available here")
    assert set(lines.values()) == {"state: resolved"}, lines


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
