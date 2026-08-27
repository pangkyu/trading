"""FastAPI gateway: one NH connection + SimBroker paper accounts, over REST + WS.

Run:  uvicorn gateway.app:app --reload
Env:  GATEWAY_FEED=synthetic|nh  GATEWAY_SYMBOLS=005930,000660  GATEWAY_DB=data/gateway.sqlite
      GATEWAY_NH_ACCOUNT=... GATEWAY_NH_DRY_RUN=1   (NH routes; omit account to disable)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.models import Order, OrderType, Side

from . import config, serialize
from .db import DB
from .hub import Hub

log = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config.load()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = DB(cfg.db_path)
    hub = Hub(cfg, db)
    hub.start(asyncio.get_running_loop())
    app.state.hub = hub
    app.state.db = db
    try:
        yield
    finally:
        hub.stop()
        db.close()


app = FastAPI(title="trading gateway", lifespan=lifespan)


# --- request bodies --------------------------------------------------------
class NewSimAccount(BaseModel):
    name: str
    cash: float | None = None


class NewOrder(BaseModel):
    symbol: str
    side: Side
    qty: int = Field(gt=0)
    type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    client_order_id: str | None = None

    def to_order(self) -> Order:
        kw = {
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "type": self.type,
            "limit_price": self.limit_price,
        }
        if self.client_order_id:
            kw["client_order_id"] = self.client_order_id
        return Order(**kw)


# --- health / quotes -----------------------------------------------------
@app.get("/health")
def health() -> dict:
    h = app.state.hub
    return {"ok": True, "feed": h.cfg.feed, "symbols": h.cfg.symbols,
            "sim_accounts": len(h.list_sims()), "nh": h.nh is not None}


@app.get("/quotes")
def quotes() -> dict:
    return {s: serialize.quote(q) for s, q in app.state.hub.all_quotes().items()}


@app.get("/quotes/{symbol}")
def quote_one(symbol: str) -> dict:
    q = app.state.hub.latest(symbol)
    if q is None:
        raise HTTPException(404, f"no quote for {symbol}")
    return serialize.quote(q)


@app.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket) -> None:
    await ws.accept()
    wanted = ws.query_params.get("symbols")
    allow = {s.strip() for s in wanted.split(",")} if wanted else None
    h = app.state.hub
    q = h.subscribe()
    try:
        for sym, quote in h.all_quotes().items():          # prime with snapshot
            if allow is None or sym in allow:
                await ws.send_json(serialize.quote(quote))
        while True:
            quote = await q.get()
            if allow is None or quote.symbol in allow:
                await ws.send_json(serialize.quote(quote))
    except WebSocketDisconnect:
        pass
    finally:
        h.unsubscribe(q)


# --- sim accounts ------------------------------------------------------
@app.post("/sim/accounts", status_code=201)
def create_sim(body: NewSimAccount) -> dict:
    acct_id = app.state.hub.create_sim(body.name, body.cash)
    return {"id": acct_id}


@app.get("/sim/accounts")
def list_sim() -> list[dict]:
    h = app.state.hub
    return [serialize.sim_summary(a, h.sim_name(a), h.sim(a)) for a in h.list_sims()]


def _sim_or_404(acct_id: str):
    try:
        return app.state.hub.sim(acct_id)
    except KeyError:
        raise HTTPException(404, f"no sim account {acct_id}") from None


@app.get("/sim/accounts/{acct_id}")
def get_sim(acct_id: str) -> dict:
    h = app.state.hub
    b = _sim_or_404(acct_id)
    out = serialize.sim_summary(acct_id, h.sim_name(acct_id), b)
    out["positions"] = [
        serialize.position(p, b.mark_price(s)) for s, p in b.positions().items()
    ]
    return out


@app.delete("/sim/accounts/{acct_id}", status_code=204)
def delete_sim(acct_id: str) -> None:
    _sim_or_404(acct_id)
    app.state.hub.delete_sim(acct_id)


@app.post("/sim/accounts/{acct_id}/orders", status_code=201)
def submit_sim_order(acct_id: str, body: NewOrder) -> dict:
    b = _sim_or_404(acct_id)
    try:
        o = b.submit(body.to_order())
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    app.state.hub.persist_sim(acct_id)
    return serialize.order(o)


@app.get("/sim/accounts/{acct_id}/orders")
def list_sim_orders(acct_id: str, open_only: bool = False) -> list[dict]:
    b = _sim_or_404(acct_id)
    orders = b.open_orders() if open_only else b._orders.values()
    return [serialize.order(o) for o in orders]


@app.post("/sim/accounts/{acct_id}/orders/{broker_order_id}/cancel")
def cancel_sim_order(acct_id: str, broker_order_id: str) -> dict:
    b = _sim_or_404(acct_id)
    try:
        o = b.cancel(broker_order_id)
    except KeyError:
        raise HTTPException(404, "no such order") from None
    app.state.hub.persist_sim(acct_id)
    return serialize.order(o)


@app.get("/sim/accounts/{acct_id}/fills")
def sim_fills(acct_id: str, since_ms: int = 0) -> list[dict]:
    b = _sim_or_404(acct_id)
    return [serialize.fill(f) for f in b.fills(since_ms)]


# --- NH (the bot's account) ------------------------------------------
@app.get("/nh/status")
def nh_status() -> dict:
    nh = app.state.hub.nh
    if nh is None:
        return {"enabled": False}
    return {"enabled": True, "env": nh.env, "account": nh.act_no, "dry_run": nh.dry_run}


def _nh_or_404():
    nh = app.state.hub.nh
    if nh is None:
        raise HTTPException(404, "NH broker not configured (set GATEWAY_NH_ACCOUNT)")
    return nh


@app.get("/nh/positions")
def nh_positions() -> list[dict]:
    nh = _nh_or_404()
    return [serialize.position(p, None) for p in nh.positions().values()]


@app.get("/nh/fills")
def nh_fills(start: str | None = None, end: str | None = None) -> list[dict]:
    """Trade history. start/end are YYYY-MM-DD; default = today only.

    Days are served from the SQLite cache first to protect the NH quota.
    """
    nh = _nh_or_404()
    h = app.state.hub
    d0 = date.fromisoformat(start) if start else date.today()
    d1 = date.fromisoformat(end) if end else d0
    out: list[dict] = []
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            out.extend(_nh_fills_for_day(nh, h, d))
        d = date.fromordinal(d.toordinal() + 1)
    return out


def _nh_fills_for_day(nh, h: Hub, d: date) -> list[dict]:
    key = d.strftime("%Y%m%d")
    cached = h.db.get_nh_history(nh.act_no, key, h.cfg.nh_history_ttl_s)
    if cached is not None:
        from core.nh import fills_from_daily_execution

        return [serialize.fill(f) for f in fills_from_daily_execution(cached, key)]
    rows = nh._daily_rows(ost_cns_dit="2", orr_dt=key)
    h.db.put_nh_history(nh.act_no, key, rows)
    from core.nh import fills_from_daily_execution

    return [serialize.fill(f) for f in fills_from_daily_execution(rows, key)]


@app.post("/nh/orders", status_code=201)
def nh_submit(body: NewOrder) -> dict:
    nh = _nh_or_404()
    o = nh.submit(body.to_order())
    return serialize.order(o)
