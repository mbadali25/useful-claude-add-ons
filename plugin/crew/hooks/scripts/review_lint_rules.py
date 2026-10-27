"""Reads the review-finding rule file, and refuses every shape it does not know (L-0931).

WHAT. `plugin/crew/lint/semgrep/crew-classes.yml` holds the data of the five rule classes: ids,
messages, classes, path scopes and the regexes. The checker that matches them (L-0715 PR B2) reads
that one file through this module, so the checker has no YAML package and no second copy of the
data. This module is inert: nothing calls it yet.

FAIL CLOSED. It is not a YAML parser. It reads the shape PR A wrote and raises `RuleFileError`
(message, line) for any other: an extra or missing key, a tab in the indentation, an anchor, alias
or tag, a duplicate rule id or key, a symlink or a non-regular file, an empty file, an unterminated
flow list, an unknown escape, a quoting form it does not read. A line it does not understand is
never skipped, because a skipped line turns a changed rule into a silent pass (GEN-01). A caller
prints the error and exits 2; there is never a partial rule set.

FINGERPRINT. The pattern blocks (`pattern-sources`, `pattern-sinks`, `patterns`, `pattern-regex`)
are opaque: their lines are dedented by the common prefix, right-stripped, blank lines dropped, and
hashed with `languages` and `mode`, so relative indentation (which can change YAML meaning) is part
of the hash. The five regex VALUES are replaced by a placeholder first, because they are data: a
regex edit needs no checker change, a structural edit does. The reader exposes one fingerprint per
rule; the SET of accepted fingerprints belongs to the checker, so a rule edit can land as a harness
PR that adds the new fingerprint, a feature PR that edits the file, and a cleanup PR that drops the
old one.

LINES are counted after decoding, on "\\n" only; `splitlines` is never used on file text, because it
also splits on U+2028, U+2029 and U+0085 (PYTHON-10).
"""

import dataclasses
import fnmatch
import hashlib
import os
import re
import stat

TOP_KEYS = ("languages", "severity", "mode", "message", "metadata", "paths")
OPAQUE_KEYS = ("pattern-sources", "pattern-sinks", "patterns", "pattern-regex")
REQUIRED_KEYS = ("languages", "severity", "message", "metadata", "paths")

_RULE_START = re.compile(r"^  - id:(?: (.*))?$")
_KEY_LINE = re.compile(r"^( *)([a-z][a-z-]*):(?: (.*))?$")
_WORD = re.compile(r"\s*([A-Za-z0-9_.-]+)\s*")
_QUOTED = re.compile(r'\s*"((?:[^"\\]|\\.)*)"\s*')
_PLAIN = re.compile(r"^[A-Za-z0-9_.-]+$")
_CLASS_NAME = re.compile(r"^[a-z0-9-]+$")
_SINGLE_QUOTED = re.compile(r"^'((?:[^']|'')*)'$")
_METAVARIABLE = re.compile(r"^\$[A-Z0-9_]+$")
_REGEX_LINE = re.compile(r"^(\s*(?:-\s+)*)(metavariable|regex|pattern-regex|pattern-not-regex):(\s*)(.*)$")
_NOT_SHIPPED_ENTRY = re.compile(r"^#   ([a-z0-9-]+): (\S.*)$")
_PLACEHOLDER = "<regex>"


class RuleFileError(Exception):
    """The rule file is missing, unreadable, or in a shape this reader does not know."""

    def __init__(self, message, line=0):
        super().__init__(message)
        self.message = message
        self.line = line

    def __str__(self):
        return ("line " + str(self.line) + ": " + self.message) if self.line else self.message


@dataclasses.dataclass(frozen=True)
class Rule:
    """One rule. `regexes` maps `pattern-regex`, `pattern-not-regex` and
    `metavariable-regex:<$VAR>` to the decoded regex text."""

    id: str
    line: int
    languages: tuple
    severity: str
    mode: str
    message: str
    rule_class: str
    standards: tuple
    include: tuple
    exclude: tuple
    regexes: dict
    fingerprint: str


@dataclasses.dataclass(frozen=True)
class Rules:
    """Every rule in file order, and the `# not-shipped:` header as {class: reason}."""

    rules: tuple
    not_shipped: dict

    @property
    def ids(self):
        return tuple(rule.id for rule in self.rules)


def read_rules(path):
    """Read one rule file alone. Raises RuleFileError; never returns part of a file."""
    lines = _load_lines(path)
    body_start = _find_rules_line(lines)
    not_shipped = _parse_not_shipped(lines[:body_start])
    chunks = _rule_chunks(lines, body_start + 2)
    rules, seen = [], {}
    for start, chunk in chunks:
        rule = _parse_rule(start, chunk)
        if rule.id in seen:
            raise RuleFileError("duplicate rule id " + rule.id + " (first at line " + str(seen[rule.id]) + ")", start)
        seen[rule.id] = start
        rules.append(rule)
    if not rules:
        raise RuleFileError("the file defines no rules", body_start + 1)
    return Rules(tuple(rules), not_shipped)


def _load_lines(path):
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise RuleFileError("cannot read the rule file: " + str(exc)) from exc
    if stat.S_ISLNK(mode):
        raise RuleFileError("the rule file is a symlink, which is refused")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuleFileError("cannot read the rule file: " + str(exc)) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuleFileError("the rule file is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read()
    finally:
        os.close(descriptor)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuleFileError("the rule file is not UTF-8: " + str(exc)) from exc
    text = text.replace("\r\n", "\n")
    if not text.strip(" \n"):
        raise RuleFileError("the rule file is empty")
    lines = [line.rstrip(" ") for line in text.split("\n")]
    current = ""
    for number, line in enumerate(lines, 1):
        start = _RULE_START.match(line)
        current = " (rule " + start.group(1) + ")" if start and start.group(1) else current
        if "\x00" in line or "\r" in line:
            raise RuleFileError("a NUL or a lone carriage return" + current, number)
        if "\t" in line[: len(line) - len(line.lstrip(" \t"))]:
            raise RuleFileError("a tab in the indentation; spaces only" + current, number)
    return lines


def _find_rules_line(lines):
    found = None
    for index, line in enumerate(lines):
        if line.startswith("rules:"):
            if line != "rules:" or found is not None:
                raise RuleFileError("expected a single bare `rules:` key", index + 1)
            found = index
        elif found is None and line.strip(" ") and not line.startswith("#"):
            raise RuleFileError("expected `rules:` or a comment, found: " + line.strip(" "), index + 1)
        elif found is not None and line.startswith("# not-shipped:"):
            raise RuleFileError("the `# not-shipped:` header belongs above `rules:`", index + 1)
    if found is None:
        raise RuleFileError("the file has no `rules:` key")
    return found


def _parse_not_shipped(header):
    """The comment block that starts at `# not-shipped:`: entries `#   <class>: <reason>`, ended by
    the first line that is not indented three spaces after the hash. An indented line that is not an
    entry, a second header and a repeated class are refused, never read as the end of the block."""
    listed, inside, seen = {}, False, False
    for number, line in enumerate(header, 1):
        if line.startswith("# not-shipped:"):
            if seen or line != "# not-shipped:":
                raise RuleFileError("a second or malformed `# not-shipped:` header", number)
            inside = seen = True
        elif inside and line.startswith("#   "):
            entry = _NOT_SHIPPED_ENTRY.match(line)
            if not entry:
                raise RuleFileError("not a `#   <class>: <reason>` entry: " + line, number)
            if entry.group(1) in listed:
                raise RuleFileError("class " + entry.group(1) + " listed twice under not-shipped", number)
            listed[entry.group(1)] = entry.group(2)
        else:
            inside = False
    return listed


def _rule_chunks(lines, first):
    """(line number, [(line number, text)]) per rule. Comments and blanks between rules are skipped;
    anything else outside a rule is an error."""
    chunks = []
    for number in range(first, len(lines) + 1):
        line = lines[number - 1]
        if _RULE_START.match(line):
            chunks.append((number, [(number, line)]))
        elif chunks:
            chunks[-1][1].append((number, line))
        elif line.strip(" ") and not line.lstrip(" ").startswith("#"):
            raise RuleFileError("expected a rule (`  - id:`), found: " + line.strip(" "), number)
    return chunks


def _parse_rule(start, chunk):
    rule_id = _RULE_START.match(chunk[0][1]).group(1)
    if not rule_id or not _PLAIN.match(rule_id):
        raise RuleFileError("rule id missing or not a plain word", start)

    def fail(message, line=start):
        raise RuleFileError("rule " + rule_id + ": " + message, line)

    for number, line in chunk[1:]:
        _refuse_yaml_features(line, number, fail)
    keys = _split_keys(chunk[1:], fail)
    for name in REQUIRED_KEYS:
        if name not in keys:
            fail("missing key `" + name + "`")
    if not any(name in keys for name in OPAQUE_KEYS):
        fail("no pattern key (one of " + ", ".join(OPAQUE_KEYS) + ")")
    languages = _flow_list(keys["languages"], False, fail)
    severity = _plain(keys["severity"], "severity", fail)
    mode = _plain(keys["mode"], "mode", fail) if "mode" in keys else ""
    metadata = _mapping(keys["metadata"], ("class", "standards"), fail)
    paths = _mapping(keys["paths"], ("include", "exclude"), fail, required=False)
    if not paths:
        fail("`paths` has neither include nor exclude", keys["paths"][0])
    if not _CLASS_NAME.match(_plain(metadata["class"], "metadata.class", fail)):
        fail("metadata.class is not a lowercase word", metadata["class"][0])
    regexes, blocks = {}, []
    for name in OPAQUE_KEYS:
        if name in keys:
            blocks.append(_opaque(name, keys[name], regexes, fail))
    fingerprint = hashlib.sha256(
        "\n".join(["languages=" + ",".join(languages), "mode=" + mode, *blocks]).encode("utf-8")
    ).hexdigest()
    return Rule(
        id=rule_id,
        line=start,
        languages=tuple(languages),
        severity=severity,
        mode=mode,
        message=_folded(keys["message"], fail),
        rule_class=metadata["class"][1],
        standards=tuple(_flow_list(metadata["standards"], False, fail)),
        include=tuple(_flow_list(paths["include"], True, fail)) if "include" in paths else (),
        exclude=tuple(_flow_list(paths["exclude"], True, fail)) if "exclude" in paths else (),
        regexes=regexes,
        fingerprint=fingerprint,
    )


def _refuse_yaml_features(line, number, fail):
    content = line.strip(" ")
    if not content or content.startswith("#"):
        return
    while content.startswith("- "):
        content = content[2:].lstrip(" ")
    keyed = re.match(r"^[A-Za-z0-9_$<-]+:\s+(\S)", content)
    if content[:1] in "&*!" or content.startswith("<<:") or (keyed and keyed.group(1) in "&*!"):
        fail("an anchor, alias, merge key or tag: " + content, number)


def _split_keys(lines, fail):
    """{key: (line number, inline value, [(line number, body text)])} for the keys at indent 4. A body
    line is blank or indented deeper; anything else at a shallower indent ends the key's body."""
    keys, current = {}, ()
    for number, line in lines:
        if not line.strip(" "):
            if current:
                current[2].append((number, line))
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent > 4:
            if not current:
                fail("an indented line with no key above it: " + line.strip(" "), number)
                continue
            current[2].append((number, line))
            continue
        current = ()
        if line.lstrip(" ").startswith("#"):
            continue
        match = _KEY_LINE.match(line)
        if indent != 4 or not match:
            fail("expected a key at indent 4, found: " + line.strip(" "), number)
        name = match.group(2)
        if name not in TOP_KEYS + OPAQUE_KEYS:
            fail("unknown key `" + name + "`", number)
        if name in keys:
            fail("duplicate key `" + name + "` (first at line " + str(keys[name][0]) + ")", number)
        current = keys[name] = (number, match.group(3) or "", [])
    return keys


def _plain(entry, name, fail):
    number, value, body = entry
    if not _PLAIN.match(value) or any(text.strip(" ") for _, text in body):
        fail(name + " must be one plain word", number)
    return value


def _flow_list(entry, quoted, fail):
    number, value, body = entry
    if any(text.strip(" ") for _, text in body):
        fail("a flow list must sit on one line", number)
    if not (value.startswith("[") and value.endswith("]")):
        fail("unterminated or unrecognised flow list: " + value, number)
    inner, position, items = value[1:-1], 0, []
    while True:
        match = (_QUOTED if quoted else _WORD).match(inner, position)
        if not match:
            fail("cannot read this flow list: " + value, number)
        items.append(_unescape(match.group(1), number, fail) if quoted else match.group(1))
        position = match.end()
        if position == len(inner):
            return items
        if inner[position] != ",":
            fail("cannot read this flow list: " + value, number)
        position += 1


def _unescape(text, number, fail):
    out, index = [], 0
    while index < len(text):
        if text[index] == "\\":
            if text[index + 1] not in '\\"':
                fail("unknown escape \\" + text[index + 1] + " in a quoted scalar", number)
            index += 1
        out.append(text[index])
        index += 1
    return "".join(out)


def _mapping(entry, allowed, fail, required=True):
    """The children of `metadata` or `paths`: {key: (line number, value, [])} at indent 6, one line each."""
    number, value, body = entry
    if value:
        fail("this key takes an indented block, not a value", number)
    found = {}
    for line_number, text in body:
        if not text.strip(" "):
            continue
        match = _KEY_LINE.match(text)
        if not match or len(match.group(1)) != 6 or match.group(2) not in allowed or not match.group(3):
            fail("expected one of " + ", ".join(allowed) + " at indent 6, found: " + text.strip(" "), line_number)
        if match.group(2) in found:
            fail("duplicate key `" + match.group(2) + "`", line_number)
        found[match.group(2)] = (line_number, match.group(3), [])
    if required:
        for name in allowed:
            if name not in found:
                fail("missing key `" + name + "`", number)
    return found


def _folded(entry, fail):
    number, value, body = entry
    if value != ">-":
        fail("message must be a `>-` folded scalar", number)
    text = list(body)
    while text and not text[-1][1].strip(" "):
        text.pop()
    if not text or any(not t.strip(" ") for _, t in text):
        fail("message is empty or holds a blank line", number)
    indents = {len(t) - len(t.lstrip(" ")) for _, t in text}
    if len(indents) != 1:
        fail("message lines must share one indentation", number)
    return " ".join(t.strip(" ") for _, t in text)


def _opaque(name, entry, regexes, fail):
    """Canonical text of one pattern block, filling `regexes` from the five regex positions."""
    number, value, body = entry
    first = "    " + name + ":" + (" " + value if value else "")
    block = [first]
    if name == "pattern-regex":
        if any(text.strip(" ") for _, text in body):
            fail("pattern-regex takes one single-quoted value", number)
        _record_regex(regexes, name, value, number, fail)
        block = ["    pattern-regex: " + _PLACEHOLDER]
    else:
        if value or not any(text.strip(" ") for _, text in body):
            fail(name + " takes an indented block, not a value", number)
        pending = ()
        for line_number, text in body:
            if not text.strip(" "):
                continue
            if text.lstrip(" ").startswith("#"):
                block.append(text)
                continue
            match = _REGEX_LINE.match(text)
            kind = match.group(2) if match else None
            if pending and (kind != "regex" or len(match.group(1)) != pending[1]):
                fail("metavariable " + pending[0] + " is not followed by its regex", pending[2])
            if kind == "metavariable":
                if not _METAVARIABLE.match(match.group(4)):
                    fail("cannot read this metavariable: " + match.group(4), line_number)
                pending = (match.group(4), len(match.group(1)), line_number)
                block.append(text)
            elif kind == "regex":
                if not pending:
                    fail("`regex:` with no metavariable above it", line_number)
                _record_regex(regexes, "metavariable-regex:" + pending[0], match.group(4), line_number, fail)
                pending = ()
                block.append(match.group(1) + "regex: " + _PLACEHOLDER)
            elif match:
                _record_regex(regexes, match.group(2), match.group(4), line_number, fail)
                block.append(match.group(1) + match.group(2) + ": " + _PLACEHOLDER)
            else:
                block.append(text)
        if pending:
            fail("metavariable " + pending[0] + " is not followed by its regex", pending[2])
    indent = min(len(text) - len(text.lstrip(" ")) for text in block)
    return name + "\n" + "\n".join(text[indent:].rstrip(" ") for text in block)


def _record_regex(regexes, key, value, number, fail):
    match = _SINGLE_QUOTED.match(value)
    if not match:
        fail("a regex must be one single-quoted scalar: " + value, number)
    if key in regexes:
        fail("duplicate regex position `" + key + "`", number)
    regexes[key] = match.group(1).replace("''", "'")


def matches_scope(rel, include, exclude):
    """Is `rel` (a POSIX path relative to the tree root) inside a rule's `paths`? An empty `include`
    admits every path; any `exclude` match removes it. Raises ValueError for a path that is not
    relative POSIX form: absolute, drive-lettered, backslashed, empty or climbing out of the tree."""
    if (
        not rel
        or "\\" in rel
        or re.match(r"^[A-Za-z]:", rel)
        or any(part in ("", "..") for part in rel.split("/"))
    ):
        raise ValueError("not a relative POSIX path: " + repr(rel))
    parts = rel.split("/")

    def hit(pattern):
        if "/" not in pattern:
            return fnmatch.fnmatchcase(parts[-1], pattern)
        return _glob(pattern.split("/"), parts)

    return (not include or any(hit(pattern) for pattern in include)) and not any(hit(pattern) for pattern in exclude)


def _glob(pattern, parts):
    """`**` is any run of directories, and a trailing `**` needs at least one name below it."""
    if not pattern:
        return not parts
    head = pattern[0]
    if head == "**":
        if len(pattern) == 1:
            return len(parts) >= 1
        return any(_glob(pattern[1:], parts[skip:]) for skip in range(len(parts) + 1))
    return bool(parts) and fnmatch.fnmatchcase(parts[0], head) and _glob(pattern[1:], parts[1:])


@dataclasses.dataclass(frozen=True)
class Canary:
    """One positive snippet per rule. `path` carries `{dir}`, `source` carries `{token}`. The checker's
    runner fills both with per-run random values and writes the file into the tree it checks."""

    rule_id: str
    path: str
    source: str

    def render(self, directory, token):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", directory) or not re.fullmatch(r"[a-z0-9]{6,}", token):
            raise ValueError("canary directory or token has an unexpected shape")
        return self.path.replace("{dir}", directory), self.source.replace("{token}", token)


CANARIES = {
    "crew-splitlines-untrusted-text": Canary(
        "crew-splitlines-untrusted-text",
        "{dir}/canary_splitlines.py",
        "import pathlib\n\n\ndef canary_{token}(path):\n    text = pathlib.Path(path).read_text()\n"
        "    return text.splitlines()\n",
    ),
    "crew-json-duplicate-keys": Canary(
        "crew-json-duplicate-keys",
        "{dir}/canary_json.py",
        "import json\nimport pathlib\n\n\ndef canary_{token}(path):\n    raw = pathlib.Path(path).read_text()\n"
        "    return json.loads(raw)\n",
    ),
    "crew-bare-interpreter": Canary(
        "crew-bare-interpreter",
        "{dir}/canary_interpreter.py",
        "import subprocess\n\n\ndef canary_{token}():\n"
        '    return subprocess.run(["python3", "-c", "pass"], check=False)\n',
    ),
    "crew-unquoted-plugin-root": Canary(
        "crew-unquoted-plugin-root",
        "{dir}/canary-root.md",
        "Run it:\n\npython3 $CLAUDE_PLUGIN_ROOT/scripts/canary_{token}.py\n",
    ),
    "crew-test-no-assertion": Canary(
        "crew-test-no-assertion",
        "{dir}/tests/test_canary.py",
        "def test_canary_{token}():\n    value = 1\n    print(value)\n",
    ),
}
