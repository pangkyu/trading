"""The gateway's single shared runtime.

Owns exactly one market-data feed and fans its quotes out to:
* every SimBroker (so resting limit orders match), and
* every connected WebSocket client.

Also holds the sim-account registry (persisted to SQLite) and, optionally, the
one NH broker the bot trades through.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from core import Quote, SimBroker
from core.models import new_id

from .config import Config
from .db import DB

log = logging.getLogger("gateway.hub")


class Hub:
    def __init__(self, cfg: Config, db: DB) -> None:
        self.cfg = cfg
        self.db = db
        self._loop: asyncio.AbstractEventLoop | None = None

        self._quotes: dict[str, Quote] = {}
        self._sims: dict[str, SimBroker] = {}
        self._sim_names: dict[str, str] = {}
        self._subscribers: set[asyncio.Queue[Quote]] = set()
        self._lock = threading.RLock()

        self._feed_thread: threading.Thread | None = None
        self._stop = threading.Event()

        self.nh: Any = None  # core.nh_broker.NHBroker | None

    # --- lifecycle ----------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._restore_sims()
        self._maybe_start_nh()
        self._start_feed()

    def stop(self) -> None:
        self._stop.set()

    def _restore_sims(self) -> None:
        for row in self.db.all_sim_accounts():
            b = SimBroker.from_state(
                row["state"],
                fee_bps=self.cfg.sim_fee_bps,
                slippage_bps=self.cfg.sim_slippage_bps,
            )
            self._sims[row["id"]] = b
            self._sim_names[row["id"]] = row["name"]
        log.info("restored %d sim account(s)", len(self._sims))

    def _maybe_start_nh(self) -> None:
        if not self.cfg.nh_account:
            return
        try:
            from core.nh_broker import NHBroker

            self.nh = NHBroker(
                act_no=self.cfg.nh_account,
                dry_run=self.cfg.nh_dry_run,
                verify_account=False,
            )
            log.info("NH broker enabled (dry_run=%s)", self.cfg.nh_dry_run)
        except Exception as e:  # noqa: BLE001 - NH is optional, never block boot
            log.warning("NH broker disabled: %s", e)

    def _start_feed(self) -> None:
        if self.cfg.feed == "manual":
            log.info("feed 'manual' — quotes must be pushed via Hub.push_quote")
            return
        if self.cfg.feed == "synthetic":
            from core import SyntheticFeed

            feed = SyntheticFeed(
                {s: 50_000.0 for s in self.cfg.symbols}, interval_s=0.5, seed=7
            )
        elif self.cfg.feed == "nh":
            from core.nh_feed import NHFeed

            feed = NHFeed()
            feed.subscribe(self.cfg.symbols)
        else:
            raise ValueError(f"unknown GATEWAY_FEED: {self.cfg.feed}")

        def run() -> None:
            log.info("feed '%s' started for %s", self.cfg.feed, self.cfg.symbols)
            for q in feed.stream():
                if self._stop.is_set():
                    break
                self.push_quote(q)

        self._feed_thread = threading.Thread(target=run, daemon=True, name="hub-feed")
        self._feed_thread.start()

    # --- market data ------------------------------------------------
    def push_quote(self, quote: Quote) -> None:
        with self._lock:
            self._quotes[quote.symbol] = quote
            sims = list(self._sims.values())
        for b in sims:
            b.on_quote(quote)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._fanout, quote)

    def _fanout(self, quote: Quote) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(quote)
            except asyncio.QueueFull:
                pass

    def latest(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)

    def all_quotes(self) -> dict[str, Quote]:
        with self._lock:
            return dict(self._quotes)

    def subscribe(self) -> asyncio.Queue[Quote]:
        q: asyncio.Queue[Quote] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Quote]) -> None:
        self._subscribers.discard(q)

    # --- sim accounts ----------------------------------------------
    def create_sim(self, name: str, cash: float | None = None) -> str:
        acct_id = new_id("sim")
        b = SimBroker(
            cash=cash if cash is not None else self.cfg.sim_starting_cash,
            fee_bps=self.cfg.sim_fee_bps,
            slippage_bps=self.cfg.sim_slippage_bps,
        )
        with self._lock:
            for q in self._quotes.values():   # prime marks so an immediate order can fill
                b.on_quote(q)
            self._sims[acct_id] = b
            self._sim_names[acct_id] = name
        self.db.create_sim_account(acct_id, name, b.export_state())
        return acct_id

    def sim(self, acct_id: str) -> SimBroker:
        b = self._sims.get(acct_id)
        if b is None:
            raise KeyError(acct_id)
        return b

    def sim_name(self, acct_id: str) -> str:
        return self._sim_names.get(acct_id, "")

    def list_sims(self) -> list[str]:
        with self._lock:
            return list(self._sims)

    def persist_sim(self, acct_id: str) -> None:
        self.db.save_sim_state(acct_id, self._sims[acct_id].export_state())

    def delete_sim(self, acct_id: str) -> None:
        with self._lock:
            self._sims.pop(acct_id, None)
            self._sim_names.pop(acct_id, None)
        self.db.delete_sim_account(acct_id)
