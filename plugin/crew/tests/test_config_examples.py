"""R-C3: the configuration guide and its worked examples.

`plugin/crew/docs/configuration/guide.md` is hand-written, and
`plugin/crew/docs/configuration/examples/*.json` are hand-written example
files: `repo-*.json` is a repo `.crew/config.json`, `machine-*.json` a machine
`~/.claude/crew/config.json` (spec decision 4). This suite holds them to the
plan's acceptance (docs/plans/crew-revamp-2026-11-18.md, row R-C3): repo
examples pass `--check`, machine examples pass `--check-global`, and the guide
names only commands that exist.

`--check` and `--check-global` alone miss typos, bad values and layer mistakes
(both always exit 0, and neither reads most keys), so an example passes only
when it meets every one of (spec decision 5):

(a) it parses as a JSON object;
(b) repo: `--check` prints exactly `no warnings`; machine: `--check-global
    --json` has no finding kind outside `CHECK_GLOBAL_INFO`, and the file
    exists and is readable;
(c) `--inert --json` is `[]` with the example in its layer, the other empty;
(d) every leaf maps to a `keys.json` key, and that key's layer class allows
    the value in this layer (`LAYER_CLASS`); confirm-only keys hold `"off"`;
(e) where `keys.json` declares `values`, the leaf (or each list element) is
    one of them;
(f) a `tiers` map has no layer problem and each target resolves to the tier
    the file states.

The guide checks (decisions 6-9) are `guide_problems`. Both checkers take the
registry and the lists as arguments, so the must-block rows below pass a
mutated copy and never touch a committed file.

Isolation: HOME, USERPROFILE and CLAUDE_CONFIG_DIR point under `tmp_path` for
every subprocess, every CLI call gets an explicit `--global-path`, and a guard
fails the test if this process opens or lists the real `~/.claude/crew/`
(the pattern of `test_config_blanks.py`).
"""
import builtins
import copy
import io
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_gitallow
import crew_humanonly
import crew_keys
import crew_tiers

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(PLUGIN))
CONF_DIR = os.path.join(PLUGIN, "docs", "configuration")
EXAMPLES = os.path.join(CONF_DIR, "examples")
GUIDE = os.path.join(CONF_DIR, "guide.md")
KEYS_JSON = os.path.join(CONF_DIR, "keys.json")
SCRIPTS = os.path.join(PLUGIN, "hooks", "scripts")
COMMANDS = os.path.join(PLUGIN, "commands")
CREW_CONFIG_PY = os.path.join(SCRIPTS, "crew_config.py")
CONFIRM_PY = os.path.join(SCRIPTS, "crew_confirm_config.py")
REAL_CREW_DIR = os.path.normcase(os.path.realpath(os.path.join(
    os.path.expanduser("~"), ".claude", "crew")))

# The keys `crew_confirm_config.py propose` accepts: the expression it refuses
# against (crew_confirm_config.py, `propose`). Derived, never listed.
CONFIRM_ONLY = tuple(crew_humanonly.PATHS) + (crew_gitallow.KEY,)

# `--check-global` kinds that a partial machine file always gets and that say
# nothing wrong with it. Fail-closed: a new kind fails the machine examples
# until it is judged and added here.
CHECK_GLOBAL_INFO = frozenset({"missing-keys", "authority"})

# Key families the plan adds that have no key yet (plan line 596). A backticked
# token under one of these roots is checked even before the family lands.
PLANNED_FAMILIES = ("mode", "decider", "serious", "accounts", "applications", "admin")

# The only way the guide may name a key that has not landed: key -> ticket, and
# the guide line naming it must name the ticket too. The ticket that adds the
# key deletes its entry here in the same PR (`test_not_yet_has_not_landed`).
NOT_YET = {
    "mode": "R-M1",              # plan line 667; docs/tickets/pending/R-M1.md
    "accounts": "R-A1",          # plan line 709 (account registry)
    "production.hours": "R-40",  # plan lines 330 and 727
}

ANY, REFUSED, ONLY_FALSE, DECLARED, ONLY_TRUE = (
    "any", "refused", "only-false", "declared", "only-true")

# One row per `layer` string in keys.json: what a repo example and a machine
# example may hold. Hand-written, because each class's rule lives in different
# runtime code; `test_every_layer_string_has_a_row` keeps it complete.
LAYER_CLASS = {
    "repo": {"repo": ANY, "machine": REFUSED},
    "machine-only": {"repo": REFUSED, "machine": ANY},
    "both": {"repo": ANY, "machine": ANY},
    "both, ratchet": {"repo": ANY, "machine": ANY},
    "both, stricter wins": {"repo": ANY, "machine": ANY},
    "both, widening warned": {"repo": ANY, "machine": ANY},
    # The repo may only veto (crew_config.REPO_VETO_ONLY).
    "machine-arms": {"repo": ONLY_FALSE, "machine": DECLARED},
    # `false` counts only with the receipt two /crew:confirm-config prompts
    # leave, which a copied example never has, so only the veto is taught.
    "human-only opt-out": {"repo": ONLY_TRUE, "machine": ONLY_TRUE},
}

KEY_TOKEN = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")
PATH_SUFFIXES = (".md", ".json", ".py", ".sh", ".ps1")
FLAG = re.compile(r"(?<![\w-])--[A-Za-z][\w-]*")
COMMAND = re.compile(r"/crew:([A-Za-z0-9][\w-]*)")
SCRIPT = re.compile(r"[\w${}./-]*[\w-]+\.py\b")
EXAMPLE_REF = re.compile(r"examples/([\w.-]+\.json)")


def load_keys():
    with open(KEYS_JSON, encoding="utf-8") as fh:
        return json.load(fh)["keys"]


def read_guide():
    with open(GUIDE, encoding="utf-8") as fh:
        return fh.read()


def example_paths():
    return sorted(os.path.join(EXAMPLES, n) for n in os.listdir(EXAMPLES)
                  if n.endswith(".json"))


def example_layer(path):
    """`repo`, `machine`, or None for a name with no layer prefix (decision 4)."""
    name = os.path.basename(path)
    for layer in ("repo", "machine"):
        if name.startswith(layer + "-") and name.endswith(".json"):
            return layer
    return None


# --- isolation ---------------------------------------------------------------

def _under_real_crew(path):
    try:
        text = os.fspath(path)
    except TypeError:
        return False
    if isinstance(text, bytes) or not text:
        return False
    full = os.path.normcase(os.path.realpath(os.path.abspath(text)))
    return full == REAL_CREW_DIR or full.startswith(REAL_CREW_DIR + os.sep)


@pytest.fixture(scope="module")
def _isolated(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    touched = []
    real_open, real_listdir = builtins.open, os.listdir

    def guarded_open(file, *args, **kwargs):
        if _under_real_crew(file):
            touched.append(str(file))
        return real_open(file, *args, **kwargs)

    def guarded_listdir(path="."):
        if _under_real_crew(path):
            touched.append(str(path))
        return real_listdir(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HOME", str(home))
        patch.setenv("USERPROFILE", str(home))
        patch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
        patch.setattr(builtins, "open", guarded_open)
        patch.setattr(io, "open", guarded_open)
        patch.setattr(os, "listdir", guarded_listdir)
        yield touched


@pytest.fixture(autouse=True)
def _no_real_crew_dir(_isolated):
    before = len(_isolated)
    yield
    assert _isolated[before:] == [], f"opened the real crew directory: {_isolated[before:]}"


def _env(home):
    home = str(home)
    return dict(os.environ, HOME=home, USERPROFILE=home,
                CLAUDE_CONFIG_DIR=os.path.join(home, ".claude"))


def _run(script, args, home):
    proc = subprocess.run([sys.executable, script, *args], capture_output=True,
                          text=True, env=_env(home), check=False, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


# --- (b) and (c): the CLI ----------------------------------------------------

def _layout(data, layer, tmp):
    """`(root, global_path)` with `data` written as `layer`'s file, the other
    layer absent."""
    root = os.path.join(tmp, "r")
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    global_path = os.path.join(tmp, "machine.json")
    target = os.path.join(root, ".crew", "config.json") if layer == "repo" else global_path
    text = json.dumps(data, indent=2)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text)
    return root, global_path


def cli_problems(data, layer, tmp):
    root, global_path = _layout(data, layer, tmp)
    base = ["--root", root, "--global-path", global_path]
    out = []
    if layer == "repo":
        code, stdout, stderr = _run(CREW_CONFIG_PY, base + ["--check"], tmp)
        if code != 0 or stdout.strip() != "no warnings":
            out.append(f"(b) --check: exit {code}: {stdout.strip()} {stderr.strip()}".strip())
    else:
        code, stdout, stderr = _run(CREW_CONFIG_PY, base + ["--check-global", "--json"], tmp)
        try:
            report = json.loads(stdout)
        except ValueError:
            out.append(f"(b) --check-global: not JSON: exit {code}: {stdout} {stderr}")
        else:
            if not (report.get("exists") and report.get("readable")):
                out.append(f"(b) --check-global: exists/readable is not true: {report}")
            for finding in report.get("findings", []):
                if finding.get("kind") not in CHECK_GLOBAL_INFO:
                    out.append(f"(b) --check-global: [{finding.get('kind')}] "
                               f"{finding.get('detail')}")
    code, stdout, stderr = _run(CREW_CONFIG_PY, base + ["--inert", "--json"], tmp)
    try:
        inert = json.loads(stdout)
    except ValueError:
        out.append(f"(c) --inert: not JSON: exit {code}: {stdout} {stderr}")
    else:
        for entry in inert:
            out.append(f"(c) --inert: {entry.get('key')}: {entry.get('kind')} "
                       f"{entry.get('effect', '')}".rstrip())
    return out


# --- (d) and (e): the registry -----------------------------------------------

def _same(a, b):
    """JSON equality that keeps `true` and `1` apart."""
    return type(a) is type(b) and a == b


def _leaves(data, by_key, open_tables, prefix=""):
    """`(dotted path, value, key or None)` per leaf. A value under an open
    table maps to that table; a non-empty object anywhere else is walked into,
    so an object can sit only where `keys.json` declares an open table."""
    for name, value in data.items():
        path = f"{prefix}{name}"
        table = next((t for t in open_tables if path == t or path.startswith(t + ".")), None)
        if table is not None:
            yield path, value, table
        elif isinstance(value, dict) and value:
            yield from _leaves(value, by_key, open_tables, path + ".")
        else:
            yield path, value, path if path in by_key else None


def registry_problems(data, layer, keys, confirm_only=CONFIRM_ONLY):
    by_key = {k["key"]: k for k in keys}
    open_tables = {k["key"] for k in keys if k["kind"] == "open-table"}
    out = []
    for path, value, key in _leaves(data, by_key, open_tables):
        if key is None:
            out.append(f"(d) {path}: maps to no keys.json key")
            continue
        meta = by_key[key]
        row = LAYER_CLASS.get(meta["layer"])
        if row is None:
            out.append(f"(d) {path}: layer class {meta['layer']!r} has no rule "
                       "in LAYER_CLASS")
            continue
        rule = row[layer]
        if rule == REFUSED:
            out.append(f"(d) {path}: layer {meta['layer']!r} may not be set in a {layer} file")
        elif rule == ONLY_FALSE and value is not False:
            out.append(f"(d) {path}: a {layer} file may only veto it with false")
        elif rule == ONLY_TRUE and value is not True:
            out.append(f"(d) {path}: an example may only hold the veto true "
                       "(an opt-out needs the owner's receipt)")
        elif (key in confirm_only and meta["layer"] != "human-only opt-out"
              and not _same(value, "off")):
            out.append(f"(d) {path}: confirm-only; an example may hold only \"off\"")
        values = meta.get("values")
        if values is not None and path == key:
            items = value if isinstance(value, list) else [value]
            for item in items:
                if not any(_same(item, allowed) for allowed in values):
                    out.append(f"(e) {path}: {json.dumps(item)} is not one of "
                               f"{json.dumps(values)}")
    return out


# --- (f): tiers --------------------------------------------------------------

def tiers_problems(data, layer, tmp):
    if "tiers" not in data:
        return []
    root, global_path = _layout(data, layer, tmp)
    machine, repo = crew_tiers.read_layers(root if layer == "repo" else None, global_path)
    out = [f"(f) {p}" for p in crew_tiers.layer_problems(machine, repo)]
    tiers = data["tiers"]
    if not isinstance(tiers, dict):
        return out + ["(f) tiers is not an object"]
    for target, entry in tiers.items():
        stated = entry.get("tier") if isinstance(entry, dict) else None
        result = crew_tiers.resolve_layers(machine, repo, target)
        got = result["machine"] if layer == "machine" else result["repo"]
        if got != stated or result["reason"] in ("invalid", "repo-invalid-entry", "conflicting"):
            out.append(f"(f) {target}: resolves to {result['tier']} ({result['reason']}), "
                       f"the file states {stated!r}")
    return out


def example_problems(path, layer, tmp, keys, confirm_only=CONFIRM_ONLY):
    """Every problem with the example file at `path` read as `layer`."""
    if layer is None:
        return [f"{os.path.basename(path)}: not named repo-*.json or machine-*.json"]
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError as exc:
        return [f"(a) not JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"(a) not a JSON object: {type(data).__name__}"]
    os.makedirs(tmp, exist_ok=True)
    return (cli_problems(data, layer, os.path.join(tmp, "cli"))
            + registry_problems(data, layer, keys, confirm_only)
            + tiers_problems(data, layer, os.path.join(tmp, "tiers")))


# --- the guide (decisions 6-9) -----------------------------------------------

def _sections(text):
    """`[(heading, body)]` split at `## ` headings; the text before the first is
    heading ``."""
    out, heading, body = [], "", []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append((heading, "\n".join(body)))
            heading, body = line[3:].strip(), []
        else:
            body.append(line)
    out.append((heading, "\n".join(body)))
    return out


def _key_tokens(line):
    for span in re.findall(r"`([^`\n]+)`", line):
        token = re.split(r"[=: ]", span, maxsplit=1)[0]
        if "/" in token or token.endswith(PATH_SUFFIXES):
            continue
        if KEY_TOKEN.fullmatch(token):
            yield token


def _names(token, line):
    return re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", line) is not None


def _script_problem(name, line):
    if name.startswith("${CLAUDE_PLUGIN_ROOT}/"):
        rel = name[len("${CLAUDE_PLUGIN_ROOT}/"):]
        return None if os.path.isfile(os.path.join(PLUGIN, rel)) else f"no such script {name}"
    if "/" not in name:
        return None if os.path.isfile(os.path.join(SCRIPTS, name)) else f"no such script {name}"
    if os.path.isfile(os.path.join(PLUGIN, name)):
        return None
    if os.path.isfile(os.path.join(REPO, name)):
        return None if "repo-only" in line else (
            f"{name} is not in an installed copy; say `repo-only` on its line")
    return f"no such script {name}"


def guide_problems(text, keys, not_yet, confirm_only, *, help_flags,
                   planned=PLANNED_FAMILIES, families=crew_keys.FAMILIES,
                   example_names=None):
    """Every problem with the guide `text`. `help_flags` maps a script name to
    the flags its help prints; `example_names` is the set on disk (None skips
    decision 8)."""
    names = {k["key"] for k in keys}
    open_tables = {k["key"] for k in keys if k["kind"] == "open-table"}
    checked_roots = {n.split(".")[0] for n in names} | set(planned)
    out = []
    named = set()
    for number, line in enumerate(text.splitlines(), 1):
        for cmd in COMMAND.findall(line):
            if not os.path.isfile(os.path.join(COMMANDS, cmd + ".md")):
                out.append(f"line {number}: /crew:{cmd} is not a command")
        scripts = [s for s in ("crew_confirm_config.py", "crew_config.py") if _names(s, line)]
        if scripts:
            allowed = set().union(*(help_flags[s] for s in scripts))
            for flag in FLAG.findall(line):
                if flag not in allowed:
                    out.append(f"line {number}: {flag} is not a flag of {' or '.join(scripts)}")
        for script in SCRIPT.findall(line):
            problem = _script_problem(script, line)
            if problem:
                out.append(f"line {number}: {problem}")
        for token in _key_tokens(line):
            named.add(token)
            if token.split(".")[0] not in checked_roots:
                continue
            if token in names or any(n.startswith(token + ".") for n in names):
                continue
            if any(token.startswith(t + ".") for t in open_tables):
                continue
            if token in not_yet:
                if not _names(not_yet[token], line):
                    out.append(f"line {number}: `{token}` has not landed; name its ticket "
                               f"{not_yet[token]} on the same line")
                continue
            out.append(f"line {number}: `{token}` is not a keys.json key")
        if "--set" in line and any(_names(k, line) for k in confirm_only + ("humanOnly",)):
            out.append(f"line {number}: --set beside a confirm-only or humanOnly key")
    for entry, ticket in not_yet.items():
        if entry in names or any(n.startswith(entry + ".") for n in names):
            out.append(f"NOT_YET {entry} ({ticket}) landed: remove it from NOT_YET and "
                       "write the example")
        if entry not in named:
            out.append(f"NOT_YET {entry} ({ticket}) is never named in the guide")
    sections = _sections(text)
    for key in confirm_only:
        holding = [(h, b) for h, b in sections if _names(key, b) or _names(key, h)]
        if not holding:
            out.append(f"confirm-only key {key} is not named in the guide")
        for heading, body in holding:
            if "crew_confirm_config.py propose" not in body or "/crew:confirm-config" not in body:
                out.append(f"section {heading!r} names {key} without the propose and "
                           "/crew:confirm-config route")
    family_body = next((b for h, b in sections if "Where each key family" in h), None)
    if family_body is None:
        out.append("no 'Where each key family is explained' section")
    else:
        for family in families:
            if f"`{family}`" not in family_body:
                out.append(f"family {family} is not named in the family section")
    if example_names is not None:
        cited = set(EXAMPLE_REF.findall(text))
        for name in sorted(cited - set(example_names)):
            out.append(f"examples/{name} is named but does not exist")
        for name in sorted(set(example_names) - cited):
            out.append(f"examples/{name} exists but the guide does not name it")
    return out


@pytest.fixture(scope="module")
def help_flags(tmp_path_factory, _isolated):  # pylint: disable=unused-argument
    home = tmp_path_factory.mktemp("helphome")
    flags = {}
    for name, script, args in (("crew_config.py", CREW_CONFIG_PY, ["--help"]),
                               ("crew_confirm_config.py", CONFIRM_PY, ["propose", "--help"])):
        code, stdout, _ = _run(script, args, home)
        assert code == 0, f"{name} {' '.join(args)} exit {code}"
        flags[name] = set(FLAG.findall(stdout))
    assert "--check-global" in flags["crew_config.py"]
    assert "--layer" in flags["crew_confirm_config.py"]
    return flags


@pytest.fixture(scope="module")
def keys():
    return load_keys()


def _guide(keys, help_flags, text=None, **kwargs):
    kwargs.setdefault("not_yet", NOT_YET)
    kwargs.setdefault("confirm_only", CONFIRM_ONLY)
    return guide_problems(read_guide() if text is None else text, keys,
                          kwargs.pop("not_yet"), kwargs.pop("confirm_only"),
                          help_flags=help_flags, **kwargs)


# === must-allow ================================================================

@pytest.mark.parametrize("path", example_paths(), ids=os.path.basename)
def test_committed_example_passes(path, tmp_path, keys):
    assert example_layer(path) is not None, path
    assert example_problems(path, example_layer(path), str(tmp_path), keys) == []


def test_both_layers_have_examples():
    layers = {example_layer(p) for p in example_paths()}
    assert layers == {"repo", "machine"}


def test_committed_guide_passes(keys, help_flags):
    names = [os.path.basename(p) for p in example_paths()]
    assert _guide(keys, help_flags, example_names=names) == []


def test_every_family_is_named(keys, help_flags):
    problems = _guide(keys, help_flags)
    assert not [p for p in problems if p.startswith("family ")]


@pytest.mark.parametrize("layer,data", [
    ("repo", {"resume": {"auto": False}}),
    ("machine", {"resume": {"auto": True}}),
    ("repo", {"humanOnly": {"approve": True}}),
    ("machine", {"humanOnly": {"approve": True}}),
    ("repo", {"guards": {"git": {"allow": "off"}}}),
    ("machine", {"guards": {"git": {"allow": "off"}}}),
])
def test_layer_class_allows(layer, data, keys):
    assert registry_problems(data, layer, keys) == []


@pytest.mark.parametrize("text", [
    "Production hours (`production.hours`) arrive with R-40.",
    "The table `qa` and the table `guards.git`.",
    "An entry `tiers.workspace:example` under the open table.",
])
def test_guide_key_tokens_allowed(text, keys, help_flags):
    assert [p for p in _guide(keys, help_flags, text=text) if p.startswith("line")] == []


def test_every_layer_string_has_a_row(keys):
    assert {k["layer"] for k in keys} <= set(LAYER_CLASS)


def test_open_tables_derived_and_not_empty(keys):
    assert {k["key"] for k in keys if k["kind"] == "open-table"}


def test_not_yet_has_not_landed(keys):
    names = {k["key"] for k in keys}
    for entry, ticket in NOT_YET.items():
        assert entry not in names and not any(n.startswith(entry + ".") for n in names), (
            f"{entry} landed: remove it from NOT_YET (it waited for {ticket}) and write "
            "the example")


def test_confirm_only_matches_propose(tmp_path):
    """Decision 9: `propose` refuses a key outside CONFIRM_ONLY (exit 2) and its
    message lists exactly CONFIRM_ONLY. The refused key writes nothing."""
    code, stdout, stderr = _run(CONFIRM_PY, [
        "propose", "--layer", "machine", "--key", "qa.provider",
        "--global-path", str(tmp_path / "machine.json")], tmp_path)
    assert code == 2, (code, stdout, stderr)
    found = re.search(r"those are: ([^)]*)\)", stdout + stderr)
    assert found, stdout + stderr
    assert {s.strip() for s in found.group(1).split(",")} == set(CONFIRM_ONLY)
    assert not (tmp_path / "machine.json").exists()


# === must-block (sabotage rows) =================================================

def _mutated(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


def _load_example(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as fh:
        return json.load(fh)


def _caught(problems, *checks):
    return [p for p in problems if p.startswith(checks)]


def _check(tmp_path, keys, name, data, *checks, layer=None):
    path = _mutated(tmp_path, name, data)
    problems = example_problems(path, layer or example_layer(path), str(tmp_path / "w"), keys)
    assert _caught(problems, *checks), problems
    return problems


def test_s1_repo_typo_key(tmp_path, keys):
    data = _load_example("repo-production.json")
    data["producton"] = data.pop("production")
    _check(tmp_path, keys, "repo-x.json", data, "(c)")


def test_s2_machine_repo_only_key(tmp_path, keys):
    data = _load_example("machine-reviewers-kimi-first.json")
    data["production"] = {"hosts": ["prod-*"]}
    problems = _check(tmp_path, keys, "machine-x.json", data, "(b)")
    assert _caught(problems, "(c)"), problems


def test_s3_machine_typo_key(tmp_path, keys):
    data = _load_example("machine-reviewers-kimi-first.json")
    data["qa"]["ordr"] = data["qa"].pop("order")
    problems = _check(tmp_path, keys, "machine-x.json", data, "(b)")
    assert _caught(problems, "(c)"), problems


def test_s4_repo_nonprod_not_a_list(tmp_path, keys):
    data = _load_example("repo-production.json")
    data["environments"]["nonProd"] = "dev*"
    _check(tmp_path, keys, "repo-x.json", data, "(b)")


@pytest.mark.parametrize("name", ["repo-minimal.json", "machine-reviewers-kimi-first.json"])
def test_s5_bad_value(tmp_path, keys, name):
    data = _load_example(name)
    data["pm"] = {"authority": "yolo"}
    _check(tmp_path, keys, name, data, "(e)")


def test_s6_bad_list_element(tmp_path, keys):
    data = _load_example("machine-reviewers-codex-first.json")
    data["qa"]["order"] = ["codex", "gpt"]
    _check(tmp_path, keys, "machine-x.json", data, "(e)")


@pytest.mark.parametrize("entries", [
    {"workspace:example-dev": {"tier": "staging"}},
    {"cluster:x": {"tier": "dev"}},
])
def test_s7_bad_tiers(tmp_path, keys, entries):
    _check(tmp_path, keys, "machine-x.json", {"tiers": entries}, "(f)")


@pytest.mark.parametrize("data", [
    {"unattendedCloud": {"aws": {"nonProd": {"dev": {"profile": "p", "identity": "arn:x/"}}}}},
    {"notify": {"tokenEnv": "CREW_BOT_TOKEN"}},
])
def test_s8_repo_machine_only_key(tmp_path, keys, data):
    _check(tmp_path, keys, "repo-x.json", dict(data, schema=8), "(d)")


@pytest.mark.parametrize("text", ["[]", '{"schema": 8,'])
def test_s9_not_an_object(tmp_path, keys, text):
    _check(tmp_path, keys, "repo-x.json", text, "(a)")


def test_s10_no_layer_prefix(tmp_path, keys):
    path = _mutated(tmp_path, "other.json", {"schema": 8})
    assert example_layer(path) is None
    assert example_problems(path, example_layer(path), str(tmp_path / "w"), keys)


@pytest.mark.parametrize("line", [
    "Run `crew_config.py --frobnicate`.",
    "Run `crew_confirm_config.py propose --frobnicate`.",
])
def test_s11_unknown_flag(keys, help_flags, line):
    assert any("--frobnicate" in p for p in _guide(keys, help_flags, text=line))


def test_s12_unknown_command(keys, help_flags):
    assert any("/crew:nonesuch" in p for p in _guide(keys, help_flags, text="Run `/crew:nonesuch`."))


def test_s13a_planned_family_sub_key(keys, help_flags):
    problems = _guide(keys, help_flags, text="Set `mode.default` (R-M1).")
    assert any("`mode.default`" in p for p in problems), problems


def test_s13f_planned_families_is_what_catches_s13a(keys, help_flags):
    problems = _guide(keys, help_flags, text="Set `mode.default` (R-M1).", planned=())
    assert not any("`mode.default`" in p for p in problems), problems


@pytest.mark.parametrize("token", ["qa.nosuch", "production.nosuch"])
def test_s13b_unknown_key(keys, help_flags, token):
    problems = _guide(keys, help_flags, text=f"Set `{token}`.")
    assert any(f"`{token}`" in p for p in problems), problems


@pytest.mark.parametrize("token", ["production.hours", "mode"])
def test_s13c_not_yet_without_ticket(keys, help_flags, token):
    problems = _guide(keys, help_flags, text=f"Set `{token}` soon.")
    assert any("has not landed" in p and token in p for p in problems), problems


def test_s13d_not_yet_landed(keys, help_flags):
    not_yet = dict(NOT_YET, **{"qa.order": "R-XX"})
    problems = _guide(keys, help_flags, not_yet=not_yet)
    assert any("NOT_YET qa.order" in p and "landed" in p for p in problems), problems


def test_s13e_not_yet_unnamed(keys, help_flags):
    not_yet = dict(NOT_YET, decider="R-D1")
    problems = _guide(keys, help_flags, not_yet=not_yet)
    assert any("NOT_YET decider" in p and "never named" in p for p in problems), problems


def test_s14_example_index(keys, help_flags):
    names = [os.path.basename(p) for p in example_paths()]
    extra = _guide(keys, help_flags, example_names=names + ["repo-unnamed.json"])
    assert any("repo-unnamed.json exists" in p for p in extra), extra
    missing = _guide(keys, help_flags, example_names=names[1:])
    assert any(f"{names[0]} is named but does not exist" in p for p in missing), missing


def test_s15_family_removed(keys, help_flags):
    text = read_guide().replace("- `memory`:", "- memory:")
    assert "family memory is not named in the family section" in _guide(keys, help_flags, text=text)


@pytest.mark.parametrize("line", [
    "crew_config.py --set humanOnly.approve=false --global --apply",
    "crew_config.py --set guards.git.allow='\"all\"' --global",
])
def test_s16_s17_set_beside_confirm_only(keys, help_flags, line):
    text = read_guide() + "\n" + line + "\n"
    assert any("--set beside" in p for p in _guide(keys, help_flags, text=text))


@pytest.mark.parametrize("old,new", [
    ("- `guards.git.allow`:", "- the git key:"),
    ("`crew_confirm_config.py propose --layer", "`crew_confirm_config.py --layer"),
    ("`/crew:confirm-config <change_id>` twice", "the confirm command twice"),
])
def test_s18_confirm_route_missing(keys, help_flags, old, new):
    text = read_guide()
    assert old in text, old
    text = text.replace(old, new)
    if old.startswith("- `guards"):
        text = text.replace("guards.git.allow", "the git key")
    assert any("confirm" in p for p in _guide(keys, help_flags, text=text))


def test_s19_unrouted_confirm_only_key(keys, help_flags):
    confirm_only = CONFIRM_ONLY + ("qa.provider",)
    problems = _guide(keys, help_flags, confirm_only=confirm_only)
    assert any("qa.provider" in p for p in problems), problems


@pytest.mark.parametrize("data", [
    {"resume": {"auto": True}},
    {"context": {"autoClear": {"enabled": True}}},
])
def test_s20_repo_arms_machine_key(tmp_path, keys, data):
    _check(tmp_path, keys, "repo-x.json", dict(data, schema=8), "(d)")


@pytest.mark.parametrize("name", ["repo-x.json", "machine-x.json"])
def test_s21_human_only_opt_out(tmp_path, keys, name):
    data = {"humanOnly": {"approve": False}}
    if name.startswith("repo"):
        data["schema"] = 8
    _check(tmp_path, keys, name, data, "(d)")


@pytest.mark.parametrize("name", ["repo-x.json", "machine-x.json"])
@pytest.mark.parametrize("value", ["all", ["commit"]])
def test_s22_confirm_only_value(tmp_path, keys, name, value):
    data = {"guards": {"git": {"allow": value}}}
    if name.startswith("repo"):
        data["schema"] = 8
    _check(tmp_path, keys, name, data, "(d)")


def test_s23_unknown_layer_class(keys):
    mutated = copy.deepcopy(keys)
    next(k for k in mutated if k["key"] == "qa.provider")["layer"] = "mystery"
    data = _load_example("machine-reviewers-kimi-first.json")
    problems = registry_problems(data, "machine", mutated)
    assert any("'mystery'" in p for p in problems), problems


def test_s24_open_tables_are_derived(tmp_path, keys):
    mutated = copy.deepcopy(keys)
    next(k for k in mutated if k["key"] == "tiers")["kind"] = "type"
    path = os.path.join(EXAMPLES, "machine-tiers.json")
    problems = example_problems(path, "machine", str(tmp_path), mutated)
    assert _caught(problems, "(d)"), problems


def test_s25_leaf_under_closed_table(tmp_path, keys):
    data = _load_example("machine-reviewers-codex-first.json")
    data["qa"]["codex"]["nosuch"] = 1
    problems = _check(tmp_path, keys, "machine-x.json", data, "(d)")
    assert any("qa.codex.nosuch" in p for p in problems), problems
