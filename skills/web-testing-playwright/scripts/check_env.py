#!/usr/bin/env python3
"""Report what's installed for Playwright work, and what to run for what's missing.

Safe to run anywhere: it only inspects, it never installs. Use --json for a
machine-readable summary.

    python3 check_env.py
    python3 check_env.py --json
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 20


def run(cmd):
    """Run a command, return stripped stdout or None. Never raises."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            shell=(platform.system() == "Windows"),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or proc.stderr).strip() or None


def which(name):
    return shutil.which(name)


def browsers_dir():
    """Where Playwright caches its browser binaries."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override != "0":
        return Path(override)
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def installed_browsers():
    d = browsers_dir()
    if not d.is_dir():
        return []
    names = []
    for child in sorted(d.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return names


def python_playwright():
    try:
        import playwright  # noqa: F401
    except Exception:
        return None
    out = run([sys.executable, "-m", "playwright", "--version"])
    return out or "installed (version unknown)"


def node_playwright():
    """Check for a locally or globally installed Node Playwright.

    Uses --no-install so npx never silently downloads a package.
    """
    if not which("npx"):
        return None
    return run(["npx", "--no-install", "playwright", "--version"])


def collect():
    system = platform.system()
    info = {
        "os": system,
        "os_release": platform.release(),
        "arch": platform.machine(),
        "wsl": False,
        "python": platform.python_version(),
        "python_exe": sys.executable,
        "node": run(["node", "--version"]),
        "npm": run(["npm", "--version"]),
        "python_playwright": python_playwright(),
        "node_playwright": node_playwright(),
        "browsers_dir": str(browsers_dir()),
        "browsers": installed_browsers(),
        "package_managers": {},
        "display": None,
    }

    if system == "Linux":
        rel = Path("/proc/version")
        if rel.exists():
            try:
                info["wsl"] = "microsoft" in rel.read_text().lower()
            except OSError:
                pass
        info["display"] = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        for mgr in ("apt-get", "dnf", "yum", "pacman", "zypper"):
            if which(mgr):
                info["package_managers"][mgr] = True
    elif system == "Windows":
        for mgr in ("winget", "choco", "scoop"):
            ver = run([mgr, "--version"]) if which(mgr) else None
            if ver:
                info["package_managers"][mgr] = ver

    return info


def recommendations(info):
    """Ordered list of (what, why, command) for anything missing."""
    recs = []
    system = info["os"]
    win = system == "Windows"

    if not info["node"] and not info["python_playwright"]:
        if win:
            if "winget" in info["package_managers"]:
                cmd = "winget install --id OpenJS.NodeJS.LTS -e"
            elif "choco" in info["package_managers"]:
                cmd = "choco install nodejs-lts -y   (needs an elevated shell)"
            else:
                cmd = "No winget or choco found — see references/setup-windows.md"
            recs.append(("Node.js (optional)", "only if you want @playwright/test", cmd))
        else:
            recs.append(
                ("Node.js (optional)", "only if you want @playwright/test",
                 "see references/setup-linux.md")
            )

    if not info["python_playwright"]:
        pipcmd = f"{Path(sys.executable).name} -m pip install playwright"
        if system == "Linux":
            pipcmd += "   (add --break-system-packages on Debian/Ubuntu, or use a venv)"
        recs.append(("Playwright for Python", "required by the bundled scripts", pipcmd))

    if not info["browsers"]:
        if info["python_playwright"] or not recs:
            base = f"{Path(sys.executable).name} -m playwright install chromium"
        else:
            base = "python -m playwright install chromium   (after installing the package)"
        if system == "Linux":
            base += "\n      then: sudo " + base.split("   ")[0] + "-deps chromium"
        recs.append(
            ("Browser binaries", "~150-400 MB download per browser", base)
        )

    if system == "Linux" and not info["display"] and not info["wsl"]:
        recs.append(
            ("Headed mode (optional)", "no DISPLAY detected — headless works fine as-is",
             "install xvfb and prefix commands with: xvfb-run -a")
        )

    return recs


def render(info):
    lines = []
    ok = lambda b: "yes" if b else "NO"  # noqa: E731

    wsl = " (WSL)" if info["wsl"] else ""
    lines.append(f"OS            : {info['os']} {info['os_release']} [{info['arch']}]{wsl}")
    lines.append(f"Python        : {info['python']}  ({info['python_exe']})")
    lines.append(f"Node / npm    : {info['node'] or 'not found'} / {info['npm'] or 'not found'}")
    lines.append(f"Playwright/py : {info['python_playwright'] or 'not installed'}")
    lines.append(f"Playwright/js : {info['node_playwright'] or 'not installed'}")
    lines.append(f"Browsers dir  : {info['browsers_dir']}")
    lines.append(f"Browsers      : {', '.join(info['browsers']) if info['browsers'] else 'none installed'}")
    if info["package_managers"]:
        pretty = ", ".join(
            k if v is True else f"{k} {v.splitlines()[0]}"
            for k, v in info["package_managers"].items()
        )
        lines.append(f"Pkg managers  : {pretty}")
    if info["os"] == "Linux":
        lines.append(f"DISPLAY       : {info['display'] or 'none (headless only)'}")

    recs = recommendations(info)
    lines.append("")
    if not recs:
        lines.append("Ready to go. Try: python3 scripts/audit_page.py https://example.com")
    else:
        lines.append("Missing pieces — ASK THE USER before running any of these:")
        for what, why, cmd in recs:
            lines.append(f"\n  {what}  — {why}")
            lines.append(f"      {cmd}")
        guide = "setup-windows.md" if info["os"] == "Windows" else "setup-linux.md"
        lines.append(f"\n  Full instructions: references/{guide}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    info = collect()
    if args.json:
        info["recommendations"] = [
            {"what": w, "why": y, "command": c} for w, y, c in recommendations(info)
        ]
        print(json.dumps(info, indent=2))
    else:
        print(render(info))


if __name__ == "__main__":
    main()
