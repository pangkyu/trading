"""NH connectivity helpers shared by NHFeed and NHBroker.

Everything NH-specific that isn't a Broker or a Feed lives here: environment
detection, account selection, and the field maps between NH's wire format and
our :mod:`core.models` types.

``nhplug`` (Python >=3.11) is an optional dependency; importing this module
requires it.
"""

from __future__ import annotations

import datetime as _dt

import nhplug

from .models import Fill, Order, OrderType, Quote, Side

# NH 성공코드는 nhplug.call() 이 이미 판정한다. 여기서는 매핑만.

LIVE_HOSTS = ("api.nhplug.com", "api.n2plug.com")
MOCK_HOSTS = ("moapi.nhplug.com", "moapi.n2plug.com")


def current_env() -> str:
    """'live' or 'mock', derived from NHPLUG_BASE_URL (SDK's single source)."""
    base = nhplug.get_base_url()
    if any(h in base for h in MOCK_HOSTS):
        return "mock"
    if any(h in base for h in LIVE_HOSTS):
        return "live"
    raise RuntimeError(f"cannot classify NHPLUG_BASE_URL: {base}")


def usable_accounts() -> list[dict]:
    """Accounts from /n2/acctinfo filtered to the ones valid for the current env.

    live -> acct_type in {01, 02}; mock -> acct_type == 03.
    """
    env = current_env()
    want = {"01", "02"} if env == "live" else {"03"}
    resp = nhplug.call("/n2/acctinfo", {})
    rows = resp.get("Output_0", []) or []
    return [r for r in rows if r.get("acct_type") in want]


def resolve_account(act_no: str | None = None) -> str:
    """Pick the account to trade. Explicit act_no wins; otherwise the sole
    env-appropriate account. Refuses to guess when several are available.
    """
    accts = usable_accounts()
    if act_no:
        if act_no not in {a["acct_no"] for a in accts}:
            raise ValueError(
                f"account {act_no} not valid for {current_env()} env "
                f"(available: {[a['acct_no'] for a in accts]})"
            )
        return act_no
    if not accts:
        raise RuntimeError(f"no {current_env()} accounts on this app key")
    if len(accts) > 1:
        raise RuntimeError(
            f"multiple {current_env()} accounts; pass act_no explicitly: "
            f"{[a['acct_no'] for a in accts]}"
        )
    return accts[0]["acct_no"]


# --- wire <-> model maps -------------------------------------------------------

# realtime 체결가 통합 채널 (mc). 호가잔량은 이 채널에 없다(호가는 ob/mb).
def quote_from_mc(body: dict[str, str]) -> Quote:
    def num(key: str) -> float | None:
        v = body.get(key)
        return float(v) if v not in (None, "") else None

    hhmmss = body.get("time")  # "14:00:31"
    ts_ms = _clock_to_ms(hhmmss) if hhmmss else None
    return Quote(
        symbol=body["code"],
        ts_ms=ts_ms or _now_ms(),
        last=num("price"),
        bid=num("bid"),
        ask=num("offer"),
    )


def _clock_to_ms(hhmmss: str) -> int:
    today = _dt.date.today()
    parts = hhmmss.replace(":", "")
    h, m, s = int(parts[0:2]), int(parts[2:4]), int(parts[4:6])
    dt = _dt.datetime.combine(today, _dt.time(h, m, s))
    return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


# 호가유형코드 (nmn_pr_tp_cd): 01 보통가(지정가), 05 시장가
_PRICE_TYPE = {OrderType.LIMIT: "01", OrderType.MARKET: "05"}
# 주문조건 (orr_cnd_dit_cd): 00 없음, 01 IOC, 02 FOK
_TIF_NONE = "00"


def order_to_params(order: Order, act_no: str, *, market: str = "KRX") -> dict[str, object]:
    """Order -> cashBuy/cashSell Input_0. Caller picks the endpoint by side."""
    params: dict[str, object] = {
        "act_no": act_no,
        "iem_cd": order.symbol,
        "orr_qty": order.qty,
        "nmn_pr_tp_cd": _PRICE_TYPE[order.type],
        "orr_cnd_dit_cd": _TIF_NONE,
        "ssl_nmn_pr_dit_cd": "00",          # 정상 (not short)
        "rmt_mkt_cd": market,               # SOR / KRX / NXT
        "sor_mkt_sli_yn": "N",
    }
    if order.type is OrderType.LIMIT:
        if order.limit_price is None:
            raise ValueError("limit order without limit_price")
        params["orr_pr"] = round(order.limit_price)   # 원 단위 정수
    return params


def endpoint_for(side: Side) -> str:
    return "/krstock/order/v1/cashBuy" if side is Side.BUY else "/krstock/order/v1/cashSell"


def _side_from_name(name: str) -> Side:
    # sby_dit_cd_nm: "현금매수" / "현금매도" / "신용매도" ...
    return Side.SELL if "매도" in name else Side.BUY


def fills_from_daily_execution(rows: list[dict], orr_dt: str) -> list[Fill]:
    """dailyOrderExecution Output_1 -> Fill list (order-level aggregate).

    Only rows with an actual executed quantity are returned. This is the
    '매매 기록' view, not a tick-by-tick fill log.
    """
    out: list[Fill] = []
    for r in rows:
        qty = int(r.get("tot_cns_qty") or 0)
        if qty <= 0:
            continue
        price = float(r.get("cns_avg_uit_pr") or 0)
        tm = str(r.get("orr_tm") or "000000")[:6]
        out.append(
            Fill(
                order_id=str(r.get("itg_orr_no", "")),
                client_order_id="",
                symbol=str(r.get("iem_cd", "")).strip(),
                side=_side_from_name(str(r.get("sby_dit_cd_nm", ""))),
                qty=qty,
                price=price,
                ts_ms=_clock_to_ms(f"{tm[0:2]}:{tm[2:4]}:{tm[4:6]}")
                if len(tm) >= 6
                else _now_ms(),
            )
        )
    return out
