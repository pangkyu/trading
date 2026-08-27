"""Dev entrypoint for the gateway.

    python -m scripts.run_gateway              # synthetic feed, ./data/gateway.sqlite
    GATEWAY_FEED=nh python -m scripts.run_gateway --reload

Equivalent to:  uvicorn gateway.app:app
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    uvicorn.run("gateway.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
