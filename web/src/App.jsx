import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { useQuotes, usePoll } from "./hooks.js";
import AccountBar from "./components/AccountBar.jsx";
import Watchlist from "./components/Watchlist.jsx";
import OrderTicket from "./components/OrderTicket.jsx";
import Holdings from "./components/Holdings.jsx";
import Activity from "./components/Activity.jsx";

const LAST_ACCT = "trading.web.lastAccount";

export default function App() {
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState(
    () => localStorage.getItem(LAST_ACCT) || "",
  );
  const [selected, setSelected] = useState(null);
  const [bootError, setBootError] = useState(null);

  const symbols = useMemo(() => ["005930", "000660", "035720"], []);
  const quotes = useQuotes(symbols);

  const refreshAccounts = useCallback(async () => {
    const list = await api.listAccounts();
    setAccounts(list);
    setAccountId((cur) => {
      if (cur && list.some((a) => a.id === cur)) return cur;
      return list[0]?.id || "";
    });
  }, []);

  useEffect(() => {
    refreshAccounts().catch((e) => setBootError(e.message));
  }, [refreshAccounts]);

  useEffect(() => {
    if (accountId) localStorage.setItem(LAST_ACCT, accountId);
  }, [accountId]);

  const account = usePoll(
    () => (accountId ? api.getAccount(accountId) : Promise.resolve(null)),
    2000,
    [accountId],
  );
  const orders = usePoll(
    () => (accountId ? api.listOrders(accountId) : Promise.resolve([])),
    2000,
    [accountId],
  );
  const fills = usePoll(
    () => (accountId ? api.fills(accountId) : Promise.resolve([])),
    2000,
    [accountId],
  );

  const refreshAll = useCallback(() => {
    account.refresh();
    orders.refresh();
    fills.refresh();
  }, [account, orders, fills]);

  if (bootError)
    return (
      <div className="boot-error">
        <h1>gateway에 연결할 수 없습니다</h1>
        <p>{bootError}</p>
        <p className="muted">
          <code>python -m scripts.run_gateway</code> 실행 후 새로고침하세요.
        </p>
      </div>
    );

  return (
    <div className="app">
      <AccountBar
        accounts={accounts}
        current={account.data}
        onSwitch={setAccountId}
        onCreated={async (id) => {
          await refreshAccounts();
          setAccountId(id);
        }}
      />

      {accounts.length === 0 ? (
        <div className="empty">
          <p>계좌가 없습니다. 상단의 <b>+ 새 계좌</b>로 시작하세요.</p>
        </div>
      ) : (
        <main className="layout">
          <div className="col">
            <Watchlist
              quotes={quotes}
              selected={selected}
              onSelect={setSelected}
            />
            <OrderTicket
              accountId={accountId}
              symbol={selected}
              quote={selected ? quotes[selected] : null}
              onDone={refreshAll}
            />
          </div>
          <div className="col wide">
            <Holdings account={account.data} />
            <Activity
              accountId={accountId}
              orders={orders.data ?? []}
              fills={fills.data ?? []}
              onChange={refreshAll}
            />
          </div>
        </main>
      )}
    </div>
  );
}
