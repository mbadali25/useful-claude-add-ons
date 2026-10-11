"""File logging of the Bridge and the MCP clients, rotated by size as set in the config."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config_loader import load_config

LOG_DIR = Path.home() / ".config" / "ai-connect"


def setup_logging(file_name: str, *extra_handlers: logging.Handler) -> None:
    """Log to LOG_DIR/file_name, rotated at logging.max_megabytes.

    Rotation renames the file, so exactly one process may write to it:
    each STDIO client therefore gets a file of its own (see client/server.py).
    """
    rotation = load_config()["logging"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / file_name,
        maxBytes=rotation["max_megabytes"] * 1024 * 1024,
        backupCount=rotation["backup_count"],
        # Windows would otherwise use its ANSI code page
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[file_handler, *extra_handlers],
    )
