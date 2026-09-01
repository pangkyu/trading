"""Bot configuration from environment variables.

The bot builds its OWN feed + broker from ``core`` (it does not go through the
gateway). Promotion is one variable: BOT_BROKER = sim | nhmock | live.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _symbols(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _f(name: str, default: str) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: str) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Config:
    # --- wiring ---
    broker: str = os.environ.get("BOT_BROKER", "sim")          # sim | nhmock | live
    feed: str = os.environ.get("BOT_FEED", "synthetic")        # synthetic | nh | replay
    symbols: list[str] = field(
        default_factory=lambda: _symbols(os.environ.get("BOT_SYMBOLS", "005930,000660"))
    )
    nh_account: str = os.environ.get("BOT_NH_ACCOUNT", "")
    nh_dry_run: bool = os.environ.get("BOT_NH_DRY_RUN", "1") != "0"
    replay_file: str = os.environ.get("BOT_REPLAY_FILE", "")

    # --- strategy (SMA cross) ---
    strategy: str = os.environ.get("BOT_STRATEGY", "sma")
    sma_fast: int = _i("BOT_SMA_FAST", "10")
    sma_slow: int = _i("BOT_SMA_SLOW", "30")
    lot: int = _i("BOT_LOT", "10")

    # --- risk limits ---
    max_order_qty: int = _i("BOT_MAX_ORDER_QTY", "100")
    max_position_qty: int = _i("BOT_MAX_POSITION_QTY", "100")
    max_gross_notional: float = _f("BOT_MAX_GROSS_NOTIONAL", "50000000")   # 5천만
    max_daily_loss: float = _f("BOT_MAX_DAILY_LOSS", "1000000")            # 100만
    enforce_market_hours: bool = os.environ.get("BOT_ENFORCE_HOURS", "0") == "1"

    # --- operations ---
    kill_switch_file: str = os.environ.get("BOT_KILL_FILE", "data/KILL")
    status_file: str = os.environ.get("BOT_STATUS_FILE", "data/bot-status.json")
    reconcile_s: float = _f("BOT_RECONCILE_S", "30")       # NH: pull fills / positions
    status_every_s: float = _f("BOT_STATUS_EVERY_S", "5")

    @property
    def is_nh(self) -> bool:
        return self.broker in ("nhmock", "live")


def load() -> Config:
    return Config()
