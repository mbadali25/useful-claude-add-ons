"""Setup half of vault_ops.py: detect/install Obsidian, create a vault, assign roles.

    detect-obsidian  [--os OS] [--json]                   is Obsidian installed, and how we know
    install-obsidian [--os OS] [--method M] [--apply]     install only when absent; dry run prints the command
    create-vault     --name N --path P [--apply]          make a vault directory and name it in config
    adopt            [--role NAME=ROLE ...] [--apply]     give every discovered vault a role

Three answers, never two. Detection reports `installed`, `missing` or
`unknown`. `unknown` means no probe that could have seen Obsidian was able to
run, and it is never treated as `missing`: installing on an unknown is how a
second copy lands beside a first one nobody could see.

Roles are stored per vault in config as "role":

    primary  receives captures and imports; exactly one, and it is also `default`
    recall   read for injection (vault_ops.py recall), never written
    ignore   answered "no" - kept in config so a re-run does not ask again;
             never recalled, written, or included in --all

A write that would leave zero or two primaries is refused before anything is
written, whichever order the roles were asked in.
"""
import glob
import json
import os
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2

STATE_INSTALLED = "installed"
STATE_MISSING = "missing"
STATE_UNKNOWN = "unknown"

WINGET_ID = "Obsidian.Obsidian"
FLATPAK_ID = "md.obsidian.Obsidian"
DOWNLOAD_PAGE = "https://obsidian.md/download"


# --- probes (module-level so tests can replace them) --------------------------

def which(name):
    return shutil.which(name)


def run(argv, timeout=60):
    """(returncode, stdout) or (None, error text) when the program could not start."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout or ""


def exists(path):
    return os.path.exists(path)


def current_os():
    system = platform.system()
    return {"Windows": "windows", "Darwin": "macos"}.get(system, "linux")


# --- detection -----------------------------------------------------------------

def _linux_probes(evidence, ran):
    if exists("/snap/bin/obsidian"):
        evidence.append("snap: /snap/bin/obsidian exists")
    if which("snap"):
        rc, _ = run(["snap", "list", "obsidian"])
        if rc is not None:
            ran.append("snap list obsidian")
            if rc == 0:
                evidence.append("snap: `snap list obsidian` lists it")
    if which("flatpak"):
        rc, _ = run(["flatpak", "info", FLATPAK_ID])
        if rc is not None:
            ran.append(f"flatpak info {FLATPAK_ID}")
            if rc == 0:
                evidence.append(f"flatpak: {FLATPAK_ID} is installed")
    if which("dpkg-query"):
        rc, out = run(["dpkg-query", "-W", "-f=${Status}", "obsidian"])
        if rc is not None:
            ran.append("dpkg-query -W obsidian")
            if rc == 0 and "install ok installed" in out:
                evidence.append("deb: package `obsidian` is installed")
    home = obsidian_common._home()  # pylint: disable=protected-access
    patterns = [os.path.join(home, "Applications", "Obsidian*.AppImage"),
                os.path.join(home, ".local", "bin", "Obsidian*.AppImage"),
                os.path.join(home, "Downloads", "Obsidian*.AppImage"),
                "/opt/Obsidian*.AppImage", "/opt/obsidian/obsidian"]
    for pattern in patterns:
        for hit in sorted(glob.glob(pattern)):
            evidence.append(f"AppImage/manual: {hit}")
    on_path = which("obsidian")
    if on_path:
        evidence.append(f"PATH: {on_path}")


def _windows_probes(evidence, ran):
    local = os.environ.get("LOCALAPPDATA") or os.path.join(obsidian_common._home(),  # pylint: disable=protected-access
                                                            "AppData", "Local")
    program_files = os.environ.get("ProgramFiles") or "C:\\Program Files"
    for candidate in (os.path.join(local, "Programs", "Obsidian", "Obsidian.exe"),
                      os.path.join(program_files, "Obsidian", "Obsidian.exe")):
        if exists(candidate):
            evidence.append(f"file: {candidate}")
    if which("winget"):
        rc, out = run(["winget", "list", "--id", WINGET_ID, "-e",
                       "--accept-source-agreements"])
        if rc is not None:
            ran.append(f"winget list --id {WINGET_ID} -e")
            if rc == 0 and WINGET_ID.lower() in out.lower():
                evidence.append(f"winget: {WINGET_ID} is installed")


def _macos_probes(evidence, ran):
    if exists("/Applications/Obsidian.app"):
        evidence.append("file: /Applications/Obsidian.app")
    ran.append("ls /Applications/Obsidian.app")


def detect(os_name=None):
    """{"os", "state", "evidence": [...], "probes_ran": [...]}.

    `installed` on any evidence; `missing` when at least one inventory probe
    ran and none found it; `unknown` when nothing that could have seen it ran.
    """
    os_name = os_name or current_os()
    evidence, ran = [], []
    if os_name == "windows":
        _windows_probes(evidence, ran)
    elif os_name == "macos":
        _macos_probes(evidence, ran)
    else:
        _linux_probes(evidence, ran)
    if evidence:
        state = STATE_INSTALLED
    elif ran:
        state = STATE_MISSING
    else:
        state = STATE_UNKNOWN
    return {"os": os_name, "state": state, "evidence": evidence, "probes_ran": ran}


def install_plan(os_name, method=None):
    """(method, argv or None, note). argv None means a manual step, never run for you."""
    if os_name == "windows":
        return ("winget", ["winget", "install", "--id", WINGET_ID, "-e",
                           "--accept-source-agreements", "--accept-package-agreements"],
                "Windows Package Manager, user scope")
    if os_name == "macos":
        return ("manual", None, f"download the .dmg from {DOWNLOAD_PAGE}")
    if method is None:
        if which("snap"):
            method = "snap"
        elif which("flatpak"):
            method = "flatpak"
        else:
            method = "appimage"
    if method == "snap":
        return ("snap", ["sudo", "snap", "install", "obsidian", "--classic"],
                "snap needs sudo; you will be prompted for a password")
    if method == "flatpak":
        return ("flatpak", ["flatpak", "install", "-y", "flathub", FLATPAK_ID],
                "needs the flathub remote (flatpak remote-add --if-not-exists flathub "
                "https://dl.flathub.org/repo/flathub.flatpakrepo)")
    if method == "deb":
        return ("deb", None, f"download obsidian_<version>_amd64.deb from {DOWNLOAD_PAGE}, "
                             "then: sudo apt install ./obsidian_<version>_amd64.deb")
    return ("appimage", None, f"download Obsidian-<version>.AppImage from {DOWNLOAD_PAGE} "
                              "into ~/Applications and chmod +x it")


def cmd_detect_obsidian(args, prober):  # pylint: disable=unused-argument
    result = detect(args.os)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Obsidian on {result['os']}: {result['state'].upper()}")
        for line in result["evidence"]:
            print(f"  found  {line}")
        for line in result["probes_ran"]:
            print(f"  probed {line}")
        if result["state"] == STATE_UNKNOWN:
            print("  no probe that could see an install was able to run - this is NOT "
                  "the same as missing")
    return EXIT_OK if result["state"] == STATE_INSTALLED else EXIT_PROBLEMS


def cmd_install_obsidian(args, prober):  # pylint: disable=unused-argument
    result = detect(args.os)
    os_name = result["os"]
    if result["state"] == STATE_INSTALLED:
        print(f"Obsidian is already installed ({'; '.join(result['evidence'])}). "
              "Nothing to do.")
        return EXIT_OK
    if result["state"] == STATE_UNKNOWN and not args.even_if_unknown:
        print("Refusing: detection could not run any probe, so an existing install "
              "cannot be ruled out. Re-run with --even-if-unknown once you have checked "
              "by hand.", file=sys.stderr)
        return EXIT_PROBLEMS
    method, argv, note = install_plan(os_name, args.method)
    if argv is None:
        print(f"Manual install ({method}): {note}")
        print("Nothing here downloads Obsidian for you on this path.")
        return EXIT_PROBLEMS
    print(f"Planned install ({method}): {' '.join(argv)}")
    print(f"  {note}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to run exactly that command.")
        return EXIT_PROBLEMS
    rc, out = run(argv, timeout=1800)
    if out:
        print(out.rstrip())
    if rc != 0:
        print(f"install command failed (exit {rc})", file=sys.stderr)
        return EXIT_PROBLEMS
    after = detect(os_name)
    print(f"after install: {after['state']}")
    return EXIT_OK if after["state"] == STATE_INSTALLED else EXIT_PROBLEMS


# --- config helpers ------------------------------------------------------------

def _config_vaults(config):
    """A mutable copy of config["vaults"], carrying the legacy vaultPath across."""
    vaults = config.get("vaults")
    vaults = {k: dict(v) for k, v in vaults.items() if isinstance(v, dict)} \
        if isinstance(vaults, dict) else {}
    if not vaults and config.get("vaultPath"):
        vaults["memory"] = {"path": config["vaultPath"], "default": True}
    return vaults


def primaries(vaults):
    return sorted(n for n, e in vaults.items() if isinstance(e, dict) and e.get("role") == "primary")


def validate_roles(vaults):
    """None when the role set is acceptable, else the reason it is refused."""
    if not any(isinstance(e, dict) and e.get("role") for e in vaults.values()):
        return None  # roles never assigned: the pre-roles config shape, still valid
    found = primaries(vaults)
    if not found:
        return "no vault has role primary - captures and imports would have nowhere to go"
    if len(found) > 1:
        return f"{len(found)} vaults have role primary ({', '.join(found)}) - exactly one may"
    return None


def primary_vault():
    """(name, path) of the vault captures and imports go to, or (None, None).

    The role-primary vault when roles are in use, else the default vault - the
    same one the capture hook has always written to.
    """
    vaults = obsidian_common.list_vaults()
    for name, entry in vaults.items():
        if entry.get("role") == "primary":
            return name, entry["path"]
    name = obsidian_common.default_vault_name()
    path = obsidian_common.resolve_vault_path()
    return (name, path) if path else (None, None)


# --- create-vault ----------------------------------------------------------------

def cmd_create_vault(args, prober):  # pylint: disable=unused-argument
    path = os.path.abspath(os.path.expanduser(args.path))
    config = obsidian_common.read_config()
    vaults = _config_vaults(config)
    steps = []
    if not os.path.isdir(path):
        steps.append(("mkdir", path))
    for sub in (".obsidian", "inbox"):
        if not os.path.isdir(os.path.join(path, sub)):
            steps.append(("mkdir", os.path.join(path, sub)))
    existing = vaults.get(args.name) or {}
    if existing.get("path") and os.path.abspath(existing["path"]) != path:
        print(f"refused: vaults.{args.name} already points at {existing['path']}",
              file=sys.stderr)
        return EXIT_USAGE
    if not existing.get("path"):
        steps.append(("config", f"vaults.{args.name}.path = {path}"))
    if not steps:
        print(f"{path} is already a vault named {args.name!r} in config. Nothing to do.")
        return EXIT_OK
    if os.path.isdir(path) and os.listdir(path) and \
            not os.path.isdir(os.path.join(path, ".obsidian")):
        print(f"note: {path} already holds files; this turns that folder into a vault "
              "in place and moves nothing.")
    print("Planned:")
    for kind, what in steps:
        print(f"  {kind:6} {what}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to do exactly that. Then give it a role "
              "with `adopt --role NAME=primary`.")
        return EXIT_PROBLEMS
    for kind, what in steps:
        if kind == "mkdir":
            os.makedirs(what, exist_ok=True)
    if not existing.get("path"):
        entry = dict(existing)
        entry["path"] = path
        vaults[args.name] = entry
        config["vaults"] = vaults
        obsidian_common.write_config(config)
    print(f"created. Open {path} once in Obsidian (Open folder as vault) so it registers "
          "the vault itself.")
    return EXIT_OK


# --- adopt -------------------------------------------------------------------------

def _parse_role_pairs(pairs):
    out = {}
    for raw in pairs or []:
        name, sep, role = raw.partition("=")
        if not sep or not name or role not in obsidian_common.ROLES:
            return None, (f"--role takes NAME=ROLE with ROLE one of "
                          f"{', '.join(obsidian_common.ROLES)} (got {raw!r})")
        if name in out and out[name] != role:
            return None, f"{name!r} given two roles"
        out[name] = role
    return out, None


def plan_roles(discovered, config, wanted):
    """(new_vaults, changes) - changes is [(name, field, old, new)]."""
    vaults = _config_vaults(config)
    changes = []
    for name, role in wanted.items():
        entry = vaults.get(name)
        if entry is None:
            entry = {"path": discovered[name]["path"]}
            vaults[name] = entry
            changes.append((name, "path", None, entry["path"]))
        if entry.get("role") != role:
            changes.append((name, "role", entry.get("role"), role))
            entry["role"] = role
    new_primary = [n for n, r in wanted.items() if r == "primary"]
    if len(new_primary) == 1:
        target = new_primary[0]
        for name, entry in vaults.items():
            want_default = name == target
            if (entry.get("default") is True) != want_default:
                changes.append((name, "default", entry.get("default"),
                                True if want_default else None))
                if want_default:
                    entry["default"] = True
                else:
                    entry.pop("default", None)
    return vaults, changes


def cmd_adopt(args, prober):  # pylint: disable=unused-argument
    discovered = obsidian_common.discover_vaults()
    config = obsidian_common.read_config()
    wanted, err = _parse_role_pairs(args.role)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    current = _config_vaults(config)

    if not wanted:
        rows = []
        for name in sorted(set(discovered) | set(current)):
            entry = current.get(name) or {}
            path = entry.get("path") or discovered.get(name, {}).get("path")
            rows.append({"vault": name, "path": path, "role": entry.get("role"),
                         "configured": name in current,
                         "on_disk": bool(path and os.path.isdir(path))})
        problem = validate_roles(current)
        if args.json:
            print(json.dumps({"vaults": rows, "problem": problem}, indent=2))
        else:
            print(f"{len(rows)} vault(s). Ask for a role for each: primary (exactly one; "
                  "receives captures and imports), recall (read for injection), ignore.\n")
            for r in rows:
                print(f"  {r['vault']:24} {r['role'] or 'unassigned':10} {r['path']}"
                      + ("" if r["on_disk"] else "   [not on disk]"))
            if problem:
                print(f"\n[FAIL] {problem}")
        return EXIT_PROBLEMS if problem else EXIT_OK

    unknown = sorted(n for n in wanted if n not in discovered and n not in current)
    if unknown:
        print(f"unknown vault(s): {', '.join(unknown)} (known: "
              f"{', '.join(sorted(set(discovered) | set(current))) or 'none'})",
              file=sys.stderr)
        return EXIT_USAGE
    vaults, changes = plan_roles(discovered, config, wanted)
    problem = validate_roles(vaults)
    if problem:
        print(f"refused, nothing written: {problem}", file=sys.stderr)
        return EXIT_USAGE
    if not changes:
        print("Every requested role is already set. Nothing to change.")
        return EXIT_OK
    print(f"Planned config change ({obsidian_common.config_path()}):")
    for name, field, old, new in changes:
        print(f"  vaults.{name}.{field}: {old!r} -> {new!r}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to write it.")
        return EXIT_PROBLEMS
    config["vaults"] = vaults
    obsidian_common.write_config(config)
    print(f"wrote {obsidian_common.config_path()}")
    return EXIT_OK


def add_parsers(sub):
    s = sub.add_parser("detect-obsidian", help="is Obsidian installed: installed/missing/unknown")
    s.add_argument("--os", choices=("linux", "windows", "macos"))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_detect_obsidian)

    s = sub.add_parser("install-obsidian",
                       help="install Obsidian only when absent; dry run prints the command")
    s.add_argument("--os", choices=("linux", "windows", "macos"))
    s.add_argument("--method", choices=("snap", "flatpak", "deb", "appimage", "winget"))
    s.add_argument("--even-if-unknown", action="store_true",
                   help="install even though detection could not run any probe")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_install_obsidian)

    s = sub.add_parser("create-vault", help="create a vault directory and name it in config")
    s.add_argument("--name", required=True)
    s.add_argument("--path", required=True)
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_create_vault)

    s = sub.add_parser("adopt", help="list vaults with their roles, or set roles "
                                     "(primary/recall/ignore) - exactly one primary")
    s.add_argument("--role", action="append", metavar="NAME=ROLE")
    s.add_argument("--json", action="store_true")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_adopt)
