"""SQLite store for checkouts made through the web shop (the "Transaction" part of CARTS)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    items       TEXT NOT NULL,      -- JSON list of {item, qty, price, profit}
    total       REAL NOT NULL,
    profit      REAL NOT NULL,
    strategy    TEXT NOT NULL,
    recommended TEXT NOT NULL,      -- JSON list of item names shown to the shopper
    accepted    TEXT NOT NULL       -- JSON list of recommended items that were bought
);
"""


class OrderStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, lines: list[dict], strategy: str, recommended: list[str], accepted: list[str]) -> dict:
        total = round(sum(l["price"] * l["qty"] for l in lines), 2)
        profit = round(sum(l["profit"] * l["qty"] for l in lines), 2)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO orders (created_at, items, total, profit, strategy, recommended, accepted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, json.dumps(lines), total, profit, strategy, json.dumps(recommended), json.dumps(accepted)),
            )
            order_id = cur.lastrowid
        return {"id": order_id, "created_at": now, "total": total, "profit": profit}

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("items", "recommended", "accepted"):
                d[k] = json.loads(d[k])
            out.append(d)
        return out

    def baskets(self) -> list[list[str]]:
        with self._conn() as c:
            rows = c.execute("SELECT items FROM orders").fetchall()
        return [[l["item"] for l in json.loads(r["items"])] for r in rows]

    def summary(self) -> dict:
        orders = self.list(limit=100000)
        by_strategy: dict[str, dict] = {}
        for o in orders:
            s = by_strategy.setdefault(o["strategy"], {"orders": 0, "revenue": 0.0, "profit": 0.0,
                                                       "shown": 0, "accepted": 0, "rec_profit": 0.0})
            s["orders"] += 1
            s["revenue"] += o["total"]
            s["profit"] += o["profit"]
            s["shown"] += len(o["recommended"])
            s["accepted"] += len(o["accepted"])
            accepted = set(o["accepted"])
            s["rec_profit"] += sum(l["profit"] * l["qty"] for l in o["items"] if l["item"] in accepted)
        for s in by_strategy.values():
            s["acceptance_rate"] = round(s["accepted"] / s["shown"], 4) if s["shown"] else 0
            for k in ("revenue", "profit", "rec_profit"):
                s[k] = round(s[k], 2)
        return {
            "orders": len(orders),
            "revenue": round(sum(o["total"] for o in orders), 2),
            "profit": round(sum(o["profit"] for o in orders), 2),
            "by_strategy": by_strategy,
        }

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM orders")
