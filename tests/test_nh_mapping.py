"""Pure wire<->model mapping tests for the NH layer (no network, no credentials).

Skipped entirely if nhplug isn't installed (Python <3.11 / core-only checkout).
"""

from __future__ import annotations

import pytest

nh = pytest.importorskip("core.nh")

from core.models import Order, OrderType, Side


def test_quote_from_mc_channel():
    body = {
        "code": "005930",
        "time": "14:00:31",
        "price": "78500",
        "bid": "78400",
        "offer": "78600",
    }
    q = nh.quote_from_mc(body)
    assert q.symbol == "005930"
    assert q.last == 78500 and q.bid == 78400 and q.ask == 78600
    assert q.mid == 78500  # (78400 + 78600) / 2


def test_order_to_params_market_buy():
    o = Order(symbol="005930", side=Side.BUY, qty=10, type=OrderType.MARKET)
    p = nh.order_to_params(o, "12345678901", market="KRX")
    assert p["act_no"] == "12345678901"
    assert p["iem_cd"] == "005930"
    assert p["orr_qty"] == 10
    assert p["nmn_pr_tp_cd"] == "05"        # 시장가
    assert "orr_pr" not in p
    assert nh.endpoint_for(Side.BUY).endswith("cashBuy")


def test_order_to_params_limit_sell_uses_integer_won():
    o = Order(symbol="000660", side=Side.SELL, qty=3, type=OrderType.LIMIT, limit_price=175_450.7)
    p = nh.order_to_params(o, "12345678901")
    assert p["nmn_pr_tp_cd"] == "01"        # 보통가(지정가)
    assert p["orr_pr"] == 175451 and isinstance(p["orr_pr"], int)
    assert nh.endpoint_for(Side.SELL).endswith("cashSell")


def test_fills_from_daily_execution_filters_and_maps_side():
    rows = [
        {"itg_orr_no": 30, "iem_cd": "005930 ", "sby_dit_cd_nm": "현금매수",
         "tot_cns_qty": 10, "cns_avg_uit_pr": 78200.0, "orr_tm": "090512"},
        {"itg_orr_no": 31, "iem_cd": "005930", "sby_dit_cd_nm": "현금매도",
         "tot_cns_qty": 0, "cns_avg_uit_pr": 0.0, "orr_tm": "091000"},   # unfilled -> dropped
        {"itg_orr_no": 32, "iem_cd": "000660", "sby_dit_cd_nm": "신용매도",
         "tot_cns_qty": 5, "cns_avg_uit_pr": 175000.0, "orr_tm": "100000"},
    ]
    fills = nh.fills_from_daily_execution(rows, "20260827")
    assert [f.order_id for f in fills] == ["30", "32"]
    assert fills[0].symbol == "005930" and fills[0].side is Side.BUY and fills[0].qty == 10
    assert fills[1].side is Side.SELL and fills[1].price == 175000.0
