"""One real call to a review provider, from the repo root, with review's own flags.

    python3 provider_probe.py codex --root . [--model M] [--effort E] [--timeout 120]
    python3 provider_probe.py copilot --root . --model M

Why it exists (T-0065, item 10): the only real-call check used to be a
`codex exec ... "reply OK"` an agent typed by hand, from whatever directory it
was in. Typed from a `/tmp` export, Codex refuses with "Not inside a trusted
directory". This script builds the command with `review_run.command_for` and
runs it with `review_run.launch`, so the probe and a real review run the same
command line: `--skip-git-repo-check`, `-C <root>`, and `<root>` as the cwd,
whatever directory the probe itself was started from.

It costs one real call, so it runs only when someone invokes it: never from a
hook, never from `/crew:status`, never from `/crew:review` on its own. It
reserves nothing and never touches the review ledger.

Exit 0 `<provider>: ok (<model or default>)`: a delivered answer (codex: a
completed turn with no failure event, at exit 0). Exit 1 `<provider>: FAILED
- <reason>`: the call failed, its event stream is incomplete, or it timed
out. Exit 2: the provider is not installed, or a usage error (copilot needs
`--model`, as `review_run.run` does).
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import os  # noqa: E402

import review_checks  # noqa: E402
import review_run  # noqa: E402
import review_verdict  # noqa: E402

PROVIDERS = ("codex", "copilot")
PROMPT = "Reply with the single word OK."
DEFAULT_TIMEOUT = 120


def _first_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[0] if lines else ""


def probe(provider, root, model="", effort="", timeout=DEFAULT_TIMEOUT):
    """(exit code, line)."""
    exe = review_checks.resolve_executable(provider)
    if not exe:
        return 2, f"{provider}: not installed"
    cmd = review_run.command_for(provider, exe, root, PROMPT, model, effort)
    stdout, stderr, code, timed_out = review_run.launch(cmd, root, timeout)
    if timed_out:
        return 1, f"{provider}: FAILED - timed out"
    if provider == "codex":
        message, error = review_verdict.codex_final_message(stdout)
        # A malformed event can carry a non-string text: no message, not a crash.
        message = message if isinstance(message, str) else ""
        if code == 0 and error is None and message.strip():
            return 0, f"{provider}: ok ({model or 'default'})"
        if code == 0 and error is None:
            error = "the call completed with no agent message"
        reason = (_first_line(stderr) if code != 0 else "") or error or f"exit {code}"
    else:
        if code == 0 and stdout.strip():
            return 0, f"{provider}: ok ({model})"
        reason = _first_line(stderr) or (f"exit {code}" if code else "no output")
    return 1, f"{provider}: FAILED - {reason}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("provider", choices=PROVIDERS)
    parser.add_argument("--root", default=".")
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    if args.provider == "copilot" and not args.model:
        print("copilot: usage - --model is required (copilot has no default model here)")
        return 2
    code, line = probe(args.provider, os.path.abspath(args.root), args.model, args.effort,
                       args.timeout)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
