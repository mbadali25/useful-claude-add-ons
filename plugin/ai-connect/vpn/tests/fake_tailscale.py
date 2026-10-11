"""Stand-in for the `tailscale` CLI. Behaviour comes from the JSON file in $FAKE_TS_STATE:

  backend      BackendState that `status --json` reports ("Running", "Stopped", ...)
  after_up     BackendState to switch to after a successful `up` (default "Running")
  up_rc        exit code of `up` (default 0); up_stderr is printed on stderr
  up_rc_userspace / up_stderr_userspace   the same, when --socket= is passed
  status_rc    exit code of `status` (default 0)

Every invocation's argv is appended to $FAKE_TS_LOG, one JSON list per line.
"""
import json
import os
import sys


def save(path: str, state: dict) -> None:
    text = json.dumps(state)  # build the payload before the open truncates the file
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main() -> int:
    state_path = os.environ["FAKE_TS_STATE"]
    with open(state_path, encoding="utf-8") as fh:
        state = json.load(fh)
    argv = sys.argv[1:]
    with open(os.environ["FAKE_TS_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")
    userspace = any(a.startswith("--socket=") for a in argv)
    args = [a for a in argv if not a.startswith("--socket=")]
    cmd = args[0] if args else ""
    if cmd == "status":
        print(json.dumps({"BackendState": state.get("backend", "Stopped")}))
        return int(state.get("status_rc", 0))
    if cmd == "up":
        suffix = "_userspace" if userspace else ""
        rc = int(state.get("up_rc" + suffix, state.get("up_rc", 0) if not userspace else 0))
        err = state.get("up_stderr" + suffix, "" if userspace else state.get("up_stderr", ""))
        if err:
            print(err, file=sys.stderr)
        if rc == 0:
            state["backend"] = state.get("after_up", "Running")
            save(state_path, state)
        return rc
    if cmd in ("down", "logout"):
        state["backend"] = "Stopped"
        save(state_path, state)
        return int(state.get("down_rc", 0))
    print(f"fake tailscale: unknown command {argv}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
