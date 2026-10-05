"""autopilot's deploy phase (L-0649): after the ship phase reports the
ticket's PR merged, name `/crew:promote <env>` for the first GitHub Actions
environment autopilot may drive, or stop.

Read-only: it runs no `gh`, calls no `crew_ghdeploy.py` subcommand and writes
nothing. `crew_autopilot._ship_phase` hands it the `closed` answer
`crew_ship.merged_phase` gave for a PR that merged this checkout's HEAD (any
other answer passes through), and it answers:

  - `closed`, unchanged, under `autopilot.deploy: none` (the default);
  - `closed`, saying promotion is a person's, when no environment in
    `.crew/verify.json` has a `github` entry;
  - `failed-deploy` (stop) when the target's NEWEST `.work/PROMOTIONS.md` row
    for the sha is not all-pass: autopilot never re-deploys after it;
  - `deploy-target` (stop) when the target cannot be told or is not safe to
    drive: the map unreadable, an entry `crew_ghdeploy.py check` refuses,
    `requireHuman`, no `shaInput`, T-0009's class unknown, mismatched or
    crashing, or `deploy_allowed` answering anything but exactly `allow`
    (its reason and every non-empty `report` are printed);
  - `deploy` (no stop), `/crew:promote <env>`, for the first target with no
    row for the sha. Targets are the `github` environments in file order,
    nonProd before prod, so production is named only once every nonProd
    target has an all-pass row;
  - `closed`, naming each environment and the sha, when every target has an
    all-pass row.
"""
import os

import crew_ghdeploy
import crew_ship

PROMOTIONS = os.path.join(".work", "PROMOTIONS.md")


def _row(top, env, sha):
    """'pass', 'fail' or None: the newest row for `env` and `sha`, read as
    promote-gate reads it (L-0665)."""
    try:
        with open(os.path.join(top, PROMOTIONS), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except FileNotFoundError:
        return None
    newest = None
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[1] == env and cells[2].startswith(sha[:7]):
            newest = "pass" if all(c.lower() == "pass" for c in cells[3:6]) else "fail"
    return newest


def _targets(top, sha):
    """`[(env, class)]` for every `github` environment, nonProd first, or
    raises ValueError naming why a target cannot be told."""
    path = os.path.join(top, ".crew", "verify.json")
    if not os.path.lexists(path):
        return []
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            envs = crew_ghdeploy.load_map(fh.read())
    except (OSError, crew_ghdeploy._MapRefused) as exc:  # pylint: disable=protected-access
        raise ValueError(f"verify-json-unreadable: {path}: {exc}") from exc
    found = []
    for env, cfg in envs.items():
        if crew_ghdeploy._get_ci(cfg, "github", None) is None:  # pylint: disable=protected-access
            continue
        try:
            entry = crew_ghdeploy.validated(envs, env)[0]
        except crew_ghdeploy.Refused as exc:
            raise ValueError(f"{env}: `crew_ghdeploy.py check` refuses it ({exc.reason}): {exc}") \
                from exc
        if crew_ghdeploy._get_ci(cfg, "requireHuman", False) is True:  # pylint: disable=protected-access
            raise ValueError(f"require-human-target: {env} has requireHuman: true, which "
                             "autopilot never drives")
        if not entry.get("shaInput"):
            raise ValueError(f"no-sha-input: {env}'s github entry has no shaInput, so the "
                             "workflow would deploy its branch tip, not the merged sha")
        try:
            klass = crew_ghdeploy.classify(top, env, crew_ghdeploy.dispatch(entry, env, sha))
        except crew_ghdeploy.Refused as exc:
            raise ValueError(f"class {exc.reason}: {env}: {exc}") from exc
        found.append((env, klass))
    return sorted(found, key=lambda pair: pair[1] != "nonProd")


def after_merge(top, branch, pr, answer, deploy, allowed):
    """`next`'s answer for a MERGED PR: `crew_ship.merged_phase`'s, then the
    deploy phase. `deploy` is the `autopilot.deploy` setting, `allowed`
    `deploy_allowed`; the sha is the PR's merged head, which `merged_phase`
    has checked is this checkout's HEAD."""
    closed = crew_ship.merged_phase(top, branch, pr, answer)
    if closed.get("phase") != "closed" or deploy == "none":
        return closed
    return deploy_phase(top, closed, answer, allowed, pr.get("headRefOid") or "")


def deploy_phase(top, closed, answer, allowed, sha):
    """The deploy phase proper, after `closed`: see the module docstring."""
    try:
        targets = _targets(top, sha)
    except ValueError as exc:
        return answer("deploy-target", True, f"{exc} - a person promotes")
    except Exception as exc:  # pylint: disable=broad-except
        return answer("deploy-target", True, f"the deploy target could not be told "
                      f"({type(exc).__name__}: {exc}) - a person promotes")
    if not targets:
        return answer("closed", True, f"{closed['reason']}; no environment in "
                      ".crew/verify.json has a github entry, so promotion is a person's")
    done = []
    for env, klass in targets:
        row = _row(top, env, sha)
        if row == "pass":
            done.append(env)
            continue
        if row == "fail":
            return answer("failed-deploy", True, f"{env}'s newest .work/PROMOTIONS.md row for "
                          f"{sha[:7]} is not all-pass: autopilot never re-deploys; a person "
                          "rolls back or fixes forward")
        verdict = allowed(top, env, klass)
        report = f" [{verdict['report']}]" if verdict.get("report") else ""
        if verdict.get("verdict") != "allow":
            return answer("deploy-target", True, f"deploy-allowed answers "
                          f"{verdict.get('verdict')} for {env} ({klass}): "
                          f"{verdict.get('reason')}{report}")
        return answer("deploy", False, f"PR merged at {sha[:7]}; {env} ({klass}) is the "
                      f"next GitHub environment: {verdict.get('reason')}{report}",
                      f"/crew:promote {env}")
    return answer("closed", True, f"{closed['reason']}; {', '.join(done)} "
                  f"{'has' if len(done) == 1 else 'have'} an all-pass row for {sha[:7]}")
