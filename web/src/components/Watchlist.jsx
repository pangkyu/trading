import { won } from "../api.js";

const NAMES = {
  "005930": "삼성전자",
  "000660": "SK하이닉스",
  "035720": "카카오",
};

export default function Watchlist({ quotes, selected, onSelect }) {
  const rows = Object.values(quotes).sort((a, b) =>
    a.symbol.localeCompare(b.symbol),
  );

  return (
    <div className="panel">
      <h2>관심종목</h2>
      <table className="grid">
        <thead>
          <tr>
            <th>종목</th>
            <th className="num">현재가</th>
            <th className="num">매수호가</th>
            <th className="num">매도호가</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                시세 대기 중…
              </td>
            </tr>
          )}
          {rows.map((q) => (
            <tr
              key={q.symbol}
              className={q.symbol === selected ? "sel" : ""}
              onClick={() => onSelect(q.symbol)}
            >
              <td>
                <div className="sym">{NAMES[q.symbol] || q.symbol}</div>
                <div className="muted small">{q.symbol}</div>
              </td>
              <td className="num strong">{won(q.last)}</td>
              <td className="num">{won(q.bid)}</td>
              <td className="num">{won(q.ask)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { NAMES };
