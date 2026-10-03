"""Read-only crew status for one repository, at most 40 lines.

    python3 crew_status.py [--root .] [--memory]

Replaces what `/crew:pm`, `/crew:roster` and `/crew:scale` reported, and does
none of what they did: no dispatch, no config edit, no file written anywhere.
Every section is a fact read from disk or git, or it says it could not tell.

`--memory` adds the context hook's own numbers by running `crew_context.py
--stats --root <root>` from this directory when that script exists, and says
"context hook not installed" when it does not. `--root` is passed explicitly:
without it `crew_context.py` resolves `CLAUDE_PROJECT_DIR` first, so a status
run for one repo from a session in another read the other repo's log.

Read-only is a property, not a promise: git runs with `GIT_OPTIONAL_LOCKS=0`
so `git status` cannot refresh the index and with `core.fsmonitor=false` so a
configured fsmonitor hook never runs, and bytecode writing is off so even
the import of the sibling modules leaves no `__pycache__` behind. The test
suite snapshots every mtime in a fixture repo around a run.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

import crew_common  # noqa: E402
import crew_freshness  # noqa: E402
import crew_migrate  # noqa: E402
import crew_shell  # noqa: E402
import crew_tracker  # noqa: E402
import review_gate  # noqa: E402
import review_ledger  # noqa: E402
import verify_fingerprint  # noqa: E402
import verify_record  # noqa: E402
from crew_common import read_text  # noqa: E402

MAX_LINES = 40
HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXT_SCRIPT = os.path.join(HERE, "crew_context.py")
_GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def _git(root, *args):
    try:
        done = subprocess.run(("git", "-c", "core.fsmonitor=false") + args, cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10, check=False,
                              stdin=subprocess.DEVNULL, env=_GIT_ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return "corrupt"


def _tracker_line(root):
    # Both config shapes, through the one resolver every tracker write uses:
    # crew.json's kind shown while the commands gated on config.json's string
    # was how the two disagreed with nothing reporting it.
    return "tracker  " + crew_tracker.describe(crew_tracker.resolve(root))


def _config_lines(root):
    crew = _json(crew_common.repo_config_file(root, "crew.json"))
    legacy = _json(crew_common.repo_config_file(root, "config.json"))
    lines, cfg = _config_lines_for(root, crew, legacy)
    # Which file is in force, when it is not simply this checkout's (T-0088).
    source = crew_common.repo_config_source_line(root)
    if source:
        lines.insert(1, f"config   {source}")
    return lines, cfg


def _config_lines_for(root, crew, legacy):
    if crew is not None and not isinstance(crew, dict):
        return ["config   .crew/crew.json unreadable - status cannot tell the setup"], {}
    if isinstance(crew, dict):
        agents = crew.get("agents") or []
        return [f"config   .crew/crew.json schema {crew.get('schema', '?')}",
                f"roster   {', '.join(agents) or 'none'} (1.0 roster: {', '.join(crew_migrate.ROSTER)})",
                _tracker_line(root)], crew
    if isinstance(legacy, dict):
        roles = legacy.get("roles") if isinstance(legacy.get("roles"), list) else []
        kept = [r for r in crew_migrate.ROSTER
                if r in roles or any(crew_migrate.RENAMED.get(x) == r for x in roles)]
        return [f"config   .crew/config.json schema {legacy.get('schema', '?')} - run /crew:migrate",
                f"roster   {len(roles)} roles active; 1.0 keeps {', '.join(kept) or 'none of them'}",
                _tracker_line(root)], legacy
    if crew == "corrupt" or legacy == "corrupt":
        return ["config   unreadable JSON in .crew/ - status cannot tell the setup"], {}
    return ["config   none - run /crew:init"], {}


def _ticket_lines(root):
    folder = os.path.join(root, ".work", "tickets")
    try:
        names = os.listdir(folder)
    except OSError:
        return ["tickets  none (.work/tickets/ absent)"]
    dirs = sorted(n for n in names if os.path.isdir(os.path.join(folder, n)))
    files = [n for n in names if n.endswith(".md")]
    open_ids = []
    for line in (read_text(os.path.join(root, ".work", "INDEX.md")) or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) > 1 and cells[1].lower() in ("open", "in-progress", "in progress", "review"):
            open_ids.append(cells[0])
    lines = [f"tickets  {len(dirs)} ticket dir(s), {len(files)} legacy file(s)"]
    if open_ids:
        shown = ", ".join(open_ids[:5]) + (f" (+{len(open_ids) - 5})" if len(open_ids) > 5 else "")
        lines.append(f"open     {shown}")
    return lines


def _review_lines(root):
    common = _git(root, "rev-parse", "--git-common-dir")
    if common is None:
        return ["review   unknown (not a git repository)"]
    folder = os.path.join(root, common, "crew", "review")
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
    except OSError:
        return ["review   no ledgers"]
    names.sort(key=lambda n: os.path.getmtime(os.path.join(folder, n)), reverse=True)
    lines = []
    for name in names[:3]:
        path = os.path.join(folder, name)
        # The ledger's own summary, so status counts rounds exactly as the
        # budget does: refunded tool-failure rounds are not "used" (T-0087).
        summary = review_ledger.summary(*review_ledger.load(path), name[:-5], path)
        if summary["state"] == review_ledger.UNKNOWN:
            lines.append(f"review   {name[:-5]}: UNKNOWN (ledger unreadable)")
            continue
        used = f"{summary['rounds_spent']}/{summary['budget']} rounds used"
        line = f"review   {name[:-5]}: {summary['state']}, {used}"
        if summary["rounds_refunded"]:
            line += f", {summary['rounds_refunded']} refunded"
        lines.append(line)
    if len(names) > 3:
        lines.append(f"review   (+{len(names) - 3} older ledgers)")
    return lines


# /crew:done check 2 passes only on a line starting with this (L-0602).
VERIFY_CLEAN = "verify   clean"
_GATE_LOCK = os.path.join(".crew", ".verify-gate.lock")


class _QuietGit:
    """Run review_gate's own git calls with fsmonitor off and no optional
    locks, so status stays read-only (the same two settings `_git` above
    uses). review_gate passes no environment of its own, so the settings go
    in through GIT_CONFIG_COUNT, appended to any the caller already set, and
    os.environ is restored exactly afterwards."""

    _KEYS = ("GIT_CONFIG_COUNT", "GIT_OPTIONAL_LOCKS")

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self._KEYS}
        count = int(os.environ.get("GIT_CONFIG_COUNT") or "0")
        self.added = (f"GIT_CONFIG_KEY_{count}", f"GIT_CONFIG_VALUE_{count}")
        self.saved.update({k: os.environ.get(k) for k in self.added})
        os.environ[self.added[0]] = "core.fsmonitor"
        os.environ[self.added[1]] = "false"
        os.environ["GIT_CONFIG_COUNT"] = str(count + 1)
        os.environ["GIT_OPTIONAL_LOCKS"] = "0"
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


def _material_now(root):
    return verify_fingerprint._material(review_gate.changed_now(root))  # pylint: disable=protected-access


def _verify_line(root):
    """Check 2's evidence, read inside one window (L-0602): the per-rule record
    lists nothing outstanding and names a fully clean --all at HEAD
    (`all_clean_at`), review_gate says VERIFIED, and nothing material differs
    from HEAD. The marker and the tree are read last. A read-only check cannot
    see a writer that acts after its last read, or one that edits and restores
    inside the window; the Stop gate stays the enforcement."""
    if os.path.lexists(os.path.join(root, _GATE_LOCK)):
        return "verify   gate running - rerun when it finishes"
    head1 = _git(root, "rev-parse", "HEAD")
    first = verify_record.read_record_meta(root)
    state, rules, clean_at = first
    if state == "absent":
        return "verify   no gate record yet"
    if state != "ok":
        return "verify   UNKNOWN (gate record unreadable)"
    if rules:
        counts = {}
        for rule in rules.values():
            status = rule.get("status", "unknown") if isinstance(rule, dict) else "unknown"
            counts[status] = counts.get(status, 0) + 1
        return "verify   " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    try:
        with _QuietGit():
            gate1 = review_gate.gate_state(root)
            material1 = _material_now(root) if gate1[0] != review_gate.NO_GATE else []
            second = verify_record.read_record_meta(root)
            head2 = _git(root, "rev-parse", "HEAD")
            gate2 = review_gate.gate_state(root)
            material2 = _material_now(root) if gate2[0] != review_gate.NO_GATE else []
    except Exception as exc:  # pylint: disable=broad-except
        return f"verify   UNKNOWN ({type(exc).__name__}: {exc})"
    if os.path.lexists(os.path.join(root, _GATE_LOCK)):
        return "verify   gate running - rerun when it finishes"
    if gate1[0] == gate2[0] == review_gate.NO_GATE:
        return ("verify   no gate - no .crew/verify.json, or the gate is stood down; "
                "check 2 cannot pass")
    if head1 is None:
        return f"verify   UNKNOWN (HEAD could not be read; gate state: {gate1[1]})"
    if (head1 != head2 or first != second or gate1[0] != gate2[0]
            or material1 != material2):
        return ("verify   UNKNOWN (HEAD, the gate record, the gate state or the tree moved "
                "while it was read - rerun)")
    if clean_at != head1:
        last = clean_at[:12] if clean_at else "none"
        return f"verify   NOT VERIFIED (no clean --all at HEAD: last clean --all {last})"
    gate, reason = gate1
    if gate != review_gate.VERIFIED:
        word = "NOT VERIFIED" if gate == review_gate.UNVERIFIED else "UNKNOWN"
        return f"verify   {word} ({reason})"
    if material1:
        return (f"verify   NOT VERIFIED ({len(material1)} path(s) differ from HEAD - commit, "
                "then run /crew:verify --all)")
    return f"{VERIFY_CLEAN} at {head1[:12]}: --all passed at HEAD, nothing outstanding, tree committed"


def _codemap_line(root, cfg):
    if not os.path.isdir(os.path.join(root, ".crew", "codemap")):
        return "codemap  none - /crew:onboard writes one"
    info = crew_freshness.read_knowledge(root, cfg if isinstance(cfg, dict) else {})
    line = f"codemap  {info['subsystems']} subsystem(s)"
    if info["behind"]:
        line += f", behind: {', '.join(info['behind'][:4])}"
    if info["unresolvable"]:
        line += f", unresolvable: {', '.join(info['unresolvable'][:4])}"
    return line


def _metrics_line(root):
    for name in ("metrics.jsonl", "metrics.md"):
        text = read_text(os.path.join(root, ".crew", name))
        if text is not None:
            rows = sum(1 for line in text.splitlines() if line.strip())
            return f"metrics  .crew/{name}: {rows} row(s)"
    return "metrics  none recorded"


def _memory_lines(root, budget):
    if not os.path.isfile(CONTEXT_SCRIPT):
        return ["memory   context hook not installed (crew_context.py absent)"]
    try:
        done = subprocess.run([sys.executable, "-B", CONTEXT_SCRIPT, "--stats", "--root", root],
                              cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20, check=False,
                              stdin=subprocess.DEVNULL,
                              env=dict(_GIT_ENV, CLAUDE_PROJECT_DIR=root))
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"memory  crew_context.py --stats could not run: {exc}"]
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["no stderr"])[0]
        return [f"memory   crew_context.py --stats failed (exit {done.returncode}): {first[:80]}"]
    body = [line.rstrip() for line in done.stdout.splitlines() if line.strip()]
    lines = ["memory   " + (body[0] if body else "no stats reported")]
    lines += ["         " + line for line in body[1:]]
    if len(lines) > budget:
        lines = lines[:budget - 1] + [f"         ... {len(lines) - budget + 1} more line(s) clipped"]
    return lines


def collect(root, memory=False):
    root = os.path.abspath(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git(root, "rev-parse", "--short=8", "HEAD") or "?"
    porcelain = _git(root, "status", "--porcelain")
    tree = "unknown" if porcelain is None else (
        "clean" if not porcelain else f"{len(porcelain.splitlines())} changed path(s)")
    lines = [f"crew status  {os.path.basename(root)}  {branch}@{head}  tree {tree}"]
    config_lines, cfg = _config_lines(root)
    lines += config_lines
    lines += _ticket_lines(root)
    lines += _review_lines(root)
    lines.append(_verify_line(root))
    # T-0040: native Windows only. Read from config and the machine-local
    # probe cache; runs no wsl.exe, no pwsh and no git.
    shell = crew_shell.status_line(root)
    if shell:
        lines.append(shell)
    lines.append(_codemap_line(root, cfg))
    lines.append(_metrics_line(root))
    handoff = os.path.isfile(os.path.join(root, ".work", "HANDOFF.md"))
    lines.append("handoff  " + ("pending (.work/HANDOFF.md)" if handoff else "none"))
    interrupted = crew_migrate.find_interrupted(root)
    if interrupted:
        lines.append(f"migrate  INTERRUPTED apply at {interrupted} - /crew:migrate --rollback it")
    if memory:
        lines += _memory_lines(root, MAX_LINES - len(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + [f"... {len(lines) - MAX_LINES + 1} line(s) clipped"]
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--memory", action="store_true", help="add crew_context.py --stats")
    args = parser.parse_args(argv)
    print("\n".join(collect(args.root, memory=args.memory)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
