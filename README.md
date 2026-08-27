# trading

NH투자증권 **PLUG Open API**([PLUG-OpenAPI](https://github.com/PLUG-OpenAPI)) 기반으로

1. **자동매매 봇** — 무인으로 전략을 돌려 실거래/모의투자 주문
2. **모의투자 웹 서비스** — 여러 사용자가 가상 잔고로 매매

를 **하나의 공통 코어** 위에 얹어서 만든다.

## 설계

```
                  ┌──────────── gateway (FastAPI, 상주) ────────────┐
                  │  NH 연결 1개 · 토큰관리 · 시세 팬아웃 · DB       │
                  └────┬──────────────────────────────┬─────────────┘
                       │                              │
        ┌──────────────┴─────────┐        ┌───────────┴──────────────┐
        │ bot (파이썬, 스케줄러) │        │ web (Node + React)        │
        │ 전략→주문 Mock/Live   │        │ SimBroker 가상계좌 매매   │
        └────────────────────────┘        └──────────────────────────┘
```

핵심은 [`core/broker.py`](core/broker.py)의 `Broker` 추상 인터페이스와 구현 3종:

| 구현 | 대상 | 용도 |
|---|---|---|
| `SimBroker` | 자체 체결엔진 (시세만 NH) | 웹 모의투자, 전략 1차 검증 |
| `NHMockBroker` *(M2)* | `moapi.nhplug.com`, `acct_type=03` | 봇 무인 검증 |
| `LiveBroker` *(M2)* | `api.nhplug.com`, `acct_type=01` | 실거래 |

봇도 웹도 이 인터페이스만 의존하므로 승급은 **설정 한 줄**.

## 로드맵

- [x] **M1 — core** : 모델 + `Broker`/`QuoteFeed` 추상 + `SimBroker` + `SyntheticFeed` + 전략 인터페이스 + 데모/테스트 *(NH 계정 불필요)*
- [ ] **M2 — NH 연동** : Python 3.12 환경, `nh_client.py`(`nhplug` 래핑), `NHFeed`, `NHMockBroker`, `LiveBroker`
- [ ] **M3 — gateway** : FastAPI REST + WebSocket, SQLite(유저/주문/체결/PnL), 시세 팬아웃
- [ ] **M4 — web** : Node + React 모의투자 화면 (gateway 호출만)
- [ ] **M5 — bot** : 전략 루프 + 리스크 게이트 + kill switch + 프로세스 매니저(무인)

## 지금 실행해보기 (M1)

```bash
python3 -m scripts.demo      # SyntheticFeed → SMACross → SimBroker → 체결/PnL
python3 -m pytest -q         # core 정확성 테스트 (pip install --user pytest)
```

`core/`는 표준 라이브러리만 사용한다. NH 연동(`nhplug`)은 M2부터, Python **3.11+** 필요.

## 디렉토리

```
core/         공통 코어 (의존성 없음)
  models.py     Quote / Order / Fill / Position
  broker.py     Broker · QuoteFeed 추상
  sim_broker.py 자체 체결엔진
  feed.py       SyntheticFeed / ReplayFeed
  strategy.py   Strategy 추상 + SMACross 예제
scripts/      실행 스크립트 (demo)
tests/        pytest
```

## 보안

- 앱키/시크릿은 `~/.nhplug/.env` (레포 밖). 브라우저로 절대 내려보내지 않음 — gateway가 프록시.
- NH 실거래 전 반드시 모의투자(`moapi`)에서 검증. `dry_run` 기본 유지.
- NH WebSocket은 앱키당 세션 2개 제한 → gateway가 1개만 잡고 팬아웃.
