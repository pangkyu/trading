import { useState } from "react";
import { api, won } from "../api.js";
import { NAMES } from "./Watchlist.jsx";

const time = (ms) =>
  new Date(ms).toLocaleTimeString("ko-KR", { hour12: false });

export default function Activity({ accountId, orders, fills, onChange }) {
  const [tab, setTab] = useState("fills");
  const open = orders.filter((o) => ["PENDING", "PARTIAL"].includes(o.status));

  const cancel = async (oid) => {
    await api.cancelOrder(accountId, oid);
    onChange?.();
  };

  return (
    <div className="panel">
      <div className="tabs">
        <button className={tab === "fills" ? "on" : ""} onClick={() => setTab("fills")}>
          매매 기록 ({fills.length})
        </button>
        <button className={tab === "open" ? "on" : ""} onClick={() => setTab("open")}>
          미체결 ({open.length})
        </button>
      </div>

      {tab === "fills" && (
        <table className="grid">
          <thead>
            <tr>
              <th>시각</th>
              <th>종목</th>
              <th>구분</th>
              <th className="num">수량</th>
              <th className="num">체결가</th>
              <th className="num">수수료</th>
            </tr>
          </thead>
          <tbody>
            {fills.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  체결 내역 없음
                </td>
              </tr>
            )}
            {[...fills].reverse().map((f) => (
              <tr key={f.fill_id}>
                <td className="muted">{time(f.ts_ms)}</td>
                <td>{NAMES[f.symbol] || f.symbol}</td>
                <td className={f.side === "BUY" ? "up" : "down"}>
                  {f.side === "BUY" ? "매수" : "매도"}
                </td>
                <td className="num">{f.qty}</td>
                <td className="num">{won(f.price)}</td>
                <td className="num muted">{won(f.fee)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "open" && (
        <table className="grid">
          <thead>
            <tr>
              <th>종목</th>
              <th>구분</th>
              <th>유형</th>
              <th className="num">수량</th>
              <th className="num">지정가</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {open.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  미체결 주문 없음
                </td>
              </tr>
            )}
            {open.map((o) => (
              <tr key={o.broker_order_id}>
                <td>{NAMES[o.symbol] || o.symbol}</td>
                <td className={o.side === "BUY" ? "up" : "down"}>
                  {o.side === "BUY" ? "매수" : "매도"}
                </td>
                <td>{o.type === "LIMIT" ? "지정가" : "시장가"}</td>
                <td className="num">
                  {o.qty}
                  {o.filled_qty ? ` (${o.filled_qty})` : ""}
                </td>
                <td className="num">{o.limit_price ? won(o.limit_price) : "-"}</td>
                <td>
                  <button className="link" onClick={() => cancel(o.broker_order_id)}>
                    취소
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
