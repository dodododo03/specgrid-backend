"""Create demo sellers and products with real photos, through the public HTTP API.

    python -m scripts.seed_demo                                         # local server (localhost:8000)
    python -m scripts.seed_demo --base-url https://specgrid.duckdns.org # the live site
    python -m scripts.seed_demo --password 'MyDemoPw1!'                 # choose the sellers' password

Going through the API (not the DB) means the same code path as a real user: validation, photo
re-encoding/EXIF stripping, trade-point checks. Only the standard library is used, so it runs
from any machine with Python. Safe to run twice: existing sellers log in, products with the same
title are skipped.

Photos: Wikimedia Commons, free licenses (CC0 / CC BY / CC BY-SA). The author and license are
added to each product's description, see scripts/demo_data/photo_credits.json.
"""

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DATA = Path(__file__).parent / "demo_data"

SELLERS = [
    {"email": "demo.yongsan@specgrid.duckdns.org", "nickname": "용산부품왕"},
    {"email": "demo.pangyo@specgrid.duckdns.org", "nickname": "판교개발자"},
    {"email": "demo.hongdae@specgrid.duckdns.org", "nickname": "홍대작업실"},
]

# Trade spots (name, lat, lng)
YONGSAN = ("용산전자상가 나진상가", 37.5313, 126.9632)
GANGNAM = ("강남역 11번 출구", 37.4981, 127.0276)
PANGYO = ("판교역 1번 출구", 37.3948, 127.1112)
HONGDAE = ("홍대입구역 9번 출구", 37.5571, 126.9245)
JAMSIL = ("잠실역 8번 출구", 37.5133, 127.1001)
SINDORIM = ("신도림역 테크노마트 앞", 37.5072, 126.8903)

# seller index, photo slug, category, condition, price, place, title, description, spec
PRODUCTS = [
    (0, "gpu-rtx3090", "gpu", "used", 690000, YONGSAN, "기가바이트 RTX 3090 이글 OC 24GB",
     "채굴 이력 없는 게이밍 전용 카드입니다. 2년 정도 사용했고 써멀패드는 작년에 교체했어요.\n"
     "풀로드 시 코어 72도 정도. 박스 없음, 본품만 드립니다. 용산 직거래 시 테스트 가능해요.",
     {"manufacturer": "GIGABYTE", "model_name": "RTX 3090 EAGLE OC", "gpu_model": "RTX 3090", "vram_gb": 24}),
    (0, "gpu-rtx3070", "gpu", "lightly_used", 290000, YONGSAN, "MSI RTX 3070 벤투스 3X OC 8GB",
     "4070으로 업그레이드하면서 내놓습니다. 사용감 적고 코일 소음 거의 없어요.\n"
     "QHD 게임용으로 아직 충분합니다. 정품 박스 포함.",
     {"manufacturer": "MSI", "model_name": "VENTUS 3X OC", "gpu_model": "RTX 3070", "vram_gb": 8}),
    (1, "gpu-rtx5060ti", "gpu", "like_new", 520000, PANGYO, "PNY RTX 5060 Ti 16GB 듀얼팬",
     "구매 후 한 달 사용했습니다. 로컬 LLM 돌리려고 샀는데 VRAM이 더 필요해서 판매해요.\n"
     "영수증 있고 무상 AS 기간 넉넉히 남았습니다.",
     {"manufacturer": "PNY", "model_name": "RTX 5060 Ti Dual Fan OC", "gpu_model": "RTX 5060 Ti", "vram_gb": 16}),
    (0, "cpu-5900x", "cpu", "used", 210000, YONGSAN, "AMD 라이젠9 5900X 12코어",
     "AM4 마지막 세대 플래그십입니다. 오버클럭 안 했고 핀 휨 없어요.\n"
     "쿨러는 미포함입니다. 트레이 상태로 드려요.",
     {"manufacturer": "AMD", "model_name": "Ryzen 9 5900X", "cpu_model": "Ryzen 9 5900X", "cpu_cores": 12}),
    (1, "cpu-9950x", "cpu", "like_new", 640000, PANGYO, "AMD 라이젠9 9950X 16코어 (정품)",
     "빌드 서버용으로 샀다가 회사 장비로 대체돼서 판매합니다. 사용 기간 2주.\n"
     "정품 박스·스티커 모두 있어요. 판교역 근처 직거래 선호합니다.",
     {"manufacturer": "AMD", "model_name": "Ryzen 9 9950X", "cpu_model": "Ryzen 9 9950X", "cpu_cores": 16}),
    (1, "ram-ddr5-sodimm", "ram", "lightly_used", 85000, GANGNAM, "킹스톤 FURY Impact DDR5 32GB 노트북용",
     "노트북 램 업그레이드하고 남은 32GB 1장입니다. 5600MHz, 이상 없음.\n"
     "MemTest 4패스 통과 확인했어요.",
     {"manufacturer": "Kingston", "model_name": "FURY Impact DDR5 SO-DIMM", "ram_gb": 32,
      "extra_specs": {"규격": "DDR5 SO-DIMM", "클럭": "5600MHz"}}),
    (0, "ssd-980pro", "storage", "used", 79000, SINDORIM, "삼성 980 PRO 1TB NVMe",
     "PCIe 4.0 NVMe입니다. 사용 시간 약 3,000시간, 수명 96% 남았어요.\n"
     "CrystalDiskInfo 캡처 보내드릴 수 있습니다. PS5 증설용으로도 좋아요.",
     {"manufacturer": "삼성전자", "model_name": "980 PRO", "storage_gb": 1000, "storage_type": "NVMe"}),
    (2, "hdd-exos12tb", "storage", "used", 140000, HONGDAE, "씨게이트 엑소스 12TB 엔터프라이즈 HDD",
     "NAS에서 쓰던 하드입니다. 배드섹터 없고 S.M.A.R.T. 정상이에요.\n"
     "데이터는 완전 삭제했습니다. 7200rpm이라 소음은 좀 있어요.",
     {"manufacturer": "Seagate", "model_name": "Exos X12 ST12000NM0117", "storage_gb": 12000, "storage_type": "HDD"}),
    (1, "laptop-mbp13-m1", "laptop", "lightly_used", 750000, GANGNAM, "맥북 프로 13 M1 16GB/512GB",
     "배터리 성능 89%, 외관 찍힘 없습니다. 개발용으로만 썼어요.\n"
     "충전기 포함, 박스 있음. 강남역에서 직접 확인하고 가져가세요.",
     {"manufacturer": "Apple", "model_name": "MacBook Pro 13 (M1, 2020)", "cpu_model": "Apple M1",
      "cpu_cores": 8, "ram_gb": 16, "storage_gb": 512, "storage_type": "NVMe"}),
    (2, "laptop-galaxybook", "laptop", "lightly_used", 820000, HONGDAE, "삼성 갤럭시북 프로 360 15인치",
     "S펜 포함 터치 노트북입니다. 그림 작업용으로 썼고 화면 상태 아주 좋아요.\n"
     "i7 / 16GB / 512GB. 정품 충전기 드립니다.",
     {"manufacturer": "삼성전자", "model_name": "Galaxy Book Pro 360", "cpu_model": "Intel Core i7-1165G7",
      "cpu_cores": 4, "ram_gb": 16, "storage_gb": 512, "storage_type": "NVMe"}),
    (0, "desktop-gaming", "desktop", "used", 1350000, YONGSAN, "게이밍 본체 (라이젠7 + RTX 4070)",
     "직접 조립한 본체입니다. 라이젠7 7800X3D / RTX 4070 / 32GB / 1TB NVMe.\n"
     "케이스는 콜링크 옵저버토리 RGB, 윈도우 정품 인증 상태로 드려요. 용산 직거래만 합니다.",
     {"manufacturer": "조립PC", "model_name": "커스텀 게이밍 PC", "cpu_model": "Ryzen 7 7800X3D", "cpu_cores": 8,
      "ram_gb": 32, "gpu_model": "RTX 4070", "vram_gb": 12, "storage_gb": 1000, "storage_type": "NVMe"}),
    (2, "desktop-macmini", "desktop", "used", 380000, HONGDAE, "맥 미니 2018 i5 / 16GB",
     "홈서버로 쓰던 맥미니입니다. 조용하고 전기 적게 먹어서 서버용으로 추천해요.\n"
     "macOS 초기화 완료했습니다.",
     {"manufacturer": "Apple", "model_name": "Mac mini (2018)", "cpu_model": "Intel Core i5-8500B",
      "cpu_cores": 6, "ram_gb": 16, "storage_gb": 256, "storage_type": "NVMe"}),
    (1, "server-huawei", "server", "used", 450000, PANGYO, "화웨이 RH2288H V2 2U 랙서버",
     "사내 테스트 장비 정리합니다. 제온 E5 2개, 메모리 128GB 장착 상태예요.\n"
     "랙 레일 포함. 무거워서 직접 가져가셔야 합니다 (판교).",
     {"manufacturer": "Huawei", "model_name": "RH2288H V2", "cpu_model": "Xeon E5-2650 v2 x2",
      "cpu_cores": 16, "ram_gb": 128, "extra_specs": {"폼팩터": "2U"}}),
    (2, "monitor-ultrawide", "monitor", "lightly_used", 330000, HONGDAE, "델 34인치 울트라와이드 모니터 (3440x1440)",
     "영상 편집할 때 쓰던 커브드 울트라와이드입니다. 불량화소 없어요.\n"
     "스탠드, 전원선, DP 케이블 포함입니다.",
     {"manufacturer": "Dell", "model_name": "34 Curved Ultrawide", "extra_specs": {"해상도": "3440x1440", "크기": "34인치"}}),
    (2, "keyboard-mech", "keyboard", "like_new", 95000, HONGDAE, "RGB 기계식 키보드 (적축)",
     "구매 후 몇 번 안 썼어요. 적축이라 조용한 편입니다.\n"
     "RGB 정상 작동, 키캡 번들 포함.",
     {"manufacturer": "기타", "model_name": "RGB 기계식 키보드", "extra_specs": {"스위치": "적축"}}),
    (2, "audio-sony", "audio", "used", 35000, JAMSIL, "소니 WH-CH510 블루투스 헤드폰",
     "가볍고 배터리 오래가요 (최대 35시간). 사용감 약간 있지만 소리 이상 없습니다.\n"
     "잠실역 직거래 또는 택배 가능.",
     {"manufacturer": "Sony", "model_name": "WH-CH510"}),
    (1, "audio-airpods", "audio", "lightly_used", 170000, GANGNAM, "에어팟 프로 2세대 (USB-C)",
     "애플케어 남아 있습니다. 이어팁 새것으로 교체해서 드려요.\n"
     "배터리 정상, 노이즈캔슬링 잘 됩니다.",
     {"manufacturer": "Apple", "model_name": "AirPods Pro (2nd generation)"}),
    (0, "etc-g903", "etc", "used", 65000, YONGSAN, "로지텍 G903 무선 게이밍 마우스",
     "더블클릭 증상 없습니다. 리시버, 연장 어댑터 포함.\n"
     "파워플레이 패드는 미포함이에요.",
     {"manufacturer": "Logitech", "model_name": "G903 LIGHTSPEED"}),
]


class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/") + "/api/v1"

    def call(self, method, path, body=None, token=None, files=None):
        headers = {"Accept": "application/json"}
        data = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if files is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for name, filename, content in files:
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: image/jpeg\r\n\r\n".encode() + content + b"\r\n"
                )
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                text = res.read().decode()
                return res.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as err:
            text = err.read().decode()
            try:
                return err.code, json.loads(text)
            except ValueError:
                return err.code, text


def login_or_signup(api: Api, seller: dict, password: str) -> str:
    status, body = api.call("POST", "/auth/login", {"email": seller["email"], "password": password})
    if status == 200:
        print(f"  로그인: {seller['nickname']}")
        return body["access_token"]
    status, body = api.call("POST", "/auth/signup", {
        **seller, "password": password, "agree_terms": True, "agree_privacy": True, "over_14": True,
    })
    if status != 201:
        sys.exit(f"가입 실패 ({seller['email']}): {status} {body}\n"
                 "이미 가입된 계정이면 처음 실행할 때 쓴 --password 를 넣어 주세요.")
    print(f"  가입: {seller['nickname']} ({seller['email']})")
    status, body = api.call("POST", "/auth/login", {"email": seller["email"], "password": password})
    if status != 200:
        sys.exit(f"로그인 실패 ({seller['email']}): {status} {body}")
    return body["access_token"]


def my_titles(api: Api, token: str) -> set[str]:
    titles, page = set(), 1
    while True:
        status, body = api.call("GET", f"/users/me/products?page={page}&size=50", token=token)
        if status != 200:
            sys.exit(f"내 상품 조회 실패: {status} {body}")
        titles |= {p["title"] for p in body["items"]}
        if not body["has_next"]:
            return titles
        page += 1


def credit_line(credit: dict) -> str:
    return f"\n\n(사진: {credit['author']}, {credit['license']}, Wikimedia Commons)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--password", help="데모 판매자 비밀번호 (생략하면 새로 만들어 출력)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    password = args.password or "Demo-" + secrets.token_urlsafe(9) + "1!"
    credits = json.loads((DATA / "photo_credits.json").read_text(encoding="utf-8"))
    api = Api(args.base_url)

    status, _ = api.call("GET", "/health")
    if status != 200:
        sys.exit(f"{args.base_url} 에 연결할 수 없습니다 (health {status}).")

    print("판매자 계정")
    tokens = [login_or_signup(api, s, password) for s in SELLERS]
    existing = [my_titles(api, t) for t in tokens]

    print("상품")
    created = []
    for seller_i, slug, category, condition, price, place, title, desc, spec in PRODUCTS:
        if title in existing[seller_i]:
            print(f"  건너뜀 (이미 있음): {title}")
            continue
        name, lat, lng = place
        status, product = api.call("POST", "/products", {
            "category": category, "title": title, "description": desc + credit_line(credits[slug]),
            "price": price, "condition": condition, "trade_location": name,
            "trade_point": {"lat": lat, "lng": lng}, "spec": spec,
        }, token=tokens[seller_i])
        if status != 201:
            sys.exit(f"상품 등록 실패 ({title}): {status} {product}")
        photo = (DATA / "photos" / f"{slug}.jpg").read_bytes()
        status, body = api.call("POST", f"/products/{product['id']}/images", token=tokens[seller_i],
                                files=[("files", f"{slug}.jpg", photo)])
        if status != 201:
            sys.exit(f"사진 업로드 실패 ({title}): {status} {body}")
        created.append((seller_i, product["id"]))
        print(f"  등록: #{product['id']} {title}")

    # A little activity so the 찜/조회 rankings aren't empty: sellers browse and like each other's items.
    for i, (seller_i, pid) in enumerate(created):
        for viewer in range(len(SELLERS)):
            if viewer == seller_i:
                continue
            api.call("GET", f"/products/{pid}", token=tokens[viewer])
            if (i + viewer) % 2 == 0:
                api.call("PUT", f"/products/{pid}/favorite", token=tokens[viewer])

    print(f"\n완료: 새 상품 {len(created)}개 → {args.base_url}")
    if not args.password:
        print(f"데모 판매자 비밀번호: {password}   (다시 실행할 땐 --password 로 넣어 주세요)")


if __name__ == "__main__":
    main()
