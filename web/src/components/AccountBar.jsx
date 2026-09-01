import { useState } from "react";
import { api, won, pct } from "../api.js";

export default function AccountBar({ accounts, current, onSwitch, onCreated }) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const create = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    const { id } = await api.createAccount(name.trim(), null);
    setName("");
    setCreating(false);
    onCreated(id);
  };

  const acc = current;
  const pnlPct =
    acc && acc.starting_cash ? (acc.pnl / acc.starting_cash) * 100 : null;

  return (
    <header className="accountbar">
      <div className="brand">모의투자</div>

      <select
        value={acc?.id ?? ""}
        onChange={(e) => onSwitch(e.target.value)}
        disabled={accounts.length === 0}
      >
        {accounts.length === 0 && <option value="">계좌 없음</option>}
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>

      {creating ? (
        <form onSubmit={create} className="newacc">
          <input
            autoFocus
            placeholder="계좌 이름"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="submit">생성</button>
          <button type="button" className="link" onClick={() => setCreating(false)}>
            취소
          </button>
        </form>
      ) : (
        <button className="link" onClick={() => setCreating(true)}>
          + 새 계좌
        </button>
      )}

      <div className="spacer" />

      {acc && (
        <div className="summary">
          <div>
            <span className="muted">평가자산</span> {won(acc.equity)} 원
          </div>
          <div>
            <span className="muted">현금</span> {won(acc.cash)} 원
          </div>
          <div className={acc.pnl > 0 ? "up" : acc.pnl < 0 ? "down" : ""}>
            <span className="muted">손익</span> {acc.pnl > 0 ? "+" : ""}
            {won(acc.pnl)} 원 ({pct(pnlPct)})
          </div>
        </div>
      )}
    </header>
  );
}
