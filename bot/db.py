import logging
import os

import aiosqlite

logger = logging.getLogger("bot.db")

DB_PATH = os.getenv("DB_PATH", "/data/subscribers.db")

CURRENT_SCHEMA_VERSION = 2


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
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT NULL,
                joined_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
        """)

        cursor = await db.execute("SELECT version FROM schema_version")
        row = await cursor.fetchone()
        if row is None:
            await db.execute("INSERT INTO schema_version (version) VALUES (0)")
            await db.commit()
            current_version = 0
        else:
            current_version = row[0]

        if current_version < CURRENT_SCHEMA_VERSION:
            await _run_migrations(db, current_version)

    logger.info("Database initialized (schema version %d)", CURRENT_SCHEMA_VERSION)


async def _run_migrations(db: aiosqlite.Connection, from_version: int):
    for version in range(from_version + 1, CURRENT_SCHEMA_VERSION + 1):
        migration_func = _MIGRATIONS.get(version)
        if migration_func:
            logger.info("Running migration to version %d", version)
            await migration_func(db)
        await db.execute("UPDATE schema_version SET version = ? WHERE version = ?", (version, version - 1))
        await db.commit()


async def _migration_1(db: aiosqlite.Connection):
    pass


async def _migration_2(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            price_kwh REAL NOT NULL,
            price_mwh REAL NOT NULL,
            fetched_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            PRIMARY KEY (date, hour)
        )
    """)


_MIGRATIONS = {
    1: _migration_1,
    2: _migration_2,
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


async def get_prices(date: str) -> list[dict] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT hour, price_kwh, price_mwh FROM prices WHERE date = ? ORDER BY hour",
            (date,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return [{"hour": r[0], "price_kwh": r[1], "price_mwh": r[2]} for r in rows]


async def save_prices(date: str, prices: list[dict]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO prices (date, hour, price_kwh, price_mwh) VALUES (?, ?, ?, ?)",
            [(date, p["hour"], p["price_kwh"], p["price_mwh"]) for p in prices],
        )
        await db.commit()


async def get_all_subscribers() -> list[tuple[int, str | None]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT chat_id, username FROM subscribers")
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]
