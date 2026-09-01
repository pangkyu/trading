import { useEffect, useRef, useState } from "react";
import { openQuoteStream } from "./api.js";

// Live map of symbol -> quote, kept fresh over the gateway WebSocket.
export function useQuotes(symbols) {
  const [quotes, setQuotes] = useState({});
  const key = symbols?.join(",") ?? "";
  useEffect(() => {
    const close = openQuoteStream(
      (q) => setQuotes((prev) => ({ ...prev, [q.symbol]: q })),
      symbols,
    );
    return close;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return quotes;
}

// Re-run an async fn every `ms`, plus a manual refresh(). Pauses when hidden.
export function usePoll(fn, ms, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const savedFn = useRef(fn);
  savedFn.current = fn;

  const run = () =>
    savedFn.current().then(setData).catch((e) => setError(e.message ?? String(e)));

  useEffect(() => {
    setError(null);
    run();
    const id = setInterval(() => {
      if (!document.hidden) run();
    }, ms);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, refresh: run };
}
