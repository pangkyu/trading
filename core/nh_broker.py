"""NH-backed Broker: routes orders to NH 모의투자 (moapi) or 실거래 (api).

Which environment is decided entirely by ``NHPLUG_BASE_URL`` (the SDK's single
switch), exactly like every other nhplug call. ``NHMockBroker`` / ``LiveBroker``
are thin aliases that additionally assert the env matches, so a misconfigured
.env fails loudly instead of trading in the wrong place.

Safety:
* ``dry_run=True`` by default — orders are logged and validated but NOT sent.
* NH order entry is asynchronous: ``submit()`` returns once NH *accepts* the
  order (status PENDING). Fills arrive later — subscribe to the ``d2`` channel,
  or call :meth:`reconcile` which pulls today's 체결 from dailyOrderExecution.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date

import nhplug

from .broker import Broker
from .models import Fill, Order, OrderStatus, Position, new_id
from .nh import (
    current_env,
    endpoint_for,
    fills_from_daily_execution,
    order_to_params,
    resolve_account,
)

log = logging.getLogger("core.nh_broker")

_DAILY_EXEC = "/krstock/inquiry/v1/dailyOrderExecution"
_BALANCE = "/krstock/inquiry/v1/balance"
_CANCEL = "/krstock/order/v1/cancel"


class NHBroker(Broker):
    def __init__(
        self,
        *,
        act_no: str | None = None,
        market: str = "KRX",
        dry_run: bool = True,
        expect_env: str | None = None,   # "mock" | "live" | None
        verify_account: bool = True,     # False + explicit act_no -> skip the /n2/acctinfo call
    ) -> None:
        super().__init__()
        env = current_env()
        if expect_env and env != expect_env:
            raise RuntimeError(
                f"NHPLUG_BASE_URL is '{env}' but this broker requires '{expect_env}'"
            )
        self.env = env
        self.market = market
        self.dry_run = dry_run
        # NH mock keys carry a tight APP+API daily quota (IGW42903); skip the
        # account lookup when the caller already knows the number.
        if act_no and not verify_account:
            self.act_no = act_no
        else:
            self.act_no = resolve_account(act_no)
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}          # broker_order_id -> Order
        self._by_client: dict[str, str] = {}         # client_order_id -> broker_order_id
        self._seen_exec: set[str] = set()            # itg_orr_no already turned into a Fill

        log.info(
            "NHBroker ready env=%s account=%s dry_run=%s", self.env, self.act_no, self.dry_run
        )

    # --- Broker API ---------------------------------------------------------
    def submit(self, order: Order) -> Order:
        with self._lock:
            if order.client_order_id in self._by_client:
                return self._orders[self._by_client[order.client_order_id]]

            params = order_to_params(order, self.act_no, market=self.market)
            path = endpoint_for(order.side)

            if self.dry_run:
                order.broker_order_id = new_id("dry")
                order.status = OrderStatus.PENDING
                log.warning("DRY-RUN %s %s %s", order.side.value, path, params)
            else:
                log.info("SUBMIT %s %s %s", order.side.value, path, params)
                try:
                    resp = nhplug.call(path, params)
                except nhplug.NhplugError as e:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = f"[{e.category}] {e.code or ''} {e.message}".strip()
                    log.error("REJECTED %s: %s", order.client_order_id, order.reject_reason)
                    self._track(order)
                    return order
                out = resp.get("Output_0", {}) or {}
                order.broker_order_id = str(
                    out.get("mkt_orr_no")
                    or out.get("anw_cld_mkt_orr_no1")
                    or new_id("ord")
                )
                order.status = OrderStatus.PENDING
                log.info("ACCEPTED %s -> mkt_orr_no=%s", order.client_order_id, order.broker_order_id)

            self._track(order)
            return order

    def cancel(self, broker_order_id: str) -> Order:
        with self._lock:
            order = self._orders.get(broker_order_id)
            if order is None:
                raise KeyError(broker_order_id)
            if self.dry_run:
                order.status = OrderStatus.CANCELED
                return order
            nhplug.call(
                _CANCEL,
                {
                    "act_no": self.act_no,
                    "org_mkt_orr_no": broker_order_id,
                    "all_pat_dit_cd": "1",            # 전량
                    "iem_cd": order.symbol,
                },
            )
            order.status = OrderStatus.CANCELED
            return order

    def get_order(self, broker_order_id: str) -> Order | None:
        return self._orders.get(broker_order_id)

    def open_orders(self) -> list[Order]:
        rows = self._daily_rows(ost_cns_dit="1")   # 미체결
        # return tracked orders that still have unfilled qty per NH
        live_ids = {str(r.get("itg_orr_no")) for r in rows if int(r.get("ny_cns_qty") or 0) > 0}
        with self._lock:
            return [o for o in self._orders.values() if o.broker_order_id in live_ids]

    def positions(self) -> dict[str, Position]:
        resp = nhplug.call(
            _BALANCE,
            {
                "act_no": self.act_no,
                "bnc_bse_cd": "1",
                "ltg_aot_dit_cd": "1",
                "aet_bse": "1",
                "qut_dit_cd": "UNT",
            },
        )
        out: dict[str, Position] = {}
        for r in resp.get("Output_1", []) or []:
            qty = int(float(r.get("itg_bnc_qty") or 0))
            if qty == 0:
                continue
            sym = str(r.get("iem_cd", "")).strip()
            out[sym] = Position(
                symbol=sym,
                qty=qty,
                avg_price=float(r.get("phs_pr") or 0),
                realized_pnl=float(r.get("sll_pls_amt") or 0),
            )
        return out

    def fills(self, since_ms: int = 0) -> list[Fill]:
        return [f for f in self._fills_for(date.today()) if f.ts_ms >= since_ms]

    # --- NH-specific extras ------------------------------------------------
    def fills_between(self, start: date, end: date, *, skip_weekends: bool = True,
                      pause_s: float = 0.3) -> list[Fill]:
        """Trade history over a date range — one dailyOrderExecution call per day.

        NH enforces an APP+API transaction-count quota (IGW42903) well below the
        per-second rate limit, so keep ranges tight and let the gateway (M3)
        cache days that won't change. ``pause_s`` spaces the calls out.
        """
        out: list[Fill] = []
        d = start
        while d <= end:
            if not (skip_weekends and d.weekday() >= 5):
                out.extend(self._fills_for(d))
                if d < end:
                    time.sleep(pause_s)
            d = date.fromordinal(d.toordinal() + 1)
        return out

    def reconcile(self) -> list[Fill]:
        """Pull today's executions, update tracked order status, emit new fills."""
        new: list[Fill] = []
        for f in self._fills_for(date.today()):
            if f.order_id in self._seen_exec:
                continue
            self._seen_exec.add(f.order_id)
            with self._lock:
                order = self._orders.get(f.order_id)
                if order is not None:
                    order.filled_qty = f.qty
                    order.avg_fill_price = f.price
                    order.status = (
                        OrderStatus.FILLED
                        if f.qty >= order.qty
                        else OrderStatus.PARTIAL
                    )
            self._emit_fill(f)
            new.append(f)
        return new

    # --- internals -------------------------------------------------------
    def _track(self, order: Order) -> None:
        assert order.broker_order_id
        self._orders[order.broker_order_id] = order
        self._by_client[order.client_order_id] = order.broker_order_id

    def _daily_rows(self, *, ost_cns_dit: str, orr_dt: str | None = None) -> list[dict]:
        d = orr_dt or date.today().strftime("%Y%m%d")
        rows: list[dict] = []
        for page in nhplug.paginate(
            _DAILY_EXEC,
            {
                "orr_dt": d,
                "act_no": self.act_no,
                "ost_cns_dit": ost_cns_dit,
                "orr_mkt_cd": "00",
            },
        ):
            rows.extend(page.get("Output_1", []) or [])
        return rows

    def _fills_for(self, d: date) -> list[Fill]:
        s = d.strftime("%Y%m%d")
        return fills_from_daily_execution(self._daily_rows(ost_cns_dit="2", orr_dt=s), s)


class NHMockBroker(NHBroker):
    def __init__(self, **kw) -> None:
        kw.setdefault("expect_env", "mock")
        super().__init__(**kw)


class LiveBroker(NHBroker):
    def __init__(self, **kw) -> None:
        kw.setdefault("expect_env", "live")
        # 실거래는 dry_run 기본값을 유지하되, 무인 실행 시 명시적으로 꺼야 한다.
        super().__init__(**kw)
