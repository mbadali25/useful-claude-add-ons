#!/usr/bin/env python3
"""Preflight checks for `terraform-docs .` - reports state, changes nothing.

Verifies that the binary exists, that its version satisfies both the repo's
.tool-versions pin and the minimum the config file actually requires, and that
every file the config points at is present and well-formed.

This script never installs, upgrades or modifies anything.

Usage:
    python3 tfdocs_preflight.py [MODULE_DIR]   # default: current directory

Exit codes:
    0  ready to run
    1  blocked - at least one FAIL
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Minimum release that supports `footer-from` and exposes `.Module` in `content`.
MODERN_FEATURES_MIN = (0, 16, 0)
BASELINE_MIN = (0, 12, 0)

CONFIG_NAMES = (".terraform-docs.yml", ".terraform-docs.yaml")

results: list[tuple[str, str, str]] = []


def record(status: str, label: str, detail: str = "") -> None:
    results.append((status, label, detail))


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def fmt(v: tuple[int, int, int]) -> str:
    return ".".join(str(p) for p in v)


def find_config(module_dir: Path) -> Path | None:
    candidates = []
    for base in (module_dir, module_dir / ".config", Path.cwd(), Path.cwd() / ".config"):
        candidates.extend(base / n for n in CONFIG_NAMES)
    candidates.extend(Path.home() / ".tfdocs.d" / n for n in CONFIG_NAMES)
    return next((c for c in candidates if c.is_file()), None)


def load_config(path: Path) -> dict:
    """Extract the handful of keys this script cares about.

    Uses PyYAML when available and falls back to regex so the script runs on a
    bare Python install. The fallback only reads top-level scalars plus
    `output.file`, which is all that is needed here.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    cfg: dict = {"_raw": raw}

    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw) or {}
        cfg["formatter"] = parsed.get("formatter")
        cfg["header-from"] = parsed.get("header-from")
        cfg["footer-from"] = parsed.get("footer-from")
        cfg["content"] = parsed.get("content") or ""
        cfg["output-file"] = (parsed.get("output") or {}).get("file")
        cfg["output-mode"] = (parsed.get("output") or {}).get("mode")
        cfg["recursive"] = bool((parsed.get("recursive") or {}).get("enabled"))
        return cfg
    except ImportError:
        pass

    def top(key: str) -> str | None:
        m = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.+?)[ \t]*$", raw)
        if not m:
            return None
        return m.group(1).strip().strip("\"'") or None

    cfg["formatter"] = top("formatter")
    cfg["header-from"] = top("header-from")
    cfg["footer-from"] = top("footer-from")
    cfg["content"] = raw  # substring checks below stay valid
    out = re.search(r"(?ms)^output:\s*\n((?:[ \t]+.*\n?)+)", raw)
    block = out.group(1) if out else ""
    fm = re.search(r"(?m)^[ \t]+file:[ \t]*(.+?)[ \t]*$", block)
    cfg["output-file"] = fm.group(1).strip().strip("\"'") if fm else None
    mm = re.search(r"(?m)^[ \t]+mode:[ \t]*(.+?)[ \t]*$", block)
    cfg["output-mode"] = mm.group(1).strip().strip("\"'") if mm else None
    rec = re.search(r"(?ms)^recursive:\s*\n((?:[ \t]+.*\n?)+)", raw)
    cfg["recursive"] = bool(rec and re.search(r"enabled:[ \t]*true", rec.group(1)))
    return cfg


def read_tool_versions(start: Path) -> tuple[tuple[int, int, int] | None, Path | None]:
    for d in [start, *start.parents]:
        tv = d / ".tool-versions"
        if tv.is_file():
            m = re.search(
                r"(?m)^terraform-docs[ \t]+(\S+)", tv.read_text(encoding="utf-8", errors="replace")
            )
            return (parse_version(m.group(1)) if m else None), tv
    return None, None


def main() -> int:
    module_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not module_dir.is_dir():
        print(f"FAIL  {module_dir} is not a directory")
        return 1

    print(f"terraform-docs preflight - {module_dir}\n")

    # --- config -----------------------------------------------------------
    cfg_path = find_config(module_dir)
    if not cfg_path:
        record("FAIL", "config", "no .terraform-docs.yml found (scaffold from assets/)")
        cfg: dict = {}
    else:
        rel = os.path.relpath(cfg_path, module_dir)
        record("PASS", "config", rel)
        cfg = load_config(cfg_path)
        if not cfg.get("formatter"):
            record("FAIL", "formatter", "not set - bare `terraform-docs .` needs it")

    needs_modern = bool(cfg.get("footer-from")) or ".Module" in (cfg.get("content") or "")
    required_min = MODERN_FEATURES_MIN if needs_modern else BASELINE_MIN

    # --- binary -----------------------------------------------------------
    exe = shutil.which("terraform-docs")
    installed = None
    if not exe:
        record("FAIL", "terraform-docs", "not on PATH - see references/install.md")
    else:
        try:
            out = subprocess.run(
                [exe, "--version"], capture_output=True, text=True, timeout=30, check=False
            ).stdout
            installed = parse_version(out)
            record("PASS", "terraform-docs", f"{fmt(installed) if installed else out.strip()} ({exe})")
        except Exception as e:  # noqa: BLE001
            record("WARN", "terraform-docs", f"found at {exe} but --version failed: {e}")

    if installed and installed < required_min:
        why = "config uses footer-from / .Module in content" if needs_modern else "baseline"
        record(
            "FAIL",
            "version",
            f"{fmt(installed)} < {fmt(required_min)} required ({why})",
        )
    elif installed:
        record("PASS", "version", f">= {fmt(required_min)} required")

    # --- .tool-versions pin ----------------------------------------------
    pinned, tv_path = read_tool_versions(module_dir)
    if tv_path is None:
        record("WARN", ".tool-versions", "not found - version is unpinned")
    elif pinned is None:
        record("WARN", ".tool-versions", f"{tv_path} has no terraform-docs line")
    elif pinned < required_min:
        record(
            "FAIL",
            ".tool-versions",
            f"pins {fmt(pinned)}, config requires >= {fmt(required_min)} - bump the pin",
        )
    else:
        record("PASS", ".tool-versions", f"pins {fmt(pinned)}")
        if installed and installed != pinned:
            record(
                "WARN",
                "pin drift",
                f"running {fmt(installed)} but pinned {fmt(pinned)} - run `asdf install`",
            )

    # --- referenced files -------------------------------------------------
    header_rel = cfg.get("header-from") or "main.tf"
    header = module_dir / header_rel
    if not header.is_file():
        record("FAIL", "header-from", f"{header_rel} missing")
    else:
        text = header.read_text(encoding="utf-8", errors="replace")
        if header.suffix in (".tf", ".tofu"):
            if not text.lstrip().startswith("/**"):
                record(
                    "FAIL",
                    "header-from",
                    f"{header_rel} does not open with a /** */ block - header renders empty",
                )
            else:
                record("PASS", "header-from", header_rel)
        else:
            record("PASS", "header-from", header_rel)
        if b"\r\n" in header.read_bytes():
            record("WARN", "line endings", f"{header_rel} is CRLF - see SKILL.md on diff noise")

    footer_rel = cfg.get("footer-from")
    if footer_rel:
        if (module_dir / footer_rel).is_file():
            record("PASS", "footer-from", footer_rel)
        else:
            record("FAIL", "footer-from", f"{footer_rel} missing")

    # --- output file and markers -----------------------------------------
    out_rel = cfg.get("output-file")
    mode = (cfg.get("output-mode") or "inject").lower()
    if not out_rel:
        record("WARN", "output.file", "not set - output goes to stdout only")
    else:
        out_path = module_dir / out_rel
        if not out_path.is_file():
            record("WARN", "output.file", f"{out_rel} does not exist yet - it will be created")
        else:
            body = out_path.read_text(encoding="utf-8", errors="replace")
            has_begin = "BEGIN_TF_DOCS" in body
            has_end = "END_TF_DOCS" in body
            if mode == "inject" and has_begin and has_end:
                record("PASS", "markers", f"{out_rel} has BEGIN/END_TF_DOCS")
            elif mode == "inject":
                record(
                    "WARN",
                    "markers",
                    f"{out_rel} is missing BEGIN/END_TF_DOCS - generated block will be appended",
                )
            elif mode == "replace":
                record("WARN", "output.mode", "replace - the whole file is overwritten")

    if cfg.get("recursive"):
        record("WARN", "recursive", "enabled - submodules under `path` are also regenerated")

    # --- report -----------------------------------------------------------
    width = max((len(label) for _, label, _ in results), default=0)
    for status, label, detail in results:
        print(f"{status:<5} {label.ljust(width)}  {detail}")

    fails = sum(1 for s, _, _ in results if s == "FAIL")
    print()
    if fails:
        print(f"{fails} blocking issue(s). Fix these before running `terraform-docs .`")
        return 1
    print("Ready. Run:  terraform-docs .")
    return 0


if __name__ == "__main__":
    sys.exit(main())
