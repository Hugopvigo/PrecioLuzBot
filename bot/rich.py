"""Telegram Rich Message API helper.

Sends rich formatted messages using Bot API 10.1 sendRichMessage / sendRichMessageDraft.
Uses direct HTTP calls since python-telegram-bot may not expose these methods yet.
"""

import io
import logging
import os

import aiohttp

logger = logging.getLogger("bot.rich")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _get_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


async def send_rich_message(
    chat_id: int,
    markdown: str,
    *,
    disable_notification: bool = False,
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a rich formatted message via sendRichMessage.

    Falls back to send_message with HTML if sendRichMessage is unavailable.

    Args:
        chat_id: Target chat ID.
        markdown: Rich markdown content (Telegram Bot API 10.1 markdown syntax).
        disable_notification: Send silently.
        reply_markup: Optional InlineKeyboardMarkup dict.

    Returns:
        The API response dict, or None on failure.
    """
    payload = {
        "chat_id": chat_id,
        "rich_message": {"markdown": markdown},
    }
    if disable_notification:
        payload["disable_notification"] = True
    if reply_markup:
        payload["reply_markup"] = reply_markup

    result = await _api_call("sendRichMessage", payload)
    if result is not None:
        return result

    # Fallback: send as plain Markdown via sendMessage
    logger.info("sendRichMessage failed, falling back to sendMessage for chat %s", chat_id)
    return await _fallback_send_message(chat_id, markdown, disable_notification)


async def send_rich_draft(
    chat_id: int,
    draft_id: int,
    markdown: str,
) -> dict | None:
    """Send a streaming draft via sendRichMessageDraft.

    The draft is ephemeral (30s preview). Changes with the same draft_id
    animate seamlessly. After streaming, call send_rich_message with the
    final content.

    Args:
        chat_id: Target chat ID.
        draft_id: Non-zero integer identifying this draft stream.
        markdown: Partial rich markdown content.

    Returns:
        The API response dict, or None on failure.
    """
    payload = {
        "chat_id": chat_id,
        "draft_id": draft_id,
        "rich_message": {"markdown": markdown},
    }
    return await _api_call("sendRichMessageDraft", payload)


async def edit_rich_message(
    chat_id: int,
    message_id: int,
    markdown: str,
) -> dict | None:
    """Edit an existing message with new rich content.

    Args:
        chat_id: Chat ID where the message lives.
        message_id: ID of the message to edit.
        markdown: New rich markdown content.

    Returns:
        The API response dict, or None on failure.
    """
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "rich_message": {"markdown": markdown},
    }
    return await _api_call("editMessageText", payload)


async def send_photo(
    chat_id: int,
    photo: io.BytesIO,
    caption: str = "",
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a photo with optional caption and inline keyboard.

    Args:
        chat_id: Target chat ID.
        photo: PNG image as BytesIO.
        caption: Optional text caption (Markdown).
        reply_markup: Optional InlineKeyboardMarkup dict.

    Returns:
        The API response dict, or None on failure.
    """
    token = _get_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    url = API_BASE.format(token=token, method="sendPhoto")

    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    form.add_field("photo", photo, filename="chart.png", content_type="image/png")
    if caption:
        form.add_field("caption", caption[:1024])
    if reply_markup:
        import json
        form.add_field("reply_markup", json.dumps(reply_markup))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data
                logger.warning("Telegram sendPhoto error: %s", data.get("description"))
                return None
    except Exception:
        logger.exception("Failed calling Telegram sendPhoto")
        return None


async def set_my_commands(commands: list[dict]) -> dict | None:
    """Set the bot's command menu via setMyCommands.

    Args:
        commands: List of {"command": "...", "description": "..."} dicts.

    Returns:
        The API response dict, or None on failure.
    """
    payload = {"commands": commands}
    return await _api_call("setMyCommands", payload)


async def _api_call(method: str, payload: dict) -> dict | None:
    """Make a raw API call to the Telegram Bot API."""
    token = _get_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    url = API_BASE.format(token=token, method=method)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data
                logger.warning("Telegram API %s error: %s", method, data.get("description"))
                return None
    except Exception:
        logger.exception("Failed calling Telegram API %s", method)
        return None


async def _fallback_send_message(
    chat_id: int,
    markdown: str,
    disable_notification: bool = False,
) -> dict | None:
    """Fallback: send via sendMessage with MarkdownV2 parse mode.

    Strips block-level elements (tables, headings, details, hr, footer)
    that aren't supported in sendMessage, keeping only inline formatting.
    """
    plain = _markdown_to_plain(markdown)

    payload = {
        "chat_id": chat_id,
        "text": plain,
        "parse_mode": "MarkdownV2",
    }
    if disable_notification:
        payload["disable_notification"] = True

    result = await _api_call("sendMessage", payload)
    if result is not None:
        return result

    # Last resort: send as raw text without parse mode
    payload.pop("parse_mode", None)
    payload["text"] = _strip_all_markdown(markdown)
    return await _api_call("sendMessage", payload)


def _markdown_to_plain(md: str) -> str:
    """Convert rich markdown to MarkdownV2-compatible text.

    Removes block-level elements not supported by sendMessage.
    """
    lines = []
    for line in md.split("\n"):
        stripped = line.strip()

        # Skip block-level elements
        if stripped.startswith("## "):
            # Convert headings to bold text
            lines.append(f"*{stripped[3:]}*")
        elif stripped.startswith("### "):
            lines.append(f"*{stripped[4:]}*")
        elif stripped.startswith("---"):
            lines.append("—————————")
        elif stripped.startswith("<details>") or stripped.startswith("</details>"):
            continue
        elif stripped.startswith("<summary>"):
            text = stripped.replace("<summary>", "").replace("</summary>", "")
            lines.append(f"▸ *{text}*")
        elif stripped.startswith("<footer>") or stripped.startswith("</footer>"):
            text = stripped.replace("<footer>", "").replace("</footer>", "")
            lines.append(text)
        elif stripped.startswith("<tg-thinking>"):
            continue
        elif stripped.startswith("| ") and "|" in stripped[2:]:
            # Table row — convert to simple text
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            lines.append("  ".join(cells))
        elif stripped.startswith("|:") or stripped.startswith("|--"):
            continue  # Skip table separators
        elif stripped.startswith("- "):
            lines.append(f"  {stripped}")
        elif stripped.startswith("> "):
            lines.append(f"_{stripped[2:]}_")
        else:
            lines.append(line)

    return "\n".join(lines)


def _strip_all_markdown(md: str) -> str:
    """Strip ALL markdown formatting, returning plain text."""
    import re
    text = _markdown_to_plain(md)
    # Remove markdown bold/italic markers
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text
