"""Risk gate + engine loop — deterministic, SimBroker + ReplayFeed."""

from __future__ import annotations

import json

from bot.config import Config
from bot.engine import Bot
from bot.risk import RiskGate
from core import ReplayFeed
from core.models import Order, OrderType, Position, Quote, Side
from core.strategy import Strategy


def cfg(tmp_path, **over):
    base = {
        "broker": "sim",
        "feed": "synthetic",
        "symbols": ["005930"],
        "kill_switch_file": str(tmp_path / "KILL"),
        "status_file": str(tmp_path / "status.json"),
        **over,
    }
    return Config(**base)


# --- RiskGate ---------------------------------------------------------
def _buy(qty=10):
    return Order(symbol="005930", side=Side.BUY, qty=qty, type=OrderType.MARKET)


def test_kill_file_blocks_everything(tmp_path):
    g = RiskGate(cfg(tmp_path))
    assert g.check(_buy(), book={}, marks={"005930": 70000}, session_pnl=0).ok
    g.arm_kill("test")
    assert not g.check(_buy(), book={}, marks={"005930": 70000}, session_pnl=0).ok


def test_max_order_qty(tmp_path):
    g = RiskGate(cfg(tmp_path, max_order_qty=50))
    assert not g.check(_buy(51), book={}, marks={"005930": 70000}, session_pnl=0).ok


def test_max_position_qty(tmp_path):
    g = RiskGate(cfg(tmp_path, max_position_qty=100))
    book = {"005930": Position(symbol="005930", qty=95, avg_price=70000)}
    assert not g.check(_buy(10), book=book, marks={"005930": 70000}, session_pnl=0).ok
    assert g.check(_buy(5), book=book, marks={"005930": 70000}, session_pnl=0).ok


def test_daily_loss_arms_kill(tmp_path):
    g = RiskGate(cfg(tmp_path, max_daily_loss=500_000))
    v = g.check(_buy(), book={}, marks={"005930": 70000}, session_pnl=-600_000)
    assert not v.ok
    assert g.kill_armed()                      # persisted for the next restart


def test_gross_notional_cap(tmp_path):
    g = RiskGate(cfg(tmp_path, max_gross_notional=1_000_000))
    v = g.check(_buy(100), book={}, marks={"005930": 70_000}, session_pnl=0)
    assert not v.ok and "gross" in v.reason


# --- engine ----------------------------------------------------------
class BuyThenSell(Strategy):
    """Emits one BUY on the 2nd tick, one SELL on the 5th."""

    def __init__(self):
        self.n = 0

    def on_quote(self, quote, positions):
        self.n += 1
        if self.n == 2:
            return [Order(symbol=quote.symbol, side=Side.BUY, qty=10, type=OrderType.MARKET)]
        if self.n == 5:
            return [Order(symbol=quote.symbol, side=Side.SELL, qty=10, type=OrderType.MARKET)]
        return []


def _quotes(symbol, prices):
    return [Quote(symbol=symbol, last=p, bid=p - 5, ask=p + 5) for p in prices]


def build_bot(tmp_path, strategy, quotes, **over):
    bot = Bot(cfg(tmp_path, **over))
    bot.feed = ReplayFeed(quotes)
    bot.strategy = strategy
    return bot


def test_engine_runs_strategy_through_broker(tmp_path):
    bot = build_bot(
        tmp_path, BuyThenSell(),
        _quotes("005930", [70_000, 70_100, 70_500, 71_000, 71_500, 72_000]),
    )
    bot.run()
    assert bot._submitted == 2
    assert bot._fills == 2
    assert bot.book["005930"].qty == 0
    assert bot.session_pnl() > 0               # bought ~70.1k, sold ~71.5k

    status = json.loads((tmp_path / "status.json").read_text())
    assert status["running"] is False and status["fills"] == 2


def test_engine_blocks_when_over_position_limit(tmp_path):
    bot = build_bot(
        tmp_path, BuyThenSell(),
        _quotes("005930", [70_000] * 6),
        max_position_qty=5,                    # lot is 10 -> BUY blocked
    )
    bot.run()
    assert bot._submitted == 0 and bot._blocked >= 1
    assert "005930" not in bot.book or bot.book["005930"].qty == 0


def test_engine_halts_on_kill_file(tmp_path):
    strat = BuyThenSell()
    bot = build_bot(tmp_path, strat, _quotes("005930", [70_000] * 10))
    # arm kill before the SELL tick
    orig = strat.on_quote

    def wrapped(q, p):
        if strat.n == 3:
            bot.risk.arm_kill("mid-run")
        return orig(q, p)

    strat.on_quote = wrapped
    bot.run()
    assert bot._stop.is_set()
    assert bot._submitted == 1                 # BUY on tick 2 went through, then halted


def test_bot_refuses_to_start_when_kill_armed(tmp_path):
    bot = build_bot(tmp_path, BuyThenSell(), _quotes("005930", [70_000] * 4))
    bot.risk.arm_kill("pre-armed")
    bot.run()
    assert bot._submitted == 0 and bot._fills == 0
