"""Gateway configuration. All values come from environment variables, read
fresh in :func:`load` (so tests can vary them per-case)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _symbols(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Config:
    feed: str = "synthetic"                       # "synthetic" | "nh" | "manual"
    symbols: list[str] = field(default_factory=lambda: ["005930", "000660", "035720"])
    db_path: str = "data/gateway.sqlite"

    sim_starting_cash: float = 100_000_000
    sim_fee_bps: float = 1.5
    sim_slippage_bps: float = 5.0

    nh_account: str = ""                          # empty -> NH routes disabled
    nh_dry_run: bool = True
    nh_history_ttl_s: int = 86_400               # historical fills never change

    bot_status_file: str = "data/bot-status.json"
    bot_kill_file: str = "data/KILL"
    bot_stale_s: int = 30


def load() -> Config:
    g = os.environ.get
    return Config(
        feed=g("GATEWAY_FEED", "synthetic"),
        symbols=_symbols(g("GATEWAY_SYMBOLS", "005930,000660,035720")),
        db_path=g("GATEWAY_DB", "data/gateway.sqlite"),
        sim_starting_cash=float(g("GATEWAY_SIM_CASH", "100000000")),
        sim_fee_bps=float(g("GATEWAY_SIM_FEE_BPS", "1.5")),
        sim_slippage_bps=float(g("GATEWAY_SIM_SLIPPAGE_BPS", "5")),
        nh_account=g("GATEWAY_NH_ACCOUNT", ""),
        nh_dry_run=g("GATEWAY_NH_DRY_RUN", "1") != "0",
        nh_history_ttl_s=int(g("GATEWAY_NH_HISTORY_TTL", "86400")),
        bot_status_file=g("GATEWAY_BOT_STATUS_FILE", "data/bot-status.json"),
        bot_kill_file=g("GATEWAY_BOT_KILL_FILE", "data/KILL"),
        bot_stale_s=int(g("GATEWAY_BOT_STALE_S", "30")),
    )
