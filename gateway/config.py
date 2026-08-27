"""Gateway configuration, all from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _symbols(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Config:
    # "synthetic" (offline, no NH) or "nh" (real NH WebSocket)
    feed: str = os.environ.get("GATEWAY_FEED", "synthetic")
    symbols: list[str] = field(
        default_factory=lambda: _symbols(
            os.environ.get("GATEWAY_SYMBOLS", "005930,000660,035720")
        )
    )
    db_path: str = os.environ.get("GATEWAY_DB", "data/gateway.sqlite")

    # sim account defaults
    sim_starting_cash: float = float(os.environ.get("GATEWAY_SIM_CASH", "100000000"))
    sim_fee_bps: float = float(os.environ.get("GATEWAY_SIM_FEE_BPS", "1.5"))
    sim_slippage_bps: float = float(os.environ.get("GATEWAY_SIM_SLIPPAGE_BPS", "5"))

    # NH broker (the bot's account). Empty -> NH routes disabled.
    nh_account: str = os.environ.get("GATEWAY_NH_ACCOUNT", "")
    nh_dry_run: bool = os.environ.get("GATEWAY_NH_DRY_RUN", "1") != "0"
    # historical NH executions never change -> cache them this long (seconds).
    nh_history_ttl_s: int = int(os.environ.get("GATEWAY_NH_HISTORY_TTL", "86400"))


def load() -> Config:
    return Config()
