# SpecGrid API — 스펙그리드 백엔드

전자기기·IT 하드웨어 중고거래 플랫폼 백엔드. FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · Redis · MariaDB.

## 디렉토리 구조

```
specgrid-backend/
├── app/
│   ├── main.py                 # FastAPI 앱 팩토리 (CORS, 라우터 등록)
│   ├── core/
│   │   ├── config.py           # .env 기반 설정 (pydantic-settings)
│   │   └── redis.py            # Redis 클라이언트 / 의존성
│   ├── db/
│   │   ├── base.py             # DeclarativeBase, 제약조건 네이밍 규칙, 타임스탬프 믹스인
│   │   └── session.py          # 엔진, SessionLocal, get_db 의존성
│   ├── models/                 # SQLAlchemy 모델 (ERD)
│   │   ├── enums.py
│   │   ├── user.py             # users
│   │   ├── product.py          # products, product_specs
│   │   ├── chat.py             # chat_rooms, chat_messages
│   │   └── activity.py         # user_activity_logs
│   ├── schemas/                # Pydantic 요청/응답 스키마
│   ├── services/               # 비즈니스 로직
│   └── api/v1/
│       ├── router.py
│       └── endpoints/health.py # GET /api/v1/health (DB·Redis 상태)
├── alembic/
│   ├── env.py                  # .env의 DB 설정과 app.models 메타데이터 사용
│   └── versions/               # 0001_initial_schema
├── alembic.ini
├── requirements.txt
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
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

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
| GET | `/api/v1/users/me/products` | ✅ | 내 판매 상품 (숨김·판매완료 포함, `status` 필터) |

### Redis (Memurai 4 / Redis 7 호환, 포트 6379)

| 키 | 용도 |
|---|---|
| `specgrid:auth:refresh:{jti}` | 미사용 refresh 토큰 허용 목록 (TTL = 토큰 만료) |
| `specgrid:auth:revoked:{jti}` | 로그아웃한 access 토큰 (TTL = 토큰 만료) |
| `specgrid:auth:gen:{user_id}` | 토큰 세대 번호. logout-all 시 증가 → 이전 토큰 전부 무효 |
| `specgrid:login_fail:email:{sha256}` / `:ip:{ip}` | 로그인 실패 카운터 (이메일 5회 / IP 30회, 15분) |

Redis에 연결할 수 없으면 인증이 필요한 요청과 로그인은 503으로 거부한다 (fail closed). 공개 상품 조회는 영향 없음.
리버스 프록시 뒤에서는 `uvicorn --proxy-headers --forwarded-allow-ips=<프록시 IP>`로 실행해야 IP 제한이 실제 클라이언트 IP로 동작한다.
테스트는 Redis DB 15번을 사용하고 매 테스트마다 비운다.

에러 응답은 항상 `{"code": "...", "message": "..."}` 형식이다 (입력 검증 실패는 FastAPI 기본 422).

## 테스트

```bash
pip install -r requirements-dev.txt
pytest
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
| user_activity_logs | activity_type, session_id(비로그인), search_keyword, detail(JSON), ip, UA | user_id·product_id → SET NULL |
