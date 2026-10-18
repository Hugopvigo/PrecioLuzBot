"""Regression tests: Telegram fallback path (bot.rich).

Run inside the bot container (has all deps):
    docker cp tests <contenedor>:/tmp/pltests
    docker exec <contenedor> python -m unittest discover -s /tmp/pltests -t /app -v

Needs no network: HTTP is stubbed, the MarkdownV2 converter is pure.
"""
import asyncio
import io
import os
import re
import unittest
from unittest.mock import patch

from bot.formatter import format_rich_message
from bot.rich import (
    _escape_md_v2,
    _markdown_to_plain,
    _strip_all_markdown,
    is_blocked_response,
    send_photo,
)


def _prices():
    return [{"hour": h, "price_kwh": 0.08 + 0.004 * ((h * 7) % 9)} for h in range(24)]


def _assert_v2_clean(testcase, text):
    """Every MarkdownV2 reserved char must be escaped or inside an entity."""
    # Remove valid top-level entities: *bold*, _italic_, `code`.
    stripped = re.sub(r"\*[^*\n]+\*", "", text)
    stripped = re.sub(r"_[^_\n]+_", "", stripped)
    stripped = re.sub(r"`[^`\n]+`", "", stripped)
    # Anything reserved left must carry a backslash escape.
    for match in re.finditer(r"[_*\[\]()~`>#+\-=|{}.!\\]", stripped):
        pos = match.start()
        backslashes = 0
        i = pos - 1
        while i >= 0 and stripped[i] == "\\":
            backslashes += 1
            i -= 1
        testcase.assertEqual(
            backslashes % 2, 1,
            f"unescaped {match.group()!r} in: {text!r}",
        )


class FakePost:
    def __init__(self):
        self.calls = 0

    async def __call__(self, url, data=None, timeout=None):
        self.calls += 1
        return FakeResponse()


class FakeResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return {"ok": True, "result": {}}


class FakeSession:
    poster = FakePost()

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, data=None, timeout=None):
        return self.poster(url, data=data, timeout=timeout)


def _run(coro):
    return asyncio.run(coro)


class EscapeTest(unittest.TestCase):
    def test_reserved_chars_escaped(self):
        out = _escape_md_v2("a-b_c.d!e")
        self.assertEqual(out, "a\\-b\\_c\\.d\\!e")

    def test_backslash_escaped_first(self):
        self.assertEqual(_escape_md_v2("a\\b"), "a\\\\b")


class MarkdownToPlainTest(unittest.TestCase):
    def test_real_notification_message_is_v2_clean(self):
        md = format_rich_message(_prices(), "2026-10-19", yesterday_avg=0.10)
        plain = _markdown_to_plain(md)
        # The old code kept "- " list markers, which Telegram rejects.
        for line in plain.split("\n"):
            self.assertFalse(line.lstrip().startswith("- "))
        _assert_v2_clean(self, plain)

    def test_bold_and_code_preserved(self):
        plain = _markdown_to_plain("- **Más barata:** `03:00h` → **0,1234 €/kWh**")
        self.assertIn("*Más barata:*", plain)
        self.assertIn("`03:00h`", plain)
        _assert_v2_clean(self, plain)

    def test_last_resort_has_no_backslashes(self):
        md = format_rich_message(_prices(), "2026-10-19", yesterday_avg=0.10)
        raw = _strip_all_markdown(md)
        self.assertNotIn("\\", raw)
        self.assertNotIn("**", raw)


class BlockedResponseTest(unittest.TestCase):
    def test_dead_chats_detected(self):
        for desc in (
            "Forbidden: bot was blocked by the user",
            "Forbidden: bot was kicked from the group chat",
            "Forbidden: user is deactivated",
            "Bad Request: chat not found",
        ):
            self.assertTrue(
                is_blocked_response({"ok": False, "description": desc}), desc
            )

    def test_transient_and_ok_are_not_blocked(self):
        self.assertFalse(is_blocked_response({"ok": True, "result": {}}))
        self.assertFalse(is_blocked_response(None))
        self.assertFalse(
            is_blocked_response({"ok": False, "description": "Bad Gateway"})
        )
        self.assertFalse(
            is_blocked_response(
                {"ok": False, "description": "Can't parse entities: ..."}
            )
        )


class SendPhotoTest(unittest.TestCase):
    def test_rewinds_shared_buffer(self):
        """Same BytesIO for N subscribers: the 2nd..Nth upload must be full.

        aiohttp reads the stream from its current position, so send_photo
        must rewind before every upload (nightly bug: 8/9 photos empty).
        """
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        buf = io.BytesIO(b"PNGDATA" * 1000)
        buf.read()  # simulate a previous subscriber's upload consuming it
        self.assertNotEqual(buf.tell(), 0)
        with patch("aiohttp.ClientSession", FakeSession):
            _run(send_photo(123, buf))
        # Rewound before the HTTP layer read it.
        self.assertEqual(buf.tell(), 0)


if __name__ == "__main__":
    unittest.main()
