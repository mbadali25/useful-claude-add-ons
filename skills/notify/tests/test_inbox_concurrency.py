"""Concurrency tests for the notify inbox.

read() and _trim() both do read-all -> filter -> os.replace. An append landing
between the read and the replace is in neither list, so the replace destroys it -
silently, and precisely the message loss inbox.py exists to prevent.

These tests are written to FAIL if the lock is removed. Verified by removing it:
4 of 240 messages lost, plus a PermissionError on Windows where os.replace hit a
file another thread still had open.

    python -m pytest skills/notify/tests/ -q
"""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))

import inbox  # noqa: E402  pylint: disable=wrong-import-position


class TestInboxConcurrency(unittest.TestCase):
    """Every appended message must survive a concurrent consuming read."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_no_message_is_lost_under_concurrent_read(self):
        writers, per_writer = 4, 60
        total = writers * per_writer
        consumed = []
        stop = threading.Event()
        errors = []

        def write(worker):
            try:
                for i in range(per_writer):
                    inbox.append(self.root, {"job": "default",
                                             "text": f"w{worker}-{i}"})
            except Exception as exc:      # pylint: disable=broad-except
                errors.append(exc)

        def consume():
            while not stop.is_set():
                try:
                    consumed.extend(inbox.read(self.root, job="default"))
                except Exception as exc:  # pylint: disable=broad-except
                    errors.append(exc)
                time.sleep(0.001)

        reader = threading.Thread(target=consume)
        reader.start()
        threads = [threading.Thread(target=write, args=(w,))
                   for w in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        time.sleep(0.3)
        stop.set()
        reader.join()
        consumed.extend(inbox.read(self.root, job="default"))

        self.assertEqual(errors, [], f"threads raised: {errors[:3]}")
        seen = {entry["text"] for entry in consumed}
        self.assertEqual(len(seen), total,
                         f"{total - len(seen)} message(s) lost to the race")

    def test_a_peek_does_not_consume(self):
        inbox.append(self.root, {"job": "default", "text": "one"})
        self.assertEqual(len(inbox.read(self.root, job="default", peek=True)), 1)
        self.assertEqual(len(inbox.read(self.root, job="default", peek=True)), 1)
        self.assertEqual(len(inbox.read(self.root, job="default")), 1)
        self.assertEqual(inbox.read(self.root, job="default"), [])

    def test_a_stale_lock_is_broken_rather_than_wedging(self):
        """A holder killed mid-write must not block the inbox forever."""
        lock = os.path.join(self.root, inbox.LOCK_NAME)
        with open(lock, "w", encoding="utf-8") as handle:
            handle.write("999999 0\n")
        old = time.time() - (inbox.LOCK_STALE_SECONDS + 5)
        os.utime(lock, (old, old))

        inbox.append(self.root, {"job": "default", "text": "after a stale lock"})
        self.assertEqual(len(inbox.read(self.root, job="default")), 1)

    def test_a_fresh_lock_is_respected(self):
        """The lock has to actually exclude, or none of the above means much."""
        lock = os.path.join(self.root, inbox.LOCK_NAME)
        with open(lock, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()} {int(time.time())}\n")
        inbox.LOCK_TIMEOUT_SECONDS, saved = 0.2, inbox.LOCK_TIMEOUT_SECONDS
        try:
            with self.assertRaises(inbox.InboxLocked):
                inbox.append(self.root, {"job": "default", "text": "blocked"})
        finally:
            inbox.LOCK_TIMEOUT_SECONDS = saved
            os.unlink(lock)


if __name__ == "__main__":
    unittest.main()
