"""The single abstraction every consumer (bot, gateway, web) codes against.

Swapping ``SimBroker`` -> ``NHMockBroker`` -> ``LiveBroker`` must be a one-line
config change and nothing else.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Iterable

from .models import Fill, Order, Position, Quote

FillCallback = Callable[[Fill], None]


class Broker(abc.ABC):
    """Order entry + account state. Market data comes from a :class:`QuoteFeed`."""

    @abc.abstractmethod
    def submit(self, order: Order) -> Order:
        """Accept (or reject) an order. Must be idempotent on ``client_order_id``:
        re-submitting the same key returns the existing order, never a duplicate.
        """

    @abc.abstractmethod
    def cancel(self, broker_order_id: str) -> Order:
        ...

    @abc.abstractmethod
    def get_order(self, broker_order_id: str) -> Order | None:
        ...

    @abc.abstractmethod
    def open_orders(self) -> list[Order]:
        ...

    @abc.abstractmethod
    def positions(self) -> dict[str, Position]:
        ...

    @abc.abstractmethod
    def fills(self, since_ms: int = 0) -> list[Fill]:
        """Trade history — the '매매 기록' view."""

    def on_fill(self, cb: FillCallback) -> None:
        """Register a listener notified on every fill (execution notification)."""
        self._fill_listeners.append(cb)  # type: ignore[attr-defined]

    # --- helpers for subclasses -------------------------------------------------
    def __init__(self) -> None:
        self._fill_listeners: list[FillCallback] = []

    def _emit_fill(self, fill: Fill) -> None:
        for cb in self._fill_listeners:
            cb(fill)


class QuoteFeed(abc.ABC):
    """A stream of :class:`Quote` ticks for a set of symbols."""

    @abc.abstractmethod
    def subscribe(self, symbols: Iterable[str]) -> None:
        ...

    @abc.abstractmethod
    def stream(self) -> Iterable[Quote]:
        """Yield quotes as they arrive. Blocking iterator."""
