"""NH connectivity smoke test. Requires credentials in .env (see .env.example).

    python -m scripts.nh_smoke              # env, accounts, current price
    python -m scripts.nh_smoke --ticks 20   # + 20 live quotes from the mc channel

Never places an order.
"""

from __future__ import annotations

import argparse
import logging

import nhplug

from core.nh import current_env, quote_from_mc, usable_accounts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="005930")
    ap.add_argument("--ticks", type=int, default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("loaded env files:", nhplug.loaded_files())
    print("env:", current_env(), "| base:", nhplug.get_base_url())

    accts = usable_accounts()
    print(f"usable accounts ({len(accts)}):", [a["acct_no"] for a in accts])

    cp = nhplug.call(
        "/krstock/quote/v1/currentPrice",
        {"market_cd": "KRX", "iem_cd": args.symbol},
    )
    o = cp.get("Output_0", {})
    print(f"{args.symbol} {o.get('iem_nm')}: {o.get('stck_prpr'):,} "
          f"({o.get('prdy_ctrt')}%)  bid {o.get('bidp'):,} / ask {o.get('askp'):,}")

    if args.ticks:
        from nhplug.realtime import subscribe

        n = [0]

        def on_msg(msg: dict) -> None:
            body = msg.get("body") or {}
            if not body.get("code"):
                return
            q = quote_from_mc(body)
            n[0] += 1
            print(f"  tick {n[0]:>3}  {q.symbol}  last={q.last:,.0f}  bid={q.bid:,.0f}  ask={q.ask:,.0f}")

        print(f"\nsubscribing mc for {args.ticks} ticks (needs market hours)...")
        subscribe([args.symbol], on_msg, tr_cd="mc", max_messages=args.ticks, timeout=30)


if __name__ == "__main__":
    main()
