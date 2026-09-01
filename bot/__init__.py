"""Unattended trading bot: strategy loop + risk gate + kill switch.

Runs standalone on ``core`` (its own feed + broker), not through the gateway.
Promote with BOT_BROKER = sim | nhmock | live.
"""

from .config import Config, load
from .engine import Bot
from .risk import RiskGate, Verdict

__all__ = ["Bot", "Config", "RiskGate", "Verdict", "load"]
