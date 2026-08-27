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
| `NHMockBroker` | `moapi.nhplug.com`, `acct_type=03` | 봇 무인 검증 |
| `LiveBroker` | `api.nhplug.com`, `acct_type=01` | 실거래 |

봇도 웹도 이 인터페이스만 의존하므로 승급은 **`.env` 의 `NHPLUG_BASE_URL` 한 줄**.

## 로드맵

- [x] **M1 — core** : 모델 + `Broker`/`QuoteFeed` 추상 + `SimBroker` + `SyntheticFeed` + 전략 인터페이스 + 데모/테스트 *(NH 계정 불필요)*
- [x] **M2 — NH 연동** : `.venv`(Python 3.12, uv), `core.nh`(매핑·계좌), `NHFeed`(WebSocket→QuoteFeed), `NHBroker`/`NHMockBroker`/`LiveBroker`, 매매기록 조회(`fills`/`reconcile`)
- [x] **M3 — gateway** : FastAPI REST + WS 시세 팬아웃, SQLite 영속(SimBroker 상태 blob + NH 히스토리 캐시), 재시작 복원, NH 라우트(dry-run 기본)
- [ ] **M4 — web** : Node + React 모의투자 화면 (gateway 호출만)
- [ ] **M5 — bot** : 전략 루프 + 리스크 게이트 + kill switch + 프로세스 매니저(무인)

## 개발 환경

```bash
brew install uv
uv venv --python 3.12 .venv
uv pip install "nhplug[instruments]" pytest
```

`core/` 자체는 표준 라이브러리만 쓰지만, NH 연동 모듈(`core.nh*`)과 테스트는 `.venv`(3.11+) 필요.

## 실행

```bash
.venv/bin/python -m scripts.demo         # 오프라인: SyntheticFeed → SMACross → SimBroker
.venv/bin/python -m pytest -q            # 전체 테스트 (NH 매핑은 network 없이 검증)

cp .env.example .env && $EDITOR .env     # NH 자격증명 입력 (또는 ~/.nhplug/.env)
.venv/bin/python -m scripts.nh_smoke              # 접속 확인: env·계좌·현재가
.venv/bin/python -m scripts.nh_smoke --ticks 20   # + 실시간 시세 20틱 (장중)
```

### gateway (M3)

```bash
.venv/bin/python -m scripts.run_gateway           # http://127.0.0.1:8000, 합성 시세
#   http://127.0.0.1:8000/docs 에서 전체 API

# NH 시세 + 봇 계좌까지:
GATEWAY_FEED=nh GATEWAY_NH_ACCOUNT=50001001987 .venv/bin/python -m scripts.run_gateway
```

| 그룹 | 엔드포인트 |
|---|---|
| 시세 | `GET /quotes`, `GET /quotes/{sym}`, `WS /ws/quotes?symbols=` |
| 모의계좌 | `POST /sim/accounts`, `GET /sim/accounts[/{id}]`, `DELETE …` |
| 주문 | `POST /sim/accounts/{id}/orders`, `…/orders?open_only=`, `…/orders/{oid}/cancel` |
| 매매기록 | `GET /sim/accounts/{id}/fills?since_ms=` |
| NH(봇) | `GET /nh/status`, `/nh/positions`, `/nh/fills?start=&end=`(캐시), `POST /nh/orders` |

SimBroker 상태는 매 주문마다 SQLite(`GATEWAY_DB`)에 저장돼 재시작 시 복원된다.
NH 매매기록은 날짜별로 캐시(`GATEWAY_NH_HISTORY_TTL`)해 쿼터(IGW42903)를 아낀다.

## 디렉토리

```
core/         공통 코어
  models.py     Quote / Order / Fill / Position (표준 라이브러리만)
  broker.py     Broker · QuoteFeed 추상
  sim_broker.py 자체 체결엔진
  feed.py       SyntheticFeed / ReplayFeed
  strategy.py   Strategy 추상 + SMACross 예제
  nh.py         NH env·계좌 판별 + wire↔model 매핑        ── nhplug 필요
  nh_feed.py    NHFeed: nhplug.realtime.subscribe → QuoteFeed
  nh_broker.py  NHBroker / NHMockBroker / LiveBroker
gateway/      FastAPI 서비스 (M3)
  config.py     GATEWAY_* 환경변수
  db.py         SQLite: sim_account 상태 blob + nh_history 캐시
  hub.py        피드 1개 소유 → SimBroker·WS 팬아웃, 계좌 레지스트리
  app.py        REST + WebSocket 라우트
  serialize.py  model → JSON
scripts/      demo · nh_smoke · run_gateway
tests/        pytest
CLAUDE.md     NH SDK 개발 규칙 (PLUG-OpenAPI 공식 템플릿)
```

## 보안

- 앱키/시크릿은 `~/.nhplug/.env` (레포 밖). 브라우저로 절대 내려보내지 않음 — gateway가 프록시.
- `NHBroker` 는 `dry_run=True` 기본. 실전송은 명시적으로 꺼야 함. 실거래 전 반드시 `moapi` 검증.
- `LiveBroker`/`NHMockBroker` 는 `NHPLUG_BASE_URL` 환경이 기대와 다르면 **생성 시 예외** (엉뚱한 환경 주문 방지).
- NH WebSocket은 앱키당 세션 2개 제한 → gateway가 1개만 잡고 팬아웃 (M3).
