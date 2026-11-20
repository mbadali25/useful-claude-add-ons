"""R-34a, R-34b: the one-way lane's command-text tripwire (`crew_oneway.py`), report-only.

R-34b adds state-file writes (redirections, head-keyed rows, the git table)
and file-tool payloads, all under the same operation, and keeps a recorded
redirection target's whitespace (F1).

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
import scope_guard

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
    # round 4: an fd copy's operand is a whole word, so `>&2list` writes the
    # file `2list` and the command is `terraform state rm x.y`.
    ("bash", "terraform state >&2list rm x.y", "tf-state-write"),
    ("bash", "terraform state >&2foo rm x.y", "tf-state-write"),
    ("bash", "terraform state >&-list rm x.y", "tf-state-write"),
    ("bash", 'terraform state >&2"list" rm x.y', "tf-state-write"),
    ("bash", "terraform state 2>&1list rm x.y", "tf-state-write"),
    # round 5: a quoted empty word is the here-string's operand, so `state`
    # is not; a quoted operand with a space in it is one operand.
    ("bash", 'terraform <<< "" state rm x', "tf-state-write"),
    ("bash", "terraform <<< '' state rm x", "tf-state-write"),
    ("bash", 'terraform > "" state rm x', "tf-state-write"),
    ("bash", 'terraform <<< "a b" state rm x', "tf-state-write"),
    ("bash", "terraform <<< 'a b c' state rm x", "tf-state-write"),
    # round 5: a comment is not an argument, so its -help exempts nothing.
    ("bash", "terraform state rm x # -help", "tf-state-write"),
    ("bash", "terraform state rm x #--help", "tf-state-write"),
    ("bash", "terraform state rm x > out.txt # -h", "tf-state-write"),
    ("bash", "cd infra && terraform import a b # -help", "tf-import"),
    ("powershell", "terraform state rm x # -help", "tf-state-write"),
    # round 6: an escaped quote closes nothing, and a quote that opens inside
    # the word is followed too, so `b"` is the operand's end, not a subcommand.
    ("bash", r'terraform <<< "a\" b" state rm x', "tf-state-write"),
    ("bash", 'terraform <<< a" b" state rm x', "tf-state-write"),
    ("bash", "terraform <<< a' b' state rm x", "tf-state-write"),
    ("bash", r"terraform <<< a\ b state rm x", "tf-state-write"),
    ("bash", r'terraform > "a\"b c" state rm x', "tf-state-write"),
    ("powershell", 'terraform *> "a`" b" state rm x', "tf-state-write"),
    ("bash", 'terraform state rm x >"a>b"', "tf-state-write"),
    # R-34b (B3): a redirection into a state word, whatever the head.
    ("bash", "echo {} > terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {} >terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {}>terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {} >>terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {} 1>terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {} >| terraform.tfstate", "tfstate-redirect"),
    ("bash", "echo {} &> terraform.tfstate", "tfstate-redirect"),
    ("bash", "terraform show -json &> terraform.tfstate", "tfstate-redirect"),
    ("bash", "terraform show -json > terraform.tfstate", "tfstate-redirect"),
    # a known over-report (the backup idiom), pinned here.
    ("bash", "terraform state pull > backup.tfstate", "tfstate-redirect"),
    ("bash", "cd infra && echo {} > envs/prod/terraform.tfstate", "tfstate-redirect"),
    ("powershell", "echo x *> terraform.tfstate", "tfstate-redirect"),
    ("powershell", "echo x > terraform.tfstate", "tfstate-redirect"),
    # the state-word test runs before the expansion test.
    ("bash", 'cat x.json > "$D/terraform.tfstate"', "tfstate-redirect"),
    # R-34b (B5): a state word after a writing head.
    ("bash", "rm terraform.tfstate", "tfstate-remove"),
    ("bash", "rm -f envs/prod/terraform.tfstate.backup", "tfstate-remove"),
    ("bash", "rm -rf terraform.tfstate.d", "tfstate-remove"),
    ("bash", "sudo rm terraform.tfstate", "tfstate-remove"),
    ("bash", "mv a.tfstate b.tfstate", "tfstate-move"),
    ("bash", "cp fixed.json terraform.tfstate", "tfstate-overwrite"),
    ("bash", "sed -i s/a/b/ terraform.tfstate", "tfstate-inplace"),
    ("bash", "perl -pi -e s/a/b/ terraform.tfstate", "tfstate-inplace"),
    ("bash", "jq . x.json | tee terraform.tfstate", "tfstate-write"),
    ("bash", "aws s3 cp state.json s3://b/env/terraform.tfstate", "tfstate-remote"),
    ("bash", "aws s3 rm s3://b/env/terraform.tfstate", "tfstate-remote"),
    ("bash", "gsutil rm gs://b/terraform.tfstate", "tfstate-remote"),
    ("powershell", "Remove-Item terraform.tfstate", "tfstate-remove"),
    ("powershell", "Set-Content terraform.tfstate x", "tfstate-write"),
    ("bash", "terragrunt exec -- rm terraform.tfstate", "tfstate-remove"),
    # R-34b (B6): the git table, state words after the subcommand.
    ("bash", "git rm terraform.tfstate", "tfstate-git-remove"),
    # a known over-report (`--cached` keeps the file), pinned here.
    ("bash", "git rm --cached terraform.tfstate", "tfstate-git-remove"),
    ("bash", "git -C infra rm terraform.tfstate", "tfstate-git-remove"),
    ("bash", "git mv terraform.tfstate old.tfstate", "tfstate-git-move"),
    ("bash", "git checkout -- terraform.tfstate", "tfstate-git-overwrite"),
    ("bash", "git restore terraform.tfstate", "tfstate-git-overwrite"),
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
    # round 4: an fd copy that ends its word is still dropped.
    ("bash", "terraform state >&2 list rm x"),
    ("bash", "(terraform state list >&2)"),
    ("bash", "terraform state list >&2; ls"),
    ("bash", 'bash -c "terraform state list >&2" | tee log'),
    ("bash", "terraform state list >&out.txt"),
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
    # round 5: the comment is dropped, the command before it still reads.
    ("bash", "terraform state list # rm x"),
    ("bash", "terraform state rm -help # why"),
    ("bash", "terraform plan > out.txt # state rm x"),
    # a quoted `#` is an argument, so the accepted help exemption holds.
    ("bash", 'terraform state rm x "#" -help'),
    ("bash", 'terraform state list <<< ""'),
    ("bash", 'terraform state list <<< "a b"'),
    # round 6: the escaped space makes `x state` one operand, so the shell
    # runs `terraform rm y`.
    ("bash", r"terraform <<< x\ state rm y"),
    ("bash", r'terraform state list <<< "a\" b"'),
    ("bash", 'terraform state list >"a>b"'),
    # R-34b: reading a state file, or a redirection that is not a write.
    ("bash", "cat terraform.tfstate"),
    ("bash", "cat < terraform.tfstate"),
    ("bash", "jq .serial terraform.tfstate"),
    ("bash", "jq . terraform.tfstate > out.json"),
    ("bash", "cp terraform.tfstate /tmp/inspect.json"),
    ("bash", "aws s3 cp s3://b/env/terraform.tfstate state.json"),
    ("bash", "ls *.tfstate"),
    ("bash", "echo terraform.tfstate"),
    ("bash", "echo x > notes.txt"),
    ("bash", "echo x >notes.txt"),
    ("bash", "echo x > $OUT"),
    ("bash", "cat terraform.tfstate 2>&1"),
    ("bash", "cat terraform.tfstate >&2"),
    ("bash", "cat <<< terraform.tfstate"),
    # R-34b: head precedence, a terraform head reads its own table only.
    ("bash", "terraform show terraform.tfstate"),
    ("bash", "terraform plan -state=terraform.tfstate"),
    # R-34b: git reads.
    ("bash", "git status terraform.tfstate"),
    ("bash", "git diff terraform.tfstate"),
    ("bash", "git log -- terraform.tfstate"),
    ("bash", "git add terraform.tfstate"),
    ("bash", "git show HEAD:terraform.tfstate"),
    ("bash", 'git commit -m "stop tracking terraform.tfstate"'),
    ("bash", 'git commit --message="drop terraform.tfstate"'),
    # the plain pass: nothing is lifted from inside the quotes.
    ("bash", 'git commit -m "a > terraform.tfstate"'),
    ("bash", 'echo "a>terraform.tfstate"'),
)

# Known false negatives (Risks): terragrunt's `stack run` and `graph` run
# terraform but are not unwrapped here. Pinned clear so the later ticket that
# covers them sees the row flip.
KNOWN_FALSE_NEGATIVES = (
    "terragrunt stack run state rm x",
    "terragrunt stack run -- state rm x",
    "terragrunt graph state rm x",
)

# R-34b known false negatives (B6, B7, Risks), pinned clear: (shell, command).
STATE_FALSE_NEGATIVES = (
    ("bash", "cp terraform.tfstate backup/"),
    ("powershell", "Copy-Item -Destination terraform.tfstate -Path x"),
    ("bash", "git -C terraform.tfstate.d rm x"),
    ("bash", "rm $F"),
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
    # round 4: an unknown option may have swallowed a subcommand crew cannot read.
    ("terraform --unknown $SUB x", "tf-sub-unseen"),
    ("terragrunt --unknown-flag $SUB x", "tf-sub-unseen"),
    ("terragrunt run --unknown-flag $SUB x", "tf-sub-unseen"),
    # round 5: a quoted target the segment never closes is unseen (the `;`
    # inside the quotes cut the segment: quote-blind).
    ('terraform <<< "a; b" state rm x', "redirect-target-unseen"),
    ('terraform state list > "a b', "redirect-target-unseen"),
    # round 5: everything after the head is a comment.
    ("terraform # state rm x", "tf-sub-unseen"),
    ("terraform state list > # out.txt", "redirect-target-unseen"),
    # round 6: a quote opened inside the target and never closed.
    ("terraform <<< it's state list", "redirect-target-unseen"),
    (r'terraform state list > "a\"', "redirect-target-unseen"),
    # R-34b: a state word under a head crew does not list, or only as an
    # option value under a read head, or an unexpanded write target.
    ("chmod 600 terraform.tfstate", "tfstate-head-unseen"),
    ("sed -n p terraform.tfstate", "tfstate-head-unseen"),
    ("$CMD terraform.tfstate", "tfstate-head-unseen"),
    ("git stash push terraform.tfstate", "tfstate-git-unseen"),
    ("git diff --output=terraform.tfstate", "tfstate-option-value"),
    ("cat --x=terraform.tfstate", "tfstate-option-value"),
    ("jq '.serial=5' terraform.tfstate > $T", "tfstate-redirect-unseen"),
)

# Known over-reports pinned as hits (Risks).
KNOWN_OVER_REPORTS = (
    ("terragrunt --unknown-flag refresh plan", "tf-refresh"),
    # quote-blind raw pass: the `;` inside the message cuts the segment.
    ('git add . && git commit -m "x; terraform state rm y"', "tf-state-write"),
    # R-34b: a backup copy next to the state file reads as an overwrite.
    ("cp terraform.tfstate terraform.tfstate.bak", "tfstate-overwrite"),
    # R-34a review round 7 follow-up, left as main has it (R-34b approver
    # condition, option A): a comment stops only its own segment, so the
    # shell's comment-to-end-of-line is not followed. The fix is a later ticket.
    ("echo ok # x; terraform state rm x", "tf-state-write"),
)

# Known over-reports pinned as could-not-tell (B11): the parent spec's
# "known false positive" is could-not-tell on main, not hit. The raw
# reader's target `terraform.tfstate"` opens a quote the segment never
# closes, so the operator dangles.
KNOWN_OVER_REPORTS_CNT = (
    ('git add . && git commit -m "a > terraform.tfstate"', "redirect-target-unseen"),
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


@pytest.mark.parametrize("command,rule", KNOWN_OVER_REPORTS_CNT)
def test_known_over_reports_are_pinned_could_not_tell(command, rule):
    assert_cnt(crew_oneway, command, rule)


@pytest.mark.parametrize("shell,command", STATE_FALSE_NEGATIVES)
def test_state_false_negatives_are_pinned_clear(shell, command):
    assert_clear(crew_oneway, command, shell)


# (word, kind): B1, the state word.
STATE_WORDS = (
    ("terraform.tfstate", "word"),
    ("envs/prod/terraform.tfstate.backup", "word"),
    ("terraform.tfstate.d", "word"),
    ("terraform.tfstate.d/", "word"),
    ("infra\\TERRAFORM.TFSTATE", "word"),
    ("*.tfstate", "word"),
    ('"terraform.tfstate"', "word"),
    ("s3://b/env/terraform.tfstate", "word"),
    ("HEAD:terraform.tfstate", "word"),
    ("--output=terraform.tfstate", "option"),
    ("-state=x/terraform.tfstate", "option"),
    ("docs/tfstate-notes.md", None),
    ("terraform.tfstatex", None),
    ("terraform.tfstate/x.json", None),
    ("--output=out.json", None),
)


@pytest.mark.parametrize("word,kind", STATE_WORDS)
def test_the_state_word(word, kind):
    assert crew_oneway._state_kind(word) == kind


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
    # R-34b: a head-keyed row at every exec start is judged in constant time.
    ("terragrunt " + "exec -- cp " * LONG + "terraform.tfstate", "hit"),
    # the first git's subcommand is `exec` (unlisted): could-not-tell.
    ("terragrunt " + "exec -- git " * LONG + "rm terraform.tfstate " + "-x " * LONG,
     "could-not-tell"),
    ("terragrunt " + "exec -- aws " * LONG + "terraform.tfstate " + "-x " * LONG,
     "could-not-tell"),
)


@pytest.mark.parametrize("command,verdict", LONG_COMMANDS,
                         ids=[str(n) for n in range(len(LONG_COMMANDS))])
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

@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep", "WebFetch", "write", None, [], {}, 3,
                                  "bash"])
def test_a_payload_that_is_not_a_command(tool):
    payload = {"tool_name": tool, "tool_input": {"command": "terraform state rm x"}}
    assert crew_oneway.judge_payload(payload)["verdict"] == "not-a-command"
    assert crew_oneway.judge_payload("junk")["verdict"] == "not-a-command"


def test_a_read_of_a_state_file_is_not_a_command():
    payload = {"tool_name": "Read", "tool_input": {"file_path": "terraform.tfstate"}}
    assert crew_oneway.judge_payload(payload)["verdict"] == "not-a-command"


FILE_TOOL_PLACE = {"pass": "file-tool", "command": None, "word": None}

# (tool, tool_input): B8, a file tool naming a state file.
FILE_TOOL_BLOCK = (
    ("Write", {"file_path": "infra/terraform.tfstate", "content": "{}"}),
    ("Edit", {"file_path": "infra/terraform.tfstate", "old_string": "a", "new_string": "b"}),
    ("NotebookEdit", {"notebook_path": "infra/terraform.tfstate", "new_source": "x"}),
    ("MultiEdit", {"file_path": "main.tf",
                   "edits": [{"old_string": "a"}, {"file_path": "terraform.tfstate"}]}),
)
FILE_TOOL_ALLOW = (
    ("Write", {"file_path": "docs/tfstate-notes.md", "content": "x"}),
    ("NotebookEdit", {"notebook_path": "nb/analysis.ipynb"}),
)
FILE_TOOL_UNSEEN = (
    ("Write", {"content": "x"}),
    ("Write", {"file_path": 123}),
    ("NotebookEdit", {}),
    ("MultiEdit", {"edits": "abc"}),
    ("Write", "not a dict"),
    ("Edit", None),
    ("MultiEdit", {"edits": 5, "file_path": ""}),
    ("MultiEdit", {"edits": [{"file_path": ["unhashable"]}, 7]}),
)


def _tool(tool, tool_input):
    return crew_oneway.judge_payload({"tool_name": tool, "tool_input": tool_input})


@pytest.mark.parametrize("tool,tool_input", FILE_TOOL_BLOCK)
def test_a_file_tool_writing_a_state_file_is_a_hit(tool, tool_input):
    got = _tool(tool, tool_input)
    assert got["verdict"] == "hit" and got["operations"] == [OP], got
    assert got["findings"] == [{"verdict": "hit", "rule": "tfstate-file-tool", "operation": OP,
                                **FILE_TOOL_PLACE}]


@pytest.mark.parametrize("tool,tool_input", FILE_TOOL_ALLOW)
def test_a_file_tool_writing_another_file_is_clear(tool, tool_input):
    got = _tool(tool, tool_input)
    assert got["verdict"] == "clear" and got["operations"] == [] and got["findings"] == []


@pytest.mark.parametrize("tool,tool_input", FILE_TOOL_UNSEEN)
def test_a_file_tool_with_no_readable_path_is_could_not_tell(tool, tool_input):
    got = _tool(tool, tool_input)
    assert got["verdict"] == "could-not-tell" and got["operations"] == [OP], got
    assert rules(got) == ["file-tool-path-unseen"]


def test_the_file_tool_paths_are_scope_guards():
    tool_input = {"file_path": "a.tf", "notebook_path": "b.ipynb",
                  "edits": [{"file_path": "c.tfstate"}, {"file_path": "a.tf"}, "x",
                            {"file_path": "d.md"}]}
    want = scope_guard.targets({"tool_input": tool_input})
    assert want == ["a.tf", "b.ipynb", "c.tfstate", "d.md"]
    assert crew_oneway._tool_paths(tool_input) == want
    for tool_input in ({}, {"file_path": ""}, {"edits": []}, {"notebook_path": "n"}):
        assert crew_oneway._tool_paths(tool_input) == scope_guard.targets(
            {"tool_input": tool_input})


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
    (["--unknown-flag", "$SUB", "x"], (2, [1])),
    (["--working-dir", "$DIR", "plan"], (2, [])),
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
    # an fd copy ends where its word ends; glued to more, `>&` takes the word.
    ("a >&2list b", [seg(["a", "b"], [(">&", "2list")])]),
    ("a 2>&1x b", [seg(["a", "b"], [("2>&", "1x")])]),
    ("a >&-x b", [seg(["a", "b"], [(">&", "-x")])]),
    ("a >&f", [seg(["a"], [(">&", "f")])]),
    ("a >&2 list", [seg(["a", "list"])]),
    ("(a >&2)", [seg(["a"])]),
    ("a >&2>f", [seg(["a"], [(">", "f")])]),
    ('x "a >&2" b', [seg(["x", "a", "b"])]),
    ("a >&2`b`", [seg(["a", "`b`"])]),
    # round 5: a quoted empty word is a target, never a word.
    ('cat <<< "" x', [seg(["cat", "x"], [("<<<", "")])]),
    ("cat <<< '' x", [seg(["cat", "x"], [("<<<", "")])]),
    ('a > "" b', [seg(["a", "b"], [(">", "")])]),
    ('a "" b', [seg(["a", "b"])]),
    ("(a >)", [seg(["a"], dangling=[">"])]),
    # a target that opens a quote runs to the token that closes it.
    ('cat <<< "a b" x', [seg(["cat", "x"], [("<<<", "a b")])]),
    # R-34b (F1): the whitespace between a target's tokens is the command's own.
    ("cat <<< 'a  b c' x", [seg(["cat", "x"], [("<<<", "a  b c")])]),
    ("echo x >'a\tb.tfstate'", [seg(["echo", "x"], [(">", "a\tb.tfstate")])]),
    ('a > "b  >  c" d', [seg(["a", "d"], [(">", "b  >  c")])]),
    ('cat <<< "a" x', [seg(["cat", "x"], [("<<<", "a")])]),
    ('cat <<< "a b', [seg(["cat"], dangling=["<<<"])]),
    ('cat <<< "a # b" x', [seg(["cat", "x"], [("<<<", "a # b")])]),
    # round 6: quotes are followed through the whole target.
    (r'cat <<< "a\" b" x', [seg(["cat", "x"], [("<<<", r'a\" b')])]),
    ('cat <<< a" b" x', [seg(["cat", "x"], [("<<<", 'a" b')])]),
    (r"cat <<< a\ b x", [seg(["cat", "x"], [("<<<", r"a\ b")])]),
    ("cat <<< a\\", [seg(["cat"], [("<<<", "a\\")])]),
    (r"cat <<< a\ >f x", [seg(["cat", "x"], [("<<<", "a\\"), (">", "f")])]),
    (r"cat <<< a\>f x", [seg(["cat", "x"], [("<<<", r"a\>f")])]),
    ("cat <<< 'a\\' x", [seg(["cat", "x"], [("<<<", "a\\")])]),
    ("""cat <<< 'b " c' x""", [seg(["cat", "x"], [("<<<", 'b " c')])]),
    ("cat <<< it's x", [seg(["cat"], dangling=["<<<"])]),
    # round 6: an operator inside a quoted target is put back as it stood.
    ('a >"b>c" d', [seg(["a", "d"], [(">", "b>c")])]),
    ('a > "b > c" d', [seg(["a", "d"], [(">", "b > c")])]),
    ('a > "b >c" d', [seg(["a", "d"], [(">", "b >c")])]),
    ('a > "b> c" d', [seg(["a", "d"], [(">", "b> c")])]),
    ('a >"b 2>&1 c" d', [seg(["a", "d"], [(">", "b 2>&1 c")])]),
    ('a >"b>|c" d', [seg(["a", "d"], [(">", "b>|c")])]),
    ('a >"b<<<c" >>e', [seg(["a"], [(">", "b<<<c"), (">>", "e")])]),
    # the words stop at a comment.
    ("a b # c > d", [seg(["a", "b"])]),
    ("a b #c", [seg(["a", "b"])]),
    ("a b#c", [seg(["a", "b#c"])]),
    ('a "#" b', [seg(["a", "#", "b"])]),
    ("a > # f", [seg(["a"], dangling=[">"])]),
    ("# a b", []),
    ("a # b; c", [seg(["a"]), seg(["c"])]),
)

PS_READER_ROWS = (
    ("a *>&1", [seg(["a"])]),
    ("a *>&1 b", [seg(["a", "b"])]),
    ("a *> f", [seg(["a"], [("*>", "f")])]),
    ("a *>> f", [seg(["a"], [("*>>", "f")])]),
    ("a 3>&1", [seg(["a"])]),
    ("a x*>&1", [seg(["a", "x*"])]),
    ("a b # c *> d", [seg(["a", "b"])]),
    ('a *> "" b', [seg(["a", "b"], [("*>", "")])]),
    # round 6: powershell escapes with a backtick; a backslash escapes nothing.
    ('a *> "b`" c" d', [seg(["a", "d"], [("*>", 'b`" c')])]),
    ('a *> "b\\" c', [seg(["a", "c"], [("*>", "b\\")])]),
    ('a *>"b*>c" d', [seg(["a", "d"], [("*>", "b*>c")])]),
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
    # R-34b: what the plain pass hands the head-keyed rows.
    ("bash", "rm terraform.tfstate", [["rm", "terraform.tfstate"]]),
    ("bash", "cp a terraform.tfstate", [["cp", "a", "terraform.tfstate"]]),
    ("bash", "sed -i s/a/b/ terraform.tfstate", [["sed", "-i", "s/a/b/", "terraform.tfstate"]]),
    ("bash", "chmod 600 terraform.tfstate", [["chmod", "600", "terraform.tfstate"]]),
    ("powershell", "Remove-Item terraform.tfstate", [["Remove-Item", "terraform.tfstate"]]),
    ("bash", "git rm terraform.tfstate", [["git", "rm", "terraform.tfstate"]]),
    ("bash", "git -C infra rm terraform.tfstate",
     [["git", "-C", "infra", "rm", "terraform.tfstate"]]),
    ("bash", "git diff --output=terraform.tfstate",
     [["git", "diff", "--output=terraform.tfstate"]]),
    ("bash", 'git commit -m "a > terraform.tfstate"',
     [["git", "commit", "-m", "a > terraform.tfstate"]]),
    ("bash", 'echo "a>terraform.tfstate"', [["echo", "a>terraform.tfstate"]]),
    ("bash", "echo {} > terraform.tfstate", None),
    ("bash", "echo {} >terraform.tfstate", None),
    ("bash", "echo {} &> terraform.tfstate", None),
    ("bash", "cat < terraform.tfstate", None),
    ("bash", "jq . x.json | tee terraform.tfstate", None),
)


@pytest.mark.parametrize("shell,command,expected", PLAIN_PINS)
def test_plain_commands_pin(shell, command, expected):
    assert crew_gitallow.plain_commands(command, shell) == expected


def test_gitallow_helper_pins():
    """B6 reads git's subcommand and globals through these as they stand."""
    assert crew_gitallow.subcommand(["-C", "infra", "rm", "terraform.tfstate"]) == "rm"
    assert crew_gitallow._global_split(["-C", "infra", "rm", "terraform.tfstate"]) == (
        ["-C", "infra"], 2)
    assert crew_gitallow.subcommand(["commit", "-m", "x"]) == "commit"
    assert crew_gitallow.subcommand(["Rm", "x"]) is None
    assert crew_gitallow.subcommand(["$X", "rm"]) is None
    assert crew_gitallow.UNSEEN is None


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
    for command, _ in COULD_NOT_TELL + KNOWN_OVER_REPORTS + KNOWN_OVER_REPORTS_CNT:
        names.update(run(crew_oneway, command)["operations"])
    for tool, tool_input in FILE_TOOL_BLOCK + FILE_TOOL_UNSEEN:
        names.update(_tool(tool, tool_input)["operations"])
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

TARGETS = ("aws_s3_bucket.x", "x.tfstate", "out.txt", "envs/prod/terraform.tfstate")
OUTPUT_LINES = (
    "terraform state rm aws_s3_bucket.x > out.txt",
    "cd infra && terraform state push x.tfstate 2> out.txt",
    "terraform import aws_s3_bucket.x b >> out.txt",
    "rm envs/prod/terraform.tfstate",
    "echo {} > envs/prod/terraform.tfstate",
)
OUTPUT_PAYLOAD = {"tool_name": "Write",
                  "tool_input": {"file_path": "envs/prod/terraform.tfstate", "content": "{}"}}


def test_no_finding_carries_a_word_of_the_command():
    for command in OUTPUT_LINES:
        shown = json.dumps(run(crew_oneway, command))
        for target in TARGETS:
            assert target not in shown, (command, shown)
    shown = json.dumps(crew_oneway.judge_payload(OUTPUT_PAYLOAD))
    assert '"hit"' in shown and "tfstate\"" not in shown and "envs" not in shown, shown


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


def test_the_module_never_calls_tf_skip_options():
    """A12: the helper's one-step reading is restated in `_takes_value` and
    pinned to it at every index above; the module itself never calls it."""
    names = {node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)
             for node in ast.walk(ast.parse(source()))}
    assert "tf_skip_options" not in names
    assert {"_TF_GLOBAL_VALUE_OPTS", "_TF_GLOBAL_FLAG_OPTS", "_TF_OPS", "_HOLE"} <= names


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


# What a child Python needs to start; nothing else of this process's
# environment reaches the probes (no tokens, no PYTHONPATH, no crew settings).
_ENV_KEPT = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC")


def _isolated_env(home):
    env = {key: value for key, value in os.environ.items() if key.upper() in _ENV_KEPT}
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR"):
        env[key] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_the_probes_inherit_no_setting_from_this_process(monkeypatch, tmp_path):
    monkeypatch.setenv("CREW_R34A_CANARY", "1")
    monkeypatch.setenv("PYTHONPATH", "nowhere")
    env = _isolated_env(tmp_path)
    assert "CREW_R34A_CANARY" not in env and "PYTHONPATH" not in env
    assert {key.upper() for key in env} <= set(_ENV_KEPT) | {
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
        "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING"}


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
    # an integer longer than int() converts is still JSON: the field is not
    # read, so the verdict is the command's.
    done = cli("payload", stdin=payload[:-1] + ', "n": ' + "9" * 5000 + "}")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "hit", done.stderr[-300:]
    done = cli("payload", stdin='{"tool_name": "Bash", "tool_input": {"command": 12}}')
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "could-not-tell"
    # JSON nested deeper than this Python reads (RecursionError on 3.11) is
    # still a judgement: exit 0 and a verdict that is not `clear` or `hit`.
    for deep in ("[" * 1500 + "]" * 1500, "[" * 200000 + "]" * 200000):
        done = cli("payload", stdin=deep)
        assert done.returncode == 0, done.stderr[-300:]
        assert json.loads(done.stdout)["verdict"] in ("could-not-tell", "not-a-command")
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


def case_block_fd_copy_glued_to_a_word(mod):
    assert_hit(mod, "terraform state >&2list rm x.y", "tf-state-write")


def case_cnt_swallowed_unseen_sub(mod):
    assert_cnt(mod, "terraform --unknown $SUB x", "tf-sub-unseen")


def case_block_empty_here_string(mod):
    assert_hit(mod, 'terraform <<< "" state rm x', "tf-state-write")
    assert mod.raw_segments('cat <<< "" x') == [seg(["cat", "x"], [("<<<", "")])]


def case_block_quoted_here_string_with_a_space(mod):
    assert_hit(mod, 'terraform <<< "a b" state rm x', "tf-state-write")


def case_cnt_unclosed_quoted_target(mod):
    assert_cnt(mod, 'terraform <<< "a; b" state rm x', "redirect-target-unseen")


def case_block_escaped_quote_in_target(mod):
    assert_hit(mod, r'terraform <<< "a\" b" state rm x', "tf-state-write")
    assert_hit(mod, 'terraform *> "a`" b" state rm x', "tf-state-write", shell="powershell")


def case_block_quote_opened_inside_target(mod):
    assert_hit(mod, 'terraform <<< a" b" state rm x', "tf-state-write")


def case_allow_escaped_space_in_target(mod):
    assert_clear(mod, r"terraform <<< x\ state rm y")


def case_reader_operator_inside_quoted_target(mod):
    assert mod.raw_segments('a >"b>c" d') == [seg(["a", "d"], [(">", "b>c")])]
    assert mod.raw_segments('a > "b > c" d') == [seg(["a", "d"], [(">", "b > c")])]


def case_block_help_in_a_comment(mod):
    assert_hit(mod, "terraform state rm x # -help", "tf-state-write")
    assert_hit(mod, "terraform state rm x # -help", "tf-state-write", shell="powershell")


def case_cnt_comment_as_target(mod):
    assert_cnt(mod, "terraform state list > # out.txt", "redirect-target-unseen")


def case_allow_quoted_hash_then_help(mod):
    assert_clear(mod, 'terraform state rm x "#" -help')
    assert mod.raw_segments('a "#" b') == [seg(["a", "#", "b"])]


# R-34b cases.

def case_allow_cp_source(mod):
    assert_clear(mod, "cp terraform.tfstate /tmp/inspect.json")


def case_block_redirect(mod):
    assert_hit(mod, "echo {} > terraform.tfstate", "tfstate-redirect")


def case_cnt_other_head(mod):
    assert_cnt(mod, "chmod 600 terraform.tfstate", "tfstate-head-unseen")


def case_block_write_tool(mod):
    got = mod.judge_payload({"tool_name": "Write",
                             "tool_input": {"file_path": "infra/terraform.tfstate"}})
    assert got["verdict"] == "hit", got


def case_block_git_rm(mod):
    assert_hit(mod, "git rm terraform.tfstate", "tfstate-git-remove")


def case_allow_git_diff(mod):
    assert_clear(mod, "git diff terraform.tfstate")


def case_allow_terraform_head_precedence(mod):
    assert_clear(mod, "terraform show terraform.tfstate")
    assert_clear(mod, "terraform plan -state=terraform.tfstate")


def case_block_glued_redirect(mod):
    assert_hit(mod, "echo {} >terraform.tfstate", "tfstate-redirect")
    assert_hit(mod, "echo {}>terraform.tfstate", "tfstate-redirect")
    assert_hit(mod, "echo {} 1>terraform.tfstate", "tfstate-redirect")


def case_allow_state_fd_copy(mod):
    assert_clear(mod, "cat terraform.tfstate 2>&1")


def case_allow_input_redirects(mod):
    assert_clear(mod, "cat < terraform.tfstate")
    assert_clear(mod, "cat <<< terraform.tfstate")


def case_allow_plain_pass_quoted_operator(mod):
    assert_clear(mod, 'git commit -m "a > terraform.tfstate"')
    assert_clear(mod, 'echo "a>terraform.tfstate"')


def case_allow_git_commit(mod):
    assert_clear(mod, 'git commit -m "stop tracking terraform.tfstate"')


def case_block_notebook_and_multiedit(mod):
    for tool, tool_input in FILE_TOOL_BLOCK[2:]:
        got = mod.judge_payload({"tool_name": tool, "tool_input": tool_input})
        assert got["verdict"] == "hit", (tool, got)


def case_cnt_write_tool_without_path(mod):
    got = mod.judge_payload({"tool_name": "Write", "tool_input": {"content": "x"}})
    assert got["verdict"] == "could-not-tell", got


def case_reader_target_whitespace(mod):
    assert mod.raw_segments("cat <<< 'a  b c' x") == [seg(["cat", "x"], [("<<<", "a  b c")])]


def case_block_redirect_state_before_expansion(mod):
    assert_hit(mod, 'cat x.json > "$D/terraform.tfstate"', "tfstate-redirect")


def case_block_inplace(mod):
    assert_hit(mod, "sed -i s/a/b/ terraform.tfstate", "tfstate-inplace")
    assert_hit(mod, "perl -pi -e s/a/b/ terraform.tfstate", "tfstate-inplace")


def case_block_exec_unwraps_a_state_head(mod):
    assert_hit(mod, "terragrunt exec -- rm terraform.tfstate", "tfstate-remove")


def case_cnt_option_value(mod):
    assert_cnt(mod, "git diff --output=terraform.tfstate", "tfstate-option-value")
    assert_cnt(mod, "cat --x=terraform.tfstate", "tfstate-option-value")


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
     '        if segment["dangling"] and verdict != HIT:\n',
     '        if segment["dangling"]:\n'
     '            out.append(_finding(COULD_NOT_TELL, "redirect-target-unseen", TF_STATE,\n'
     "                                word=None, **where))\n"
     "        if False:\n",
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
    ("R14 an fd copy takes the digit prefix of a longer word",
     'r"[<>]&(?:[0-9]+|-)" + _WORD_END + "|"', 'r"[<>]&(?:[0-9]+|-)|"',
     ("case_block_fd_copy_glued_to_a_word",)),
    ("R15 a `>&` glued to its word takes no target",
     '"|" + fd + _GLUED + r"|&>>?|"', 'r"|&>>?|"', ("case_block_fd_copy_glued_to_a_word",)),
    ("R16 an unreadable word after an unknown option is not an alternate",
     "    return args[j + 1] in AMBIGUOUS_SUBS or _unseen(args[j + 1])\n",
     "    return args[j + 1] in AMBIGUOUS_SUBS\n", ("case_cnt_swallowed_unseen_sub",)),
    ("R17 a quoted empty word dropped before the redirections are lifted",
     "        if token.strip(_STRIP) or any(quote in token for quote in _QUOTES):\n",
     "        if token.strip(_STRIP):\n", ("case_block_empty_here_string",)),
    ("R18 a quoted target ends at its first token",
     "        if quote is None and not skip and not glued:\n            break\n",
     "        break\n",
     ("case_block_quoted_here_string_with_a_space", "case_cnt_unclosed_quoted_target")),
    ("R19 a comment's words are read as arguments",
     "            if _comment(token):\n                break\n", "",
     ("case_block_help_in_a_comment",)),
    ("R20 a comment taken as a redirection's target",
     "tokens[index].startswith(_MARK) or _comment(tokens[index]):",
     "tokens[index].startswith(_MARK):", ("case_cnt_comment_as_target",)),
    ("R21 a quoted `#` starts a comment",
     '    return token.lstrip("()").startswith("#")\n',
     '    return token.strip(_STRIP).startswith("#")\n', ("case_allow_quoted_hash_then_help",)),
    ("R22 an escaped quote closes the target",
     "        elif char == escape:\n            skip = True\n", "",
     ("case_block_escaped_quote_in_target", "case_allow_escaped_space_in_target")),
    ("R23 only a quote that opens the target is followed",
     "        quote, skip = _quotes(piece, quote, skip, escape)\n",
     "        quote, skip = _quotes(piece if quote or piece[:1] in _QUOTES else \"\", quote, skip,\n"
     "                              escape)\n",
     ("case_block_quote_opened_inside_target",)),
    ("R24 powershell targets read with the bash escape",
     "        segment = _lift(piece, _ESCAPE[shell])\n", "        segment = _lift(piece)\n",
     ("case_block_escaped_quote_in_target",)),
    ("R25 an operator inside a quoted target keeps the reader's padding",
     "        gap = gap[after_mark:len(gap) - mark]\n", "",
     ("case_reader_operator_inside_quoted_target",)),
    ("R26 an operator inside a quoted target keeps the reader's marker",
     "            text, right = text[2:].translate(_SHOW), text[1] in \"23\"\n",
     "            right = text[1] in \"23\"\n",
     ("case_reader_operator_inside_quoted_target",)),
    # R-34b. The numbers are the parent spec's sabotage rows.
    ("6 every cp state word read as a write",
     "    if last is not None and info.kind[last]:\n",
     "    last = info.next_state[head + 1]\n    if True:\n",
     ("case_allow_cp_source",)),
    ("7 the write-target (redirection) row dropped",
     '        readings += [_write_reading(op, target, held) for op, target in segment["targets"]]\n',
     "", ("case_block_redirect", "case_block_glued_redirect")),
    ("8 any other head becomes clear",
     '    return (COULD_NOT_TELL, "tfstate-head-unseen", first)\n', "    return _CLEAR\n",
     ("case_cnt_other_head",)),
    ("9 the file-tool branch dropped",
     "    if isinstance(tool, str) and tool in FILE_TOOLS:\n        return _file_tool(payload)\n",
     "", ("case_block_write_tool",)),
    ("23 the whole git head clear on a state word",
     "        return _git_state(info, index)\n", "        return _CLEAR\n",
     ("case_block_git_rm",)),
    ("24 every git subcommand could-not-tell",
     "    if sub in GIT_READ_SUBS:\n",
     '    return (COULD_NOT_TELL, "tfstate-git-unseen", git_first)\n    if sub in GIT_READ_SUBS:\n',
     ("case_allow_git_diff", "case_block_git_rm")),
    ("25 the head-keyed rows applied to a terraform head",
     "                            else _judge_tf(scan, found[1], found[0] + 1))\n",
     "                            else _first_worst([_judge_tf(scan, found[1], found[0] + 1),\n"
     "                                               _state_head(scan.state_words(), start)]))\n",
     ("case_allow_terraform_head_precedence",)),
    ("27 an operator lifted only with whitespace on both sides",
     '        return f" {_MARK}{glue}{match.group(0).translate(_HIDE)} "\n',
     "        return match.group(0) if glue else "
     'f" {_MARK}{glue}{match.group(0).translate(_HIDE)} "\n',
     ("case_block_glued_redirect",)),
    ("28a an fd copy kept as an operator",
     "        if _FD_COPY_RE.fullmatch(operator):\n            continue\n", "",
     ("case_allow_state_fd_copy",)),
    ("28b every lifted target read as a write, input operators included",
     '    if ">" not in operator:\n        return _CLEAR\n', "",
     ("case_allow_input_redirects",)),
    ("35 the plain pass replaced by the raw pass",
     "    return _plain_pass(commands)\n", "    return _raw_pass(command, shell)\n",
     ("case_allow_plain_pass_quoted_operator",)),
    ("36 commit dropped from the git clear list",
     '    if sub == "commit":\n        return _CLEAR\n', "", ("case_allow_git_commit",)),
    ("39 only file_path read in a file-tool payload",
     '    found = [tool_input.get(key) for key in ("file_path", "notebook_path")] + (\n'
     '        [edit.get("file_path") for edit in edits if isinstance(edit, dict)]\n'
     "        if isinstance(edits, list) else [])\n",
     '    found = [tool_input.get("file_path")]\n',
     ("case_block_notebook_and_multiedit",)),
    ("40 a file tool with no readable path is clear",
     "    if not paths:\n", "    if not paths:\n        return _result([])\n",
     ("case_cnt_write_tool_without_path",)),
    ("F1 target tokens joined with one space",
     "        piece = text if not parts else gaps[index] + text\n",
     '        piece = text if not parts else " " + text\n',
     ("case_reader_target_whitespace",)),
    ("B3 the expansion test run before the state-word test",
     "    if _state_path(target):\n        return (HIT, \"tfstate-redirect\", None)\n",
     '    if _unseen(target):\n        return (COULD_NOT_TELL, "tfstate-redirect-unseen", None)\n'
     "    if _state_path(target):\n        return (HIT, \"tfstate-redirect\", None)\n",
     ("case_block_redirect_state_before_expansion",)),
    ("B5 the in-place bundle read as -i only",
     '_INPLACE_RE = re.compile(r"^(?:-[A-Za-z]*i.*|--in-place(?:=.*)?)$", re.S)',
     '_INPLACE_RE = re.compile(r"^(?:-i.*|--in-place(?:=.*)?)$", re.S)',
     ("case_block_inplace",)),
    ("B2 an exec start with another head is clear",
     "        scan.memo[start] = (_state_head(scan.state_words(), start) if found is None\n",
     "        scan.memo[start] = (_CLEAR if found is None\n",
     ("case_block_exec_unwraps_a_state_head",)),
    ("B5 a read head's option value read as a positional",
     "        if info.next_word[index + 1] < len(info.words):\n",
     "        if True:\n", ("case_cnt_option_value",)),
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
