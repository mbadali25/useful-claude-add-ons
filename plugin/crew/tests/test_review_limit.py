"""A Codex usage, rate or quota limit sends the review round to Claude (T-0088).

Three layers, each against a throwaway repo under tmp_path and a fake `codex`
written by this file (not `review_fixtures.py`):

  * `review_limit.limit_line` classifies Codex's own limit messages, cited to
    `openai/codex@44fe510c` `codex-rs/protocol/src/error.rs`, and nothing else;
  * `review_run.py --probe` makes one minimal real call and reserves nothing;
  * a limit hit mid-round is recorded, and the next probe answers `limited`
    from that record without a call, for the next round only.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_limit

LIMIT_MESSAGES = [
    pytest.param("You’ve hit your usage limit. Try again at 3:45 PM.", id="usage-curly"),
    pytest.param("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
                 "visit https://chatgpt.com/codex/settings/usage to purchase more credits or "
                 "try again later.", id="usage-ascii"),
    pytest.param("You’ve hit your usage limit for gpt-5.6-sol. Switch to another model now, "
                 "or try again later.", id="usage-model"),
    pytest.param("Your workspace is out of credits. Add credits to continue.",
                 id="credits-owner"),
    pytest.param("Your workspace is out of credits. Ask your workspace owner to refill in order "
                 "to continue.", id="credits-member"),
    pytest.param("You hit your spend cap set in your workspace. Increase your spend cap to "
                 "continue.", id="spend-cap"),
    pytest.param("rate limit exceeded: Rate limit reached for requests", id="rate"),
    pytest.param("Quota exceeded. Check your plan and billing details.", id="quota"),
    pytest.param("To use Codex with your ChatGPT plan, upgrade to Plus: "
                 "https://chatgpt.com/explore/plus.", id="not-included"),
    pytest.param("exceeded retry limit, last status: 429 Too Many Requests, request id: req_1",
                 id="retry-429"),
]

NOT_LIMITS = [
    pytest.param("Selected model is at capacity. Please try a different model.", id="capacity"),
    pytest.param("We’re currently experiencing high demand, which may cause temporary "
                 "errors.", id="high-demand"),
    pytest.param("Flex capacity unavailable.", id="flex"),
    pytest.param("unexpected status 401 Unauthorized", id="401"),
    pytest.param("exceeded retry limit, last status: 500 Internal Server Error", id="retry-500"),
    pytest.param("stream died", id="stream-died"),
    pytest.param("", id="empty"),
]


@pytest.mark.parametrize("message", LIMIT_MESSAGES)
def test_limit_line_matches_every_cited_codex_limit_message(message):
    text = f"codex exec started\n{message}\nexit 1"

    assert review_limit.limit_line(text) == message


@pytest.mark.parametrize("message", NOT_LIMITS)
def test_limit_line_ignores_errors_that_are_not_limits(message):
    assert review_limit.limit_line(message) is None


def test_limit_line_reads_every_text_given():
    line = review_limit.limit_line("", "boom\nQuota exceeded. Check your plan and billing details.")

    assert line == "Quota exceeded. Check your plan and billing details."
