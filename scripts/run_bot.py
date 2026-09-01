"""Bot entrypoint. Config is entirely from BOT_* env vars (see bot/config.py).

    python -m scripts.run_bot                 # BOT_BROKER=sim, synthetic feed
    BOT_BROKER=nhmock BOT_NH_ACCOUNT=... python -m scripts.run_bot

SIGINT/SIGTERM -> clean stop (writes final status). To hard-stop trading even
across restarts, create the kill file:  touch data/KILL
"""

from __future__ import annotations

import logging
import signal

from bot import Bot, load


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load()
    bot = Bot(cfg)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: bot.stop())

    bot.run()


if __name__ == "__main__":
    main()
