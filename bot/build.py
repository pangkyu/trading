"""Factories: turn Config into a concrete broker / feed / strategy."""

from __future__ import annotations

import json
from pathlib import Path

from core import ReplayFeed, SimBroker, SMACross
from core.broker import Broker, QuoteFeed
from core.models import Quote
from core.strategy import Strategy

from .config import Config


def build_broker(cfg: Config) -> Broker:
    if cfg.broker == "sim":
        return SimBroker()
    if cfg.broker in ("nhmock", "live"):
        from core.nh_broker import LiveBroker, NHMockBroker

        cls = NHMockBroker if cfg.broker == "nhmock" else LiveBroker
        return cls(
            act_no=cfg.nh_account or None,
            dry_run=cfg.nh_dry_run,
            verify_account=bool(cfg.nh_account),
        )
    raise ValueError(f"unknown BOT_BROKER: {cfg.broker}")


def build_feed(cfg: Config) -> QuoteFeed:
    if cfg.feed == "synthetic":
        from core import SyntheticFeed

        return SyntheticFeed({s: 50_000.0 for s in cfg.symbols}, interval_s=0.2, seed=11)
    if cfg.feed == "replay":
        if not cfg.replay_file:
            raise ValueError("BOT_FEED=replay needs BOT_REPLAY_FILE")
        rows = json.loads(Path(cfg.replay_file).read_text())
        quotes = [Quote(**r) for r in rows]
        return ReplayFeed(quotes, speed=0.0)
    if cfg.feed == "nh":
        from core.nh_feed import NHFeed

        f = NHFeed()
        f.subscribe(cfg.symbols)
        return f
    raise ValueError(f"unknown BOT_FEED: {cfg.feed}")


def build_strategy(cfg: Config) -> Strategy:
    if cfg.strategy == "sma":
        return SMACross(fast=cfg.sma_fast, slow=cfg.sma_slow, lot=cfg.lot)
    raise ValueError(f"unknown BOT_STRATEGY: {cfg.strategy}")
