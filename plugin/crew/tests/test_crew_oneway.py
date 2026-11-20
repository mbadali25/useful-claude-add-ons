"""R-34a, R-34b, R-34c: the one-way lane's command-text tripwire (`crew_oneway.py`), report-only.

R-34b adds state-file writes (redirections, head-keyed rows, the git table)
and file-tool payloads, all under the same operation, and keeps a recorded
redirection target's whitespace (F1). R-34c adds `delete-others-branch` and
`delete-others-worktree`, decided from a caller-supplied context; its path
rows run under `ntpath` and under `posixpath`.

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
import ntpath
import os
import posixpath
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
BR = crew_oneway.BRANCH
WT = crew_oneway.WORKTREE
# pylint: disable=protected-access


def source():
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


def run(mod, command, shell="bash", ctx=None):
    return mod.judge(command, shell, ctx)


def rules(result):
    return [f["rule"] for f in result["findings"]]


def _ops(op):
    return [op] if op else []


def assert_hit(mod, command, rule=None, shell="bash", op=OP, ctx=None):
    result = run(mod, command, shell, ctx)
    assert result["verdict"] == "hit", (command, result)
    assert result["operations"] == _ops(op), (command, result)
    if rule is not None:
        assert rule in rules(result), (command, result)
    return result


def assert_clear(mod, command, shell="bash", ctx=None):
    result = run(mod, command, shell, ctx)
    assert result["verdict"] == "clear", (command, result)
    assert result["operations"] == [], (command, result)
    return result


def assert_cnt(mod, command, rule=None, shell="bash", op=OP, ctx=None):
    result = run(mod, command, shell, ctx)
    assert result["verdict"] == "could-not-tell", (command, result)
    assert result["operations"] == _ops(op), (command, result)
    if rule is not None:
        assert rule in rules(result), (command, result)
    return result


# --- R-34c contexts: paths built through the path module under test (C6) ---------------------

OWN_BRANCHES = ["worktree-R-34", "feat/r-34-x"]


def _p(pathmod, *parts):
    return pathmod.join("C:\\" if pathmod is ntpath else "/", *parts)


def _without(ctx, key):
    return {k: v for k, v in ctx.items() if k != key}


def own(pathmod=os.path):
    """The default context `OWN`: cwd /w/r34, which is the one own worktree."""
    w34 = _p(pathmod, "w", "r34")
    return {"cwd": w34, "own_branches": list(OWN_BRANCHES), "own_worktrees": [w34]}


CONTEXTS = {
    "OWN": own,
    "OTHER": lambda p: dict(own(p), cwd=_p(p, "other", "repo")),
    "R34X": lambda p: dict(own(p), cwd=_p(p, "w", "r34x")),
    "SUB": lambda p: dict(own(p), cwd=_p(p, "w", "r34", "plugin", "crew")),
    "NO_CWD": lambda p: _without(own(p), "cwd"),
    "NO_WORKTREES": lambda p: _without(own(p), "own_worktrees"),
    "BRANCHES_STR": lambda p: dict(own(p), own_branches="worktree-R-34"),
    "EMPTY": lambda p: {},
    "NONE": lambda p: None,
}


def ctx_of(name, pathmod=os.path):
    return CONTEXTS[name](pathmod)


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
    ("bash", "exec -- terraform state rm x", "tf-state-write"),
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
    # review round 1: a target built from quoted and unquoted parts.
    ("bash", 'echo x > terra"form.tf"state', "tfstate-redirect"),
    ("bash", "echo x > 'terraform'.tfstate", "tfstate-redirect"),
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
    # review round 1: terragrunt's `--` is not the inner command's.
    ("bash", "terragrunt exec -- sed -i s/a/b/ terraform.tfstate", "tfstate-inplace"),
    ("bash", "sed -i -- s/a/b/ terraform.tfstate", "tfstate-inplace"),
    ("bash", "aws s3 cp -- x s3://b/terraform.tfstate", "tfstate-remote"),
    # R-34b (B6): the git table, state words after the subcommand.
    ("bash", "git rm terraform.tfstate", "tfstate-git-remove"),
    # a known over-report (`--cached` keeps the file), pinned here.
    ("bash", "git rm --cached terraform.tfstate", "tfstate-git-remove"),
    ("bash", "git -C infra rm terraform.tfstate", "tfstate-git-remove"),
    ("bash", "git mv terraform.tfstate old.tfstate", "tfstate-git-move"),
    ("bash", "git checkout -- terraform.tfstate", "tfstate-git-overwrite"),
    ("bash", "git restore terraform.tfstate", "tfstate-git-overwrite"),
    # review round 2 (B1, B5): after `--` the whole word is a positional.
    ("bash", "cp src -- -name.tfstate.bak=notes.txt", "tfstate-overwrite"),
    ("bash", "rm -- -name.tfstate.bak=notes.txt", "tfstate-remove"),
    ("bash", "git rm -- -name.tfstate.bak=notes.txt", "tfstate-git-remove"),
    # review round 2: the raw pass joins a word's quoted parts, and reads a
    # write target with its escapes taken out.
    ("bash", 'rm terra"form.tf"state > /dev/null', "tfstate-remove"),
    ("bash", r"echo x > terraform.tfstat\e", "tfstate-redirect"),
    ("powershell", "echo x > terraform.tfstat`e", "tfstate-redirect"),
    # F2 (allow-list): a `#` ends its line only after safe text. Each of
    # these runs the terraform command, and each is read as main reads it.
    ("bash", "echo ok # x\nterraform state rm x", "tf-state-write"),
    ("powershell", "echo ok # x\rterraform state rm x", "tf-state-write"),
    ("bash", "echo a#b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a#b; terraform state rm x", "tf-state-write"),
    ("bash", 'git commit -m "a # b"; terraform state rm x', "tf-state-write"),
    ("bash", r"echo a\ #b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo ok <# c #> ; terraform state rm x", "tf-state-write"),
    ("powershell", "echo ok <#c#>; terraform state rm x", "tf-state-write"),
    ("powershell", "echo ok <# a\n# b\n#> ; terraform state rm x", "tf-state-write"),
    ("bash", 'echo "$(echo "a # b")"; terraform state rm x', "tf-state-write"),
    ("powershell", 'echo "$(echo "a # b")"; terraform state rm x', "tf-state-write"),
    ("bash", 'echo "`echo "a # b"`"; terraform state rm x', "tf-state-write"),
    ("bash", r"echo $'a\'b # c'; terraform state rm x", "tf-state-write"),
    ("bash", 'gh pr create --body "$(printf "fixes #12")"; terraform state rm x',
     "tf-state-write"),
    ("bash", 'echo "${X:-"a # b"}"; terraform state rm x', "tf-state-write"),
    ("powershell", "echo ${a # b}; terraform state rm x", "tf-state-write"),
    ("powershell", "echo @'\na # b\n'@; terraform state rm x", "tf-state-write"),
    ("powershell", "echo \u201ca # b\u201d; terraform state rm x", "tf-state-write"),
    ("bash", r"echo a\>#b; terraform state rm x", "tf-state-write"),
    # the approver's three classes (comment 52770): an escaped separator
    # glued to the `#`, whitespace Python splits on and the shell does not,
    # and a declined `#` that holds a quote.
    ("bash", r"echo a\;#b; terraform state rm x", "tf-state-write"),
    ("bash", r"echo a\&#b; terraform state rm x", "tf-state-write"),
    ("bash", r"echo a\|#b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a`;#b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a`|#b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a\x1f#b; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a\x1c#b; terraform state rm x", "tf-state-write"),
    ("bash", "echo a\u00a0#b; terraform state rm x", "tf-state-write"),
    ("bash", "echo a\x0c#b; terraform state rm x", "tf-state-write"),
    ("bash", "echo a\x0b#b; terraform state rm x", "tf-state-write"),
    ("bash", "echo a\u3000#b; terraform state rm x", "tf-state-write"),
    ("bash", "echo a\\  # it's\necho 'x # y'; terraform state rm x", "tf-state-write"),
    ("powershell", "echo a`  # it's\necho 'x # y'; terraform state rm x", "tf-state-write"),
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
    # review round 1 (B5): every word after `--` is a positional.
    ("bash", "cat -- -report.tfstate"),
    ("bash", "git diff -- -report.tfstate"),
    ("bash", "terragrunt exec -- cat -- -report.tfstate"),
    ("bash", "cat -- -name.tfstate.bak=notes.txt"),
    # F2 (R-34a review round 7 follow-up): after safe text, a `#` comments
    # out the rest of its line, separators included.
    ("bash", "echo ok # x; terraform state rm x"),
    ("powershell", "echo ok # x; terraform state rm x"),
    ("powershell", "echo ok # x <# y; terraform state rm x"),
    ("bash", "echo ok # a\necho b # c; terraform state rm x"),
    ("bash", "# terraform state rm x"),
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
    # review round 1 (B3): the state word is a lifted input target.
    ("cat < terraform.tfstate > $OUT", "tfstate-redirect-unseen"),
    # review round 1 (B5): after `--`, `-i` is sed's program, not an option.
    ("sed -- -i terraform.tfstate", "tfstate-head-unseen"),
)

# Known over-reports pinned as hits (Risks).
KNOWN_OVER_REPORTS = (
    ("terragrunt --unknown-flag refresh plan", "tf-refresh"),
    # quote-blind raw pass: the `;` inside the message cuts the segment.
    ('git add . && git commit -m "x; terraform state rm y"', "tf-state-write"),
    # R-34b: a backup copy next to the state file reads as an overwrite.
    ("cp terraform.tfstate terraform.tfstate.bak", "tfstate-overwrite"),
    # F2: text outside the allow-list before the `#` keeps main's reading,
    # where a comment stops only its own segment (bash runs no terraform).
    ('echo "$(date)" # x; terraform state rm x', "tf-state-write"),
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
# Linear time is checked by growth, not by an absolute budget: a 2.0 s budget
# at 4000 repeats failed on CI's Linux 3.12 job with 16 xdist workers (4.75 to
# 7.05 s for a linear reading that takes under 1 s here), because a loaded
# runner slows every run. Four times the input takes about four times as long
# when the reading is linear and about sixteen times when it is quadratic
# (measured, R-34c fix round 1: 3.9-4.2x linear, 12.6-15.4x with C14's window
# removed); GROWTH_LIMIT sits between. Each size keeps the best of
# GROWTH_REPEATS interleaved runs, so a load spike in one run does not count
# and a steady load slows both sizes alike.
GROWTH_SMALL, GROWTH_BIG = LONG // 16, LONG // 4
GROWTH_LIMIT = 8.0
GROWTH_REPEATS = 3


def _growth(judge_at, small=GROWTH_SMALL, big=GROWTH_BIG):
    """How many times longer `judge_at(big)` takes than `judge_at(small)`,
    best run against best run."""
    best = {small: float("inf"), big: float("inf")}
    for _ in range(GROWTH_REPEATS):
        for size in best:
            started = time.perf_counter()
            judge_at(size)
            best[size] = min(best[size], time.perf_counter() - started)
    return best[big] / max(best[small], 1e-6)


def assert_grows_linearly(judge_at, small=GROWTH_SMALL, big=GROWTH_BIG):
    growth = _growth(judge_at, small, big)
    assert growth < GROWTH_LIMIT, f"{big / small:.0f}x the input took {growth:.1f}x"


def assert_linear(mod, make, ctx=None):
    assert_grows_linearly(lambda size: run(mod, make(size), ctx=ctx))


# Quadratic reading took 3.9 s at 2000 repeats in review round 3; each row is
# built at any repeat count, its verdict read at LONG.
LONG_COMMANDS = (
    (lambda n: "echo " + "--unknown exec " * n + "terraform state rm x", "clear"),
    (lambda n: "terragrunt " + "--unknown exec " * n + "terraform state rm x", "hit"),
    (lambda n: "terragrunt " + "--unknown state " * n + "rm x", "hit"),
    (lambda n: "terragrunt " + "exec --unknown " * n + "terraform plan", "could-not-tell"),
    (lambda n: "terraform " + "-x " * n + "state list", "clear"),
    # R-34b: a head-keyed row at every exec start is judged in constant time.
    (lambda n: "terragrunt " + "exec -- cp " * n + "terraform.tfstate", "hit"),
    # the first git's subcommand is `exec` (unlisted): could-not-tell.
    (lambda n: "terragrunt " + "exec -- git " * n + "rm terraform.tfstate " + "-x " * n,
     "could-not-tell"),
    (lambda n: "terragrunt " + "exec -- aws " * n + "terraform.tfstate " + "-x " * n,
     "could-not-tell"),
)


@pytest.mark.parametrize("make,verdict", LONG_COMMANDS,
                         ids=[str(n) for n in range(len(LONG_COMMANDS))])
def test_a_long_command_is_judged_in_linear_time(make, verdict):
    assert run(crew_oneway, make(LONG))["verdict"] == verdict
    assert_linear(crew_oneway, make)


# R-34c: every git start reads at most GIT_WINDOW words after its subcommand
# (C14), so a chain of git deletes stays linear. The first row is the spec's:
# the shell builtin `exec` before each `git` (a head prefix), an `exec` start
# at every `git`; the third strips a long run of prefixes at every start.
GIT_LONG_COMMANDS = (
    (lambda n: "terragrunt exec -- " + "exec git branch -D a " * n, "hit"),
    (lambda n: "terragrunt " + "exec -- git branch -D a " * n, "hit"),
    (lambda n: "terragrunt exec -- " + "exec " * n + "git branch -D a", "hit"),
    (lambda n: "git branch -D " + "worktree-R-34 " * n, "could-not-tell"),
    (lambda n: "git worktree remove " + "-f " * n + "/w/r35", "could-not-tell"),
    # fix round 2: every `exec` start strips its prefixes down to one git head
    # whose globals are long, so that head is read once, not once per start.
    (lambda n: "terragrunt exec -- " + "exec " * n + "git " + "-c a.b=c " * n
     + "branch -D feature-x", "hit"),
    # fix round 3: a stack of relative `-C x` is joined once, not re-normalised
    # at each `-C` (that was quadratic in the path's length).
    (lambda n: "git " + "-C x " * n + "branch -D feature-x", "hit"),
)


@pytest.mark.parametrize("make,verdict", GIT_LONG_COMMANDS,
                         ids=[str(n) for n in range(len(GIT_LONG_COMMANDS))])
@pytest.mark.parametrize("ctx", ["OWN", "NONE"])
def test_a_long_git_command_is_judged_in_linear_time(make, verdict, ctx):
    got = run(crew_oneway, make(LONG), ctx=ctx_of(ctx))["verdict"]
    assert got == (verdict if ctx == "OWN" else "could-not-tell")
    assert_linear(crew_oneway, make, ctx_of(ctx))


@pytest.mark.parametrize("repeat", [1, 100, 300, 2000])
def test_a_long_exec_chain_gives_a_verdict(repeat):
    assert_hit(crew_oneway, "terragrunt exec -- " * repeat + "terraform state rm x",
               "tf-state-write")
    assert_clear(crew_oneway, "terragrunt exec -- " * repeat + "terraform state list")
    assert_cnt(crew_oneway, "terragrunt exec --unknown-flag " * repeat + "terraform plan",
               "tg-exec-unseen")


def test_git_reads_a_window_of_its_globals():
    """Review round 2: a git start reads its globals, not the rest of the
    command, so chained `terragrunt exec -- git` starts stay linear."""
    words = ["git", "-C", "d", "rm", "x"] + ["y"] * 10000
    args, split = crew_oneway._git_args(crew_oneway._StateWords(words), 0)
    assert split == 2 and len(args) < 64
    words = ["git"] + ["-x"] * 100 + ["rm", "terraform.tfstate"]
    args, split = crew_oneway._git_args(crew_oneway._StateWords(words), 0)
    assert split == 100 and crew_gitallow.subcommand(args) == "rm"
    assert_hit(crew_oneway, " ".join(words), "tfstate-git-remove")


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


def test_context_does_not_change_a_terraform_row():
    """R-34c narrows R-34a's "accepted and ignored": no terraform row reads it."""
    for ctx in (None, {}, {"ownership": "own"}, "x", 1, own()):
        assert_clear(crew_oneway, "terraform state list", ctx=ctx)
        assert run(crew_oneway, "terraform state rm x", ctx=ctx)["verdict"] == "hit"


# --- R-34c: branch and worktree deletes ------------------------------------------------------

DEL = "branch-delete-other"
WDEL = "worktree-remove-other"

# (shell, command, operation, rule, context)
GIT_BLOCK = (
    ("bash", "git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -d feature-x", BR, DEL, "OWN"),
    ("bash", "git branch --delete feature-x", BR, DEL, "OWN"),
    ("bash", "git branch --del feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -fD feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -D worktree-R-34 feature-x", BR, DEL, "OWN"),
    ("bash", "git -C x branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "git -c core.x=y branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -D feature-x", BR, DEL, "OTHER"),
    ("bash", "git push origin --delete feature-x", BR, DEL, "OWN"),
    ("bash", "git push --delete origin feature-x", BR, DEL, "OWN"),
    ("bash", "git push -d origin feature-x", BR, DEL, "OWN"),
    ("bash", "git push origin feature-x --delete", BR, DEL, "OWN"),
    ("bash", "git push -o ci.skip --delete origin feature-x", BR, DEL, "OWN"),
    # an attached `-o` value is not followed by one (review round 1).
    ("bash", "git push -ofoo origin :feature-x", BR, DEL, "OWN"),
    ("bash", "git push -fo ci.skip origin :feature-x", BR, DEL, "OWN"),
    ("bash", "git push origin :feature-x", BR, DEL, "OWN"),
    ("bash", "git push origin +:feature-x", BR, DEL, "OWN"),
    ("bash", "git push origin --delete refs/heads/feature-x", BR, DEL, "OWN"),
    ("bash", "git update-ref -d refs/heads/feature-x", BR, DEL, "OWN"),
    # git reads update-ref's options anywhere before `--`.
    ("bash", "git update-ref refs/heads/feature-x -d", BR, DEL, "OWN"),
    ("bash", "git update-ref -m why -d refs/heads/feature-x", BR, DEL, "OWN"),
    ("bash", "git update-ref -mwhy -d refs/heads/feature-x", BR, DEL, "OWN"),
    ("bash", "git fetch && git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "for b in a b; do git branch -D feature-x; done", BR, DEL, "OWN"),
    ("bash", "if true; then git branch -D feature-x; fi", BR, DEL, "OWN"),
    ("bash", "! git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "command git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "exec git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -D feature-x > out.txt", BR, DEL, "OWN"),
    ("bash", "terragrunt exec -- git branch -D feature-x", BR, DEL, "OWN"),
    # a branch option's value is the next word whatever it is (fix round 2).
    ("bash", "git branch --sort -- -D feature-x", BR, DEL, "OWN"),
    ("powershell", "git.exe branch -D feature-x", BR, DEL, "OWN"),
    # the `--` that ends exec's (command's, env's, sudo's) options (fix round 3).
    ("bash", "exec -- git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "terragrunt exec -- exec -- git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "command -- git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "env -- git branch -D feature-x", BR, DEL, "OWN"),
    ("bash", "sudo -- git worktree remove ../r35", WT, WDEL, "OWN"),
    # --no-delete clears -d's bit only, and a value is never one (fix round 3).
    ("bash", "git branch -D --no-delete feature-x", BR, DEL, "OWN"),
    ("bash", "git branch --no-delete -d feature-x", BR, DEL, "OWN"),
    ("bash", "git branch -d --sort --no-delete feature-x", BR, DEL, "OWN"),
    ("bash", "git worktree remove ../r35", WT, WDEL, "OWN"),
    ("bash", "git worktree remove --force /w/r35", WT, WDEL, "OWN"),
    ("bash", "git -C ../r35 worktree remove .", WT, WDEL, "OWN"),
    ("bash", "git -C .. -C r35 worktree remove .", WT, WDEL, "OWN"),
    ("bash", "git worktree list; git worktree remove ../r35", WT, WDEL, "OWN"),
    ("bash", "if true; then true; else git worktree remove ../r35; fi", WT, WDEL, "OWN"),
)

# (shell, command, operation, rule, context)
GIT_CNT = (
    # an own name where the command does not run inside an own worktree.
    ("bash", "git branch -D worktree-R-34", BR, "branch-own-outside", "OTHER"),
    ("bash", "git branch -D worktree-R-34", BR, "branch-own-outside", "R34X"),
    ("bash", "git branch -D worktree-R-34", BR, "branch-own-outside", "NO_CWD"),
    ("bash", "git -C ../other branch -D worktree-R-34", BR, "branch-own-outside", "OWN"),
    ("bash", "git push origin --delete feat/r-34-x", BR, "branch-own-outside", "OTHER"),
    # no own list.
    ("bash", "git branch -D feature-x", BR, "branch-owner-unseen", "EMPTY"),
    ("bash", "git branch -D feature-x", BR, "branch-owner-unseen", "NONE"),
    ("bash", "git branch -D feature-x", BR, "branch-owner-unseen", "BRANCHES_STR"),
    ("bash", "git worktree remove ../r35", WT, "worktree-owner-unseen", "NO_WORKTREES"),
    # an expansion or a glob.
    ("bash", 'git branch -D "$B"', BR, "branch-target-unseen", "OWN"),
    ("powershell", "git branch -D %B%", BR, "branch-target-unseen", "OWN"),
    ("bash", "git branch -D feat*", BR, "branch-target-unseen", "OWN"),
    ("bash", 'git update-ref -d "$R"', BR, "branch-target-unseen", "OWN"),
    ("bash", "git worktree remove $W", WT, "worktree-target-unseen", "OWN"),
    ("bash", "git worktree remove ~/w/r35", WT, "worktree-target-unseen", "OWN"),
    ("bash", 'for b in $(git branch --merged); do git branch -D "$b"; done', BR,
     "branch-target-unseen", "OWN"),
    # a repository crew cannot see.
    ("bash", "git --git-dir=/o/.git branch -D worktree-R-34", BR, "git-repo-unseen", "OWN"),
    ("bash", "git --git-dir /o/.git branch -D feature-x", BR, "git-repo-unseen", "OWN"),
    ("bash", "git --work-tree=/o worktree remove .", WT, "git-repo-unseen", "OWN"),
    ("bash", "git --namespace=n branch -D feature-x", BR, "git-repo-unseen", "OWN"),
    ("bash", "git --namespace n branch -D feature-x", BR, "git-repo-unseen", "OWN"),
    ("bash", "GIT_DIR=/o/.git git branch -D worktree-R-34", BR, "git-repo-unseen", "OWN"),
    ("bash", "env GIT_WORK_TREE=/o git worktree remove .", WT, "git-repo-unseen", "OWN"),
    ("bash", "GIT_WORK_TREE=/o git branch -D worktree-R-34", BR, "git-repo-unseen", "OWN"),
    ("bash", "GIT_NAMESPACE=n git branch -D worktree-R-34", BR, "git-repo-unseen", "OWN"),
    # a global the raw pass may have misread (fix round 2).
    ("bash", 'git --git-"dir"=/o/.git branch -D worktree-R-34 > out.txt', BR, "git-repo-unseen",
     "OWN"),
    # a word after the subcommand the raw pass may have misread (fix round 2).
    ("bash", 'git push -o "" origin :feature-x > out.txt', BR, "branch-target-unseen", "OWN"),
    ("bash", 'git worktree remove /w/r34" backup" > out.txt', WT, "worktree-target-unseen",
     "OWN"),
    ("bash", 'git worktree remove "/w/r34 backup" > out.txt', WT, "worktree-target-unseen",
     "OWN"),
    ("bash", 'git wo"rktree" remove /w/r35 > out.txt', None, "git-sub-unseen", "OWN"),
    # a bracket inside quotes is part of the word, which the raw pass strips:
    # `(worktree-R-34)` and `/w/r34)` are another branch and path (fix round 3).
    ("bash", "git branch -D '(worktree-R-34)' > out.txt", BR, "branch-target-unseen", "OWN"),
    ("bash", 'git branch -D "worktree-R-34)" > out.txt', BR, "branch-target-unseen", "OWN"),
    ("bash", "git worktree remove '/w/r34)' > out.txt", WT, "worktree-target-unseen", "OWN"),
    ("bash", "git worktree remove '(/w/r34)' > out.txt", WT, "worktree-target-unseen", "OWN"),
    # a brace the shell keeps as part of the word.
    ("bash", "git branch -D worktree-R-34} > out.txt", BR, "branch-target-unseen", "OWN"),
    ("bash", 'git -C "$D" branch -D worktree-R-34', BR, "git-repo-unseen", "OWN"),
    ("bash", "git -C %D% branch -D feature-x", BR, "git-repo-unseen", "OWN"),
    # C5 beats the tag rule, the --prune row and an unreadable ref (review round 1).
    ("bash", "git --namespace=n push --delete origin refs/tags/v1", BR, "git-repo-unseen",
     "OWN"),
    ("bash", "git --namespace=n push --prune origin", BR, "git-repo-unseen", "OWN"),
    ("bash", 'git --namespace=n update-ref -d "$R"', BR, "git-repo-unseen", "OWN"),
    # no directory to resolve a worktree path against.
    ("bash", "git worktree remove /w/r35", WT, "worktree-owner-unseen", "NO_CWD"),
    ("bash", "git -C ../r35 worktree remove .", WT, "worktree-owner-unseen", "NO_CWD"),
    # no target.
    ("bash", "git branch -D", BR, "branch-target-unseen", "OWN"),
    ("bash", "git push --delete origin", BR, "branch-target-unseen", "OWN"),
    ("bash", "git worktree remove", WT, "worktree-target-unseen", "OWN"),
    # an empty path would resolve to the cwd (review round 1).
    ("bash", 'git worktree remove ""', WT, "worktree-target-unseen", "OWN"),
    ("bash", "git push --prune origin", BR, "push-prune", "OWN"),
    ("bash", "git push --mirror origin", BR, "push-prune", "OWN"),
    ("bash", "git $SUB -D x", None, "git-sub-unseen", "OWN"),
    # C3/C13: git-sub-unseen, no operation, even beside a state word.
    ("bash", "git $SUB terraform.tfstate", None, "git-sub-unseen", "OWN"),
    ("bash", "git branch -D " + "worktree-R-34 " * 300, BR, "git-window-exceeded", "OWN"),
    ("bash", "git worktree remove " + "-f " * 300 + "/w/r34", WT, "git-window-exceeded", "OWN"),
)

# (shell, command, context)
GIT_ALLOW = (
    ("bash", "git branch -D worktree-R-34", "OWN"),
    ("bash", "git branch -D worktree-R-34", "SUB"),
    ("bash", "git branch -d feat/r-34-x", "OWN"),
    ("bash", "git -C /w/r34 branch -D worktree-R-34", "OWN"),
    ("bash", "git -c core.x=y branch -D worktree-R-34", "OWN"),
    ("bash", "for b in a b; do git branch -D worktree-R-34; done", "OWN"),
    ("bash", "git push origin --delete feat/r-34-x", "OWN"),
    ("bash", "git push --delete origin feat/r-34-x", "OWN"),
    ("bash", "git branch -dr origin/feature-x", "OWN"),
    ("bash", "git branch -r -d origin/feature-x", "OWN"),
    ("bash", "git push origin --delete refs/tags/v1", "OWN"),
    ("bash", "git update-ref -d refs/tags/v1", "OWN"),
    ("bash", "git update-ref -d feature-x", "OWN"),
    ("bash", "git push -ostuffd origin feature-x", "OWN"),
    ("bash", "git push --receiv git-receive-pack origin --delete feat/r-34-x", "OWN"),
    ("bash", "git push --push-opt ci.skip origin --delete feat/r-34-x", "OWN"),
    ("bash", "git branch -uorigin/dev", "OWN"),
    # an option's value is not an operand (fix round 2).
    ("bash", "git branch -D --sort refname worktree-R-34", "OWN"),
    # a quote the raw pass reads as the shell does is no reason to doubt.
    ("bash", 'git "branch" -D "worktree-R-34" > out.txt', "OWN"),
    ("bash", '(git branch -D "worktree-R-34") > out.txt', "OWN"),
    # --no-delete clears -d: git lists, or creates, and deletes nothing (fix round 3).
    ("bash", "git branch -d --no-delete --list feature-x", "OWN"),
    ("bash", "git branch -d --no-del feature-x", "OWN"),
    ("bash", "git branch feature-y", "OWN"),
    ("bash", "git branch -m old new", "OWN"),
    ("bash", "git branch --list", "OWN"),
    ("bash", "git log --decorate", "OWN"),
    ("bash", "git push origin feat/r-34-x", "OWN"),
    ("bash", "git --git-dir=/o/.git status", "OWN"),
    ("bash", "git --version", "OWN"),
    ("bash", "git worktree remove .", "OWN"),
    ("bash", "git worktree remove /w/r34", "OWN"),
    ("bash", "git -C . worktree remove .", "OWN"),
    ("bash", "git -C ../r35 worktree remove ../r34", "OWN"),
    ("bash", "git worktree prune", "OWN"),
    ("bash", "git worktree list", "OWN"),
    ("bash", "git worktree add ../r34b -b x", "OWN"),
)

# Known false negatives, pinned clear under OWN; the sibling that flips each.
GIT_FALSE_NEGATIVES = (
    "xargs git branch -D feature-x",  # R-34d
    "git branch --merged | xargs git branch -d",  # R-34d
    "sudo -u bob git branch -D feature-x",  # R-34d
    "env -C /other git branch -D worktree-R-34",  # R-34d
    "cd ../r35 && git worktree remove .",  # R-34d
    "export GIT_DIR=/o/.git; git branch -D worktree-R-34",  # R-34d
    "gh api -X DELETE repos/o/r/git/refs/heads/feature-x",  # R-34e
    "gh pr merge 12 --delete-branch",  # R-34e
    "git update-ref --stdin",  # follow-up
    "rm -rf ../r35",  # follow-up: needs the all-worktrees list
)

# Known over-reports and limits, pinned: (command, verdict, operation, rule, context).
GIT_PINNED = (
    # only the branch rule reads "inside" (INFERRED: git refuses this anyway).
    ("git worktree remove .", "hit", WT, WDEL, "SUB"),
    # a tag by its short name reads as a branch.
    ("git push --delete origin v1.0", "hit", BR, DEL, "OWN"),
    # the remote is not compared.
    ("git push other-remote --delete feat/r-34-x", "clear", None, None, "OWN"),
)

PATH_MODULES = pytest.mark.parametrize("pathmod", [ntpath, posixpath],
                                       ids=["ntpath", "posixpath"])


@pytest.fixture(name="paths")
def _paths(request, monkeypatch):
    monkeypatch.setattr(crew_oneway, "_PATH", request.param)
    return request.param


ON_BOTH = pytest.mark.parametrize("paths", [ntpath, posixpath], ids=["ntpath", "posixpath"],
                                  indirect=True)


@ON_BOTH
@pytest.mark.parametrize("shell,command,op,rule,ctx", GIT_BLOCK)
def test_git_must_block(paths, shell, command, op, rule, ctx):
    assert_hit(crew_oneway, command, rule, shell, op, ctx_of(ctx, paths))


@ON_BOTH
@pytest.mark.parametrize("shell,command,op,rule,ctx", GIT_CNT)
def test_git_could_not_tell(paths, shell, command, op, rule, ctx):
    assert_cnt(crew_oneway, command, rule, shell, op, ctx_of(ctx, paths))


@ON_BOTH
@pytest.mark.parametrize("shell,command,ctx", GIT_ALLOW)
def test_git_must_allow(paths, shell, command, ctx):
    assert_clear(crew_oneway, command, shell, ctx_of(ctx, paths))


@ON_BOTH
@pytest.mark.parametrize("command", GIT_FALSE_NEGATIVES)
def test_git_false_negatives_are_pinned_clear(paths, command):
    assert_clear(crew_oneway, command, ctx=ctx_of("OWN", paths))


@ON_BOTH
@pytest.mark.parametrize("command,verdict,op,rule,ctx", GIT_PINNED)
def test_git_over_reports_and_limits_are_pinned(paths, command, verdict, op, rule, ctx):
    result = run(crew_oneway, command, ctx=ctx_of(ctx, paths))
    assert result["verdict"] == verdict, result
    assert result["operations"] == _ops(op), result
    assert rule is None or rule in rules(result), result


def test_a_delete_and_a_state_write_in_one_segment_report_the_delete():
    """C3: one finding per segment, the head's delete reading first."""
    result = assert_hit(crew_oneway, "git branch -D feature-x > terraform.tfstate", DEL,
                        op=BR, ctx=own())
    assert rules(result) == [DEL] and len(result["findings"]) == 1


def test_mixed_operations_are_listed_sorted():
    result = run(crew_oneway, "git branch -D feature-x; terraform state rm x", ctx=own())
    assert result["verdict"] == "hit"
    assert result["operations"] == sorted([BR, OP])


def test_without_context_no_delete_is_clear():
    """C1: an unknown never collapses into clear."""
    for _shell, command, _op, _rule, _ctx in GIT_BLOCK:
        assert run(crew_oneway, command, _shell)["verdict"] != "clear", command


@pytest.mark.parametrize("shell,command", MUST_ALLOW)
def test_every_terraform_must_allow_row_stays_clear_with_context(shell, command):
    assert_clear(crew_oneway, command, shell, own())


@pytest.mark.parametrize("shell,command,rule", MUST_BLOCK)
def test_every_terraform_must_block_row_stays_a_hit_with_context(shell, command, rule):
    assert_hit(crew_oneway, command, rule, shell, ctx=own())


@pytest.mark.parametrize("command,rule", COULD_NOT_TELL)
def test_every_terraform_could_not_tell_row_stays_with_context(command, rule):
    assert_cnt(crew_oneway, command, rule, ctx=own())


@pytest.mark.parametrize("given,expected", [
    (None, (None, None, None)),
    ("x", (None, None, None)),
    ({"cwd": "", "own_branches": "a", "own_worktrees": ("a",)}, (None, None, None)),
    ({"cwd": 3, "own_branches": ["a", 1], "own_worktrees": ["a", ""]}, (None, None, ("a", ""))),
    ({"cwd": "/w", "own_branches": [""], "own_worktrees": None}, ("/w", ("",), None)),
    ({"cwd": "/w", "own_branches": [], "own_worktrees": ["/w"]}, ("/w", (), ("/w",))),
])
def test_the_context_is_read_once_and_junk_is_absent(given, expected):
    # the fourth field, `quoted`, is the raw pass's, never the caller's.
    assert tuple(crew_oneway._read_context(given)) == expected + ((),)


@ON_BOTH
def test_an_escaped_space_in_a_raw_worktree_path_never_clears(paths):
    """Fix round 2: bash reads `/w/r34\\ backup` as one path. The raw pass
    reads `/w/r34\\`, which ntpath folds into the own worktree; a word
    holding the escape cannot clear (posixpath keeps the backslash: a hit)."""
    result = run(crew_oneway, "git worktree remove /w/r34\\ backup > out.txt",
                 ctx=ctx_of("OWN", paths))
    assert result["verdict"] != "clear", result
    assert result["operations"] == [WT], result


@PATH_MODULES
def test_the_dash_c_stack_resolves_as_one_step_at_a_time(pathmod, monkeypatch):
    """Fix round 3: `_effective` joins the stack once; it lands where joining
    and normalising after each `-C` lands, resets and drives included."""
    monkeypatch.setattr(crew_oneway, "_PATH", pathmod)
    pool = ["x", "..", ".", "", "a/b", "../..", "/abs", "\\root", "D:", "D:rel", "C:\\c",
            "y\\z", "x/"]
    rng = random.Random(34)
    cwd = _p(pathmod, "w", "r34")
    for _ in range(400):
        dirs = tuple(rng.choice(pool) for _ in range(rng.randint(0, 7)))
        expected = cwd
        for value in dirs:
            expected = pathmod.normpath(pathmod.join(expected, value))
        assert crew_oneway._effective(cwd, dirs) == pathmod.normpath(expected), dirs


@PATH_MODULES
def test_inside_an_own_worktree_is_by_whole_components(pathmod, monkeypatch):
    monkeypatch.setattr(crew_oneway, "_PATH", pathmod)
    own_list = [_p(pathmod, "w", "r34")]
    assert crew_oneway._inside(_p(pathmod, "w", "r34"), own_list)
    assert crew_oneway._inside(_p(pathmod, "w", "r34", "plugin"), own_list)
    assert not crew_oneway._inside(_p(pathmod, "w", "r34x"), own_list)
    assert not crew_oneway._inside(_p(pathmod, "w"), own_list)
    assert not crew_oneway._inside(None, own_list)
    assert not crew_oneway._inside(_p(pathmod, "w", "r34"), None)
    assert crew_oneway._inside(_p(pathmod, "x"), [_p(pathmod)])  # a root own worktree


def _cleanup_calls(path):
    """C16: the `_git(...)` calls whose leading string constants are
    `worktree remove` or `branch -d`, found by content."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_git"):
            continue
        words = [arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                 else None for arg in node.args[1:]]
        if words[:2] in (["worktree", "remove"], ["branch", "-d"]):
            found.append(tuple(words))
    return found


@ON_BOTH
@pytest.mark.parametrize("name", ["crew_wave.py", "crew_worktrees.py"])
def test_crews_own_cleanup_reads_as_a_delete_of_anothers(paths, name):
    calls = _cleanup_calls(os.path.join(SCRIPTS, name))
    shapes = {call[:2] for call in calls}
    assert shapes == {("worktree", "remove"), ("branch", "-d")}, calls
    fill = {("worktree", "remove"): "/w/r35", ("branch", "-d"): "worktree-R-35"}
    for call in calls:
        assert call[2:] == (None,), call  # the target is the one non-constant argument
        command = " ".join(("git",) + call[:2] + (fill[call[:2]],))
        op = WT if call[0] == "worktree" else BR
        assert_hit(crew_oneway, command, op=op, ctx=own(paths))


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
    # F2: after safe text a comment runs to the line's end; after anything
    # else it stops only its own segment, as on main.
    ("a # b; c", [seg(["a"])]),
    ("a # b; c\nd", [seg(["a"]), seg(["d"])]),
    ("a > f # b; c", [seg(["a"], [(">", "f")]), seg(["c"])]),
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


@pytest.mark.parametrize("word,option,expected", [
    ("--del", "--delete", True), ("--d", "--delete", True), ("--delete=x", "--delete", True),
    ("-fD", "-D", True), ("-dr", "-d", True), ("--remote", "--remotes", True),
    ("--prun", "--prune", True), ("-fD", "-d", False), ("--dry-run", "--delete", False),
])
def test_option_hit_pins(word, option, expected):
    """R-34c (C9) reads git's delete options through `_option_hit` as it stands."""
    assert crew_gitallow._option_hit(word, option) is expected


def test_gitallow_helper_pins_for_deletes():
    """R-34c (C4, C5): how git's globals and `-C` values read today."""
    assert crew_gitallow.subcommand(["--namespace", "n", "branch", "-D", "x"]) == "branch"
    assert crew_gitallow._global_split(["--namespace=n", "branch"]) == (["--namespace=n"], 1)
    assert crew_gitallow._global_split(["-C", "a", "-C", "b", "worktree", "remove", "."]) == (
        ["-C", "a", "-C", "b"], 4)
    assert crew_gitallow.target_dirs(["-C", "../r35", "worktree"]) == ("../r35",)
    assert crew_gitallow.target_dirs(["--namespace=n", "branch"]) == ()
    assert crew_gitallow.target_dirs(["--git-dir=/o/.git", "branch"]) is None
    assert crew_gitallow.target_dirs(["--work-tree", "/o", "branch"]) is None
    assert crew_gitallow.target_dirs(["-C", "", "branch"]) is None
    # why C5 checks `%` and `--namespace` itself: target_dirs flags neither.
    assert crew_gitallow.target_dirs(["-C", "%X%", "branch"]) == ("%X%",)


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
    for shell, command, _op, _rule, ctx in GIT_BLOCK + GIT_CNT:
        names.update(run(crew_oneway, command, shell, ctx_of(ctx))["operations"])
    for _shape, _rule, _verdict, operation in crew_oneway.SHAPES:
        names.update([operation] if operation else [])
    return names


EMITTED = (OP, BR, WT)


def test_the_emitted_names_are_human_rows_the_owner_answers():
    assert _emitted() == set(EMITTED) == set(crew_oneway.OPERATIONS_EMITTED)
    for name in EMITTED:
        assert crew_policy.OPERATIONS[name].lane == "human"
        for presence in crew_policy.PRESENCE:
            for tier in crew_policy.TIERS:
                got = crew_policy.decide({"operation": name, "presence": presence, "tier": tier,
                                          "machine_layer": "clear"})
                assert (got["outcome"], got["rule"]) == ("ask-owner", "human"), got


@pytest.mark.parametrize("name", EMITTED)
def test_nothing_waves_a_one_way_row_through(name):
    emergency = {"declared_by": "owner", "incident": "i", "target": "t",
                 "action": name, "expiry": "2999-01-01T00:00:00Z", "uses_left": 1}
    for presence in crew_policy.PRESENCE:
        for tier in crew_policy.TIERS:
            for layer in crew_policy.MACHINE_LAYER:
                for provenance in crew_policy.PROVENANCE:
                    got = crew_policy.decide({
                        "operation": name, "presence": presence, "tier": tier,
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
    for command in ("git branch -D secret-branch-x", "git worktree remove /w/secret-dir",
                    "git push origin :secret-branch-x"):
        shown = json.dumps(run(crew_oneway, command, ctx=own()))
        assert '"hit"' in shown and "secret" not in shown, shown


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
    lines = [line.split("\t") for line in done.stdout.splitlines()]
    assert [(r, v, o) for _, r, v, o in lines] == [
        (r, v, o or "-") for _, r, v, o in crew_oneway.SHAPES]
    # R-34c: the context flags (C15).
    done = cli("judge", "--", "git branch -D feature-x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "could-not-tell"
    flags = ("--cwd", "/w/r34", "--own-branch", "worktree-R-34", "--own-branch", "feat/r-34-x",
             "--own-worktree", "/w/r34")
    done = cli("judge", *flags, "--", "git branch -D feature-x")
    assert done.returncode == 0 and json.loads(done.stdout)["operations"] == [BR]
    assert json.loads(done.stdout)["verdict"] == "hit"
    done = cli("judge", *flags, "--", "git branch -D feat/r-34-x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "clear"
    done = cli("judge", *flags, "--", "git worktree remove ../r35")
    assert done.returncode == 0 and json.loads(done.stdout)["operations"] == [WT]
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
    def make(n):
        return "terragrunt " + "--unknown exec " * n + "terraform state rm x"
    assert_hit(mod, make(GROWTH_BIG), "tf-state-write")
    assert_linear(mod, make)


def case_long_git_delete_chain_is_linear(mod):
    def make(n):
        return "terragrunt " + "exec -- git branch -D a " * n
    assert_hit(mod, make(GROWTH_BIG), DEL, op=BR, ctx=own())
    assert_linear(mod, make, own())


def case_long_git_shared_head_is_linear(mod):
    def make(n):
        return ("terragrunt exec -- " + "exec " * n + "git " + "-c a.b=c " * n
                + "branch -D feature-x")
    assert_hit(mod, make(GROWTH_BIG), DEL, op=BR, ctx=own())
    assert_linear(mod, make, own())


def case_long_stacked_dash_c_is_linear(mod):
    """Fix round 3. The directory of `git -C x -C x ...` is timed alone, at
    sizes where re-normalising the growing path at each `-C` dominates."""
    assert_hit(mod, "git " + "-C x " * GROWTH_BIG + "branch -D feature-x", DEL, op=BR,
               ctx=own())
    assert_grows_linearly(lambda n: mod._effective(own()["cwd"], ("x",) * n), 4000, 16000)


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
    # The quote keeps F2's line reader off, so the segment's own comment
    # rule is what drops `-help` here.
    assert_hit(mod, 'terraform state rm "x" # -help', "tf-state-write")


def case_block_help_in_a_comment_powershell(mod):
    assert_hit(mod, 'terraform state rm "x" # -help', "tf-state-write", shell="powershell")


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


# Review round 2: one assertion per case, so a mutation that names several
# cases proves each input it lists goes red, not only the first.

def case_allow_terraform_head_precedence_show(mod):
    assert_clear(mod, "terraform show terraform.tfstate")


def case_allow_terraform_head_precedence_plan(mod):
    assert_clear(mod, "terraform plan -state=terraform.tfstate")


def case_block_glued_redirect_attached(mod):
    assert_hit(mod, "echo {} >terraform.tfstate", "tfstate-redirect")


def case_block_glued_redirect_braces(mod):
    assert_hit(mod, "echo {}>terraform.tfstate", "tfstate-redirect")


def case_block_glued_redirect_fd(mod):
    assert_hit(mod, "echo {} 1>terraform.tfstate", "tfstate-redirect")


def case_allow_state_fd_copy(mod):
    assert_clear(mod, "cat terraform.tfstate 2>&1")


def case_allow_input_redirect(mod):
    assert_clear(mod, "cat < terraform.tfstate")


def case_allow_input_here_string(mod):
    assert_clear(mod, "cat <<< terraform.tfstate")


def case_allow_plain_pass_quoted_operator_commit(mod):
    assert_clear(mod, 'git commit -m "a > terraform.tfstate"')


def case_allow_plain_pass_quoted_operator_echo(mod):
    assert_clear(mod, 'echo "a>terraform.tfstate"')


def case_allow_git_commit(mod):
    assert_clear(mod, 'git commit -m "stop tracking terraform.tfstate"')


def _file_tool_hit(mod, tool, tool_input):
    got = mod.judge_payload({"tool_name": tool, "tool_input": tool_input})
    assert got["verdict"] == "hit", (tool, got)


def case_block_notebook_edit(mod):
    _file_tool_hit(mod, *FILE_TOOL_BLOCK[2])


def case_block_multiedit(mod):
    _file_tool_hit(mod, *FILE_TOOL_BLOCK[3])


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


def case_cnt_input_target_held(mod):
    assert_cnt(mod, "cat < terraform.tfstate > $OUT", "tfstate-redirect-unseen")


def case_allow_after_dashdash_cat(mod):
    assert_clear(mod, "cat -- -report.tfstate")


def case_allow_after_dashdash_git(mod):
    assert_clear(mod, "git diff -- -report.tfstate")


def case_cnt_sed_operand_after_dashdash(mod):
    assert_cnt(mod, "sed -- -i terraform.tfstate", "tfstate-head-unseen")


def case_block_quoted_parts_target(mod):
    assert_hit(mod, 'echo x > terra"form.tf"state', "tfstate-redirect")


def case_reader_target_keeps_brackets(mod):
    assert mod.raw_segments('echo x >"a  (  b.tfstate"') == [
        seg(["echo", "x"], [(">", "a  (  b.tfstate")])]
    assert mod.raw_segments("( echo x ) > ( out") == [seg(["echo", "x"], [(">", "out")])]


# Review round 2.

def case_block_cp_option_shaped_operand(mod):
    assert_hit(mod, "cp src -- -name.tfstate.bak=notes.txt", "tfstate-overwrite")


def case_block_rm_option_shaped_operand(mod):
    assert_hit(mod, "rm -- -name.tfstate.bak=notes.txt", "tfstate-remove")


def case_block_git_rm_option_shaped_operand(mod):
    assert_hit(mod, "git rm -- -name.tfstate.bak=notes.txt", "tfstate-git-remove")


def case_block_quoted_parts_word(mod):
    assert_hit(mod, 'rm terra"form.tf"state > /dev/null', "tfstate-remove")


def case_block_escaped_target(mod):
    assert_hit(mod, r"echo x > terraform.tfstat\e", "tfstate-redirect")


def case_block_escaped_target_powershell(mod):
    assert_hit(mod, "echo x > terraform.tfstat`e", "tfstate-redirect", shell="powershell")


# F2: the allow-list comment reader.

def case_allow_comment_ends_the_line(mod):
    assert_clear(mod, "echo ok # x; terraform state rm x")


def case_allow_comment_ends_the_line_powershell(mod):
    assert_clear(mod, "echo ok # x; terraform state rm x", shell="powershell")


def case_block_comment_stops_at_newline(mod):
    assert_hit(mod, "echo ok # x\nterraform state rm x", "tf-state-write")


def case_block_comment_stops_at_carriage_return(mod):
    assert_hit(mod, "echo ok # x\rterraform state rm x", "tf-state-write", shell="powershell")


def case_block_hash_inside_a_word(mod):
    assert_hit(mod, "echo a#b; terraform state rm x", "tf-state-write")


def case_block_hash_in_quotes(mod):
    assert_hit(mod, 'git commit -m "a # b"; terraform state rm x', "tf-state-write")


def case_block_hash_in_substitution(mod):
    assert_hit(mod, 'echo "$(echo "a # b")"; terraform state rm x', "tf-state-write")


def case_block_ps_block_comment(mod):
    assert_hit(mod, "echo ok <# c #> ; terraform state rm x", "tf-state-write",
               shell="powershell")


def case_block_escaped_separator_bash(mod):
    assert_hit(mod, r"echo a\;#b; terraform state rm x", "tf-state-write")


def case_block_escaped_separator_powershell(mod):
    assert_hit(mod, "echo a`;#b; terraform state rm x", "tf-state-write", shell="powershell")


def case_block_unit_separator_whitespace(mod):
    assert_hit(mod, "echo a\x1f#b; terraform state rm x", "tf-state-write", shell="powershell")


def case_block_no_break_space(mod):
    assert_hit(mod, "echo a\u00a0#b; terraform state rm x", "tf-state-write")


def case_block_declined_hash_holding_a_quote(mod):
    assert_hit(mod, "echo a\\  # it's\necho 'x # y'; terraform state rm x", "tf-state-write")


# R-34c. Every case runs with the module's own `_PATH` (os.path).

def case_allow_own_branch(mod):
    assert_clear(mod, "git branch -D worktree-R-34", ctx=own())


def case_cnt_no_own_list(mod):
    assert_cnt(mod, "git branch -D feature-x", "branch-owner-unseen", op=BR, ctx={})


def case_block_own_and_other(mod):
    assert_hit(mod, "git branch -D worktree-R-34 feature-x", DEL, op=BR, ctx=own())


def case_allow_remote_delete(mod):
    assert_clear(mod, "git branch -dr origin/feature-x", ctx=own())


def case_block_delete_abbreviation(mod):
    assert_hit(mod, "git branch --del feature-x", DEL, op=BR, ctx=own())


def case_block_push_colon_ref(mod):
    assert_hit(mod, "git push origin :feature-x", DEL, op=BR, ctx=own())


def case_allow_remove_own_worktree_dot(mod):
    assert_clear(mod, "git worktree remove .", ctx=own())


def case_block_dash_c_worktree(mod):
    assert_hit(mod, "git -C ../r35 worktree remove .", WDEL, op=WT, ctx=own())


def case_cnt_dash_c_own_branch_elsewhere(mod):
    assert_cnt(mod, "git -C ../other branch -D worktree-R-34", "branch-own-outside", op=BR,
               ctx=own())


def case_block_dash_c_branch(mod):
    assert_hit(mod, "git -C x branch -D feature-x", DEL, op=BR, ctx=own())


def case_cnt_git_dir(mod):
    assert_cnt(mod, "git --git-dir=/o/.git branch -D worktree-R-34", "git-repo-unseen", op=BR,
               ctx=own())


def case_block_push_delete_before_remote(mod):
    assert_hit(mod, "git push --delete origin feature-x", DEL, op=BR, ctx=own())


def case_cnt_own_branch_other_cwd(mod):
    assert_cnt(mod, "git branch -D worktree-R-34", "branch-own-outside", op=BR,
               ctx=ctx_of("OTHER"))


def case_cnt_own_branch_no_cwd(mod):
    assert_cnt(mod, "git branch -D worktree-R-34", "branch-own-outside", op=BR,
               ctx=ctx_of("NO_CWD"))


def case_cnt_own_branch_prefix_sibling(mod):
    assert_cnt(mod, "git branch -D worktree-R-34", "branch-own-outside", op=BR,
               ctx=ctx_of("R34X"))


def case_allow_own_branch_below_worktree(mod):
    assert_clear(mod, "git branch -D worktree-R-34", ctx=ctx_of("SUB"))


def case_allow_push_delete_tag(mod):
    assert_clear(mod, "git push origin --delete refs/tags/v1", ctx=own())


def case_cnt_push_prune(mod):
    assert_cnt(mod, "git push --prune origin", "push-prune", op=BR, ctx=own())


def case_cnt_namespace(mod):
    assert_cnt(mod, "git --namespace=n branch -D feature-x", "git-repo-unseen", op=BR, ctx=own())


def case_cnt_percent_dash_c(mod):
    assert_cnt(mod, "git -C %D% branch -D feature-x", "git-repo-unseen", op=BR, ctx=own())


def case_block_git_rm_with_context(mod):
    assert_hit(mod, "git rm terraform.tfstate", "tfstate-git-remove", ctx=own())


def case_block_push_attached_o_value(mod):
    assert_hit(mod, "git push -ofoo origin :feature-x", DEL, op=BR, ctx=own())


def case_cnt_namespace_tag_delete(mod):
    assert_cnt(mod, "git --namespace=n push --delete origin refs/tags/v1", "git-repo-unseen",
               op=BR, ctx=own())


def case_cnt_worktree_empty_path(mod):
    assert_cnt(mod, 'git worktree remove ""', "worktree-target-unseen", op=WT, ctx=own())


def case_block_exec_builtin(mod):
    assert_hit(mod, "exec git branch -D feature-x", DEL, op=BR, ctx=own())


# R-34c fix round 3.
def case_block_exec_dashdash(mod):
    assert_hit(mod, "exec -- git branch -D feature-x", DEL, op=BR, ctx=own())
    assert_hit(mod, "terragrunt exec -- exec -- git branch -D feature-x", DEL, op=BR,
               ctx=own())


def case_cnt_quoted_bracket(mod):
    assert_cnt(mod, "git branch -D '(worktree-R-34)' > out.txt", "branch-target-unseen",
               op=BR, ctx=own())
    assert_cnt(mod, "git worktree remove '/w/r34)' > out.txt", "worktree-target-unseen",
               op=WT, ctx=own())


def case_cnt_kept_brace(mod):
    assert_cnt(mod, "git branch -D worktree-R-34} > out.txt", "branch-target-unseen", op=BR,
               ctx=own())


def case_allow_branch_no_delete(mod):
    assert_clear(mod, "git branch -d --no-delete --list feature-x", ctx=own())


def case_block_no_delete_keeps_force_delete(mod):
    assert_hit(mod, "git branch -D --no-delete feature-x", DEL, op=BR, ctx=own())


def case_block_no_delete_as_a_value(mod):
    assert_hit(mod, "git branch -d --sort --no-delete feature-x", DEL, op=BR, ctx=own())


# R-34c fix round 1.
def case_block_branch_sort_value(mod):
    assert_hit(mod, "git branch -D --sort -r feature-x", DEL, op=BR, ctx=own())


def case_block_branch_refs_tags_operand(mod):
    assert_hit(mod, "git branch -D refs/tags/feature-x", DEL, op=BR, ctx=own())


def case_block_branch_refs_heads_operand(mod):
    assert_hit(mod, "git branch -D refs/heads/worktree-R-34", DEL, op=BR, ctx=own())


def case_cnt_worktree_quoted_sub(mod):
    assert_cnt(mod, 'git worktree re"move" ../r35 > out', "worktree-target-unseen", op=WT,
               ctx=own())


def case_cnt_branch_quoted_option(mod):
    assert_cnt(mod, 'git branch --del"ete" feature-x > out', "branch-target-unseen", op=BR,
               ctx=own())


def case_cnt_glob_dash_c(mod):
    ctx = own()
    ctx["own_worktrees"].append(_p(os.path, "w", "[rs]34"))
    assert_cnt(mod, "git -C ../[rs]34 branch -D worktree-R-34", "git-repo-unseen", op=BR,
               ctx=ctx)


# R-34c fix round 2.
def case_cnt_push_dropped_empty_value(mod):
    assert_cnt(mod, 'git push -o "" origin :feature-x > out.txt', "branch-target-unseen",
               op=BR, ctx=own())


def case_cnt_worktree_split_quoted_path(mod):
    assert_cnt(mod, 'git worktree remove /w/r34" backup" > out.txt', "worktree-target-unseen",
               op=WT, ctx=own())


def case_cnt_quoted_global(mod):
    assert_cnt(mod, 'git --git-"dir"=/o/.git branch -D worktree-R-34 > out.txt',
               "git-repo-unseen", op=BR, ctx=own())


def case_cnt_quoted_subcommand(mod):
    assert_cnt(mod, 'git wo"rktree" remove /w/r35 > out.txt', "git-sub-unseen", op=None,
               ctx=own())


def case_block_branch_sort_dashdash_value(mod):
    assert_hit(mod, "git branch --sort -- -D feature-x", DEL, op=BR, ctx=own())


def case_allow_branch_value_not_operand(mod):
    assert_clear(mod, "git branch -D --sort refname worktree-R-34", ctx=own())


def case_cnt_assign_git_dir(mod):
    assert_cnt(mod, "GIT_DIR=/o/.git git branch -D worktree-R-34", "git-repo-unseen", op=BR,
               ctx=own())


def case_cnt_assign_git_work_tree(mod):
    assert_cnt(mod, "GIT_WORK_TREE=/o git branch -D worktree-R-34", "git-repo-unseen", op=BR,
               ctx=own())


def case_cnt_assign_git_namespace(mod):
    assert_cnt(mod, "GIT_NAMESPACE=n git branch -D worktree-R-34", "git-repo-unseen", op=BR,
               ctx=own())


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
    # Re-anchored by R-34c: the context is read where `del context` stood.
    ("11 a missing context is could-not-tell",
     "    ctx = _read_context(context)\n",
     "    if not isinstance(context, dict):\n"
     '        return _result([_finding(COULD_NOT_TELL, "no-context", TF_STATE)])\n'
     "    ctx = _read_context(context)\n",
     ("case_allow_with_no_context",)),
    ("12 could-not-tell collapses to clear",
     "    if COULD_NOT_TELL in verdicts:\n        return COULD_NOT_TELL",
     "    if COULD_NOT_TELL in verdicts:\n        return CLEAR", ("case_cnt_state_sub",)),
    ("18 the redirect targets put in the finding",
     '        where = {"pass": "raw", "command": number}\n',
     '        where = {"pass": "raw", "command": number, "targets": segment["targets"]}\n',
     ("case_no_target_in_output",)),
    ("19 raw pass skipped",
     "    if commands is None:\n        return _raw_pass(command, shell, ctx)",
     "    if commands is None:\n        return []", ("case_block_raw_chain",)),
    ("29 only assignments, env and sudo stripped",
     'HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!",\n'
     '                           "if", "elif", "while", "until", "exec"))',
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
     "    return not token.strip(_STRIP) and not any(quote in token for quote in _QUOTES)\n",
     "    return not token.strip(_STRIP)\n", ("case_block_empty_here_string",)),
    ("R18 a quoted target ends at its first token",
     "        if quote is None and not skip and not glued:\n            break\n",
     "        break\n",
     ("case_block_quoted_here_string_with_a_space", "case_cnt_unclosed_quoted_target")),
    ("R19 a comment's words are read as arguments",
     "            if _comment(token):\n                break\n", "",
     ("case_block_help_in_a_comment", "case_block_help_in_a_comment_powershell")),
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
     "        gaps.append(gap[after_mark:len(gap) - mark])\n", "        gaps.append(gap)\n",
     ("case_reader_operator_inside_quoted_target",)),
    ("R26 an operator inside a quoted target keeps the reader's marker",
     "            text, right = text[2:].translate(_SHOW), text[1] in \"23\"\n",
     "            right = text[1] in \"23\"\n",
     ("case_reader_operator_inside_quoted_target",)),
    # R-34b. The numbers are the parent spec's sabotage rows.
    ("6 every cp state word read as a write",
     "    if last is not None and (info.kind[last] or (\n"
     "            info.whole[last] and info.next_dashdash[head + 1] < last)):\n",
     "    last = info.first_state(head + 1)\n    if True:\n",
     ("case_allow_cp_source",)),
    ("7 the write-target (redirection) row dropped",
     '        readings += [_write_reading(op, target, held) for op, target in segment["targets"]]\n',
     "", ("case_block_redirect", "case_block_glued_redirect_attached", "case_block_glued_redirect_braces",
      "case_block_glued_redirect_fd")),
    ("8 any other head becomes clear",
     '    return (COULD_NOT_TELL, "tfstate-head-unseen", first)\n', "    return _CLEAR\n",
     ("case_cnt_other_head",)),
    ("9 the file-tool branch dropped",
     "    if isinstance(tool, str) and tool in FILE_TOOLS:\n        return _file_tool(payload)\n",
     "", ("case_block_write_tool",)),
    # Re-anchored by R-34c: the git head now reads deletes, then state words (C3).
    ("23 the whole git head clear on a state word",
     "    deleted, stated = _git_delete(info, start, head), _git_state(info, head)\n",
     "    deleted, stated = _git_delete(info, start, head), _CLEAR\n",
     ("case_block_git_rm", "case_block_git_rm_with_context")),
    ("24 every git subcommand could-not-tell",
     "    if sub in GIT_READ_SUBS:\n",
     '    return (COULD_NOT_TELL, "tfstate-git-unseen", git_first)\n    if sub in GIT_READ_SUBS:\n',
     ("case_allow_git_diff", "case_block_git_rm")),
    ("25 the head-keyed rows applied to a terraform head",
     "                            else _judge_tf(scan, found[1], found[0] + 1))\n",
     "                            else _first_worst([_judge_tf(scan, found[1], found[0] + 1),\n"
     "                                               _state_head(scan.state_words(), start)]))\n",
     ("case_allow_terraform_head_precedence_show", "case_allow_terraform_head_precedence_plan")),
    ("27 an operator lifted only with whitespace on both sides",
     '        return f" {_MARK}{glue}{match.group(0).translate(_HIDE)} "\n',
     "        return match.group(0) if glue else "
     'f" {_MARK}{glue}{match.group(0).translate(_HIDE)} "\n',
     ("case_block_glued_redirect_attached", "case_block_glued_redirect_braces",
      "case_block_glued_redirect_fd")),
    ("28a an fd copy kept as an operator",
     "        if _FD_COPY_RE.fullmatch(operator):\n            continue\n", "",
     ("case_allow_state_fd_copy",)),
    ("28b every lifted target read as a write, input operators included",
     '    if ">" not in operator:\n        return _CLEAR\n', "",
     ("case_allow_input_redirect", "case_allow_input_here_string")),
    ("35 the plain pass replaced by the raw pass",
     "    return _plain_pass(commands, ctx)\n", "    return _raw_pass(command, shell, ctx)\n",
     ("case_allow_plain_pass_quoted_operator_commit",
      "case_allow_plain_pass_quoted_operator_echo")),
    ("36 commit dropped from the git clear list",
     '    if sub == "commit":\n        return _CLEAR\n', "", ("case_allow_git_commit",)),
    ("39 only file_path read in a file-tool payload",
     '    found = [tool_input.get(key) for key in ("file_path", "notebook_path")] + (\n'
     '        [edit.get("file_path") for edit in edits if isinstance(edit, dict)]\n'
     "        if isinstance(edits, list) else [])\n",
     '    found = [tool_input.get("file_path")]\n',
     ("case_block_notebook_edit", "case_block_multiedit")),
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
     "        if info.positional_state(index + 1):\n",
     "        if True:\n", ("case_cnt_option_value",)),
    ("B3 a lifted input target not counted as held",
     "        held = any(_state_kind(word) for word in segment[\"words\"]) or any(\n"
     "            _state_path(target) for _op, target in segment[\"targets\"])\n",
     "        held = any(_state_kind(word) for word in segment[\"words\"])\n",
     ("case_cnt_input_target_held",)),
    ("B5 a word after -- read by its own spelling",
     "                or self.first_after_dashdash(after) < len(self.words))\n",
     "                or False)\n",
     ("case_allow_after_dashdash_cat", "case_allow_after_dashdash_git")),
    ("B5 an in-place option read after --",
     "        return self.next_inplace[after] < self.next_dashdash[after]\n",
     "        return self.next_inplace[after] < len(self.words)\n",
     ("case_cnt_sed_operand_after_dashdash",)),
    ("B3 a word's or target's quotes kept for the state-word test",
     '    joined = text.replace(\'"\', "").replace("\'", "")\n',
     "    joined = text\n",
     ("case_block_quoted_parts_target", "case_block_quoted_parts_word")),
    ("F1 a bracket-only token dropped from a target",
     "        gaps.append(gap[after_mark:len(gap) - mark])\n        tokens.append(token)\n",
     "        if not _bare(token):\n"
     "            gaps.append(gap[after_mark:len(gap) - mark])\n            tokens.append(token)\n",
     ("case_reader_target_keeps_brackets",)),
    # review round 2.
    ("B5 an option-shaped word after -- read as an option value",
     "        self.whole = [_state_path(word) for word in words]\n",
     '        self.whole = [_state_kind(word) == "word" for word in words]\n',
     ("case_block_cp_option_shaped_operand", "case_block_rm_option_shaped_operand",
      "case_block_git_rm_option_shaped_operand")),
    ("B3 escapes kept for the state-word test",
     '    return (text, joined, re.sub(r"[\\\\`](.)", r"\\1", joined, flags=re.S))\n',
     "    return (text, joined)\n",
     ("case_block_escaped_target", "case_block_escaped_target_powershell")),
    # F2, the allow-list comment reader.
    ("F2a the comment reader dropped", "    text = _drop_comments(text)\n", "",
     ("case_allow_comment_ends_the_line", "case_allow_comment_ends_the_line_powershell")),
    ("F2b the allow-list check removed",
     "        if char not in _COMMENT_SAFE:\n            break\n", "",
     ("case_block_hash_in_quotes", "case_block_hash_in_substitution",
      "case_block_ps_block_comment")),
    ("F2c a `#` inside a word starts a comment",
     '        if char == "#" and (index == 0 or text[index - 1] in _COMMENT_START):\n',
     '        if char == "#":\n',
     ("case_block_hash_inside_a_word",)),
    ("F2d a comment runs to the end of the command",
     "            end = end.start() if end else len(text)\n",
     "            end = len(text)\n",
     ("case_block_comment_stops_at_newline",)),
    ("F2e only a newline ends a comment",
     '_LINE_END_RE = re.compile(r"[\\n\\r\\x0b\\x0c\\x1c\\x1d\\x1e\\x85\\u2028\\u2029]")',
     '_LINE_END_RE = re.compile(r"\\n")',
     ("case_block_comment_stops_at_carriage_return",)),
    ("F2f class 1: escapes safe and a separator starts a comment",
     '                          " \\t\\n-_./:=,;&|")\n_COMMENT_START = " \\t\\n"\n',
     '                          " \\t\\n-_./:=,;&|\\\\`")\n_COMMENT_START = " \\t\\n;&|"\n',
     ("case_block_escaped_separator_bash", "case_block_escaped_separator_powershell")),
    ("F2g class 2: any whitespace Python knows is safe and starts a comment",
     '        if char == "#" and (index == 0 or text[index - 1] in _COMMENT_START):\n'
     "            end = _LINE_END_RE.search(text, index)\n"
     "            end = end.start() if end else len(text)\n"
     "            out.append(text[start:index])\n"
     "            start = index = end\n"
     "            continue\n"
     "        if char not in _COMMENT_SAFE:\n",
     '        if char == "#" and (index == 0 or text[index - 1] in _COMMENT_START\n'
     "                            or text[index - 1].isspace()):\n"
     "            end = _LINE_END_RE.search(text, index)\n"
     "            end = end.start() if end else len(text)\n"
     "            out.append(text[start:index])\n"
     "            start = index = end\n"
     "            continue\n"
     "        if char not in _COMMENT_SAFE and not char.isspace():\n",
     ("case_block_unit_separator_whitespace", "case_block_no_break_space")),
    ("F2h class 3: escapes and quotes safe",
     '                          " \\t\\n-_./:=,;&|")\n',
     '                          " \\t\\n-_./:=,;&|\\\\`\\"\'")\n',
     ("case_block_declined_hash_holding_a_quote", "case_block_hash_in_quotes")),
    # R-34c. The numbers are the parent spec's sabotage rows.
    ("10 the own list ignored (every target hits)",
     "    if name not in ctx.own_branches:\n", "    if True:\n", ("case_allow_own_branch",)),
    ("11b an absent own list read as empty",
     "    if ctx.own_branches is None:\n"
     '        return (COULD_NOT_TELL, "branch-owner-unseen", offset)\n',
     "    if ctx.own_branches is None:\n        ctx = ctx._replace(own_branches=())\n",
     ("case_cnt_no_own_list",)),
    ("13 only the first target judged",
     "    for offset, name in named:\n", "    for offset, name in named[:1]:\n",
     ("case_block_own_and_other",)),
    ("14 -r deletes read as branch deletes",
     "    if remotes:\n        return None\n", "", ("case_allow_remote_delete",)),
    # Re-anchored by fix round 3: the delete options are read as git's two bits.
    ("15 exact --delete match only",
     '            deleting |= (hit(word, "-d") or hit(word, "--delete")) | 2 * hit(word, "-D")\n',
     '            deleting |= (hit(word, "-d") or word == "--delete") | 2 * hit(word, "-D")\n',
     ("case_block_delete_abbreviation",)),
    ("16 the :ref push form dropped",
     '        elif spec.startswith((":", "+:")):\n'
     '            targets.append((at, spec.partition(":")[2]))\n', "",
     ("case_block_push_colon_ref",)),
    ("17 worktree paths compared without resolving against eff",
     "    removed = _norm(_PATH.join(eff, path))\n", "    removed = _norm(path)\n",
     ("case_allow_remove_own_worktree_dot",)),
    # Re-anchored by fix round 3: the `-C` stack is joined once.
    ("20 -C ignored",
     "            tail.append(value)\n", "            pass\n",
     ("case_block_dash_c_worktree", "case_cnt_dash_c_own_branch_elsewhere")),
    ("21 the subcommand is the first word after git",
     "    sub_at = head + 1 + split\n",
     "    sub_at = head + 1 + split\n    sub = args[0]\n",
     ("case_block_dash_c_branch",)),
    ("22 --git-dir and --work-tree read as ordinary options",
     "    dirs = crew_gitallow.target_dirs(globals_)\n",
     "    dirs = crew_gitallow.target_dirs([word for word in globals_ if word.split(\"=\", 1)[0]\n"
     "                                      not in (\"--git-dir\", \"--work-tree\")])\n",
     ("case_cnt_git_dir",)),
    ("26 the push delete option accepted only after the remote",
     '            deleting = deleting or hit(cut, "-d") or hit(cut, "--delete")\n',
     "            deleting = deleting or (bool(positional) and (\n"
     '                hit(cut, "-d") or hit(cut, "--delete")))\n',
     ("case_block_push_delete_before_remote",)),
    ("32a/32b an own name clear wherever the command runs",
     "    if own_inside:\n", "    if True:\n",
     ("case_cnt_own_branch_other_cwd", "case_cnt_own_branch_no_cwd")),
    ("33 inside by string prefix",
     "        if here == entry or here.startswith(entry.rstrip(_PATH.sep) + _PATH.sep):\n",
     "        if here.startswith(entry):\n", ("case_cnt_own_branch_prefix_sibling",)),
    ("34 inside by equality",
     "        if here == entry or here.startswith(entry.rstrip(_PATH.sep) + _PATH.sep):\n",
     "        if here == entry:\n", ("case_allow_own_branch_below_worktree",)),
    ("C-tags refs/tags/ read as a branch",
     '        if target.startswith("refs/tags/"):\n            continue\n', "",
     ("case_allow_push_delete_tag",)),
    ("C-prune the --prune/--mirror row dropped",
     "        elif pruning:\n", "        elif False:\n", ("case_cnt_push_prune",)),
    ("C-ns the --namespace repo check dropped",
     '    if any(word.split("=", 1)[0] == "--namespace" for word in globals_):\n'
     "        return True\n", "", ("case_cnt_namespace",)),
    ("C-pct the % and ~ -C repo check dropped",
     '    return any(value.startswith("~") or any(mark in value for mark in _TARGET_UNSEEN)\n'
     "               for value in dirs)\n",
     "    return False\n", ("case_cnt_percent_dash_c", "case_cnt_glob_dash_c")),
    # R-34c review round 1.
    ("C-o an attached -o value read as taking the next word",
     "        return cut + letter == word\n", "        return word.endswith(letter)\n",
     ("case_block_push_attached_o_value",)),
    ("C-tags-ns the unknown repository judged after the tag rule",
     "    if repo_unseen:\n"
     '        return (COULD_NOT_TELL, ("git-repo-unseen", BRANCH), where)\n'
     "    named = []\n", "    named = []\n", ("case_cnt_namespace_tag_delete",)),
    ("C-empty an empty worktree path resolved to the cwd",
     "    if not path or any(", "    if any(", ("case_cnt_worktree_empty_path",)),
    ("C-exec the shell builtin exec not a head prefix",
     '"if", "elif", "while", "until", "exec"))', '"if", "elif", "while", "until"))',
     ("case_block_exec_builtin",)),
    # R-34c fix round 1.
    ("C14 the git word window removed (quadratic)",
     "    rest = info.words[where:where + GIT_WINDOW]\n", "    rest = info.words[where:]\n",
     ("case_long_git_delete_chain_is_linear",)),
    # Re-anchored by fix round 2: one scanner reads the options, operands and -r.
    ("C-sort a branch option's value read as -r, a separator or an operand",
     '            taken = _git_takes_value(word, short, "u", _BRANCH_VALUE_OPTS, _BRANCH_LONG_FLAGS)\n',
     "            taken = False\n",
     ("case_block_branch_sort_value", "case_block_branch_sort_dashdash_value",
      "case_allow_branch_value_not_operand")),
    ("C-refs a git branch operand read as a ref",
     "        if not refs:\n            named.append((where + index, target))\n"
     "            continue\n", "",
     ("case_block_branch_refs_tags_operand", "case_block_branch_refs_heads_operand")),
    # Re-anchored by fix round 2: `_quoted_option` folded into the raw pass's
    # misread words, which also catch a dropped `""` and a split quoted path.
    ("C-quote a word after the subcommand the raw pass may have misread trusted",
     "    if reading[0] != HIT and _quoted_in(ctx.quoted, where, where + GIT_WINDOW + 1):\n",
     "    if False:\n",
     ("case_cnt_worktree_quoted_sub", "case_cnt_branch_quoted_option",
      "case_cnt_push_dropped_empty_value", "case_cnt_worktree_split_quoted_path")),
    # R-34c fix round 2.
    ("C-raw-global a global the raw pass may have misread trusted",
     "    repo_unseen = _repo_unseen(globals_, dirs, info.repo_assign[start] < head\n"
     "                               or _quoted_in(ctx.quoted, head + 1, sub_at))\n",
     "    repo_unseen = _repo_unseen(globals_, dirs, info.repo_assign[start] < head)\n",
     ("case_cnt_quoted_global",)),
    ("C-faithful every raw word read as the shell reads it",
     "    body = token.strip(\"()\")\n", "    return True\n",
     ("case_cnt_worktree_split_quoted_path", "case_cnt_quoted_global",
      "case_cnt_branch_quoted_option")),
    ("C-empty-word a dropped quoted empty word not recorded",
     "            elif not _bare(token):\n                quoted.append(len(out))\n", "",
     ("case_cnt_push_dropped_empty_value",)),
    ("C5-dir GIT_DIR dropped from the repository variables",
     '_REPO_VARS = frozenset(("GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE"))',
     '_REPO_VARS = frozenset(("GIT_WORK_TREE", "GIT_NAMESPACE"))', ("case_cnt_assign_git_dir",)),
    ("C5-wt GIT_WORK_TREE dropped from the repository variables",
     '_REPO_VARS = frozenset(("GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE"))',
     '_REPO_VARS = frozenset(("GIT_DIR", "GIT_NAMESPACE"))', ("case_cnt_assign_git_work_tree",)),
    ("C5-ns GIT_NAMESPACE dropped from the repository variables",
     '_REPO_VARS = frozenset(("GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE"))',
     '_REPO_VARS = frozenset(("GIT_DIR", "GIT_WORK_TREE"))', ("case_cnt_assign_git_namespace",)),
    ("C14b a shared git head read again at every start (quadratic)",
     "    if key not in info.git_memo:\n", "    if True:\n",
     ("case_long_git_shared_head_is_linear",)),
    # R-34c fix round 3.
    ("C-bracket a bracket inside quotes read as syntax",
     "            and token.strip(_STRIP) == body[1:-1])\n", ")\n", ("case_cnt_quoted_bracket",)),
    ("C-brace a brace the shell keeps read as syntax",
     "        return body == token.strip(_STRIP)\n", "        return True\n",
     ("case_cnt_kept_brace",)),
    ("C-exec-dashdash the -- after exec read as the head",
     '_DASHDASH_PREFIXES = frozenset(("exec", "command", "env", "sudo"))',
     "_DASHDASH_PREFIXES = frozenset()", ("case_block_exec_dashdash",)),
    ("C-no-delete --no-delete ignored",
     "            deleting &= 2\n", "            pass\n", ("case_allow_branch_no_delete",)),
    ("C-no-delete-D --no-delete clears -D too",
     "            deleting &= 2\n", "            deleting = 0\n",
     ("case_block_no_delete_keeps_force_delete",)),
    ("C-no-delete-value an option's value read as --no-delete",
     "        if at not in values and _no_delete(word):\n", "        if _no_delete(word):\n",
     ("case_block_no_delete_as_a_value",)),
    ("C14c each -C re-normalises the growing path (quadratic)",
     "    return _PATH.normpath(_PATH.join(base, _PATH.sep.join(tail)) if tail else base)\n",
     "    for value in tail:\n        base = _PATH.normpath(_PATH.join(base, value))\n"
     "    return base\n", ("case_long_stacked_dash_c_is_linear",)),
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
