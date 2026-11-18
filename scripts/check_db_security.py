"""Prove the runtime DB account (specgrid_app, from .env) is locked down — run after harden_db_privileges.sql.

    python -m scripts.check_db_security

Connects exactly like the web server does and *tries* things it should and shouldn't be able to do.
Nothing is changed: every statement runs in a transaction that is rolled back.
Exit code 1 if any check fails (usable in a deploy script).
"""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import DB_CONNECT_ARGS, settings
from app.models import UserActivityLog
from app.models.enums import ActivityType

DENIED = {1142, 1143, 1044, 1045}  # table / column / database access denied

# (description, SQL, should_succeed)
CHECKS: list[tuple[str, str, bool]] = [
    ("랭킹용 컬럼 조회 (허용되어야 함)",
     "SELECT id, activity_type, created_at, search_keyword, product_id FROM user_activity_logs LIMIT 1", True),
    ("활동 기록 추가 (허용되어야 함)",
     "INSERT INTO user_activity_logs (activity_type) VALUES ('view')", True),
    ("상품 조회 (허용되어야 함)", "SELECT id FROM products LIMIT 1", True),
    ("로그의 IP 조회 차단", "SELECT ip_address FROM user_activity_logs LIMIT 1", False),
    ("로그의 사용자 ID 조회 차단", "SELECT user_id FROM user_activity_logs LIMIT 1", False),
    ("로그의 브라우저 정보 조회 차단", "SELECT user_agent FROM user_activity_logs LIMIT 1", False),
    ("로그의 세션 ID 조회 차단", "SELECT session_id FROM user_activity_logs LIMIT 1", False),
    ("로그의 detail 조회 차단", "SELECT detail FROM user_activity_logs LIMIT 1", False),
    ("SELECT * 로 로그 통째로 조회 차단", "SELECT * FROM user_activity_logs LIMIT 1", False),
    ("로그 수정(조작) 차단", "UPDATE user_activity_logs SET search_keyword = 'x' WHERE id = -1", False),
    ("로그 삭제(증거 인멸) 차단", "DELETE FROM user_activity_logs WHERE id = -1", False),
    ("마이그레이션 버전 테이블 접근 차단", "SELECT * FROM alembic_version", False),
    ("테이블 생성(DDL) 차단", "CREATE TABLE specgrid_privilege_probe (x INT)", False),
    ("테이블 삭제(DDL) 차단", "DROP TABLE user_activity_logs", False),
    ("MariaDB 계정 목록 조회 차단", "SELECT user FROM mysql.user LIMIT 1", False),
]


def main() -> None:
    engine = create_engine(settings.database_url, connect_args=DB_CONNECT_ARGS)
    print(f"계정 {settings.db_user}@{settings.db_host}:{settings.db_port}/{settings.db_name} 으로 점검합니다.\n")
    failed = 0
    for desc, sql, should_succeed in CHECKS:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(sql))
                ok, why = should_succeed, "실행됨"
            except DBAPIError as exc:
                code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
                if code not in DENIED:
                    ok, why = False, f"예상 밖의 오류 {code}: {exc.orig}"
                else:
                    ok, why = not should_succeed, f"권한 거부 ({code})"
            finally:
                trans.rollback()
        failed += not ok
        print(f"  {'✅' if ok else '❌'} {desc} — {why}")

    # The exact code path the web server uses (ORM insert). Raw SQL alone isn't enough: e.g. an
    # INSERT ... RETURNING would need SELECT on the personal columns and logging would silently stop.
    with engine.connect() as conn:
        trans = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            log = UserActivityLog(activity_type=ActivityType.VIEW, user_id=None, ip_address="probe", user_agent="probe")
            db.add(log)
            db.flush()
            ok, why = log.id is not None, "실행됨"
        except DBAPIError as exc:
            ok, why = False, f"오류: {exc.orig}"
        finally:
            db.close()
            trans.rollback()
    failed += not ok
    print(f"  {'✅' if ok else '❌'} 앱 코드(ORM)로 활동 기록 저장 (허용되어야 함) — {why}")

    with engine.connect() as conn:
        bind = conn.scalar(text("SELECT @@bind_address"))
    print()
    if bind in ("127.0.0.1", "localhost", "::1"):
        print(f"  ✅ MariaDB가 이 컴퓨터에서만 접속을 받음 (bind_address={bind})")
    else:
        print(f"  ⚠️  MariaDB가 외부 네트워크에서도 접속을 받음 (bind_address={bind or '모든 주소'}). "
              "서버에서는 my.cnf에 bind-address=127.0.0.1 권장")

    print(f"\n{'모든 점검 통과' if not failed else f'실패 {failed}건 — scripts/harden_db_privileges.sql 을 root로 실행하세요'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
