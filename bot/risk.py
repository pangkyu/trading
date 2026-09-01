"""Pre-trade risk gate. Every order the strategy emits passes through here
before it can reach the broker. A breach of the daily-loss limit also *arms*
the kill switch so a restart won't resume trading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

from core.models import Order, Position, Side

from .config import Config

log = logging.getLogger("bot.risk")

_KRX_OPEN = time(9, 0)
_KRX_CLOSE = time(15, 30)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


class RiskGate:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._kill = Path(cfg.kill_switch_file)

    # --- kill switch ---------------------------------------------------
    def kill_armed(self) -> bool:
        return self._kill.exists()

    def arm_kill(self, why: str) -> None:
        self._kill.parent.mkdir(parents=True, exist_ok=True)
        self._kill.write_text(f"{datetime.now().isoformat()} {why}\n")
        log.critical("KILL SWITCH ARMED: %s", why)

    # --- the check ---------------------------------------------------
    def check(
        self,
        order: Order,
        *,
        book: dict[str, Position],
        marks: dict[str, float],
        session_pnl: float,
    ) -> Verdict:
        if self.kill_armed():
            return Verdict(False, "kill switch armed")

        if session_pnl <= -self.cfg.max_daily_loss:
            self.arm_kill(f"daily loss {session_pnl:,.0f} <= -{self.cfg.max_daily_loss:,.0f}")
            return Verdict(False, "daily loss limit breached")

        if self.cfg.enforce_market_hours and not self._market_open():
            return Verdict(False, "market closed")

        if order.qty > self.cfg.max_order_qty:
            return Verdict(False, f"order qty {order.qty} > max {self.cfg.max_order_qty}")

        held = book.get(order.symbol)
        cur = held.qty if held else 0
        signed = order.qty if order.side is Side.BUY else -order.qty
        projected = abs(cur + signed)
        if projected > self.cfg.max_position_qty:
            return Verdict(
                False,
                f"{order.symbol} position would be {projected} > max {self.cfg.max_position_qty}",
            )

        mark = marks.get(order.symbol)
        if mark:
            gross = sum(
                abs(p.qty) * marks.get(s, p.avg_price) for s, p in book.items()
            )
            gross += order.qty * mark  # rough upper bound for the new order
            if gross > self.cfg.max_gross_notional:
                return Verdict(
                    False,
                    f"gross notional {gross:,.0f} > max {self.cfg.max_gross_notional:,.0f}",
                )

        return Verdict(True)

    # --- helpers ---------------------------------------------------
    @staticmethod
    def _market_open() -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        return _KRX_OPEN <= now.time() <= _KRX_CLOSE
