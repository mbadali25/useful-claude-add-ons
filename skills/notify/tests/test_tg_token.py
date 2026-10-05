"""A bot token with whitespace around or inside it (setx, a paste, a file
with a trailing newline) must neither break a send nor appear in an error.

2026-10-05: a trailing space reached the API URL, and urllib's InvalidURL
message - which quotes the path, token included - escaped tg.api uncaught,
so notify.py's broad except printed the token.
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)

import tg  # noqa: E402  pylint: disable=wrong-import-position


class TokenFromEnv(unittest.TestCase):
    def test_surrounding_whitespace_is_stripped(self):
        for raw in ("123456:ABC \r\n", "  123456:ABC", "\t123456:ABC\n"):
            with mock.patch.dict(os.environ, {"TOK": raw}):
                self.assertEqual(tg.token_from_env("TOK"), "123456:ABC")

    def test_blank_or_unset_is_none(self):
        with mock.patch.dict(os.environ, {"TOK": " \r\n"}):
            self.assertIsNone(tg.token_from_env("TOK"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(tg.token_from_env("TOK"))


class ApiNeverQuotesTheToken(unittest.TestCase):
    def test_a_token_urllib_refuses_is_a_tgerror_without_the_token(self):
        for bad in ("123456:SECRET TOK", "123456:SECRET\r\nTOK"):
            with self.assertRaises(tg.TgError) as caught:
                tg.api(bad, "getMe", retries=0)
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertIn("not usable in a URL", str(caught.exception))


class GetChatIdHelper(unittest.TestCase):
    def test_an_inner_space_is_refused_before_any_request(self):
        env = dict(os.environ, TELEGRAM_BOT_TOKEN="123456:SECRET TOK")
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "telegram_get_chat_id.py")],
                              env=env, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(done.returncode, 2)
        self.assertNotIn("SECRET", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
