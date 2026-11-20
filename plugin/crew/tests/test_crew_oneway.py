"""R-34a: the one-way lane's command-text tripwire (`crew_oneway.py`), report-only.

Must-block rows (verdict `hit`, operation `hand-edit-terraform-state`), must-allow
rows (verdict `clear`, including the known false negatives pinned so the ticket
that covers them sees the row flip), could-not-tell rows, the pinned known
over-reports, `skip_options` and reader unit rows, helper pins on
`crew_gitallow` and `crew_guards`, the binding of the emitted name to its
one-way row in the policy table, the inertness checks, and the in-file
MUTATIONS: weakened copies of the module, each of which must turn a named case
red (R-01/R-33's pattern; the shared `sabotage*.py` files are review harness
and wait for the ticket that lets a verdict refuse).

Nothing here touches real config: the module is pure string work, and the
import check runs in a subprocess with cwd and HOME on throwaway directories.
"""
import ast
import json
import os
import random
import subprocess
import sys
import time
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_gitallow
import crew_guards
import crew_never
import crew_oneway
import crew_policy

SCRIPTS = os.path.dirname(os.path.abspath(crew_oneway.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
MODULE = os.path.join(SCRIPTS, "crew_oneway.py")
ME = os.path.abspath(__file__)
OP = crew_oneway.TF_STATE
# pylint: disable=protected-access


def source():
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


def run(mod, command, shell="bash", ctx=None):
    return mod.judge(command, shell, ctx)


def rules(result):
    return [f["rule"] for f in result["findings"]]


def assert_hit(mod, command, rule=None, shell="bash"):
    result = run(mod, command, shell)
    assert result["verdict"] == "hit", (command, result)
    assert result["operations"] == [OP], (command, result)
    if rule is not None:
        assert rule in rules(result), (command, result)
    return result


def assert_clear(mod, command, shell="bash", ctx=None):
    result = run(mod, command, shell, ctx)
    assert result["verdict"] == "clear", (command, result)
    assert result["operations"] == [], (command, result)
    return result


def assert_cnt(mod, command, rule=None, shell="bash"):
    result = run(mod, command, shell)
    assert result["verdict"] == "could-not-tell", (command, result)
    assert result["operations"] == [OP], (command, result)
    if rule is not None:
        assert rule in rules(result), (command, result)
    return result


# --- the tables ------------------------------------------------------------------------------

# (shell, command, rule)
MUST_BLOCK = (
    ("bash", "terraform state rm aws_s3_bucket.x", "tf-state-write"),
    ("bash", "terraform state mv a b", "tf-state-write"),
    ("bash", "terraform state push x.tfstate", "tf-state-write"),
    ("bash", "terraform state replace-provider a b", "tf-state-write"),
    ("bash", "tofu state rm x", "tf-state-write"),
    ("bash", "terraform -chdir=infra state rm x", "tf-state-write"),
    ("bash", "terragrunt state rm x", "tf-state-write"),
    ("bash", "terragrunt run -- state rm x", "tf-state-write"),
    ("bash", "terragrunt run-all state rm x", "tf-state-write"),
    ("bash", "terragrunt exec -- terraform state rm x", "tf-state-write"),
    ("bash", "terraform import aws_s3_bucket.x b", "tf-import"),
    ("bash", "terraform taint x", "tf-taint"),
    ("bash", "terraform untaint x", "tf-untaint"),
    ("bash", "terraform force-unlock 123", "tf-force-unlock"),
    ("bash", "terraform refresh", "tf-refresh"),
    ("bash", "TF_LOG=1 terraform state rm x", "tf-state-write"),
    ("bash", "env TF_LOG=1 terraform state rm x", "tf-state-write"),
    ("powershell", "terraform.exe state rm x", "tf-state-write"),
    ("bash", "command terraform state rm x", "tf-state-write"),
    ("bash", "time terraform state rm x", "tf-state-write"),
    ("bash", "cd infra && terraform state rm x", "tf-state-write"),
    ("bash", "if true; then terraform state rm x; fi", "tf-state-write"),
    ("bash", "for d in a; do terraform state rm x; done", "tf-state-write"),
    ("bash", "! terraform state rm x", "tf-state-write"),
    ("bash", "if terraform state rm x; then :; fi", "tf-state-write"),
    ("bash", "terraform state rm x &> log.txt", "tf-state-write"),
    # A12: an unknown option that may have swallowed the subcommand.
    ("bash", "terragrunt --unknown-flag state rm x", "tf-state-write"),
    ("bash", "terragrunt --unknown-flag import aws_s3_bucket.x b", "tf-import"),
    ("bash", "terragrunt run --unknown-flag state rm x", "tf-state-write"),
    ("bash", "terraform -unknown state rm x", "tf-state-write"),
    # A12: an unknown option that may have swallowed terragrunt's exec.
    ("bash", "terragrunt --unknown-flag exec -- terraform state rm x", "tf-state-write"),
    ("bash", "terragrunt --unknown-flag exec terraform state rm x", "tf-state-write"),
    ("bash", "terragrunt --log-disable exec -- terraform state rm x", "tf-state-write"),
    # rev 4: the `end` reading lands on `state rm x`.
    ("bash", "terragrunt --unknown-flag exec --other terraform state rm x", "tf-state-write"),
    # PowerShell's all-streams redirections are lifted whole, `*` included.
    ("powershell", "terraform *>&1 state rm x", "tf-state-write"),
    ("powershell", "terraform *> out.txt state rm x", "tf-state-write"),
    ("powershell", "terraform *>> out.txt state rm x", "tf-state-write"),
    ("powershell", "terraform state rm x *>&1", "tf-state-write"),
    ("bash", "terraform >&1 state rm x", "tf-state-write"),
)

# (shell, command)
MUST_ALLOW = (
    ("bash", "terraform state list"),
    ("bash", "terraform state show x"),
    ("bash", "terraform state pull"),
    ("bash", "terraform state rm -help"),
    ("bash", "terraform import -h"),
    ("bash", "terraform plan"),
    ("bash", "terraform apply"),
    ("bash", "terraform init"),
    ("bash", "terraform output"),
    # head precedence: the message is text after a `git` head (defect 1).
    ("bash", 'git add . && git commit -m "never terraform state rm"'),
    ("bash", 'git commit -m "fix terraform state rm docs"'),
    ("bash", "echo terraform state rm x"),
    # redirections lifted before the head is read (defect 2).
    ("bash", "terraform state list 2>&1"),
    ("bash", "terraform state list >| out.txt"),
    ("bash", "terraform state list > out.txt"),
    ("powershell", "terraform state list 2>&1"),
    ("powershell", "terraform state list *>&1"),
    ("powershell", "terraform state list *> out.txt"),
    # A12 and A13.
    ("bash", "terragrunt --unknown-flag state list"),
    ("bash", "terragrunt --working-dir state plan"),
    ("bash", "terragrunt --unknown-flag=1 plan"),
    ("bash", "terragrunt --non-interactive plan"),
    ("bash", "terragrunt --unknown-flag exec -- terraform state list"),
    ("bash", "terragrunt exec --unknown-flag -- terraform state list"),
    ("bash", "terragrunt exec -- terraform state list"),
    ("bash", "terragrunt exec ls"),
    ("bash", "terraform -unknown exec plan"),
)

# Known false negatives (Risks): terragrunt's `stack run` and `graph` run
# terraform but are not unwrapped here. Pinned clear so the later ticket that
# covers them sees the row flip.
KNOWN_FALSE_NEGATIVES = (
    "terragrunt stack run state rm x",
    "terragrunt stack run -- state rm x",
    "terragrunt graph state rm x",
)

# (command, rule)
COULD_NOT_TELL = (
    ("terraform state $SUB x", "tf-state-unseen"),
    ("terraform state", "tf-state-unseen"),
    ("terraform $OP x", "tf-sub-unseen"),
    ("terraform state list >", "redirect-target-unseen"),
    # A7 under a non-terraform head: accepted while inert.
    ("ls >", "redirect-target-unseen"),
    ("terraform -unknown exec", "tf-sub-unseen"),
    # accepted over-reports (rev 4): the option swallows the one word.
    ("terragrunt --log-disable plan", "tf-sub-unseen"),
    ("terragrunt -unknown plan", "tf-sub-unseen"),
    # A13.
    ("terragrunt exec --unknown-flag terraform state rm x", "tg-exec-unseen"),
    ("terragrunt --unknown-flag exec --other terraform plan", "tg-exec-unseen"),
    ("terragrunt exec --unknown-flag ls", "tg-exec-unseen"),
    # A5: `>& file` is not protected, so it leaves a dangling `>`.
    ("terraform state list >& out.txt", "redirect-target-unseen"),
)

# Known over-reports pinned as hits (Risks).
KNOWN_OVER_REPORTS = (
    ("terragrunt --unknown-flag refresh plan", "tf-refresh"),
    # quote-blind raw pass: the `;` inside the message cuts the segment.
    ('git add . && git commit -m "x; terraform state rm y"', "tf-state-write"),
)


@pytest.mark.parametrize("shell,command,rule", MUST_BLOCK)
def test_must_block(shell, command, rule):
    assert_hit(crew_oneway, command, rule, shell)


@pytest.mark.parametrize("shell,command", MUST_ALLOW)
def test_must_allow(shell, command):
    assert_clear(crew_oneway, command, shell)


@pytest.mark.parametrize("command", KNOWN_FALSE_NEGATIVES)
def test_known_false_negatives_are_pinned_clear(command):
    assert_clear(crew_oneway, command)


@pytest.mark.parametrize("command,rule", COULD_NOT_TELL)
def test_could_not_tell(command, rule):
    assert_cnt(crew_oneway, command, rule)


@pytest.mark.parametrize("command,rule", KNOWN_OVER_REPORTS)
def test_known_over_reports_are_pinned_hits(command, rule):
    assert_hit(crew_oneway, command, rule)


def test_a_tie_keeps_the_earlier_reading():
    result = assert_cnt(crew_oneway, "terragrunt --unknown-flag state")
    assert rules(result) == ["tf-state-unseen"]


LONG = 4000
LONG_BUDGET_SECONDS = 2.0
# Quadratic reading took 3.9 s at 2000 repeats in review round 3, so 4000
# repeats would take about 16 s; the linear reading takes well under 0.5 s.
LONG_COMMANDS = (
    ("echo " + "--unknown exec " * LONG + "terraform state rm x", "clear"),
    ("terragrunt " + "--unknown exec " * LONG + "terraform state rm x", "hit"),
    ("terragrunt " + "--unknown state " * LONG + "rm x", "hit"),
    ("terragrunt " + "exec --unknown " * LONG + "terraform plan", "could-not-tell"),
    ("terraform " + "-x " * LONG + "state list", "clear"),
)


@pytest.mark.parametrize("command,verdict", LONG_COMMANDS, ids=[str(n) for n in range(5)])
def test_a_long_command_is_judged_in_linear_time(command, verdict):
    started = time.perf_counter()
    got = run(crew_oneway, command)["verdict"]
    took = time.perf_counter() - started
    assert got == verdict
    assert took < LONG_BUDGET_SECONDS, took


@pytest.mark.parametrize("repeat", [1, 100, 300, 2000])
def test_a_long_exec_chain_gives_a_verdict(repeat):
    assert_hit(crew_oneway, "terragrunt exec -- " * repeat + "terraform state rm x",
               "tf-state-write")
    assert_clear(crew_oneway, "terragrunt exec -- " * repeat + "terraform state list")
    assert_cnt(crew_oneway, "terragrunt exec --unknown-flag " * repeat + "terraform plan",
               "tg-exec-unseen")


def test_one_finding_per_segment():
    result = run(crew_oneway, "terragrunt --unknown-flag state rm x")
    assert len(result["findings"]) == 1


def test_a_dangling_operator_does_not_hide_a_hit():
    # A7: a hit in the segment wins; A14: one finding per segment.
    result = run(crew_oneway, "terraform state rm x >")
    assert result["verdict"] == "hit"
    assert rules(result) == ["tf-state-write"]
    assert len(result["findings"]) == 1


def test_a_dangling_operator_gives_one_finding_per_segment():
    result = run(crew_oneway, "terraform state $SUB x >")
    assert rules(result) == ["redirect-target-unseen"]
    assert len(result["findings"]) == 1


# A trailing digit belongs to the word unless it starts one (bash reads
# `list2>&1` as the word `list2` and the operator `>&1`).
@pytest.mark.parametrize("command", ["terraform state list2>&1", "terraform state list2>out.txt",
                                     "terraform state rm2>&1"])
def test_a_digit_glued_to_a_word_stays_in_the_word(command):
    assert_hit(crew_oneway, command, "tf-state-write")


def test_a_marker_character_in_the_command_is_not_an_operator():
    assert_hit(crew_oneway, "terraform state \x01name list show > out.txt", "tf-state-write")
    assert_hit(crew_oneway, "terraform state \x02x > out.txt", "tf-state-write")


def test_findings_name_rule_operation_and_place_only():
    result = run(crew_oneway, "cd infra && terraform state rm aws_s3_bucket.x > out.txt")
    for finding in result["findings"]:
        assert set(finding) == {"verdict", "rule", "operation", "pass", "command", "word"}
        assert finding["word"] is None or isinstance(finding["word"], int)


def test_context_is_accepted_and_ignored():
    for ctx in (None, {}, {"ownership": "own"}, "x", 1):
        assert_clear(crew_oneway, "terraform state list", ctx=ctx)
        assert run(crew_oneway, "terraform state rm x", ctx=ctx)["verdict"] == "hit"


# --- payloads --------------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["Read", "Write", "Edit", "Glob", None, [], {}, 3, "bash"])
def test_a_payload_that_is_not_a_command(tool):
    payload = {"tool_name": tool, "tool_input": {"command": "terraform state rm x"}}
    assert crew_oneway.judge_payload(payload)["verdict"] == "not-a-command"
    assert crew_oneway.judge_payload("junk")["verdict"] == "not-a-command"


def test_payloads_that_are_commands():
    bash = {"tool_name": "Bash", "tool_input": {"command": "terraform state rm x"}}
    assert crew_oneway.judge_payload(bash)["verdict"] == "hit"
    ps = {"tool_name": "PowerShell", "tool_input": {"command": "terraform.exe state rm x"}}
    assert crew_oneway.judge_payload(ps)["verdict"] == "hit"
    for tool_input in ({}, {"command": None}, {"command": 3}, None):
        got = crew_oneway.judge_payload({"tool_name": "Bash", "tool_input": tool_input})
        assert got["verdict"] == "could-not-tell"
        assert rules(got) == ["unreadable-input"]
        assert got["operations"] == []
        assert got["findings"] == [UNREADABLE]


UNREADABLE = {"verdict": "could-not-tell", "rule": "unreadable-input", "operation": None,
              "pass": None, "command": None, "word": None}


def test_an_unknown_shell_is_could_not_tell():
    got = run(crew_oneway, "terraform state rm x", shell="zsh")
    assert got["verdict"] == "could-not-tell" and got["findings"] == [UNREADABLE]


# --- skip_options (A12) ----------------------------------------------------------------------

SKIP_ROWS = (
    (["--unknown-flag", "state", "rm", "x"], (2, [1])),
    (["-unknown", "state"], (2, [1])),
    (["--working-dir", "state", "rm", "x"], (2, [])),
    (["--unknown-flag", "foo", "state", "rm", "x"], (2, [])),
    (["--working-dir", "--foo", "state", "rm"], (2, [])),
    (["--non-interactive", "state", "rm", "x"], (1, [])),
    (["--unknown-flag=1", "state", "rm", "x"], (1, [])),
    (["--", "state", "rm"], (1, [])),
    (["--unknown-flag", "run", "state", "rm"], (1, [])),
    (["--a", "import", "--b", "state", "rm"], (4, [1, 3])),
    (["--unknown-flag", "exec", "--", "terraform", "state", "rm", "x"], (3, [1])),
    (["--unknown-flag", "exec", "terraform", "state", "rm", "x"], (2, [1])),
    (["--working-dir", "exec", "--", "terraform", "state", "rm", "x"], (3, [])),
    (["--unknown-flag", "run-all", "state", "rm"], (1, [])),
    (["--a", "exec", "--b", "state", "rm"], (4, [1, 3])),
)


@pytest.mark.parametrize("args,expected", SKIP_ROWS)
def test_skip_options(args, expected):
    assert crew_oneway.skip_options(args, 0) == expected


def test_the_ambiguous_sets():
    assert crew_oneway.AMBIGUOUS_SUBS == {"state", "import", "taint", "untaint", "force-unlock",
                                          "refresh", "exec"}
    assert crew_oneway.AMBIGUOUS_SUBS == (crew_oneway.TABLE_SUBS
                                          | crew_oneway.SWALLOWABLE_UNWRAPS)
    assert crew_oneway.TABLE_SUBS == {"state"} | set(crew_oneway.TABLE_HITS)
    assert crew_oneway.UNWRAP_WORDS == {"run", "run-all", "exec"}
    assert crew_oneway.UNWRAP_WORDS - crew_oneway.AMBIGUOUS_SUBS <= crew_guards._TF_OPS


_VOCABULARY = ("--", "-", "--unknown-flag", "-unknown", "--working-dir", "-chdir=infra",
               "--non-interactive", "--log-disable", "--x=1", "state", "rm", "exec", "run",
               "run-all", "apply", "destroy", "plan", "terraform", "-help", "x", "$X",
               "a\x00b")


def _agreement_rows():
    rows = [list(args) for args, _ in SKIP_ROWS]
    rng = random.Random(34)
    for _ in range(400):
        rows.append([rng.choice(_VOCABULARY) for _ in range(rng.randint(0, 9))])
    return rows


def test_the_scan_reads_options_exactly_as_crew_guards_does():
    """`_Scan` replaces one `tf_skip_options` walk per call with one read of
    the command; it must agree with the helper at every index."""
    for args in _agreement_rows():
        scan = crew_oneway._Scan(args)
        for index in range(len(args) + 1):
            assert scan.end[index] == crew_guards.tf_skip_options(args, index), (args, index)
            assert scan.help_from[index] == any(w in crew_oneway.HELP_WORDS
                                                for w in args[index:]), (args, index)
            assert scan.dashdash[index] == args[index:].count("--"), (args, index)


# --- the raw reader --------------------------------------------------------------------------

def seg(words, targets=(), dangling=()):
    return {"words": list(words), "targets": list(targets), "dangling": list(dangling)}


READER_ROWS = (
    ("echo {} >| f", [seg(["echo"], [(">|", "f")])]),
    ("cmd &> f", [seg(["cmd"], [("&>", "f")])]),
    ("cmd &>> f", [seg(["cmd"], [("&>>", "f")])]),
    ("cat x 2>&1 | wc -l", [seg(["cat", "x"]), seg(["wc", "-l"])]),
    ("a >&2; b", [seg(["a"]), seg(["b"])]),
    ("a <&0", [seg(["a"])]),
    ("a 2>>f && b", [seg(["a"], [("2>>", "f")]), seg(["b"])]),
    ("a & b", [seg(["a"]), seg(["b"])]),
    ("a | b", [seg(["a"]), seg(["b"])]),
    ("a && b", [seg(["a"]), seg(["b"])]),
    ("a || b", [seg(["a"]), seg(["b"])]),
    ("a; b", [seg(["a"]), seg(["b"])]),
    ("a\nb", [seg(["a"]), seg(["b"])]),
    ("a >", [seg(["a"], dangling=[">"])]),
    ("a >f", [seg(["a"], [(">", "f")])]),
    ("cat <<EOF", [seg(["cat"], [("<<", "EOF")])]),
    ("cat <<-EOF", [seg(["cat"], [("<<-", "EOF")])]),
    ("cat <<< word", [seg(["cat"], [("<<<", "word")])]),
    ("a >& f", [seg(["a"], dangling=[">"]), seg(["f"])]),
    ("a list2>&1", [seg(["a", "list2"])]),
    ("a x2>f", [seg(["a", "x2"], [(">", "f")])]),
    ("a 2>f", [seg(["a"], [("2>", "f")])]),
    # bash: a `*` before an operator is a glob word, not a stream.
    ("a *>&1", [seg(["a", "*"])]),
)

PS_READER_ROWS = (
    ("a *>&1", [seg(["a"])]),
    ("a *>&1 b", [seg(["a", "b"])]),
    ("a *> f", [seg(["a"], [("*>", "f")])]),
    ("a *>> f", [seg(["a"], [("*>>", "f")])]),
    ("a 3>&1", [seg(["a"])]),
    ("a x*>&1", [seg(["a", "x*"])]),
)


@pytest.mark.parametrize("text,expected", READER_ROWS)
def test_the_reader(text, expected):
    assert crew_oneway.raw_segments(text) == expected


@pytest.mark.parametrize("text,expected", PS_READER_ROWS)
def test_the_powershell_reader(text, expected):
    assert crew_oneway.raw_segments(text, "powershell") == expected


# --- helper pins -----------------------------------------------------------------------------

PLAIN_PINS = (
    ("bash", "TF_LOG=1 terraform state rm x", [["TF_LOG=1", "terraform", "state", "rm", "x"]]),
    ("bash", "terragrunt run -- state rm x", [["terragrunt", "run", "--", "state", "rm", "x"]]),
    ("bash", "terraform -chdir=infra state rm x",
     [["terraform", "-chdir=infra", "state", "rm", "x"]]),
    ("bash", "command terraform state rm x", [["command", "terraform", "state", "rm", "x"]]),
    ("bash", "time terraform state rm x", [["time", "terraform", "state", "rm", "x"]]),
    ("bash", "sudo terraform state rm x", [["sudo", "terraform", "state", "rm", "x"]]),
    ("bash", "env TF_LOG=1 terraform state rm x",
     [["env", "TF_LOG=1", "terraform", "state", "rm", "x"]]),
    ("powershell", "terraform.exe state rm x", [["terraform.exe", "state", "rm", "x"]]),
    ("bash", "cd infra && terraform state rm x", None),
    ("bash", "if true; then terraform state rm x; fi", None),
    ("bash", "for d in a; do terraform state rm x; done", None),
    ("bash", "! terraform state rm x", None),
    ("bash", "terraform state $SUB x", None),
    ("bash", "terraform state list > out.txt", None),
    ("bash", "terraform state list 2>&1", None),
    ("bash", "terraform state list >| out.txt", None),
    ("bash", "terraform state list &> out.txt", None),
    ("powershell", "terraform state list > out.txt", None),
    ("powershell", "terraform state list 2>&1", None),
    ("powershell", "terraform state list >| out.txt", None),
    ("powershell", "terraform state list &> out.txt", None),
)


@pytest.mark.parametrize("shell,command,expected", PLAIN_PINS)
def test_plain_commands_pin(shell, command, expected):
    assert crew_gitallow.plain_commands(command, shell) == expected


def test_guards_helper_pins():
    skip = crew_guards.tf_skip_options
    assert skip(["-chdir=infra", "state", "rm"], 0) == 1
    assert skip(["--", "state", "rm"], 0) == 1
    # The behaviour A12 exists for: if it stops, re-read A12, do not delete it.
    assert skip(["--unknown-flag", "state", "rm", "x"], 0) == 2
    assert crew_guards._TF_READ_ONLY_PAIRS["state"] <= crew_oneway.STATE_READ
    assert {"run", "run-all"} <= crew_guards._TF_OPS
    assert "exec" not in crew_guards._TF_OPS
    assert skip(["--unknown-flag", "exec", "--", "terraform", "state", "rm", "x"], 0) == 3
    # The behaviour A13 exists for.
    assert skip(["exec", "--unknown-flag", "terraform", "state", "rm", "x"], 1) == 3


def test_the_head_prefixes_are_a_superset_of_the_never_tripwire():
    assert crew_never.HEAD_PREFIXES <= crew_oneway.HEAD_PREFIXES
    assert {"if", "elif", "while", "until"} <= crew_oneway.HEAD_PREFIXES


# --- policy binding --------------------------------------------------------------------------

def _emitted():
    names = set(crew_oneway.OPERATIONS_EMITTED)
    for shell, command, _ in MUST_BLOCK:
        names.update(run(crew_oneway, command, shell)["operations"])
    for command, _ in COULD_NOT_TELL:
        names.update(run(crew_oneway, command)["operations"])
    return names


def test_the_emitted_name_is_a_human_row_the_owner_answers():
    assert _emitted() == {OP}
    assert crew_policy.OPERATIONS[OP].lane == "human"
    for presence in crew_policy.PRESENCE:
        for tier in crew_policy.TIERS:
            got = crew_policy.decide({"operation": OP, "presence": presence, "tier": tier,
                                      "machine_layer": "clear"})
            assert (got["outcome"], got["rule"]) == ("ask-owner", "human"), got


def test_nothing_waves_the_one_way_row_through():
    emergency = {"declared_by": "owner", "incident": "i", "target": "t",
                 "action": OP, "expiry": "2999-01-01T00:00:00Z", "uses_left": 1}
    for presence in crew_policy.PRESENCE:
        for tier in crew_policy.TIERS:
            for layer in crew_policy.MACHINE_LAYER:
                for provenance in crew_policy.PROVENANCE:
                    got = crew_policy.decide({
                        "operation": OP, "presence": presence, "tier": tier,
                        "machine_layer": layer, "provenance": provenance,
                        "plan_covers": True, "attested": True, "prodcheck": "pass",
                        "target": "t", "emergency": emergency})
                    assert got["outcome"] not in ("allow", "ask-routine"), got


# --- output ----------------------------------------------------------------------------------

TARGETS = ("aws_s3_bucket.x", "x.tfstate", "out.txt")
OUTPUT_LINES = (
    "terraform state rm aws_s3_bucket.x > out.txt",
    "cd infra && terraform state push x.tfstate 2> out.txt",
    "terraform import aws_s3_bucket.x b >> out.txt",
)


def test_no_finding_carries_a_word_of_the_command():
    for command in OUTPUT_LINES:
        shown = json.dumps(run(crew_oneway, command))
        for target in TARGETS:
            assert target not in shown, (command, shown)


# --- inertness -------------------------------------------------------------------------------

def _plugin_files():
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__")]
        for name in files:  # every file: a .cmd or .toml wrapper counts too
            yield os.path.join(root, name)


def test_nothing_in_the_plugin_reaches_the_tripwire_yet():
    mine = {os.path.normcase(MODULE), os.path.normcase(ME)}
    hits = []
    for path in _plugin_files():
        if os.path.normcase(path) in mine:
            continue
        with open(path, "rb") as handle:
            if b"crew_oneway" in handle.read():
                hits.append(os.path.relpath(path, PLUGIN))
    assert hits == [], "report-only until a later ticket wires it"


def _imports(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_direct_imports_are_the_standard_library_and_two_modules():
    allowed = {"crew_gitallow", "crew_guards"}
    for name in _imports(MODULE):
        assert name in sys.stdlib_module_names or name in allowed, name


def test_the_module_declares_itself_report_only():
    assert crew_oneway.REPORT_ONLY is True
    assert "REPORT-ONLY" in source()
    assert "crew_never" not in source()
    assert "crew_policy" not in source()


def _tree(path):
    return sorted(os.path.relpath(os.path.join(r, f), path)
                  for r, _, files in os.walk(path) for f in files)


def test_importing_loads_no_policy_hook_never_or_coord_and_writes_nothing(tmp_path):
    cwd, home = tmp_path / "cwd", tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    env = _isolated_env(home)
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); before = set(sys.modules); "
            "import crew_oneway; crew_oneway.judge('terraform state rm x'); "
            "print(json.dumps(sorted(set(sys.modules) - before)))")
    before = (_tree(cwd), _tree(home))
    done = subprocess.run([sys.executable, "-c", code, SCRIPTS], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", check=False,
                          timeout=120)
    assert done.returncode == 0 and done.stderr == "", done.stderr
    loaded = set(json.loads(done.stdout))
    assert "crew_oneway" in loaded
    assert not loaded & {"crew_policy", "crew_hook", "crew_never", "crew_coord"}, loaded
    assert (_tree(cwd), _tree(home)) == before == ([], [])


def _isolated_env(home):
    env = dict(os.environ)
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        env[key] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_the_cli(tmp_path):
    env = _isolated_env(tmp_path)

    def cli(*args, stdin=None):
        return subprocess.run([sys.executable, MODULE, *args], input=stdin, capture_output=True,
                              text=True, encoding="utf-8", check=False, timeout=120,
                              cwd=tmp_path, env=env)
    done = cli("judge", "--", "terraform state rm x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "hit"
    done = cli("judge", "--shell", "powershell", "--", "terraform state list 2>&1")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "clear"
    done = cli("judge", "--", "terraform state $SUB x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "could-not-tell"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "terraform taint x"}})
    done = cli("payload", stdin=payload)
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "hit"
    done = cli("shapes")
    assert done.returncode == 0
    for _, rule, _ in crew_oneway.SHAPES:
        assert rule in done.stdout
    assert cli("payload", stdin="not json").returncode == 2
    assert cli("frobnicate").returncode == 2
    assert cli("judge", "--shell", "zsh", "--", "x").returncode == 2


# --- sabotage: each weakened copy must turn a named case red --------------------------------

def case_block_state_rm(mod):
    assert_hit(mod, "terraform state rm aws_s3_bucket.x", "tf-state-write")


def case_block_import(mod):
    assert_hit(mod, "terraform import aws_s3_bucket.x b", "tf-import")


def case_block_taint(mod):
    assert_hit(mod, "terraform taint x", "tf-taint")


def case_block_run_unwrap(mod):
    assert_hit(mod, "terragrunt run -- state rm x", "tf-state-write")


def case_allow_state_show(mod):
    assert_clear(mod, "terraform state show x")


def case_allow_help(mod):
    assert_clear(mod, "terraform state rm -help")


def case_allow_with_no_context(mod):
    assert_clear(mod, "terraform state list", ctx=None)


def case_cnt_state_sub(mod):
    assert_cnt(mod, "terraform state $SUB x", "tf-state-unseen")


def case_no_target_in_output(mod):
    for command in OUTPUT_LINES:
        shown = json.dumps(run(mod, command))
        for target in TARGETS:
            assert target not in shown, (command, target)


def case_block_raw_chain(mod):
    assert_hit(mod, "cd infra && terraform state rm x", "tf-state-write")


def case_block_prefix_then(mod):
    assert_hit(mod, "if true; then terraform state rm x; fi", "tf-state-write")


def case_block_prefix_do(mod):
    assert_hit(mod, "for d in a; do terraform state rm x; done", "tf-state-write")


def case_block_prefix_bang(mod):
    assert_hit(mod, "! terraform state rm x", "tf-state-write")


def case_block_prefix_command(mod):
    assert_hit(mod, "command terraform state rm x", "tf-state-write")


def case_allow_fd_copy(mod):
    assert_clear(mod, "terraform state list 2>&1")


def case_reader_clobber(mod):
    assert mod.raw_segments("echo {} >| f") == [seg(["echo"], [(">|", "f")])]


def case_reader_amp(mod):
    assert mod.raw_segments("cmd &> f") == [seg(["cmd"], [("&>", "f")])]


def case_block_unknown_option_state(mod):
    assert_hit(mod, "terragrunt --unknown-flag state rm x", "tf-state-write")


def case_skip_rows_with_alternates(mod):
    wrong = [(args, mod.skip_options(args, 0), expected) for args, expected in SKIP_ROWS
             if expected[1] and mod.skip_options(args, 0) != expected]
    assert wrong == [], wrong


def case_block_swallowed_exec_dashdash(mod):
    assert_hit(mod, "terragrunt --unknown-flag exec -- terraform state rm x", "tf-state-write")


def case_block_swallowed_exec_bare(mod):
    assert_hit(mod, "terragrunt --unknown-flag exec terraform state rm x", "tf-state-write")


def case_long_exec_chain(mod):
    try:
        assert_hit(mod, "terragrunt exec -- " * 300 + "terraform state rm x", "tf-state-write")
    except RecursionError as exc:
        raise AssertionError("no verdict: RecursionError") from exc


def case_block_log_disable_exec(mod):
    assert_hit(mod, "terragrunt --log-disable exec -- terraform state rm x", "tf-state-write")


def case_exec_skip_row(mod):
    args = ["--unknown-flag", "exec", "--", "terraform", "state", "rm", "x"]
    assert mod.skip_options(args, 0) == (3, [1])


def case_ambiguous_literal(mod):
    assert mod.AMBIGUOUS_SUBS == {"state", "import", "taint", "untaint", "force-unlock",
                                  "refresh", "exec"}


def case_cnt_exec_options_no_dashdash(mod):
    assert_cnt(mod, "terragrunt exec --unknown-flag terraform state rm x", "tg-exec-unseen")


def case_cnt_swallowed_exec_options(mod):
    assert_cnt(mod, "terragrunt --unknown-flag exec --other terraform plan", "tg-exec-unseen")


def case_tie_keeps_earlier(mod):
    result = assert_cnt(mod, "terragrunt --unknown-flag state")
    assert rules(result) == ["tf-state-unseen"], result


def case_block_glued_digit(mod):
    assert_hit(mod, "terraform state list2>&1", "tf-state-write")


def case_block_marker_in_command(mod):
    assert_hit(mod, "terraform state \x01name list show > out.txt", "tf-state-write")


def case_one_finding_with_dangling(mod):
    result = run(mod, "terraform state rm x >")
    assert rules(result) == ["tf-state-write"], result


def case_block_ps_all_streams(mod):
    assert_hit(mod, "terraform *>&1 state rm x", "tf-state-write", shell="powershell")


def case_bash_star_is_a_word(mod):
    assert mod.raw_segments("a *>&1") == [seg(["a", "*"])]


def case_long_swallowed_exec_chain_is_linear(mod):
    command = "terragrunt " + "--unknown exec " * LONG + "terraform state rm x"
    started = time.perf_counter()
    assert_hit(mod, command, "tf-state-write")
    took = time.perf_counter() - started
    assert took < LONG_BUDGET_SECONDS, took


MUTATIONS = (
    ("1 rm added to the state read set",
     'STATE_READ = frozenset(("list", "show", "pull", "identities"))',
     'STATE_READ = frozenset(("list", "show", "pull", "identities", "rm"))',
     ("case_block_state_rm",)),
    ("2 import and taint dropped", '    "import": "tf-import", "taint": "tf-taint",\n', "",
     ("case_block_import", "case_block_taint")),
    ("3 the terragrunt run unwrap skipped",
     "    end, alternates = skip_options(scan.words, at + 1, scan)\n",
     "    end, alternates = at, []\n", ("case_block_run_unwrap",)),
    ("4 state show treated as a write",
     'STATE_READ = frozenset(("list", "show", "pull", "identities"))',
     'STATE_READ = frozenset(("list", "pull", "identities"))', ("case_allow_state_show",)),
    ("5 the -help check dropped",
     "    if scan.help_from[at + 1]:\n        return _CLEAR\n", "",
     ("case_allow_help",)),
    ("11 a missing context is could-not-tell",
     "    del context  # accepted and ignored by every terraform row (A4)\n",
     "    if not isinstance(context, dict):\n"
     '        return _result([_finding(COULD_NOT_TELL, "no-context", TF_STATE)])\n',
     ("case_allow_with_no_context",)),
    ("12 could-not-tell collapses to clear",
     "    if COULD_NOT_TELL in verdicts:\n        return COULD_NOT_TELL",
     "    if COULD_NOT_TELL in verdicts:\n        return CLEAR", ("case_cnt_state_sub",)),
    ("18 the redirect targets put in the finding",
     '        where = {"pass": "raw", "command": number}\n',
     '        where = {"pass": "raw", "command": number, "targets": segment["targets"]}\n',
     ("case_no_target_in_output",)),
    ("19 raw pass skipped", "    if commands is None:\n        return _raw_pass(command, shell)",
     "    if commands is None:\n        return []", ("case_block_raw_chain",)),
    ("29 only assignments, env and sudo stripped",
     'HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!",\n'
     '                           "if", "elif", "while", "until"))',
     'HEAD_PREFIXES = frozenset(("env", "sudo"))', ("case_block_prefix_then", "case_block_prefix_do",
                                                  "case_block_prefix_bang",
                                                  "case_block_prefix_command")),
    ("R1 cut at separators before protecting redirections",
     "    for piece in _SEPARATORS_RE.split(_protect(text, shell)):",
     "    for piece in map(_protect, _SEPARATORS_RE.split(text)):",
     ("case_allow_fd_copy", "case_reader_clobber", "case_reader_amp")),
    ("R2 skip_options without alternates", "    return end, alternates\n",
     "    return end, []\n",
     ("case_block_unknown_option_state", "case_skip_rows_with_alternates",
      "case_block_swallowed_exec_dashdash", "case_block_swallowed_exec_bare",
      "case_block_log_disable_exec")),
    ("R3 exec dropped from the swallowable unwraps",
     'SWALLOWABLE_UNWRAPS = frozenset(("exec",))', "SWALLOWABLE_UNWRAPS = frozenset()",
     ("case_block_swallowed_exec_dashdash", "case_block_swallowed_exec_bare",
      "case_exec_skip_row", "case_ambiguous_literal")),
    ("R4 an alternate judged through the table only",
     "        readings[at] = _reading(scan, head, at)\n",
     "        readings[at] = _table(scan, at)\n",
     ("case_block_swallowed_exec_dashdash", "case_block_swallowed_exec_bare")),
    ("R5 the no-dash-dash check after exec dropped",
     "        if end > at + 1 and scan.dashdash[at + 1] == scan.dashdash[end]:",
     "        if False:",
     ("case_cnt_exec_options_no_dashdash", "case_cnt_swallowed_exec_options")),
    ("R6 a tie keeps the last reading",
     "        if _RANK[reading[0]] > _RANK[kept[0]]:",
     "        if _RANK[reading[0]] >= _RANK[kept[0]]:", ("case_tie_keeps_earlier",)),
    ("R7 the exec chain judged by plain recursion",
     "            scan.memo[later] = _judge_from(scan, later)\n",
     "            pass\n", ("case_long_exec_chain",)),
    ("R8 any digits before an operator taken as its fd",
     '_FD = r"(?:(?<![^\\s;&|(){}])[0-9]+)?"', '_FD = r"[0-9]*"', ("case_block_glued_digit",)),
    ("R9 marker characters in the command left in place",
     "    text = text.translate(_UNMARK)\n", "", ("case_block_marker_in_command",)),
    ("R10 a dangling segment reports both findings",
     "            out.append(_finding(verdict, rule, TF_STATE, word=word, **where))\n"
     "            continue\n",
     '            out.append(_finding(COULD_NOT_TELL, "redirect-target-unseen", TF_STATE,\n'
     "                                word=None, **where))\n",
     ("case_one_finding_with_dangling",)),
    ("R11 powershell's `*` stream not taken as an fd",
     '_PS_FD = r"(?:(?<![^\\s;&|(){}])(?:[0-9]+|\\*))?"', "_PS_FD = _FD",
     ("case_block_ps_all_streams",)),
    ("R12 bash reads `*` as a stream too",
     '_REDIRECT_RE = {"bash": _redirect_re(_FD), "powershell": _redirect_re(_PS_FD)}',
     '_REDIRECT_RE = {"bash": _redirect_re(_PS_FD), "powershell": _redirect_re(_PS_FD)}',
     ("case_bash_star_is_a_word",)),
    ("R13 the exec chain re-walks the options from every exec (quadratic)",
     "        end = scan.end[at + 1]\n",
     "        end = crew_guards.tf_skip_options(scan.words, at + 1)\n",
     ("case_long_swallowed_exec_chain_is_linear",)),
)


def _variant(old, new):
    text = source()
    assert text.count(old) == 1, f"mutation target moved: {old!r}"
    name = "crew_oneway_mutant"
    module = types.ModuleType(name)
    module.__file__ = MODULE
    sys.modules[name] = module
    try:
        exec(compile(text.replace(old, new), name, "exec"),  # pylint: disable=exec-used
             module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("name", sorted(n for n in globals() if n.startswith("case_")))
def test_every_case_is_green_on_the_real_module(name):
    globals()[name](crew_oneway)


@pytest.mark.parametrize("label,old,new,cases", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_tripwire_is_caught(label, old, new, cases):
    mutant = _variant(old, new)
    for name in cases:
        try:
            globals()[name](mutant)
        except AssertionError:
            continue  # red for the reason the case asserts, not a crash
        pytest.fail(f"{label}: {name} stayed green against the mutant")


def test_r3_leaves_the_plain_unknown_option_row_a_hit():
    """What separates R3 from R2: dropping `exec` keeps `--unknown-flag state rm x`."""
    mutant = _variant('SWALLOWABLE_UNWRAPS = frozenset(("exec",))',
                      "SWALLOWABLE_UNWRAPS = frozenset()")
    assert_hit(mutant, "terragrunt --unknown-flag state rm x", "tf-state-write")


def test_r4_leaves_every_skip_options_row_green():
    """What separates R4 from R3: the alternates are found, then judged wrongly."""
    mutant = _variant("        readings[at] = _reading(scan, head, at)\n",
                      "        readings[at] = _table(scan, at)\n")
    for args, expected in SKIP_ROWS:
        assert mutant.skip_options(args, 0) == expected  # pylint: disable=no-member
