"""Regression tests: REE's all-zero unpublished-day placeholder.

Run:  .venv/bin/python -m unittest discover -s tests -v
Needs no network: DB hits short-circuit before any API call, and the
API layer is never touched (no ESIOS_API_TOKEN in this env).
"""
import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot.db as db
from bot.db import init_db, is_placeholder_day
from bot.esios import fetch_pvpc_prices

POISON_DATE = "2026-10-08"
LEGIT_DATE = "2026-10-07"


def _run(coro):
    return asyncio.run(coro)


def _prices(values):
    return [
        {"hour": h, "price_kwh": v / 1000, "price_mwh": v}
        for h, v in enumerate(values)
    ]


class PlaceholderTest(unittest.TestCase):
    def setUp(self):
        # Isolated temp DB per test (DB_PATH is read at call time).
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._old_path = db.DB_PATH
        db.DB_PATH = self._tmp.name
        self._old_token = os.environ.pop("ESIOS_API_TOKEN", None)
        _run(init_db())

    def tearDown(self):
        db.DB_PATH = self._old_path
        if self._old_token is not None:
            os.environ["ESIOS_API_TOKEN"] = self._old_token
        os.unlink(self._tmp.name)

    def test_predicate_all_zero_is_placeholder(self):
        self.assertTrue(is_placeholder_day(_prices([0] * 24)))
        self.assertTrue(is_placeholder_day(_prices([0.0] * 24)))

    def test_predicate_keeps_real_days(self):
        self.assertFalse(is_placeholder_day([]))
        # Single zero hour amid real prices is genuine market data.
        self.assertFalse(is_placeholder_day(_prices([0] + [50 + h for h in range(1, 24)])))

    def test_poisoned_db_day_is_not_served(self):
        # Simulate rows persisted by the pre-guard code via raw SQL,
        # bypassing the save_prices guard under test below.
        async def seed():
            import aiosqlite
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.executemany(
                    "INSERT INTO prices (date, hour, price_kwh, price_mwh)"
                    " VALUES (?, ?, ?, ?)",
                    [(POISON_DATE, h, 0.0, 0) for h in range(24)],
                )
                await conn.commit()
        _run(seed())
        # No token either: must fall through to "unavailable", never zeros.
        self.assertIsNone(_run(fetch_pvpc_prices(POISON_DATE)))

    def test_save_prices_refuses_placeholder(self):
        _run(db.save_prices(POISON_DATE, _prices([0] * 24)))
        self.assertIsNone(_run(db.get_prices(POISON_DATE)))
        # ...but persists genuine days, including one with a zero hour.
        legit = _prices([0] + [50 + h for h in range(1, 24)])
        _run(db.save_prices(LEGIT_DATE, legit))
        stored = _run(db.get_prices(LEGIT_DATE))
        self.assertEqual(len(stored), 24)

    def test_migration_4_cleans_poisoned_days(self):
        async def seed_v3():
            import aiosqlite
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute("UPDATE schema_version SET version = 3 WHERE version = 4")
                await conn.executemany(
                    "INSERT INTO prices (date, hour, price_kwh, price_mwh)"
                    " VALUES (?, ?, ?, ?)",
                    [(POISON_DATE, h, 0.0, 0) for h in range(24)]
                    + [(LEGIT_DATE, h, (50 + h) / 1000, 50 + h) for h in range(24)],
                )
                await conn.execute(
                    "INSERT INTO daily_avg (date, avg_kwh) VALUES (?, 0)",
                    (POISON_DATE,),
                )
                await conn.execute(
                    "INSERT INTO daily_avg (date, avg_kwh) VALUES (?, 0.06)",
                    (LEGIT_DATE,),
                )
                await conn.commit()
        _run(seed_v3())
        _run(init_db())  # upgrade path 3 -> 4 runs the cleanup
        self.assertIsNone(_run(db.get_prices(POISON_DATE)))
        self.assertIsNone(_run(db.get_daily_avg(POISON_DATE)))
        self.assertEqual(len(_run(db.get_prices(LEGIT_DATE))), 24)
        self.assertAlmostEqual(_run(db.get_daily_avg(LEGIT_DATE)), 0.06)


if __name__ == "__main__":
    unittest.main()
