"""Telegram Rich Message API helper.

Sends rich formatted messages using Bot API 10.1 sendRichMessage / sendRichMessageDraft.
Uses direct HTTP calls since python-telegram-bot may not expose these methods yet.
"""

import io
import json
import logging
import os
import re

import aiohttp

logger = logging.getLogger("bot.rich")

API_BASE = "https://api.telegram.org/bot{token}/{method}"

# Fragmentos de "description" que indican un chat muerto (bloqueo, baja,
# cuenta eliminada): reintentar es inútil, hay que dar de baja al suscriptor.
_DEAD_CHAT_HINTS = (
    "blocked",
    "deactivated",
    "kicked",
    "chat not found",
    "user not found",
    "group chat was deleted",
    "group chat was upgraded",
)


def is_blocked_response(result: dict | None) -> bool:
    """True si la respuesta de la API indica un chat muerto.

    Sirve para dar de baja al suscriptor en vez de reintentar cada día.
    """
    if not result or result.get("ok"):
        return False
    description = str(result.get("description", "")).lower()
    return any(hint in description for hint in _DEAD_CHAT_HINTS)


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
        The API response dict, or None on transport failure.
        When the API answers with ok=False the error dict is returned
        so callers can react (e.g. drop blocked subscribers).
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
        if result.get("ok"):
            return result
        if is_blocked_response(result):
            # El usuario bloqueó o eliminó el chat: el fallback tampoco llegaría.
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
        The API response dict, or None on transport failure.
        When the API answers with ok=False the error dict is returned
        so callers can react (e.g. drop blocked subscribers).
    """
    token = _get_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    url = API_BASE.format(token=token, method="sendPhoto")

    # Rebobinar: el mismo buffer se reutiliza para todos los suscriptores y
    # el primer envío lo deja al final (el resto saldría vacío).
    try:
        photo.seek(0)
    except (AttributeError, OSError, ValueError):
        pass

    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    form.add_field("photo", photo, filename="chart.png", content_type="image/png")
    if caption:
        form.add_field("caption", caption[:1024])
    if reply_markup:
        form.add_field("reply_markup", json.dumps(reply_markup))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram sendPhoto error: %s", data.get("description"))
                return data
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
    """Make a raw API call to the Telegram Bot API.

    Returns the full response dict (check ``ok``), or None when the
    request itself failed (network error, bad JSON, missing token).
    """
    token = _get_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    url = API_BASE.format(token=token, method=method)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram API %s error: %s", method, data.get("description"))
                return data
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
        if result.get("ok") or is_blocked_response(result):
            return result
        logger.info("MarkdownV2 send failed, retrying as plain text for chat %s", chat_id)

    # Last resort: send as raw text without parse mode
    payload.pop("parse_mode", None)
    payload["text"] = _strip_all_markdown(markdown)
    return await _api_call("sendMessage", payload)


# Caracteres reservados de MarkdownV2: deben llevar `\` delante, incluso
# dentro de listas o de texto normal ("-" o "." sueltos ya dan error).
_MD_V2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")

# Fragmentos con formato inline: **negrita**, _cursiva_ y `código`.
_INLINE_RE = re.compile(r"(\*\*[^*\n]+?\*\*|`[^`\n]+?`|_[^_\n]+?_)")

# Etiquetas de bloque del markdown enriquecido que no existen en sendMessage.
_BLOCK_TAG_RE = re.compile(r"</?(?:details|summary|footer|tg-thinking)>")


def _escape_md_v2(text: str) -> str:
    """Escapa los caracteres reservados de MarkdownV2."""
    return _MD_V2_SPECIAL.sub(r"\\\1", text)


def _convert_inline(text: str) -> str:
    """Normaliza el formato inline y escapa el resto para MarkdownV2.

    Conserva **negrita** (como *negrita*), _cursiva_ y `código`; todo lo
    demás se escapa para que la API no rechace el mensaje.
    """
    out = []
    for i, token in enumerate(_INLINE_RE.split(text)):
        if not token:
            continue
        if i % 2 == 1 and len(token) >= 5 and token.startswith("**"):
            out.append("*" + _escape_md_v2(token[2:-2]) + "*")
        elif i % 2 == 1 and len(token) >= 2 and token[0] == token[-1] and token[0] in ("`", "_"):
            out.append(token[0] + _escape_md_v2(token[1:-1]) + token[0])
        else:
            out.append(_escape_md_v2(token))
    return "".join(out)


def _markdown_to_plain(md: str, *, escape: bool = True) -> str:
    """Convert rich markdown to MarkdownV2-compatible text.

    Removes block-level elements not supported by sendMessage.

    Args:
        md: Rich markdown content.
        escape: Escape MarkdownV2 reserved chars (False for the
            no-parse-mode last resort, where backslashes would show).
    """
    def _inline(text: str) -> str:
        return _convert_inline(text) if escape else text

    lines = []
    for line in md.split("\n"):
        stripped = line.strip()

        # Skip block-level elements
        if stripped.startswith("## "):
            # Convert headings to bold text (inner markers are escaped:
            # MarkdownV2 forbids nested entities)
            content = stripped[3:]
            lines.append(f"*{_escape_md_v2(content) if escape else content}*")
        elif stripped.startswith("### "):
            content = stripped[4:]
            lines.append(f"*{_escape_md_v2(content) if escape else content}*")
        elif stripped.startswith("---"):
            lines.append("—————————")
        elif stripped.startswith("<details>") or stripped.startswith("</details>"):
            continue
        elif stripped.startswith("<summary>"):
            text = stripped.replace("<summary>", "").replace("</summary>", "")
            # Full escape inside: MarkdownV2 forbids nested entities.
            lines.append(f"▸ *{_escape_md_v2(text) if escape else text}*")
        elif stripped.startswith("<footer>") or stripped.startswith("</footer>"):
            text = _BLOCK_TAG_RE.sub("", stripped)
            lines.append(_inline(text))
        elif stripped.startswith("<tg-thinking>"):
            continue
        elif stripped.startswith("| ") and "|" in stripped[2:]:
            # Table row — convert to simple text
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            lines.append("  ".join(_inline(c) for c in cells))
        elif stripped.startswith("|:") or stripped.startswith("|--"):
            continue  # Skip table separators
        elif stripped.startswith("- "):
            lines.append(f"• {_inline(stripped[2:])}")
        elif stripped.startswith("> "):
            # Full escape inside: MarkdownV2 forbids nested entities.
            lines.append(f"_{_escape_md_v2(stripped[2:]) if escape else stripped[2:]}_")
        else:
            lines.append(_inline(line))

    return "\n".join(lines)


def _strip_all_markdown(md: str) -> str:
    """Strip ALL markdown formatting, returning plain text."""
    text = _markdown_to_plain(md, escape=False)
    # Remove markdown bold/italic markers
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text
