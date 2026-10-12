"""MessageStore: owner-only database file and the per-peer storage cap."""

import asyncio
import os
import stat
import sys

import test_server_harness as h  # noqa: F401  (sets sys.path)  # pylint: disable=unused-import

import pytest

from server.message_store import MessageStore


def test_db_created_owner_only(tmp_path):
    async def run():
        store = MessageStore(str(tmp_path / "sub" / "messages.db"))
        await store.connect()
        await store.close()

    asyncio.run(run())
    path = tmp_path / "sub" / "messages.db"
    assert path.exists()
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    else:
        # Windows: chmod only toggles read-only; best effort keeps it writable
        assert os.access(path, os.W_OK)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_existing_db_tightened(tmp_path):
    path = tmp_path / "messages.db"
    path.touch()
    os.chmod(path, 0o644)

    async def run():
        store = MessageStore(str(path))
        await store.connect()
        await store.close()

    asyncio.run(run())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_cap_keeps_newest_per_sender(tmp_path):
    async def run():
        store = MessageStore(str(tmp_path / "m.db"), max_stored_per_peer=3)
        await store.connect()
        for i in range(5):
            await store.store("A:x", "B:y", f"m{i}", None, delivered=False)
        await store.store("C:z", "B:y", "other", None, delivered=False)
        history = await store.get_history("A:x", "B:y", 50)
        unread = await store.get_unread("B:y")
        await store.close()
        return history, unread

    history, unread = asyncio.run(run())
    assert [m["content"] for m in history] == ["m2", "m3", "m4"]
    # Another sender's messages are untouched by A's cap
    assert "other" in [m["content"] for m in unread]


def test_cap_zero_means_unlimited(tmp_path):
    async def run():
        store = MessageStore(str(tmp_path / "m.db"), max_stored_per_peer=0)
        await store.connect()
        for i in range(5):
            await store.store("A:x", "B:y", f"m{i}", None, delivered=True)
        history = await store.get_history("A:x", "B:y", 50)
        await store.close()
        return history

    assert len(asyncio.run(run())) == 5


def test_chmod_owner_only_requested_on_every_platform(tmp_path, monkeypatch):
    calls = []
    real_chmod = os.chmod

    def spy(path, mode, *args, **kwargs):
        calls.append((str(path), mode))
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "chmod", spy)
    path = tmp_path / "messages.db"

    async def run():
        store = MessageStore(str(path))
        await store.connect()
        await store.close()

    asyncio.run(run())
    assert (str(path), 0o600) in calls
