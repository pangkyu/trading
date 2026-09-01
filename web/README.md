# web — 모의투자 프런트엔드

React SPA. 게이트웨이(`gateway/`)의 REST/WS만 호출하며 NH API는 직접 보지 않는다.

## 개발

```bash
npm install
npm run dev          # http://localhost:5173  (/api → 127.0.0.1:8000 프록시)
```

게이트웨이를 먼저 띄운다: `cd .. && .venv/bin/python -m scripts.run_gateway`

다른 주소면 `GATEWAY_URL=http://host:port npm run dev`.

## 배포

```bash
npm run build        # → dist/
GATEWAY_URL=http://127.0.0.1:8000 npm start   # Express: dist/ 서빙 + /api 프록시(REST+WS), 포트 4173
```

## 구조

```
src/
  api.js         게이트웨이 fetch 래퍼 + openQuoteStream(WS, 자동 재접속)
  hooks.js       useQuotes(WS 시세맵) · usePoll(주기 폴링)
  App.jsx        계좌 상태 + 레이아웃
  components/
    AccountBar   계좌 선택/생성 + 평가자산·손익 요약
    Watchlist    실시간 관심종목 (클릭 → 종목 선택)
    OrderTicket  매수/매도 · 시장가/지정가 주문
    Holdings     보유 종목 + 평가손익
    Activity     매매 기록 / 미체결(취소)
    BotPanel     봇 관제 — 상태·세션손익·kill switch·NH 포지션/매매기록
```

상단 탭으로 **모의투자**(SimBroker 가상계좌)와 **봇 관제**(무인 봇 모니터링)를 오간다.

계좌 상태는 게이트웨이가 SQLite에 영속화하므로 새로고침/재시작에도 유지된다.
마지막으로 본 계좌 id만 `localStorage`에 저장한다.
