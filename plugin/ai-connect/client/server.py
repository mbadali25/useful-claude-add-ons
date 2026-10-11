"""AI-Connect MCP server over STDIO — one per Claude Code session.

The session's peer name is client.name, the name its token is bound to
(see peer_name.py). A second session with the same name waits on standby
until the name is free.
"""

import os
import signal
import sys
from pathlib import Path

# Started as a plain script by Claude Code: make the client modules and
# config_loader importable.
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import client_settings, load_config
from log_setup import setup_logging
from mcp_app import create_app  # pylint: disable=import-error
from peer_name import peer_name, record_session_name, remove_dead_sessions, session_pid

name = peer_name(os.environ, Path.cwd(), client_settings(load_config()).name)
# STDIO carries the MCP protocol, so logs go to a file only, one per peer:
# several sessions run at once, and a rotated file must have a single writer
setup_logging(f"mcp-{name.replace(':', '_')}.log")
mcp = create_app(name)


def main() -> None:
    # The session's watcher finds the name by CLAUDE_PID
    remove_dead_sessions()
    session_file = record_session_name(session_pid(), name)
    def end(*_: object) -> None:
        # Claude Code ends its MCP servers with SIGTERM, which would skip the
        # finally below. Remove the file, then end as SIGTERM would have.
        # Windows ends them hard; the file then stays until the next session
        # with that process id overwrites it.
        session_file.unlink(missing_ok=True)
        session_file.with_suffix(".seen").unlink(missing_ok=True)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)

    signal.signal(signal.SIGTERM, end)
    try:
        mcp.run()
    finally:
        session_file.unlink(missing_ok=True)
        session_file.with_suffix(".seen").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
