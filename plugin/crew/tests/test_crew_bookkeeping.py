"""crew's own bookkeeping under `.crew/` (T-0068): ONE list,
`crew_ticket.CREW_BOOKKEEPING_PATHS`, that the review bundle, the completion
audit, the scope guard and the verify gate all leave out.

Two-sided on purpose. A path a crew script writes for itself that is missing
from the list keeps the TSS-510 deadlock (the gate's record stales the
receipt, the scope base fails the audit). A path crew READS as config or a map
wrongly put on it hides a real change from review and the audit. So every
`.crew/<name>` a crew hook script spells must be in exactly one of
`CREW_BOOKKEEPING_PATHS` and `CREW_CONTENT_PATHS`, and the matcher is pinned
against git's own reading of the exclude pathspecs.
"""
import ast
import glob
import os
import re
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access

# `.crew/<first segment>` as text. The look-behind keeps `sub.crew/` and
# `my.crew/` out; a regex escape (`\.crew/crew\.json`) is unescaped first.
_CREW_RE = re.compile(r"(?<![A-Za-z0-9_-])\.crew/([A-Za-z0-9._<>*${}-]+)")
# A variable tail, in each spelling the scripts use, becomes `*`.
_VARIABLE_RE = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|<[^>]*>|\{[^}]*\}")

# Joins whose `.crew` child is a run-time value the walk cannot resolve, each
# with the names it takes. A new one fails the walk until it is listed here.
_DYNAMIC_JOINS = {
    ("crew_migrate.py", "name"): ("pm-journal.md", "pm-standing.md"),  # JOURNAL_FILES
    ("crew_status.py", "name"): ("metrics.jsonl", "metrics.md"),  # _metrics_line, a read
}


def _normalise(name):
    name = _VARIABLE_RE.sub("*", name).rstrip(".")
    return re.sub(r"\*+", "*", name)


def _module_constants(tree):
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _all_constants():
    out = {}
    for path in glob.glob(os.path.join(SCRIPTS, "*.py")):
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            out[stem] = _module_constants(ast.parse(handle.read()))
    return out


def _value(node, own, everything):
    """The string `node` evaluates to, with each unknown part as `*`; None
    when nothing of it is known."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in own:
        return own[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        found = everything.get(node.value.id, {}).get(node.attr)
        if found is not None:
            return found
        for consts in everything.values():  # re-exported (crew_state -> crew_guards)
            if node.attr in consts:
                return consts[node.attr]
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _value(node.left, own, everything)
        right = _value(node.right, own, everything)
        if left is None and right is None:
            return None
        return (left or "*") + (right or "*")
    if isinstance(node, ast.JoinedStr):
        parts = [_value(v, own, everything) if not isinstance(v, ast.FormattedValue)
                 else (_value(v.value, own, everything) or "*") for v in node.values]
        return "".join(p or "*" for p in parts)
    return None


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant) \
                and isinstance(node.body[0].value.value, str):
            ids.add(id(node.body[0].value))
    return ids


def crew_names():
    """{normalised `.crew/` child: {where}} for every crew hook script, plus
    the dynamic joins that could not be resolved, as [(file, expr)]."""
    found, unresolved = {}, []
    everything = _all_constants()

    def add(name, where):
        found.setdefault(_normalise(name), set()).add(where)

    for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
        base = os.path.basename(path)
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        own = _module_constants(tree)
        docs = _docstring_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs:
                for match in _CREW_RE.finditer(node.value.replace("\\.", ".")):
                    add(match.group(1), f"{base}:{node.lineno}")
            if isinstance(node, ast.Call):
                args = node.args
                for i, arg in enumerate(args[:-1]):
                    if _value(arg, own, everything) != ".crew":
                        continue
                    child = _value(args[i + 1], own, everything)
                    if child is None:
                        key = (base, ast.unparse(args[i + 1]))
                        for name in _DYNAMIC_JOINS.get(key, ()):
                            add(name, f"{base}:{node.lineno}")
                        if key not in _DYNAMIC_JOINS:
                            unresolved.append(key)
                    else:
                        add(child.split("/")[0], f"{base}:{node.lineno} join")
    for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.sh"))
                       + glob.glob(os.path.join(SCRIPTS, "*.ps1"))):
        base = os.path.basename(path)
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if line.lstrip().startswith("#"):
                    continue
                for match in _CREW_RE.finditer(line):
                    add(match.group(1), f"{base}:{number}")
    # A pattern over the whole directory (`.crew/**`, `.crew/*`) names no path.
    for pattern in [n for n in found if set(n) <= {"*"}]:
        del found[pattern]
    return found, unresolved


def _samples(name):
    concrete = name.replace("*", "x")
    return (f".crew/{concrete}", f".crew/{concrete}/x")


def test_every_crew_state_path_is_classified():
    found, unresolved = crew_names()
    for expected in (".scope-base", ".verify-gate.record.json", "metrics.jsonl", "config.json"):
        assert expected in found, f"the walk is vacuous: {expected} was not found"
    assert not unresolved, ("a join builds a `.crew/` path the walk cannot resolve; list it in "
                            f"_DYNAMIC_JOINS with the names it takes: {unresolved}")
    problems = []
    for name, where in sorted(found.items()):
        hits = [(s, crew_ticket.is_crew_bookkeeping(s), crew_ticket.is_crew_content(s))
                for s in _samples(name)]
        if any(b and c for _s, b, c in hits):
            problems.append(f"BOTH lists: .crew/{name} ({sorted(where)[0]})")
        elif not any(b or c for _s, b, c in hits):
            problems.append(f"unclassified: .crew/{name} ({', '.join(sorted(where)[:3])})")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("rel,expected", [
    (".crew/.scope-base", True),
    (".crew/.verify-gate.timings.json", True),
    (".crew/.verify-gate.record.json", True),
    (".crew/.verify-gate.lock/owner", True),
    (".crew/.autoclear-sent-abc", True),
    (".crew/event-claims/x", True),
    (".crew/event-claims/a/b", True),
    (".crew/metrics.md", True),
    ("sub/.crew/.scope-base", False),
    (".crew/.scope-baseX", False),
    (".crew/metrics.md.bak", False),
    (".crew/verify.json", False),
    (".crew/config.json", False),
    (".crew/codemap/INDEX.md", False),
    (".crew/event-claims", False),
    ("./.crew/.scope-base", False),
    (".crew//.scope-base", False),
    (".crew/../.crew/.scope-base", False),
    (".crew\\.scope-base", False),
    ("/.crew/.scope-base", False),
    ("", False),
    (None, False),
])
def test_is_crew_bookkeeping_matches_whole_segments_at_the_root(rel, expected):
    assert crew_ticket.is_crew_bookkeeping(rel) is expected


def test_git_excludes_are_root_anchored():
    specs = crew_ticket.bookkeeping_excludes()
    assert len(specs) == len(crew_ticket.CREW_BOOKKEEPING_PATHS)
    for spec, entry in zip(specs, crew_ticket.CREW_BOOKKEEPING_PATHS):
        assert spec == ":(exclude,top,glob)" + entry


def test_no_entry_is_on_both_lists():
    assert not set(crew_ticket.CREW_BOOKKEEPING_PATHS) & set(crew_ticket.CREW_CONTENT_PATHS)


def test_the_matcher_agrees_with_git(tmp_path):
    """git, not the matcher, decides what the bundle and the audit drop, so
    the two must agree path for path, from the root and from a subdirectory."""
    paths = [".crew/.scope-base", ".crew/.scope-baseX", ".crew/.verify-gate.record.json",
             ".crew/.verify-gate.lock/owner", ".crew/metrics.md", ".crew/metrics.md.bak",
             ".crew/event-claims/a/b", ".crew/x.lock", ".crew/verify.json",
             ".crew/codemap/x.md", ".crew/config.json.bak-1", "sub/.crew/.scope-base",
             "sub/.crew/metrics.md", ".crew/.autoclear-sent", ".crew/.autoclear-sentX/y"]
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel in paths:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x\n", encoding="utf-8")
    for cwd in (root, root / "sub"):
        listed = subprocess.run(
            ["git", "ls-files", "-o", "--full-name", "--", ":/"]
            + crew_ticket.bookkeeping_excludes(),
            cwd=str(cwd), capture_output=True, text=True, check=True).stdout.split("\n")
        kept = {p for p in listed if p}
        for rel in paths:
            assert (rel in kept) is (not crew_ticket.is_crew_bookkeeping(rel)), (cwd, rel)
