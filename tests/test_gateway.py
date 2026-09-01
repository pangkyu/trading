"""Gateway API tests — manual feed, temp SQLite, deterministic."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from core.models import Quote


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_FEED", "manual")
    monkeypatch.setenv("GATEWAY_DB", str(tmp_path / "gw.sqlite"))
    monkeypatch.setenv("GATEWAY_SYMBOLS", "005930,000660")
    monkeypatch.setenv("GATEWAY_BOT_STATUS_FILE", str(tmp_path / "bot-status.json"))
    monkeypatch.setenv("GATEWAY_BOT_KILL_FILE", str(tmp_path / "KILL"))
    monkeypatch.delenv("GATEWAY_NH_ACCOUNT", raising=False)
    import gateway.app as appmod

    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        c.app = appmod.app
        yield c


def push(client, symbol, last, spread=10):
    client.app.state.hub.push_quote(
        Quote(symbol=symbol, last=last, bid=last - spread / 2, ask=last + spread / 2)
    )


def test_health_and_empty_state(client):
    r = client.get("/health").json()
    assert r["ok"] and r["feed"] == "manual" and r["nh"] is False


def test_market_order_fills_and_books_pnl(client):
    acct = client.post("/sim/accounts", json={"name": "kim", "cash": 10_000_000}).json()["id"]
    push(client, "005930", 70_000)

    o = client.post(
        f"/sim/accounts/{acct}/orders",
        json={"symbol": "005930", "side": "BUY", "qty": 10, "type": "MARKET"},
    ).json()
    assert o["status"] == "FILLED" and o["filled_qty"] == 10

    push(client, "005930", 77_000)
    client.post(
        f"/sim/accounts/{acct}/orders",
        json={"symbol": "005930", "side": "SELL", "qty": 10, "type": "MARKET"},
    )

    detail = client.get(f"/sim/accounts/{acct}").json()
    assert detail["positions"] == [] or detail["positions"][0]["qty"] == 0
    assert detail["pnl"] > 0                       # bought ~70k, sold ~77k
    fills = client.get(f"/sim/accounts/{acct}/fills").json()
    assert len(fills) == 2


def test_limit_order_rests_then_fills_on_quote(client):
    acct = client.post("/sim/accounts", json={"name": "lee"}).json()["id"]
    push(client, "000660", 200_000)
    o = client.post(
        f"/sim/accounts/{acct}/orders",
        json={"symbol": "000660", "side": "BUY", "qty": 5, "type": "LIMIT", "limit_price": 190_000},
    ).json()
    assert o["status"] == "PENDING"
    assert len(client.get(f"/sim/accounts/{acct}/orders?open_only=true").json()) == 1

    push(client, "000660", 189_000)               # trades through the limit
    filled = client.get(f"/sim/accounts/{acct}/orders").json()[0]
    assert filled["status"] == "FILLED"


def test_idempotent_client_order_id(client):
    acct = client.post("/sim/accounts", json={"name": "park"}).json()["id"]
    push(client, "005930", 70_000)
    body = {"symbol": "005930", "side": "BUY", "qty": 1, "type": "MARKET",
            "client_order_id": "abc-123"}
    a = client.post(f"/sim/accounts/{acct}/orders", json=body).json()
    b = client.post(f"/sim/accounts/{acct}/orders", json=body).json()
    assert a["broker_order_id"] == b["broker_order_id"]
    assert len(client.get(f"/sim/accounts/{acct}/fills").json()) == 1


def test_state_survives_restart(client, tmp_path, monkeypatch):
    acct = client.post("/sim/accounts", json={"name": "survivor", "cash": 5_000_000}).json()["id"]
    push(client, "005930", 60_000)
    client.post(
        f"/sim/accounts/{acct}/orders",
        json={"symbol": "005930", "side": "BUY", "qty": 3, "type": "MARKET"},
    )
    before = client.get(f"/sim/accounts/{acct}").json()

    # fresh app instance, same DB file
    import gateway.app as appmod

    importlib.reload(appmod)
    with TestClient(appmod.app) as c2:
        after = c2.get(f"/sim/accounts/{acct}").json()
    assert after["cash"] == before["cash"]
    assert after["name"] == "survivor"
    fills = None
    with TestClient(appmod.app) as c3:
        fills = c3.get(f"/sim/accounts/{acct}/fills").json()
    assert len(fills) == 1 and fills[0]["qty"] == 3


def test_ws_quotes_streams(client):
    push(client, "005930", 71_000)
    with client.websocket_connect("/ws/quotes?symbols=005930") as ws:
        first = ws.receive_json()                  # primed snapshot
        assert first["symbol"] == "005930"
        push(client, "005930", 71_500)
        nxt = ws.receive_json()
        assert nxt["last"] == 71_500


def test_nh_routes_disabled_without_account(client):
    assert client.get("/nh/status").json() == {"enabled": False}
    assert client.get("/nh/positions").status_code == 404


def test_bot_status_absent_then_present(client, tmp_path):
    r = client.get("/bot/status").json()
    assert r["present"] is False and r["kill_armed"] is False

    (tmp_path / "bot-status.json").write_text(
        '{"broker":"sim","session_pnl":1234,"submitted":3,"blocked":0,"fills":2,'
        '"uptime_s":42,"positions":{}}',
    )
    r = client.get("/bot/status").json()
    assert r["present"] is True and r["stale"] is False
    assert r["session_pnl"] == 1234 and r["broker"] == "sim"


def test_bot_kill_arm_and_disarm(client):
    assert client.get("/bot/kill").json()["armed"] is False
    client.post("/bot/kill", json={"reason": "test stop"})
    got = client.get("/bot/kill").json()
    assert got["armed"] is True and "test stop" in got["detail"]
    assert client.get("/bot/status").json()["kill_armed"] is True
    assert client.delete("/bot/kill").status_code == 204
    assert client.get("/bot/kill").json()["armed"] is False
