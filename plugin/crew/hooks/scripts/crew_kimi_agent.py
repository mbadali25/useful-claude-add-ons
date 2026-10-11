"""Run one crew subagent role on the Kimi Code CLI, read-only (L-0777).

    python3 crew_kimi_agent.py --role explorer|researcher|security|reviewer \\
        --root DIR [--authors "claude gpt"] [--timeout SECONDS]  < task.txt

WHY THIS EXISTS. Claude Code's subagent `model` field accepts Claude models
only, so `agents/explorer.md` cannot simply say "Kimi". Each crew agent is a
thin Claude dispatcher instead: its one Bash call pipes the caller's task into
this script, and it relays what this prints. When Kimi cannot run, the
dispatcher does the task itself on Claude with the same instructions -- the
agent file's text after `MARKER` -- and says so.

THE CONTRACT. Line 1 of stdout is machine-readable, and the exit code says
which of four things happened:

  0  `KIMI OK: <role> ran on kimi <alias>`, then Kimi's final message,
     secrets redacted.
  3  `KIMI UNAVAILABLE: <state> - <reason>`. Nothing Kimi could have run
     touched the tree (the probe's own tree check passed, or nothing was
     launched). The dispatcher falls back to Claude. States: not-routed,
     barred, author-unknown, not-installed, not-authenticated, rate-limited,
     unknown, timed-out, failed, too-large.
  8  `KIMI CHANGED THE TREE: <paths>` or `KIMI TREE UNKNOWN: <reason>`. The
     working tree is not, or may not be, the one the caller handed over. The
     dispatcher stops and reports; it never falls back over a changed tree.
  2  usage: an unknown role, an empty task, an unreadable config.

ROUTING is config: `crew_state.resolve_role` over `dev.roles.<role>`
(`qa.roles.review` for `reviewer`). Only a resolved provider of `kimi`
dispatches, so a fresh install, which pins nothing, keeps every role on
Claude (`not-routed`).

THE FAMILY GUARD. `security` and `reviewer` judge code, so the family that
wrote it may not be the one reading it. The author set is `--authors` united
with `crew_state.author_families`; an empty set is `author-unknown`, never "no
conflict" -- an unknown must not collapse into the safe-looking value.

READ-ONLY IS NOT A FLAG. `kimi -p` forces permission mode `auto`. The controls
are `/crew:review` step 2e's, reused from `review_run` and `kimi_probe` rather
than copied: an agent file per role allowing only reads (`ROLE_TOOLS`) and
disallowing Write, Edit and Bash, an empty `--skills-dir`, and the working
tree fingerprinted before the probe, after it, and after the run (survivors
stopped first). A write OUTSIDE the repository is caught by neither.
"""
from __future__ import annotations

import argparse
import functools
import os
import shutil
import sys
import tempfile
import time

import crew_common
import crew_config
import crew_state
import kimi_probe
import review_patch
import review_run

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_TREE = 8

DEFAULT_TIMEOUT = 900
TASK_CAP = 64000
# stdin is read to at most this many bytes (UTF-8 is at most 4 per character),
# so an oversized task is refused without reading all of it into memory.
STDIN_LIMIT = 4 * TASK_CAP + 4
# Seconds between stopping what the run left in its process group and the
# last fingerprint: a descendant that left the group (a new session) and writes
# within this window is caught. A write later than it is not (README, "Limits").
SETTLE_S = 2.0
MARKER = "<!-- crew-kimi: role instructions -->"

AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "agents")

# What each role may use on Kimi. Never Bash: no Kimi flag makes a shell
# read-only, and a plugin agent cannot hook-narrow one.
ROLE_TOOLS = {
    "explorer": ("Read", "Grep", "Glob"),
    "researcher": ("Read", "Glob", "WebSearch", "FetchURL"),
    "security": ("Read", "Grep", "Glob"),
    "reviewer": ("Read", "Grep", "Glob"),
}
DISALLOWED = ("Write", "Edit", "Bash")

# role -> (config block, role name in that block's `roles` table)
ROLE_PINS = {
    "explorer": ("dev", "explorer"),
    "researcher": ("dev", "researcher"),
    "security": ("dev", "security"),
    "reviewer": ("qa", "review"),
}
REVIEWING = ("security", "reviewer")

_CAN = {
    "explorer": "read, grep and glob this repository",
    "researcher": "read and glob this repository, search the web and fetch URLs",
    "security": "read, grep and glob this repository",
    "reviewer": "read, grep and glob this repository",
}


def _one_line(text):
    """`text` with every line break folded to ` / `: the first line is the
    contract, so a reason or a path name carrying a newline must not be able
    to print a second, forged contract line."""
    return " / ".join(part for part in str(text).splitlines() if part) or ""


def _say(line, body=None):
    sys.stdout.write(_one_line(line) + "\n")
    if body:
        sys.stdout.write(body.rstrip("\n") + "\n")
    sys.stdout.flush()


def unavailable(state, reason):
    _say(f"KIMI UNAVAILABLE: {state} - {kimi_probe.redact(reason)}")
    return EXIT_UNAVAILABLE


def role_instructions(role, agents_dir=AGENTS_DIR):
    """The agent file's text after `MARKER`, stripped, or None when the file
    is unreadable, carries the marker other than exactly once, or has
    nothing after it."""
    try:
        with open(os.path.join(agents_dir, f"{role}.md"), encoding="utf-8",
                  errors="strict", newline="") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return None
    if text.count(MARKER) != 1:
        return None
    after = text.split(MARKER, 1)[1].strip()
    return after or None


def build_prompt(role, instructions, task):
    return (f"{instructions}\n\n---\n\n"
            f"You are running as crew's `{role}` role under the Kimi Code CLI, read-only: "
            f"you can {_CAN[role]}. You cannot run commands or change files. Where the "
            "instructions above say to run a command (git diff, a test, a search tool you "
            "do not have), read the files instead and name what you could not run under "
            "**Not verified**.\n\n## Task\n\n" + task.strip() + "\n")


def _split_authors(values):
    """The `--authors` names as families, normalised the way the guard
    compares them (`crew_state.family`: `Kimi` -> `kimi`, `GPT-5` -> `gpt`,
    `k3` -> `kimi`). Raises ValueError on a name that names no family."""
    out = set()
    for value in values or ():
        for name in value.replace(",", " ").split():
            fam = crew_state.family(None, name)
            if not fam or not fam.isalpha():
                raise ValueError(f"--authors {name!r} names no model family "
                                 "(claude, gpt, kimi, ...)")
            out.add(fam)
    return frozenset(out)


def diff_bundle(root, base):
    """The change against `base` as `/crew:review` bundles it -- committed,
    staged, unstaged and untracked (`review_patch.compute`, which writes
    nothing) -- as text for the task. Raises ValueError on a base that is not
    a plain ref, or a bundle that cannot be built."""
    if (not base or base.startswith("-") or ";" in base
            or any(c.isspace() or ord(c) < 32 for c in base)):
        raise ValueError(f"--diff-base {base!r} is not a plain commit or ref")
    try:
        _manifest, patch, _parts = review_patch.compute(root, base)
    except RuntimeError as exc:
        raise ValueError(f"--diff-base {base}: the bundle could not be built: {exc}") from exc
    text = patch.decode("utf-8", errors="backslashreplace")
    return (f"\n\n## The change under review\n\nThe review bundle against `{base}`: committed, "
            "staged, unstaged and untracked changes, as /crew:review builds it.\n\n"
            f"```diff\n{text}\n```\n")


def _config_problem(root):
    """Why a crew config layer exists and cannot be read, or None.
    `resolve_config` reads a broken file as absent, which would route every
    role to its default; here a broken layer is a usage error (exit 2)."""
    for path in (crew_common.repo_config_file(root, "config.json"),
                 crew_config.GLOBAL_CONFIG_PATH):
        why = crew_config._unreadable_config(path)  # pylint: disable=protected-access
        if why:
            return f"{path}: {why}"
    return None


def route(root, role, authors_arg):
    """(row, authors, problem). `problem` is (state, reason) when Kimi must
    not run; `row` is `resolve_role`'s dict. Raises ValueError when a config
    layer is unreadable."""
    broken = _config_problem(root)
    if broken:
        raise ValueError(f"the crew config could not be read: {broken}")
    cfg = crew_config.resolve_config(root)
    problems = crew_config.provider_problems(cfg)
    if problems:
        raise ValueError(f"the crew config could not be read: {'; '.join(problems)}")
    kind, name = ROLE_PINS[role]
    authors = _split_authors(authors_arg)
    unguarded = crew_state.resolve_role(cfg, kind, name)
    if unguarded["provider"] != "kimi":
        return unguarded, authors, ("not-routed", f"{kind}.roles.{name} resolves to "
                                                  f"`{unguarded['provider']}`, not kimi")
    if role in REVIEWING:
        found, source = crew_state.author_families(root, cfg)
        if source == "unknown":
            return None, authors, ("author-unknown",
                                   "a dispatch on this branch has a family that cannot be "
                                   "determined, or a record in .work/ would not parse, so "
                                   "whether Kimi wrote this change cannot be told")
        authors = authors | frozenset(found or ())
        if not authors:
            return None, authors, ("author-unknown",
                                   "no author family is known for this change (pass --authors), "
                                   "so whether Kimi wrote it cannot be told")
    row = crew_state.resolve_role(cfg, kind, name, author=authors or None)
    if row["provider"] != "kimi":
        return row, authors, ("not-routed", f"{kind}.roles.{name} resolves to "
                                            f"`{row['provider']}`, not kimi")
    if row["barred"]:
        return row, authors, ("barred", f"kimi speaks as the `{row['barredBy']}` family, "
                                        "which wrote this change")
    return row, authors, None


def _tree_problem(before, after, graph):
    """(line, exit) when the tree changed or cannot be told, else None."""
    if before is None or after is None:
        return "KIMI TREE UNKNOWN: the working tree could not be fingerprinted", EXIT_TREE
    changed, _set_aside = review_run.reviewer_changes(before, after, graph)
    if changed:
        return f"KIMI CHANGED THE TREE: {review_run._named(changed)}", EXIT_TREE  # pylint: disable=protected-access
    return None


def run(args, task):  # pylint: disable=too-many-return-statements,too-many-locals
    root = os.path.abspath(args.root)
    instructions = role_instructions(args.role, args.agents_dir)
    if instructions is None:
        _say(f"crew-kimi-agent: agents/{args.role}.md has no text after `{MARKER}`")
        return EXIT_USAGE
    try:
        row, _authors, problem = route(root, args.role, args.authors)
    except (OSError, ValueError) as exc:
        _say(f"crew-kimi-agent: {exc}")
        return EXIT_USAGE
    if problem:
        return unavailable(*problem)
    if getattr(args, "diff_base", None):
        try:
            task = task + diff_bundle(root, args.diff_base)
        except ValueError as exc:
            _say(f"crew-kimi-agent: {exc}")
            return EXIT_USAGE
    if len(task) > TASK_CAP:
        return unavailable("too-large", f"the task is {len(task)} characters, over the "
                                        f"{TASK_CAP} cap")

    graph = review_run.graph_out(root)
    problems = []
    before = review_run.tree_fingerprint(root, problems)
    if before is None:
        _say("KIMI TREE UNKNOWN: the working tree could not be fingerprinted before "
             f"launch: {'; '.join(problems) or 'no reason given'}")
        return EXIT_TREE
    unstopped = []
    probed = kimi_probe.probe(row["model"] or None, runner=functools.partial(
        review_run._probe_runner, unstopped=unstopped))  # pylint: disable=protected-access
    mid = review_run.tree_fingerprint(root)
    tree = _tree_problem(before, mid, graph)
    if tree:
        _say(f"{tree[0]} (during the kimi probe, which answered "
             f"{probed['state']})")
        return tree[1]
    if unstopped:
        _say("KIMI TREE UNKNOWN: a process the kimi probe left running could not be stopped")
        return EXIT_TREE
    if not kimi_probe.launchable(probed["state"]):
        return unavailable(probed["state"], probed["reason"])

    try:
        scratch = tempfile.mkdtemp(prefix="crew-kimi-agent-")
    except OSError as exc:
        return unavailable("failed", f"no scratch directory: {exc}")
    try:
        try:
            prompt = build_prompt(args.role, instructions, task)
            prompt_path = os.path.join(scratch, "prompt.txt")
            review_run._write_atomic(prompt_path, prompt)  # pylint: disable=protected-access
            argument = review_run.prompt_argument(prompt_path, probed["exe"])
            cmd = [probed["exe"], "-p", argument, "-m", probed["alias"],
                   "--output-format", "stream-json",
                   *kimi_probe.read_only_flags(
                       scratch, tools=ROLE_TOOLS[args.role], disallowed=DISALLOWED,
                       name=f"crew-{args.role}", filename=f"kimi-{args.role}.md",
                       description=f"crew's read-only {args.role} role.",
                       body=(f"You are crew's read-only {args.role}. Follow the user's "
                             "message exactly; never modify files."))]
        except OSError as exc:
            return unavailable("failed", f"the prompt or agent file could not be written: {exc}")
        if argument != prompt:
            cmd += ["--add-dir", scratch]
        started = []
        stdout, stderr, code, timed_out = review_run.launch(
            cmd, root, args.timeout, env=kimi_probe.kimi_env(), started=started)
        _killed, survivor_unknown = review_run.stop_survivors(started)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    time.sleep(SETTLE_S)
    after = review_run.tree_fingerprint(root)
    tree = _tree_problem(before, after, graph)
    if tree:
        _say(tree[0])
        return tree[1]
    if survivor_unknown:
        _say(f"KIMI TREE UNKNOWN: {survivor_unknown}")
        return EXIT_TREE
    if timed_out:
        return unavailable("timed-out", f"no answer within {args.timeout}s")
    message, error = kimi_probe.final_message(stdout)
    if code != 0 or error or not (message or "").strip():
        detail = error or (stderr or "").strip()[:200] or "no final message"
        return unavailable("failed", f"exit {code}: {detail}")
    _say(f"KIMI OK: {args.role} ran on kimi {probed['alias']}", kimi_probe.redact(message))
    return EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--role", required=True, choices=sorted(ROLE_TOOLS))
    parser.add_argument("--root", default=".")
    parser.add_argument("--authors", action="append", default=[],
                        help="the author families of the change (security, reviewer)")
    parser.add_argument("--diff-base", default=None,
                        help="append the review bundle against this commit or ref to the task")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--agents-dir", default=AGENTS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    # Kimi's answer is relayed as UTF-8 whatever the console's code page; a
    # cp1252 stdout on Windows would otherwise raise mid-answer.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        raw = b"" if sys.stdin.isatty() else sys.stdin.buffer.read(STDIN_LIMIT + 1)
        if len(raw) > STDIN_LIMIT:
            return unavailable("too-large", f"the task on stdin is over {STDIN_LIMIT} bytes")
        task = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _say(f"crew-kimi-agent: the task on stdin is not UTF-8: {exc.reason} at byte {exc.start}")
        return EXIT_USAGE
    if not task.strip():
        _say("crew-kimi-agent: no task on stdin")
        return EXIT_USAGE
    return run(args, task)


if __name__ == "__main__":
    sys.exit(main())
