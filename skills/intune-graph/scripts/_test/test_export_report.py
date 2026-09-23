#!/usr/bin/env python3
"""Regression tests for export_report.py's `_download` / `_stage_write`.

Covers two shapes of the CLAUDE.md landmine "`open(p, 'w')` truncates at
open time":

1. A corrupt zip *member* (src.read() raises) used to leave a zero-byte file
   or clobber a pre-existing one, because `open(dest, "wb")` truncated
   before the read that could fail.
2. A *write* failure (ENOSPC/EIO/quota - write() raises after open(dest,
   "wb") already truncated) destroyed a prior good file even though the
   read succeeded. Fixed by writing to a temp file in the same directory and
   `os.replace`-ing onto dest.

Also covers:
- Multi-member all-or-nothing, for BOTH failure shapes: a corrupt/failing
  member N (whether its read or its write fails) must not leave members
  1..N-1 already replaced on disk while N.. are stale or missing.
- Mode preservation: `os.replace` installs whatever mode the temp file from
  `mkstemp` had (0600), so without correcting it every export would come out
  owner-only regardless of what was there before. Covers a fresh file
  (follows umask) and a pre-existing file (keeps its mode).
- Refusing to write through a symlinked dest, rather than silently replacing
  it (breaking the link) or silently following it (writing to a location
  `out_dir`'s caller never named).
- The fsync-before-replace ordering, pinned by recording the actual
  `os.fsync`/`os.replace` calls - nothing about file *contents* in this test
  environment distinguishes that order from "replace first" or "no fsync at
  all", so an outcome-based test could not catch a regression here.

No network: `requests.get` is monkeypatched to return locally-built zip
bytes. No credentials are read. Run with:

    python3 -B skills/intune-graph/scripts/_test/test_export_report.py
"""
import errno
import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SCRIPTS_DIR)

import export_report  # noqa: E402  (path must be set up first)


def _build_zip(member_name="report.csv", payload=b"DeviceName,OS\nabc123,Windows\n",
                corrupt=False):
    """A single ZIP_STORED member, optionally with one payload byte flipped so
    the CRC-32 check fails on read while the central directory stays intact
    (ZipFile() and namelist() still succeed)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr(member_name, payload)
    raw = bytearray(buf.getvalue())

    if corrupt:
        raw = _flip_member_byte(raw, member_name)

    return bytes(raw)


def _build_multi_zip(members, corrupt_name=None):
    """`members` is [(name, payload), ...], ZIP_STORED. If `corrupt_name` is
    given, that member's payload byte is flipped after the zip is built, same
    as `_build_zip(corrupt=True)`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, payload in members:
            z.writestr(name, payload)
    raw = bytearray(buf.getvalue())

    if corrupt_name is not None:
        raw = _flip_member_byte(raw, corrupt_name)

    return bytes(raw)


def _flip_member_byte(raw, member_name):
    """Locate `member_name`'s local file header and flip one payload byte."""
    sig = b"PK\x03\x04"
    search_from = 0
    while True:
        idx = raw.index(sig, search_from)
        name_len = int.from_bytes(raw[idx + 26:idx + 28], "little")
        extra_len = int.from_bytes(raw[idx + 28:idx + 30], "little")
        name_start = idx + 30
        name = bytes(raw[name_start:name_start + name_len]).decode()
        data_start = name_start + name_len + extra_len
        if name == member_name:
            raw[data_start] ^= 0xFF
            return raw
        search_from = data_start


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class _ENOSPCFile:
    """Wraps a real file object opened via os.fdopen, but fails on write() -
    simulating a full disk / quota / EIO partway through `_atomic_write`."""

    def __init__(self, real):
        self._real = real

    def write(self, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    def flush(self):
        pass

    def fileno(self):
        return self._real.fileno()

    def close(self):
        self._real.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def _leftover_temp_files(out_dir):
    return [n for n in os.listdir(out_dir) if n.startswith(".export-report-tmp-")]


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self._real_get = export_report.requests.get
        self.addCleanup(self._restore_get)

    def _restore_get(self):
        export_report.requests.get = self._real_get

    def _patch_get(self, content):
        export_report.requests.get = lambda url, timeout=300: _FakeResponse(content)

    # -- corrupt member (read failure) --------------------------------

    def test_corrupt_member_raises_and_leaves_no_zero_byte_file(self):
        self._patch_get(_build_zip(corrupt=True))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(zipfile.BadZipFile):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            entries = os.listdir(tmp)
            self.assertNotIn(
                "report.csv", entries,
                "a corrupt member must not leave a zero-byte (or any) file at dest "
                "when there was nothing there before",
            )

    def test_corrupt_member_preserves_preexisting_file(self):
        self._patch_get(_build_zip(corrupt=True))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "report.csv")
            original = b"previous,export\n1,2\n"
            with open(dest, "wb") as f:
                f.write(original)

            with self.assertRaises(zipfile.BadZipFile):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            with open(dest, "rb") as f:
                self.assertEqual(
                    f.read(), original,
                    "a corrupt member must not truncate/clobber a file that "
                    "already existed at dest",
                )

    def test_valid_zip_still_extracts_normally(self):
        payload = b"DeviceName,OS\nabc123,Windows\n"
        self._patch_get(_build_zip(payload=payload, corrupt=False))
        with tempfile.TemporaryDirectory() as tmp:
            written = export_report._download("https://fake.example/blob", "TestReport", tmp)
            self.assertEqual(len(written), 1)
            with open(written[0], "rb") as f:
                self.assertEqual(f.read(), payload)

    # -- write failure (ENOSPC after open(dest, "wb") would have truncated) --

    def test_write_failure_preserves_preexisting_file(self):
        self._patch_get(_build_zip(corrupt=False))
        real_fdopen = os.fdopen

        # Keeps os.fdopen's own (fd, mode, *args) order so positional mode still works.
        def failing_fdopen(fd, mode="r", *a, **kw):  # pylint: disable=keyword-arg-before-vararg
            return _ENOSPCFile(real_fdopen(fd, mode))

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "report.csv")
            original = b"previous,good,export\n1,2,3\n"
            with open(dest, "wb") as f:
                f.write(original)

            with mock.patch("os.fdopen", side_effect=failing_fdopen):
                with self.assertRaises(OSError):
                    export_report._download("https://fake.example/blob", "TestReport", tmp)

            with open(dest, "rb") as f:
                self.assertEqual(
                    f.read(), original,
                    "a write failure (ENOSPC) must not destroy the prior good "
                    "file at dest - the old bug truncated it to 0 bytes",
                )
            self.assertEqual(
                _leftover_temp_files(tmp), [],
                "a failed write must clean up its temp file",
            )

    # -- multi-member all-or-nothing -----------------------------------

    def test_multi_member_corrupt_second_leaves_first_unwritten(self):
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        self._patch_get(_build_multi_zip(
            [("a.csv", payload_a), ("b.csv", payload_b)], corrupt_name="b.csv",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(zipfile.BadZipFile):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            entries = os.listdir(tmp)
            self.assertNotIn(
                "a.csv", entries,
                "member a.csv must not be written when a later member (b.csv) "
                "is corrupt - all-or-nothing, no mixed generations in out_dir",
            )
            self.assertNotIn("b.csv", entries)

    def test_multi_member_corrupt_second_preserves_first_preexisting_file(self):
        payload_a_old = b"a,csv,old\n1,2,3\n"
        payload_a_new = b"a,csv,new\n9,9,9\n"
        payload_b = b"b,csv\n3,4\n"
        self._patch_get(_build_multi_zip(
            [("a.csv", payload_a_new), ("b.csv", payload_b)], corrupt_name="b.csv",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            dest_a = os.path.join(tmp, "a.csv")
            with open(dest_a, "wb") as f:
                f.write(payload_a_old)

            with self.assertRaises(zipfile.BadZipFile):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            with open(dest_a, "rb") as f:
                self.assertEqual(
                    f.read(), payload_a_old,
                    "a.csv from a previous run must survive a later member "
                    "(b.csv) being corrupt in this run",
                )

    def test_multi_member_valid_writes_all(self):
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        self._patch_get(_build_multi_zip([("a.csv", payload_a), ("b.csv", payload_b)]))
        with tempfile.TemporaryDirectory() as tmp:
            written = export_report._download("https://fake.example/blob", "TestReport", tmp)
            self.assertEqual(len(written), 2)
            with open(os.path.join(tmp, "a.csv"), "rb") as f:
                self.assertEqual(f.read(), payload_a)
            with open(os.path.join(tmp, "b.csv"), "rb") as f:
                self.assertEqual(f.read(), payload_b)

    def test_multi_member_write_failure_leaves_first_unwritten(self):
        """The read-only all-or-nothing test above does not cover this: a
        WRITE failure on member 2 (not a corrupt read) must also not leave
        member 1 already installed. Requires staging every member before
        committing any of them."""
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        self._patch_get(_build_multi_zip([("a.csv", payload_a), ("b.csv", payload_b)]))
        real_fdopen = os.fdopen
        call_count = {"n": 0}

        # Keeps os.fdopen's own (fd, mode, *args) order so positional mode still works.
        def fail_on_second_fdopen(fd, mode="r", *a, **kw):  # pylint: disable=keyword-arg-before-vararg
            call_count["n"] += 1
            if call_count["n"] == 2:
                return _ENOSPCFile(real_fdopen(fd, mode))
            return real_fdopen(fd, mode, *a, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("os.fdopen", side_effect=fail_on_second_fdopen):
                with self.assertRaises(OSError):
                    export_report._download("https://fake.example/blob", "TestReport", tmp)

            entries = os.listdir(tmp)
            self.assertNotIn(
                "a.csv", entries,
                "member a.csv must not be installed when a later member's "
                "WRITE (not just its read) fails - all-or-nothing must cover "
                "writes too, not only reads",
            )
            self.assertNotIn("b.csv", entries)
            self.assertEqual(
                _leftover_temp_files(tmp), [],
                "a.csv's successfully-staged temp file must be cleaned up "
                "when b.csv's staging fails",
            )

    # -- mode preservation (mkstemp defaults to 0600) --------------------

    def test_fresh_file_mode_respects_umask(self):
        """umask 0o027, not the more common 0o022: 0o666 & ~0o022 == 0o644,
        which is indistinguishable from a hard-coded "always chmod 0o644"
        bug - that bug would pass a 0o022 test by coincidence. 0o666 &
        ~0o027 == 0o640, which a hard-coded 0o644 gets wrong, so this
        actually proves the umask is being read rather than assumed."""
        payload = b"a,csv\n1,2\n"
        self._patch_get(_build_zip(payload=payload, corrupt=False))
        old_umask = os.umask(0o027)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                written = export_report._download("https://fake.example/blob", "TestReport", tmp)
                mode = os.stat(written[0]).st_mode & 0o777
                self.assertEqual(
                    mode, 0o640,
                    f"a fresh file should get 0o666 & ~umask(0o027) == 0o640, "
                    f"got {oct(mode)} - mkstemp's 0600 must not leak through, "
                    f"and a hard-coded 0o644 must not pass this either",
                )
        finally:
            os.umask(old_umask)

    def test_preexisting_file_mode_is_preserved(self):
        payload_old = b"old,export\n1,2\n"
        payload_new = b"new,export\n9,9\n"
        self._patch_get(_build_zip(payload=payload_new, corrupt=False))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "report.csv")
            with open(dest, "wb") as f:
                f.write(payload_old)
            os.chmod(dest, 0o664)

            export_report._download("https://fake.example/blob", "TestReport", tmp)

            mode = os.stat(dest).st_mode & 0o777
            self.assertEqual(
                mode, 0o664,
                f"replacing an existing export must preserve its mode, got "
                f"{oct(mode)} - mkstemp's 0600 must not reset it",
            )
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), payload_new)

    # -- symlinked dest: refuse loudly ------------------------------------

    def test_symlinked_dest_refuses_loudly_and_leaves_target_untouched(self):
        payload = b"a,csv\n1,2\n"
        self._patch_get(_build_zip(member_name="report.csv", payload=payload, corrupt=False))
        with tempfile.TemporaryDirectory() as tmp:
            real_target = os.path.join(tmp, "elsewhere.csv")
            original = b"do not touch me\n"
            with open(real_target, "wb") as f:
                f.write(original)

            dest = os.path.join(tmp, "report.csv")
            os.symlink(real_target, dest)

            with self.assertRaises(OSError):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            self.assertTrue(os.path.islink(dest), "the symlink at dest must survive a refusal")
            self.assertEqual(os.readlink(dest), real_target)
            with open(real_target, "rb") as f:
                self.assertEqual(
                    f.read(), original,
                    "refusing to write through a symlink must not touch its "
                    "target either - not just leave the symlink itself alone",
                )
            self.assertEqual(
                _leftover_temp_files(tmp), [],
                "the symlink check must happen before any temp file is created",
            )

    # -- write, then fsync, then replace - full order pinned --------------

    def test_write_fsync_replace_order(self):
        """Pins the FULL write order, not just fsync-before-replace: nothing
        about file *contents* distinguishes "fsync then write" (fsyncing
        nothing) or "replace then fsync" or "no fsync at all" from the
        correct order in this test environment, so this records the actual
        call sequence via mock rather than checking an outcome - an
        outcome-based test would still pass with any of those reordered or
        dropped."""
        self._patch_get(_build_zip(corrupt=False))
        calls = []
        real_fdopen = os.fdopen
        real_fsync = os.fsync
        real_replace = os.replace

        class _RecordingFile:
            def __init__(self, real):
                self._real = real

            def write(self, data):
                calls.append("write")
                return self._real.write(data)

            def flush(self):
                return self._real.flush()

            def fileno(self):
                return self._real.fileno()

            def close(self):
                return self._real.close()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.close()
                return False

        # Keeps os.fdopen's own (fd, mode, *args) order so positional mode still works.
        def record_fdopen(fd, mode="r", *a, **kw):  # pylint: disable=keyword-arg-before-vararg
            return _RecordingFile(real_fdopen(fd, mode))

        def record_fsync(fd):
            calls.append("fsync")
            return real_fsync(fd)

        def record_replace(src, dst):
            calls.append("replace")
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("os.fdopen", side_effect=record_fdopen), \
                    mock.patch("os.fsync", side_effect=record_fsync), \
                    mock.patch("os.replace", side_effect=record_replace):
                export_report._download("https://fake.example/blob", "TestReport", tmp)

        self.assertEqual(
            calls, ["write", "fsync", "replace"],
            f"expected write -> fsync -> replace in that exact order, got {calls}",
        )

    # -- zip directory entries must be skipped -----------------------------

    def test_directory_entry_in_zip_is_skipped(self):
        payload = b"a,csv\n1,2\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            z.writestr("subdir/", b"")
            z.writestr("a.csv", payload)
        self._patch_get(buf.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            written = export_report._download("https://fake.example/blob", "TestReport", tmp)
            self.assertEqual(written, [os.path.join(tmp, "a.csv")])
            with open(os.path.join(tmp, "a.csv"), "rb") as f:
                self.assertEqual(f.read(), payload)
            entries = sorted(os.listdir(tmp))
            self.assertEqual(
                entries, ["a.csv"],
                f"a directory entry in the zip must not produce a stray file "
                f"or attempt to replace out_dir itself, got {entries}",
            )

    def test_directory_named_member_with_data_raises_instead_of_dropping(self):
        """A member named like a directory ("report.csv/") but carrying real
        bytes is NOT a genuine directory entry - the (correct) skip for
        empty directory entries must not silently discard it too. Put it
        FIRST in the zip so the check has to fire before anything else in
        the zip is even read, let alone staged."""
        weird_name = "report.csv/"
        weird_payload = b"this is actually data, not an empty directory\n"
        good_payload = b"a,csv\n1,2\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            z.writestr(weird_name, weird_payload)
            z.writestr("a.csv", good_payload)
        self._patch_get(buf.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                export_report._download("https://fake.example/blob", "TestReport", tmp)

            self.assertIn(
                weird_name, str(ctx.exception),
                "must name the offending member, not a bare error",
            )
            entries = os.listdir(tmp)
            self.assertEqual(
                entries, [],
                f"nothing should be written - the error must fire before "
                f"anything is staged, got {entries}",
            )

    # -- commit-loop failure (os.replace raises partway) -------------------

    def test_commit_failure_reports_replaced_and_stale_files(self):
        """The reviewer's exact Windows case: os.replace raises
        PermissionError on member 2 (an export CSV open in Excel). member 1
        must already be the new version; members 2 and 3 must stay at their
        OLD version; the raised message must name all three groups instead
        of a bare traceback."""
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        payload_c = b"c,csv\n5,6\n"
        self._patch_get(_build_multi_zip([
            ("a.csv", payload_a), ("b.csv", payload_b), ("c.csv", payload_c),
        ]))
        real_replace = os.replace
        call_count = {"n": 0}

        def fail_on_second_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise PermissionError(13, "Permission denied")
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmp:
            dest_b = os.path.join(tmp, "b.csv")
            old_b = b"old,b\n0,0\n"
            with open(dest_b, "wb") as f:
                f.write(old_b)
            dest_c = os.path.join(tmp, "c.csv")
            old_c = b"old,c\n0,0\n"
            with open(dest_c, "wb") as f:
                f.write(old_c)

            with mock.patch("os.replace", side_effect=fail_on_second_replace):
                with self.assertRaises(OSError) as ctx:
                    export_report._download("https://fake.example/blob", "TestReport", tmp)

            message = str(ctx.exception)
            dest_a = os.path.join(tmp, "a.csv")
            self.assertIn(dest_a, message, "must name the file(s) already replaced")
            self.assertIn(dest_b, message, "must name the file that failed to replace")
            self.assertIn(dest_c, message, "must name the file(s) left at their old version")

            with open(dest_a, "rb") as f:
                self.assertEqual(f.read(), payload_a, "a.csv (member 1) must be the NEW version")
            with open(dest_b, "rb") as f:
                self.assertEqual(f.read(), old_b, "b.csv must stay at its OLD version - its replace failed")
            with open(dest_c, "rb") as f:
                self.assertEqual(f.read(), old_c, "c.csv must stay at its OLD version - never attempted")

    def test_main_reports_os_error_cleanly_and_exits_nonzero(self):
        """main() previously caught only (GraphError, AuthError) - an
        OSError from _download's commit loop (or anywhere else run_export
        can raise from) must get the same clean "print message, exit 1"
        treatment, not a raw traceback reaching the terminal."""

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

        def fake_run_export(*a, **kw):
            raise OSError("export partially committed - simulated for this test")

        argv = ["export_report.py", "--report", "Devices"]
        stderr = io.StringIO()
        with mock.patch("sys.argv", argv), \
                mock.patch.object(export_report, "GraphClient", _FakeClient), \
                mock.patch.object(export_report, "run_export", fake_run_export), \
                mock.patch("sys.stderr", stderr):
            with self.assertRaises(SystemExit) as ctx:
                export_report.main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("export partially committed", stderr.getvalue())

    # -- cleanup after a commit or staging failure --------------------------

    def test_cleanup_failure_does_not_mask_original_exception(self):
        """If os.unlink itself fails while cleaning up a staged temp file
        (e.g. a locked/read-only temp on Windows), that must not replace
        whatever exception is already propagating - here, the corrupt-member
        read failure."""
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        self._patch_get(_build_multi_zip(
            [("a.csv", payload_a), ("b.csv", payload_b)], corrupt_name="b.csv",
        ))

        def failing_unlink(path):
            raise PermissionError(13, "Permission denied (read-only temp)")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("os.unlink", side_effect=failing_unlink):
                with self.assertRaises(zipfile.BadZipFile):
                    export_report._download("https://fake.example/blob", "TestReport", tmp)

            # a.csv's staged temp file is still there - cleanup failed, but
            # that must not have crashed or masked the BadZipFile above.
            leftover = _leftover_temp_files(tmp)
            self.assertEqual(
                len(leftover), 1,
                f"expected exactly a.csv's staged temp left behind, got {leftover}",
            )

    def test_cleanup_keeps_going_after_one_unlink_failure(self):
        payload_a = b"a,csv\n1,2\n"
        payload_b = b"b,csv\n3,4\n"
        payload_c = b"c,csv\n5,6\n"
        self._patch_get(_build_multi_zip(
            [("a.csv", payload_a), ("b.csv", payload_b), ("c.csv", payload_c)],
            corrupt_name="c.csv",
        ))
        real_unlink = os.unlink
        calls = {"n": 0}

        def fail_first_then_real(path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError(13, "Permission denied (read-only temp)")
            return real_unlink(path)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("os.unlink", side_effect=fail_first_then_real):
                with self.assertRaises(zipfile.BadZipFile):
                    export_report._download("https://fake.example/blob", "TestReport", tmp)

            self.assertEqual(
                calls["n"], 2,
                "both staged temp files (a.csv, b.csv) must get a cleanup "
                "attempt - one unlink failure must not stop the loop",
            )
            leftover = _leftover_temp_files(tmp)
            self.assertEqual(
                len(leftover), 1,
                f"exactly one temp should survive (the one whose unlink was "
                f"sabotaged), got {leftover}",
            )


if __name__ == "__main__":
    unittest.main()
