"""Core correctness: idempotency, fills, PnL, limit resting."""

from __future__ import annotations

from core import Order, SimBroker
from core.models import OrderStatus, OrderType, Quote, Side


def q(symbol, last, spread=10):
    return Quote(symbol=symbol, last=last, bid=last - spread / 2, ask=last + spread / 2)


def test_market_buy_then_sell_realizes_pnl():
    b = SimBroker(cash=1_000_000, fee_bps=0, slippage_bps=0)
    b.on_quote(q("A", 100))

    b.submit(Order(symbol="A", side=Side.BUY, qty=10, type=OrderType.MARKET))
    b.on_quote(q("A", 110))
    b.submit(Order(symbol="A", side=Side.SELL, qty=10, type=OrderType.MARKET))

    pos = b.positions()["A"]
    assert pos.qty == 0
    # bought ~100 (+0 slippage), sold ~110 -> +100 realized
    assert round(pos.realized_pnl) == 100
    assert len(b.fills()) == 2


def test_client_order_id_is_idempotent():
    b = SimBroker()
    b.on_quote(q("A", 100))
    o1 = Order(symbol="A", side=Side.BUY, qty=5, type=OrderType.MARKET, client_order_id="k1")
    r1 = b.submit(o1)
    r2 = b.submit(Order(symbol="A", side=Side.BUY, qty=5, type=OrderType.MARKET, client_order_id="k1"))
    assert r1.broker_order_id == r2.broker_order_id
    assert len(b.fills()) == 1


def test_limit_order_rests_then_fills_on_cross():
    b = SimBroker(fee_bps=0)
    b.on_quote(q("A", 100))
    o = b.submit(Order(symbol="A", side=Side.BUY, qty=10, type=OrderType.LIMIT, limit_price=95))
    assert o.status is OrderStatus.PENDING
    assert len(b.open_orders()) == 1

    b.on_quote(q("A", 96))          # not through yet
    assert b.get_order(o.broker_order_id).status is OrderStatus.PENDING

    b.on_quote(q("A", 94))          # ask now 99? no -> ask = 94+5 = 99 > 95 ... use tighter spread
    b.on_quote(Quote(symbol="A", last=94, bid=93, ask=94.5))
    filled = b.get_order(o.broker_order_id)
    assert filled.status is OrderStatus.FILLED
    assert filled.avg_fill_price <= 95


def test_short_sell_blocked_by_default():
    b = SimBroker()
    b.on_quote(q("A", 100))
    o = b.submit(Order(symbol="A", side=Side.SELL, qty=10, type=OrderType.MARKET))
    assert o.status is OrderStatus.REJECTED


def test_fills_since_filter():
    b = SimBroker(fee_bps=0)
    b.on_quote(q("A", 100))
    b.submit(Order(symbol="A", side=Side.BUY, qty=1, type=OrderType.MARKET))
    all_fills = b.fills()
    assert len(all_fills) == 1
    assert b.fills(since_ms=all_fills[0].ts_ms + 1) == []
