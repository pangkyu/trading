"""Strategy interface.

A strategy is a (mostly) pure function of market state -> desired orders. Keeping
it free of I/O means the identical code runs in a backtest, in the SimBroker web
service, and in the live bot.
"""

from __future__ import annotations

import abc
from collections import defaultdict, deque
from typing import Deque, Dict, List

from .models import Order, OrderType, Side
from .models import Quote


class Strategy(abc.ABC):
    @abc.abstractmethod
    def on_quote(self, quote: Quote, positions: Dict[str, int]) -> List[Order]:
        """Return orders to submit in response to this tick (possibly empty).

        ``positions`` maps symbol -> signed quantity currently held. The strategy
        must be idempotent-friendly: return the *delta* it wants, and rely on the
        caller's risk layer to dedupe.
        """


class SMACross(Strategy):
    """Textbook fast/slow SMA crossover, one fixed lot per symbol."""

    def __init__(self, fast: int = 10, slow: int = 30, lot: int = 10) -> None:
        assert fast < slow
        self.fast, self.slow, self.lot = fast, slow, lot
        self._px: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=slow))
        self._last_signal: Dict[str, int] = defaultdict(int)  # -1 / 0 / +1

    def on_quote(self, quote: Quote, positions: Dict[str, int]) -> List[Order]:
        price = quote.last or quote.mid
        if price is None:
            return []
        buf = self._px[quote.symbol]
        buf.append(price)
        if len(buf) < self.slow:
            return []

        prices = list(buf)
        fast_ma = sum(prices[-self.fast:]) / self.fast
        slow_ma = sum(prices) / self.slow
        signal = 1 if fast_ma > slow_ma else -1
        if signal == self._last_signal[quote.symbol]:
            return []
        self._last_signal[quote.symbol] = signal

        held = positions.get(quote.symbol, 0)
        target = self.lot if signal == 1 else 0
        delta = target - held
        if delta == 0:
            return []
        return [
            Order(
                symbol=quote.symbol,
                side=Side.BUY if delta > 0 else Side.SELL,
                qty=abs(delta),
                type=OrderType.MARKET,
            )
        ]
