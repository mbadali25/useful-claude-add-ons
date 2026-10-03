"""Environment (E*) and gate (G*) items of crew's QA audit -- L-0618.

`qa_audit.py` imports CHECKS from here and runs them beside its H/R items, so
one report covers both. Same contract: REPORT-ONLY, nothing is written, and
every item answers PASS, GAP, N/A or UNKNOWN. UNKNOWN is never folded into
PASS. The standards each item checks are in references/environments.md; the
defects that earned them are in docs/review/09-qa-standards-crew.md, section 1.

WHAT IT READS. `.crew/verify.json`, `_verify/`, CI files (as text, not YAML),
`.gitignore`, `.crew/secrets.md`, rollback runbooks and served directories.
It never deploys, never reads a secret value and never calls a remote host.
The only process it starts is `git check-ignore` / `git ls-files` (G4); a
failed git call is UNKNOWN, not a pass.
"""
import datetime
import json
import os
import re
import subprocess
import sys

# The Stop gate's own reach classifier, read (never changed) so G1 and the gate
# cannot disagree about which undeclared rules are deferred. CONFIG.md §19.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, os.pardir, os.pardir, "hooks", "scripts"))
try:
    import verify_record  # noqa: E402  pylint: disable=wrong-import-position
except ImportError:  # a copy of this skill without crew's hooks beside it
    verify_record = None

PASS, GAP, NA, UNKNOWN = "PASS", "GAP", "N/A", "UNKNOWN"
REF = "references/environments.md"
ROLLBACK_MAX_DAYS = 90  # promote-gate.sh's ceiling; the audit reports, the gate refuses
PROVENANCE = ("seeded", "restored-from-prod", "shared-with-prod")
PROD_NAMES = ("prod", "production", "prd", "live")
ENV_COMMAND_KEYS = ("deploy", "smoke", "regression", "verify")
GENERATED_DIRS = ("node_modules", "graphify-out", "dist", "build", "coverage", ".venv",
                  "obj", "target", ".next", "playwright-report", "test-results")
SERVED_DIRS = ("public", "public_html", "wwwroot", "htdocs", "www", "web")
SERVED_VERIFIER_RE = re.compile(r"(?:^|[/_-])(?:_?verify|smoke|qa[_-]?check)\w*\.(?:php|sh|py|aspx|ps1)$",
                                re.I)
CREW_IGNORE_LINES = (".crew/*", ".crew/.approved-*", ".work/")

_CURL_FAIL_RE = re.compile(r"(?:^|\s)(?:--fail(?:-with-body)?|-[A-Za-z]*f[A-Za-z]*)(?=\s|$)")
_SWALLOW_RE = re.compile(r"\|\|\s*true\b|;\s*true\s*$|\|\s*Out-Null\b")
# A pipe into one of these reports the filter's exit status, not the command's.
# `| grep -q` is deliberately absent: it fails when the expected text is missing,
# which is how a health check reads the body (standard 12).
_PIPE_RE = re.compile(r"(?<!\|)\|(?!\|)\s*(tee|head|tail|grep\s+-[A-Za-z]*v)\b")
_REV_PARSE_HEAD_RE = re.compile(r"git\s+rev-parse\s+HEAD")
_LAST_VERIFIED_RE = re.compile(r"last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})", re.I)
_VERIFY_REF_RE = re.compile(r"(?:^|[\s/])(_verify/[\w./-]+)")


def posix(rel):
    """A repo-relative path with `/` separators, whatever OS built it: CI paths
    come from os.path.join, so on Windows they carry backslashes, and every
    comparison and every line of evidence must read the same on both."""
    return rel.replace("\\", "/")


def _row(rule, title, status, evidence):
    return {"rule": rule, "title": title, "status": status, "evidence": evidence,
            "fix": f"{REF}, {rule}"}


def read_text(path):
    """The file's text, or None when it does not exist. Any other OSError
    (permission, a directory, I/O) propagates: a file that exists but cannot be
    read is "could not tell", never "absent", so every caller answers UNKNOWN
    for it and qa_doc refuses to overwrite it."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


def load_map(root):
    """(state, map): state is "absent", "unreadable" or "ok". An unreadable map
    is its own state so every item can answer UNKNOWN for it, never N/A."""
    path = os.path.join(root, ".crew", "verify.json")
    if not os.path.isfile(path):
        return "absent", None
    try:
        with open(path, encoding="utf-8") as fh:
            vmap = json.load(fh)
    except (OSError, ValueError):
        return "unreadable", None
    return ("ok", vmap) if isinstance(vmap, dict) else ("unreadable", None)


def environments(vmap):
    envs = vmap.get("environments") if vmap else None
    return {k: v for k, v in envs.items() if isinstance(v, dict)} if isinstance(envs, dict) else {}


def is_production(name, env):
    return name.lower() in PROD_NAMES or env.get("requireHuman") is True


def as_list(value):
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def map_commands(vmap):
    """(where, command) for every command the map can run: rule `run`,
    `default`, `always`, and each environment's command lists."""
    out = []
    for i, rule in enumerate(vmap.get("rules") or []):
        if isinstance(rule, dict):
            out += [(f"rules[{i}].run", c) for c in as_list(rule.get("run"))]
    for key in ("default", "always"):
        out += [(key, c) for c in as_list(vmap.get(key))]
    for name, env in environments(vmap).items():
        for key in ENV_COMMAND_KEYS:
            out += [(f"environments.{name}.{key}", c) for c in as_list(env.get(key))]
    return out


def _map_or_row(root, rule, title):
    state, vmap = load_map(root)
    if state == "absent":
        return None, _row(rule, title, NA, "no .crew/verify.json")
    if state == "unreadable":
        return None, _row(rule, title, UNKNOWN, ".crew/verify.json exists but could not be parsed")
    return vmap, None


# --- G: gate rules that can fail ----------------------------------------------------------

def deferred_on_stop(root, rules):
    """{index: reason} for each rule without `reach` that the Stop gate defers,
    by verify_record.scan_reach -- the gate's own classifier. None when that
    module is not importable: an unknown, never an empty dict."""
    if verify_record is None:
        return None
    out = {}
    for i, rule in enumerate(rules):
        if "reach" in rule:
            continue
        status, detail = verify_record.scan_reach(as_list(rule.get("run")), root)
        if status != "local":
            out[i] = f"{status}{': ' + detail if detail else ''}"
    return out


def check_rule_reach(root, ci, tests):
    """G1 (standard 19, defect D10): an undeclared rule whose command has shell
    syntax, a remote verb or a wrapper script is deferred on every Stop, so the
    gate records it as skipped while its marker advances (CONFIG.md §19). An
    undeclared plain local command still runs; it is a GAP only because the
    standard wants every rule declared."""
    title = "Every gate rule declares reach and seconds"
    vmap, row = _map_or_row(root, "G1", title)
    if row:
        return row
    rules = [r for r in vmap.get("rules") or [] if isinstance(r, dict)]
    if not rules:
        return _row("G1", title, NA, "verify.json declares no rules")
    no_reach = [i for i, r in enumerate(rules) if "reach" not in r]
    no_seconds = [str(i) for i, r in enumerate(rules)
                  if not isinstance(r.get("seconds"), (int, float)) or isinstance(r.get("seconds"), bool)]
    if not no_reach and not no_seconds:
        return _row("G1", title, PASS, f"all {len(rules)} rule(s) declare reach and seconds")
    deferred = deferred_on_stop(root, rules) if no_reach else {}
    if deferred is None:
        return _row("G1", title, UNKNOWN, f"{len(no_reach)} rule(s) have no `reach`, and the gate's "
                    "classifier (hooks/scripts/verify_record.py) could not be imported to tell which "
                    "the Stop gate skips")
    parts = []
    if deferred:
        parts.append(f"{len(deferred)} rule(s) SKIPPED on every Stop: " + "; ".join(
            f"rules[{i}] {why}" for i, why in list(deferred.items())[:6]))
    runs = [str(i) for i in no_reach if i not in deferred]
    if runs:
        parts.append(f"{len(runs)} rule(s) run but declare no `reach` (rules {', '.join(runs[:8])})")
    if no_reach:
        parts.append("declare each by hand (CONFIG.md §19) until L-0562's --stamp-reach lands")
    if no_seconds:
        parts.append(f"{len(no_seconds)} rule(s) have no numeric `seconds` (rules "
                     f"{', '.join(no_seconds[:8])})")
    return _row("G1", title, GAP, "; ".join(parts))


def _fire_and_forget(command):
    """Why a command cannot fail on the thing it claims to check, or None."""
    if "pipefail" not in command:
        pipe = _PIPE_RE.search(command)
        if pipe:
            return f"exit status is `{pipe.group(1)}`'s, not the command's (no pipefail)"
    if _SWALLOW_RE.search(command):
        return "its exit status is swallowed (`|| true`, `| Out-Null` or output discarded)"
    if re.search(r"\bcurl\b", command) and not _CURL_FAIL_RE.search(command):
        return "curl without -f exits 0 on an HTTP error"
    if re.search(r"\bgh\s+workflow\s+run\b", command) and not re.search(r"\bgh\s+run\s+watch\b", command):
        return "dispatches a workflow without `gh run watch --exit-status`: proves the dispatch, not the run"
    if re.search(r"\bsend-command\b", command) and not re.search(r"\bwait\b|get-command-invocation", command):
        return "a remote command dispatch with no wait-and-read: queues and exits 0"
    return None


def check_fire_and_forget(root, ci, tests):
    """G2 (standard 22, defect D2): a check that cannot fail is not a check."""
    title = "No fire-and-forget commands in the verify map"
    vmap, row = _map_or_row(root, "G2", title)
    if row:
        return row
    commands = map_commands(vmap)
    if not commands:
        return _row("G2", title, NA, "verify.json declares no commands")
    bad = [f"{where}: `{cmd[:60]}` -- {why}" for where, cmd in commands
           for why in [_fire_and_forget(cmd)] if why]
    if bad:
        return _row("G2", title, GAP, f"{len(bad)} command(s) cannot fail: " + "; ".join(bad[:5]))
    return _row("G2", title, PASS, f"{len(commands)} command(s); none fire-and-forget")


def _verify_scripts(root):
    base = os.path.join(root, "_verify")
    if not os.path.isdir(base):
        return []
    out = []
    for dirpath, _, names in os.walk(base):
        out += [os.path.join(dirpath, n) for n in sorted(names) if n.endswith(".sh")]
    return out


def _script_defects(text):
    found = []
    lines = text.split("\n")
    live = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if any(re.search(r"\bENV=\"?\$\{ENV:-", ln) for ln in live):
        found.append("reads an inherited ENV with a default (an ENV=prd left in a shell targets production)")
    if any(re.match(r"\s*\*\)\s*shift\s*;;", ln) for ln in live):
        found.append("`*) shift ;;` silently drops unknown flags")
    if any("${READONLY:+" in ln for ln in live):
        found.append("`${READONLY:+...}` expands on the string \"0\", so every run reads read-only")
    if any(re.search(r"if\s+\"\$@\"\s*>\s*/dev/null\s+2>&1", ln) for ln in live):
        found.append("check() discards the failing command's output, so a FAIL carries no reason")
    if any(re.match(r"\s*check\s*\(\)", ln) for ln in live) \
            and not any(re.match(r"\s*check\s+[\"'\w]", ln) for ln in live):
        found.append("defines check() but runs none: zero checks exits 0 (\"0/0 passed\")")
    return found


def check_verify_scripts(root, ci, tests):
    """G3 (standards 2 and 21, defect D1): the template's known bugs, in the repo's copy."""
    title = "_verify scripts: explicit env, strict flags, zero checks fails"
    scripts = _verify_scripts(root)
    if not scripts:
        return _row("G3", title, NA, "no _verify/*.sh")
    bad = []
    for path in scripts:
        try:
            text = read_text(path)
        except OSError as exc:
            text, why = None, exc.strerror or type(exc).__name__
        else:
            why = "it vanished while being read"
        if text is None:
            return _row("G3", title, UNKNOWN, f"could not read {os.path.relpath(path, root)} ({why})")
        bad += [f"{os.path.relpath(path, root)}: {d}" for d in _script_defects(text)]
    if bad:
        return _row("G3", title, GAP, "; ".join(bad[:6]))
    return _row("G3", title, PASS, f"{len(scripts)} script(s); none carry the template's known defects")


def _git(root, *args):
    try:
        proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc


def check_generated_ignored(root, ci, tests):
    """G4 (standard 30, defect D6): an unignored generated directory shows up as
    changed files, overflows argv and trips `unmapped: fail`."""
    title = "Generated directories are ignored (or tracked on purpose)"
    present = [d for d in GENERATED_DIRS if os.path.isdir(os.path.join(root, d))]
    if not present:
        return _row("G4", title, NA, "no generated directory present")
    probe = _git(root, "rev-parse", "--is-inside-work-tree")
    if probe is None or probe.returncode != 0:
        return _row("G4", title, UNKNOWN, "not a git work tree, or git could not run")
    loose, tracked = [], []
    for name in present:
        ignored = _git(root, "check-ignore", "-q", name)
        listed = _git(root, "ls-files", "--", name)
        if ignored is None or listed is None or ignored.returncode not in (0, 1) \
                or listed.returncode != 0:  # a failed ls-files is silent stdout, not "untracked"
            return _row("G4", title, UNKNOWN, f"git could not answer for {name}/")
        if listed.stdout.strip():
            tracked.append(name)
        elif ignored.returncode != 0:
            loose.append(name)
    note = f"; tracked (a decision to confirm, not a gap): {', '.join(tracked)}" if tracked else ""
    if loose:
        return _row("G4", title, GAP, "neither ignored nor tracked: " + ", ".join(f"{d}/" for d in loose)
                    + note)
    return _row("G4", title, PASS, f"{len(present)} generated dir(s) handled" + note)


def check_crew_ignore_block(root, ci, tests):
    """G5 (defect D9): without the block the approval marker is trackable, and
    creating it dirties the tree the promote gate then refuses."""
    title = ".gitignore carries crew's .crew/* block"
    if not os.path.isdir(os.path.join(root, ".crew")):
        return _row("G5", title, NA, "no .crew/ directory")
    try:
        text = read_text(os.path.join(root, ".gitignore"))
    except OSError as exc:
        return _row("G5", title, UNKNOWN, f"could not read .gitignore ({exc.strerror or type(exc).__name__})")
    if text is None:
        return _row("G5", title, GAP, "no .gitignore; the promotion approval marker would be tracked")
    lines = {ln.strip() for ln in text.split("\n")}
    problems = [f"missing `{want}`" for want in CREW_IGNORE_LINES if want not in lines]
    if ".crew/" in lines or ".crew" in lines:
        problems.append("`.crew/` ignores the directory itself, so no `!.crew/...` negation can apply")
    if problems:
        return _row("G5", title, GAP, "; ".join(problems))
    return _row("G5", title, PASS, "`.crew/*`, `.crew/.approved-*` and `.work/` all present")


# --- E: environments ----------------------------------------------------------------------

def _envs_or_row(root, rule, title):
    vmap, row = _map_or_row(root, rule, title)
    if row:
        return None, row
    envs = environments(vmap)
    if not envs:
        return None, _row(rule, title, NA, "no environments block")
    return envs, None


def check_env_provenance(root, ci, tests):
    """E1 (standard 1, defect D4): where does a non-production environment's data come from."""
    title = "Non-production environments declare data provenance"
    envs, row = _envs_or_row(root, "E1", title)
    if row:
        return row
    bad = []
    nonprod = {k: v for k, v in envs.items() if not is_production(k, v)}
    if not nonprod:
        return _row("E1", title, NA, "only production environments declared")
    for name, env in nonprod.items():
        prov = env.get("dataProvenance")
        if prov not in PROVENANCE:
            bad.append(f"{name}: no `dataProvenance` (one of {', '.join(PROVENANCE)})")
        elif prov == "restored-from-prod" and not as_list(env.get("scrub")):
            bad.append(f"{name}: restored from production with no `scrub` command named")
        elif prov == "shared-with-prod" and not env.get("acceptedBy"):
            bad.append(f"{name}: shares production data with no `acceptedBy` owner line")
    if bad:
        return _row("E1", title, GAP, "; ".join(bad))
    return _row("E1", title, PASS, f"{len(nonprod)} non-production environment(s) declare provenance")


def check_env_rollback(root, ci, tests):
    """E2 (standard 18, defect D3): every rung's rollback is rehearsed, not only production's."""
    title = "Every environment has a rehearsed rollback"
    envs, row = _envs_or_row(root, "E2", title)
    if row:
        return row
    bad, unread, today = [], [], datetime.date.today()
    for name, env in envs.items():
        rb = env.get("rollback")
        if rb is None:
            bad.append(f"{name}: no `rollback` key (the promote gate refuses its deploy)")
        elif rb == "none":
            if not str(env.get("rollbackReason") or "").strip():
                bad.append(f"{name}: rollback \"none\" with no rollbackReason")
        elif not isinstance(rb, str):
            bad.append(f"{name}: `rollback` is not a path")
        else:
            try:
                text = read_text(os.path.join(root, rb))
            except OSError as exc:
                unread.append(f"{name}: could not read runbook {rb} ({exc.strerror or type(exc).__name__})")
                continue
            match = _LAST_VERIFIED_RE.search(text or "")
            if text is None:
                bad.append(f"{name}: runbook {rb} does not exist")
            elif not match:  # `last verified: never` included
                bad.append(f"{name}: {rb} has never been rehearsed (no `last verified: YYYY-MM-DD`)")
            else:
                try:
                    age = (today - datetime.date.fromisoformat(match.group(1))).days
                except ValueError:
                    bad.append(f"{name}: {rb} `last verified: {match.group(1)}` is not a real date")
                    continue
                if age > ROLLBACK_MAX_DAYS:
                    bad.append(f"{name}: {rb} last rehearsed {age} days ago (ceiling {ROLLBACK_MAX_DAYS})")
    if bad:
        return _row("E2", title, GAP, "; ".join(bad + unread))
    if unread:
        return _row("E2", title, UNKNOWN, "; ".join(unread))
    return _row("E2", title, PASS, f"{len(envs)} environment(s) carry a rehearsed rollback or a reason")


def check_deploy_ref(root, ci, tests):
    """E3 (standard 16, defect D2): a deploy of whatever happens to be checked out
    is not a promotion of the SHA that was proven."""
    title = "Deploys name the promoted SHA, not the checkout's HEAD"
    hits = []
    state, vmap = load_map(root)
    if state == "ok":
        hits += [where for where, cmd in map_commands(vmap)
                 if where.startswith("environments.") and where.endswith(".deploy")
                 and _REV_PARSE_HEAD_RE.search(cmd)]
    for rel, text in ((posix(r), t) for r, t in ci):
        if "deploy" not in (rel + text).lower():
            continue
        hits += [f"{rel}:{n}" for n, ln in enumerate(text.split("\n"), 1)
                 if not ln.strip().startswith("#") and _REV_PARSE_HEAD_RE.search(ln)]
    if state == "unreadable":
        return _row("E3", title, UNKNOWN, ".crew/verify.json could not be parsed"
                    + (f"; CI already shows: {', '.join(hits)}" if hits else ""))
    if not environments(vmap) and not any("deploy" in (r + t).lower() for r, t in ci):
        return _row("E3", title, NA, "no environments block and no deploy workflow")
    if hits:
        return _row("E3", title, GAP, "deploy ref from `git rev-parse HEAD` at " + ", ".join(hits[:6]))
    return _row("E3", title, PASS, "no deploy derives its ref from the checkout")


def check_deploy_workflows(root, ci, tests):
    """E4 (standard 17, defect D2): deploy workflows fail loudly."""
    title = "Deploy workflows fail loudly"
    deploys = [(posix(rel), text) for rel, text in ci if "deploy" in (rel + text).lower()]
    if not deploys:
        return _row("E4", title, NA if ci else UNKNOWN,
                    "no deploy workflow" if ci else "no CI configuration was found")
    bad = []
    for rel, text in deploys:
        for n, ln in enumerate(text.split("\n"), 1):
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if re.search(r"\|\|\s*true\b|\|\s*Out-Null\b", s):
                bad.append(f"{rel}:{n} swallows an exit code")
            elif re.search(r"continue-on-error:\s*true", s):
                bad.append(f"{rel}:{n} continue-on-error")
            elif re.search(r"\brobocopy\b", s, re.I) and "LASTEXITCODE" not in text:
                bad.append(f"{rel}:{n} robocopy with no exit-code mapping (1-7 are success, 8+ fail)")
        if rel.startswith(".github/") and not re.search(r"^\s*concurrency\s*:", text, re.M):
            bad.append(f"{rel}: no `concurrency:` group, so two deploys can race")
    if bad:
        return _row("E4", title, GAP, "; ".join(bad[:6]))
    return _row("E4", title, PASS, f"{len(deploys)} deploy workflow(s); no swallowed exits")


def _table(text):
    """(header cells, rows) of the first markdown table in text."""
    rows = [ln for ln in text.split("\n") if ln.strip().startswith("|")]
    if len(rows) < 2:
        return [], []
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    return [c.lower() for c in cells[0]], [r for r in cells[2:] if any(r)]


def _cell(row, index):
    return row[index].lower() if index is not None and index < len(row) else ""


# E5's vocabulary. Only these words decide `live`; anything else is unknown.
LIVE_YES = ("yes", "y", "true", "live")
LIVE_NO = ("no", "n", "false")
# Environment words a reaches cell may use besides the declared `environments` keys.
NONPROD_NAMES = ("dev", "development", "local", "ci", "test", "testing", "qa", "uat", "stage",
                 "staging", "preprod", "pre-prod", "sandbox", "demo", "preview")
# Words a reaches part may hold besides environment names: they join names, never qualify one.
REACH_FILLER = ("only", "and")
# A token (case-insensitive) that IS one of these refuses an acceptance cell...
NOT_ACCEPTED = ("no", "n", "na", "n/a", "not", "false")
# ...and so does a token that STARTS WITH one of these stems, anywhere in the cell,
# a `by` name included ("accepted by Nobody", "accepted Cancelled").
NOT_ACCEPTED_STEMS = ("revok", "reject", "deni", "deny", "refus", "expir", "withdr", "cancel",
                      "rescind", "retract", "laps", "void", "invalid", "never", "nobody", "none",
                      "pending", "tbd", "todo", "unknown", "await", "wait", "declin", "maybe",
                      "perhaps", "condition", "tentativ", "provision", "draft", "unverif", "propos",
                      "supersed", "disput", "inactiv", "disabl", "obsolet", "stale", "unaccept")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# The acceptance grammar, over the whole cell in its ORIGINAL case: `accepted` or
# `yes`, an optional `,` or `.`, then optionally `by NAME` and optionally an ISO
# date, in either order; or an ISO date alone. A NAME counts only directly after
# `by` and is 1-3 words that each start with an uppercase ASCII letter, so a
# free-standing word of any case ("accepted Maybe", "yes Draft") never matches.
_NAME = r"[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,2}"
_BY_NAME = rf"(?i:by)\s+{_NAME}"
_ISO = r"\d{4}-\d{2}-\d{2}"
_ACCEPT_RE = re.compile(
    rf"(?i:accepted|yes)[.,]?(?:\s+{_BY_NAME}(?:\s+{_ISO})?|\s+{_ISO}(?:\s+{_BY_NAME})?)?")


# Inside a `by` name a stem would refuse real people (Denise, Waite, Staley), so
# there a token refuses only as one of these whole word forms; the short words
# (no, n, na, n/a, false) never apply inside a name (Matthew N Badali, Na-Young).
NAME_REFUSAL_FORMS = frozenset((
    "revoked", "revoke", "rejected", "reject", "denied", "deny", "refused", "refuse", "expired",
    "expire", "withdrawn", "withdraw", "cancelled", "canceled", "cancel", "rescinded", "retracted",
    "lapsed", "void", "invalid", "pending", "tbd", "todo", "unknown", "awaiting", "waiting",
    "declined", "maybe", "perhaps", "conditional", "conditionally", "tentative", "tentatively",
    "provisional", "draft", "unverified", "proposed", "superseded", "disputed", "inactive",
    "disabled", "obsolete", "stale", "unaccepted", "never", "nobody", "none", "not",
    "no", "no-one", "noone",
    "retract", "rescind", "lapse", "lapses", "decline", "declines", "dispute", "disputes",
    "invalidate", "invalidated", "revoking", "revokes", "rejects", "rejecting", "denies", "denying",
    "expiring", "expires", "withdrew", "withdrawing", "cancelling", "cancels", "refusing",
    "refuses", "voided", "terminated", "nullified", "revocation", "rejection", "denial", "expiry"))
_BY_NAME_SPAN_RE = re.compile(rf"(?i:\bby)\s+({_NAME})")


def _refuses(token):
    return token in NOT_ACCEPTED or token.startswith(NOT_ACCEPTED_STEMS)


def _name_forms(word):
    """The forms of one name word that are checked against NAME_REFUSAL_FORMS:
    each `-` part, then the word whole and joined ("No-one": no, one, no-one, noone)."""
    word = word.lower()
    return [*word.split("-"), word, word.replace("-", "")]


def _refusal(text):
    """The word that refuses an acceptance cell, or None. A whole refusal word is
    reported before a stem match, so two `by` clauses name the word that refused
    ("accepted by Bob by Denise Revoked" -> revoked, not denise). Outside the
    first `by` name a token refuses as a NOT_ACCEPTED or NAME_REFUSAL_FORMS word,
    or by a NOT_ACCEPTED_STEMS prefix; inside it, only as a NAME_REFUSAL_FORMS
    word (`n`, `na` and `false` stay names there: Matthew N Badali, Na-Young)."""
    span = _BY_NAME_SPAN_RE.search(text)
    name = span.group(1) if span else ""
    outside = text[:span.start(1)] + " " + text[span.end(1):] if span else text
    tokens = re.findall(r"[a-z]+(?:/[a-z]+)?", outside.lower())
    whole = [t for t in tokens if t in NOT_ACCEPTED or t in NAME_REFUSAL_FORMS]
    whole += [f for w in name.split() for f in _name_forms(w) if f in NAME_REFUSAL_FORMS]
    if whole:
        return whole[0]
    return next((t for t in tokens if _refuses(t)), None)


def _header_col(header, words):
    """Index of the first header cell holding one of `words` as a whole word."""
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b")
    return next((i for i, h in enumerate(header) if pattern.search(h.strip("`*_ "))), None)


def _plain(cell):
    return re.sub(r"[`*_]", "", cell).strip()


def parse_live(cell):
    """"yes", "no" or "unknown". A yes may carry a note in parentheses ("yes
    (rotated)"); a no must stand alone, because "no (live soon)" is not a no.
    Every other value -- `?`, TBD, blank -- is unknown."""
    plain = _plain(cell)
    if plain.rstrip(".") in LIVE_NO:
        return "no"
    if plain.split("(")[0].strip().rstrip(".") in LIVE_YES:
        return "yes"
    return "unknown"


def parse_reach(cell, envs):
    """(environment names, unparsed parts). The cell splits on `,`, `;` and `/`.
    A part parses only when every word in it is a known environment name or a
    REACH_FILLER word: "production only" and "prod + dev" parse, while "not
    prod", "all but prod", "prod replica" and "non-production" are unparsed,
    because a qualifier dropped would turn them into production. An empty cell
    is unparsed too."""
    known = set(PROD_NAMES) | set(NONPROD_NAMES) | {k.lower() for k in envs}
    found, unparsed = [], []
    for part in (p.strip() for p in re.split(r"[,;/]", _plain(cell))):
        if not part:
            continue
        words = re.findall(r"[a-z0-9][a-z0-9_-]*", part)
        names = [w for w in words if w in known]
        if names and all(w in known or w in REACH_FILLER for w in words):
            found += [n for n in names if n not in found]
        else:
            unparsed.append(part)
    if not found and not unparsed:
        unparsed.append("(empty)")
    return found, unparsed


def _iso_date(token):
    if not _DATE_RE.fullmatch(token):
        return False
    try:
        datetime.date.fromisoformat(token)
    except ValueError:
        return False
    return True


def parse_acceptance(cell):
    """"yes", "no" or "unknown"; see acceptance()."""
    return acceptance(cell)[0]


def acceptance(cell):
    """(state, refusing word or None). The state is "yes", "no" or "unknown",
    judged on the cell's original case (see _ACCEPT_RE).

    no:      blank or ASCII punctuation only (`-`, `?`), or a refusal word
             (_refusal: "rejected 2026-10-01", "accepted Cancelled",
             "accepted by Nobody"; not "accepted by Denise").
    yes:     the whole cell is an ISO date, or matches _ACCEPT_RE
             ("accepted", "Accepted by Matthew", "accepted by Matthew Badali 2026-10-01").
    unknown: everything else -- "accepted Matthew" (no `by`), "accepted Under
             Review", "accepted (verbally)", "approved", "ok", "y", an emoji, a
             non-ASCII name. Never read as an acceptance."""
    text = re.sub(r"[`*]", "", cell).strip()
    if re.fullmatch(r"[\s!-/:-@\[-`{-~]*", text):
        return "no", None
    word = _refusal(text)
    if word:
        return "no", word
    if not (_DATE_RE.fullmatch(text) or _ACCEPT_RE.fullmatch(text)):
        return "unknown", None
    return ("yes" if all(_iso_date(d) for d in _DATE_RE.findall(text)) else "unknown"), None


def check_secrets_inventory(root, ci, tests):
    """E5 (standard 6, defect D4): which environment does each credential reach, and is it live.
    A row whose `live` or reach cannot be read is UNKNOWN, never a pass (09 §6)."""
    title = "Credential inventory: reach and live columns"
    path = os.path.join(root, ".crew", "secrets.md")
    state, vmap = load_map(root)
    if state == "unreadable":  # its environment names decide reach; same answer as E2
        return _row("E5", title, UNKNOWN, "could not read the environments map (.crew/verify.json)")
    envs = environments(vmap)
    try:
        text = read_text(path)
    except OSError as exc:
        return _row("E5", title, UNKNOWN, f"could not read .crew/secrets.md ({exc.strerror or type(exc).__name__})")
    if text is None:
        if envs:
            return _row("E5", title, GAP, "environments are declared but .crew/secrets.md does not exist")
        return _row("E5", title, NA, "no environments block and no .crew/secrets.md")
    header, rows = _table(text)
    reach_col = _header_col(header, ("reach", "reaches", "environment", "environments", "env", "envs"))
    live_col = _header_col(header, ("live",))
    if reach_col is None or live_col is None:
        missing = [n for n, c in (("reaches", reach_col), ("live", live_col)) if c is None]
        return _row("E5", title, GAP, f".crew/secrets.md has no {' or '.join(missing)} column")
    accept_col = _header_col(header, ("accept", "accepted", "acceptance"))
    bad, unknown, by_name = [], [], {k.lower(): v for k, v in envs.items()}
    for r in rows:
        name = r[0] if r else "?"
        live = parse_live(_cell(r, live_col))
        if live == "no":
            continue
        reached, unparsed = parse_reach(_cell(r, reach_col), envs)
        nonprod = [e for e in reached if not is_production(e, by_name.get(e, {}))]
        if live == "unknown":
            if nonprod or unparsed:  # production-only cannot be a GAP whatever `live` says
                unknown.append(f"`{name}`: live is `{_cell(r, live_col) or '(blank)'}`, not yes or no")
            continue
        if unparsed:
            unknown.append(f"`{name}` is live and its reach `{', '.join(unparsed)}` names no known environment")
        raw = r[accept_col].strip() if accept_col is not None and accept_col < len(r) else ""
        accepted, refused_by = acceptance(raw) if nonprod else ("yes", None)
        if accepted == "no" and refused_by:
            bad.append(f"`{name}` is live and reaches {', '.join(nonprod)}: `{name}` acceptance "
                       f"refused by the word `{refused_by}`")
        elif accepted == "no":
            bad.append(f"`{name}` is live and reaches {', '.join(nonprod)} with no owner acceptance")
        elif accepted == "unknown":
            unknown.append(f"`{name}` is live and reaches {', '.join(nonprod)}; its acceptance "
                           f"`{raw}` is not a recognised form")
    if bad:
        return _row("E5", title, GAP, "; ".join(bad[:5])
                    + (f"; also could not tell: {'; '.join(unknown[:5])}" if unknown else ""))
    if unknown:
        return _row("E5", title, UNKNOWN, "; ".join(unknown[:5]))
    return _row("E5", title, PASS, f"{len(rows)} credential(s) inventoried; no unaccepted live one "
                "reaches a non-production environment")


def check_verifiers_not_served(root, ci, tests):
    """E6 (standard 5, defect D9): a verifier in a served directory is a public endpoint."""
    title = "No verifier scripts inside a served directory"
    served = [d for d in SERVED_DIRS if os.path.isdir(os.path.join(root, d))]
    if not served:
        return _row("E6", title, NA, "no served directory (" + ", ".join(SERVED_DIRS) + ")")
    hits = []
    for d in served:
        for dirpath, dirs, names in os.walk(os.path.join(root, d)):
            dirs[:] = [x for x in dirs if x not in ("node_modules", ".git")]
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            hits += [f"{rel}/{n}" for n in names
                     if SERVED_VERIFIER_RE.search(n) or "/_verify" in f"/{rel}"]
    if hits:
        return _row("E6", title, GAP, "served: " + ", ".join(hits[:6]))
    return _row("E6", title, PASS, f"nothing verifier-shaped under {', '.join(served)}")


def check_ci_parity(root, ci, tests):
    """E7 (standard 25, defect D5): the local gate and CI run the same entry points."""
    title = "CI runs the _verify entry points the gate runs"
    vmap, row = _map_or_row(root, "E7", title)
    if row:
        return row
    local_only = set()
    for rule in vmap.get("rules") or []:
        if isinstance(rule, dict) and rule.get("localOnly"):
            local_only.update(m.group(1) for c in as_list(rule.get("run"))
                              for m in _VERIFY_REF_RE.finditer(c))
    scripts = sorted({m.group(1) for _, c in map_commands(vmap) for m in _VERIFY_REF_RE.finditer(c)}
                     - local_only)
    if not scripts:
        return _row("E7", title, NA, "the map names no _verify/ entry point")
    if not ci:
        return _row("E7", title, UNKNOWN, "the map runs _verify/ scripts but no CI configuration was found")
    ci_text = "\n".join(t for _, t in ci)
    missing = [s for s in scripts if s not in ci_text]
    if missing:
        return _row("E7", title, GAP, "run locally, never in CI (mark the rule `localOnly` if that is "
                    "deliberate): " + ", ".join(missing[:6]))
    return _row("E7", title, PASS, f"{len(scripts)} _verify entry point(s) also run in CI")


CHECKS = (check_rule_reach, check_fire_and_forget, check_verify_scripts, check_generated_ignored,
          check_crew_ignore_block, check_env_provenance, check_env_rollback, check_deploy_ref,
          check_deploy_workflows, check_secrets_inventory, check_verifiers_not_served, check_ci_parity)
