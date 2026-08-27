"""Real market data from NH's WebSocket, behind the same QuoteFeed iterator.

``nhplug.realtime.subscribe`` is callback-based and blocking, and manages its
own sessions (2 max, 10 keys each, split automatically). We run it on a daemon
thread and bridge pushes into a queue that ``stream()`` drains.

Lifecycle note: the SDK exposes no clean stop signal, so ``NHFeed`` is
fire-and-forget for now — start it once and let it run. Milestone 3's gateway
owns a single long-lived NHFeed and fans quotes out to every consumer, which is
also how the 2-session limit stays respected.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterable, Iterator

from nhplug.realtime import subscribe

from .broker import QuoteFeed
from .models import Quote
from .nh import quote_from_mc

_SENTINEL = object()


class NHFeed(QuoteFeed):
    def __init__(self, *, tr_cd: str = "mc", timeout: int = 86_400) -> None:
        self._tr_cd = tr_cd
        self._timeout = timeout
        self._symbols: list[str] = []
        self._q: queue.Queue = queue.Queue(maxsize=10_000)
        self._thread: threading.Thread | None = None

    def subscribe(self, symbols: Iterable[str]) -> None:
        self._symbols = [str(s) for s in symbols]

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("NHFeed already started")
        self._thread = threading.Thread(target=self._run, daemon=True, name="nh-feed")
        self._thread.start()

    def _run(self) -> None:
        def on_message(msg: dict) -> None:
            body = msg.get("body") or {}
            if not body.get("code"):
                return
            try:
                self._q.put_nowait(quote_from_mc(body))
            except queue.Full:
                # drop oldest, keep freshest
                try:
                    self._q.get_nowait()
                    self._q.put_nowait(quote_from_mc(body))
                except queue.Empty:
                    pass

        try:
            subscribe(
                self._symbols,
                on_message,
                tr_cd=self._tr_cd,
                timeout=self._timeout,
            )
        finally:
            self._q.put(_SENTINEL)

    def stream(self) -> Iterator[Quote]:
        if self._thread is None:
            self.start()
        while True:
            item = self._q.get()
            if item is _SENTINEL:
                return
            yield item
