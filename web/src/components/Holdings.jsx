import { won } from "../api.js";
import { NAMES } from "./Watchlist.jsx";

export default function Holdings({ account }) {
  const rows = account?.positions ?? [];
  return (
    <div className="panel">
      <h2>보유 종목</h2>
      <table className="grid">
        <thead>
          <tr>
            <th>종목</th>
            <th className="num">수량</th>
            <th className="num">평균가</th>
            <th className="num">현재가</th>
            <th className="num">평가손익</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                보유 종목 없음
              </td>
            </tr>
          )}
          {rows.map((p) => {
            const u = p.unrealized_pnl;
            return (
              <tr key={p.symbol}>
                <td>
                  {NAMES[p.symbol] || p.symbol}
                  <span className="muted small"> {p.symbol}</span>
                </td>
                <td className="num">{p.qty.toLocaleString("ko-KR")}</td>
                <td className="num">{won(p.avg_price)}</td>
                <td className="num">{won(p.mark)}</td>
                <td className={"num " + (u > 0 ? "up" : u < 0 ? "down" : "")}>
                  {u == null ? "-" : (u > 0 ? "+" : "") + won(u)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
