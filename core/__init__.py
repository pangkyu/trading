"""Shared trading core: models + Broker/QuoteFeed abstractions + implementations.

Consumers (bot, gateway, web BFF) depend only on this package.
"""

from .broker import Broker, QuoteFeed
from .feed import ReplayFeed, SyntheticFeed
from .models import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    Side,
)
from .sim_broker import SimBroker
from .strategy import SMACross, Strategy

__all__ = [
    "Broker",
    "Fill",
    "Order",
    "OrderStatus",
    "OrderType",
    "Position",
    "Quote",
    "QuoteFeed",
    "ReplayFeed",
    "SMACross",
    "Side",
    "SimBroker",
    "Strategy",
    "SyntheticFeed",
]
