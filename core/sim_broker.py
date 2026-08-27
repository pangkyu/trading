"""Self-matching paper-trading broker.

It consumes the same :class:`Quote` ticks the real feed produces and decides
fills locally:

* MARKET orders fill immediately against the opposite touch (bid for a sell,
  ask for a buy), with configurable slippage when book depth is unknown.
* LIMIT orders rest until a tick trades through (or touches) the limit price.

This is what the web 모의투자 service runs. It is deliberately simple and
pessimistic rather than a full L2 matching engine.
"""

from __future__ import annotations

import threading
from typing import Any

from .broker import Broker
from .models import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Side,
    new_id,
)


class SimBroker(Broker):
    def __init__(
        self,
        *,
        cash: float = 100_000_000,
        fee_bps: float = 1.5,          # per-side commission, basis points
        slippage_bps: float = 5.0,     # applied to MARKET when no book depth
        allow_short: bool = False,
    ) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self.starting_cash = cash
        self.cash = cash
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.allow_short = allow_short

        self._orders: dict[str, Order] = {}            # broker_order_id -> Order
        self._by_client: dict[str, str] = {}           # client_order_id -> broker_order_id
        self._resting: list[str] = []                  # broker_order_ids of open LIMITs
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._last_px: dict[str, float] = {}

    # --- Broker API -----------------------------------------------------------
    def submit(self, order: Order) -> Order:
        with self._lock:
            if order.client_order_id in self._by_client:
                return self._orders[self._by_client[order.client_order_id]]

            order.broker_order_id = new_id("sord")
            self._orders[order.broker_order_id] = order
            self._by_client[order.client_order_id] = order.broker_order_id

            reason = self._risk_check(order)
            if reason:
                order.status = OrderStatus.REJECTED
                order.reject_reason = reason
                return order

            if order.type is OrderType.MARKET:
                px = self._market_price(order)
                if px is None:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = "no market data for symbol"
                    return order
                self._execute(order, order.qty, px)
            else:
                order.status = OrderStatus.PENDING
                self._resting.append(order.broker_order_id)
            return order

    def cancel(self, broker_order_id: str) -> Order:
        with self._lock:
            order = self._orders.get(broker_order_id)
            if order is None:
                raise KeyError(broker_order_id)
            if order.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                order.status = OrderStatus.CANCELED
                if broker_order_id in self._resting:
                    self._resting.remove(broker_order_id)
            return order

    def get_order(self, broker_order_id: str) -> Order | None:
        return self._orders.get(broker_order_id)

    def open_orders(self) -> list[Order]:
        with self._lock:
            return [
                self._orders[oid]
                for oid in self._resting
                if self._orders[oid].status in (OrderStatus.PENDING, OrderStatus.PARTIAL)
            ]

    def positions(self) -> dict[str, Position]:
        with self._lock:
            return {s: Position(**vars(p)) for s, p in self._positions.items()}

    def fills(self, since_ms: int = 0) -> list[Fill]:
        with self._lock:
            return [f for f in self._fills if f.ts_ms >= since_ms]

    # --- market data hook ---------------------------------------------------
    def on_quote(self, quote) -> None:
        """Feed every tick here; rests get matched."""
        with self._lock:
            if quote.last is not None:
                self._last_px[quote.symbol] = quote.last
            elif quote.mid is not None:
                self._last_px[quote.symbol] = quote.mid

            for oid in list(self._resting):
                order = self._orders[oid]
                if order.symbol != quote.symbol:
                    continue
                fill_px = self._limit_cross(order, quote)
                if fill_px is not None:
                    self._execute(order, order.remaining_qty, fill_px)
                    if order.status is OrderStatus.FILLED and oid in self._resting:
                        self._resting.remove(oid)

    # --- internals --------------------------------------------------------
    def _risk_check(self, order: Order) -> str | None:
        if not self.allow_short and order.side is Side.SELL:
            held = self._positions.get(order.symbol)
            have = held.qty if held else 0
            resting_sells = sum(
                self._orders[o].remaining_qty
                for o in self._resting
                if self._orders[o].symbol == order.symbol
                and self._orders[o].side is Side.SELL
            )
            if order.qty + resting_sells > have:
                return "insufficient position for SELL (short not allowed)"
        return None

    def _market_price(self, order: Order) -> float | None:
        # prefer the opposite touch, fall back to last +/- slippage
        # (a real feed for KR stocks always carries a book, so this is the dev path)
        last = self._last_px.get(order.symbol)
        if last is None:
            return None
        slip = last * self.slippage_bps / 10_000
        return last + slip if order.side is Side.BUY else last - slip

    @staticmethod
    def _limit_cross(order: Order, quote) -> float | None:
        lp = order.limit_price
        if order.side is Side.BUY:
            ask = quote.ask if quote.ask is not None else quote.last
            if ask is not None and ask <= lp:
                return min(ask, lp)
        else:
            bid = quote.bid if quote.bid is not None else quote.last
            if bid is not None and bid >= lp:
                return max(bid, lp)
        return None

    def _execute(self, order: Order, qty: int, price: float) -> None:
        fee = price * qty * self.fee_bps / 10_000
        fill = Fill(
            order_id=order.broker_order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            qty=qty,
            price=round(price, 4),
            fee=round(fee, 2),
        )
        self._fills.append(fill)

        cash_delta = -price * qty if order.side is Side.BUY else price * qty
        self.cash += cash_delta - fee

        pos = self._positions.setdefault(order.symbol, Position(symbol=order.symbol))
        pos.apply_fill(fill)

        order.filled_qty += qty
        prev_avg = order.avg_fill_price or 0.0
        prev_n = order.filled_qty - qty
        order.avg_fill_price = (prev_avg * prev_n + price * qty) / order.filled_qty
        order.status = (
            OrderStatus.FILLED if order.remaining_qty == 0 else OrderStatus.PARTIAL
        )
        self._emit_fill(fill)

    # --- reporting -------------------------------------------------------
    def equity(self) -> float:
        with self._lock:
            mtm = sum(
                p.qty * self._last_px.get(s, p.avg_price)
                for s, p in self._positions.items()
            )
            return self.cash + mtm

    def mark_price(self, symbol: str) -> float | None:
        return self._last_px.get(symbol)

    # --- persistence ----------------------------------------------------
    # A JSON-serializable snapshot so the gateway can rebuild the exact broker
    # after a restart. Append-only fill history lives inside it.
    def export_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "cash": self.cash,
                "starting_cash": self.starting_cash,
                "last_px": dict(self._last_px),
                "positions": [vars(p) for p in self._positions.values()],
                "orders": [_order_dict(o) for o in self._orders.values()],
                "fills": [_fill_dict(f) for f in self._fills],
            }

    @classmethod
    def from_state(cls, state: dict[str, Any], **cfg: Any) -> SimBroker:
        b = cls(cash=state.get("starting_cash", state.get("cash", 0)), **cfg)
        b.cash = state["cash"]
        b._last_px = {k: float(v) for k, v in state.get("last_px", {}).items()}
        for pd in state.get("positions", []):
            b._positions[pd["symbol"]] = Position(**pd)
        for fd in state.get("fills", []):
            b._fills.append(_fill_from_dict(fd))
        for od in state.get("orders", []):
            o = _order_from_dict(od)
            b._orders[o.broker_order_id] = o
            b._by_client[o.client_order_id] = o.broker_order_id
            if o.type is OrderType.LIMIT and o.status in (
                OrderStatus.PENDING,
                OrderStatus.PARTIAL,
            ):
                b._resting.append(o.broker_order_id)
        return b


def _order_dict(o: Order) -> dict[str, Any]:
    d = vars(o).copy()
    d["side"] = o.side.value
    d["type"] = o.type.value
    d["status"] = o.status.value
    return d


def _order_from_dict(d: dict[str, Any]) -> Order:
    d = d.copy()
    d["side"] = Side(d["side"])
    d["type"] = OrderType(d["type"])
    status = OrderStatus(d.pop("status"))
    filled = d.pop("filled_qty", 0)
    avg = d.pop("avg_fill_price", None)
    updated = d.pop("updated_ms", None)
    reject = d.pop("reject_reason", None)
    o = Order(**d)
    o.status, o.filled_qty, o.avg_fill_price = status, filled, avg
    if updated is not None:
        o.updated_ms = updated
    o.reject_reason = reject
    return o


def _fill_dict(f: Fill) -> dict[str, Any]:
    d = vars(f).copy()
    d["side"] = f.side.value
    return d


def _fill_from_dict(d: dict[str, Any]) -> Fill:
    d = d.copy()
    d["side"] = Side(d["side"])
    return Fill(**d)
