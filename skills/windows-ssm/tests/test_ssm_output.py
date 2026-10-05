"""Tests for skills/windows-ssm/scripts/ssm_output.py (T-0102).

The helper reads one `aws ssm get-command-invocation` result and says whether
the returned text is the whole output. Only "complete" exits 0: output at or
over a limit is "truncated" (exit 3), and anything it cannot judge is "could
not tell" (exit 4). It never prints the content it inspects.

    python -m pytest skills/windows-ssm/tests/ -q
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPT = os.path.join(SKILL, "scripts", "ssm_output.py")
LIMITS = os.path.join(SKILL, "references", "ssm-limits.md")

SENTINEL = "SENTINEL-c0ffee-do-not-echo"


def invocation(stdout="hello\n", stderr="", status="Success", **extra):
    doc = {
        "CommandId": "1a2b3c4d-1a2b-1a2b-1a2b-1a2b3c4d5e6f",
        "InstanceId": "i-02573cafcfEXAMPLE",
        "PluginName": "aws:runPowerShellScript",
        "ResponseCode": 0 if status == "Success" else 1,
        "Status": status,
        "StatusDetails": status,
        "StandardOutputContent": stdout,
        "StandardOutputUrl": "",
        "StandardErrorContent": stderr,
        "StandardErrorUrl": "",
    }
    doc.update(extra)
    return doc


def run(payload, via_stdin=False):
    """Run the helper on `payload` (a dict, or raw text) and return the result."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if via_stdin:
        return subprocess.run([sys.executable, SCRIPT], input=text, capture_output=True,
                              text=True, encoding="utf-8", check=False)
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return subprocess.run([sys.executable, SCRIPT, path], capture_output=True,
                              text=True, encoding="utf-8", check=False)
    finally:
        os.unlink(path)


class TestComplete(unittest.TestCase):
    def test_short_output_is_complete(self):
        for status in ("Success", "Failed"):
            r = run(invocation(stdout="ok\n" * 10, stderr="warn\n", status=status))
            self.assertEqual(r.returncode, 0, (status, r.stdout, r.stderr))
            self.assertEqual(r.stdout.splitlines()[0], "complete")

    def test_reads_stdin_when_no_path_is_given(self):
        r = run(invocation(), via_stdin=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "complete")

    def test_reads_utf16_written_by_windows_powershell(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(json.dumps(invocation()).encode("utf-16"))  # BOM included
            r = subprocess.run([sys.executable, SCRIPT, path], capture_output=True,
                               text=True, check=False)
        finally:
            os.unlink(path)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_one_under_the_limit_is_complete(self):
        r = run(invocation(stdout="a" * 23999, stderr="b" * 7999))
        self.assertEqual(r.returncode, 0, r.stderr)


class TestTruncated(unittest.TestCase):
    def assert_truncated(self, r, needle):
        self.assertEqual(r.returncode, 3, (r.stdout, r.stderr))
        self.assertEqual(r.stdout.splitlines()[0], "truncated")
        self.assertIn(needle, r.stderr)

    def test_stdout_at_the_limit_is_truncated(self):
        self.assert_truncated(run(invocation(stdout="a" * 24000)), "stdout")

    def test_stdout_over_the_limit_in_bytes_only_is_truncated(self):
        text = "é" * 12001  # 12,001 characters, 24,002 UTF-8 bytes
        self.assertLess(len(text), 24000)
        self.assert_truncated(run(invocation(stdout=text)), "bytes")

    def test_stderr_at_the_limit_is_truncated(self):
        self.assert_truncated(run(invocation(stderr="e" * 8000)), "stderr")

    def test_truncated_beats_a_non_terminal_status(self):
        # A cut is known even while the command is still running.
        self.assert_truncated(run(invocation(stdout="a" * 24000, status="InProgress")), "stdout")

    def test_truncated_output_names_the_s3_url(self):
        url = "https://s3.us-east-2.amazonaws.com/amzn-s3-demo-bucket/prefix/stdout"
        r = run(invocation(stdout="a" * 24000, StandardOutputUrl=url))
        self.assert_truncated(r, url)

    def test_truncated_without_a_url_says_how_to_get_the_full_text(self):
        r = run(invocation(stdout="a" * 24000))
        self.assert_truncated(r, "--output-s3-bucket-name")


class TestCouldNotTell(unittest.TestCase):
    def assert_unknown(self, r, needle):
        self.assertEqual(r.returncode, 4, (r.stdout, r.stderr))
        self.assertEqual(r.stdout.splitlines()[0], "could not tell")
        self.assertIn(needle, r.stderr)

    def test_non_terminal_status_could_not_tell(self):
        for status in ("Pending", "InProgress", "Delayed", "Cancelling"):
            with self.subTest(status=status):
                self.assert_unknown(run(invocation(status=status)), status)

    def test_timed_out_or_cancelled_could_not_tell(self):
        for status in ("TimedOut", "Cancelled"):
            with self.subTest(status=status):
                self.assert_unknown(run(invocation(status=status)), status)

    def test_unknown_or_missing_status_could_not_tell(self):
        self.assert_unknown(run(invocation(status="Exploded")), "Exploded")
        doc = invocation()
        del doc["Status"]
        self.assert_unknown(run(doc), "Status")

    def test_missing_identity_could_not_tell(self):
        for key in ("CommandId", "InstanceId"):
            with self.subTest(key=key):
                doc = invocation()
                del doc[key]
                self.assert_unknown(run(doc), key)
        bare = {"StandardOutputContent": "", "StandardErrorContent": "", "Status": "Success"}
        self.assert_unknown(run(bare), "CommandId")

    def test_not_json_could_not_tell(self):
        self.assert_unknown(run("this is not json {"), "JSON")

    def test_json_that_is_not_an_object_could_not_tell(self):
        self.assert_unknown(run("[1, 2, 3]"), "object")

    def test_missing_stdout_key_could_not_tell(self):
        doc = invocation()
        del doc["StandardOutputContent"]
        self.assert_unknown(run(doc), "StandardOutputContent")

    def test_missing_stderr_key_could_not_tell(self):
        doc = invocation()
        del doc["StandardErrorContent"]
        self.assert_unknown(run(doc), "StandardErrorContent")

    def test_non_string_content_could_not_tell(self):
        self.assert_unknown(run(invocation(stdout=None)), "StandardOutputContent")

    def test_empty_file_could_not_tell(self):
        self.assert_unknown(run(""), "empty")

    def test_missing_file_could_not_tell(self):
        r = subprocess.run([sys.executable, SCRIPT, os.path.join(HERE, "no-such-file.json")],
                           capture_output=True, text=True, check=False)
        self.assert_unknown(r, "no-such-file.json")


class TestNeverEchoes(unittest.TestCase):
    def test_content_is_never_echoed(self):
        cases = (
            invocation(stdout=SENTINEL + "\n"),
            invocation(stdout=SENTINEL * 2000),
            invocation(stderr=SENTINEL * 1000),
            invocation(stdout=SENTINEL, status="Pending"),
        )
        for doc in cases:
            r = run(doc)
            self.assertNotIn(SENTINEL, r.stdout)
            self.assertNotIn(SENTINEL, r.stderr)


class TestLimitsReference(unittest.TestCase):
    def test_every_limit_row_cites_a_source(self):
        with open(LIMITS, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        rows = [ln for ln in lines if ln.startswith("|") and not re.match(r"^\|[\s|:-]+\|$", ln)]
        # A row states a number when a digit is left once its links are removed.
        numbered = [ln for ln in rows if re.search(r"\d", re.sub(r"\(?https?://[^)\s]*\)?", "", ln))]
        self.assertGreaterEqual(len(numbered), 6, "expected the limits table")
        for row in numbered:
            self.assertRegex(row, r"https://(docs\.aws\.amazon\.com|learn\.microsoft\.com)/",
                             f"limit row has no AWS or Microsoft source: {row}")

    def test_the_helper_limits_match_the_reference(self):
        with open(LIMITS, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("24,000", text)
        self.assertIn("8,000", text)


if __name__ == "__main__":
    unittest.main()
