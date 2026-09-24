"""String-level check for Resolve-CrewBash's native-extension gate (#224 residue).

PR #224 (origin/todo/xdist-and-codex-profile-tickets, 31e1451c) found that
`Resolve-CrewPython`'s PATH candidates could be an extensionless PATH shim
(pyenv/conda/direnv-style) that `CreateProcess` cannot launch directly and
that hangs rather than errors when invoked anyway, and fixed it there with a
native-extension allow-list (`.exe`/`.com`/`.cmd`/`.bat`) gated on real-OS
detection. `Resolve-CrewBash`'s own PATH fallback loop (verify-gate.ps1,
after the git-relative walk-up) resolves a bare `bash` on PATH the exact same
way -- CommandType Application, a real non-WindowsApps `.Source` -- and is
exactly as vulnerable to the same extensionless shim. This module asserts
the same guard now exists there too.

This is a STRING-level test, not a behavioural one, same reasoning as
test_ps1_python_probe.py's equivalent for Resolve-CrewPython: the whole
sibling module, test_verify_gate_bash_resolver.py, is skipped everywhere but
native Windows (WSL/WindowsApps bash-shadowing is inherently Windows-only),
so a behavioural reproduction of the hang never runs in this suite's CI at
all. Reading the source is the only check that runs everywhere.
"""
import pathlib

import context  # noqa: F401  pylint: disable=unused-import

_PS1 = pathlib.Path(context._ROOT) / "hooks" / "scripts" / "verify-gate.ps1"  # pylint: disable=protected-access


def _bash_resolver():
    src = _PS1.read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewBash {")
    return src[start:src.index("\nfunction Resolve-CrewPython {", start)]


def test_resolve_crew_bash_rejects_an_extensionless_path_candidate_on_real_windows():
    body = _bash_resolver()
    assert "IsWindows" in body, "no real-Windows detection found in Resolve-CrewBash"
    for ext in (".exe", ".com", ".cmd", ".bat"):
        assert ext in body, f"native extension {ext!r} missing from Resolve-CrewBash's allow-list"

    # The gate must actually be CONSULTED inside the PATH fallback loop
    # (after the WindowsApps/SystemRoot filters and before `return $src`),
    # not merely declared somewhere in the function -- a `$crewBashRealWindows
    # = ...` assignment sitting unused above the loop would satisfy every
    # check above this one while refusing nothing.
    loop_start = body.index("$candidates = Get-Command bash -All")
    return_pos = body.index("return $src", loop_start)
    notcontains_pos = body.index("-notcontains", loop_start)
    continue_pos = body.index("continue", notcontains_pos)
    assign_line = next(
        line for line in body.splitlines()
        if "IsWindows" in line and "=" in line and not line.lstrip().startswith("#"))
    gate_pos = body.index(assign_line)
    assert loop_start < return_pos, "sanity: the PATH fallback loop's own return was not found"
    assert gate_pos < notcontains_pos < continue_pos < return_pos, (
        "the extensionless-file gate must be both declared before the PATH "
        "fallback loop AND actually checked (a '-notcontains' test followed "
        "by 'continue') before that loop's `return $src`, or a candidate it "
        "should refuse still escapes")

    # Same seam distinction test_ps1_python_probe.py makes for
    # Resolve-CrewPython: this repo's OWN bash-resolver fixtures
    # (test_verify_gate_bash_resolver.py) run under a faked $env:OS on
    # native Windows already, but gating on that seam instead of $IsWindows
    # would still be the wrong thing to depend on -- $IsWindows is the real
    # signal Resolve-CrewPython already established for this exact guard.
    assert "$env:OS" not in assign_line, (
        "Resolve-CrewBash's extensionless-file gate reads $env:OS instead of "
        "real OS detection ($IsWindows) for its real-Windows check: " + assign_line)
