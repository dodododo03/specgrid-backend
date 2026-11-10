// SpecGrid single-page app: hash router (#/product/7), header, realtime notifications.
import * as api from "./api.js";
import * as rt from "./realtime.js";
import { icon } from "./icons.js";
import { esc, toast, TRADE_STATUS } from "./ui.js";
import { renderHome } from "./views/home.js";
import { renderProduct } from "./views/product.js";
import { renderSell } from "./views/sell.js";
import { renderLogin, renderSignup } from "./views/auth.js";
import { renderTrades, renderFavorites, renderProfile } from "./views/account.js";
import { renderChat } from "./views/chat.js";
import { renderRanking } from "./views/ranking.js";

const app = document.getElementById("app");
const header = document.getElementById("header");
document.getElementById("year").textContent = new Date().getFullYear();

let current = null; // {destroy}
let unread = 0;
let menuOpen = false;
// "<trade id>:<status>" this tab just caused itself — don't toast our own action back at us,
// but still show the other side's next move on the same trade (e.g. accept right after request).
const ownTradeActions = new Set();
export function markOwnTradeAction(id, status) {
  const key = `${id}:${status}`;
  ownTradeActions.add(key);
  setTimeout(() => ownTradeActions.delete(key), 10000);
}

// ------------------------------------------------------------------ routing
export function navigate(path) {
  if (location.hash === `#${path}`) route();
  else location.hash = path;
}

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs = ""] = raw.split("?");
  return { path: path || "/", query: Object.fromEntries(new URLSearchParams(qs)) };
}

const MEMBER_ONLY = new Set(["sell", "trades", "favorites", "profile", "chat"]);

const ROUTES = [
  [/^\/$/, (m, ctx) => renderHome(ctx)],
  [/^\/ranking$/, (m, ctx) => renderRanking(ctx)],
  [/^\/product\/(\d+)$/, (m, ctx) => renderProduct({ ...ctx, id: Number(m[1]) })],
  [/^\/sell$/, (m, ctx) => renderSell(ctx), "sell"],
  [/^\/trades$/, (m, ctx) => renderTrades(ctx), "trades"],
  [/^\/favorites$/, (m, ctx) => renderFavorites(ctx), "favorites"],
  [/^\/profile$/, (m, ctx) => renderProfile(ctx), "profile"],
  [/^\/chat(?:\/(\d+))?$/, (m, ctx) => renderChat({ ...ctx, roomId: m[1] ? Number(m[1]) : null }), "chat"],
  [/^\/login$/, (m, ctx) => renderLogin(ctx)],
  [/^\/signup$/, (m, ctx) => renderSignup(ctx)],
];

function loginGate(path) {
  const next = encodeURIComponent(path);
  const el = document.createElement("section");
  el.className = "page-wrap workspace";
  el.innerHTML = `
    <div class="panel gate">
      <div class="gate-icon">${icon("lock", 24)}</div>
      <p class="eyebrow">MEMBER SPACE</p>
      <h2>로그인하고 시작하세요</h2>
      <p class="muted">판매 등록부터 채팅과 거래 관리까지,<br>로그인 후 이용할 수 있어요.</p>
      <div class="gate-actions">
        <a class="btn" href="#/login?next=${next}">로그인하기 ${icon("arrowRight", 16)}</a>
        <a class="btn btn-secondary" href="#/signup?next=${next}">회원가입</a>
      </div>
    </div>`;
  return { el };
}

function notFound() {
  const el = document.createElement("section");
  el.className = "page-wrap workspace";
  el.innerHTML = `<div class="empty-state">${icon("circuit", 36)}<h3>페이지를 찾을 수 없어요.</h3>
    <p>주소를 다시 확인해 주세요.</p><a class="btn btn-secondary" href="#/">홈으로</a></div>`;
  return { el };
}

async function route() {
  const { path, query } = parseHash();
  try {
    current?.destroy?.();
  } catch (e) {
    console.error(e);
  }
  current = null;
  menuOpen = false;
  renderHeader(path);

  let view = null;
  for (const [re, make, member] of ROUTES) {
    const m = path.match(re);
    if (!m) continue;
    if (member && !api.isLoggedIn()) view = loginGate(path + (Object.keys(query).length ? `?${new URLSearchParams(query)}` : ""));
    else view = make(m, { query, path, navigate });
    break;
  }
  view ||= notFound();
  current = view;
  app.replaceChildren(view.el);
  if (!query.keep) window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ header
function renderHeader(path = parseHash().path) {
  const me = api.currentUser();
  const loggedIn = api.isLoggedIn();
  const q = parseHash().query.q || "";
  const active = (p) => (p === "/" ? path === "/" : path.startsWith(p)) ? "active" : "";
  header.innerHTML = `
    <div class="header-main page-wrap">
      <a href="#/" class="brand" aria-label="SpecGrid 홈">
        <span class="brand-mark"><i></i><i></i><i></i><i></i></span>
        <span>spec<span class="green">grid</span><small>TECH FINDS ITS NEXT.</small></span>
      </a>
      <form class="header-search" id="search-form" role="search">
        ${icon("search", 19)}
        <input id="search-input" name="q" value="${esc(q)}" placeholder="어떤 스펙을 찾고 있나요?" aria-label="상품 검색" autocomplete="off" maxlength="100">
        <kbd>↵</kbd>
      </form>
      <div class="header-actions">
        <a href="#/favorites" class="icon-button" aria-label="찜 목록" title="찜 목록">${icon("heart", 21)}</a>
        <a href="#/chat" class="icon-button chat-link" aria-label="채팅" title="채팅">${icon("chat", 20)}
          <span class="unread-badge" id="unread-badge" ${unread ? "" : "hidden"}>${unread > 99 ? "99+" : unread}</span></a>
        ${
          loggedIn
            ? `<a href="#/profile" class="user-button" title="내 프로필">${icon("user", 19)}<span>${esc(me?.nickname || "내 프로필")}</span></a>`
            : `<a href="#/login" class="user-button">${icon("user", 19)}<span>로그인</span></a>`
        }
        <a href="#/sell" class="btn sell-button">${icon("plus", 17)} 판매하기</a>
      </div>
      <button class="icon-button mobile-menu" id="menu-toggle" aria-label="메뉴" aria-expanded="${menuOpen}">${icon(menuOpen ? "x" : "menu", 22)}</button>
    </div>
    <nav class="nav page-wrap ${menuOpen ? "open" : ""}" aria-label="주요 메뉴">
      <div class="nav-links">
        <a href="#/" class="${active("/")}">전체 매물</a>
        <a href="#/ranking" class="${active("/ranking")}">인기 랭킹 <span class="tiny-label">LIVE</span></a>
        <a href="#/chat" class="${active("/chat")}">채팅</a>
        <a href="#/trades" class="${active("/trades")}">내 거래</a>
        <a href="#/favorites" class="${active("/favorites")} mobile-only">찜 목록</a>
        <a href="${loggedIn ? "#/profile" : "#/login"}" class="${active("/profile") || active("/login")} mobile-only">${loggedIn ? "내 프로필" : "로그인"}</a>
      </div>
      <span class="nav-note"><span class="live-dot ${rt.connectionStatus() === "live" ? "" : "dim"}" id="live-dot"></span> 스펙으로 찾고, 합리적으로 거래하세요.</span>
    </nav>`;
  header.querySelector("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const value = header.querySelector("#search-input").value.trim();
    navigate(value ? `/?q=${encodeURIComponent(value)}` : "/");
  });
  header.querySelector("#menu-toggle").addEventListener("click", () => {
    menuOpen = !menuOpen;
    renderHeader(path);
  });
}

function setUnread(n) {
  unread = Math.max(0, n);
  const badge = document.getElementById("unread-badge");
  if (!badge) return;
  badge.hidden = !unread;
  badge.textContent = unread > 99 ? "99+" : String(unread);
}
export async function refreshUnread() {
  if (!api.isLoggedIn()) return setUnread(0);
  try {
    const r = await api.get("/chat/unread-count", null, { auth: "required" });
    setUnread(r.unread_count);
  } catch {
    /* badge is cosmetic */
  }
}

// ------------------------------------------------------------------ realtime notifications
rt.on("status", (s) => document.getElementById("live-dot")?.classList.toggle("dim", s !== "live"));
rt.on("message", (e) => {
  const me = api.currentUser();
  if (!me || e.message.sender_id === me.id) return;
  const inRoom = parseHash().path === `/chat/${e.room_id}` && document.visibilityState === "visible";
  if (!inRoom) {
    setUnread(unread + 1);
    toast(`새 메시지: ${e.message.content.slice(0, 40)}`, "info");
  }
});
rt.on("read", () => refreshUnread());
rt.on("resync", () => refreshUnread());
rt.on("trade", (e) => {
  const t = e.trade;
  const me = api.currentUser();
  if (!me || ownTradeActions.has(`${t.id}:${t.status}`)) return;
  const who = t.buyer.id === me.id ? t.seller.nickname : t.buyer.nickname;
  const label = TRADE_STATUS[t.status] || t.status;
  toast(`거래 알림 · ${who}: ${t.product.title.slice(0, 24)} → ${label}`, "success", 4500);
});

// ------------------------------------------------------------------ session lifecycle
api.onAuthChange((me) => {
  if (me) {
    rt.start();
    refreshUnread();
  } else {
    rt.stop();
    setUnread(0);
  }
  renderHeader();
});

// Escape closes the mobile menu.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && menuOpen) {
    menuOpen = false;
    renderHeader();
  }
});

(async function init() {
  renderHeader();
  try {
    await api.loadMe();
  } catch {
    /* offline: views will show their own errors */
  }
  route();
})();
