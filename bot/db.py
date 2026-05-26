import logging
import os

import aiosqlite

logger = logging.getLogger("bot.db")

DB_PATH = os.getenv("DB_PATH", "/data/subscribers.db")

CURRENT_SCHEMA_VERSION = 1


async def _get_connection() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO schema_version (version) VALUES (0)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT NULL,
                joined_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
        """)
        await db.commit()

        cursor = await db.execute("SELECT version FROM schema_version")
        row = await cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < CURRENT_SCHEMA_VERSION:
            await _run_migrations(db, current_version)

    logger.info("Database initialized (schema version %d)", CURRENT_SCHEMA_VERSION)


async def _run_migrations(db: aiosqlite.Connection, from_version: int):
    for version in range(from_version + 1, CURRENT_SCHEMA_VERSION + 1):
        migration_func = _MIGRATIONS.get(version)
        if migration_func:
            logger.info("Running migration to version %d", version)
            await migration_func(db)
        await db.execute("UPDATE schema_version SET version = ?", (version,))
        await db.commit()


async def _migration_1(db: aiosqlite.Connection):
    pass


_MIGRATIONS = {
    1: _migration_1,
}


async def add_subscriber(chat_id: int, username: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, username) VALUES (?, ?)",
            (chat_id, username),
        )
        await db.commit()


async def remove_subscriber(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def is_subscribed(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM subscribers WHERE chat_id = ?", (chat_id,))
        row = await cursor.fetchone()
        return row is not None


async def get_all_subscribers() -> list[tuple[int, str | None]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT chat_id, username FROM subscribers")
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]
