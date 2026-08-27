"""SQLite persistence — stdlib sqlite3, thin repo functions.

Two things survive a restart:

* ``sim_account`` — one row per virtual (web) account, full SimBroker state as
  a JSON blob (cash, positions, open orders, fill history). Rebuilt on boot.
* ``nh_history`` — cached NH dailyOrderExecution results keyed by (account,
  date). Historical days never change, so this shields the tight NH quota.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_account (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    created_ms    INTEGER NOT NULL,
    updated_ms    INTEGER NOT NULL,
    state_json    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nh_history (
    account   TEXT NOT NULL,
    orr_dt    TEXT NOT NULL,
    cached_ms INTEGER NOT NULL,
    rows_json TEXT NOT NULL,
    PRIMARY KEY (account, orr_dt)
);
"""


def _now_ms() -> int:
    return int(time.time() * 1000)


class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # one connection, guarded by a lock (sqlite + threads)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- sim accounts ---------------------------------------------------
    def create_sim_account(self, acct_id: str, name: str, state: dict[str, Any]) -> None:
        ts = _now_ms()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sim_account (id, name, created_ms, updated_ms, state_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (acct_id, name, ts, ts, json.dumps(state)),
            )
            self._conn.commit()

    def save_sim_state(self, acct_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sim_account SET state_json = ?, updated_ms = ? WHERE id = ?",
                (json.dumps(state), _now_ms(), acct_id),
            )
            self._conn.commit()

    def all_sim_accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, created_ms, updated_ms, state_json FROM sim_account"
            ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "created_ms": r["created_ms"],
                "updated_ms": r["updated_ms"],
                "state": json.loads(r["state_json"]),
            }
            for r in rows
        ]

    def delete_sim_account(self, acct_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sim_account WHERE id = ?", (acct_id,))
            self._conn.commit()

    # --- NH history cache ---------------------------------------------
    def get_nh_history(self, account: str, orr_dt: str, max_age_s: int) -> list[dict] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT cached_ms, rows_json FROM nh_history WHERE account = ? AND orr_dt = ?",
                (account, orr_dt),
            ).fetchone()
        if row is None:
            return None
        if _now_ms() - row["cached_ms"] > max_age_s * 1000:
            return None
        return json.loads(row["rows_json"])

    def put_nh_history(self, account: str, orr_dt: str, rows: list[dict]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO nh_history (account, orr_dt, cached_ms, rows_json) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(account, orr_dt) DO UPDATE SET "
                "cached_ms = excluded.cached_ms, rows_json = excluded.rows_json",
                (account, orr_dt, _now_ms(), json.dumps(rows)),
            )
            self._conn.commit()
