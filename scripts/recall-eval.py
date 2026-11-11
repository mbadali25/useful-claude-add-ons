#!/usr/bin/env python3
"""Recall evaluation harness for the obsidian-vault plugin (stdlib only, no live vault).

    python3 scripts/recall-eval.py [--golden FILE] [--scripts-dir DIR] [--latency-runs N]
        [--bulk N] [--min-recall X] [--min-precision X] [--min-mrr X] [--max-rejected N]
        [--max-p95-ms MS] [--fail-on-deadline] [--strict-gaps] [--json]

Builds a fixture vault in a temp directory (scripts/recall_eval_fixture.py), points the
recall code at it through OBSIDIAN_VAULT_CONFIG, runs a golden query set
(scripts/_test/recall-eval/golden.json) and prints one row per case plus aggregates:

  quality   recall@k, precision@k, MRR, rejected notes that came back, pairwise order
            checks (current above superseded, project match above other, vault priority)
  budget    truncated flag, held-back count (hits that ranked but did not fit the budget,
            computed here as ranked-with-a-huge-budget minus returned, so it works before
            recall reports held_back), whether a snippet was cut
  speed     --latency-runs N: wall time of `vault_ops.py recall --json` as a subprocess
            (what crew pays), p50/p95/max, the ratio to a bare interpreter start on this
            host, and whether the walk hit its deadline (truncated with a huge budget)

A case with a "gap" string describes behaviour recall does not have yet (superseded
ranking, `--file` keyed recall). Gap cases are reported, never gated; --strict-gaps fails
when one now passes, so the marker is removed in the PR that closes the gap.

Exit 0 when every gate holds, 1 when a threshold is missed, 2 on a usage or setup error.
Nothing here writes outside its temp directory, touches real config, or installs anything.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import recall_eval_fixture as fixture  # noqa: E402  pylint: disable=wrong-import-position

DEFAULT_SCRIPTS = os.path.join(os.path.dirname(HERE), "plugin", "obsidian-vault", "hooks",
                               "scripts")
DEFAULT_GOLDEN = os.path.join(HERE, "_test", "recall-eval", "golden.json")
LATENCY_QUERIES = ("port collision bridge", "hook spawn cost deadline", "bridge vault decision")
HUGE = 10 ** 7
DEADLINE_MS = 1500


def ident(hit):
    return f"{hit['vault']}:{hit['path']}"


def load_golden(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case id in the golden set")
    return cases


def cli_env(config):
    env = dict(os.environ)
    env["OBSIDIAN_VAULT_CONFIG"] = config
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cli_args(scripts_dir, case, max_chars):
    args = [sys.executable, os.path.join(scripts_dir, "vault_ops.py"), "recall", "--query",
            case["query"], "--json", "--max-chars", str(max_chars)]
    if case.get("vaults"):
        args += ["--vaults", ",".join(case["vaults"])]
    if case.get("projects"):
        args += ["--project", ",".join(case["projects"])]
    if case.get("timeout_ms"):
        args += ["--timeout-ms", str(case["timeout_ms"])]
    for flag, value in (case.get("cli") or {}).items():
        args += [f"--{flag}", value]
    return args


def cli_supports(scripts_dir, flag, config):
    """True when `vault_ops.py recall --help` lists --flag."""
    proc = subprocess.run([sys.executable, os.path.join(scripts_dir, "vault_ops.py"), "recall",
                           "--help"], capture_output=True, text=True, check=False,
                          env=cli_env(config), timeout=60)
    return f"--{flag}" in proc.stdout


def recall_via_cli(scripts_dir, config, case, max_chars):
    proc = subprocess.run(cli_args(scripts_dir, case, max_chars), capture_output=True,
                          text=True, check=False, env=cli_env(config), timeout=120)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"recall CLI exit {proc.returncode}: {proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout)


def recall_in_process(vr, case, max_chars):
    return vr.recall(case["query"], case.get("vaults") or None, max_chars,
                     case.get("timeout_ms", DEADLINE_MS), projects=case.get("projects") or [])


def metrics_for(case, res, full, patient=None):
    """Pure scoring of one recall result against its golden case. `full` is the same query
    with a huge budget and the same walk deadline (so held = ranked but over budget);
    `patient` adds a 60 s deadline (so scan_lost = hits the walk deadline cost)."""
    k = case.get("k", 3)
    got = [ident(h) for h in res["results"]]
    top = got[:k]
    expect = case.get("expect", [])
    good = set(expect) | set(case.get("also_ok", []))
    out = {"returned": got, "k": k,
           "recall_k": (len(set(top) & set(expect)) / len(expect)) if expect else None,
           "precision_k": (len([t for t in top if t in good]) / len(top)) if top and expect
           else None,
           "rr": None, "rejected": [g for g in got if g in case.get("reject", [])],
           "truncated": bool(res.get("truncated")),
           "held": max(0, len(full["results"]) - len(res["results"])) if full else None,
           "scan_lost": (len(patient["results"]) - len(full["results"])) if patient else None,
           "snippet_cut": any(h["snippet"].endswith("...") for h in res["results"])}
    out["missing_keys"] = [key for key in case.get("expect_keys", []) if key not in res]
    if expect:
        ranks = [got.index(e) + 1 for e in expect if e in got]
        out["rr"] = 1.0 / min(ranks) if ranks else 0.0
    out["order_bad"] = [f"{a} !< {b}" for a, b in case.get("order", [])
                        if a not in got or (b in got and got.index(a) > got.index(b))]
    out["order_ranks"] = {p: (got.index(p) + 1 if p in got else None)
                          for pair in case.get("order", []) for p in pair}
    out["reasons"] = judge(case, out)
    return out


def judge(case, out):
    """The reasons a case fails; empty when it passes."""
    reasons = []
    if case.get("expect") and out["recall_k"] < 1.0:
        reasons.append(f"recall@{out['k']}={out['recall_k']:.2f}")
    if case.get("expect") and out["precision_k"] is not None and out["precision_k"] < 1.0:
        reasons.append(f"precision@{out['k']}={out['precision_k']:.2f}")
    if out["rejected"]:
        reasons.append("rejected returned: " + ", ".join(out["rejected"]))
    reasons += [f"order {o}" for o in out["order_bad"]]
    if out["missing_keys"]:
        reasons.append("result lacks key(s): " + ", ".join(out["missing_keys"]))
    if case.get("abstain") and out["returned"]:
        reasons.append("expected nothing, got " + ", ".join(out["returned"]))
    for key in ("truncated", "held", "snippet_cut"):
        want = case.get(f"expect_{key}")
        if want is not None and out[key] != want:
            reasons.append(f"{key}={out[key]} want {want}")
    return reasons


def evaluate(cases, scripts_dir, config, vr):
    rows = []
    for case in cases:
        row = {"id": case["id"], "gap": case.get("gap"), "status": None}
        need = list(case.get("cli") or {})
        if need and not all(cli_supports(scripts_dir, f, config) for f in need):
            row.update(status="unsupported", reasons=[f"recall has no --{need[0]}"])
            rows.append(row)
            continue
        max_chars = case.get("max_chars", 4000)
        if need:
            res = recall_via_cli(scripts_dir, config, case, max_chars)
            full, patient = recall_via_cli(scripts_dir, config, case, HUGE), None
        else:
            res = recall_in_process(vr, case, max_chars)
            full = recall_in_process(vr, case, HUGE)
            patient = full
            if full["truncated"]:
                patient = recall_in_process(vr, dict(case, timeout_ms=60000), HUGE)
        row.update(metrics_for(case, res, full, patient))
        if "held_total" in res and res["held_total"] != row["held"]:
            row["reasons"].append(f"held_total={res['held_total']} disagrees with "
                                  f"computed held={row['held']}")
        row["status"] = "pass" if not row["reasons"] else "fail"
        rows.append(row)
    return rows


def aggregate(rows):
    gated = [r for r in rows if not r["gap"]]
    rec = [r["recall_k"] for r in gated if r.get("recall_k") is not None]
    pre = [r["precision_k"] for r in gated if r.get("precision_k") is not None]
    rrs = [r["rr"] for r in gated if r.get("rr") is not None]
    return {
        "cases": len(rows), "gated": len(gated),
        "gated_failed": sum(r["status"] != "pass" for r in gated),
        "recall_at_k": statistics.fmean(rec) if rec else 1.0,
        "precision_at_k": statistics.fmean(pre) if pre else 1.0,
        "mrr": statistics.fmean(rrs) if rrs else 1.0,
        "rejected": sum(len(r.get("rejected", [])) for r in gated),
        "truncated": sum(1 for r in rows if r.get("truncated")),
        "held_total": sum(r.get("held") or 0 for r in rows),
        "scan_lost": sum(r.get("scan_lost") or 0 for r in rows),
        "gaps": sum(1 for r in rows if r["gap"]),
        "gaps_failing": sum(1 for r in rows if r["gap"] and r["status"] != "pass"),
        "gaps_closed": [r["id"] for r in rows if r["gap"] and r["status"] == "pass"],
    }


def percentile(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(pct / 100.0 * (len(ordered) - 1))))]


def timed(args, env):
    start = time.perf_counter()
    proc = subprocess.run(args, capture_output=True, text=True, check=False, env=env, timeout=120)
    return (time.perf_counter() - start) * 1000.0, proc


def latency(scripts_dir, config, runs):
    """Wall time of the recall CLI as crew spawns it, plus a bare-interpreter reference."""
    env = cli_env(config)
    base = [timed([sys.executable, "-c", "pass"], env)[0] for _ in range(runs)]
    deadline_hits, all_ms = 0, []
    for query in LATENCY_QUERIES:
        case = {"query": query, "projects": ["crew"]}
        for _ in range(runs):
            ms, proc = timed(cli_args(scripts_dir, case, HUGE), env)
            all_ms.append(ms)
            if proc.returncode in (0, 1) and json.loads(proc.stdout).get("truncated"):
                deadline_hits += 1
    p50 = statistics.median(all_ms)
    return {"runs_per_query": runs, "samples": len(all_ms), "p50_ms": round(p50, 1),
            "p95_ms": round(percentile(all_ms, 95), 1), "max_ms": round(max(all_ms), 1),
            "interpreter_start_p50_ms": round(statistics.median(base), 1),
            "p50_over_interpreter_start": round(p50 / max(statistics.median(base), 0.001), 2),
            "deadline_hits": deadline_hits, "deadline_ms": DEADLINE_MS}


def deadline_probe(vr, bulk):
    """A 1 ms walk deadline over the bulk fixture: what an incomplete walk returns."""
    case = {"query": "port collision bridge", "projects": ["crew"], "timeout_ms": 1}
    res = recall_in_process(vr, case, 4000)
    return {"timeout_ms": 1, "bulk_notes": bulk, "truncated": res["truncated"],
            "returned": [ident(h) for h in res["results"]]}


def load_recall(scripts_dir):
    sys.path.insert(0, scripts_dir)
    return importlib.import_module("vault_recall")


def format_table(rows):
    lines = [f"{'case':<26}{'status':<18}{'R@k':>5}{'P@k':>6}{'RR':>6}{'trunc':>7}{'held':>6}{'lost':>6}"
             f"  note"]

    def num(value):
        return "-" if value is None else f"{value:.2f}"
    for r in rows:
        status = r["status"] + ("(gap)" if r["gap"] else "")
        note = "; ".join(r.get("reasons") or ([r["gap"]] if r["gap"] else []))
        lines.append(f"{r['id']:<26}{status:<18}{num(r.get('recall_k')):>5}"
                     f"{num(r.get('precision_k')):>6}{num(r.get('rr')):>6}"
                     f"{str(r.get('truncated', '-'))[:5]:>7}{str(r.get('held', '-')):>6}"
                     f"{str(r.get('scan_lost', '-')):>6}  "
                     f"{note[:90]}")
    return "\n".join(lines)


def gate(agg, lat, args):
    """The threshold misses, as readable strings; empty means every gate holds."""
    failures = []
    for label, value, floor in (("recall@k", agg["recall_at_k"], args.min_recall),
                                ("precision@k", agg["precision_at_k"], args.min_precision),
                                ("MRR", agg["mrr"], args.min_mrr)):
        if value < floor:
            failures.append(f"{label} {value:.3f} < {floor}")
    if agg["rejected"] > args.max_rejected:
        failures.append(f"rejected notes returned {agg['rejected']} > {args.max_rejected}")
    if agg["gated_failed"]:
        failures.append(f"{agg['gated_failed']} gated case(s) failed")
    if args.strict_gaps and agg["gaps_closed"]:
        failures.append("gap closed, remove its marker: " + ", ".join(agg["gaps_closed"]))
    if lat and args.max_p95_ms is not None and lat["p95_ms"] > args.max_p95_ms:
        failures.append(f"p95 {lat['p95_ms']:.0f} ms > {args.max_p95_ms}")
    if lat and args.fail_on_deadline and lat["deadline_hits"]:
        failures.append(f"walk deadline hit in {lat['deadline_hits']}/{lat['samples']} runs")
    return failures


def parser():
    ap = argparse.ArgumentParser(description="Recall evaluation harness (see module docstring)")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--scripts-dir", default=DEFAULT_SCRIPTS,
                    help="directory holding vault_ops.py and vault_recall.py to evaluate")
    ap.add_argument("--bulk", type=int, default=0, help="filler notes added to the fixture")
    ap.add_argument("--latency-runs", type=int, default=0)
    ap.add_argument("--min-recall", type=float, default=1.0)
    ap.add_argument("--min-precision", type=float, default=1.0)
    ap.add_argument("--min-mrr", type=float, default=1.0)
    ap.add_argument("--max-rejected", type=int, default=0)
    ap.add_argument("--max-p95-ms", type=float, default=None)
    ap.add_argument("--fail-on-deadline", action="store_true")
    ap.add_argument("--strict-gaps", action="store_true")
    ap.add_argument("--json", action="store_true")
    return ap


def run(args):
    """(rows, latency, deadline probe) for one evaluation in a throwaway directory."""
    scripts = os.path.abspath(args.scripts_dir)
    cases = load_golden(args.golden)
    with tempfile.TemporaryDirectory(prefix="recall-eval-") as root:
        config = fixture.build(root, args.bulk)
        os.environ["OBSIDIAN_VAULT_CONFIG"] = config
        vr = load_recall(scripts)
        rows = evaluate(cases, scripts, config, vr)
        lat = latency(scripts, config, args.latency_runs) if args.latency_runs else None
        probe = deadline_probe(vr, args.bulk) if args.bulk else None
    return rows, lat, probe


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        rows, lat, probe = run(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"recall-eval: setup error: {exc}", file=sys.stderr)
        return 2
    agg = aggregate(rows)
    failures = gate(agg, lat, args)
    if args.json:
        print(json.dumps({"cases": rows, "aggregate": agg, "latency": lat,
                          "deadline_probe": probe, "failures": failures}, indent=2))
        return 1 if failures else 0
    print(format_table(rows))
    print("\n" + "  ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                           for k, v in agg.items() if k != "gaps_closed"))
    for name, block in (("latency", lat), ("deadline_probe", probe)):
        if block:
            print(f"{name}: " + json.dumps(block))
    print("FAIL: " + "; ".join(failures) if failures else "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        sys.exit(main())
