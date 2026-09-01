import { useState } from "react";
import { api, won } from "../api.js";
import { usePoll } from "../hooks.js";
import { NAMES } from "./Watchlist.jsx";

const today = () => new Date().toISOString().slice(0, 10);

export default function BotPanel() {
  const status = usePoll(() => api.botStatus(), 3000, []);
  const nh = usePoll(() => api.nhStatus(), 10000, []);
  const nhEnabled = nh.data?.enabled;

  const positions = usePoll(
    () => (nhEnabled ? api.nhPositions() : Promise.resolve([])),
    5000,
    [nhEnabled],
  );
  const [from, setFrom] = useState(today());
  const fills = usePoll(
    () => (nhEnabled ? api.nhFills(from, today()) : Promise.resolve([])),
    8000,
    [nhEnabled, from],
  );

  const s = status.data;
  const armed = s?.kill_armed;
  const [busy, setBusy] = useState(false);

  const toggleKill = async () => {
    setBusy(true);
    try {
      if (armed) {
        await api.disarmKill();
      } else if (
        confirm("자동매매를 즉시 정지합니다. 봇은 재시작해도 뜨지 않습니다. 계속?")
      ) {
        await api.armKill("web");
      }
      await status.refresh();
    } finally {
      setBusy(false);
    }
  };

  if (status.error)
    return (
      <div className="panel">
        <h2>봇 상태</h2>
        <p className="note err">{status.error}</p>
      </div>
    );

  const dot = !s?.present
    ? "off"
    : s.stale
      ? "warn"
      : "on";
  const dotText = !s?.present
    ? "실행 이력 없음"
    : s.stale
      ? `응답 없음 (${s.age_s}s)`
      : `실행 중 · ${s.uptime_s}s`;

  return (
    <div className="botgrid">
      <div className="panel">
        <h2>봇 상태</h2>
        <div className="statusline">
          <span className={`dot ${dot}`} />
          {dotText}
        </div>

        {s?.present && (
          <table className="kv">
            <tbody>
              <tr>
                <td>브로커</td>
                <td>
                  {s.broker}
                  {s.dry_run != null && (
                    <span className={s.dry_run ? "tag" : "tag live"}>
                      {s.dry_run ? "DRY-RUN" : "실주문"}
                    </span>
                  )}
                </td>
              </tr>
              <tr>
                <td>세션 손익</td>
                <td className={s.session_pnl > 0 ? "up" : s.session_pnl < 0 ? "down" : ""}>
                  {s.session_pnl > 0 ? "+" : ""}
                  {won(s.session_pnl)} 원
                </td>
              </tr>
              <tr>
                <td>주문 / 차단 / 체결</td>
                <td>
                  {s.submitted} / <span className="down">{s.blocked}</span> / {s.fills}
                </td>
              </tr>
            </tbody>
          </table>
        )}

        <button
          className={armed ? "submit buy" : "submit sell"}
          disabled={busy}
          onClick={toggleKill}
        >
          {armed ? "kill 해제 (재개)" : "긴급 정지 (kill switch)"}
        </button>
        {armed && (
          <div className="note err" style={{ marginTop: 8 }}>
            kill switch 활성 — 봇이 주문을 내지 않습니다.
          </div>
        )}
      </div>

      <div className="panel">
        <h2>봇 포지션 {nhEnabled ? "(NH 실계좌)" : "(로컬 북)"}</h2>
        <BotPositions
          local={s?.positions}
          nh={nhEnabled ? positions.data : null}
        />
      </div>

      <div className="panel wide">
        <h2>
          NH 매매 기록{" "}
          {nhEnabled ? (
            <input
              type="date"
              value={from}
              max={today()}
              onChange={(e) => setFrom(e.target.value)}
            />
          ) : (
            <span className="muted small">— GATEWAY_NH_ACCOUNT 미설정</span>
          )}
        </h2>
        {nhEnabled && (
          <table className="grid">
            <thead>
              <tr>
                <th>종목</th>
                <th>구분</th>
                <th className="num">수량</th>
                <th className="num">체결가</th>
              </tr>
            </thead>
            <tbody>
              {(fills.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">
                    체결 없음
                  </td>
                </tr>
              )}
              {(fills.data ?? [])
                .slice()
                .reverse()
                .map((f) => (
                  <tr key={f.fill_id}>
                    <td>{NAMES[f.symbol] || f.symbol}</td>
                    <td className={f.side === "BUY" ? "up" : "down"}>
                      {f.side === "BUY" ? "매수" : "매도"}
                    </td>
                    <td className="num">{f.qty}</td>
                    <td className="num">{won(f.price)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function BotPositions({ local, nh }) {
  const rows = nh
    ? nh.map((p) => ({
        symbol: p.symbol,
        qty: p.qty,
        avg: p.avg_price,
        mark: p.mark,
        pnl: p.unrealized_pnl,
      }))
    : Object.entries(local ?? {}).map(([symbol, p]) => ({
        symbol,
        qty: p.qty,
        avg: p.avg,
        mark: p.mark,
        pnl: null,
      }));

  if (rows.length === 0) return <p className="muted">보유 종목 없음</p>;
  return (
    <table className="grid">
      <thead>
        <tr>
          <th>종목</th>
          <th className="num">수량</th>
          <th className="num">평균가</th>
          <th className="num">현재가</th>
          {nh && <th className="num">평가손익</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.symbol}>
            <td>{NAMES[r.symbol] || r.symbol}</td>
            <td className="num">{r.qty}</td>
            <td className="num">{won(r.avg)}</td>
            <td className="num">{won(r.mark)}</td>
            {nh && (
              <td className={"num " + (r.pnl > 0 ? "up" : r.pnl < 0 ? "down" : "")}>
                {r.pnl == null ? "-" : (r.pnl > 0 ? "+" : "") + won(r.pnl)}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
