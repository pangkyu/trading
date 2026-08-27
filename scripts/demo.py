"""End-to-end smoke test of the core, no NH account required.

    SyntheticFeed  ->  SMACross strategy  ->  SimBroker  ->  fills / PnL

Run:  python -m scripts.demo
"""

from __future__ import annotations

import itertools

from core import SimBroker, SMACross, SyntheticFeed
from core.models import Fill

SYMBOLS = {"005930": 78_000.0, "000660": 175_000.0}  # 삼성전자, SK하이닉스
MAX_TICKS = 1_500


def main() -> None:
    feed = SyntheticFeed(SYMBOLS, vol_bps=12, interval_s=0.0, seed=42)
    broker = SimBroker(cash=100_000_000, fee_bps=1.5, slippage_bps=5)
    strat = SMACross(fast=10, slow=30, lot=10)

    def log_fill(f: Fill) -> None:
        print(f"  FILL {f.side.value:4} {f.qty:>3} {f.symbol} @ {f.price:>10,.0f}  fee={f.fee:,.0f}")

    broker.on_fill(log_fill)

    for quote in itertools.islice(feed.stream(), MAX_TICKS):
        broker.on_quote(quote)
        pos = {s: p.qty for s, p in broker.positions().items()}
        for order in strat.on_quote(quote, pos):
            broker.submit(order)

    print("\n=== RESULT ===")
    for sym, p in broker.positions().items():
        last = broker._last_px.get(sym, p.avg_price)
        print(
            f"{sym}: qty={p.qty:>4}  avg={p.avg_price:>10,.0f}  "
            f"realized={p.realized_pnl:>12,.0f}  unreal={p.unrealized_pnl(last):>12,.0f}"
        )
    print(f"\ntrades: {len(broker.fills())}")
    print(f"cash:   {broker.cash:>16,.0f}")
    print(f"equity: {broker.equity():>16,.0f}  "
          f"(start 100,000,000  ->  {broker.equity() - broker.starting_cash:+,.0f})")


if __name__ == "__main__":
    main()
