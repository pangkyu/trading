// Thin wrapper over the gateway API (proxied at /api by Vite / server.js).

const BASE = "/api";

async function j(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);
  return data;
}

export const api = {
  health: () => j("GET", "/health"),

  listAccounts: () => j("GET", "/sim/accounts"),
  createAccount: (name, cash) => j("POST", "/sim/accounts", { name, cash }),
  getAccount: (id) => j("GET", `/sim/accounts/${id}`),
  deleteAccount: (id) => j("DELETE", `/sim/accounts/${id}`),

  submitOrder: (id, order) => j("POST", `/sim/accounts/${id}/orders`, order),
  listOrders: (id, openOnly = false) =>
    j("GET", `/sim/accounts/${id}/orders${openOnly ? "?open_only=true" : ""}`),
  cancelOrder: (id, oid) =>
    j("POST", `/sim/accounts/${id}/orders/${oid}/cancel`),
  fills: (id, sinceMs = 0) =>
    j("GET", `/sim/accounts/${id}/fills?since_ms=${sinceMs}`),

  quotes: () => j("GET", "/quotes"),
};

// Live quote stream. Returns a close() fn. Auto-reconnects with backoff.
export function openQuoteStream(onQuote, symbols) {
  let ws = null;
  let closed = false;
  let backoff = 500;
  const qs = symbols?.length ? `?symbols=${symbols.join(",")}` : "";

  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${BASE}/ws/quotes${qs}`);
    ws.onmessage = (e) => {
      try {
        onQuote(JSON.parse(e.data));
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onopen = () => {
      backoff = 500;
    };
    ws.onclose = () => {
      if (closed) return;
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 10_000);
    };
    ws.onerror = () => ws.close();
  };
  connect();

  return () => {
    closed = true;
    ws?.close();
  };
}

export const won = (n) =>
  n == null ? "-" : Math.round(n).toLocaleString("ko-KR");
export const pct = (n) => (n == null ? "-" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`);
