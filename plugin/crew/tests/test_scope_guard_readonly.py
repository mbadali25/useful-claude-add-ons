"""scope_guard's fail-closed read-only exemption (`_read_only`, `_simple_commands`).

The guard's word list is a deny-list: a command naming crew's state beside
`echo`, `python3`, `cp` ... is refused. The one exemption is a command that
`_read_only` parses completely into simple commands of a small set of
read-only programs with plain literal words. So `ls <state> | grep python3` is
allowed, and everything else keeps the deny-list verdict.

Two checked-in corpora back it: `data/scope_guard_corpus.json` holds every write
form crew 1.3.75 (origin/main) refused (`must_block`: this guard must refuse
every one, so the exemption can never allow a write the old guard refused), the
write forms it already allowed (`residual_allowed`, known gaps, not asserted)
and the read-only forms the exemption allows (`must_allow`).
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import scope_guard

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "data", "scope_guard_corpus.json"), encoding="utf-8") as _fh:
    CORPUS = json.load(_fh)

COMMON, TOP = "/repo/.git", "/repo"
S = "/repo/.git/crew"
STORE = "confirm-config/"


def refusal(command):
    return scope_guard.shell_refusal(command, COMMON, TOP)


ALLOWED = [
    pytest.param(f"ls {S}", id="ls"),
    pytest.param(f"ls -la {S}/approvals", id="ls-la"),
    pytest.param(f"find {S} -name 'python3*'", id="find-name-python3"),
    pytest.param(f"find {S} -name '*.json' -type f", id="find-name-json"),
    pytest.param(f"ls {S} | grep python3", id="ls-pipe-grep-python3"),
    pytest.param(f"ls {S} | grep echo", id="ls-pipe-grep-echo"),
    pytest.param(f"grep -r echo {S}", id="grep-r-echo"),
    pytest.param(f"grep -rn 'python3' {S}/tickets", id="grep-rn-quoted"),
    pytest.param(f"cat {S}/x 2>/dev/null", id="cat-stderr-null"),
    pytest.param(f"cat {S}/x 2>&1 | head -3", id="cat-stderr-to-stdout"),
    pytest.param(f"head -5 {S}/ledger.jsonl", id="head"),
    pytest.param(f"tail -n 3 {S}/ledger.jsonl", id="tail"),
    pytest.param(f"wc -l {S}/ledger.jsonl", id="wc"),
    pytest.param(f"stat {S}/x", id="stat"),
    pytest.param(f"find {S} -name 'python3*' -type f -print", id="find-name-type-print"),
    pytest.param(f"find {S} -maxdepth 2 -name x -o -name y", id="find-or"),
    pytest.param(f"head -n 5 {S}/x | tail -3", id="head-n-tail"),
    pytest.param(f"tail -n3 {S}/x | wc -l", id="tail-attached-count"),
    pytest.param(f"stat -c %n {S}/x", id="stat-format"),
    pytest.param(f"grep -rie python3 {S}", id="grep-cluster-with-e"),
    pytest.param(f"grep --include='*.json' --color=never -rn echo {S}", id="grep-include"),
    pytest.param(f"grep -- -x {S}/y", id="grep-double-dash"),
    pytest.param(f"ls \"{S}\" | egrep 'a|b' | fgrep x", id="double-quoted-egrep-fgrep"),
    pytest.param(f"ls {STORE}", id="ls-the-confirm-store"),
    pytest.param(f"grep echo {STORE}x", id="grep-echo-in-the-confirm-store"),
]


@pytest.mark.parametrize("command", ALLOWED)
def test_a_read_only_listing_of_crews_state_is_allowed(command):
    assert refusal(command) is None


@pytest.mark.parametrize("command", ALLOWED)
def test_every_allowed_form_is_wholly_read_only(command):
    # The deny-list verdict alone could allow these; the exemption must too.
    assert scope_guard._read_only(command) is True


@pytest.mark.parametrize("command", CORPUS["must_allow"])
def test_the_corpus_read_only_forms_are_allowed(command):
    assert refusal(command) is None


@pytest.mark.parametrize("command", CORPUS["must_block"])
def test_no_write_form_the_old_guard_refused_is_allowed(command):
    assert refusal(command) is not None


def test_the_corpus_has_its_size():
    assert (len(CORPUS["must_block"]) >= 380, len(CORPUS["must_allow"]) >= 50) == (True, True)


# Everything below names crew's state and must keep the deny-list verdict.
REFUSED = [
    pytest.param(f"echo hi {S}", id="echo-stays-refused"),
    pytest.param(f"printf x {S}", id="printf-stays-refused"),
    pytest.param(f"python3 -c \"print(open('{S}/x').read())\"", id="python-c-stays-refused"),
    pytest.param(f"ls {S} > {S}/x", id="redirect-out"),
    pytest.param(f"ls {S} >> {S}/x", id="redirect-append"),
    pytest.param(f"cat {S}/x 2> {S}/y", id="stderr-to-a-file"),
    pytest.param(f"cat < {S}/x", id="redirect-in"),
    pytest.param(f"cat <<EOF\n{S}\nEOF", id="heredoc"),
    pytest.param(f"ls {S}; rm {S}/x", id="semicolon-rm"),
    pytest.param(f"ls {S} && rm {S}/x", id="and-rm"),
    pytest.param(f"ls {S} || rm {S}/x", id="or-rm"),
    pytest.param(f"ls {S} | tee {S}/x", id="pipe-tee"),
    pytest.param(f"ls {S} & rm {S}/x", id="background-rm"),
    pytest.param(f"ls {S} |& tee {S}/x", id="pipe-ampersand"),
    pytest.param(f"ls {S}\nrm {S}/x", id="newline-rm"),
    pytest.param(f"ls {S};", id="trailing-semicolon"),
    pytest.param(f"ls {S} | ", id="empty-command"),
    pytest.param(f"ls {S} $(rm {S}/x)", id="command-substitution"),
    pytest.param(f"ls {S} `rm {S}/x`", id="backticks"),
    pytest.param(f"ls \"{S} $(rm {S}/x)\"", id="substitution-in-double-quotes"),
    pytest.param(f"ls \"{S}/$X\" > {S}/x", id="variable-and-redirect"),
    pytest.param(f"ls {S}/* > {S}/x", id="glob-and-redirect"),
    pytest.param(f"ls {S}/*", id="glob"),
    pytest.param(f"ls ~ {S}", id="tilde"),
    pytest.param(f"ls {S} # rm", id="comment"),
    pytest.param(f"ls 'unterminated {S}", id="unterminated-quote"),
    pytest.param(f"A=1 ls {S}", id="env-assignment-prefix"),
    pytest.param(f"'ls' {S}", id="quoted-program"),
    pytest.param(f"/bin/ls {S}", id="program-by-path"),
    pytest.param(f"find {S} $A -name python3", id="variable-word"),
    pytest.param(f"find {S} -delete", id="find-delete"),
    pytest.param(f"find {S} -exec ls +", id="find-exec-plus"),
    pytest.param(f"find {S} -execdir ls +", id="find-execdir-plus"),
    pytest.param(f"find {S} -ok ls +", id="find-ok-plus"),
    pytest.param(f"find {S} -okdir ls +", id="find-okdir-plus"),
    pytest.param(f"find {S} -exec rm {{}} ;", id="find-exec"),
    pytest.param(f"find {S} -execdir rm {{}} ;", id="find-execdir"),
    pytest.param(f"find {S} -ok rm {{}} ;", id="find-ok"),
    pytest.param(f"find {S} -fprint {S}/x", id="find-fprint"),
    pytest.param(f"find {S} -fprintf {S}/x x", id="find-fprintf"),
    pytest.param(f"find {S} -fls {S}/x", id="find-fls"),
    pytest.param(f"sort -o {S}/x /tmp/a", id="sort-o"),
    pytest.param(f"sort -ro {S}/x /tmp/a", id="sort-ro"),
    pytest.param(f"sort --output={S}/x /tmp/a", id="sort-output"),
    pytest.param(f"sort --out {S}/x /tmp/a", id="sort-output-abbreviated"),
    pytest.param(f"sort --compress-program=sh {S}/x", id="sort-compress-program"),
    pytest.param(f"sort -T {S} /tmp/a", id="sort-temp-dir"),
    pytest.param(f"uniq /tmp/a {S}/x", id="uniq-output-file"),
    pytest.param(f"uniq - {S}/python3", id="uniq-stdin-dash-then-output"),
    pytest.param(f"uniq -c - {S}/echo", id="uniq-c-dash-output"),
    pytest.param(f"uniq -- - {S}/python3", id="uniq-double-dash-dash-output"),
    pytest.param(f"uniq -- -x {S}/python3", id="uniq-double-dash-dashname-output"),
    pytest.param(f"uniq -- -f {S}/python3", id="uniq-double-dash-f-output"),
    pytest.param(f"uniq -s 1 - {S}/python3", id="uniq-s-dash-output"),
    pytest.param(f"uniq -w1 - {S}/python3", id="uniq-w1-dash-output"),
    pytest.param(f"uniq --skip-fields=1 - {S}/python3", id="uniq-skip-fields-dash-output"),
    pytest.param(f"uniq -u - {S}/python3", id="uniq-u-dash-output"),
    pytest.param(f"uniq -i - {S}/python3", id="uniq-i-dash-output"),
    pytest.param(f"uniq --all-repeated - {S}/python3", id="uniq-all-repeated-dash-output"),
    pytest.param(f"sort {S}/x | uniq - {S}/python3", id="uniq-in-a-pipeline"),
    pytest.param(f"uniq {S}/x", id="uniq-alone-is-not-allowlisted"),
    pytest.param(f"sort -o{S}/x /tmp/a", id="sort-oFILE"),
    pytest.param(f"sort --o={S}/x /tmp/a", id="sort-short-long-abbrev"),
    pytest.param("sort -u -o /tmp/a /tmp/a", id="sort-u-o"),
    pytest.param(f"sort -S 1M -T {S} /tmp/a", id="sort-S-T"),
    pytest.param(f"sort --temporary-directory={S} /tmp/a", id="sort-temporary-directory"),
    pytest.param(f"file -Cm {S}/x", id="file-Cm-cluster"),
    pytest.param(f"find {S} -fprint0 {S}/x", id="find-fprint0"),
    pytest.param(f"find {S} -name x -delete", id="find-name-delete"),
    pytest.param(f"file -C -m {S}/x", id="file-compile"),
    pytest.param(f"file --compile {S}/x", id="file-compile-long"),
    pytest.param(f"sed -i s/a/b/ {S}/x", id="sed-i"),
    pytest.param(f"cp /tmp/a {S}/x", id="cp"),
]


@pytest.mark.parametrize("command", REFUSED)
def test_a_command_outside_the_strict_allowlist_is_never_exempt(command):
    assert scope_guard._read_only(command) is False


# find -delete, sort -o and the like name no word on the deny-list: origin/main
# allowed them too (residual_allowed), so only the rest is judged.
@pytest.mark.parametrize("command", [
    p for p in REFUSED if scope_guard._WRITES_RE.search(p.values[0])])
def test_a_refused_command_naming_a_writing_word_keeps_the_deny_list_verdict(command):
    assert refusal(command) is not None


@pytest.mark.parametrize("command", [
    pytest.param(f"ls {STORE} > x", id="redirect"),
    pytest.param(f"ls {STORE}; rm {STORE}x", id="semicolon-rm"),
    pytest.param(f"echo x {STORE}", id="echo"),
    pytest.param(f"ls {STORE}$(rm x)", id="substitution"),
])
def test_the_confirm_config_store_keeps_the_same_verdicts(command):
    assert refusal(command) is not None


# Unchanged from origin/main: a quoted `--last-command` value is still read as
# the approve verb, chained approve and `goal-approve` stay refused. The strict
# allowlist never applies to these (an approve is refused before it is reached).
@pytest.mark.parametrize("command", [
    pytest.param("python3 crew_autopilot.py next --last-command 'approve'", id="last-command"),
    pytest.param("echo \"--last-command 'x\" ; python3 crew_autopilot.py approve "
                 "--ticket T-1 ; echo \"'\"", id="quote-trick-chained-approve"),
    pytest.param("ls x && python3 crew_autopilot.py approve --ticket T-1", id="chained-approve"),
    pytest.param("python3 crew_autopilot.py goal-approve --ticket T-1", id="goal-approve"),
    pytest.param("python3 crew_ticket.py approve --ticket T-1", id="ticket-approve"),
])
def test_approve_forms_stay_refused_exactly_as_on_main(command):
    assert refusal(command) is not None


def test_simple_commands_reads_only_the_documented_shapes():
    ls_a = [("ls", False), ("a", False)]
    assert [scope_guard._simple_commands(c) for c in (
        "ls a", "ls 'a b' | wc -l", "ls a 2>&1", "ls a; ls b && ls c || ls d", "ls $x", "ls a &")
    ] == [[(ls_a, [])],
          [([("ls", False), ("a b", True)], []), ([("wc", False), ("-l", False)], [])],
          [(ls_a, ["2>&1"])],
          [(ls_a, []), ([("ls", False), ("b", False)], []),
           ([("ls", False), ("c", False)], []), ([("ls", False), ("d", False)], [])],
          None, None]


@pytest.mark.parametrize("command,argv,redirects", [
    pytest.param("find . -name 2>/dev/null -name", ["find", ".", "-name", "-name"],
                 ["2>/dev/null"], id="between-a-value-option-and-its-value"),
    pytest.param("2>&1 ls a", ["ls", "a"], ["2>&1"], id="before-the-program"),
    pytest.param("ls -- 2>/dev/null a", ["ls", "--", "a"], ["2>/dev/null"], id="after-double-dash"),
    pytest.param("ls 2>&1 a 2>/dev/null", ["ls", "a"], ["2>&1", "2>/dev/null"], id="two"),
])
def test_a_redirect_word_is_never_part_of_argv(command, argv, redirects):
    ((words, found),) = scope_guard._simple_commands(command)
    assert ([w for w, _ in words], found) == (argv, redirects)


@pytest.mark.parametrize("command", [
    pytest.param("ls '2>/dev/null'", id="quoted-redirect"),
    pytest.param("ls \"2>&1\"", id="double-quoted-redirect"),
    pytest.param("ls 2'>'/dev/null", id="quote-inside-the-redirect"),
    pytest.param("ls x2>/dev/null", id="redirect-glued-to-a-word"),
    pytest.param("ls 22>/dev/null", id="other-descriptor"),
    pytest.param("ls 2>/dev/nullx", id="redirect-target-extended"),
    pytest.param("ls 2>&1x", id="dup-target-extended"),
    pytest.param("2>/dev/null", id="only-a-redirect"),
    pytest.param("ls 2> /dev/null", id="space-after-the-operator"),
    pytest.param("ls 1>/dev/null", id="stdout-redirect"),
])
def test_only_an_unquoted_standalone_redirect_word_is_read(command):
    assert scope_guard._simple_commands(command) is None


# Review round 4 (crew 1.3.86): `_simple_commands` kept `2>/dev/null` and `2>&1` in
# the argument list, so a value option swallowed one and every real argument after
# it shifted by one position. `find ./-name -name 2>/dev/null -name -exec touch X
# '{}' +` read as `-name` taking the redirect and `-name` taking `-exec`; real find
# sees `-name` taking `-name` and `-exec` as an action. The exemption must read
# the argv bash hands the program, so a redirect word is dropped before any option
# check.
_PWN = f"{S}/approvals/PWN"
_FIND_PAYLOADS = ["-delete", f"-fprint {_PWN}", f"-exec touch {_PWN} '{{}}' +",
                  f"-exec rm {_PWN} '{{}}' +", f"-execdir touch {_PWN} '{{}}' +",
                  f"-ok rm {_PWN} '{{}}' ;"]
_FIND_VALUE_OPTIONS = ["-name", "-iname", "-path", "-regex", "-newer", "-user", "-group",
                       "-size", "-perm", "-type", "-maxdepth", "-mtime"]
_REDIRECTS = ["2>/dev/null", "2>&1"]


@pytest.mark.parametrize("redirect", _REDIRECTS)
@pytest.mark.parametrize("payload", _FIND_PAYLOADS)
@pytest.mark.parametrize("option", _FIND_VALUE_OPTIONS)
def test_a_redirect_never_shifts_find_options_into_the_exemption(option, payload, redirect):
    for line in (f"find {S} {option} {redirect} {option} {payload}",
                 f"find ./-name -name {redirect} -name {payload}",
                 f"find {S} {redirect} {option} {option} {payload}",
                 f"{redirect} find {S} {option} {redirect} {option} {payload}",
                 f"find {S} -- {redirect} {option} {option} {payload}"):
        assert not scope_guard._read_only(line), line


@pytest.mark.parametrize("redirect", _REDIRECTS)
@pytest.mark.parametrize("line", [
    "grep -e x {r} -f {S}/x {S}", "grep -e x {r} --pager=sh {S}", "grep --include=x {r} -f x {S}",
    "grep {r} -e x --pager=sh {S}", "head -n 3 {r} -c {S}/x", "head {r} -n {r} -c 3 {S}/x",
    "tail -c {r} -f {S}/x", "tail {r} -f {S}/x", "ls {r} -I x {S}",
    "cat {r} -f {S}",
])
def test_a_redirect_never_hides_an_option_that_is_off_the_allow_list(line, redirect):
    assert not scope_guard._read_only(line.format(r=redirect, S=S))


@pytest.mark.parametrize("line", [
    "ls 2>&1 {S}/x", "grep -rn x {S} 2>/dev/null | head", "cat {S}/x 2>/dev/null",
    "cat 2>/dev/null {S}/x", "head -n 2>&1 3 {S}/x", "tail 2>&1 -n 3 {S}/x",
    "grep -e 2>/dev/null python3 {S}", "find {S} -name 2>/dev/null 'x*' -type f -print",
    "stat -c 2>&1 %n {S}/x", "find {S} 2>&1 -maxdepth 2 -name x -o -name y",
])
def test_a_redirect_is_dropped_from_argv_so_real_reads_stay_exempt(line):
    assert scope_guard._read_only(line.format(S=S))


# The third review round (crew 1.3.82): `test -v 'a[$(cmd)]'` ran cmd (bash
# evaluates the subscript of `test -v`, `[`, `[[`, `printf -v`, `declare`...)
# and bfs, Claude Code's own `find`, has `-rm`. The exemption now lists only ten
# external programs with an allow-list of options, and `$` or a backtick is
# refused even inside single quotes.
_PAYLOAD = f"rm {S}/approvals/T-1.json"
_CP = f"cp /dev/null {S}/ledger.jsonl"
NOT_EXEMPT = [
    pytest.param(f"test -v 'a[$({_PAYLOAD})]'", id="test-v-substitution"),
    pytest.param(f"test -v 'a[$({_CP})]'", id="test-v-cp-substitution"),
    pytest.param(f"test -v 'a[`{_PAYLOAD}`]'", id="test-v-backtick"),
    pytest.param(f"[ -v 'a[$({_PAYLOAD})]' ]", id="bracket-v-substitution"),
    pytest.param(f"[[ -v 'a[$({_PAYLOAD})]' ]]", id="double-bracket-v-substitution"),
    pytest.param(f"printf -v 'a[$({_PAYLOAD})]' x", id="printf-v-substitution"),
    pytest.param(f"test -f {S}/x", id="test-is-not-listed"),
    pytest.param(f"pwd; ls {S}", id="pwd-is-not-listed"),
    pytest.param(f"file {S}/x", id="file-is-not-listed"),
    pytest.param(f"du -sh {S}", id="du-is-not-listed"),
    pytest.param(f"df {S}", id="df-is-not-listed"),
    pytest.param(f"sort {S}/x", id="sort-is-not-listed"),
    pytest.param(f"cut -d, -f1 {S}/x", id="cut-is-not-listed"),
    pytest.param(f"cat {S}/x | tr a b", id="tr-is-not-listed"),
    pytest.param(f"readlink -f {S}", id="readlink-is-not-listed"),
    pytest.param(f"realpath {S}", id="realpath-is-not-listed"),
    pytest.param(f"basename {S}/x", id="basename-is-not-listed"),
    pytest.param(f"dirname {S}/x", id="dirname-is-not-listed"),
    pytest.param(f"grep '{_PAYLOAD}$(x)' {S}/y", id="dollar-in-single-quotes"),
    pytest.param("grep '^x$' /tmp/y", id="regex-anchor-in-single-quotes"),
    pytest.param(f"ls {S} '`x`'", id="backtick-in-single-quotes"),
    pytest.param(f"ls {S} \"`x`\"", id="backtick-in-double-quotes"),
    pytest.param(f"find {S} -name x -rm", id="find-rm"),
    pytest.param(f"find {S} -rm", id="find-rm-bare"),
    pytest.param(f"find {S} -name x -o -rm", id="find-or-rm"),
    pytest.param(f"find {S} -exclude x -rm", id="find-exclude-rm"),
    pytest.param(f"find {S} -hidden", id="find-hidden-is-unknown"),
    pytest.param(f"find {S} -printf x", id="find-printf-is-unknown"),
    pytest.param(f"find {S} -name", id="find-name-without-value"),
    pytest.param(f"find {S} -D exec", id="find-debug-option"),
    pytest.param(f"find {S} -name x -execdir ls +", id="find-execdir-ls"),
    pytest.param(f"grep --pager=less x {S}/y", id="grep-pager"),
    pytest.param(f"grep --pager 'rm x' x {S}/y", id="grep-pager-space"),
    pytest.param(f"grep --filter='*:cat' -r x {S}", id="grep-filter"),
    pytest.param(f"grep --save-config=x -r x {S}", id="grep-save-config"),
    pytest.param(f"grep --config=x -r x {S}", id="grep-config"),
    pytest.param(f"grep -z -r x {S}", id="grep-z"),
    pytest.param(f"grep --decompress x {S}/y", id="grep-decompress"),
    pytest.param(f"grep -f {S}/x -r y {S}", id="grep-f"),
    pytest.param(f"grep --pa=x y {S}/z", id="grep-abbreviated-long"),
    pytest.param(f"grep --color=always x {S}/z", id="grep-color-always"),
    pytest.param("grep -e", id="grep-e-without-value"),
    pytest.param(f"egrep --pager=x y {S}/z", id="egrep-pager"),
    pytest.param(f"fgrep -Q y {S}/z", id="fgrep-Q"),
    pytest.param(f"tail -f {S}/x", id="tail-f"),
    pytest.param(f"tail -F {S}/x", id="tail-F"),
    pytest.param(f"tail --follow {S}/x", id="tail-follow"),
    pytest.param(f"tail -fn 3 {S}/x", id="tail-fn"),
    pytest.param(f"tail --pid=1 {S}/x", id="tail-pid"),
    pytest.param(f"tail -n x {S}/y", id="tail-n-not-a-number"),
    pytest.param(f"head -n -x {S}/y", id="head-n-not-a-number"),
    pytest.param(f"head --lines=x {S}/y", id="head-lines-not-a-number"),
    pytest.param(f"cat -f {S}/x", id="cat-unknown-option"),
    pytest.param(f"ls -I x {S}", id="ls-ignore-takes-a-value"),
    pytest.param(f"ls --time-style=x {S}", id="ls-long-unknown"),
    pytest.param(f"wc --files0-from={S}/x", id="wc-files0-from"),
    pytest.param(f"stat --foo {S}/x", id="stat-unknown-long"),
    pytest.param("stat -c", id="stat-c-without-value"),
]


@pytest.mark.parametrize("command", NOT_EXEMPT)
def test_a_form_outside_the_option_and_program_allow_lists_is_not_exempt(command):
    assert scope_guard._read_only(command) is False


@pytest.mark.parametrize("command", [
    p for p in NOT_EXEMPT if scope_guard._WRITES_RE.search(p.values[0])
    and (S in p.values[0])])
def test_a_not_exempt_form_naming_a_writing_word_is_refused(command):
    assert refusal(command) is not None


def test_the_exempt_programs_are_exactly_these_ten():
    assert sorted(scope_guard._READ_ONLY_PROGRAMS) == sorted((
        "ls", "cat", "head", "tail", "wc", "stat", "grep", "egrep", "fgrep", "find"))
    assert set(scope_guard._OPTION_RULES) | {"find"} == scope_guard._READ_ONLY_PROGRAMS


def test_no_builtin_and_no_bfs_write_primary_is_on_an_allow_list():
    banned = {"-rm", "-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint",
              "-fprint0", "-fprintf", "-fls", "-printf", "-exclude", "-hidden"}
    assert not banned & (scope_guard._FIND_FLAGS | scope_guard._FIND_VALUES)
    for rule in scope_guard._OPTION_RULES.values():
        assert "f" not in rule[0] or rule is scope_guard._OPTION_RULES["stat"]
        assert not {"-f", "-F", "--follow", "--pager", "--filter"} & set(rule[2])
    assert "f" not in scope_guard._OPTION_RULES["tail"][0]
    assert "F" not in scope_guard._OPTION_RULES["tail"][0]
