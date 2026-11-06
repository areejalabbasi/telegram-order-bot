import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS carts (
    user_id   INTEGER NOT NULL,
    item_id   TEXT    NOT NULL,
    qty       INTEGER NOT NULL,
    PRIMARY KEY (user_id, item_id)
);
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    state     TEXT,
    name      TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    name       TEXT,
    phone      TEXT    NOT NULL,
    items      TEXT    NOT NULL,
    total      INTEGER NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'new',
    created_at TEXT    NOT NULL
);
"""

STATUSES = ("new", "preparing", "ready", "done", "cancelled")


class Store:
    def __init__(self, path: str = "orders.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add_to_cart(self, user_id, item_id, qty=1):
        self.db.execute(
            """INSERT INTO carts (user_id, item_id, qty) VALUES (?, ?, ?)
               ON CONFLICT(user_id, item_id) DO UPDATE SET qty = qty + excluded.qty""",
            (user_id, item_id, qty),
        )
        self.db.execute("DELETE FROM carts WHERE user_id = ? AND qty <= 0", (user_id,))
        self.db.commit()

    def get_cart(self, user_id) -> dict:
        rows = self.db.execute("SELECT item_id, qty FROM carts WHERE user_id = ?", (user_id,))
        return {r["item_id"]: r["qty"] for r in rows}

    def clear_cart(self, user_id):
        self.db.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        self.db.commit()

    def set_state(self, user_id, state, name=None):
        self.db.execute(
            """INSERT INTO users (user_id, state, name) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET state = excluded.state,
               name = COALESCE(excluded.name, users.name)""",
            (user_id, state, name),
        )
        self.db.commit()

    def get_state(self, user_id):
        row = self.db.execute("SELECT state FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["state"] if row else None

    def create_order(self, user_id, chat_id, name, phone, items: dict, total: int) -> int:
        cur = self.db.execute(
            """INSERT INTO orders (user_id, chat_id, name, phone, items, total, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, chat_id, name, phone, json.dumps(items), total,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.db.commit()
        return cur.lastrowid

    def get_order(self, order_id):
        row = self.db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        order = dict(row)
        order["items"] = json.loads(order["items"])
        return order

    def set_status(self, order_id, status):
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        self.db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        self.db.commit()

    def open_orders(self):
        rows = self.db.execute(
            "SELECT * FROM orders WHERE status IN ('new', 'preparing', 'ready') ORDER BY id"
        )
        result = []
        for r in rows:
            order = dict(r)
            order["items"] = json.loads(order["items"])
            result.append(order)
        return result
