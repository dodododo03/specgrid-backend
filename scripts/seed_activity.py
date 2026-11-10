"""Fill the DEV database with fake searches and product views so the rankings have something to show.

    python -m scripts.seed_activity                 # 300 searches + 600 views over the last 7 days
    python -m scripts.seed_activity --searches 1000 --views 3000 --days 30
    python -m scripts.seed_activity --clear         # remove only the fake rows again

Fake rows are marked with detail = {"seed": true}, so --clear never touches real activity.
Views are spread over existing on-sale products with a skewed distribution (a few products get most
views), like real traffic. products.view_count (the "all" period) is NOT changed.
"""

import argparse
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Product, UserActivityLog
from app.models.enums import ActivityType, ProductStatus

# (keyword, weight): higher weight = searched more often
KEYWORDS = [
    ("rtx 4090", 30), ("rtx 4080", 25), ("라이젠 7", 22), ("맥북 프로", 20), ("rtx 4070", 18),
    ("ddr5", 15), ("라이젠 9", 12), ("갤럭시북", 10), ("nvme ssd", 10), ("4k 모니터", 9),
    ("기계식 키보드", 8), ("i7 14700k", 8), ("rx 7900", 6), ("맥미니", 6), ("서버 랙", 3),
    ("에어팟", 3), ("hdd 8tb", 2), ("게이밍 노트북", 7), ("그래픽카드", 14), ("cpu", 5),
]


def _random_time(days: int) -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    return now - timedelta(seconds=random.randint(0, days * 24 * 3600))


def _fake_viewer() -> dict:
    return {"ip_address": f"10.0.{random.randint(0, 255)}.{random.randint(1, 254)}", "user_agent": "seed-script"}


def seed(searches: int, views: int, days: int) -> None:
    with SessionLocal() as db:
        product_ids = list(db.scalars(
            select(Product.id).where(Product.deleted_at.is_(None), Product.status == ProductStatus.ON_SALE)
        ))
        words, weights = zip(*KEYWORDS)
        rows = [
            UserActivityLog(activity_type=ActivityType.SEARCH, search_keyword=random.choices(words, weights)[0],
                            created_at=_random_time(days), detail={"seed": True}, **_fake_viewer())
            for _ in range(searches)
        ]
        if product_ids:
            # Zipf-like popularity: the 1st product is ~N times as popular as the N-th.
            shuffled = random.sample(product_ids, len(product_ids))
            popularity = [1 / (rank + 1) for rank in range(len(shuffled))]
            rows += [
                UserActivityLog(activity_type=ActivityType.VIEW, product_id=random.choices(shuffled, popularity)[0],
                                created_at=_random_time(days), detail={"seed": True}, **_fake_viewer())
                for _ in range(views)
            ]
        else:
            print("판매중인 상품이 없어 조회 기록은 건너뜁니다. (상품을 먼저 등록하세요)")
        db.add_all(rows)
        db.commit()
        print(f"추가 완료: 검색 {searches}건, 조회 {views if product_ids else 0}건 "
              f"(최근 {days}일, 상품 {len(product_ids)}개 대상)")


def clear() -> None:
    with SessionLocal() as db:
        result = db.execute(
            delete(UserActivityLog).where(
                UserActivityLog.user_agent == "seed-script",
                func.json_extract(UserActivityLog.detail, "$.seed") == "true",
            )
        )
        db.commit()
        print(f"샘플 데이터 {result.rowcount}건 삭제")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--searches", type=int, default=300)
    parser.add_argument("--views", type=int, default=600)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--clear", action="store_true", help="샘플 데이터만 삭제")
    args = parser.parse_args()

    if settings.db_name.endswith("_test"):
        raise SystemExit("테스트 DB에는 실행하지 않습니다.")
    print(f"대상 DB: {settings.db_name}")
    clear() if args.clear else seed(args.searches, args.views, args.days)


if __name__ == "__main__":
    main()
