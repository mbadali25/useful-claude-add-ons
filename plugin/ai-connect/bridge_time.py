"""The Bridge's timestamps: UTC, ISO with milliseconds, e.g. 2026-01-03T14:30:45.123Z.

The watcher and history_all compare them as strings, so the format must
stay fixed.
"""

from datetime import datetime, timezone


def bridge_timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_bridge_timestamp(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
