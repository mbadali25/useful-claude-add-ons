"""AI-Connect MCP server over HTTP/SSE — a permanent service.

For MCP clients that connect to a URL instead of starting a process
(VS Code, Cursor, ...). All of them share one peer: client.name from the
config, or AI_CONNECT_PEER_NAME.
"""

import logging
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import client_settings, load_config
from log_setup import setup_logging
from mcp_app import create_app  # pylint: disable=import-error

# Also to stdout for the journal
setup_logging("mcp-http.log", logging.StreamHandler())

config = load_config()
# One service for every project: client.name_mode per-project does not apply here
_name = os.environ.get("AI_CONNECT_PEER_NAME") or client_settings(config, name="").name
_settings = client_settings(config, name=_name)
mcp = create_app(_name or socket.gethostname(), _settings)


def main() -> None:
    mcp.run(transport="sse", host=config["mcp"]["host"], port=config["mcp"]["port"])


if __name__ == "__main__":
    main()
