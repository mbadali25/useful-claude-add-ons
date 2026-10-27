"""The stdlib checker for the review-finding rule classes (L-0715 PR B2).

WHAT. It applies the five rules of `plugin/crew/lint/semgrep/crew-classes.yml` to files, on any host
that runs Python, with no semgrep and no YAML package. The rule file is read through
`review_lint_rules` (data: ids, messages, scopes, regexes); the code-shaped matching lives here, in
`RULES`. Nothing calls this module yet (the runner is L-0932): it is inert.

ONE SIDE PER RUN. A caller runs it once per tree with that tree's own `--rules` copy, so a bundle that
edits the rule file is judged by its own edit on its own side:

    review_lint_classes.py --rules FILE [--skip ID]... [--strip-first-segment] PATH...

stdout is one ASCII JSON document: version, rules (ids run), skipped_rules, not_covered (the
`# not-shipped:` classes), files {scanned, skipped_by_scope, aborted [{path, reason}]} and results
[{path, rule, message, line}]. Exit 0 whenever it ran; exit 2, with a message on stderr and no
document, for any rule-file, id, shape or usage problem. `applicable_rules` is the one scope decision,
so a runner can recompute it.

UNKNOWN IS NOT A PASS (GEN-01). A rule file the reader refuses, a rule id with no implementation here,
an implementation whose rule left the file, and a rule whose pattern fingerprint is not in the SET of
accepted fingerprints below are all exit 2. A file that cannot be read, decoded or parsed is an
`aborted` row, never an empty source. A requested file is in exactly one of the three file lists.

APPROXIMATION. The taint rules follow assignment, method calls on a tainted receiver, calls with a
tainted argument, containers and one `for`/`with` hop inside one function (module level is one
pseudo-function). They do not follow calls across functions, attributes of `self` or comprehension
variables. `# nosemgrep` is read from real comment tokens, on the finding's line or the line above.
Where semgrep puts a finding on the opening parenthesis of a parenthesised multi-line sink, this
reports the call's own line (a documented divergence in the quieter direction).

LINES are counted on "\\n" after decoding; `splitlines` is never used on file text (PYTHON-10).
"""

import argparse
import ast
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tokenize
import warnings
from typing import NamedTuple

_NAME = "review_lint_rules"
_READER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), _NAME + ".py")


def _load_reader():
    """The reader is loaded by path: `-I` leaves the script directory off `sys.path`, and a stray
    module in the checked tree must never be imported in its place."""
    loaded = sys.modules.get(_NAME)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(_NAME, _READER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    spec.loader.exec_module(module)
    return module


READER = _load_reader()
_ABORTS = (SyntaxError, ValueError, RecursionError, MemoryError, UnicodeDecodeError, tokenize.TokenError, OSError)
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NOSEMGREP = re.compile(r"(?:#|<!--)[ ]*nosemgrep(?::[ ]*([^\s,]+(?:[ ]*,[ ]*[^\s,]+)*))?")


class Usage(Exception):
    """A rule-file, id, shape or usage problem: exit 2 with this message."""


class _Sources(NamedTuple):
    call_attrs: tuple
    call_names: tuple
    attrs: tuple


class Source:
    """One decoded file; `tree` is None for a non-Python file."""

    def __init__(self, text, tree):
        self.text, self.tree = text, tree
        self.lines = text.split("\n")
        self.imports = _imports(tree) if tree is not None else {}
        self.comments = _comments(text) if tree is not None else _marker_lines(self.lines)


def _imports(tree):
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                found[alias.asname or root] = alias.name if alias.asname else root
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                found[alias.asname or alias.name] = node.module + "." + alias.name
    return found


def _comments(text):
    found = {}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            found.setdefault(token.start[0], []).append(token.string)
    return found


def _marker_lines(lines):
    return {number: [line] for number, line in enumerate(lines, 1) if "nosemgrep" in line}


def _suppressed(rule_id, comments, line):
    for number in (line, line - 1):
        for comment in comments.get(number, ()):
            found = _NOSEMGREP.search(comment)
            if found and (not found.group(1) or any(rule_id.endswith(i.strip()) for i in found.group(1).split(","))):
                return True
    return False


def _resolve(node, imports):
    """Dotted name of a Name/Attribute chain, its first segment mapped through the imports."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(imports.get(node.id, node.id))
    return ".".join(reversed(parts))


def _visible(node):
    """Every node under `node` except the insides of comprehensions and generator expressions, which
    semgrep 1.95.0's taint mode does not enter (measured, and pinned by a test)."""
    found, pending = [], [node]
    while pending:
        current = pending.pop()
        found.append(current)
        if not isinstance(current, _COMPREHENSIONS):
            pending.extend(ast.iter_child_nodes(current))
    return found


class _Flow:
    """A forward taint pass in source order over one function body, a class body or the module."""

    def __init__(self, src, sources, sink):
        self.src, self.sources, self.sink, self.hits = src, sources, sink, []

    def is_source(self, node):
        if isinstance(node, ast.Call):
            func = node.func
            if _resolve(func, self.src.imports) == "subprocess.check_output":
                return True
            if isinstance(func, ast.Name):
                imported = self.src.imports.get(func.id, "").rpartition(".")[2]
                return func.id in self.sources.call_names or imported in self.sources.call_attrs
            if isinstance(func, ast.Attribute) and func.attr in self.sources.call_attrs:
                return not (func.attr == "read_bytes" and (node.args or node.keywords))
            return False
        return isinstance(node, ast.Attribute) and (
            node.attr in self.sources.attrs or _resolve(node, self.src.imports) == "sys.stdin"
        )

    def tainted(self, node, env):
        if self.is_source(node):
            return True
        if isinstance(node, ast.Name):
            return node.id in env
        if isinstance(node, ast.Call):
            receiver = isinstance(node.func, ast.Attribute) and self.tainted(node.func.value, env)
            return receiver or any(self.tainted(a, env) for a in node.args) or any(
                self.tainted(k.value, env) for k in node.keywords
            )
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred, ast.Await, ast.FormattedValue, ast.NamedExpr)):
            return self.tainted(node.value, env)
        if isinstance(node, ast.IfExp):
            return self.tainted(node.body, env) or self.tainted(node.orelse, env)
        if isinstance(node, ast.BinOp):
            return self.tainted(node.left, env) or self.tainted(node.right, env)
        if isinstance(node, ast.Dict):
            return any(v is not None and self.tainted(v, env) for v in node.values)
        children = getattr(node, "values", None) or getattr(node, "elts", None)
        return isinstance(node, (ast.BoolOp, ast.JoinedStr, ast.List, ast.Tuple, ast.Set)) and any(
            self.tainted(c, env) for c in children
        )

    def scan(self, node, env):
        nodes = _visible(node)
        exempt = {
            id(n.value.values[0])
            for n in nodes
            if isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.BoolOp)
            and isinstance(n.value.op, ast.Or)
            and len(n.value.values) == 2
            and isinstance(n.value.values[1], ast.List)
            and isinstance(n.slice, ast.Constant)
            and n.slice.value == 0
        }
        sliced = {id(n.value) for n in nodes if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)}
        self.hits.extend(
            n.lineno
            for n in nodes
            if isinstance(n, ast.Call) and id(n) not in exempt | sliced and self.sink(self, n, env)
        )

    def bind(self, target, taint, env, clear):
        if isinstance(target, ast.Name):
            if taint:
                env.add(target.id)
            elif clear:
                env.discard(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self.bind(item, taint, env, clear)
        elif isinstance(target, ast.Starred):
            self.bind(target.value, taint, env, clear)

    def block(self, stmts, env):
        for stmt in stmts:
            env = self.stmt(stmt, env)
        return env

    def stmt(self, node, env):
        if isinstance(node, _DEFS):
            return env
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if node.value is not None:
                self.scan(node.value, env)
                taint = self.tainted(node.value, env)
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    self.bind(target, taint, env, not isinstance(node, ast.AugAssign))
            return env
        blocks = [getattr(node, f) for f in ("body", "orelse", "finalbody") if isinstance(getattr(node, f, None), list)]
        blocks += [h.body for h in getattr(node, "handlers", ())] + [c.body for c in getattr(node, "cases", ())]
        if not blocks:
            self.scan(node, env)
            return env
        for field in ("test", "iter", "subject"):
            if getattr(node, field, None) is not None:
                self.scan(getattr(node, field), env)
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.bind(node.target, self.tainted(node.iter, env), env, False)
        for item in getattr(node, "items", ()):
            self.scan(item.context_expr, env)
            if item.optional_vars is not None:
                self.bind(item.optional_vars, self.tainted(item.context_expr, env), env, False)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return self.block(node.body, env)
        joined = set(env) if hasattr(node, "cases") else set()
        for stmts in blocks:
            joined |= self.block(stmts, set(env))
        return joined


def _taint_rule(sources, sink):
    def run(_rule, src):
        flow = _Flow(src, sources, sink)
        for node in ast.walk(src.tree):
            if isinstance(node, (ast.Module, *_DEFS)):
                flow.block(node.body, set())
        return flow.hits

    return run


def _splitlines_sink(flow, call, env):
    return (
        isinstance(call.func, ast.Attribute) and call.func.attr == "splitlines" and flow.tainted(call.func.value, env)
    )


def _json_sink(flow, call, env):
    if _resolve(call.func, flow.src.imports) not in ("json.load", "json.loads"):
        return False
    if any(k.arg == "object_pairs_hook" for k in call.keywords):
        return False
    return any(flow.tainted(a, env) for a in call.args) or any(flow.tainted(k.value, env) for k in call.keywords)


def _bare_interpreter(rule, src):
    element = re.compile(rule.regexes["metavariable-regex:$E"])
    names = re.compile(rule.regexes["metavariable-regex:$G"])
    hits = []
    for node in ast.walk(src.tree):
        if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], (ast.List, ast.Tuple))):
            continue
        if not node.args[0].elts:
            continue
        dotted = _resolve(node.func, src.imports)
        direct = isinstance(node.func, ast.Attribute) and bool(dotted)
        direct = direct and dotted.startswith("subprocess.") and dotted.count(".") == 1
        if direct or (isinstance(node.func, ast.Name) and names.search(node.func.id)):
            text = ast.get_source_segment(src.text, node.args[0].elts[0])
            if text is None:
                raise ValueError("no source segment for a call argument at line " + str(node.lineno))
            if element.search(text):
                hits.append(node.lineno)
    return hits


def _unquoted_root(rule, src):
    pattern = re.compile(rule.regexes["pattern-regex"])
    return [src.text.count("\n", 0, found.start()) + 1 for found in pattern.finditer(src.text)]


def _no_assertion(rule, src):
    named = re.compile(rule.regexes["metavariable-regex:$T"])
    asserting = re.compile(rule.regexes["pattern-not-regex"])
    hits = []
    for node in ast.walk(src.tree):
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and named.search(node.name)):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        chunk = src.lines[start - 1 : node.end_lineno]
        chunk[-1] = chunk[-1].encode("utf-8")[: node.end_col_offset].decode("utf-8")
        if not asserting.search("\n".join(chunk)):
            hits.append(start)
    return hits


_SPLIT = _Sources(("read_text", "read"), (), ("stdout", "stderr"))
_JSON = _Sources(("read_text", "read_bytes", "read"), ("open",), ("stdout",))

# rule id -> (matcher, SET of accepted rule-block fingerprints). A second fingerprint goes in beside
# the first when a rule's shape changes (harness PR, then the rule PR, then a cleanup PR).
RULES = {
    "crew-splitlines-untrusted-text": (
        _taint_rule(_SPLIT, _splitlines_sink),
        frozenset({"5299c144776cafd34effaacb264c69001638b543b32d9e6dd6d00590eb386132"}),
    ),
    "crew-json-duplicate-keys": (
        _taint_rule(_JSON, _json_sink),
        frozenset({"7322fd7498562559b2050c12078c35d107cf5aa4925e4b77ad88ea39f59e5181"}),
    ),
    "crew-bare-interpreter": (
        _bare_interpreter,
        frozenset({"f001f89c8a29af7218ebc65f4d94f5cab38df4457fa5f0b6eb93c0a58a6627ff"}),
    ),
    "crew-unquoted-plugin-root": (
        _unquoted_root,
        frozenset({"d583f4df483b68f8c2759a143d16ae0cdd775c5d7d6c6ae9b5a3cc420deba0fe"}),
    ),
    "crew-test-no-assertion": (
        _no_assertion,
        frozenset({"c6f9fd0d2cdbcb453d3b8c84bfe5efee4d915b924c7aef6fb21cf3358c638d26"}),
    ),
}


def load_rules(path, skip=()):
    """The rule file, checked against `RULES` both ways and by fingerprint. Raises Usage."""
    try:
        rules = READER.read_rules(path)
    except READER.RuleFileError as exc:
        raise Usage("rule file: " + str(exc)) from exc
    for rule in rules.rules:
        for key, pattern in rule.regexes.items():
            try:
                re.compile(pattern)
            except re.error as exc:
                raise Usage("rule " + rule.id + ": regex " + key + " does not compile: " + str(exc)) from exc
        if rule.id not in RULES:
            raise Usage("rule " + rule.id + " has no implementation in the checker")
        if rule.fingerprint not in RULES[rule.id][1]:
            raise Usage("rule " + rule.id + " changed shape; update the checker")
    for rule_id in RULES:
        if rule_id not in rules.ids:
            raise Usage("the checker implements " + rule_id + ", which is not in the rule file")
    for rule_id in skip:
        if rule_id not in rules.ids:
            raise Usage("--skip " + rule_id + " is not a rule id in the rule file")
    return rules


def applicable_rules(rules, rel, skip=()):
    """The active rules whose language and `paths` admit `rel` (POSIX, relative to the tree root)."""
    return [
        rule
        for rule in rules.rules
        if rule.id not in skip
        and (rel.endswith(".py") if "python" in rule.languages else "generic" in rule.languages)
        and READER.matches_scope(rel, rule.include, rule.exclude)
    ]


def check_text(rel, data, active):
    """[(rule id, line)] for one file's bytes; raises one of `_ABORTS` when the file cannot be judged."""
    if b"\x00" in data:
        raise ValueError("a NUL byte")
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    tree = None
    if rel.endswith(".py"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    src = Source(text, tree)
    found = []
    for rule in active:
        for line in RULES[rule.id][0](rule, src):
            if not _suppressed(rule.id, src.comments, line):
                found.append((rule, line))
    return found


def _read_regular(path):
    """The bytes of one regular file: no symlink, no Windows reparse point (junction), and no wait on a
    FIFO or device, decided on the opened descriptor so a swap after the check cannot be followed."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("a symlink or reparse point")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _reason(exc):
    detail = exc.args[0] if exc.args and isinstance(exc.args[0], str) else ""
    return type(exc).__name__ + (": " + detail if detail else "")


def _relative(arg, strip):
    path = arg.replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise Usage("absolute or drive-letter path refused: " + arg)
    if strip:
        path = path.partition("/")[2]
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise Usage("not a relative path inside the tree: " + arg)
    return "/".join(parts)


def run(rules_path, paths, skip=(), strip=False):
    """The result document for `paths` (disk paths), or raises Usage."""
    rules = load_rules(rules_path, skip)
    wanted = {}
    for arg in paths:
        rel = _relative(arg, strip)
        if rel in wanted:
            raise Usage("the same path twice: " + rel)
        wanted[rel] = arg
    files = {"scanned": [], "skipped_by_scope": [], "aborted": []}
    results = []
    for rel, arg in sorted(wanted.items()):
        active = applicable_rules(rules, rel, skip)
        if not active:
            files["skipped_by_scope"].append(rel)
            continue
        try:
            found = check_text(rel, _read_regular(arg), active)
        except _ABORTS as exc:
            files["aborted"].append({"path": rel, "reason": _reason(exc)})
            continue
        files["scanned"].append(rel)
        results.extend(
            {"path": rel, "rule": rule.id, "message": rule.message, "line": line} for rule, line in sorted(
                found, key=lambda item: (item[1], item[0].id)
            )
        )
    return {
        "version": 1,
        "rules": [rule.id for rule in rules.rules if rule.id not in skip],
        "skipped_rules": sorted(skip),
        "not_covered": sorted(rules.not_shipped),
        "files": files,
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="review_lint_classes.py")
    parser.add_argument("--rules", required=True)
    parser.add_argument("--skip", action="append", default=[])
    parser.add_argument("--strip-first-segment", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    try:
        document = run(args.rules, args.paths, tuple(args.skip), args.strip_first_segment)
    except Usage as exc:
        message = str(exc).encode("ascii", "backslashreplace").decode("ascii")
        sys.stderr.buffer.write(("review_lint_classes: " + message + "\n").encode("ascii"))
        return 2
    sys.stdout.buffer.write(json.dumps(document, ensure_ascii=True, sort_keys=True).encode("ascii") + b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
