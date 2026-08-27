"""Shared domain models used by every Broker implementation.

These are intentionally plain dataclasses with no NH-specific fields so that
``SimBroker`` (self-matched), ``NHMockBroker`` (NH 모의투자) and ``LiveBroker``
(NH 실거래) can all speak the same language.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    PENDING = "PENDING"        # accepted, resting in the book
    PARTIAL = "PARTIAL"        # partially filled
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Quote:
    """A single market-data tick.

    ``bid``/``ask`` are the best prices; ``last`` is the last traded price.
    Any of them may be ``None`` when a feed only provides a subset.
    """

    symbol: str
    ts_ms: int = field(default_factory=_now_ms)
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None

    @property
    def mid(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.last


@dataclass
class Order:
    symbol: str
    side: Side
    qty: int
    type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    # client-supplied idempotency key; a broker must never fill two orders
    # with the same client_order_id.
    client_order_id: str = field(default_factory=lambda: new_id("cord"))
    # broker-assigned id, populated once accepted.
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: Optional[float] = None
    created_ms: int = field(default_factory=_now_ms)
    updated_ms: int = field(default_factory=_now_ms)
    reject_reason: Optional[str] = None

    @property
    def remaining_qty(self) -> int:
        return self.qty - self.filled_qty

    def __post_init__(self) -> None:
        if self.type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if self.qty <= 0:
            raise ValueError("qty must be positive")


@dataclass(frozen=True)
class Fill:
    order_id: str            # broker_order_id
    client_order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    ts_ms: int = field(default_factory=_now_ms)
    fee: float = 0.0
    fill_id: str = field(default_factory=lambda: new_id("fill"))


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    def apply_fill(self, fill: Fill) -> None:
        """Update the position with a new fill, booking realized PnL on reductions."""
        signed = fill.qty if fill.side is Side.BUY else -fill.qty
        new_qty = self.qty + signed

        # same direction (or opening from flat) -> weighted-average the cost basis
        if self.qty == 0 or (self.qty > 0) == (signed > 0):
            total_cost = self.avg_price * abs(self.qty) + fill.price * fill.qty
            self.avg_price = total_cost / abs(new_qty) if new_qty != 0 else 0.0
        else:
            # reducing / flipping -> realize PnL on the closed portion
            closed = min(abs(signed), abs(self.qty))
            direction = 1 if self.qty > 0 else -1
            self.realized_pnl += (fill.price - self.avg_price) * closed * direction
            if new_qty == 0:
                self.avg_price = 0.0
            elif (new_qty > 0) != (self.qty > 0):
                # flipped through zero -> remainder opens at fill price
                self.avg_price = fill.price

        self.realized_pnl -= fill.fee
        self.qty = new_qty

    def unrealized_pnl(self, mark: float) -> float:
        return (mark - self.avg_price) * self.qty
