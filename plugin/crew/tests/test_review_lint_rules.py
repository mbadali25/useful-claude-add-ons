"""The rule-file reader for the stdlib review-finding checker (L-0931, L-0715 PR B1).

`review_lint_rules.read_rules` reads PR A's `plugin/crew/lint/semgrep/crew-classes.yml` and refuses
every shape it does not know. A reader that skips a line it does not understand turns a changed rule
into a silent pass (GEN-01), so the refusal table below is the control: each row is a mutation of the
real file, built with `_mutated`, which fails loudly when its anchor text has moved.
"""

import pathlib
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_lint_rules as rlr

ROOT = pathlib.Path(__file__).resolve().parents[3]
REAL = ROOT / "plugin" / "crew" / "lint" / "semgrep" / "crew-classes.yml"
BASE = REAL.read_text(encoding="utf-8")

IDS = (
    "crew-splitlines-untrusted-text",
    "crew-json-duplicate-keys",
    "crew-bare-interpreter",
    "crew-unquoted-plugin-root",
    "crew-test-no-assertion",
)
TESTS_EXCLUDE = ("**/tests/**", "**/_test/**", "**/test_*.py", "**/lint/semgrep/fixtures/**")


def _mutated(tmp_path, old, new, text=None, name="rules.yml"):
    source = BASE if text is None else text
    assert source.count(old) >= 1, "mutation anchor moved in crew-classes.yml: " + repr(old)
    path = tmp_path / name
    path.write_bytes(source.replace(old, new, 1).encode("utf-8"))
    return path


def _line_of(path, needle):
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if needle in line:
            return number
    raise AssertionError(needle + " not in the mutated file")


def _only(rules, rule_id):
    return next(rule for rule in rules.rules if rule.id == rule_id)


def test_reads_pr_a_rule_file():
    rules = rlr.read_rules(REAL)

    assert rules.ids == IDS
    assert [rule.rule_class for rule in rules.rules] == [
        "u2028-line-protocol",
        "duplicate-key-json",
        "bare-executable",
        "unquoted-plugin-root",
        "test-no-assertion",
    ]
    assert [rule.mode for rule in rules.rules] == ["taint", "taint", "", "", ""]
    assert {rule.severity for rule in rules.rules} == {"WARNING"}
    assert _only(rules, "crew-bare-interpreter").languages == ("python",)
    assert _only(rules, "crew-unquoted-plugin-root").languages == ("generic",)
    assert _only(rules, "crew-splitlines-untrusted-text").standards == ("GEN-06",)
    assert _only(rules, "crew-splitlines-untrusted-text").include == ()
    assert _only(rules, "crew-splitlines-untrusted-text").exclude == TESTS_EXCLUDE
    assert _only(rules, "crew-unquoted-plugin-root").include == ("*.md",)
    assert _only(rules, "crew-test-no-assertion").include == ("**/tests/**", "**/_test/**", "**/test_*.py")
    assert _only(rules, "crew-splitlines-untrusted-text").message.startswith(
        "str.splitlines() on text read from a file, stdin or a child process also splits on U+2028, U+2029"
    )
    assert "\\x1c-\\x1e" in _only(rules, "crew-splitlines-untrusted-text").message
    assert "\n" not in _only(rules, "crew-splitlines-untrusted-text").message
    assert list(rules.not_shipped) == ["symlink-fifo-open"]
    assert rules.not_shipped["symlink-fifo-open"].startswith("open flags are built in variables")


def test_reads_the_five_executed_regexes():
    rules = rlr.read_rules(REAL)

    assert _only(rules, "crew-bare-interpreter").regexes == {
        "metavariable-regex:$G": "^(run|Popen|call|check_call|check_output)$",
        "metavariable-regex:$E": "^[rRbBuU]?[\"'](pwsh|powershell|python3?|py)[\"']$",
    }
    assert _only(rules, "crew-unquoted-plugin-root").regexes == {
        "pattern-regex": r"(?:python3?|bash|sh|node|pwsh|source)(?:[ \t]+-[A-Za-z]+)*[ \t]+\$\{?CLAUDE_PLUGIN_ROOT",
    }
    assert _only(rules, "crew-test-no-assertion").regexes == {
        "metavariable-regex:$T": "^test_",
        "pattern-not-regex": (
            r"(?<!\w)assert\b|(?<!def )(?<!def\s)\b\w*assert\w*\("
            r"|(?<!\w)(raises|fail|check|expect|ok)\("
        ),
    }
    assert _only(rules, "crew-splitlines-untrusted-text").regexes == {}
    assert _only(rules, "crew-json-duplicate-keys").regexes == {}


REFUSALS = [
    pytest.param(
        "    severity: WARNING\n",
        "    severity: WARNING\n    bogus: 1\n",
        "bogus",
        "crew-splitlines-untrusted-text",
        id="extra-key",
    ),
    pytest.param(
        "    severity: WARNING\n    mode: taint\n",
        "    mode: taint\n",
        "",
        "crew-splitlines-untrusted-text",
        id="missing-key",
    ),
    pytest.param(
        "    languages: [python]\n",
        "\tlanguages: [python]\n",
        "tab in the indentation",
        "crew-splitlines-untrusted-text",
        id="tab-indent",
    ),
    pytest.param(
        "    severity: WARNING\n",
        "    severity: &level WARNING\n",
        "&level",
        "crew-splitlines-untrusted-text",
        id="anchor",
    ),
    pytest.param(
        "      - pattern: sys.stdin\n",
        "      - pattern: &anchor sys.stdin\n",
        "anchor",
        "crew-splitlines-untrusted-text",
        id="anchor-in-pattern-block",
    ),
    pytest.param(
        "      - pattern: sys.stdin\n",
        "      - pattern: *anchor\n",
        "alias",
        "crew-splitlines-untrusted-text",
        id="alias-in-pattern-block",
    ),
    pytest.param(
        "      - pattern: sys.stdin\n",
        "      - <<: sys.stdin\n",
        "merge key",
        "crew-splitlines-untrusted-text",
        id="merge-key-in-pattern-block",
    ),
    pytest.param(
        "    languages: [python]\n    severity: WARNING\n    mode: taint\n",
        "    languages: [python\n    severity: WARNING\n    mode: taint\n",
        "flow list",
        "crew-splitlines-untrusted-text",
        id="unterminated-bare-flow-list",
    ),
    pytest.param(
        "    severity: WARNING\n", "    severity: *level\n", "*level", "crew-splitlines-untrusted-text", id="alias"
    ),
    pytest.param(
        "    severity: WARNING\n", "    severity: !!str WARNING\n", "!!str", "crew-splitlines-untrusted-text", id="tag"
    ),
    pytest.param(
        "  - id: crew-json-duplicate-keys\n",
        "  - id: crew-splitlines-untrusted-text\n",
        "duplicate rule id",
        "crew-splitlines-untrusted-text",
        id="duplicate-id",
    ),
    pytest.param(
        "    severity: WARNING\n",
        "    severity: WARNING\n    severity: ERROR\n",
        "duplicate key",
        "crew-splitlines-untrusted-text",
        id="duplicate-key",
    ),
    pytest.param(
        'exclude: ["**/tests/**", "**/_test/**", "**/test_*.py", "**/lint/semgrep/fixtures/**"]\n    pattern-sources:',
        'exclude: ["**/tests/**"\n    pattern-sources:',
        "flow list",
        "crew-splitlines-untrusted-text",
        id="unterminated-flow-list",
    ),
    pytest.param(
        '"**/_test/**"', '"**/_te\\st/**"', "unknown escape", "crew-splitlines-untrusted-text", id="unknown-escape"
    ),
    pytest.param(
        "    message: >-\n      A bare interpreter",
        "    message: |\n      A bare interpreter",
        "folded",
        "crew-bare-interpreter",
        id="literal-message",
    ),
    pytest.param(
        "    mode: taint\n    message",
        "    mode: taint\n    message: plain\n    message",
        "duplicate key",
        "crew-splitlines-untrusted-text",
        id="second-message",
    ),
    pytest.param(
        "    pattern-regex: '(?:python3?",
        '    pattern-regex: "(?:python3?',
        "single-quoted",
        "crew-unquoted-plugin-root",
        id="double-quoted-regex",
    ),
    pytest.param(
        "          regex: '^test_'",
        "          regex: ^test_",
        "single-quoted",
        "crew-test-no-assertion",
        id="plain-regex",
    ),
    pytest.param(
        "      - metavariable-regex:\n          metavariable: $T\n          regex: '^test_'\n",
        "      - metavariable-regex:\n          metavariable: $T\n",
        "metavariable",
        "crew-test-no-assertion",
        id="metavariable-without-regex",
    ),
    pytest.param(
        "      class: bare-executable",
        "      class: Bare_Executable",
        "metadata.class",
        "crew-bare-interpreter",
        id="class-shape",
    ),
    pytest.param(
        "      class: bare-executable\n",
        "      class: bare-executable\n      color: red\n",
        "color",
        "crew-bare-interpreter",
        id="extra-metadata-key",
    ),
    pytest.param("  - id: crew-bare-interpreter\n", "  - id: crew bare\n", "plain word", "", id="id-shape"),
    pytest.param("rules:\n", "rules:\nextra: 1\n", "", "", id="top-level-key-after-rules"),
    pytest.param(
        "# not-shipped:\n", "# not-shipped:\n#   Bad_Class: reason\n", "entry", "", id="malformed-not-shipped-entry"
    ),
]


@pytest.mark.parametrize("old,new,expected,rule_id", REFUSALS)
def test_unknown_shapes_are_refused(tmp_path, old, new, expected, rule_id):
    path = _mutated(tmp_path, old, new)

    with pytest.raises(rlr.RuleFileError) as excinfo:
        rlr.read_rules(path)

    assert expected in str(excinfo.value)
    assert rule_id in str(excinfo.value)
    assert excinfo.value.line >= 1


@pytest.mark.parametrize(
    "old,new,needle",
    [
        ("    severity: WARNING\n", "    severity: WARNING\n    bogus: 1\n", "bogus: 1"),
        ("    languages: [python]\n", "\tlanguages: [python]\n", "\tlanguages"),
        ("    severity: WARNING\n", "    severity: &level WARNING\n", "&level"),
        (
            "  - id: crew-json-duplicate-keys\n",
            "  - id: crew-splitlines-untrusted-text\n",
            "id: crew-splitlines-untrusted-text\n",
        ),
    ],
)
def test_refusal_names_the_offending_line(tmp_path, old, new, needle):
    path = _mutated(tmp_path, old, new)
    wanted = [
        n for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1) if needle.strip("\n") in line
    ][-1]

    with pytest.raises(rlr.RuleFileError) as excinfo:
        rlr.read_rules(path)

    assert excinfo.value.line == wanted


def test_symlinked_rule_file_is_refused(tmp_path):
    target = tmp_path / "real.yml"
    target.write_bytes(BASE.encode("utf-8"))
    link = tmp_path / "link.yml"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks cannot be created on this host")

    with pytest.raises(rlr.RuleFileError, match="rule file is a symlink"):
        rlr.read_rules(link)


def test_directory_and_missing_file_are_refused(tmp_path):
    with pytest.raises(rlr.RuleFileError):
        rlr.read_rules(tmp_path)

    with pytest.raises(rlr.RuleFileError, match="cannot read"):
        rlr.read_rules(tmp_path / "absent.yml")


@pytest.mark.parametrize("content", [b"", b"   \n\n", b"\xef\xbb\xbf"])
def test_empty_file_is_refused_as_empty(tmp_path, content):
    path = tmp_path / "rules.yml"
    path.write_bytes(content)

    with pytest.raises(rlr.RuleFileError, match="is empty"):
        rlr.read_rules(path)


@pytest.mark.parametrize(
    "content", [b"", b"   \n\n", b"\xef\xbb\xbf", b"# only a comment\n", b"rules:\n", b"\xff\xfe broken"]
)
def test_empty_or_ruleless_file_is_refused(tmp_path, content):
    path = tmp_path / "rules.yml"
    path.write_bytes(content)

    with pytest.raises(rlr.RuleFileError):
        rlr.read_rules(path)


@pytest.mark.parametrize("bad", ["\r", "\x00"])
@pytest.mark.parametrize("where", ["a comment line", "a value"])
def test_lone_carriage_return_and_nul_are_refused(tmp_path, bad, where):
    if where == "a comment line":
        path = _mutated(tmp_path, "# Opt-in:", "# note" + bad + "x\n# Opt-in:")
    else:
        path = _mutated(tmp_path, "    severity: WARNING\n", "    severity: WARNING" + bad + "X\n")

    with pytest.raises(rlr.RuleFileError):
        rlr.read_rules(path)


def test_reader_never_returns_a_partial_rule_set(tmp_path):
    path = _mutated(tmp_path, "          regex: '^test_'", "          regex: '^test_")
    result = []

    with pytest.raises(rlr.RuleFileError):
        result.append(rlr.read_rules(path))

    assert result == []


def test_crlf_and_bom_read_the_same_as_lf(tmp_path):
    plain = rlr.read_rules(REAL)
    crlf = tmp_path / "crlf.yml"
    crlf.write_bytes(b"\xef\xbb\xbf" + BASE.replace("\n", "\r\n").encode("utf-8"))

    assert rlr.read_rules(crlf) == plain


def test_u2028_inside_a_message_does_not_move_a_line_number(tmp_path):
    path = _mutated(tmp_path, "forged by one stray", "forged\u2028by one stray")
    bad = _mutated(
        tmp_path,
        "    severity: WARNING\n    mode: taint\n    message: >-\n      str.splitlines",
        "    severity: WARNING\n\u2028   mode: taint\n    message: >-\n      str.splitlines",
        name="bad.yml",
    )

    rules = rlr.read_rules(path)

    assert "\u2028" in _only(rules, "crew-splitlines-untrusted-text").message
    with pytest.raises(rlr.RuleFileError) as excinfo:
        rlr.read_rules(bad)
    assert excinfo.value.line == _line_of(bad, "\u2028   mode")


def test_fingerprint_changes_when_a_pattern_changes_and_not_when_the_message_does(tmp_path):
    base = rlr.read_rules(REAL)
    pattern = rlr.read_rules(
        _mutated(tmp_path, "- pattern: $X.splitlines(...)", "- pattern: $X.splitlines()", name="p.yml")
    )
    message = rlr.read_rules(_mutated(tmp_path, 'Split on "\\n"', "Split on newline", name="m.yml"))
    severity = rlr.read_rules(_mutated(tmp_path, "severity: WARNING", "severity: ERROR", name="s.yml"))
    metadata = rlr.read_rules(_mutated(tmp_path, "standards: [GEN-06]", "standards: [GEN-06, GEN-07]", name="d.yml"))
    paths = rlr.read_rules(_mutated(tmp_path, '["*.md"]', '["*.md", "*.txt"]', name="x.yml"))

    changed = {rule.id for rule in pattern.rules if rule.fingerprint != _only(base, rule.id).fingerprint}
    assert changed == {"crew-splitlines-untrusted-text"}
    assert (
        _only(message, "crew-splitlines-untrusted-text").message
        != _only(base, "crew-splitlines-untrusted-text").message
    )
    for untouched in (message, severity, metadata, paths):
        assert [rule.fingerprint for rule in untouched.rules] == [rule.fingerprint for rule in base.rules]


REGEX_EDITS = [
    ("crew-test-no-assertion", "metavariable-regex:$T", "regex: '^test_'", "regex: '^check_'"),
    ("crew-test-no-assertion", "pattern-not-regex", "(?<!\\w)assert\\b|", "(?<!\\w)verify\\b|"),
    ("crew-unquoted-plugin-root", "pattern-regex", "(?:python3?|bash|", "(?:python3?|zsh|"),
    ("crew-bare-interpreter", "metavariable-regex:$G", "^(run|Popen|", "^(run|Popen|exec|"),
]


@pytest.mark.parametrize("rule_id,key,old,new", REGEX_EDITS)
def test_fingerprint_ignores_regex_values(tmp_path, rule_id, key, old, new):
    base = rlr.read_rules(REAL)

    edited = rlr.read_rules(_mutated(tmp_path, old, new))

    assert _only(edited, rule_id).regexes[key] != _only(base, rule_id).regexes[key]
    assert _only(edited, rule_id).fingerprint == _only(base, rule_id).fingerprint


def test_fingerprint_changes_when_a_regex_moves_to_another_metavariable(tmp_path):
    base = rlr.read_rules(REAL)

    moved = rlr.read_rules(_mutated(tmp_path, "          metavariable: $T\n", "          metavariable: $U\n"))

    assert _only(moved, "crew-test-no-assertion").fingerprint != _only(base, "crew-test-no-assertion").fingerprint


def test_fingerprint_changes_on_an_indentation_only_change(tmp_path):
    base = rlr.read_rules(REAL)
    shifted = rlr.read_rules(
        _mutated(tmp_path, "          - pattern-not-inside: ($X", "            - pattern-not-inside: ($X")
    )

    assert (
        _only(shifted, "crew-splitlines-untrusted-text").fingerprint
        != _only(base, "crew-splitlines-untrusted-text").fingerprint
    )
    assert _only(shifted, "crew-json-duplicate-keys").fingerprint == _only(base, "crew-json-duplicate-keys").fingerprint


def test_reader_accepts_old_and_new_shape_files(tmp_path):
    old = rlr.read_rules(REAL)
    new = rlr.read_rules(
        _mutated(
            tmp_path,
            "- pattern: sys.stdin\n    pattern-sinks",
            "- pattern: sys.stdin\n      - pattern: input()\n    pattern-sinks",
        )
    )

    assert new.ids == old.ids
    assert (
        _only(new, "crew-splitlines-untrusted-text").fingerprint
        != _only(old, "crew-splitlines-untrusted-text").fingerprint
    )


def test_comments_and_blank_lines_between_rules_are_skipped(tmp_path):
    path = _mutated(
        tmp_path,
        "\n  - id: crew-bare-interpreter",
        "\n# a note about the next rule\n\n  # indented note\n  - id: crew-bare-interpreter",
    )

    assert rlr.read_rules(path).ids == IDS


@pytest.mark.parametrize(
    "header,expected",
    [
        ("# not-shipped:\n#   a-b: reason one\n#   c: reason two\n", {"a-b": "reason one", "c": "reason two"}),
        ("# not-shipped:\n#   a-b: reason one\n#\n#   c: after the bare hash\n", {"a-b": "reason one"}),
        ("# not-shipped:\n\n#   a-b: after a blank line\n", {}),
        ("# not-shipped:\n# prose with one space\n", {}),
        ("# nothing here\n", {}),
    ],
)
def test_not_shipped_header_grammar(tmp_path, header, expected):
    path = tmp_path / "rules.yml"
    path.write_bytes((header + BASE[BASE.index("rules:\n") :]).encode("utf-8"))

    assert rlr.read_rules(path).not_shipped == expected


@pytest.mark.parametrize(
    "header",
    [
        "# not-shipped:\n#   Upper: reason\n",
        "# not-shipped:\n#   a-b:\n",
        "# not-shipped:\n#   a-b: one\n#   a-b: two\n",
        "# not-shipped:\n#   a-b: one\n#    deeper: two\n",
        "# not-shipped:\n#   a-b: one\n# not-shipped:\n",
        "# not-shipped: inline\n",
    ],
)
def test_not_shipped_header_refuses_what_it_cannot_read(tmp_path, header):
    path = tmp_path / "rules.yml"
    path.write_bytes((header + BASE[BASE.index("rules:\n") :]).encode("utf-8"))

    with pytest.raises(rlr.RuleFileError):
        rlr.read_rules(path)


def test_not_shipped_header_after_rules_is_refused(tmp_path):
    path = _mutated(tmp_path, "\n  - id: crew-bare-interpreter", "\n# not-shipped:\n  - id: crew-bare-interpreter")

    with pytest.raises(rlr.RuleFileError, match="above `rules:`"):
        rlr.read_rules(path)


SCOPE_TABLE = {
    "**/tests/**": (
        ["tests/a.py", "plugin/crew/tests/a.py", "a/tests/b/c.py"],
        ["tests", "plugin/crew/contests/a.py", "a/tests.py", "a/b.py"],
    ),
    "**/_test/**": (["scripts/_test/x.sh", "_test/x.py"], ["scripts/test/x.sh", "a/_tests/x.py"]),
    "**/test_*.py": (
        ["test_a.py", "plugin/test_a.py", "a/b/test_.py"],
        ["a/atest_a.py", "test_a.pyc", "a/test_a.md", "test_a.py/b.py"],
    ),
    "**/lint/semgrep/fixtures/**": (
        ["plugin/crew/lint/semgrep/fixtures/r/pos.py", "lint/semgrep/fixtures/x.md"],
        ["plugin/crew/lint/semgrep/crew-classes.yml", "lint/semgrep/fixtures", "x/lint/fixtures/a.py"],
    ),
    "*.md": (
        ["README.md", "docs/a/b.md", "plugin/crew/commands/x.md"],
        ["a.md.txt", "docs/md", "a.mdx", "docs/md/readme"],
    ),
}


def test_matches_scope_agrees_with_every_paths_entry_in_the_real_file():
    rules = rlr.read_rules(REAL)
    entries = {entry for rule in rules.rules for entry in rule.include + rule.exclude}

    assert entries == set(SCOPE_TABLE), (
        "a paths entry has no row in SCOPE_TABLE; add its must-match and must-miss paths"
    )
    for entry, (hits, misses) in SCOPE_TABLE.items():
        for path in hits:
            assert rlr.matches_scope(path, (entry,), ()), (entry, path)
            assert not rlr.matches_scope(path, (), (entry,)), (entry, path)
        for path in misses:
            assert not rlr.matches_scope(path, (entry,), ()), (entry, path)
            assert rlr.matches_scope(path, (), (entry,)), (entry, path)


@pytest.mark.parametrize(
    "rule_id,path,expected",
    [
        ("crew-splitlines-untrusted-text", "plugin/crew/hooks/scripts/review_run.py", True),
        ("crew-splitlines-untrusted-text", "plugin/crew/tests/test_x.py", False),
        ("crew-splitlines-untrusted-text", "scripts/_test/helper.py", False),
        (
            "crew-splitlines-untrusted-text",
            "plugin/crew/lint/semgrep/fixtures/crew-splitlines-untrusted-text/positive.py",
            False,
        ),
        ("crew-unquoted-plugin-root", "plugin/crew/commands/review.md", True),
        ("crew-unquoted-plugin-root", "plugin/crew/hooks/scripts/review_run.py", False),
        ("crew-unquoted-plugin-root", "plugin/crew/lint/semgrep/fixtures/x/a.md", False),
        ("crew-test-no-assertion", "plugin/crew/tests/helper.py", True),
        ("crew-test-no-assertion", "test_top.py", True),
        ("crew-test-no-assertion", "plugin/crew/hooks/scripts/review_run.py", False),
        ("crew-test-no-assertion", "plugin/crew/tests/README.md", True),
    ],
)
def test_matches_scope_uses_a_rules_own_include_and_exclude(rule_id, path, expected):
    rule = _only(rlr.read_rules(REAL), rule_id)

    assert rlr.matches_scope(path, rule.include, rule.exclude) is expected


@pytest.mark.parametrize(
    "bad", ["/etc/x.py", "C:/x.py", "c:x.py", "C:\\x.py", "a\\b.py", "../x.py", "a/../b.py", "a//b.py", "", "a/"]
)
def test_scope_refuses_absolute_and_drive_letter_paths(bad):
    with pytest.raises(ValueError):
        rlr.matches_scope(bad, (), ())


def test_every_canary_belongs_to_a_shipped_rule_and_sits_in_its_scope():
    rules = rlr.read_rules(REAL)

    assert set(rlr.CANARIES) == set(rules.ids)
    for rule in rules.rules:
        canary = rlr.CANARIES[rule.id]
        path, source = canary.render("canary-ab12cd", "0a1b2c3d4e5f")
        assert canary.rule_id == rule.id
        assert "canary-ab12cd" in path
        assert "0a1b2c3d4e5f" in source
        assert "{" not in path and "{token}" not in source
        assert rlr.matches_scope(path, rule.include, rule.exclude), rule.id


def test_canary_paths_are_python_or_markdown_files_for_the_rules_language():
    for rule_id, canary in rlr.CANARIES.items():
        path, _ = canary.render("canary-ab12cd", "0a1b2c3d4e5f")
        assert path.endswith(".md" if rule_id == "crew-unquoted-plugin-root" else ".py"), rule_id


@pytest.mark.parametrize(
    "directory,token",
    [("Tests/x", "0a1b2c3d"), ("", "0a1b2c3d"), ("ok", "abc"), ("ok", "ABCDEF12"), ("../x", "0a1b2c3d")],
)
def test_canary_render_refuses_a_directory_or_token_of_the_wrong_shape(directory, token):
    with pytest.raises(ValueError):
        rlr.CANARIES["crew-bare-interpreter"].render(directory, token)


def test_canary_regexes_hit_the_regex_canaries():
    rules = rlr.read_rules(REAL)
    root_rule = _only(rules, "crew-unquoted-plugin-root")
    root = rlr.CANARIES["crew-unquoted-plugin-root"].render("canary-ab12cd", "0a1b2c3d4e5f")[1]
    test_rule = _only(rules, "crew-test-no-assertion")
    test_source = rlr.CANARIES["crew-test-no-assertion"].render("canary-ab12cd", "0a1b2c3d4e5f")[1]

    assert re.search(root_rule.regexes["pattern-regex"], root)
    assert re.search(test_rule.regexes["metavariable-regex:$T"], "test_canary_0a1b2c3d4e5f")
    assert not re.search(test_rule.regexes["pattern-not-regex"], test_source)
