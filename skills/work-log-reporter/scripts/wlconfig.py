"""Shared configuration, state, and session-model helpers for work-log-reporter.

Everything the CLI needs to locate the repo, read config, and read/write
sessions lives here so the other modules stay focused on rendering and sending.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

WORKLOG_DIRNAME = "work-log"
CONFIG_FILENAME = "worklog.config.json"
STATE_FILENAME = ".worklog-state.json"
SESSION_FILENAME = "session.json"
NOTES_FILENAME = "notes.md"

SESSION_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-session-(\d{2,})$")

# Fields on an entry that hold lists of short strings. Keeping this in one
# place means adding a new dimension (say, "queues") only takes one edit.
LIST_FIELDS = [
    "code",
    "systems",
    "databases",
    "tables",
    "commands",
    "tickets",
]

FIELD_LABELS = {
    "code": "Code",
    "systems": "Systems",
    "databases": "Databases",
    "tables": "Tables",
    "commands": "Commands",
    "tickets": "Tickets / Refs",
}

DEFAULT_CONFIG = {
    "project": {
        "name": "",
        "environment": "",
    },
    "smtp": {
        "server": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "timeout_seconds": 30,
        "auth": {
            "enabled": True,
            "username": "",
            "password_env": "WORKLOG_SMTP_PASSWORD",
        },
    },
    "email": {
        "from_address": "",
        "from_name": "Work Log Reporter",
        "to": [],
        "cc": [],
        "subject_prefix": "[Work Log]",
    },
    "reporting": {
        "auto_email_enabled": False,
        "mode": "end_of_day",
        "attach_detail_pdf": True,
        "include_commands_in_pdf": True,
    },
}


class WorkLogError(Exception):
    """Raised for user-correctable problems: bad config, missing session, etc."""


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def find_root(start: Path | None = None) -> Path:
    """Locate the repository/workspace root.

    Order of preference: an explicit WORKLOG_ROOT override, then the nearest
    ancestor containing .git (or an existing work-log/), then the cwd. The
    override exists so the skill still works in a bare directory that is not
    a git repo.
    """
    override = os.environ.get("WORKLOG_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists() or (candidate / WORKLOG_DIRNAME).is_dir():
            return candidate
    return current


def worklog_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / WORKLOG_DIRNAME


def config_path(root: Path | None = None) -> Path:
    return worklog_dir(root) / CONFIG_FILENAME


def state_path(root: Path | None = None) -> Path:
    return worklog_dir(root) / STATE_FILENAME


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(root: Path | None = None) -> dict:
    path = config_path(root)
    if not path.exists():
        raise WorkLogError(
            f"No config at {path}. Run: python scripts/worklog.py init"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkLogError(f"{path} is not valid JSON: {exc}") from exc
    return _deep_merge(DEFAULT_CONFIG, raw)


def smtp_password(cfg: dict) -> str | None:
    """Read the SMTP password from the environment.

    Passwords are deliberately never read from the config file: work-log/ is
    committed, and a credential in a committed file is a credential in the
    clone history forever.
    """
    auth = cfg["smtp"]["auth"]
    if not auth.get("enabled", True):
        return None
    var = auth.get("password_env") or "WORKLOG_SMTP_PASSWORD"
    value = os.environ.get(var)
    if not value:
        raise WorkLogError(
            f"Auth is enabled but ${var} is not set in the environment.\n"
            f"Either export {var}=... or set smtp.auth.enabled to false "
            f"if you are relaying through an internal server that does not "
            f"require a login."
        )
    return value


def validate_config(cfg: dict) -> list[str]:
    """Return a list of human-readable problems; empty means good to send."""
    problems: list[str] = []
    smtp = cfg["smtp"]
    email = cfg["email"]
    reporting = cfg["reporting"]

    if not smtp.get("server") or smtp["server"] == "smtp.example.com":
        problems.append("smtp.server is still the placeholder value.")
    try:
        port = int(smtp.get("port", 0))
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("smtp.port must be a number between 1 and 65535.")
    if smtp.get("security") not in {"starttls", "ssl", "none"}:
        problems.append('smtp.security must be "starttls", "ssl", or "none".')

    auth = smtp.get("auth", {})
    if auth.get("enabled", True) and not auth.get("username"):
        problems.append("smtp.auth.enabled is true but smtp.auth.username is empty.")

    if not email.get("from_address"):
        problems.append("email.from_address is empty.")
    if not email.get("to"):
        problems.append("email.to has no recipients.")
    for field in ("to", "cc"):
        value = email.get(field)
        if value is not None and not isinstance(value, list):
            problems.append(f"email.{field} must be a list of addresses.")

    if reporting.get("mode") not in {"per_session", "end_of_day"}:
        problems.append('reporting.mode must be "per_session" or "end_of_day".')

    return problems


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_state(root: Path | None = None) -> dict:
    path = state_path(root)
    if not path.exists():
        return {
            "current_session": None,
            "last_report_sent_at": None,
            "reported_sessions": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A corrupt state file should never block logging work.
        return {
            "current_session": None,
            "last_report_sent_at": None,
            "reported_sessions": [],
        }


def save_state(state: dict, root: Path | None = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def session_dir(session_id: str, root: Path | None = None) -> Path:
    return worklog_dir(root) / session_id


def list_session_ids(root: Path | None = None) -> list[str]:
    base = worklog_dir(root)
    if not base.is_dir():
        return []
    ids = [p.name for p in base.iterdir() if p.is_dir() and SESSION_ID_RE.match(p.name)]
    return sorted(ids)


def next_session_id(date_str: str | None = None, root: Path | None = None) -> str:
    date_str = date_str or datetime.now().astimezone().strftime("%Y-%m-%d")
    highest = 0
    for sid in list_session_ids(root):
        match = SESSION_ID_RE.match(sid)
        if match and match.group(1) == date_str:
            highest = max(highest, int(match.group(2)))
    return f"{date_str}-session-{highest + 1:02d}"


def load_session(session_id: str, root: Path | None = None) -> dict:
    path = session_dir(session_id, root) / SESSION_FILENAME
    if not path.exists():
        raise WorkLogError(f"No session data at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session: dict, root: Path | None = None) -> Path:
    directory = session_dir(session["session_id"], root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SESSION_FILENAME
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return path


def new_session(title: str = "", root: Path | None = None) -> dict:
    sid = next_session_id(root=root)
    return {
        "session_id": sid,
        "title": title or "Untitled session",
        "started_at": now_iso(),
        "ended_at": None,
        "summary": "",
        "entries": [],
    }


def normalize_entry(raw: dict) -> dict:
    """Coerce a loosely-shaped entry dict into the canonical entry shape."""
    entry = {
        "timestamp": raw.get("timestamp") or now_iso(),
        "summary": (raw.get("summary") or "").strip(),
        "detail": (raw.get("detail") or "").strip(),
        "status": raw.get("status") or "done",
    }
    if not entry["summary"]:
        raise WorkLogError("Every entry needs a --summary.")
    for field in LIST_FIELDS:
        value = raw.get(field) or []
        if isinstance(value, str):
            value = [value]
        entry[field] = [str(v).strip() for v in value if str(v).strip()]
    return entry


def collect_sessions(session_ids: list[str], root: Path | None = None) -> list[dict]:
    sessions = []
    for sid in session_ids:
        try:
            sessions.append(load_session(sid, root))
        except WorkLogError:
            continue
    return sessions


def unreported_session_ids(root: Path | None = None) -> list[str]:
    """Sessions that exist on disk but have not been included in a sent report.

    This is what makes "end of day" work: the report covers everything since
    the last one went out, regardless of how many sessions that spans.
    """
    state = load_state(root)
    reported = set(state.get("reported_sessions") or [])
    return [sid for sid in list_session_ids(root) if sid not in reported]


def aggregate(sessions: list[dict]) -> dict:
    """Roll a list of sessions up into the numbers the report header shows."""
    totals: dict[str, list[str]] = {field: [] for field in LIST_FIELDS}
    entry_count = 0
    for session in sessions:
        for entry in session.get("entries", []):
            entry_count += 1
            for field in LIST_FIELDS:
                for item in entry.get(field, []):
                    if item not in totals[field]:
                        totals[field].append(item)

    starts = [parse_iso(s.get("started_at")) for s in sessions]
    ends = [parse_iso(s.get("ended_at") or s.get("started_at")) for s in sessions]
    starts = [d for d in starts if d]
    ends = [d for d in ends if d]

    return {
        "session_count": len(sessions),
        "entry_count": entry_count,
        "totals": totals,
        "first_start": min(starts) if starts else None,
        "last_end": max(ends) if ends else None,
    }


def date_range_label(agg: dict) -> str:
    start, end = agg.get("first_start"), agg.get("last_end")
    if not start:
        return "No dated activity"
    # No "%-d": that modifier is glibc-only and raises ValueError on Windows.
    if not end or start.date() == end.date():
        return f"{start:%A, %B} {start.day}, {start.year}"
    return f"{start:%b} {start.day} - {end:%b} {end.day}, {end.year}"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
