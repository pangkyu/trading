"""Quote feeds.

``SyntheticFeed`` is the dev/offline feed (no NH account needed). The real one,
``NHFeed`` (milestone 2), will wrap ``nhplug.realtime.subscribe`` and expose the
exact same iterator, so nothing downstream changes.
"""

from __future__ import annotations

import math
import random
import time
from typing import Dict, Iterable, Iterator, List

from .broker import QuoteFeed
from .models import Quote


class SyntheticFeed(QuoteFeed):
    """Correlated random-walk prices with a synthetic 1-tick-wide book."""

    def __init__(
        self,
        start_prices: Dict[str, float],
        *,
        vol_bps: float = 8.0,       # per-tick stdev in basis points
        spread_bps: float = 4.0,
        interval_s: float = 0.2,
        seed: int = 0,
    ) -> None:
        self._px = dict(start_prices)
        self._vol = vol_bps / 10_000
        self._spread = spread_bps / 10_000
        self._interval = interval_s
        self._symbols: List[str] = list(start_prices)
        self._rng = random.Random(seed)
        self._t = 0

    def subscribe(self, symbols: Iterable[str]) -> None:
        for s in symbols:
            self._px.setdefault(s, 10_000.0)
            if s not in self._symbols:
                self._symbols.append(s)

    def stream(self) -> Iterator[Quote]:
        while True:
            self._t += 1
            for sym in self._symbols:
                drift = 0.00002 * math.sin(self._t / 50)
                shock = self._rng.gauss(0, self._vol) + drift
                self._px[sym] = max(1.0, self._px[sym] * (1 + shock))
                mid = self._px[sym]
                half = mid * self._spread / 2
                yield Quote(
                    symbol=sym,
                    last=round(mid, 2),
                    bid=round(mid - half, 2),
                    ask=round(mid + half, 2),
                    bid_size=self._rng.randint(10, 500),
                    ask_size=self._rng.randint(10, 500),
                )
            time.sleep(self._interval)


class ReplayFeed(QuoteFeed):
    """Replays a list of pre-recorded quotes (for backtests / deterministic tests)."""

    def __init__(self, quotes: List[Quote], *, speed: float = 0.0) -> None:
        self._quotes = quotes
        self._speed = speed

    def subscribe(self, symbols: Iterable[str]) -> None:  # noqa: D401 - no-op
        pass

    def stream(self) -> Iterator[Quote]:
        prev_ts = None
        for q in self._quotes:
            if self._speed and prev_ts is not None:
                time.sleep(max(0.0, (q.ts_ms - prev_ts) / 1000 / self._speed))
            prev_ts = q.ts_ms
            yield q
