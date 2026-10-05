"""notifyd must never post the same message twice on its own.

2026-10-05, a Windows host: notifications kept arriving with the same
heading. A request was taken off the queue only after _send returned, so an
error that was not a TgError left it on disk and ended run(); a supervisor
(nssm, Task Scheduler) restarted the daemon and it posted the request again.
Every restart also re-posted every unanswered question.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import notifyd  # noqa: E402  pylint: disable=wrong-import-position

CFG = {"telegram": {"chat_id": "-100123", "bot_token_env": "NOTIFYD_TEST_TOKEN"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"NOTIFYD_TEST_TOKEN": "123456:ABC"})
        env.start()
        self.addCleanup(env.stop)
        self.sp = notifyd.Spool(Path(self.tmp.name))
        self.d = notifyd.Dispatcher(CFG, self.sp)

    def queue(self, req_id, **extra):
        req = {"req_id": req_id, "subject": "Heading", "body": "x", **extra}
        (self.sp.requests / f"{req_id}.json").write_text(json.dumps(req))
        return req


class PoisonRequest(Base):
    def test_an_unexpected_error_takes_the_request_off_the_queue(self):
        self.queue("r1")
        with mock.patch.object(notifyd.tg, "send_message", side_effect=KeyError("boom")) as send:
            self.d.process_requests()   # must not raise
            self.d.process_requests()   # and must not send it again
        self.assertEqual(send.call_count, 1)
        self.assertEqual(list(self.sp.requests.glob("*.json")), [])
        answer = json.loads((self.sp.answers / "r1.json").read_text())
        self.assertIsNone(answer["reply"])
        self.assertEqual(answer["error"], "KeyError")


class RestartDoesNotRepost(Base):
    def _sent_question(self):
        self.queue("q1", want_reply=True, buttons=["Yes", "No"])
        with mock.patch.object(notifyd.tg, "send_message", return_value={"message_id": 42}):
            self.d.process_requests()

    def test_a_question_already_sent_is_waited_on_not_posted_again(self):
        self._sent_question()
        again = notifyd.Dispatcher(CFG, self.sp)
        with mock.patch.object(notifyd.tg, "send_message") as send:
            again.resume_active()
        send.assert_not_called()
        self.assertIn("q1", again.pending)
        self.assertEqual(again.msg_index.get(42), "q1")
        self.assertTrue((self.sp.active / "q1.json").exists())

    def test_an_old_format_record_is_sent_once_even_if_the_send_fails(self):
        (self.sp.active / "q2.json").write_text(json.dumps(
            {"req_id": "q2", "subject": "Heading", "body": "x", "want_reply": True}))
        with mock.patch.object(notifyd.tg, "send_message", side_effect=KeyError("boom")) as send:
            self.d.resume_active()
            notifyd.Dispatcher(CFG, self.sp).resume_active()
        self.assertEqual(send.call_count, 1)

    def test_a_malformed_record_costs_that_record_not_the_start(self):
        (self.sp.active / "bad.json").write_text(json.dumps({"subject": "no req_id",
                                                             "_sent": {"message_id": 7}}))
        (self.sp.active / "junk.json").write_text("{not json")
        self.d.resume_active()   # must not raise
        self.assertEqual(sorted(p.name for p in self.sp.active.glob("*.json")), [])


class TgReplyNotUtf8(unittest.TestCase):
    def test_a_reply_that_is_not_utf8_is_not_blamed_on_the_token(self):
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"\xff\xfe<html>"
        with mock.patch.object(notifyd.tg.urllib.request, "urlopen", return_value=Reply()):
            with self.assertRaises(notifyd.tg.TgError) as caught:
                notifyd.tg.api("123456:ABC", "getMe", retries=0)
        self.assertIn("not JSON", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
