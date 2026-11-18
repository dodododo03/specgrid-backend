"""End-to-end test of the web frontend in a real Chrome, against a throwaway server.

    python tests_e2e/run_e2e.py              # headless
    python tests_e2e/run_e2e.py --headed     # watch it click around
    python tests_e2e/run_e2e.py --shots DIR  # also save screenshots

What it does:
  1. migrates + wipes the `specgrid_e2e` database and Redis db 14 (never the dev or pytest data)
  2. starts its own uvicorn on :8001 pointed at them
  3. drives TWO browser sessions at once (seller + buyer) through the whole product:
     signup -> sell with photo -> search/filters -> detail -> favorite -> realtime chat both ways
     -> purchase request -> seller accept/complete (with realtime toasts) -> rankings -> profile
     -> silent token refresh -> logout -> mobile layout
  4. fails on any JavaScript error or unexpected 5xx response in either browser

Needs: pip install playwright (uses the installed Google Chrome; no browser download).
"""

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8001
BASE = f"http://localhost:{PORT}"
E2E_DB = "specgrid_e2e"
E2E_REDIS = "redis://localhost:6379/14"

sys.path.insert(0, str(ROOT))


# ------------------------------------------------------------------ environment


def reset_state() -> None:
    os.environ["DB_NAME"] = E2E_DB
    os.environ["REDIS_URL"] = E2E_REDIS
    # Bring the e2e schema up to date first (new migrations would otherwise 500 the server).
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True,
                   env={**os.environ, "DB_NAME": E2E_DB}, stdout=subprocess.DEVNULL)
    import redis
    from sqlalchemy import create_engine, text

    from app.core.config import DB_CONNECT_ARGS, Settings

    s = Settings()
    assert s.db_name == E2E_DB, "refusing to wipe a non-e2e database"
    engine = create_engine(s.database_url, connect_args=DB_CONNECT_ARGS)
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("favorites", "trades", "chat_messages", "chat_rooms", "user_activity_logs",
                      "product_images", "product_specs", "products", "users"):
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    engine.dispose()
    r = redis.Redis.from_url(E2E_REDIS)
    assert r.connection_pool.connection_kwargs["db"] == 14
    r.flushdb()


def start_server(media_root: str) -> subprocess.Popen:
    env = {**os.environ, "DB_NAME": E2E_DB, "REDIS_URL": E2E_REDIS, "MEDIA_ROOT": media_root,
           "MEDIA_BASE_URL": f"{BASE}/media", "APP_ENV": "local",
           # No Kakao key: localhost:8001 isn't a registered Kakao domain anyway, and the fallback
           # (no map, but a working directions link) is what must never break.
           "KAKAO_JS_KEY": "", "PYTHONUNBUFFERED": "1"}
    log = open(Path(media_root) / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{BASE}/api/v1/health", timeout=1) as res:
                if res.status == 200:
                    return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("e2e server did not start; see server.log")


def make_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 600), (24, 36, 29))
    d = ImageDraw.Draw(img)
    d.rectangle((250, 150, 650, 450), fill=(57, 255, 136))
    d.rectangle((300, 200, 600, 400), fill=(18, 24, 22))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ test helpers


class Watch:
    """Collects JS errors and server errors seen by one browser page."""

    def __init__(self, name, page):
        self.name = name
        self.errors: list[str] = []
        page.on("pageerror", lambda e: self.errors.append(f"JS error: {e}"))
        page.on("console", lambda m: m.type == "error" and self._console(m.text))
        page.on("response", lambda r: r.status >= 500 and self.errors.append(f"HTTP {r.status} {r.url}"))

    def _console(self, text):
        # 4xx responses are logged by Chrome as console errors; those are expected in some steps
        if "Failed to load resource" in text and re.search(r"status of 4\d\d", text):
            return
        self.errors.append(f"console: {text}")


STEP = 0


def step(title):
    global STEP
    STEP += 1
    print(f"  [{STEP:02d}] {title}", flush=True)


def run(headed: bool, shots: Path | None) -> None:
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=10_000)
    png = make_png()
    stamp = str(int(time.time()))[-6:]
    seller = {"email": f"seller{stamp}@e2e.kr", "nick": f"판매왕{stamp}", "pw": "Passw0rd!"}
    buyer = {"email": f"buyer{stamp}@e2e.kr", "nick": f"구매자{stamp}", "pw": "Passw0rd!"}
    title = f"RTX 4080 SUPER 16GB 풀박스 e2e{stamp}"

    def shot(page, name):
        if shots:
            page.screenshot(path=str(shots / f"{STEP:02d}-{name}.png"), full_page=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=not headed, slow_mo=60 if headed else 0)
        ctx_s = browser.new_context(viewport={"width": 1366, "height": 900}, locale="ko-KR")
        ctx_b = browser.new_context(viewport={"width": 1366, "height": 900}, locale="ko-KR")
        S, B = ctx_s.new_page(), ctx_b.new_page()
        watches = [Watch("seller", S), Watch("buyer", B)]
        for p in (S, B):
            p.on("dialog", lambda d: d.accept())  # confirm() dialogs: always "OK"

        def signup(page, who):
            page.goto(f"{BASE}/#/signup")
            page.fill('input[name="email"]', who["email"])
            page.fill('input[name="nickname"]', who["nick"])
            page.fill('input[name="password"]', who["pw"])
            page.fill('input[name="password2"]', who["pw"])
            page.click('button:has-text("가입하고 시작하기")')
            expect(page.locator(".user-button")).to_contain_text(who["nick"])

        # ---------------------------------------------------------- home (anonymous)
        step("home page renders for an anonymous visitor")
        S.goto(BASE)
        expect(S.locator(".hero h1")).to_contain_text("다음 주인을 만납니다")
        expect(S.locator(".category-tabs button")).to_have_count(12)
        expect(S.locator("#count")).to_have_text("0")
        expect(S.locator(".empty-state")).to_contain_text("조건에 맞는 상품이 아직 없어요")
        shot(S, "home-empty")

        step("member-only pages show the login gate")
        S.goto(f"{BASE}/#/sell")
        expect(S.locator(".gate h2")).to_have_text("로그인하고 시작하세요")

        step("signup validation messages (client side)")
        S.goto(f"{BASE}/#/signup")
        S.fill('input[name="email"]', "not-an-email")
        S.click('button:has-text("가입하고 시작하기")')
        expect(S.locator("[data-error]")).to_contain_text("이메일")
        S.fill('input[name="email"]', seller["email"])
        S.fill('input[name="nickname"]', seller["nick"])
        S.fill('input[name="password"]', "short")
        S.click('button:has-text("가입하고 시작하기")')
        expect(S.locator("[data-error]")).to_contain_text("8자 이상")

        step("seller signs up and is logged in")
        signup(S, seller)

        step("duplicate email is rejected by the server (409 message shown)")
        B.goto(f"{BASE}/#/signup")
        B.fill('input[name="email"]', seller["email"])
        B.fill('input[name="nickname"]', "다른닉네임")
        B.fill('input[name="password"]', "Passw0rd!")
        B.fill('input[name="password2"]', "Passw0rd!")
        B.click('button:has-text("가입하고 시작하기")')
        expect(B.locator("[data-error]")).to_be_visible()

        step("wrong password shows the server message")
        B.goto(f"{BASE}/#/login")
        B.fill('input[name="email"]', seller["email"])
        B.fill('input[name="password"]', "WrongPass1")
        B.click('button:has-text("로그인")')
        expect(B.locator("[data-error]")).to_be_visible()

        step("buyer signs up in a second browser")
        signup(B, buyer)

        # ---------------------------------------------------------- sell
        step("seller lists a GPU with specs and a photo")
        S.goto(f"{BASE}/#/sell")
        S.fill('input[name="title"]', title)
        S.select_option('select[name="category"]', "gpu")
        S.select_option('select[name="condition"]', "like_new")
        S.fill('input[name="price"]', "1250000")
        S.fill('input[name="trade_location"]', "서울 강남구")
        S.fill('textarea[name="description"]', "2024년 3월 구매, 게임만 가끔 돌렸습니다. 박스·영수증 모두 있어요.")
        S.fill('input[name="manufacturer"]', "NVIDIA")
        S.fill('input[name="gpu_model"]', "RTX 4080 SUPER")
        S.fill('input[name="vram_gb"]', "16")
        expect(S.locator("[data-pv-price]")).to_have_text("1,250,000원")
        S.set_input_files('input[name="photos"]', files=[{"name": "gpu.png", "mimeType": "image/png", "buffer": png}])
        expect(S.locator(".photo-item")).to_have_count(1)
        shot(S, "sell-form")
        S.click('button:has-text("상품 등록하기")')
        expect(S.locator(".detail-title")).to_have_text(title, timeout=20_000)
        expect(S.locator(".main-image img")).to_be_visible()
        expect(S.locator(".owner-box")).to_be_visible()  # owner sees the management box, not "buy"
        product_id = int(re.search(r"/product/(\d+)", S.url).group(1))
        shot(S, "detail-owner")
        expect(S.locator(".meetup")).to_have_count(0)  # text-only location: no map section

        step("a listing with a map pin shows the meet-up section and a Kakao directions link")
        token = S.evaluate("JSON.parse(localStorage.getItem('specgrid.auth')).access_token")
        res = S.request.patch(
            f"{BASE}/api/v1/products/{product_id}",
            data={"trade_location": "강남역 11번 출구", "trade_point": {"lat": 37.497952, "lng": 127.027619}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.ok, res.text()
        S.reload()
        expect(S.locator(".meetup h2")).to_have_text("거래 장소")
        href = S.locator("[data-directions]").get_attribute("href")
        assert href.startswith("https://map.kakao.com/link/to/") and href.endswith(",37.497952,127.027619"), href
        expect(S.locator("[data-detail-map]")).to_contain_text("지도를 표시할 수 없어요")
        expect(S.locator("[data-place-search]")).to_have_count(0)  # not on this page

        step("sell form validation (description too short) stays on the page")
        S.goto(f"{BASE}/#/sell")
        S.fill('input[name="title"]', "테스트 상품")
        S.fill('input[name="price"]', "1000")
        S.fill('textarea[name="description"]', "짧음")
        S.click('button:has-text("상품 등록하기")')
        expect(S.locator("[data-error]")).to_contain_text("10자 이상")

        step("seller adds a second listing without photo (keyboard)")
        S.fill('input[name="title"]', f"키크론 Q1 기계식 키보드 e2e{stamp}")
        S.select_option('select[name="category"]', "keyboard")
        S.fill('textarea[name="description"]', "저소음 갈축, 키캡 교체했습니다. 상태 좋아요.")
        S.fill('input[name="price"]', "150000")
        S.click('button:has-text("상품 등록하기")')
        expect(S.locator(".detail-title")).to_contain_text("키크론")
        expect(S.locator(".main-image .img-placeholder")).to_be_visible()

        # ---------------------------------------------------------- search & filters (buyer)
        step("buyer searches from the header")
        B.goto(BASE)
        B.fill("#search-input", "  RTX  ")
        B.press("#search-input", "Enter")
        expect(B.locator(".market-heading h2")).to_contain_text("RTX")
        expect(B.locator("#count")).to_have_text("1")
        expect(B.locator(".product-card h3")).to_have_text(title)
        shot(B, "search")

        step("spec filters narrow and widen the results")
        B.goto(BASE)
        expect(B.locator("#count")).to_have_text("2")
        B.click('.category-tabs button:has-text("그래픽카드")')
        expect(B.locator("#count")).to_have_text("1")
        B.select_option('select[name="min_vram_gb"]', "24")
        expect(B.locator(".empty-state")).to_contain_text("조건에 맞는 상품이 아직 없어요")
        expect(B.locator("#chips button")).to_have_count(1)
        B.click("#chips button")  # remove the VRAM chip
        expect(B.locator("#count")).to_have_text("1")
        B.click('label.checkbox:has-text("NVIDIA")')
        expect(B.locator("#count")).to_have_text("1")
        B.click('label.checkbox:has-text("Apple")')
        expect(B.locator("#count")).to_have_text("0")
        B.click(".filter-title [data-reset]")
        expect(B.locator("#count")).to_have_text("2")
        B.select_option('select[name="sort"]', "price_asc")
        expect(B.locator(".product-card h3").first).to_contain_text("키크론")

        # ---------------------------------------------------------- detail, favorite
        step("buyer opens the product (view counted) and hearts it")
        B.goto(f"{BASE}/#/product/{product_id}")
        expect(B.locator(".detail-title")).to_have_text(title)
        expect(B.locator(".info-grid")).to_contain_text("1 ·")  # 1 view
        B.click(".heart-btn")
        expect(B.locator(".heart-btn")).to_have_class(re.compile("saved"))
        expect(B.locator(f'[data-likes="{product_id}"]')).to_contain_text("1")
        B.reload()
        expect(B.locator(".heart-btn")).to_have_class(re.compile("saved"))  # persisted

        step("favorites page lists it; un-hearting removes it")
        B.goto(f"{BASE}/#/favorites")
        expect(B.locator(".product-card")).to_have_count(1)
        B.click(".card-heart")
        expect(B.locator(".empty-state")).to_contain_text("찜한 상품이 없어요")
        B.goto(f"{BASE}/#/product/{product_id}")
        B.click(".heart-btn")
        expect(B.locator(".heart-btn")).to_have_class(re.compile("saved"))

        # ---------------------------------------------------------- realtime chat
        step("seller waits on the chat page (realtime connected)")
        S.goto(f"{BASE}/#/chat")
        expect(S.locator(".room-empty")).to_be_visible()
        expect(S.locator("#live-dot")).not_to_have_class(re.compile("dim"), timeout=15_000)

        step("buyer starts a chat and sends a message")
        B.goto(f"{BASE}/#/product/{product_id}")
        B.click('button:has-text("채팅하기")')
        expect(B.locator(".conv-head")).to_contain_text(title)
        expect(B.locator("#live-dot")).not_to_have_class(re.compile("dim"), timeout=15_000)
        B.fill('textarea[name="content"]', "안녕하세요! 아직 판매 중인가요?")
        B.press('textarea[name="content"]', "Enter")
        expect(B.locator(".message.mine")).to_contain_text("아직 판매 중인가요")

        step("seller's room list updates live (no reload)")
        expect(S.locator(".list-row")).to_have_count(1, timeout=10_000)
        expect(S.locator(".list-row")).to_contain_text("아직 판매 중인가요")
        expect(S.locator(".list-row .unread-dot")).to_have_text("1")
        expect(S.locator("#unread-badge")).to_have_text("1")

        step("seller opens the room and replies; buyer receives it live")
        S.click(".list-row")
        expect(S.locator(".message").first).to_contain_text("아직 판매 중인가요")
        expect(S.locator("#unread-badge")).to_be_hidden()
        S.fill('textarea[name="content"]', "네 판매 중입니다. 강남역 직거래 가능해요.")
        S.click('.composer button[type="submit"]')
        expect(B.locator(".message:not(.mine)")).to_contain_text("강남역 직거래", timeout=10_000)
        expect(B.locator(".message.mine small")).to_contain_text("읽음", timeout=10_000)  # read receipt pushed
        shot(B, "chat-buyer")

        step("multi-line message with Shift+Enter, and HTML is shown as text (no XSS)")
        B.fill('textarea[name="content"]', "<img src=x onerror=alert(1)>")
        B.press('textarea[name="content"]', "Enter")
        expect(S.locator(".message").last).to_contain_text("<img src=x onerror=alert(1)>", timeout=10_000)
        assert S.locator(".message img").count() == 0

        # ---------------------------------------------------------- trade flow
        step("buyer sends a purchase request")
        B.goto(f"{BASE}/#/product/{product_id}")
        B.click('button:has-text("구매 요청하기")')
        B.fill('textarea[name="message"]', "오늘 저녁 7시 가능할까요?")
        B.click('button:has-text("요청 보내기")')
        expect(B.locator("#actions")).to_contain_text("구매 요청 · 거래 내역 보기")

        step("seller gets a realtime trade toast")
        expect(S.locator(".toast").filter(has_text="거래 알림")).to_be_visible(timeout=10_000)

        step("seller accepts on the trades page -> product reserved")
        S.goto(f"{BASE}/#/trades")
        row = S.locator(".trade-row").first
        expect(row).to_contain_text("오늘 저녁 7시")
        row.locator('button:has-text("수락")').click()
        expect(S.locator(".trade-row .badge").first).to_have_text("예약중")
        expect(B.locator(".toast").filter(has_text="예약중")).to_be_visible(timeout=10_000)
        B.goto(f"{BASE}/#/product/{product_id}")
        expect(B.locator(".badges .badge").first).to_have_text("예약중")
        shot(S, "trades-accepted")

        step("reserved product: manual status change is refused with a clear message")
        S.goto(f"{BASE}/#/product/{product_id}")
        S.select_option("[data-status]", "on_sale")
        expect(S.locator(".toast.error")).to_contain_text("예약중인 거래")
        expect(S.locator("[data-status]")).to_have_value("reserved")

        step("seller completes the trade -> product sold")
        S.goto(f"{BASE}/#/trades")
        S.locator('.trade-row button:has-text("거래 완료")').click()
        expect(S.locator(".trade-row .badge").first).to_have_text("거래 완료")
        B.goto(f"{BASE}/#/trades")
        expect(B.locator(".trade-row .badge").first).to_have_text("거래 완료")
        B.goto(f"{BASE}/#/product/{product_id}")
        expect(B.locator(".buy-actions button").first).to_have_text("판매완료")

        # ---------------------------------------------------------- rankings / profile
        step("ranking page shows the searched keyword and the viewed product")
        B.goto(f"{BASE}/#/ranking")
        expect(B.locator("#kw")).to_contain_text("rtx")
        B.locator('[data-group="period"] button:has-text("전체 기간")').click()
        B.locator('[data-group="metric"] button:has-text("찜 많은")').click()
        B.select_option("select[data-category]", "")
        # sold products are hidden from rankings by default -> empty is the right answer here
        expect(B.locator("#products")).to_contain_text("아직 없어요")
        shot(B, "ranking")

        step("seller profile shows stats and listings")
        S.goto(f"{BASE}/#/profile")
        expect(S.locator("#me")).to_contain_text(seller["email"])
        expect(S.locator("#stats")).to_contain_text("2개")
        expect(S.locator(".mine-row")).to_have_count(2)

        step("seller sets a profile photo; header, product page and chat show it; then removes it")
        expect(S.locator("#me .avatar-img.empty")).to_be_visible()
        S.set_input_files("[data-avatar-file]", files=[{"name": "me.png", "mimeType": "image/png", "buffer": png}])
        expect(S.locator("#me .avatar-img img")).to_be_visible(timeout=15_000)
        expect(S.locator(".user-button .avatar-img img")).to_be_visible()
        S.goto(f"{BASE}/#/product/{product_id}")
        expect(S.locator(".info-grid .avatar-img img")).to_be_visible()
        B.goto(f"{BASE}/#/chat")
        expect(B.locator(".list-row .avatar-img img").first).to_be_visible()
        shot(B, "chat-avatar")
        S.goto(f"{BASE}/#/profile")
        S.click("[data-avatar-remove]")
        expect(S.locator("#me .avatar-img.empty")).to_be_visible()
        expect(S.locator(".user-button .avatar-img")).to_have_count(1)
        expect(S.locator(".user-button .avatar-img img")).to_have_count(0)

        step("expired access token is refreshed silently")
        S.evaluate("""() => { const a = JSON.parse(localStorage.getItem('specgrid.auth'));
                              a.access_token = 'expired.garbage.token';
                              localStorage.setItem('specgrid.auth', JSON.stringify(a)); }""")
        S.reload()
        expect(S.locator(".user-button")).to_contain_text(seller["nick"])
        expect(S.locator("#me")).to_contain_text(seller["email"])

        step("logout returns to anonymous state")
        S.click("[data-logout]")
        expect(S.locator(".user-button")).to_contain_text("로그인")
        S.goto(f"{BASE}/#/trades")
        expect(S.locator(".gate")).to_be_visible()

        step("login with next= returns to the page you came from")
        S.goto(f"{BASE}/#/login?next=%2Ftrades")
        S.fill('input[name="email"]', seller["email"])
        S.fill('input[name="password"]', seller["pw"])
        S.click('button:has-text("로그인")')
        expect(S.locator(".trade-list")).to_be_visible()

        step("open-redirect attempt via next= stays on the site")
        S.goto(f"{BASE}/#/login?next=//evil.example")
        expect(S).to_have_url(re.compile(rf"{BASE}/#/$"))

        step("unknown page and missing product show friendly errors")
        S.goto(f"{BASE}/#/nope")
        expect(S.locator(".empty-state h3")).to_have_text("페이지를 찾을 수 없어요.")
        S.goto(f"{BASE}/#/product/999999")
        expect(S.locator(".empty-state h3")).to_have_text("상품을 찾을 수 없어요.")

        # ---------------------------------------------------------- mobile
        step("mobile layout: no horizontal scroll on main pages")
        M = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        watches.append(Watch("mobile", M))
        for path in ("/", f"/#/product/{product_id}", "/#/ranking", "/#/login"):
            M.goto(BASE + path)
            M.wait_for_load_state("networkidle")
            sw = M.evaluate("document.documentElement.scrollWidth")
            assert sw <= 392, f"horizontal overflow on {path}: scrollWidth={sw}"
        M.goto(BASE)
        expect(M.locator(".product-card").first).to_be_visible()
        shot(M, "mobile-home")
        M.click("#menu-toggle")
        expect(M.locator(".nav.open")).to_be_visible()
        M.goto(f"{BASE}/#/product/{product_id}")
        expect(M.locator(".detail-title")).to_be_visible()
        shot(M, "mobile-detail")

        step("mobile chat: list and conversation each take the full screen")
        M.goto(f"{BASE}/#/login?next=%2Fchat")
        M.fill('input[name="email"]', buyer["email"])
        M.fill('input[name="password"]', buyer["pw"])
        M.click('button:has-text("로그인")')
        expect(M.locator(".list-row")).to_have_count(1)
        expect(M.locator(".conversation")).to_be_hidden()
        M.click(".list-row")
        expect(M.locator(".composer")).to_be_visible()
        expect(M.locator(".room-list")).to_be_hidden()
        assert M.evaluate("document.documentElement.scrollWidth") <= 392
        shot(M, "mobile-chat")

        browser.close()

    problems = [f"{w.name}: {e}" for w in watches for e in w.errors]
    if problems:
        print("\nBrowser errors:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--shots", type=Path)
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)

    reset_state()
    media = tempfile.mkdtemp(prefix="specgrid-e2e-")
    server = start_server(media)
    print(f"e2e server on {BASE} (db={E2E_DB}, redis db 14, media={media})")
    ok = False
    try:
        run(args.headed, args.shots)
        ok = True
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if not ok:
            log = Path(media) / "server.log"
            print("\n--- server log (tail) ---")
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))
    print(f"\nE2E PASSED: {STEP} steps")


if __name__ == "__main__":
    main()
