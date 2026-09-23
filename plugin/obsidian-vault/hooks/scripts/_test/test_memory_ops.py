#!/usr/bin/env python3
"""Regression suite for adopt / import / recall / gardener / schedule / capture.

    python3 hooks/scripts/_test/test_memory_ops.py

Plain assertions, no pytest, same shape as test_vault_ops.py. Everything runs
in a throwaway HOME with a fake Obsidian registry; nothing installs, nothing
schedules, nothing reaches the network. The gardener's processor is a local
python script standing in for `claude -p`.

The guards pinned here, each sabotage-tested (reintroduce the bug -> red):
  * exactly one primary: zero or two is refused and nothing is written
  * import never overwrites: a collision leaves the existing file byte-identical
  * gardener bound: 6 queued -> 5 processed, never more
  * ack only after a write: a processor that claims a file it did not write,
    or that fails, leaves its item queued
  * recall budget: sum(len(line)+1) <= --max-chars, and vault priority holds
  * writers use the primary only: an unmounted primary is refused, never
    replaced by a recall vault
  * ack needs a write: naming a file that existed, untouched, acks nothing
  * git under --commit is bounded: a hanging pre-commit hook is cut off
  * schedule quoting: ' space $(...) ` % in paths are text, never executed
  * import containment (no symlinked dirs) and suffix-collision idempotence
  * adopt refuses while any discovered vault has no role
  * the runner acks on what a before/after vault snapshot shows changed, not on
    the path the processor reported (a misreport, or a note Obsidian moved)
  * a processor that writes nothing, or exits 1, is not acked, and its bounded
    stdout+stderr land in the reason and the run log
  * an item whose session page exists is acked without running the processor;
    `reconcile` without --apply writes nothing
  * the default processor runs with --settings disableAllHooks, CREW_HOOKS=off
    and OBSIDIAN_VAULT_GARDENER=1, and leaves no .crew/ in the vault
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..")
sys.path.insert(0, SCRIPTS)
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_garden  # noqa: E402  pylint: disable=wrong-import-position
import vault_ops  # noqa: E402  pylint: disable=wrong-import-position
import vault_setup  # noqa: E402  pylint: disable=wrong-import-position

FAILURES = []


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def check_true(desc, cond):
    if not cond:
        FAILURES.append(desc)


def check_in(desc, needle, haystack):
    if needle not in haystack:
        FAILURES.append(f"{desc}: {needle!r} not found in {haystack[:600]!r}")


class Sandbox:
    """A throwaway HOME + config + fake Obsidian registry + fixed host id."""

    def __init__(self, config=None, app_vaults=None, host="hosta"):
        self.tmp = tempfile.mkdtemp(prefix="obsidian-memory-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude", "obsidian"))
        self.config_file = os.path.join(self.home, ".claude", "obsidian", "config.json")
        if config is not None:
            with open(self.config_file, "w", encoding="utf-8") as fh:
                json.dump(config, fh)
        self.app_vaults = app_vaults or {}
        self.host = host
        self._saved = {}
        self._old_app_json = None

    def vault(self, name, files=None):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(path, ".obsidian"), exist_ok=True)
        for rel, text in (files or {}).items():
            full = os.path.join(path, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        return path

    def write_config(self, config):
        with open(self.config_file, "w", encoding="utf-8") as fh:
            json.dump(config, fh)

    def config_bytes(self):
        try:
            with open(self.config_file, "rb") as fh:
                return fh.read()
        except OSError:
            return None

    def config(self):
        with open(self.config_file, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def __enter__(self):
        for key in ("HOME", "OBSIDIAN_VAULT_PATH", "OBSIDIAN_VAULT_CONFIG", "OBSIDIAN_VAULT_HOST"):
            self._saved[key] = os.environ.pop(key, None)
        os.environ["HOME"] = self.home
        os.environ["OBSIDIAN_VAULT_HOST"] = self.host
        app_json = os.path.join(self.tmp, "obsidian.json")
        with open(app_json, "w", encoding="utf-8") as fh:
            json.dump({"vaults": self.app_vaults}, fh)
        self._old_app_json = obsidian_common.obsidian_app_json_path
        obsidian_common.obsidian_app_json_path = lambda: app_json
        return self

    def __exit__(self, *_exc):
        obsidian_common.obsidian_app_json_path = self._old_app_json
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = vault_ops.main(argv, prober=object())
    return code, out.getvalue() + err.getvalue()


def tree_snapshot(root):
    snap = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(base, name)
            with open(full, "rb") as fh:
                snap[os.path.relpath(full, root)] = (fh.read(), os.path.getmtime(full))
    return snap


# --- adopt: roles, exactly one primary, idempotence ------------------------------

def _t_adopt():
    with Sandbox() as sb:
        a = sb.vault("alpha")
        b = sb.vault("beta")
        c = sb.vault("gamma")
        sb.write_config({"vaults": {"alpha": {"path": a}, "beta": {"path": b}}})
        sb.app_vaults = {}
        app_json = obsidian_common.obsidian_app_json_path()
        with open(app_json, "w", encoding="utf-8") as fh:
            json.dump({"vaults": {"id-gamma": {"path": c}}}, fh)

        code, out = run_cli(["adopt"])
        check("listing with no roles yet exits 0", code, 0)
        check_in("listing shows a discovered-only vault", "gamma", out)
        check_in("listing shows unassigned", "unassigned", out)

        before = sb.config_bytes()
        code, out = run_cli(["adopt", "--role", "alpha=primary", "--role", "beta=primary"])
        check("two primaries is refused (exit 2)", code, 2)
        check_in("refusal names the reason", "exactly one", out)
        check("two primaries: config untouched", sb.config_bytes(), before)

        code, out = run_cli(["adopt", "--role", "alpha=primary", "--role", "beta=primary",
                             "--apply"])
        check("two primaries refused even with --apply", code, 2)
        check("two primaries --apply: config untouched", sb.config_bytes(), before)

        code, out = run_cli(["adopt", "--role", "alpha=recall", "--apply"])
        check("zero primaries is refused", code, 2)
        check_in("zero primaries names the reason", "no vault has role primary", out)
        check("zero primaries: config untouched", sb.config_bytes(), before)

        code, out = run_cli(["adopt", "--role", "nosuch=recall"])
        check("unknown vault is a usage error", code, 2)

        code, out = run_cli(["adopt", "--role", "alpha=boss"])
        check("unknown role is a usage error", code, 2)

        roles = ["--role", "alpha=primary", "--role", "beta=recall", "--role", "gamma=ignore"]
        code, out = run_cli(["adopt"] + roles)
        check("valid roles dry run exits 1", code, 1)
        check("dry run writes nothing", sb.config_bytes(), before)

        code, out = run_cli(["adopt"] + roles + ["--apply"])
        check("valid roles apply exits 0", code, 0)
        cfg = sb.config()["vaults"]
        check("alpha is primary", cfg["alpha"].get("role"), "primary")
        check("primary is also default", cfg["alpha"].get("default"), True)
        check("beta is recall", cfg["beta"].get("role"), "recall")
        check("gamma (discovered only) was added with its path", cfg["gamma"].get("path"), c)
        check("gamma is ignore", cfg["gamma"].get("role"), "ignore")

        after = sb.config_bytes()
        mtime = os.path.getmtime(sb.config_file)
        code, out = run_cli(["adopt"] + roles + ["--apply"])
        check("idempotent re-run exits 0", code, 0)
        check_in("idempotent re-run says so", "Nothing to change", out)
        check("idempotent re-run leaves bytes identical", sb.config_bytes(), after)
        check("idempotent re-run does not rewrite the file", os.path.getmtime(sb.config_file),
              mtime)

        code, out = run_cli(["adopt", "--role", "beta=primary", "--apply"])
        check("promoting a second primary without demoting the first is refused", code, 2)
        check("...and writes nothing", sb.config_bytes(), after)

        code, out = run_cli(["adopt", "--role", "alpha=recall", "--role", "beta=primary",
                             "--apply"])
        check("moving primary in one call is accepted", code, 0)
        cfg = sb.config()["vaults"]
        check("default moved with primary", (cfg["alpha"].get("default"),
                                              cfg["beta"].get("default")), (None, True))
        check("capture target follows primary", obsidian_common.resolve_vault_path(), b)

        vaults = obsidian_common.discover_vaults()
        chosen, _ = vault_ops.select(vaults, all_vaults=True)
        check("--all never includes an ignore-role vault", sorted(chosen), ["alpha", "beta"])

        code, out = run_cli(["adopt"])
        check("listing a valid role set exits 0", code, 0)
        sb.write_config({"vaults": {"alpha": {"path": a, "role": "primary"},
                                    "beta": {"path": b, "role": "primary"}}})
        code, out = run_cli(["adopt"])
        check("listing a hand-edited two-primary config fails", code, 1)
        check_in("and says why", "[FAIL]", out)


# --- import: dry run, provenance, never overwrite ----------------------------------

def _t_import():
    with Sandbox() as sb:
        primary = sb.vault("mem", {"imported/notes/clash.md": "ORIGINAL - do not touch\n"})
        src = os.path.join(sb.tmp, "notes")
        os.makedirs(os.path.join(src, "sub"))
        with open(os.path.join(src, "plain.md"), "wb") as fh:
            fh.write(b"# Plain\r\nline one\r\nline two\r\n")
        with open(os.path.join(src, "sub", "fm.md"), "w", encoding="utf-8") as fh:
            fh.write("---\ntitle: \"Has FM\"\ntags:\n  - x\n---\nbody\n")
        with open(os.path.join(src, "clash.md"), "w", encoding="utf-8") as fh:
            fh.write("incoming clash\n")
        with open(os.path.join(src, "image.png"), "wb") as fh:
            fh.write(b"\x89PNG")
        sb.write_config({"vaults": {"mem": {"path": primary, "role": "primary",
                                            "default": True}}})

        before = tree_snapshot(primary)
        code, out = run_cli(["import", "--source", src])
        check("import dry run exits 1 (work pending)", code, 1)
        check("import dry run writes nothing", tree_snapshot(primary), before)
        check_in("dry run reports the collision", "COLLISION", out)

        code, out = run_cli(["import", "--source", src, "--apply", "--json"])
        report = json.loads(out[:out.rindex("}") + 1])
        check("apply with a collision exits 1", code, 1)
        check("counts", report["counts"], {"write": 2, "collision": 1})
        check("non-markdown counted", report["non_markdown_skipped"], 1)
        clash = os.path.join(primary, "imported", "notes", "clash.md")
        with open(clash, "r", encoding="utf-8") as fh:
            check("collision never overwrites", fh.read(), "ORIGINAL - do not touch\n")

        plain = os.path.join(primary, "imported", "notes", "plain.md")
        with open(plain, "rb") as fh:
            raw = fh.read()
        check_true("imported file is LF only", b"\r" not in raw)
        text = raw.decode("utf-8")
        check_in("provenance: imported_from is the absolute source path",
                 f"imported_from: {json.dumps(os.path.join(src, 'plain.md'))}", text)
        check_in("provenance: imported_at present", "imported_at: 20", text)
        check_true("body preserved", text.endswith("# Plain\nline one\nline two\n"))

        with open(os.path.join(primary, "imported", "notes", "sub", "fm.md"),
                  "r", encoding="utf-8") as fh:
            fm = fh.read()
        check_true("existing frontmatter kept and extended",
                   fm.startswith("---\ntitle: \"Has FM\"\ntags:\n  - x\nimported_from: "))
        check("only one frontmatter block", fm.count("---\n"), 2)

        snap = tree_snapshot(primary)
        code, out = run_cli(["import", "--source", src, "--apply", "--json"])
        report = json.loads(out[:out.rindex("}") + 1])
        check("re-run: previously imported files are recognised",
              report["counts"].get("already-imported"), 2)
        check("re-run writes nothing new", tree_snapshot(primary), snap)

        code, out = run_cli(["import", "--source", src, "--apply", "--suffix-collisions"])
        suffixed = os.path.join(primary, "imported", "notes", "clash (imported).md")
        check_true("--suffix-collisions writes beside the collision", os.path.isfile(suffixed))
        with open(clash, "r", encoding="utf-8") as fh:
            check("...and still never overwrites", fh.read(), "ORIGINAL - do not touch\n")

        code, out = run_cli(["import", "--source", primary])
        check("importing the primary into itself is refused", code, 2)
        code, out = run_cli(["import", "--source", src, "--dest-subdir", "../escape"])
        check("a dest-subdir escaping the vault is refused", code, 2)


# --- recall: labels, budget, priority, read-only -------------------------------------

def _t_recall():
    with Sandbox() as sb:
        a = sb.vault("alpha", {
            "wiki/Port collisions break the bridge.md":
                "---\ntitle: \"Port collisions break the bridge\"\n---\n# Port collision\n"
                "Two vaults on one port collision: the loser never binds.\n" * 3,
            "other.md": "nothing relevant here\n"})
        b = sb.vault("beta", {"b-note.md": "# Weak\nport mentioned once\n"})
        c = sb.vault("gamma", {"g.md": "# port collision port collision\n"})
        sb.write_config({"vaults": {"alpha": {"path": a, "role": "primary", "default": True},
                                    "beta": {"path": b, "role": "recall"},
                                    "gamma": {"path": c, "role": "ignore"}}})
        before = {k: tree_snapshot(v) for k, v in (("a", a), ("b", b), ("c", c))}

        code, out = run_cli(["recall", "--query", "port collision", "--json"])
        res = json.loads(out)
        check("recall exits 0", code, 0)
        check("default order is primary then recall; ignore excluded", res["vaults"],
              ["alpha", "beta"])
        top = res["results"][0]
        check("top hit labelled with its vault", top["vault"], "alpha")
        check("top hit labelled with its note path", top["path"],
              "wiki/Port collisions break the bridge.md")
        check_true("line carries vault and path",
                   top["line"].startswith("[alpha] wiki/Port collisions break the bridge.md: "))

        code, out = run_cli(["recall", "--query", "port collision", "--vaults", "beta,alpha",
                             "--json"])
        res = json.loads(out)
        check("--vaults order is priority: weaker beta hit ranks first",
              [r["vault"] for r in res["results"]][:2], ["beta", "alpha"])

        for budget in (1, 30, 60, 90, 150, 400, 5000):
            code, out = run_cli(["recall", "--query", "port collision", "--max-chars",
                                 str(budget), "--json"])
            res = json.loads(out)
            used = sum(len(r["line"]) + 1 for r in res["results"])
            check_true(f"max-chars {budget} respected (used {used})", used <= budget)
            check(f"reported chars match at {budget}", res["chars"], used)

        code, out = run_cli(["recall", "--query", "port collision", "--max-chars", "60",
                             "--vaults", "beta,alpha", "--json"])
        res = json.loads(out)
        check("a tight budget keeps the higher-priority vault",
              [r["vault"] for r in res["results"]], ["beta"])
        check_true("and says it truncated", res["truncated"])

        code, out = run_cli(["recall", "--query", "port", "--vaults", "alpha,nosuch,gamma",
                             "--json"])
        res = json.loads(out)
        check("an unknown or ignored vault is an error exit", code, 1)
        check("both are named, not dropped", sorted(e["vault"] for e in res["errors"]),
              ["gamma", "nosuch"])

        after = {k: tree_snapshot(v) for k, v in (("a", a), ("b", b), ("c", c))}
        check("recall is read-only", after, before)


# --- gardener: bound, ack only after write, hosts, lock, owned commits ----------------

PROCESSOR = r'''
import os, sys
vault, ident, mode = sys.argv[1], sys.argv[2], sys.argv[3]
rel = "wiki/daily/" + ident + ".md"
if mode == "existing":
    rel = "wiki/existing.md"   # names a file that is already there, touches nothing
if mode in ("ok", "fail", "misreport", "crash"):
    os.makedirs(os.path.join(vault, "wiki", "daily"), exist_ok=True)
    with open(os.path.join(vault, rel), "w") as fh:
        fh.write("digest for " + ident + "\n")
if mode == "misreport":
    rel = "wiki/concepts/somewhere-else.md"   # wrote the daily note, reports another path
if mode == "moved":
    # What happened on 2026-09-23: the note was written under the vault's own
    # <org>/<project> folder (anew/anew), reported there, and Obsidian's
    # auto-note-mover moved it to wiki/concepts/ (first tag #concept) before
    # the processor exited.
    rel = "wiki/concepts/anew/anew/AWS VPN Client checksums its script.md"
    os.makedirs(os.path.join(vault, os.path.dirname(rel)), exist_ok=True)
    with open(os.path.join(vault, rel), "w") as fh:
        fh.write("---\ntags:\n  - concept\n---\nnote for " + ident + "\n")
    os.replace(os.path.join(vault, rel),
               os.path.join(vault, "wiki", "concepts", os.path.basename(rel)))
if mode == "counted":
    with open(os.path.join(os.path.dirname(vault), "processor-ran"), "a") as fh:
        fh.write(ident + "\n")
if mode == "crash":
    print("Error: Reached max turns (40)")
    sys.stderr.write("boom on stderr\n")
    sys.exit(1)
if mode != "nothing":
    print("GARDENER-WROTE: " + rel)
sys.exit(1 if mode == "fail" else 0)
'''

# Stands in for the `claude` CLI on PATH, so the DEFAULT processor argv is what
# runs. It behaves like crew's hooks did inside the vault unless the argv turns
# every hook off: SessionStart creates `.crew/config.json` in its cwd, and the
# capture hook queues the processor's own session.
FAKE_CLAUDE = r'''
import json, os, sys
argv = sys.argv[1:]
settings = {}
if "--settings" in argv:
    settings = json.loads(argv[argv.index("--settings") + 1])
out = os.environ["FAKE_CLAUDE_RECORD"]
with open(out, "w") as fh:
    json.dump({"argv": argv, "CREW_HOOKS": os.environ.get("CREW_HOOKS"),
               "OBSIDIAN_VAULT_GARDENER": os.environ.get("OBSIDIAN_VAULT_GARDENER")}, fh)
if settings.get("disableAllHooks") is not True:
    os.makedirs(".crew", exist_ok=True)
    with open(os.path.join(".crew", "config.json"), "w") as fh:
        fh.write("{}\n")
os.makedirs(os.path.join("wiki", "daily"), exist_ok=True)
with open(os.path.join("wiki", "daily", "fake.md"), "a") as fh:
    fh.write("digest\n")
print("GARDENER-WROTE: wiki/daily/fake.md")
'''


def _queue_line(sid, transcript, ts="2026-09-20 10:00"):
    return f"- [ ] {ts} | SessionEnd | session={sid} | cwd=/w | transcript={transcript}\n"


def _garden_fixture(sb, count, host="hosta", legacy=None):
    vault = sb.vault("mem")
    tdir = os.path.join(sb.tmp, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    lines = []
    for n in range(count):
        t = os.path.join(tdir, f"s{n}.jsonl")
        with open(t, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        lines.append(_queue_line(f"s{n}", t, f"2026-09-20 10:{n:02d}"))
    os.makedirs(os.path.join(vault, "inbox"), exist_ok=True)
    with open(os.path.join(vault, "inbox", f"pending-reflect.{host}.md"), "w",
              encoding="utf-8") as fh:
        fh.write("# queue\n\n" + "".join(lines))
    if legacy is not None:
        with open(os.path.join(vault, "inbox", "pending-reflect.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(legacy)
    sb.write_config({"vaults": {"mem": {"path": vault, "role": "primary", "default": True}},
                     "gardener": {"host": "hosta"}})
    proc = os.path.join(sb.tmp, "proc.py")
    with open(proc, "w", encoding="utf-8") as fh:
        fh.write(PROCESSOR)
    return vault, tdir, proc


def _proc(proc, mode):
    return json.dumps([sys.executable, proc, "{vault}", "{id}", mode])


def _t_garden_bound():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 6)
        check("six queued", len(vault_garden.read_queue(vault)), 6)
        code, out = run_cli(["garden-run", "--processor", _proc(proc, "ok"), "--json"])
        summary = json.loads(out[out.index("{"):])
        check("bounded run exits 0", code, 0)
        check("six queued -> exactly five processed", len(summary["acked"]), 5)
        check("oldest first", summary["acked"], ["s0", "s1", "s2", "s3", "s4"])
        check("one left", [i["id"] for i in vault_garden.read_queue(vault)], ["s5"])
        check("the sixth was not started", summary["not_started"], 1)

        code, out = run_cli(["garden-run", "--max", "50", "--processor", _proc(proc, "ok"),
                             "--json"])
        summary = json.loads(out[out.index("{"):])
        check("--max cannot raise the bound past five (1 left anyway)",
              len(summary["acked"]), 1)
        check("queue empty", vault_garden.read_queue(vault), [])

    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 9)
        summary = vault_garden.garden_run(vault, max_items=99,
                                          processor=json.loads(_proc(proc, "ok")))
        check("garden_run() itself clamps max_items to five", len(summary["acked"]), 5)


def _t_garden_ack_after_write():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 2)
        code, out = run_cli(["garden-run", "--processor", _proc(proc, "lie"), "--json"])
        summary = json.loads(out[out.index("{"):])
        check("a claimed-but-unwritten file acks nothing", summary["acked"], [])
        check("a lying processor exits 1", code, 1)
        check("both items stay queued", len(vault_garden.read_queue(vault)), 2)
        check_true("no ledger written", not os.path.exists(vault_garden.ledger_path(vault)))

        code, out = run_cli(["garden-run", "--processor", _proc(proc, "fail"), "--json"])
        summary = json.loads(out[out.index("{"):])
        check("a failing processor acks nothing even though it wrote", summary["acked"], [])
        check("items stay queued after a failed write", len(vault_garden.read_queue(vault)), 2)

        code, out = run_cli(["ack", "--id", "s0"])
        check("ack with no written file is refused", code, 1)
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "wiki/nope.md"])
        check("ack naming a missing file is refused", code, 1)
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "../outside.md"])
        check("ack naming a path outside the vault is refused", code, 1)
        empty = os.path.join(vault, "empty.md")
        with open(empty, "w", encoding="utf-8"):
            pass
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "empty.md"])
        check("ack naming an empty file is refused", code, 1)
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "wiki/daily/s0.md"])
        check("ack after a real write succeeds", code, 0)
        check("acked item leaves the queue", [i["id"] for i in vault_garden.read_queue(vault)],
              ["s1"])
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "wiki/daily/s0.md"])
        check("acking twice is refused", code, 1)


def _t_garden_hosts_and_legacy():
    legacy = ("# old\n\n"
              + "- [x] 2026-01-01 09:00 | SessionEnd | session=old-done | cwd=/ | transcript=/x\n"
              + "- [ ] 2026-01-01 09:01 | SessionEnd | session=s1 | cwd=/ | transcript=/x\n"
              + "- [ ] 2026-01-01 09:02 | SessionEnd | session=old-pending | cwd=/ | "
                "transcript=/gone\n")
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 2, legacy=legacy)
        ids = [i["id"] for i in vault_garden.read_queue(vault)]
        check("legacy queue still read; checked-off skipped; duplicate id merged",
              sorted(ids), ["old-pending", "s0", "s1"])
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "ok")))
        check("a transcript missing on this host is unresolved, not processed",
              summary["unresolved_here"], ["old-pending"])
        check("and does not use up a slot", sorted(summary["acked"]), ["s0", "s1"])

    with Sandbox(host="hostb") as sb:
        _garden_fixture(sb, 1)
        code, out = run_cli(["garden-run", "--processor", "[\"true\"]"])
        check("a non-designated host refuses", code, 1)
        check_in("and names the designated host", "hosta", out)

    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        check_true("lock taken", vault_garden.take_lock(vault))
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "ok")))
        check("a second concurrent run does nothing", summary.get("locked"), True)
        vault_garden.release_lock(vault)

    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 3)
        ticks = iter([0, 0, 700, 700, 700])
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "ok")),
                                          clock=lambda: next(ticks))
        check("time bound: nothing starts once ten minutes are spent",
              (len(summary["acked"]), summary["not_started"]), (1, 2))


def _t_garden_owned_commit():
    if not shutil.which("git"):
        print("SKIP: git not on PATH - owned-commit case not run")
        return
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

        def git(*args):
            return subprocess.run(["git", "-C", vault] + list(args), capture_output=True,
                                  text=True, env=env, check=False)
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        with open(os.path.join(vault, "someone-else.md"), "w", encoding="utf-8") as fh:
            fh.write("staged by another writer\n")
        git("add", "someone-else.md")
        old = {k: os.environ.get(k) for k in env if k.startswith("GIT_")}
        os.environ.update({k: v for k, v in env.items() if k.startswith("GIT_")})
        try:
            summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "ok")),
                                              commit=True)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        check("commit step succeeded", (summary["commit"] or (None,))[0], True)
        committed = git("show", "--name-only", "--format=", "HEAD").stdout.split()
        check("only the run's own files are committed", sorted(committed),
              sorted(["wiki/daily/s0.md", "inbox/reflected.hosta.md"]))
        staged = git("diff", "--cached", "--name-only").stdout.split()
        check("another writer's staged file is left staged", staged, ["someone-else.md"])


# --- schedule: generated units, never installed --------------------------------------

def _t_schedule():
    with Sandbox() as sb:
        vault = sb.vault("mem")
        sb.write_config({"vaults": {"mem": {"path": vault, "role": "primary"}}})
        home_before = tree_snapshot(sb.home)
        code, out = run_cli(["schedule", "--os", "cron", "--time", "03:15"])
        check("cron unit exits 0", code, 0)
        check_in("cron line at 03:15", "15 3 * * * ", out)
        check_in("cron line runs garden-run", "garden-run", out)
        check_in("cron install is printed, not run", "crontab -", out)
        check_in("cron line carries a PATH (cron's own PATH lacks claude)", "* * * PATH=", out)
        code, out = run_cli(["schedule", "--os", "systemd"])
        check_in("systemd service", "obsidian-gardener.service", out)
        check_in("systemd timer", "OnCalendar=*-*-* 02:23:00", out)
        check_in("systemd persistent", "Persistent=true", out)
        check_in("systemd unit carries a PATH", 'Environment="PATH=', out)
        check_in("systemd enable printed", "systemctl --user enable --now", out)
        code, out = run_cli(["schedule", "--os", "windows"])
        check_in("windows task", "Register-ScheduledTask -TaskName 'Obsidian Gardener'", out)
        check_in("windows daily trigger", "New-ScheduledTaskTrigger -Daily -At '02:23'", out)
        check_in("windows catch-up", "-StartWhenAvailable", out)
        check("printing units wrote nothing under HOME", tree_snapshot(sb.home), home_before)
        code, out = run_cli(["schedule", "--os", "cron", "--time", "25:00"])
        check("bad time is a usage error", code, 2)

        code, out = run_cli(["schedule", "--os", "cron", "--designate"])
        check("designate dry run exits 1", code, 1)
        check("designate dry run writes nothing", tree_snapshot(sb.home), home_before)
        code, out = run_cli(["schedule", "--os", "cron", "--designate", "--apply"])
        check("designate apply exits 0", code, 0)
        check("gardener.host written", sb.config()["gardener"]["host"], "hosta")
        check("vaults block survives", sb.config()["vaults"]["mem"]["role"], "primary")
        code, out = run_cli(["schedule", "--os", "cron", "--designate", "--apply"])
        check_in("designate is idempotent", "Nothing to change", out)


# --- capture: per-host queue, legacy de-duplication ------------------------------------

def _t_capture():
    with Sandbox() as sb:
        vault = sb.vault("mem", {"inbox/pending-reflect.md":
                                 "- [ ] 2026-01-01 00:00 | SessionEnd | session=legacy1 | "
                                 "cwd=/ | transcript=/t\n"})
        sb.write_config({"vaults": {"mem": {"path": vault, "role": "primary",
                                            "default": True}}})
        script = os.path.join(SCRIPTS, "vault_capture.py")

        def capture(sid, trigger="SessionEnd"):
            return subprocess.run([sys.executable, script, trigger],
                                  input=json.dumps({"session_id": sid, "cwd": "/w",
                                                    "transcript_path": "/t.jsonl"}),
                                  capture_output=True, text=True, env=dict(os.environ),
                                  check=False)
        capture("new1")
        capture("new1", "PreCompact")
        capture("legacy1")
        host_file = os.path.join(vault, "inbox", "pending-reflect.hosta.md")
        check_true("capture writes the per-host queue", os.path.isfile(host_file))
        with open(host_file, "rb") as fh:
            data = fh.read()
        check("one entry per session across triggers", data.count(b"session=new1 "), 1)
        check("a session already in the legacy queue is not queued again",
              data.count(b"session=legacy1 "), 0)
        check_true("capture output is LF only", b"\r" not in data)
        with open(os.path.join(vault, "inbox", "pending-reflect.md"), "r",
                  encoding="utf-8") as fh:
            check("legacy queue is not written", fh.read().count("session="), 1)
        os.environ["OBSIDIAN_VAULT_HOST"] = "hostb"
        capture("new2")
        check_true("a second host gets its own file",
                   os.path.isfile(os.path.join(vault, "inbox", "pending-reflect.hostb.md")))


# --- detect / install: three states, never installs on a dry run ------------------------

def _t_detect_install():
    saved = (vault_setup.which, vault_setup.run, vault_setup.exists)
    calls = []

    def fake(which_map, run_map, files):
        vault_setup.which = which_map.get
        vault_setup.exists = lambda p: p in files

        def run(argv, timeout=60):  # pylint: disable=unused-argument
            calls.append(argv)
            return run_map.get(argv[0], (1, ""))
        vault_setup.run = run
    try:
        with Sandbox():
            fake({"snap": "/usr/bin/snap"}, {"snap": (0, "obsidian 1.9")}, {"/snap/bin/obsidian"})
            check("snap install detected", vault_setup.detect("linux")["state"], "installed")
            calls.clear()
            code, out = run_cli(["install-obsidian", "--os", "linux", "--apply"])
            check("already installed: exit 0", code, 0)
            check_in("already installed: says so", "already installed", out)
            check("already installed: no install command run",
                  [c for c in calls if "install" in c], [])

            fake({"snap": "/usr/bin/snap"}, {"snap": (1, "")}, set())
            check("snap probe ran and found nothing -> missing",
                  vault_setup.detect("linux")["state"], "missing")
            calls.clear()
            code, out = run_cli(["install-obsidian", "--os", "linux"])
            check("dry run exits 1", code, 1)
            check_in("dry run prints the exact command", "sudo snap install obsidian --classic",
                     out)
            check("dry run runs no install", [c for c in calls if "install" in c], [])
            calls.clear()
            code, out = run_cli(["install-obsidian", "--os", "linux", "--apply"])
            check("apply runs exactly the printed command",
                  [c for c in calls if "install" in c],
                  [["sudo", "snap", "install", "obsidian", "--classic"]])

            fake({}, {}, set())
            check("no probe could run -> unknown, not missing",
                  vault_setup.detect("linux")["state"], "unknown")
            calls.clear()
            code, out = run_cli(["install-obsidian", "--os", "linux", "--apply"])
            check("unknown refuses to install", code, 1)
            check("unknown ran nothing", calls, [])

            fake({"winget": "winget"}, {"winget": (0, "No installed package found")}, set())
            check("winget without the id -> missing", vault_setup.detect("windows")["state"],
                  "missing")
            code, out = run_cli(["install-obsidian", "--os", "windows"])
            check_in("winget command", "winget install --id Obsidian.Obsidian -e", out)

            fake({"flatpak": "/usr/bin/flatpak"}, {"flatpak": (0, "")}, set())
            check("flatpak info exit 0 -> installed", vault_setup.detect("linux")["state"],
                  "installed")
    finally:
        vault_setup.which, vault_setup.run, vault_setup.exists = saved


def _t_create_vault_and_config_override():
    with Sandbox() as sb:
        target = os.path.join(sb.tmp, "fresh")
        code, out = run_cli(["create-vault", "--name", "fresh", "--path", target])
        check("create-vault dry run exits 1", code, 1)
        check_true("create-vault dry run creates nothing", not os.path.exists(target))
        code, out = run_cli(["create-vault", "--name", "fresh", "--path", target, "--apply"])
        check("create-vault apply exits 0", code, 0)
        check_true(".obsidian created", os.path.isdir(os.path.join(target, ".obsidian")))
        check("named in config", sb.config()["vaults"]["fresh"]["path"], target)
        code, out = run_cli(["create-vault", "--name", "fresh", "--path", target, "--apply"])
        check("create-vault is idempotent", code, 0)
        check_in("and says so", "Nothing to do", out)

        alt = os.path.join(sb.tmp, "alt-config.json")
        os.environ["OBSIDIAN_VAULT_CONFIG"] = alt
        try:
            check("OBSIDIAN_VAULT_CONFIG overrides the path", obsidian_common.config_path(), alt)
            obsidian_common.write_config({"vaults": {}})
            check_true("write_config honours the override", os.path.isfile(alt))
            check_true("and leaves no temp file behind",
                       not [f for f in os.listdir(sb.tmp) if ".tmp-" in f])
        finally:
            os.environ.pop("OBSIDIAN_VAULT_CONFIG", None)


# --- review round 1 regressions ----------------------------------------------------------

def _t_writers_primary_only():
    """An unmounted primary is refused, never replaced by a recall vault."""
    with Sandbox() as sb:
        recall = sb.vault("aaa-recall", {"note.md": "recall only\n"})
        missing = os.path.join(sb.tmp, "unmounted-primary")
        src = os.path.join(sb.tmp, "notes")
        os.makedirs(src)
        with open(os.path.join(src, "n.md"), "w", encoding="utf-8") as fh:
            fh.write("incoming\n")
        sb.write_config({"vaults": {"aaa-recall": {"path": recall, "role": "recall"},
                                    "zzz": {"path": missing, "role": "primary",
                                            "default": True}},
                         "gardener": {"host": "hosta"}})
        before = tree_snapshot(recall)
        check("writer_vault names the primary and no path",
              obsidian_common.writer_vault()[:2], ("zzz", None))

        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "vault_capture.py"),
                               "SessionEnd"],
                              input=json.dumps({"session_id": "x1", "cwd": "/w",
                                                "transcript_path": "/t.jsonl"}),
                              capture_output=True, text=True, env=dict(os.environ), check=False)
        check("capture with an unmounted primary still exits 0", proc.returncode, 0)
        check_in("capture says why it wrote nothing", "not available", proc.stderr)
        code, out = run_cli(["import", "--source", src, "--apply"])
        check("import with an unmounted primary is refused", code, 2)
        check_in("import names the unavailable primary", "zzz", out)
        code, _ = run_cli(["garden-run", "--force-host", "--processor", '["true"]'])
        check("garden-run with an unmounted primary is refused", code, 2)
        code, _ = run_cli(["drain", "--apply", "--force-host"])
        check("drain with an unmounted primary is refused", code, 2)
        code, _ = run_cli(["ack", "--id", "x1", "--wrote", "note.md"])
        check("ack with an unmounted primary is refused", code, 2)
        check("the recall vault was not written by any writer", tree_snapshot(recall), before)

        sb.write_config({"vaults": {"aaa": {"path": recall},
                                    "zzz": {"path": missing, "default": True}}})
        check("pre-roles config: an unmounted default is not replaced either",
              obsidian_common.writer_vault()[:2], ("zzz", None))


def _t_garden_ack_needs_a_write():
    """Naming a file that already existed, untouched, proves nothing."""
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        existing = os.path.join(vault, "wiki", "existing.md")
        os.makedirs(os.path.dirname(existing), exist_ok=True)
        with open(existing, "w", encoding="utf-8") as fh:
            fh.write("was already here\n")
        code, out = run_cli(["garden-run", "--processor", _proc(proc, "existing"), "--json"])
        summary = json.loads(out[out.index("{"):])
        check("a no-op processor naming an existing file acks nothing", summary["acked"], [])
        check("and exits 1", code, 1)
        check("the item stays queued", len(vault_garden.read_queue(vault)), 1)
        check_in("the reason says unchanged", "unchanged", json.dumps(summary["failed"]))

        old = 1_600_000_000  # 2020 - before the fixture's 2026-09-20 capture stamp
        os.utime(existing, (old, old))
        code, out = run_cli(["ack", "--id", "s0", "--wrote", "wiki/existing.md"])
        check("manual ack of a file older than the capture is refused", code, 1)
        check_in("and says why", "before this session was captured", out)

        code, out = run_cli(["garden-run", "--processor", _proc(proc, "ok"), "--json"])
        summary = json.loads(out[out.index("{"):])
        check("a processor that really writes is still acked", summary["acked"], ["s0"])


HANG_HOOK = "#!/bin/sh\nsleep 900\n"


def _t_garden_commit_bounded():
    if not shutil.which("git") or os.name != "posix":
        print("SKIP: git or a POSIX shell missing - bounded-commit case not run")
        return
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
                subprocess.run(["git", "-C", vault] + args, capture_output=True, check=False)
            hook = os.path.join(vault, ".git", "hooks", "pre-commit")
            with open(hook, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(HANG_HOOK)
            os.chmod(hook, 0o755)
            started = time.monotonic()
            summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "ok")),
                                              seconds=4, commit=True)
            elapsed = time.monotonic() - started
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        check_true(f"a hanging pre-commit hook is cut off inside the bound ({elapsed:.1f}s)",
                   elapsed < 30)
        check("the commit is reported as not made", (summary["commit"] or (None,))[0], False)
        check_in("and says it timed out", "timed out", (summary["commit"] or ("", ""))[1])
        check_true("git's index.lock is not left behind",
                   not os.path.exists(os.path.join(vault, ".git", "index.lock")))


def _read_or_none(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _t_schedule_quoting():
    """Paths with ' space $(...) ` and % are passed as text, never executed."""
    if os.name != "posix":
        print("SKIP: POSIX shell missing - cron quoting case not run")
        return
    tmp = tempfile.mkdtemp(prefix="obsidian-quote-test-")
    try:
        weird = os.path.join(tmp, "it's a $(touch PWNED1) `touch PWNED2` 50% dir")
        os.makedirs(weird)
        fake_py = os.path.join(weird, "py thon")
        with open(fake_py, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$(dirname "$0")/argv.txt"\n')
        os.chmod(fake_py, 0o755)
        script = os.path.join(weird, "vault_ops.py")
        log = os.path.join(weird, "garden log.txt")
        shim = os.path.join(tmp, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "crontab"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write('#!/bin/sh\n[ "$1" = "-l" ] && exit 1\ncat > "$CRONTAB_OUT"\n')
        os.chmod(os.path.join(shim, "crontab"), 0o755)

        unit = vault_garden.unit_text("cron", fake_py, script, "03:15", log,
                                      path_env="/usr/bin:/bin")
        command = unit["line"].split(" ", 5)[5].replace("\\%", "%")
        subprocess.run(["sh", "-c", command], cwd=tmp, check=False)
        check("cron line passes each path as one argument",
              (_read_or_none(os.path.join(weird, "argv.txt")) or "").splitlines(),
              [script, "garden-run"])
        check_true("cron line appends to the quoted log path", os.path.isfile(log))

        installed = os.path.join(tmp, "installed-crontab")
        subprocess.run(["sh", "-c", unit["install"][0]], cwd=tmp, check=False,
                       env=dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"],
                                CRONTAB_OUT=installed))
        check("install writes the line verbatim", _read_or_none(installed), unit["line"] + "\n")
        check_true("nothing in a path was executed at run or install time",
                   not any(n.startswith("PWNED") for n in os.listdir(tmp) + os.listdir(weird)))

        service = vault_garden.unit_text("systemd", fake_py, script, "03:15", log,
                                         path_env="/usr/bin:/bin")["files"]
        text = next(v for k, v in service.items() if k.endswith(".service"))
        check_in("systemd: $ is doubled, so no variable expansion", "$$(touch PWNED1)", text)
        check_in("systemd: % is doubled, so no specifier expansion", "50%% dir", text)

        win = vault_garden.unit_text("windows", fake_py, script, "03:15", log)
        pwsh = shutil.which("pwsh")
        if not pwsh:
            print("SKIP: pwsh not on PATH - PowerShell literal case not run")
            return
        match = re.search(r"-Execute ('(?:[^']|'')*') -Argument ('(?:[^']|'')*')",
                          win["install"][0])
        check_true("windows install carries two PowerShell literals", match is not None)
        if match:
            probe = (f"[Console]::Out.Write({match.group(1)} + [char]10 + "
                     f"{match.group(2)})")
            got = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", probe],
                                 cwd=tmp, capture_output=True, text=True, check=False).stdout
            check("PowerShell reads -Execute and -Argument back as the exact text",
                  got.split("\n"), [fake_py, subprocess.list2cmdline([script, "garden-run"])])
            check_true("and executed nothing", not any(n.startswith("PWNED")
                                                        for n in os.listdir(tmp)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _t_import_containment_and_suffix_idempotence():
    with Sandbox() as sb:
        primary = sb.vault("mem", {"imported/notes/clash.md": "ORIGINAL\n"})
        src = os.path.join(sb.tmp, "notes")
        os.makedirs(src)
        with open(os.path.join(src, "clash.md"), "w", encoding="utf-8") as fh:
            fh.write("incoming clash\n")
        sb.write_config({"vaults": {"mem": {"path": primary, "role": "primary",
                                            "default": True}}})

        code, _ = run_cli(["import", "--source", src, "--apply", "--suffix-collisions"])
        check("first suffixed import writes", code, 0)
        snap = tree_snapshot(primary)
        code, out = run_cli(["import", "--source", src, "--apply", "--suffix-collisions",
                             "--json"])
        report = json.loads(out[:out.rindex("}") + 1])
        check("second suffixed import is a no-op", report["counts"], {"already-imported": 1})
        check("...and writes nothing", tree_snapshot(primary), snap)
        check_true("no (imported 2) copy",
                   not os.path.exists(os.path.join(primary, "imported", "notes",
                                                   "clash (imported 2).md")))

        with open(os.path.join(src, "clash.md"), "w", encoding="utf-8") as fh:
            fh.write("incoming clash, edited since\n")
        code, out = run_cli(["import", "--source", src, "--apply", "--suffix-collisions",
                             "--json"])
        report = json.loads(out[:out.rindex("}") + 1])
        check("a changed source is imported again beside the old copy",
              report["counts"], {"write-suffixed": 1})

    if not hasattr(os, "symlink"):
        return
    with Sandbox() as sb:
        primary = sb.vault("mem")
        outside = os.path.join(sb.tmp, "outside")
        os.makedirs(outside)
        os.makedirs(os.path.join(primary, "imported"))
        try:
            os.symlink(outside, os.path.join(primary, "imported", "notes"))
        except OSError:
            print("SKIP: cannot create a symlink here - containment case not run")
            return
        src = os.path.join(sb.tmp, "notes")
        os.makedirs(os.path.join(src, "sub"))
        for rel in ("a.md", os.path.join("sub", "b.md")):
            with open(os.path.join(src, rel), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        sb.write_config({"vaults": {"mem": {"path": primary, "role": "primary",
                                            "default": True}}})
        code, out = run_cli(["import", "--source", src, "--apply", "--json"])
        report = json.loads(out[:out.rindex("}") + 1])
        check("an import through a symlinked dir exits 1", code, 1)
        check("every file is refused as outside-vault", report["counts"], {"outside-vault": 2})
        check("nothing was created outside the vault", os.listdir(outside), [])


def _t_adopt_every_vault_gets_a_role():
    with Sandbox() as sb:
        a = sb.vault("alpha")
        b = sb.vault("beta")
        c = sb.vault("gamma")
        sb.write_config({"vaults": {"alpha": {"path": a}, "beta": {"path": b}}})
        with open(obsidian_common.obsidian_app_json_path(), "w", encoding="utf-8") as fh:
            json.dump({"vaults": {"id-gamma": {"path": c}}}, fh)
        before = sb.config_bytes()
        code, out = run_cli(["adopt", "--role", "alpha=primary", "--apply"])
        check("a primary with other vaults unassigned is refused", code, 2)
        check_in("the unassigned vaults are listed", "beta, gamma", out)
        check("...and nothing is written", sb.config_bytes(), before)
        code, out = run_cli(["adopt", "--role", "alpha=primary", "--role", "beta=recall",
                             "--apply"])
        check("a discovered-only vault left unassigned is refused too", code, 2)
        check_in("and named", "gamma", out)
        sb.write_config({"vaults": {"alpha": {"path": a, "role": "primary", "default": True},
                                    "beta": {"path": b}}})
        code, out = run_cli(["adopt"])
        check("listing a partly assigned config fails", code, 1)
        check_in("and names the gap", "no role", out)


# --- T7: ack by vault snapshot, stderr, dedupe, reconcile, hooks off ------------------

def _ledger_text(vault):
    return _read_or_none(vault_garden.ledger_path(vault)) or ""


def _session_page(vault, sid, name="Session - already distilled 2026-09-23.md"):
    path = os.path.join(vault, "wiki", "sessions", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'---\ntype: session\ntitle: "x"\nsession_id: "{sid}"\n---\n\n# x\n')
    return "wiki/sessions/" + name


def _t_garden_acks_on_what_changed_not_what_was_reported():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "misreport")))
        check("a processor that reports a different path than it wrote is acked",
              summary["acked"], ["s0"])
        check("the run's written list is what changed, not what was reported",
              summary["written"], ["wiki/daily/s0.md"])
        check_in("the ledger records the file that really changed",
                 "notes=wiki/daily/s0.md", _ledger_text(vault))


def _t_garden_note_moved_by_obsidian_is_acked():
    """The 2026-09-23 item 1 regression: reported wiki/concepts/anew/anew/..., found
    at wiki/concepts/... . No code here builds that path - the anew/anew folder is
    the vault's own <org>/<project> convention - so the fix is to stop trusting it."""
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        os.makedirs(os.path.join(vault, "wiki", "concepts", "anew", "anew"))
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "moved")))
        check("a note moved after it was written still acks its item", summary["acked"], ["s0"])
        check("the moved note is what the ledger names",
              summary["written"], ["wiki/concepts/AWS VPN Client checksums its script.md"])
        log = _read_or_none(vault_garden.log_path()) or ""
        check_in("the stale reported path is logged as a hint, verbatim (not doubled)",
                 "reported but not found changed: wiki/concepts/anew/anew/AWS VPN", log)
        check_true("and never with the domain folder doubled again",
                   "anew/anew/anew" not in log + _ledger_text(vault))


def _t_garden_nothing_written_is_not_acked():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "nothing")))
        check("a processor that writes nothing is not acked", summary["acked"], [])
        reason = json.dumps(summary["failed"])
        check_in("the reason says nothing changed", "no file in the vault was created or changed",
                 reason)
        check_in("and the reason is in the run log",
                 "left queued s0: no file in the vault was created or changed",
                 _read_or_none(vault_garden.log_path()) or "")
        check("the item stays queued", len(vault_garden.read_queue(vault)), 1)


def _t_garden_failed_processor_output_is_captured():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 1)
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "crash")))
        check("an exit-1 processor is not acked even though it wrote", summary["acked"], [])
        reason = (summary["failed"] or [{"reason": ""}])[0]["reason"]
        check_in("the exit status is in the reason", "processor exited 1", reason)
        check_in("stderr is in the reason", "stderr: boom on stderr", reason)
        check_in("stdout too - claude -p prints its own errors there",
                 "stdout: Error: Reached max turns (40)", reason)
        check_in("and the log has it", "boom on stderr",
                 _read_or_none(vault_garden.log_path()) or "")


def _t_garden_dedupe_acks_without_processing():
    with Sandbox() as sb:
        vault, _, proc = _garden_fixture(sb, 2)
        page = _session_page(vault, "s0")
        summary = vault_garden.garden_run(vault, processor=json.loads(_proc(proc, "counted")))
        check("the item whose session page exists is acked without the processor",
              summary["deduped"], ["s0"])
        ran = (_read_or_none(os.path.join(sb.tmp, "processor-ran")) or "").split()
        check("the processor ran only for the other item", ran, ["s1"])
        check_in("the ledger names the session page and how", f"notes={page} | by=dedupe",
                 _ledger_text(vault))
        check("s0 left the queue; s1 wrote nothing and stays",
              [i["id"] for i in vault_garden.read_queue(vault)], ["s1"])


def _t_reconcile_dry_run_writes_nothing():
    with Sandbox() as sb:
        vault, _, _ = _garden_fixture(sb, 2)
        page = _session_page(vault, "s1")
        before = tree_snapshot(sb.tmp)
        code, out = run_cli(["reconcile"])
        check("reconcile dry run exits 1 when something is reconcilable", code, 1)
        check_in("and names what it would ack", f"would ack s1  <- {page}", out)
        check("the dry run wrote nothing anywhere under the sandbox", tree_snapshot(sb.tmp),
              before)
        code, out = run_cli(["reconcile", "--apply"])
        check("reconcile --apply exits 0", code, 0)
        check("s1 acked, s0 left", [i["id"] for i in vault_garden.read_queue(vault)], ["s0"])
        check_in("by=reconcile in the ledger", "| by=reconcile", _ledger_text(vault))


def _t_processor_runs_with_hooks_off():
    argv = vault_garden.default_processor("/v", {"id": "abc", "text": "t", "transcript": "?"})
    settings = argv[argv.index("--settings") + 1] if "--settings" in argv else "{}"
    check("the default processor passes --settings with disableAllHooks true",
          json.loads(settings).get("disableAllHooks"), True)
    if os.name != "posix":
        print("SKIP: no POSIX shebang - fake-claude end-to-end case not run")
        return
    with Sandbox() as sb:
        vault, _, _ = _garden_fixture(sb, 1)
        bindir = os.path.join(sb.tmp, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "claude")
        with open(fake, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"#!{sys.executable}\n" + FAKE_CLAUDE)
        os.chmod(fake, 0o755)
        record = os.path.join(sb.tmp, "fake-claude.json")
        saved = {k: os.environ.get(k) for k in ("PATH", "FAKE_CLAUDE_RECORD")}
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
        os.environ["FAKE_CLAUDE_RECORD"] = record
        try:
            summary = vault_garden.garden_run(vault)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        seen = json.loads(_read_or_none(record) or "{}")
        check("the real default argv reached the fake claude", seen.get("argv", [])[:1], ["-p"])
        check("CREW_HOOKS=off in the processor's environment", seen.get("CREW_HOOKS"), "off")
        check("OBSIDIAN_VAULT_GARDENER=1 in the processor's environment",
              seen.get("OBSIDIAN_VAULT_GARDENER"), "1")
        check_true("no .crew/ is created in the vault",
                   not os.path.exists(os.path.join(vault, ".crew")))
        check("and the item is acked on what it wrote", summary["acked"], ["s0"])


def _t_snapshot_bounds_and_touch():
    with Sandbox() as sb:
        vault = sb.vault("snap", {"wiki/a.md": "a\n", "inbox/q.md": "q\n",
                                  ".obsidian/app.json": "{}", "wiki/b.md": "b\n"})
        before = vault_garden.snapshot(vault)
        check("inbox/ and dot-directories are outside the snapshot",
              sorted(before["files"]), ["wiki/a.md", "wiki/b.md"])
        future = time.time() + 5
        os.utime(os.path.join(vault, "wiki", "a.md"), (future, future))
        after = vault_garden.snapshot(vault, previous=before)
        check("a touch with identical content is not a write",
              vault_garden.changed_files(before, after), [])
        old = vault_garden.MAX_SNAPSHOT_FILES
        vault_garden.MAX_SNAPSHOT_FILES = 1
        try:
            capped = vault_garden.snapshot(vault)
        finally:
            vault_garden.MAX_SNAPSHOT_FILES = old
        check("an over-size vault is reported incomplete, not truncated quietly",
              capped["complete"], False)


for case in (_t_adopt, _t_import, _t_recall, _t_garden_bound, _t_garden_ack_after_write,
             _t_garden_hosts_and_legacy, _t_garden_owned_commit, _t_schedule, _t_capture,
             _t_detect_install, _t_create_vault_and_config_override,
             _t_writers_primary_only, _t_garden_ack_needs_a_write, _t_garden_commit_bounded,
             _t_schedule_quoting, _t_import_containment_and_suffix_idempotence,
             _t_adopt_every_vault_gets_a_role,
             _t_garden_acks_on_what_changed_not_what_was_reported,
             _t_garden_note_moved_by_obsidian_is_acked, _t_garden_nothing_written_is_not_acked,
             _t_garden_failed_processor_output_is_captured,
             _t_garden_dedupe_acks_without_processing, _t_reconcile_dry_run_writes_nothing,
             _t_processor_runs_with_hooks_off, _t_snapshot_bounds_and_touch):
    try:
        case()
    except Exception as exc:  # pylint: disable=broad-except
        FAILURES.append(f"{case.__name__} raised {type(exc).__name__}: {exc}")

print(f"RESULT: {len(FAILURES)} failed")
for failure in FAILURES:
    print("FAIL:", failure)
sys.exit(1 if FAILURES else 0)
