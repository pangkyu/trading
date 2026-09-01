"""The unattended trading loop.

    feed.stream()  ->  strategy.on_quote()  ->  RiskGate.check()  ->  broker.submit()

The bot keeps its OWN position book (updated from fills), so the strategy and
risk checks never need a per-tick REST call. For NH brokers it periodically
``reconcile()``s that book against the broker and pulls fresh executions.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from core.models import Fill, OrderStatus, Position, Quote
from core.sim_broker import SimBroker

from .build import build_broker, build_feed, build_strategy
from .config import Config
from .risk import RiskGate

log = logging.getLogger("bot")


class Bot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.broker = build_broker(cfg)
        self.feed = build_feed(cfg)
        self.strategy = build_strategy(cfg)
        self.risk = RiskGate(cfg)

        self.book: dict[str, Position] = {}
        self.marks: dict[str, float] = {}
        self.realized_start = 0.0            # realized PnL already booked before this session
        self._submitted = 0
        self._blocked = 0
        self._fills = 0
        self._started_ms = _now_ms()
        self._last_status = 0.0
        self._last_reconcile = 0.0
        self._stop = threading.Event()

        self.broker.on_fill(self._on_fill)

    # --- lifecycle --------------------------------------------------
    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        if self.risk.kill_armed():
            log.critical("kill switch is armed (%s) — not starting", self.cfg.kill_switch_file)
            return
        log.info(
            "bot start: broker=%s feed=%s symbols=%s dry_run=%s",
            self.cfg.broker, self.cfg.feed, self.cfg.symbols,
            getattr(self.broker, "dry_run", "n/a"),
        )
        if self.cfg.is_nh:
            self._reconcile()

        for quote in self.feed.stream():
            if self._stop.is_set():
                break
            self._on_quote(quote)
            self._periodic()

        self._write_status(final=True)
        log.info("bot stopped: submitted=%d blocked=%d fills=%d", self._submitted, self._blocked, self._fills)

    # --- per tick --------------------------------------------------
    def _on_quote(self, quote: Quote) -> None:
        self.marks[quote.symbol] = quote.last or quote.mid or self.marks.get(quote.symbol, 0.0)
        if isinstance(self.broker, SimBroker):
            self.broker.on_quote(quote)

        if self.risk.kill_armed():
            if not self._stop.is_set():
                log.critical("kill switch detected — halting")
                self._stop.set()
            return

        positions = {s: p.qty for s, p in self.book.items()}
        for order in self.strategy.on_quote(quote, positions):
            v = self.risk.check(
                order, book=self.book, marks=self.marks, session_pnl=self.session_pnl()
            )
            if not v.ok:
                self._blocked += 1
                log.warning("BLOCKED %s %s x%d: %s", order.side.value, order.symbol, order.qty, v.reason)
                continue
            res = self.broker.submit(order)
            self._submitted += 1
            if res.status is OrderStatus.REJECTED:
                log.error("REJECTED %s: %s", order.symbol, res.reject_reason)
            else:
                log.info("SUBMIT %s %s x%d (%s)", order.side.value, order.symbol, order.qty, res.status.value)

    def _periodic(self) -> None:
        now = time.time()
        if self.cfg.is_nh and now - self._last_reconcile >= self.cfg.reconcile_s:
            self._reconcile()
        if now - self._last_status >= self.cfg.status_every_s:
            self._write_status()

    # --- fills / book ---------------------------------------------
    def _on_fill(self, fill: Fill) -> None:
        self._fills += 1
        pos = self.book.setdefault(fill.symbol, Position(symbol=fill.symbol))
        pos.apply_fill(fill)
        log.info(
            "FILL %s %s x%d @ %s  (session pnl %s)",
            fill.side.value, fill.symbol, fill.qty,
            f"{fill.price:,.0f}", f"{self.session_pnl():,.0f}",
        )

    def _reconcile(self) -> None:
        self._last_reconcile = time.time()
        try:
            if hasattr(self.broker, "reconcile"):
                self.broker.reconcile()          # emits fills we haven't seen
            broker_pos = self.broker.positions()
        except Exception as e:  # noqa: BLE001 - never let reconcile kill the loop
            log.warning("reconcile failed: %s", e)
            return
        for sym, bp in broker_pos.items():
            local = self.book.get(sym)
            lq = local.qty if local else 0
            if lq != bp.qty:
                log.warning("DRIFT %s: local=%d broker=%d — adopting broker", sym, lq, bp.qty)
                self.book[sym] = Position(**vars(bp))

    # --- reporting ----------------------------------------------
    def session_pnl(self) -> float:
        realized = sum(p.realized_pnl for p in self.book.values()) - self.realized_start
        unreal = sum(
            p.unrealized_pnl(self.marks.get(s, p.avg_price)) for s, p in self.book.items()
        )
        return realized + unreal

    def status(self) -> dict:
        return {
            "ts_ms": _now_ms(),
            "uptime_s": round((_now_ms() - self._started_ms) / 1000),
            "broker": self.cfg.broker,
            "dry_run": getattr(self.broker, "dry_run", None),
            "kill_armed": self.risk.kill_armed(),
            "submitted": self._submitted,
            "blocked": self._blocked,
            "fills": self._fills,
            "session_pnl": round(self.session_pnl()),
            "positions": {
                s: {"qty": p.qty, "avg": round(p.avg_price), "mark": round(self.marks.get(s, 0))}
                for s, p in self.book.items()
                if p.qty
            },
        }

    def _write_status(self, *, final: bool = False) -> None:
        self._last_status = time.time()
        try:
            p = Path(self.cfg.status_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            data = self.status()
            data["running"] = not final
            p.write_text(json.dumps(data, indent=2))
        except OSError as e:
            log.warning("status write failed: %s", e)


def _now_ms() -> int:
    return int(time.time() * 1000)
