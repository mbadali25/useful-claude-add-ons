"""crew's workflow-dispatch reader (T-0009): which `gh workflow run` or
`gh api .../dispatches` a Bash or PowerShell line sends, and the environment
`environments.workflows` says each one deploys to.

Split out of `crew_guards` when the T-0009 port onto release/1.2.0 took that
module past `.pylintrc`'s `max-module-lines`: this whole section is one new
subsystem, and it reads `crew_guards`' command-word trigger (T-0005) through
`_DispatchTool` rather than the other way round, so the import runs one way
only. `cloud_guard` imports the public names from here. Standard library only.
"""
from __future__ import annotations

import fnmatch
import json
import re
import unicodedata

from crew_guards import (
    _GATE_CONTROL_RE, _GateReader, _HOLE, _PLAIN_WORD_RE, _PS_LAUNCHERS,
    _Unsure, _bash_trigger, _brace_expand, _head_name, _name_candidates,
    ps_trigger)


# --- workflow dispatches (T-0009) -------------------------------------------
#
# Two spellings of one act: `gh workflow run <wf>` and the REST call it makes,
# `gh api -X POST repos/<o>/<r>/actions/workflows/<wf>/dispatches`. It lives
# here rather than in `cloud_guard.py` for the reason the literal allowlist
# does: that module sits at `.pylintrc`'s max-module-lines, so it keeps only
# the call sites (`_literal_gate`, `_classify`'s `gh` branch, `_judge_one`).
#
# THE DISPATCH GRAMMAR (successor plan, 2026-09-27). Review rounds 1 and 2
# found nine ways past a parser that read what the lexer made of a line --
# stdin rewritten by a filter, a `<` or `0>&3` replacing it, a variable, a
# bracket glob, a script piped into bash -- each a shell construct the lexer
# read differently from bash. T-0005 met the same pattern and answered with
# the literal-word allowlist; this extends it to dispatches. A line the
# trigger (`dispatch_trigger`: T-0005's command-word reader, parametrised by
# `_DispatchTool`) finds sending a dispatch is judged only when
# `dispatch_first_non_literal` accepts every word and operator on it:
#
#     words      `_PLAIN_WORD_RE` words, or a whole single-quoted word `'...'`
#                with no `'` or control character inside (bash and PowerShell
#                both pass it verbatim). PowerShell also refuses `,` and a
#                leading `@`.
#     operators  `;` `&&` `||` `&` and newline between commands; `>` `>>`
#                `&>` `&>>` to a plain word; the exact token `2>&1`.
#
# Everything else -- `|` anywhere, every `<`-family operator, any other
# `N>&M`, `>|`, `<(`/`>(`, double quotes, `$'`, a backslash, `$`, a
# backquote, `*` `?` `[` `]` `{` `}` `~`, a tab or CR in a word, a control
# character -- and a dispatch the lexer is not known to read (inside `bash
# -c`/`eval`/`pwsh -c`, behind `xargs`/`parallel`/`find -exec`, an alias or a
# copy of gh made on the line, a command word made at run time), and gh
# reading its inputs from stdin or a file (`--json`, `--input`, `-F k=@f`),
# is "could not tell": `ENV_UNKNOWN` with `op: line-not-literal`, asked about
# and never allowed unattended. Stdin is never modelled. The grammar does not
# resolve; it recognises or refuses.
#
# A command word made at run time is read by its argv's SHAPE (`_hole_shape`),
# never by what the rest of the line mentions (review round 3): bash's `$X`
# (which may split into several words), an `xargs`/`parallel` placeholder,
# PowerShell's `& $x`, a `Start-Process` target (`_ps_values`) and a name an
# alias points at gh or a run-time value (`ps_aliases`); a PowerShell
# variable in gh's own argv is a hole too (`symbolic`). A malformed
# `environments` block in EITHER config layer is could-not-tell for every
# dispatch (`dispatchProblem`); the terraform layer keeps reading only the
# repo's.
#
# THE LAUNCHER RULE (review round 4): a PowerShell launcher or alias writer
# (`Start-Process`, `Set-Alias`, an `alias:` path, ...) holding a
# dispatch-shaped word -- gh, `workflow`, `dispatches`, or a word made at run
# time -- is could-not-tell unless every parameter on it is a full,
# value-taking name in `_PS_FULL_PARAMS`, because PowerShell binds a switch,
# an abbreviation or a parameter alias by rules crew does not model. A
# trusted line is read by `_ps_values`, which passes gh only the positional
# values and `-ArgumentList`. THE SAME-COMMAND RULE: a command crew cannot
# split is gated only when gh and `workflow`/`dispatches` are in that ONE
# command (the whole line only when a word in it is made at run time), and a
# bash `alias NAME=VALUE` or `hash -p PATH NAME` pointing at gh makes NAME a
# copy of gh for the rest of the line (`bash_aliases`) -- the commands AFTER
# it, or the whole line when a loop, a function or a trap on it can run
# earlier text later (review round 5) -- where VALUE's last command runs gh
# (`alias g='echo gh'` runs echo). In PowerShell a comma inside one whole
# single-quoted word is text; a bare one makes an array and is refused.
#
# Once a line passes, the parser below reads it -- ONE flag parser
# (`_gh_words`) for both forms -- and `dispatch_environment` classifies it by
# the repo-only `environments.workflows` map (fnmatch, case-insensitive,
# against the argument as written). A workflow matching no key is not
# judged, as before. `dispatch_answer` is the one public road through all of
# it (T-0045, T-0072): the gate first, then the parser. `deploy_verdict` then
# applies T-0005's table with `guards.deployWorkflow` as the base policy,
# except that `allow` covers nonProd only. Not seen: an unlisted spelling of a
# deploy workflow (a display name or numeric id), the workflow YAML
# (`environment:` keys, `${{ inputs.* }}`), `gh run rerun`, `gh alias`, a
# `gh` copied or aliased by an earlier command, and a dispatch sent by `curl`.

DEPLOY_RULE = "deployWorkflow"

# The three environment classes. `cloud_guard` imports these, so the
# terraform layer and the dispatch layer cannot name a class differently.
# `unlisted` is the fourth answer `dispatch_answer` gives: nothing to judge.
ENV_NONPROD, ENV_PROD, ENV_UNKNOWN = "nonProd", "prod", "unknown"
ENV_UNLISTED = "unlisted"
_STATE_RANK = {ENV_UNLISTED: 0, ENV_NONPROD: 1, ENV_PROD: 2, ENV_UNKNOWN: 3}

# `cloud_guard.OP_UNREADABLE_LINE`'s value: a could-not-tell finding's `op`.
OP_LINE_NOT_LITERAL = "line-not-literal"

_GH_NAMES = ("gh", "gh.exe")
_DISPATCH_OPS = frozenset((";", "&&", "||", "&", "\n", ">", ">>", "&>", "&>>"))
_DISPATCH_REDIRECTS = frozenset((">", ">>", "&>", "&>>"))
_STDERR_TO_STDOUT = "2>&1"
_SINGLE_QUOTED_RE = re.compile(r"^'[^'\x00-\x1f\x7f]*'$")
_DISPATCH_WORD_ENDS = " \t\n;&|<>()"

# A word the parser still refuses to read as a value, though the grammar
# passed it: what a single quote kept verbatim (`'environment=$E'` sends the
# five characters `$E`) is a name no environment glob was written for, and
# a text `_classify` rebuilt from the lexer's words may carry what the lexer
# left unexpanded. Unknown, never a guess.
_DISPATCH_NON_LITERAL_RE = re.compile(r"[$`*?\[\]{}()<>|;&\s'\"\0]")
# A workflow NAME is a whole word, so a blank or a quote in it came from
# quoting (`gh workflow run 'Deploy Staging'`). Expansion and glob characters
# still make it unknown, and so does any character that does not show
# (round 6): a control, a line or paragraph separator, a bidi or zero-width
# format character, or a blank other than U+0020. Each looks like a name
# it is not and lands on the guard.log row verbatim.
_WORKFLOW_NON_LITERAL_RE = re.compile(r"[$`*?\[\]{}~\0]")
_WORKFLOW_UNSEEN = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs")

# `gh` options that take a value, across both forms (`-R/--repo`, `-r/--ref`,
# the fields, and `gh api`'s own). A value is never a positional word. Every
# other short flag is a boolean (`-i`, `--paginate`); gh's flag parser
# (pflag) lets booleans cluster in front of a valued one: `-iX POST`.
_GH_VALUE_OPTS = frozenset((
    "-R", "--repo", "-r", "--ref", "-f", "--raw-field", "-F", "--field",
    "-X", "--method", "-H", "--header", "--input", "-q", "--jq", "-t",
    "--template", "-p", "--preview", "--hostname", "--cache"))
# `-f`/`--raw-field` send the value as written; `-F`/`--field` read a value
# starting with `@` from that file (`@-`: stdin).
_GH_FIELD_OPTS = {"-f": "raw", "--raw-field": "raw",
                  "-F": "typed", "--field": "typed"}
# gh prints help and runs nothing for either, standing alone before `--`
# (measured 2026-09-27, gh 2.46.0).
_GH_HELP = frozenset(("-h", "--help"))

# The REST dispatch endpoint, leading `/` or a full API URL allowed. The
# owner and repo may be gh's own `{owner}`/`{repo}` placeholders.
_DISPATCH_RE = re.compile(
    r"^(?:https?://[^/]+/)?/?repos/[^/]+/[^/]+/actions/workflows/([^/?#]+)"
    r"/dispatches/?(?:[?#].*)?$", re.IGNORECASE)
# A REST field naming a workflow input: `inputs[<name>]=<value>`.
_API_INPUT_RE = re.compile(r"^inputs\[([^\[\]]*)\]$")

# What an input occurrence is called when crew cannot tell its name: it may
# be any input, so it counts against every one.
_ANY_INPUT = "*"


def _gh_name(word):
    """True when `word` is gh as a command word: its last path part."""
    return word.replace("\\", "/").rsplit("/", 1)[-1].lower() in _GH_NAMES


def _dispatch_mentions(text, shell, wild=True):
    """`(gh, verb)` for the generous read of `text` (`_name_candidates`: quotes
    and escapes out, an expansion as a wildcard): the first word that could
    be gh -- a wildcard that could match it counts only when `wild` -- and
    whether any word is `workflow` or names a `dispatches` endpoint."""
    named, verb = None, False
    for part in _name_candidates(text, shell):
        words = _brace_expand(part) if "{" in part \
            and shell != "powershell" else [part]
        for word in words if words is not None else [part]:
            base = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
            base = base[1:] if base.startswith("=") else base  # zsh's =gh
            could = wild and any(c in base for c in "*?[") and any(
                fnmatch.fnmatchcase(n, base) for n in _GH_NAMES)
            if named is None and (base in _GH_NAMES or could):
                named = part
            verb = verb or base == "workflow" or "dispatches" in word.lower()
    return named, verb


def _dispatch_shape(argv, fed=()):
    """True when `argv` -- gh, or a command word made at run time, and its
    arguments -- could send a dispatch: positionals that could be `workflow
    run ...` or `api <endpoint>` with the endpoint made at run time or
    matching `_DISPATCH_RE`. `_HOLE` stands for any words, and so does a
    word `xargs`/`parallel` (`fed`: `(via, placeholders)` pairs) fills in or
    appends. Other gh commands are never dispatch-shaped."""
    positionals, options, _help = _gh_words(_fed_args(argv[1:], fed))
    if any(_HOLE in name for name, _value in options):
        return True
    if not positionals:
        return False
    first = positionals[0]
    second = positionals[1] if len(positionals) > 1 else ""
    if _HOLE in first:
        return True
    if first == "workflow":
        return _HOLE in second or second == "run"
    if first == "api":
        return _HOLE in second or bool(_DISPATCH_RE.match(second))
    return False


def _fed_args(args, fed):
    """`args` with every word `xargs`/`parallel` (`fed`) fills in marked as
    `_HOLE`, and one more `_HOLE` for what they append."""
    reps = [r for _via, reps in fed for r in reps]
    args = [w + _HOLE if fed and ("{" in w or any(r in w for r in reps))
            else w for w in args]
    return args + [_HOLE] if fed else args


def _hole_shape(args, fed=(), split=True):
    """True when a command word made at run time, then `args`, could send a
    dispatch -- read from the argv's SHAPE, never from what the raw line
    mentions (review round 3: `$X $Y run deploy-prod.yml`, both words built
    at run time). The hole stands for any word; with `split` (bash splits an
    unquoted expansion, `parallel` runs a shell) for any WORDS, so it may
    hold `gh`, `gh workflow`, `gh workflow run [<wf>]` or `gh api
    [<endpoint>]`, and `args` need only be what could follow one of those:
    options and at most one positional, or `run ...`."""
    args = _fed_args(list(args), fed)
    if _dispatch_shape([_HOLE] + args):
        return True
    positionals = _gh_words(args)[0]
    return split and (len(positionals) <= 1 or positionals[0] == "run"
                      or bool(_DISPATCH_RE.match(positionals[0])))


# PowerShell parameters naming what a launcher runs or an alias stands for,
# and the commands that make an alias (`Set-Alias NAME VALUE`, in that order).
_PS_TARGET_PARAMS = ("-filepath", "-path", "-literalpath", "-value")
_PS_ALIASERS = frozenset(("set-alias", "sal", "new-alias", "nal"))
# THE LAUNCHER RULE (review round 4). A launcher's or aliaser's alias, as the
# command it is; and each one's FULL, value-taking parameter names, measured
# with pwsh 7 (`test_r4_ps_full_params_match_powershell`) minus the common
# parameters and `-RedirectStandardInput`, which feeds gh's stdin. A switch
# (`-NoNewWindow`) takes no value and an abbreviation (`-Fi`) or parameter
# alias (`-Args`) is bound by PowerShell's own rules, so any other parameter on
# a line holding a dispatch-shaped word makes it could-not-tell. `alias-path`
# is a command writing an `alias:`/`function:` path; a launcher with no entry
# (`Invoke-Command`, `Start-Job`, ...) trusts no parameter.
_PS_CANON = {"saps": "start-process", "start": "start-process",
             "sal": "set-alias", "nal": "new-alias", "ipal": "import-alias",
             "icm": "invoke-command", "sajb": "start-job",
             "ii": "invoke-item"}
_PS_ALIAS_PARAMS = frozenset(("-name", "-value", "-description", "-option",
                              "-scope"))
_PS_FULL_PARAMS = {
    "start-process": frozenset((
        "-filepath", "-argumentlist", "-workingdirectory", "-credential",
        "-verb", "-windowstyle", "-redirectstandardoutput",
        "-redirectstandarderror", "-environment")),
    "set-alias": _PS_ALIAS_PARAMS, "new-alias": _PS_ALIAS_PARAMS,
    "alias-path": frozenset(("-path", "-literalpath", "-name", "-value"))}
# PowerShell reads an en dash, em dash or horizontal bar as a parameter's dash.
_PS_DASHES = ("-", "\u2013", "\u2014", "\u2015")
_PS_BOUND_PARAM_RE = re.compile(
    "^[-\u2013\u2014\u2015][A-Za-z_?][A-Za-z0-9_-]*:")
_PS_CONSTANTS = frozenset(("$true", "$false", "$null"))


def _ps_canon(word):
    """A PowerShell command word as the command it runs: module qualifier and
    path dropped, lowered, an alias of a launcher or aliaser resolved."""
    head = str(word).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return _PS_CANON.get(head, head)


def _ps_param(word):
    """The parameter name `word` is (lowered, dash as written, before any
    `:`), or None when it is a value. A quoted word is a value unless it is
    a name bound with a colon (`-ArgumentList:'x'`, which the lexer keeps as
    one quoted word)."""
    text = str(word)
    if type(word).__name__ == "_Bare" and text.startswith(_PS_DASHES) \
            and len(text) > 1:
        return text.split(":", 1)[0].lower()
    if _PS_BOUND_PARAM_RE.match(text):
        return text.split(":", 1)[0].lower()
    return None


def _ps_dispatch_word(word, text):
    """True when one PowerShell word could be part of a dispatch: it names gh,
    it is or holds `workflow` or a `dispatches` endpoint (a quoted value
    split on whitespace and commas, as `_ps_values` splits `-ArgumentList`),
    or it is made at run time. A parameter is judged by its bound value, and
    `$true`/`$false`/`$null` are constants."""
    if _ps_param(word) is not None:
        bound = str(word).partition(":")[2]
        if not bound or bound.lower() in _PS_CONSTANTS:
            return False
        return any(c in bound for c in "$(@") or _ps_names_dispatch(bound)
    return _ps_runtime(word, text) or _ps_names_dispatch(str(word))


def _ps_names_dispatch(value):
    """True when a PowerShell value, split on whitespace and commas, holds a
    word naming gh, `workflow`, or a `dispatches` endpoint."""
    return any(_gh_name(p) or p.lower() == "workflow"
               or "dispatches" in p.lower()
               for p in re.split(r"[\s,]+", value) if p)


def _ps_param_table(words):
    """The trusted parameter names for the launcher or alias writer `words`."""
    canon = _ps_canon(words[0])
    if canon in _PS_FULL_PARAMS:
        return _PS_FULL_PARAMS[canon]
    if canon in _PS_LAUNCHERS:
        return frozenset()
    return _PS_FULL_PARAMS["alias-path"]


def _ps_params_trusted(words, table):
    """True when every parameter on `words` is a full name in `table`."""
    return all(name in table for name in (_ps_param(w) for w in words[1:])
               if name is not None)


def _ps_untrusted_dispatch(words, text):
    """The word that makes a launcher or alias writer could-not-tell -- the gh
    word, else the run-time word, else the command -- or None when it holds
    no dispatch-shaped word or every parameter on it is trusted."""
    shaped = [w for w in words[1:] if _ps_dispatch_word(w, text)]
    if not shaped or _ps_params_trusted(words, _ps_param_table(words)):
        return None
    return next((str(w) for w in shaped if _gh_name(str(w))), None) or next(
        (str(w) for w in shaped if _ps_runtime(w, text)), None) \
        or str(words[0])


def _ps_runtime(word, text):
    """True when PowerShell makes `word`'s value at run time: a variable or a
    splat, or a word the lexer did not read bare that `text` does not hold
    quoted as written -- `(Get-X)`, whose value the lexer only guessed."""
    if "$" in word or word.startswith("@"):
        return True
    return type(word).__name__ != "_Bare" and not any(
        q + word + q in text for q in "'\"")


def _ps_values(words, text):
    """A PowerShell launcher's or alias's words as `(name, target, rest)`.
    For an alias (`Set-Alias NAME VALUE`, or `-Name`/`-Value`): its name and
    what it stands for. For a launcher: the value of `-FilePath`/`-Path`
    (else its first value), and the other positional values and
    `-ArgumentList`'s as the words it passes on -- `-ArgumentList 'workflow
    run x'` is three -- with a run-time value as `_HOLE`. Another
    parameter's value (`-WindowStyle Hidden`) is not passed on (review round
    4: read as gh's first argument it hid the dispatch). Parameter names are
    dropped; the launcher rule has already refused a line whose parameters
    are not all full, value-taking names (`_ps_untrusted_dispatch`)."""
    values, found, index = [], {}, 1
    while index < len(words):
        word, index = words[index], index + 1
        name, bound, value = str(word).partition(":")
        if type(word).__name__ != "_Bare" or not word.startswith("-"):
            values.append(word)
            continue
        if not bound and index < len(words) and not (type(
                words[index]).__name__ == "_Bare" and words[index].startswith("-")):
            value, index = words[index], index + 1
        if bound or value:
            found[name.lower()] = value
    target = next((found[p] for p in _PS_TARGET_PARAMS if p in found), None)
    if _ps_canon(words[0]) in _PS_ALIASERS:
        name = found.get("-name") or (values.pop(0) if values else None)
        return name, target or (values[0] if values else None), []
    if target is None and values:
        target = values.pop(0)
    values += [v for k, v in found.items() if k == "-argumentlist"]
    rest = []
    for value in values:
        rest += [_HOLE] if "$" in value or value.startswith("@") or not \
            _ps_quoted(value, text) else re.split(r"[\s,]+", str(value))
    return None, target, [w for w in rest if w]


def _ps_named(words, param):
    """The value `words` give the full parameter `param` (`-Name g`, or
    `-Name:g`), else `""`."""
    for index, word in enumerate(words):
        if _ps_param(word) == param:
            bound = str(word).partition(":")[2]
            return bound or (str(words[index + 1]) if index + 1 < len(words)
                             else "")
    return ""


def _ps_quoted(word, text):
    """A value `text` spells literally: bare, or quoted as written."""
    return type(word).__name__ == "_Bare" or any(
        q + word + q in text for q in "'\"")


class _DispatchTool:
    """`_TerraformTool`'s questions, answered for a workflow dispatch. Every
    dispatch the lexer is not known to read as bash runs it is `unseen`: a
    nested script (`bash -c`, `eval`, `pwsh -c`), `xargs`/`parallel`, `find
    -exec`, zsh's `=gh`, a name the line copied or aliased gh to, a command
    word made at run time (read by `_hole_shape`). `fed` is
    `cloud_guard.scan`'s `(via, placeholders)` for a command `xargs` or
    `parallel` feeds, when the text is one the lexer already unwrapped."""

    def __init__(self, fed=()):
        self.fed = tuple(fed) if fed else ()

    @staticmethod
    def on_line(text, shell="bash"):
        named, verb = _dispatch_mentions(text, shell)
        return named if verb else None

    verb_on_line = on_line  # `on_line` already asks for the dispatch verb

    @staticmethod
    def names(word):
        return _gh_name(word)

    @staticmethod
    def hole(argv, top, shell="bash"):
        """A command word made at run time: gated when its argv's SHAPE could
        be a dispatch -- bash splits the word, PowerShell does not -- never
        by what the raw line mentions (review round 3)."""
        if not _hole_shape(argv[1:], (), shell != "powershell"):
            return None
        named = _dispatch_mentions(top, shell, wild=False)[0]
        return named or "a command word made at run time", True

    def direct(self, argv, fed, depth):
        first = argv[0]
        fed = list(fed) + ([self.fed] if self.fed else [])
        reps = [r for _via, reps in fed for r in reps]
        if fed and ("{" in first or any(r and r in first for r in reps)):
            # `xargs -I CMD CMD workflow run ...`: xargs or parallel fills the
            # command word in from input crew never reads -- a hole.
            return (first, True) if _hole_shape(argv[1:], fed) else None
        zsh = first.startswith("=") and _gh_name(first[1:])
        if not zsh and not _gh_name(first):
            return False
        if not _dispatch_shape(argv, fed):
            return None
        return first, bool(zsh or depth > 0 or fed)

    @staticmethod
    def copy_source(word):
        return _HOLE in word or _gh_name(word.lstrip("="))

    @staticmethod
    def copied(argv, _top, _shell="bash"):
        return (argv[0], True) if _dispatch_shape(argv) else None

    @staticmethod
    def opaque(args, top, launched=None, typed=None, _copies=()):
        if launched is None:
            # Gh and `workflow` in the SAME command (review round 4: `alias
            # g=gh; echo workflow` sends nothing); the whole line only when a
            # word here is made at run time (`source <(...)`). A name the
            # line made a copy of gh counts as gh (review round 5: `trap 'g
            # workflow run x' EXIT; hash -p /usr/bin/gh g`).
            own = top if any(_HOLE in a for a in args) else " ".join(args)
            named, verb = _dispatch_mentions(own, "bash")
            named = named or next((w for w in own.split()
                                   if _head_name(w) in _copies), None)
            return named if named and verb else None
        refused = _ps_untrusted_dispatch(typed, top)
        if refused is not None:
            # A switch, an abbreviation, a parameter alias or an unknown
            # parameter beside a dispatch-shaped word: PowerShell binds it by
            # rules crew does not model (the launcher rule, review round 4).
            return refused
        named = next((w for w in launched if _gh_name(w)), None)
        _alias, target, rest = _ps_values(typed, top)
        if target is not None and (_gh_name(str(target)) or _ps_runtime(
                target, top)) and _dispatch_shape([_HOLE] + rest):
            # `Start-Process $x -ArgumentList 'workflow run x'`: what it
            # launches is gh or is made at run time, with a dispatch's
            # arguments (review round 3).
            return named or str(target)
        own = top if any(_ps_runtime(w, top) for w in typed[1:]) \
            else " ".join(launched)
        return named if named and _dispatch_mentions(
            own, "powershell")[1] else None

    @staticmethod
    def symbolic(argv, words, text):
        """PowerShell's argv with every word it makes at run time as `_HOLE`
        (`gh $w run x`); the command word stays as written."""
        return argv[:1] + [_HOLE if _ps_runtime(w, text) else str(w)
                           for w in words[1:]]

    @staticmethod
    def ps_aliases(cmds, text):
        """The names the line points at gh or at a value made at run time --
        `Set-Alias`/`New-Alias`, or an `alias:`/`function:` provider path
        (`Set-Item alias:g $x`) -- each then run as a copy of gh would be."""
        out = set()
        for words in (list(c.words) for c in cmds if c.words):
            path = next((str(w) for w in words[1:] if str(w).lower().startswith(
                ("alias:", "function:"))), None)
            if _ps_canon(words[0]) in _PS_ALIASERS:
                name, target, _rest = _ps_values(words, text)
                targets = [target]
            elif path is not None:
                # `alias:g`, `alias:\g`, or `alias:` with `-Name g` (review
                # round 4: `New-Item -Path alias: -Name g -Value gh`).
                name = path.split(":", 1)[1].lstrip("\\/") or _ps_named(
                    words, "-name")
                targets = [
                    w for w in words[1:] if str(w) != path
                    and not (type(w).__name__ == "_Bare" and w.startswith("-"))]
            else:
                continue
            if _ps_untrusted_dispatch(words, text) is not None:
                continue  # an untrusted aliaser: the line is already refused
            if name and any(t is not None and (_gh_name(str(t)) or _ps_runtime(
                    t, text)) for t in targets):
                out.add(_head_name(str(name)))
        return out

    @staticmethod
    def bash_aliases(cmds, helpers=None):
        """The names a bash line points at gh (review round 4): each `alias
        NAME=VALUE` whose VALUE runs gh with the words after NAME
        (`_alias_runs_gh`), and each NAME of `hash -p PATH NAME` whose PATH
        names gh -- each then run as a copy of gh would be."""
        out = set()
        for argv in cmds:
            head = _head_name(argv[0]) if argv else ""
            if head == "alias":
                for word in argv[1:]:
                    name, eq, value = word.partition("=")
                    if eq and not name.startswith("-") \
                            and _alias_runs_gh(value, helpers):
                        out.add(_head_name(name))
            elif head == "hash":
                path, names = None, []
                for index, word in enumerate(argv[1:], 1):
                    if path is None and word.startswith("-") \
                            and "p" in word[1:] and index + 1 < len(argv):
                        path = argv[index + 1]
                    elif path is not None and word != path \
                            and not word.startswith("-"):
                        names.append(word)
                if path is not None and (_HOLE in path or _gh_name(path)):
                    out.update(_head_name(n) for n in names)
        return out


def _alias_runs_gh(value, helpers):
    """True when an alias VALUE runs gh with the words written after the
    alias's name (review round 5): bash reads VALUE again as text, and those
    words join its LAST simple command, read through `_unwrap`'s wrappers
    (`alias g='env gh'`, `alias g='cd x; gh'`), whose command word names gh
    or is made at run time (`alias g='$x'`). `alias g='echo gh'` runs echo.
    A value crew cannot read counts when any word in it names gh."""
    if _HOLE in value:
        return True
    cmds = []
    try:
        if _GATE_CONTROL_RE.search(value):
            raise _Unsure("a control character")
        _GateReader(value, 0, cmds).read()
    except _Unsure:
        return any(_gh_name(w) for w in value.split())
    argv = cmds[-1] if cmds else []
    if argv and helpers is not None:
        argv = helpers[0](argv, {}, [], {"cd": False})
    return bool(argv) and (_HOLE in argv[0] or _gh_name(argv[0]))


def fed_dispatch(argv):
    """True when `argv` -- a command `xargs`/`parallel` feeds, whose command
    word they fill in -- literally continues as a dispatch (`CMD workflow run
    <wf>`, `CMD api <dispatches endpoint>`): only gh has that shape, so
    `cloud_guard.scan` leaves the line to the dispatch gate's could-not-tell
    finding when the gate made one (review round 3), instead of cloudGuard's
    unconditional "unreadable" refusal."""
    return _dispatch_shape(["gh"] + list(argv[1:]))


def dispatch_trigger(text, helpers, shell="bash", fed=()):
    """`(word, unseen)` when `text` sends a workflow dispatch -- gh as a
    command word with a dispatch's shape, read through `_unwrap`'s wrappers
    and into `bash -c`/`eval`/`pwsh -c`/substitutions, or behind a command
    word crew cannot read on a line naming gh, `workflow` or `dispatches` --
    else None. On a reading `_GateReader` gives up on, the generous raw-text
    read naming gh together with `workflow` or `dispatches` decides.
    `helpers` as for `command_trigger`."""
    tool = _DispatchTool(fed)
    if shell == "powershell":
        return ps_trigger(helpers[3](text)[0], helpers, 0, tool)
    return _bash_trigger(text, text, helpers, 0, None, tool)


def _dispatch_tokens(text):
    """`text` as `(kind, token, start, end)`: `word` (quotes kept) or `op` (a
    run of `;&|<>`, a paren, a newline). A single quote is read as bash reads
    it only when the word turns out to be one whole quoted word, which is all
    the grammar accepts."""
    tokens, pos = [], 0
    while pos < len(text):
        char = text[pos]
        if char in " \t":
            pos += 1
            continue
        end = pos + 1
        if char in ";&|<>":
            while end < len(text) and text[end] in ";&|<>":
                end += 1
            kind = "op"
        elif char in "()\n":
            kind = "op"
        else:
            end, quoted = pos, False
            while end < len(text) and (quoted or text[end] not in
                                       _DISPATCH_WORD_ENDS):
                quoted ^= text[end] == "'"
                end += 1
            kind = "word"
        tokens.append((kind, text[pos:end], pos, end))
        pos = end
    return tokens


def _dispatch_word_ok(word, shell):
    if shell == "powershell" and (word.startswith("@") or "," in word
                                  and not _SINGLE_QUOTED_RE.match(word)):
        # A splat, or a bare comma: an array PowerShell passes as two words.
        # Inside one whole single-quoted word a comma is text (review round 5).
        return False
    return bool(_PLAIN_WORD_RE.match(word) or _SINGLE_QUOTED_RE.match(word))


def _fd_redirect(tokens, index, text):
    """The text of an fd-numbered redirection starting at `tokens[index]`
    (`2>&1`, `0>&3`, `3<`, `2>log`) -- digits, then an operator and any
    word written against them -- or None when that token is not one."""
    kind, token, start, end = tokens[index]
    after = tokens[index + 1:index + 3] + [("end", "", -1, -1)] * 2
    oper, target = after[0], after[1]
    if kind != "word" or not token.isdigit() or oper[0] != "op" \
            or oper[2] != end or oper[1][0] not in "<>":
        return None
    return text[start:target[3] if target[2] == oper[3] else oper[3]]


def _dispatch_grammar(text, shell):
    """`(word, commands)`: the first token the dispatch grammar refuses, or
    None and the line's simple commands -- each a list of words, quotes
    removed, redirections dropped."""
    tokens = _dispatch_tokens(text) + [("end", "", -1, -1)]
    commands, words, index = [], [], 0
    while tokens[index][0] != "end":
        kind, token = tokens[index][:2]
        redirect = _fd_redirect(tokens, index, text)
        if redirect is not None:
            # An fd number: `2>&1` exactly, and nothing else.
            if redirect != _STDERR_TO_STDOUT:
                return redirect, []
            index += 3
            continue
        if kind == "word":
            if not _dispatch_word_ok(token, shell):
                return token, []
            words.append(token[1:-1] if token.startswith("'") else token)
        elif token in _DISPATCH_REDIRECTS:
            target = tokens[index + 1]
            if target[0] != "word" or not _PLAIN_WORD_RE.match(target[1]):
                return token, []
            index += 1  # its target, a plain word, is not an argument
        elif token in _DISPATCH_OPS:
            commands.append(words)
            words = []
        else:
            return token, []
        index += 1
    commands.append(words)
    return None, [c for c in commands if c]


def dispatch_first_non_literal(text, shell):
    """The first word or operator of `text` the dispatch grammar does not
    accept (THE DISPATCH GRAMMAR, above), or None when every one is."""
    return _dispatch_grammar(text, shell)[0]


def dispatch_text(argv):
    """`argv` -- words the lexer produced -- as a line the grammar reads back
    word for word: a plain word as it is, any other in single quotes, and one
    single quotes cannot hold (a `'` or a control character) left bare, so
    the grammar refuses it. A word with a comma is quoted too: the one word
    PowerShell's lexer made of `'a,b'` is two when written back bare."""
    return " ".join(
        w if _PLAIN_WORD_RE.match(w) and "," not in w else
        w if "'" in w or _GATE_CONTROL_RE.search(w) or "\n" in w else
        f"'{w}'" for w in argv)


def _gh_words(args):
    """`(positionals, options, help)` for a `gh` command line -- THE parser
    for both dispatch forms: options in order as `(name, value)`, value None
    for a boolean flag. Split the way gh's flag parser (pflag) splits them:
    `--name=value`; a short cluster read one letter at a time, where the
    first letter that takes a value takes the rest of the cluster (`-iXPOST`,
    `-iX=POST`) or, if nothing is left, the next word (`-iX POST`); `--` ends
    the options. `help` is a standalone `-h`/`--help` before `--` that no
    valued option took as its value: gh prints help and sends nothing."""
    positionals, options, index, helped = [], [], 0, False
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1:])
            break
        if arg in _GH_HELP:
            helped = True
        elif arg.startswith("--") and len(arg) > 2:
            name, sep, value = arg.partition("=")
            if not sep and name in _GH_VALUE_OPTS:
                value = args[index + 1] if index + 1 < len(args) else None
                index += 1
            options.append((name, value if sep or name in _GH_VALUE_OPTS
                            else None))
        elif arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            while letters:
                name, letters = "-" + letters[0], letters[1:]
                if name not in _GH_VALUE_OPTS:
                    options.append((name, None))
                    continue
                if letters:
                    value = letters[1:] if letters.startswith("=") else letters
                else:
                    value = args[index + 1] if index + 1 < len(args) else None
                    index += 1
                options.append((name, value))
                break
        else:
            positionals.append(arg)
        index += 1
    return positionals, options, helped


def _dispatch_literal(value):
    return isinstance(value, str) and bool(value) \
        and not _DISPATCH_NON_LITERAL_RE.search(value)


def _workflow_literal(value):
    return isinstance(value, str) and bool(value.strip()) \
        and not _WORKFLOW_NON_LITERAL_RE.search(value) \
        and not any(ch != " " and unicodedata.category(ch) in _WORKFLOW_UNSEEN
                    for ch in value)


def _field_input(raw, api):
    """`(name, value, why)` for one `-f`/`-F` field that is a workflow input,
    or None when it is not one. `value` None means crew cannot tell it.
    `gh workflow run` sends every field as an input; the REST body carries
    them as `inputs[<name>]`, and its top-level `ref` is the branch, never an
    input."""
    if raw is None:
        return None
    key, sep, value = raw.partition("=")
    if not sep:
        return None
    if api:
        match = _API_INPUT_RE.match(key)
        if match is None:
            if _dispatch_literal(key):
                return None
            return (_ANY_INPUT, None, f"the field `{raw}` names no literal "
                                      "key, so it may be any input")
        key = match.group(1)
    if not _dispatch_literal(key):
        return (_ANY_INPUT, None, f"the field `{raw}` names no literal input")
    if not _dispatch_literal(value):
        return (key, None, f"`{raw}` is not a literal value")
    return (key, value, "")


def _dispatch_reads(options):
    """The first option by which gh reads its inputs from stdin or a file --
    `--json`, `--input <any>`, a typed field `-F k=@...` -- or None. Crew
    never reads either, so a dispatch carrying one is could-not-tell."""
    for name, value in options:
        if name in ("--json", "--input"):
            return name if value is None else f"{name} {value}"
        if _GH_FIELD_OPTS.get(name) == "typed" and \
                (value or "").partition("=")[2].startswith("@"):
            return f"{name} {value}"
    return None


def _dispatch_endpoint(endpoint):
    """The `<wf>` of a REST dispatch endpoint; None when the endpoint is
    built at run time (so it may be one, naming a workflow crew cannot see);
    False when it is plainly some other endpoint."""
    match = _DISPATCH_RE.match(endpoint)
    if match:
        return match.group(1)
    if any(c in endpoint for c in ("$", "`", _HOLE)):
        return None
    return False


def _dispatch_from_run(rest, options):
    """`gh workflow run [<wf>] [-f|-F k=v]...`."""
    inputs = [f for f in (_field_input(v, api=False) for n, v in options
                          if n in _GH_FIELD_OPTS) if f is not None]
    return {"form": "workflow run", "workflow": rest[0] if rest else None,
            "extra": rest[1:], "inputs": inputs}


def _dispatch_from_api(rest, options):
    """`gh api [-X POST] repos/<o>/<r>/actions/workflows/<wf>/dispatches`, or
    None when the call is not a dispatch: another endpoint, or a method that
    is not POST. With no `-X`/`--method`, gh sends POST when any field or an
    `--input` body is given, and GET otherwise; a method that is not a
    literal may be POST."""
    if not rest:
        return None
    workflow = _dispatch_endpoint(rest[0])
    if workflow is False:
        return None
    methods = [v for n, v in options if n in ("-X", "--method")]
    fields = [v for n, v in options if n in _GH_FIELD_OPTS]
    if methods:
        method = methods[-1] or ""
        if _dispatch_literal(method) and method.upper() != "POST":
            return None
    elif not fields and not any(n == "--input" for n, _v in options):
        return None
    inputs = [f for f in (_field_input(v, api=True) for v in fields)
              if f is not None]
    return {"form": "api", "workflow": workflow, "extra": [],
            "inputs": inputs}


def dispatch_what(scope):
    """The finding's `what`: the command as crew read it."""
    workflow = scope.get("workflow")
    named = workflow if workflow is not None else "(no workflow named)"
    if scope.get("form") == "api":
        return f"gh api POST .../actions/workflows/{named}/dispatches"
    return f"gh workflow run {named}"


def dispatch_scopes(args):
    """The workflow dispatch gh's arguments `args` send, as a list of zero or
    one scope in the shape both forms share: `{"op": "deploy", "form",
    "workflow", "extra", "inputs": [(name, value-or-None, why)], "reads",
    "what"}`. None for a help request (`--help`) and for a `gh api` call
    that is not a dispatch. Read only after the grammar passed the line."""
    positionals, options, helped = _gh_words(args)
    scope = None
    if helped:
        return []
    if positionals[:2] == ["workflow", "run"]:
        scope = _dispatch_from_run(positionals[2:], options)
    elif positionals[:1] == ["api"]:
        scope = _dispatch_from_api(positionals[1:], options)
    if scope is None:
        return []
    scope.update(op="deploy", reads=_dispatch_reads(options))
    scope["what"] = dispatch_what(scope)
    return [scope]


def _dispatch_class(value, globs):
    return ENV_NONPROD if any(fnmatch.fnmatch(str(value).lower(), g.lower())
                              for g in globs) else ENV_PROD


def _dispatch_source(source, inputs, globs):
    """`(class, value, why)` for one `environments.workflows` value."""
    if not source.startswith("input:"):
        return _dispatch_class(source, globs), source, ""
    name = source[len("input:"):]
    seen = [o for o in inputs
            if o[0] == _ANY_INPUT or o[0].lower() == name.lower()]
    if not seen:
        return ENV_UNKNOWN, None, (f"no `{name}` input is given, and crew does "
                                   "not read the workflow's default")
    unknown = [why for _n, value, why in seen if value is None]
    if unknown:
        return ENV_UNKNOWN, None, "; ".join(unknown)
    values = sorted({value for _n, value, _w in seen})
    if len(values) > 1:
        return ENV_UNKNOWN, None, (f"the `{name}` input is given more than "
                                   "once, with different values: "
                                   + ", ".join(f"`{v}`" for v in values))
    return _dispatch_class(values[0], globs), values[0], ""


def dispatch_environment(scope, envs):
    """THE classifier for a workflow dispatch, whichever form it came in:
    `(class, value, why, key)`, or None when the dispatch is unclassified --
    `environments.workflows` is empty, or no workflow gh was given matches a
    key (fnmatch, case-insensitive, against the argument as written).

    Never None for what crew could not tell once a key may match: no
    workflow named (gh prompts), a workflow that is not a literal, a second
    workflow argument, and an input it cannot read are each `unknown`.
    `envs` is `cloud_guard.environments_config`'s dict."""
    workflows = envs.get("workflows") or {}
    if not workflows:
        return None
    named = [w for w in [scope.get("workflow")] + list(scope.get("extra", ()))
             if w is not None]
    keys = {w: [k for k in workflows if fnmatch.fnmatch(w.lower(), k.lower())]
            for w in named if _workflow_literal(w)}
    if named and len(keys) == len(named) and not any(keys.values()):
        return None
    if not named:
        return ENV_UNKNOWN, None, ("no workflow is named, so gh would prompt "
                                   "for one"), None
    odd = next((w for w in named if w not in keys), None)
    if odd is not None:
        return ENV_UNKNOWN, None, f"the workflow `{odd}` is not a literal", None
    if len(named) > 1:
        return ENV_UNKNOWN, None, ("gh takes one workflow, and this line names "
                                   + ", ".join(f"`{w}`" for w in named)), None
    workflow, matched = named[0], keys[named[0]]
    globs = envs.get("nonProd", [])
    results = {key: _dispatch_source(workflows[key], scope.get("inputs", []),
                                     globs) for key in matched}
    if len({(k, v) for k, v, _w in results.values()}) > 1:
        return ENV_UNKNOWN, None, (f"`{workflow}` matches keys that name "
                                   "different environments: "
                                   + ", ".join(sorted(matched))), None
    klass, value, why = results[matched[0]]
    return klass, value, why, matched[0]


def dispatch_engaged(envs):
    """True while the dispatch gate runs: `environments.workflows` lists a
    workflow, or the `environments` block cannot be read. A repo that never
    listed one sees no new refusal. Either config layer's malformed block
    counts (`dispatchProblem`, review round 3)."""
    return bool(envs.get("workflows") or _envs_problem(envs))


def _envs_problem(envs):
    """What makes `envs` unreadable for a dispatch: the repo block's problem,
    or the machine-global block's (`environments_config`'s
    `dispatchProblem`), else `""`."""
    return envs.get("problem") or envs.get("dispatchProblem") or ""


def _gate_helpers():
    """cloud_guard's reader helpers, for a caller that did not pass them.
    Imported at call time, never at load: cloud_guard imports this module."""
    import cloud_guard  # pylint: disable=import-outside-toplevel,cyclic-import
    return cloud_guard.GATE_HELPERS


def _not_literal(why, word, unseen):
    """`dispatch_answer`'s could-not-tell answer."""
    shown = word if word is None or len(word) <= 40 else word[:37] + "..."
    return ENV_UNKNOWN, why, {"op": OP_LINE_NOT_LITERAL, "word": shown,
                              "unseen": unseen,
                              "what": "a workflow-dispatch line"}


def _read_line(text, shell, helpers, fed=(), problem=None):
    """`dispatch_answer`'s reading steps, in its order and with its reasons:
    the trigger, the grammar, the lexer's reach, `problem` (an unreadable
    `environments` block, or None), then the parser. `("none", why, None)`,
    `("unsure", why, (word, unseen))` or `("read", why, scopes)`.
    `dispatch_answer` keeps its own copy of the steps, which T-0009's suite
    reads by source; test_promote_dispatch_reader.py holds the two to the same
    answer on one table of lines."""
    found = dispatch_trigger(text, helpers, shell, fed)
    if found is None:
        return "none", "the line sends no workflow dispatch", None
    word = dispatch_first_non_literal(text, shell)
    if word is not None:
        return "unsure", f"`{word}` is not a plain literal", (word, False)
    if found[1]:
        return "unsure", (
            f"it runs `{found[0]}` in a way crew does not follow -- a nested "
            "shell or eval, xargs, parallel or find -exec, another name for "
            "gh, or a command word made at run time"), (None, True)
    if problem:
        return "unsure", f"the environments block cannot be read: {problem}", \
            (None, False)
    shaped, scopes = 0, []
    for argv in _dispatch_grammar(text, shell)[1]:
        argv = helpers[0](argv, {}, [], {"cd": False})
        if argv and _gh_name(argv[0]) and _dispatch_shape(argv):
            shaped += 1
            scopes += dispatch_scopes(argv[1:])
    reads = next((s["reads"] for s in scopes if s["reads"]), None)
    if reads is not None:
        return "unsure", (f"gh reads `{reads}` from stdin or a file, which "
                          "crew never reads"), (reads, False)
    if not shaped:
        # The reader found a dispatch the literal reading does not run as
        # one (`. gh ...` in PowerShell): the two disagree, so neither is
        # believed.
        return "unsure", ("crew's two readings of this line disagree about "
                          "which command sends the dispatch"), (None, True)
    return "read", "the line's dispatches are read", scopes


def dispatch_read(text, shell, helpers=None):
    """T-0062's entry point: the dispatches `text` sends, read exactly as
    `dispatch_answer` reads them, without `environments.workflows` and
    without classifying -- so promote-gate, whose list of deploy workflows is
    `.crew/verify.json`, reads a dispatch with this reader and no second one.

    `("none", why, [])`: no dispatch-shaped command. `("unsure", why, [])`:
    a dispatch-shaped line crew cannot read with certainty (could not tell).
    `("read", why, scopes)`: every dispatch on the line, each in
    `dispatch_scopes`' shape; empty for `--help` and a `gh api` GET."""
    kind, why, extra = _read_line(text, shell, helpers or _gate_helpers())
    return kind, why, extra if kind == "read" else []


def dispatch_answer(text, shell, envs, fed=(), helpers=None):
    """THE one public road to a dispatch's environment (T-0045, T-0072):
    `(state, why, scope)` for the dispatches bash (or PowerShell, `shell`)
    would send running `text`, `state` in `nonProd | prod | unknown |
    unlisted`. Pure: `envs` is `cloud_guard.environments_config`'s dict.

    The grammar runs before any parsing, so no caller reaches the parser
    around it: a dispatch-shaped line with a word or operator the grammar
    refuses, a dispatch the lexer is not known to read, gh reading stdin or
    a file, or an `environments` block crew cannot read is `unknown` with
    `scope["op"] == "line-not-literal"` -- could not tell. Only then are the
    literal line's commands parsed and classified: `unlisted` when none is a
    dispatch of a listed workflow, else the most severe dispatch's state and
    scope, `scope["dispatches"]` holding every classified one. `fed` is
    `cloud_guard.scan`'s `(via, placeholders)` for a text the lexer already
    unwrapped from `xargs`/`parallel`."""
    if not dispatch_engaged(envs):
        return ENV_UNLISTED, "environments.workflows lists no workflow", None
    helpers = helpers or _gate_helpers()
    found = dispatch_trigger(text, helpers, shell, fed)
    if found is None:
        return ENV_UNLISTED, "the line sends no workflow dispatch", None
    word = dispatch_first_non_literal(text, shell)
    if word is not None:
        return _not_literal(f"`{word}` is not a plain literal", word, False)
    if found[1]:
        return _not_literal((
            f"it runs `{found[0]}` in a way crew does not follow -- a nested "
            "shell or eval, xargs, parallel or find -exec, another name for "
            "gh, or a command word made at run time"), None, True)
    if _envs_problem(envs):
        return _not_literal("the environments block cannot be read: "
                            f"{_envs_problem(envs)}", None, False)
    shaped, scopes = 0, []
    for argv in _dispatch_grammar(text, shell)[1]:
        argv = helpers[0](argv, {}, [], {"cd": False})
        if argv and _gh_name(argv[0]) and _dispatch_shape(argv):
            shaped += 1
            scopes += dispatch_scopes(argv[1:])
    reads = next((s["reads"] for s in scopes if s["reads"]), None)
    if reads is not None:
        return _not_literal(f"gh reads `{reads}` from stdin or a file, which "
                            "crew never reads", reads, False)
    if not shaped:
        # The reader found a dispatch the literal reading does not run as
        # one (`. gh ...` in PowerShell): the two disagree, so neither is
        # believed.
        return _not_literal("crew's two readings of this line disagree about "
                            "which command sends the dispatch", None, True)
    answers = []
    for scope in scopes:
        klass = dispatch_environment(scope, envs)
        if klass is not None:
            answers.append((klass[0], klass[2], dict(
                scope, value=klass[1], key=klass[3])))
    if not answers:
        return ENV_UNLISTED, "no dispatch on the line names a listed workflow", \
            None
    state, why, scope = max(answers, key=lambda a: _STATE_RANK[a[0]])
    return state, why, dict(scope, dispatches=answers)


def _dispatch_row(state, scope):
    """One dispatch as the gate compares it: a tuple of strings, `None` (no
    workflow named, no environment read) written as `-`, so rows sort --
    `None` beside a string would raise (review round 5)."""
    return tuple("-" if v is None else "=" + str(v) for v in (
        state, scope.get("key"), scope.get("value"), scope.get("workflow")))


def dispatch_gate(text, shell, envs, lexed, helpers=None):
    """`cloud_guard.scan`'s check of the RAW line, once, at the top: the
    could-not-tell scope (`state` and `why` in it) that replaces every
    dispatch finding the lexer made, or None when those stand. `lexed` is
    their scopes. The line is could-not-tell when `dispatch_answer` says so
    for the raw text, and when its literal reading names other dispatches
    than the lexer's did -- a reading only one of the two made (`. gh` in
    PowerShell, which the lexer does not unwrap) is not judged by the other
    one's silence."""
    state, why, scope = dispatch_answer(text, shell, envs, (), helpers)
    if scope is not None and scope.get("op") == OP_LINE_NOT_LITERAL:
        return dict(scope, state=state, why=why)
    raw = sorted(_dispatch_row(st, s) for st, _w, s in
                 (scope or {}).get("dispatches", ()))
    if raw == sorted(_dispatch_row(s.get("state"), s) for s in lexed):
        return None
    _state, why, scope = _not_literal(
        "crew's two readings of this line disagree about what it dispatches",
        None, True)
    return dict(scope, state=ENV_UNKNOWN, why=why)


def dispatch_marker_key(text, scope):
    """What a dispatch's approval marker is keyed on: the whole command text,
    byte for byte -- never a subset of it, so a marker for one `<` path or
    one stdin cannot cover another -- and, for a classified dispatch, the
    workflow key and environment judged, AND every other dispatch in
    `scope["dispatches"]` (review round 5: `dispatch_answer`'s scope for a
    two-dispatch line is its highest-ranked one), so a config edit inside the
    TTL that reclassifies any of them does not carry an approval across."""
    if scope.get("op") == OP_LINE_NOT_LITERAL:
        return text
    judged = sorted(json.dumps([klass, s.get("key"), s.get("value")])
                    for klass, _why, s in scope.get("dispatches") or ())
    return text + "\n" + json.dumps(
        {"workflow": scope.get("key"),
         "environment": [scope.get("state"), scope.get("value")],
         "dispatches": judged}, sort_keys=True)


def deploy_verdict(what, scope, out, envs, live):
    """`(decision, reason, policy, marker)` for a dispatch: T-0005's table
    with `guards.deployWorkflow` as the base policy, except that `allow`
    covers nonProd only (T-0009 amendment) -- a deploy never destroys, so
    T-0005's `allow` row would otherwise reach production and an unknown
    environment with nobody attending.

        block          deny, whatever the environment
        live marker    allow (the person approved this exact command)
        could not tell ask, naming the marker that approves this text
        nonProd        allow, logged (`ask` or `allow`)
        production     allow only under `prodUnattended` in both layers
                       (logged, and said on screen); otherwise ask
        unknown        ask

    `out` is `crew_config.guard_decision`'s dict, `live` the approval-marker
    test. `ask` becomes deny when nobody is attending (`cloud_guard.evaluate`).
    """
    klass, value, why = scope["state"], scope.get("value"), scope.get("why")
    base = f"[{DEPLOY_RULE}] {what}"
    policy, marker = out["policy"], out["marker"]
    if policy == "block":
        return "deny", f"{base}: {out['reason']}", "block", marker
    if live(marker):
        return "allow", f"{base}: approved for this command: {marker}", \
            policy, marker
    if scope.get("op") == OP_LINE_NOT_LITERAL:
        # The wording avoids the words other rows' reasons are checked for
        # (unknown, production), so this finding can never stand in for the
        # one a test expects the parser to make.
        return "ask", (f"{base} -- crew judges a workflow dispatch only when "
                       "every word on its line is a plain literal or a whole "
                       f"single-quoted word, so it could not tell where this "
                       f"line deploys: {why}. Such a line is asked about and "
                       "never allowed unattended; approve this exact text "
                       f"once with {marker}, or spell it with plain words "
                       "and `-f` fields to have it judged"), \
            "could-not-tell", marker
    head = f"{base}: guards.deployWorkflow is `{policy}`"
    if klass == ENV_NONPROD:
        return "allow", f"{head}; environment `{value}` is nonProd", \
            f"env:nonProd:{value}", marker
    if klass == ENV_PROD and envs.get("prodUnattended"):
        return "allow", (f"{head}; environment `{value}` is production and "
                         "environments.prodUnattended is true in both config "
                         "layers"), f"env:prod-unattended:{value}", marker
    if klass == ENV_PROD:
        return "ask", (f"{head}: environment `{value}` is production -- it "
                       "matches no environments.nonProd glob, and "
                       "environments.prodUnattended is not true in both "
                       "config layers (a deploy's `allow` covers nonProd "
                       "only)"), f"env:prod:{value}", marker
    return "ask", (f"{head}: environment unknown -- {why}. An environment "
                   "crew cannot identify is never allowed unattended"), \
        "env:unknown", marker


def judge_dispatch(scope, what, decide, text, envs, live):
    """`cloud_guard._judge_one`'s `(decision, reason, policy, marker,
    applies)` for a dispatch finding, whose scope carries `dispatch_answer`'s
    `state` and `why`. An unlisted dispatch is not judged at all, exactly as
    before T-0009 -- no row, no decision. `decide` is
    `crew_config.guard_decision` for this guard, handed
    `dispatch_marker_key`'s text; `text` is the whole command (`envs`'s
    `command` when `evaluate` set it)."""
    scope = scope or {}
    if scope.get("state") not in (ENV_NONPROD, ENV_PROD, ENV_UNKNOWN):
        return "allow", "", "", "", False
    out = decide(dispatch_marker_key(envs.get("command") or text, scope))
    return deploy_verdict(what, scope, out, envs, live) + (True,)
