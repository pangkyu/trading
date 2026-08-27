"""core model -> JSON-friendly dict."""

from __future__ import annotations

from typing import Any

from core import SimBroker
from core.models import Fill, Order, Position, Quote


def quote(q: Quote) -> dict[str, Any]:
    return {
        "symbol": q.symbol,
        "ts_ms": q.ts_ms,
        "last": q.last,
        "bid": q.bid,
        "ask": q.ask,
        "bid_size": q.bid_size,
        "ask_size": q.ask_size,
    }


def order(o: Order) -> dict[str, Any]:
    return {
        "client_order_id": o.client_order_id,
        "broker_order_id": o.broker_order_id,
        "symbol": o.symbol,
        "side": o.side.value,
        "type": o.type.value,
        "qty": o.qty,
        "limit_price": o.limit_price,
        "status": o.status.value,
        "filled_qty": o.filled_qty,
        "avg_fill_price": o.avg_fill_price,
        "reject_reason": o.reject_reason,
        "created_ms": o.created_ms,
    }


def fill(f: Fill) -> dict[str, Any]:
    return {
        "fill_id": f.fill_id,
        "order_id": f.order_id,
        "client_order_id": f.client_order_id,
        "symbol": f.symbol,
        "side": f.side.value,
        "qty": f.qty,
        "price": f.price,
        "fee": f.fee,
        "ts_ms": f.ts_ms,
    }


def position(p: Position, mark: float | None) -> dict[str, Any]:
    return {
        "symbol": p.symbol,
        "qty": p.qty,
        "avg_price": p.avg_price,
        "mark": mark,
        "realized_pnl": p.realized_pnl,
        "unrealized_pnl": p.unrealized_pnl(mark) if mark is not None else None,
    }


def sim_summary(acct_id: str, name: str, b: SimBroker) -> dict[str, Any]:
    return {
        "id": acct_id,
        "name": name,
        "cash": round(b.cash, 2),
        "starting_cash": b.starting_cash,
        "equity": round(b.equity(), 2),
        "pnl": round(b.equity() - b.starting_cash, 2),
        "open_orders": len(b.open_orders()),
        "trades": len(b.fills()),
    }
