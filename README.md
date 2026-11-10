# SpecGrid — 스펙그리드

전자기기·IT 하드웨어 중고거래 플랫폼. 백엔드 FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · Redis · MariaDB,
프론트엔드는 빌드 과정 없는 HTML/CSS/JavaScript(ES modules)로 같은 서버가 함께 제공한다.

## 디렉토리 구조

```
specgrid-backend/
├── app/                        # 백엔드
│   ├── main.py                 # 앱 생성, 에러 처리, /media·프론트엔드 정적 파일 제공
│   ├── api/
│   │   ├── deps.py             # 공통 의존성 (DB 세션, 로그인 사용자, 선택적 로그인, Redis)
│   │   └── v1/endpoints/       # auth · users · products · product_images · chat(+WebSocket)
│   │                           # trades · favorites · rankings · health
│   ├── schemas/                # 요청/응답 모델 (Pydantic)
│   ├── services/               # 비즈니스 로직 (거래 락, 실시간 이벤트, 활동 로그, 랭킹 …)
│   ├── models/                 # 테이블 (users, products, chat, trades, favorites, activity)
│   ├── db/                     # Base, 세션
│   └── core/                   # 설정, JWT·비밀번호, 에러 타입, Redis, 파일 저장소
├── frontend/                   # 웹 화면 (http://localhost:8000/)
│   ├── index.html
│   ├── css/style.css           # 원본 디자인 시스템 (흑연색 + 시그널 그린)
│   ├── css/app.css             # 랭킹·채팅·로그인 등 추가 화면 스타일
│   └── js/
│       ├── app.js              # 해시 라우터(#/product/7), 헤더, 실시간 알림
│       ├── api.js              # REST 호출, 토큰 저장·자동 재발급
│       ├── realtime.js         # WebSocket (자동 재연결, 토큰 만료 시 재발급)
│       ├── ui.js · icons.js    # 공통 UI (상품 카드, 토스트, XSS 이스케이프), 아이콘
│       └── views/              # home · product · sell · auth · account · chat · ranking
├── alembic/versions/           # 마이그레이션 0001~0005
├── tests/                      # pytest (API, 동시성)
├── tests_e2e/run_e2e.py        # 실제 크롬으로 전체 화면 흐름 테스트
├── scripts/                    # init_db.sql, seed_activity.py
├── requirements.txt / requirements-dev.txt
└── .env.example
```

## 시작하기

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 값 수정
```

MariaDB에 DB와 계정 생성 (root로 1회): `scripts/init_db.sql`의 비밀번호 두 개를 `.env`와 같게 바꾼 뒤 실행한다.

```bash
mariadb -u root -p -h 127.0.0.1 -P 3307 -e "source scripts/init_db.sql"
```

| 계정 | 권한 | 용도 |
|---|---|---|
| `specgrid_migrator` | DML + CREATE/ALTER/DROP/INDEX/REFERENCES | Alembic 마이그레이션 전용 (`DB_MIGRATION_*`) |
| `specgrid_app` | SELECT/INSERT/UPDATE/DELETE | FastAPI 런타임 (`DB_*`) |

모든 연결은 `time_zone='+00:00'`(UTC 저장)과 strict `sql_mode`로 시작한다 (`app/core/config.py`의 `DB_CONNECT_ARGS`).
이 PC에서는 MariaDB가 **3307**, 별도 MySQL 9.5가 3306을 쓰므로 포트를 혼동하지 않는다.

마이그레이션 및 서버 실행:

```bash
alembic upgrade head            # 테이블 생성
alembic upgrade head --sql      # (선택) DB 없이 실행될 SQL만 확인
uvicorn app.main:app --reload
```

- 웹 화면: **http://localhost:8000/** (회원가입 → 판매 등록 → 검색·필터 → 채팅 → 구매 요청 → 수락·완료)
- API 문서(Swagger): http://localhost:8000/docs

## 프론트엔드

- 빌드 도구 없이 브라우저가 바로 읽는 ES 모듈이라 `frontend/` 파일을 고치고 새로고침하면 끝. 서버가 `Cache-Control: no-cache`로
  제공해 옛 JS가 남지 않는다. API와 같은 주소에서 제공하므로 CORS 설정이 필요 없다.
- 화면 주소는 `#/` 해시 라우팅: `#/`, `#/?q=rtx`, `#/product/7`, `#/sell`, `#/chat/3`, `#/trades`, `#/favorites`, `#/profile`, `#/ranking`.
- 로그인 토큰은 `localStorage`에 저장한다. 401이 오면 refresh 토큰으로 **한 번만** 재발급 후 재시도한다
  (동시에 여러 요청이 401을 받아도 재발급 요청은 1개 — refresh 토큰 재사용으로 오인되어 전체 로그아웃되는 것을 방지).
- 실시간: 로그인하면 WebSocket에 연결해 새 메시지·읽음·거래 상태를 받는다. 끊기면 지수 백오프로 재연결하고,
  재연결 후에는 열려 있던 화면이 놓친 데이터를 다시 불러온다.
- 사용자 입력(상품명, 채팅 등)은 항상 HTML 이스케이프 후 그린다 (e2e에서 `<img onerror>` 메시지로 확인).

## API

Swagger UI: `http://localhost:8000/docs` (우측 상단 Authorize에 access_token 입력)

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/v1/auth/signup` | | 회원가입 (비밀번호 8자+ 영문·숫자, Argon2id 해싱) |
| POST | `/api/v1/auth/login` | | access(30분) + refresh(14일) 토큰 발급 |
| POST | `/api/v1/auth/refresh` | | 재발급. refresh 토큰은 1회용(rotation), 재사용 감지 시 전체 세션 폐기 |
| POST | `/api/v1/auth/logout` | ✅ | 현재 access 토큰 폐기 (+ body의 refresh 토큰 폐기) |
| POST | `/api/v1/auth/logout-all` | ✅ | 모든 기기의 토큰 폐기 |
| GET | `/api/v1/users/me` | ✅ | 내 정보 |
| POST | `/api/v1/products` | ✅ | 상품 등록 (스펙 포함 가능) |
| GET | `/api/v1/products` | | 검색: `q, category, condition, min/max_price, manufacturer, cpu, gpu, min_cores, min_ram_gb, min_vram_gb, min_storage_gb, hot_only, include_sold, sort, page, size` |
| GET | `/api/v1/products/{id}` | | 상세 (조회수 +1) |
| PATCH | `/api/v1/products/{id}` | ✅ 본인 | 부분 수정 (보낸 항목만 변경, `spec: null`이면 스펙 삭제) |
| PATCH | `/api/v1/products/{id}/status` | ✅ 본인 | `on_sale` / `reserved` / `sold` / `hidden` |
| DELETE | `/api/v1/products/{id}` | ✅ 본인 | 소프트 삭제 (DB 행 유지, API에서 제외) |
| POST | `/api/v1/products/{id}/images` | ✅ 본인 | 사진 업로드 (multipart `files`, 여러 장) |
| DELETE | `/api/v1/products/{id}/images/{image_id}` | ✅ 본인 | 사진 삭제 |
| PUT | `/api/v1/products/{id}/images/order` | ✅ 본인 | 사진 순서 변경 (첫 번째가 대표 사진) |
| GET | `/api/v1/users/me/products` | ✅ | 내 판매 상품 (숨김·판매완료 포함, `status` 필터) |
| POST | `/api/v1/chat/rooms` | ✅ | `{"product_id": 7}` 판매자와 채팅 시작. 새 방 201, 이미 있으면 기존 방 200 |
| GET | `/api/v1/chat/rooms` | ✅ | 내 채팅방 목록 (최근 대화순, 상대방·마지막 메시지·안 읽은 수 포함) |
| GET | `/api/v1/chat/unread-count` | ✅ | 안 읽은 메시지 총 개수 (배지용) |
| GET | `/api/v1/chat/rooms/{id}` | ✅ 참여자 | 채팅방 정보 |
| GET | `/api/v1/chat/rooms/{id}/messages` | ✅ 참여자 | 메시지 목록: 기본 최신 30개, `before_id`(이전 메시지), `after_id`(새 메시지), `limit` |
| POST | `/api/v1/chat/rooms/{id}/messages` | ✅ 참여자 | `{"content": "..."}` 메시지 전송 (1~1000자) |
| POST | `/api/v1/chat/rooms/{id}/read` | ✅ 참여자 | 상대가 보낸 메시지 모두 읽음 처리 |
| WS | `/api/v1/chat/ws` | 첫 메시지 | 실시간 수신 (아래 '채팅' 참고) |
| POST | `/api/v1/trades` | ✅ | `{"product_id": 7, "message": "..."}` 구매 요청 |
| GET | `/api/v1/trades` | ✅ | 내 거래 목록: `role`(buyer/seller), `status`, `product_id`, `page`, `size` |
| GET | `/api/v1/trades/{id}` | ✅ 참여자 | 거래 상세 |
| POST | `/api/v1/trades/{id}/accept` | ✅ 판매자 | 수락 → 상품 `reserved` |
| POST | `/api/v1/trades/{id}/reject` | ✅ 판매자 | 거절 |
| POST | `/api/v1/trades/{id}/complete` | ✅ 판매자 | 거래 완료 → 상품 `sold`, 다른 대기 요청 자동 거절 |
| POST | `/api/v1/trades/{id}/cancel` | ✅ 참여자 | 구매자: 대기·예약 중 취소 / 판매자: 예약 후 취소 → 상품 `on_sale` |
| GET | `/api/v1/rankings/keywords` | | 인기 검색어: `period`(day/week/month), `limit` |
| GET | `/api/v1/rankings/products` | | 인기 상품: `metric`(views=많이 본 / favorites=찜 많은), `period`(day/week/month/all), `category`, `include_sold`, `limit` |
| PUT | `/api/v1/products/{id}/favorite` | ✅ | 찜하기 (여러 번 보내도 1번) |
| DELETE | `/api/v1/products/{id}/favorite` | ✅ | 찜 취소 |
| GET | `/api/v1/users/me/favorites` | ✅ | 내 찜 목록 (최근 찜한 순, 삭제·숨김 제외) |

### 채팅

- 방은 (상품, 구매자)당 하나. 본인 상품·판매완료(409)·숨김/삭제(404) 상품에는 새 방을 만들 수 없다.
  이미 있는 방은 상품이 삭제돼도 유지되며 `product.is_deleted`로 표시된다.
- 참여자가 아닌 사용자에게는 방이 존재하지 않는 것처럼 404를 돌려준다 (방 id 추측 방지).
- 메시지는 id 기준 커서 페이지네이션이며 항상 오래된 순으로 반환한다. 탈퇴·정지된 상대에게는 보낼 수 없다(409).
- 실시간 수신: `ws://<host>/api/v1/chat/ws` 연결 후 10초 안에 `{"type":"auth","token":"<access_token>"}` 전송
  → `ready` 응답 후 `message` / `read` / `trade` 이벤트가 푸시된다. 보내기는 REST로 한다.
  토큰은 쿼리스트링이 아니라 첫 메시지로 받는다 (액세스 로그에 토큰이 남지 않도록). 만료·로그아웃 시 4401로 종료.
- 이벤트는 Redis Pub/Sub(`specgrid:{db}:chat:user:{user_id}`)로 전달되어 여러 서버 프로세스에서도 동작한다.
  전달은 best-effort이고 DB가 원본이므로, 재연결한 클라이언트는 `after_id`로 놓친 메시지를 가져온다.

### 거래 (구매 흐름)

```
requested ──accept──▶ accepted ──complete──▶ completed      상품: on_sale → reserved → sold
    ├─reject──▶ rejected   └─cancel──▶ canceled (상품 다시 on_sale)
    └─cancel──▶ canceled
```

- 요청은 판매중 상품에만, 구매자당 상품별 진행 중 요청 1개. 여러 구매자가 동시에 요청할 수 있고 판매자가 하나를 수락한다.
- 가격은 요청 시점 값으로 저장된다. 예약중인 상품은 수동 상태 변경·삭제가 막힌다(409). 삭제 시 대기 요청은 자동 거절.
- **동시성 방어 3단계**: ① Redis 분산 락 `specgrid:lock:product:{id}` (TTL 10초, 최대 3초 대기 후 409)
  ② 트랜잭션 안에서 상품 행 `SELECT ... FOR UPDATE` (항상 상품 → 거래 순으로 잠가 데드락 방지)
  ③ DB 유니크 인덱스(생성 컬럼): 상품당 accepted 1건, 구매자·상품당 진행 중 요청 1건.
- 상태가 바뀔 때마다 구매자·판매자에게 WebSocket `{"type":"trade","trade":{...}}` 이벤트를 보낸다.
- MariaDB 11.6+의 `innodb_snapshot_isolation` 때문에, 락을 잡기 전에 읽기 트랜잭션을 끝내고 새로 시작한다
  (`trade_service._end_read_snapshot`). 그래도 남는 DB 충돌(1020/1205/1213)은 500이 아니라 409로 응답한다.

### 찜

- `favorites` (UQ user_id+product_id) + `products.favorite_count`(비정규화 카운터)를 같은 트랜잭션에서 함께 바꾼다.
  PUT/DELETE는 멱등: 중복 요청은 에러 없이 무시되고 카운트도 변하지 않는다 (동시 중복 INSERT는 유니크 키가 막음).
- 본인 상품(400), 판매완료(409), 숨김·삭제(404)는 찜할 수 없다. 찜 취소는 상품 상태와 관계없이 가능.
- 상품 상세·검색 응답에 `favorite_count`와 `is_favorited`(로그인 시 true/false, 비로그인 null)가 포함된다.
  검색 결과의 하트 상태는 페이지당 쿼리 1번으로 조회한다.

### 활동 로그 · 랭킹

- `user_activity_logs`에 조회(view)·검색(search)·채팅 시작(chat)·거래 단계(trade)를 기록한다. 채팅 내용은 저장하지 않는다.
- 로그 저장 실패는 서버 로그에만 남기고 사용자 요청은 그대로 성공시킨다 (best-effort).
- **어뷰징 방지**: 같은 사람(로그인 사용자 id, 비로그인은 IP+User-Agent)의 같은 상품 조회는 30분, 같은 검색어는 10분에 1번만 센다.
  판매자 본인 조회는 세지 않는다. `products.view_count`도 같은 규칙. (Redis `specgrid:seen:*`, Redis 장애 시엔 그냥 센다)
- 검색어는 소문자 + 공백 정리 후 저장(`"  RTX  4080"` → `"rtx 4080"`). 키워드 없는 필터 검색과 2페이지 이후는 기록하지 않는다.
- 랭킹은 DB 집계(`GROUP BY` + `COUNT`)로 계산하고 Redis에 60초 캐시한다(`specgrid:ranking:*`).
  커버링 인덱스 `(activity_type, created_at, search_keyword | product_id)`로 기간 범위만 인덱스에서 읽는다.
- 상품 공개 API는 토큰이 있으면 로그인 사용자로, 없거나 잘못됐으면 비로그인으로 기록한다 (에러 없음).

샘플 데이터 (개발 DB 전용, `detail.seed=true`로 표시되어 따로 지울 수 있음):

```bash
python -m scripts.seed_activity                         # 검색 300 + 조회 600건 (최근 7일)
python -m scripts.seed_activity --searches 1000 --views 3000 --days 30
python -m scripts.seed_activity --clear                 # 샘플만 삭제
```

### 상품 사진

- JPG/PNG/WebP만 허용. 확장자·Content-Type이 아니라 실제 파일 내용을 Pillow로 디코딩해 판별한다.
- 장당 10MB, 상품당 10장, 40MP 초과(압축 폭탄) 거부. 한 장이라도 잘못되면 전체를 저장하지 않는다.
- WebP로 재인코딩(원본 최대 1600px, 썸네일 400px)하면서 **EXIF(GPS 위치 포함)를 제거**하고 회전값은 적용한다.
- DB에는 저장 키(`products/{id}/{uuid}.webp`)만 저장하고 URL은 `MEDIA_BASE_URL`로 만든다.
  지금은 로컬 `media/` 폴더(개발 서버가 `/media`로 제공), 운영에서는 `app/core/storage.py`의 백엔드를 S3 등으로 교체한다.
- 운영 환경에서는 리버스 프록시에서도 요청 크기를 제한한다 (예: nginx `client_max_body_size 100m`).

### Redis (Memurai 4 / Redis 7 호환, 포트 6379)

| 키 | 용도 |
|---|---|
| `specgrid:auth:refresh:{jti}` | 미사용 refresh 토큰 허용 목록 (TTL = 토큰 만료) |
| `specgrid:auth:revoked:{jti}` | 로그아웃한 access 토큰 (TTL = 토큰 만료) |
| `specgrid:auth:gen:{user_id}` | 토큰 세대 번호. logout-all 시 증가 → 이전 토큰 전부 무효 |
| `specgrid:login_fail:email:{sha256}` / `:ip:{ip}` | 로그인 실패 카운터 (이메일 5회 / IP 30회, 15분) |
| `specgrid:lock:product:{id}` | 상품별 거래 분산 락 (TTL 10초, 소유자만 해제) |
| `specgrid:{db}:chat:user:{id}` (Pub/Sub 채널) | 사용자별 실시간 이벤트 |

Redis에 연결할 수 없으면 인증이 필요한 요청과 로그인은 503으로 거부한다 (fail closed). 공개 상품 조회는 영향 없음.
리버스 프록시 뒤에서는 `uvicorn --proxy-headers --forwarded-allow-ips=<프록시 IP>`로 실행해야 IP 제한이 실제 클라이언트 IP로 동작한다.
테스트는 Redis DB 15번을 사용하고 매 테스트마다 비운다.

에러 응답은 항상 `{"code": "...", "message": "..."}` 형식이다 (입력 검증 실패는 FastAPI 기본 422).

## 테스트

```bash
pip install -r requirements-dev.txt
pytest                          # API·서비스 테스트 (specgrid_test DB)
python tests_e2e/run_e2e.py     # 화면 E2E (specgrid_e2e DB, 포트 8001, 설치된 Chrome 사용)
python tests_e2e/run_e2e.py --headed --shots e2e-shots   # 브라우저가 움직이는 걸 보고, 스크린샷 저장
```

E2E는 판매자·구매자 브라우저 두 개를 동시에 띄워 가입부터 판매·검색·찜·실시간 채팅·구매 요청·수락·완료·랭킹·
토큰 자동 재발급·로그아웃·모바일 레이아웃까지 33단계를 확인하고, 어느 브라우저에서든 JS 에러나 5xx가 나면 실패한다.
실행할 때마다 `specgrid_e2e` DB와 Redis **14번** DB만 비운다 (개발용 0번, pytest용 15번은 건드리지 않음). 최초 1회 root로 E2E DB를 만든다:

```sql
CREATE DATABASE specgrid_e2e CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES ON specgrid_e2e.* TO 'specgrid_migrator'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid_e2e.* TO 'specgrid_app'@'localhost';
-- 그 다음: DB_NAME=specgrid_e2e alembic upgrade head
```

테스트는 개발 DB가 아닌 `specgrid_test` DB에서 실행되며, 테스트마다 트랜잭션을 롤백해 데이터가 남지 않는다.
최초 1회 root로 테스트 DB를 만든다:

```sql
CREATE DATABASE specgrid_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES ON specgrid_test.* TO 'specgrid_migrator'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid_test.* TO 'specgrid_app'@'localhost';
```

## 모델 변경 시

```bash
alembic revision --autogenerate -m "add favorites"
alembic upgrade head
```

새 모델 파일은 `app/models/__init__.py`에 import해야 autogenerate가 인식한다.

## ERD 요약

| 테이블 | 주요 컬럼 | 관계 |
|---|---|---|
| users | email(UQ), password_hash(소셜 로그인은 NULL), nickname(UQ), role, status | |
| products | category, title, price, condition, status, is_hot_deal, view_count, deleted_at(소프트 삭제) | seller_id → users |
| product_specs | manufacturer, cpu_model, cpu_cores, ram_gb, gpu_model, vram_gb, storage_gb, extra_specs(JSON) | product_id → products (1:1, CASCADE) |
| chat_rooms | last_message_at, UQ(product_id, buyer_id), CHECK buyer≠seller | product, buyer, seller |
| chat_messages | message_type, content, is_read, IX(room_id, id) | room_id → chat_rooms (CASCADE), sender_id → users |
| trades | price(요청 시점), status, message, responded_at, completed_at, 생성 컬럼 active_buyer_id / accepted_product_id (UQ) | product_id → products, buyer_id / seller_id → users |
| user_activity_logs | activity_type, session_id(비로그인), search_keyword, detail(JSON), ip, UA | user_id·product_id → SET NULL |
