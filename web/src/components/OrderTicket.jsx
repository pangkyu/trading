import { useEffect, useState } from "react";
import { api, won } from "../api.js";
import { NAMES } from "./Watchlist.jsx";

export default function OrderTicket({ accountId, symbol, quote, onDone }) {
  const [side, setSide] = useState("BUY");
  const [type, setType] = useState("MARKET");
  const [qty, setQty] = useState(10);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (quote?.last) setLimit(String(Math.round(quote.last)));
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const ref = type === "LIMIT" ? Number(limit) : quote?.last;
  const notional = ref && qty ? ref * qty : null;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const order = {
        symbol,
        side,
        qty: Number(qty),
        type,
        limit_price: type === "LIMIT" ? Number(limit) : null,
      };
      const r = await api.submitOrder(accountId, order);
      setMsg(
        r.status === "REJECTED"
          ? { err: true, text: `거부: ${r.reject_reason}` }
          : {
              err: false,
              text:
                r.status === "FILLED"
                  ? `체결 ${r.filled_qty}주 @ ${won(r.avg_fill_price)}`
                  : `접수됨 (${r.status})`,
            },
      );
      onDone?.();
    } catch (err) {
      setMsg({ err: true, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  if (!symbol)
    return (
      <div className="panel">
        <h2>주문</h2>
        <p className="muted">관심종목에서 종목을 선택하세요.</p>
      </div>
    );

  return (
    <div className="panel">
      <h2>
        주문 · {NAMES[symbol] || symbol}{" "}
        <span className="muted small">{won(quote?.last)}</span>
      </h2>
      <form onSubmit={submit} className="ticket">
        <div className="seg">
          <button
            type="button"
            className={side === "BUY" ? "buy on" : "buy"}
            onClick={() => setSide("BUY")}
          >
            매수
          </button>
          <button
            type="button"
            className={side === "SELL" ? "sell on" : "sell"}
            onClick={() => setSide("SELL")}
          >
            매도
          </button>
        </div>

        <label>
          유형
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="MARKET">시장가</option>
            <option value="LIMIT">지정가</option>
          </select>
        </label>

        <label>
          수량
          <input
            type="number"
            min="1"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
          />
        </label>

        {type === "LIMIT" && (
          <label>
            가격 (원)
            <input
              type="number"
              min="0"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </label>
        )}

        <div className="muted small">
          예상 금액 {notional ? `${won(notional)} 원` : "-"}
        </div>

        <button
          type="submit"
          disabled={busy}
          className={side === "BUY" ? "submit buy" : "submit sell"}
        >
          {busy ? "전송 중…" : side === "BUY" ? "매수 주문" : "매도 주문"}
        </button>

        {msg && (
          <div className={msg.err ? "note err" : "note ok"}>{msg.text}</div>
        )}
      </form>
    </div>
  );
}
