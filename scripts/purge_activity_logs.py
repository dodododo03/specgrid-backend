"""Activity-log retention: keep personal data only as long as it is useful.

    python -m scripts.purge_activity_logs              # anonymize after 30 days, delete after 180 days
    python -m scripts.purge_activity_logs --dry-run    # only print how many rows would change
    python -m scripts.purge_activity_logs --anonymize-days 7 --delete-days 90

1) Rows older than --anonymize-days: user_id / session_id / ip_address / user_agent are set to NULL.
   The rankings only look back 30 days (period=month), so older rows never need to know *who*.
2) Rows older than --delete-days are deleted entirely.

Runs with the migrator account (scripts/admin_db.py), because the app account can't modify logs.
On the server, schedule it daily (cron: `0 4 * * * cd /srv/specgrid && .venv/bin/python -m scripts.purge_activity_logs`).
"""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update

from app.models import UserActivityLog
from scripts.admin_db import AdminSession

L = UserActivityLog
RANKING_WINDOW_DAYS = 30  # longest ranking period (Period.MONTH)


def purge(anonymize_days: int, delete_days: int, dry_run: bool) -> tuple[int, int]:
    now = datetime.now(UTC).replace(tzinfo=None)  # created_at is naive UTC
    anon_before = now - timedelta(days=anonymize_days)
    delete_before = now - timedelta(days=delete_days)
    personal = or_(L.user_id.is_not(None), L.session_id.is_not(None), L.ip_address.is_not(None),
                   L.user_agent.is_not(None))

    with AdminSession() as db:
        if dry_run:
            n_anon = db.scalar(select(func.count()).where(L.created_at < anon_before, L.created_at >= delete_before,
                                                          personal))
            n_del = db.scalar(select(func.count()).where(L.created_at < delete_before))
            return n_anon or 0, n_del or 0
        n_del = db.execute(delete(L).where(L.created_at < delete_before)).rowcount
        n_anon = db.execute(
            update(L).where(L.created_at < anon_before, personal)
            .values(user_id=None, session_id=None, ip_address=None, user_agent=None)
        ).rowcount
        db.commit()
        return n_anon, n_del


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--anonymize-days", type=int, default=30)
    parser.add_argument("--delete-days", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.anonymize_days < 0 or args.delete_days < args.anonymize_days:
        raise SystemExit("--delete-days 는 --anonymize-days 이상이어야 합니다.")
    if args.delete_days < RANKING_WINDOW_DAYS:
        print(f"주의: {args.delete_days}일 보다 오래된 기록이 지워져 월간 랭킹({RANKING_WINDOW_DAYS}일)이 줄어듭니다.")

    n_anon, n_del = purge(args.anonymize_days, args.delete_days, args.dry_run)
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}익명화 {n_anon}건 ({args.anonymize_days}일 경과), 삭제 {n_del}건 ({args.delete_days}일 경과)")


if __name__ == "__main__":
    main()
