import * as api from "../api.js";
import * as rt from "../realtime.js";
import { icon } from "../icons.js";
import {
  PRODUCT_STATUS, TRADE_STATUS, busy, emptyState, errorState, esc, formatDate, loading, money, productCard,
  productImage, toast,
} from "../ui.js";
import { markOwnTradeAction, navigate } from "../app.js";
import { bindHearts, section, workspaceHeader } from "./common.js";

// ================================================================== 거래 내역
export function renderTrades({ query }) {
  const el = section();
  let role = ["buyer", "seller"].includes(query.role) ? query.role : "";
  let alive = true;
  el.innerHTML = `
    ${workspaceHeader("YOUR TRANSACTIONS", "거래 내역", "구매 요청과 판매 진행 상황을 한눈에 확인하세요.", "trades")}
    <div class="seg" role="group" aria-label="거래 구분">
      <button data-role="" class="${role === "" ? "active" : ""}">전체</button>
      <button data-role="buyer" class="${role === "buyer" ? "active" : ""}">구매</button>
      <button data-role="seller" class="${role === "seller" ? "active" : ""}">판매</button>
    </div>
    <div id="list">${loading("거래 내역을 불러오는 중이에요")}</div>`;
  const list = el.querySelector("#list");

  async function load() {
    try {
      const data = await api.get("/trades", { role: role || undefined, size: 50 }, { auth: "required" });
      if (!alive) return;
      render(data.items);
    } catch (err) {
      if (alive) list.innerHTML = errorState(err);
    }
  }

  function actions(t, isSeller) {
    const b = [];
    if (isSeller && t.status === "requested") {
      b.push(`<button class="btn" data-act="accept" data-id="${t.id}">수락</button>`);
      b.push(`<button class="btn btn-secondary" data-act="reject" data-id="${t.id}">거절</button>`);
    }
    if (isSeller && t.status === "accepted") {
      b.push(`<button class="btn" data-act="complete" data-id="${t.id}">거래 완료</button>`);
      b.push(`<button class="btn btn-secondary" data-act="cancel" data-id="${t.id}">예약 취소</button>`);
    }
    if (!isSeller && (t.status === "requested" || t.status === "accepted")) {
      b.push(`<button class="btn btn-secondary" data-act="cancel" data-id="${t.id}">요청 취소</button>`);
    }
    return b.join("");
  }

  function render(items) {
    const me = api.currentUser();
    if (!items.length) {
      list.innerHTML = emptyState(
        "아직 거래 내역이 없어요",
        "마음에 드는 상품에서 '구매 요청하기'를 누르면 이곳에서 진행 상황을 확인할 수 있어요.",
        `<a href="#/" class="btn btn-secondary">상품 둘러보기</a>`,
        "repeat",
      );
      return;
    }
    list.innerHTML = `<div class="trade-list">${items
      .map((t) => {
        const isSeller = me && t.seller.id === me.id;
        const other = isSeller ? t.buyer : t.seller;
        return `
        <article class="trade-row" data-trade-row="${t.id}">
          <a href="#/product/${t.product.id}" class="trade-thumb">${productImage(t.product)}</a>
          <div class="trade-main">
            <div class="trade-meta"><span class="badge status-${t.status}">${TRADE_STATUS[t.status]}</span>
              <span class="muted">${isSeller ? "판매" : "구매"} · ${esc(other.nickname)}님 · ${formatDate(t.created_at, true)}</span></div>
            <a href="#/product/${t.product.id}" class="trade-title">${esc(t.product.title)}${t.product.is_deleted ? ' <span class="muted">(삭제된 상품)</span>' : ""}</a>
            <p class="price">${money(t.price)}원</p>
            ${t.message ? `<p class="trade-msg">“${esc(t.message)}”</p>` : ""}
          </div>
          <div class="trade-actions">${actions(t, isSeller)}</div>
        </article>`;
      })
      .join("")}</div>`;
  }

  const LABEL = { accept: "수락했어요. 상품이 예약중으로 바뀌었어요.", reject: "요청을 거절했어요.", complete: "거래를 완료했어요. 상품이 판매완료로 바뀌었어요.", cancel: "거래를 취소했어요." };
  el.addEventListener("click", async (e) => {
    const r = e.target.closest("[data-role]");
    if (r) {
      role = r.dataset.role;
      el.querySelectorAll("[data-role]").forEach((b) => b.classList.toggle("active", b === r));
      list.innerHTML = loading("거래 내역을 불러오는 중이에요");
      return load();
    }
    const b = e.target.closest("[data-act]");
    if (b) {
      const { act, id } = b.dataset;
      if (act === "complete" && !confirm("거래를 완료 처리할까요? 상품이 판매완료로 바뀌고 다른 대기 요청은 자동으로 거절돼요.")) return;
      if (act === "cancel" && !confirm("이 거래를 취소할까요?")) return;
      markOwnTradeAction(Number(id), { accept: "accepted", reject: "rejected", complete: "completed", cancel: "canceled" }[act]);
      const ok = await busy(b, () => api.post(`/trades/${id}/${act}`, undefined, { auth: "required" }), "처리 중");
      if (ok) toast(LABEL[act], "success");
      load(); // refresh either way: on 409 the list shows the real current state
      return;
    }
    if (e.target.closest("[data-retry]")) load();
  });

  const offs = [rt.on("trade", () => load()), rt.on("resync", () => load())];
  load();
  return { el, destroy: () => ((alive = false), offs.forEach((f) => f())) };
}

// ================================================================== 찜 목록
export function renderFavorites() {
  const el = section();
  let page = 1;
  let items = [];
  el.innerHTML = `
    ${workspaceHeader("SAVED ITEMS", "찜 목록", "마음에 담아둔 장비를 다시 만나보세요.", "favorites")}
    <div id="list">${loading("찜 목록을 불러오는 중이에요")}</div>`;
  const list = el.querySelector("#list");

  async function load(append = false) {
    try {
      const data = await api.get("/users/me/favorites", { page, size: 12 }, { auth: "required" });
      items = append ? items.concat(data.items) : data.items;
      if (!items.length) {
        list.innerHTML = emptyState("찜한 상품이 없어요", "마음에 드는 상품에 하트를 눌러 찜 목록에 담아 보세요.", `<a href="#/" class="btn btn-secondary">${icon("heart", 16)} 상품 둘러보기</a>`, "heart");
        return;
      }
      list.innerHTML = `<p class="muted list-count">총 <b class="green">${data.total}</b>개</p>
        <div class="product-grid wide">${items.map(productCard).join("")}</div>
        ${data.has_next ? `<div class="more"><button class="btn btn-secondary" data-more>더 보기</button></div>` : ""}`;
    } catch (err) {
      list.innerHTML = errorState(err);
    }
  }
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-more]")) {
      page += 1;
      load(true);
    }
    if (e.target.closest("[data-retry]")) load();
  });
  // Un-hearting here removes the card.
  bindHearts(el, (id, r) => {
    if (!r.favorited) {
      items = items.filter((p) => p.id !== id);
      el.querySelector(`[data-product="${id}"]`)?.remove();
      if (!items.length) load();
    }
  });
  load();
  return { el };
}

// ================================================================== 프로필
export function renderProfile() {
  const el = section();
  let statusFilter = "";
  el.innerHTML = `
    ${workspaceHeader("MY ACCOUNT", "내 프로필", "계정 정보와 내 판매 상품을 관리하세요.", "profile")}
    <div class="profile-grid">
      <div class="panel" id="me">${loading()}</div>
      <aside class="panel" id="stats">${loading()}</aside>
    </div>
    <section class="panel my-products">
      <div class="panel-head row"><div><p class="eyebrow">MY LISTINGS</p><h2>내 판매 상품</h2></div>
        <select data-filter aria-label="상태 필터"><option value="">전체</option>${Object.entries(PRODUCT_STATUS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
      <div id="mine">${loading()}</div>
    </section>`;

  async function loadMe() {
    try {
      const me = await api.get("/users/me", null, { auth: "required" });
      el.querySelector("#me").innerHTML = `
        <div class="me-head"><div class="avatar">${icon("user", 27)}</div>
          <div><p class="eyebrow">MY ACCOUNT</p><h2>${esc(me.nickname)}</h2><p class="muted">${esc(me.email)}</p></div></div>
        <dl class="kv">
          <div><dt>가입일</dt><dd>${formatDate(me.created_at)}</dd></div>
          <div><dt>최근 로그인</dt><dd>${me.last_login_at ? formatDate(me.last_login_at, true) : "-"}</dd></div>
          <div><dt>회원 등급</dt><dd>${me.role === "admin" ? "관리자" : "일반 회원"}</dd></div>
        </dl>
        <div class="row-actions">
          <button class="btn btn-secondary" data-logout>${icon("logout", 16)} 로그아웃</button>
          <button class="btn btn-secondary" data-logout-all>모든 기기에서 로그아웃</button>
        </div>
        <p class="muted small">공용 기기에서는 사용 후 꼭 로그아웃해 주세요.</p>`;
    } catch (err) {
      el.querySelector("#me").innerHTML = errorState(err);
    }
  }

  async function loadStats() {
    try {
      const [all, buying, selling, favs] = await Promise.all([
        api.get("/users/me/products", { size: 1 }, { auth: "required" }),
        api.get("/trades", { role: "buyer", size: 1 }, { auth: "required" }),
        api.get("/trades", { role: "seller", size: 1 }, { auth: "required" }),
        api.get("/users/me/favorites", { size: 1 }, { auth: "required" }),
      ]);
      el.querySelector("#stats").innerHTML = `
        <p class="eyebrow">YOUR ACTIVITY</p><h2>나의 활동</h2>
        <a class="stat" href="#/profile">${icon("package", 16)} 등록 상품<strong>${all.total}개</strong></a>
        <a class="stat" href="#/trades?role=buyer">${icon("repeat", 16)} 구매 요청<strong>${buying.total}건</strong></a>
        <a class="stat" href="#/trades?role=seller">${icon("repeat", 16)} 받은 요청<strong>${selling.total}건</strong></a>
        <a class="stat" href="#/favorites">${icon("heart", 16)} 찜<strong>${favs.total}개</strong></a>`;
    } catch (err) {
      el.querySelector("#stats").innerHTML = errorState(err);
    }
  }

  async function loadMine() {
    const box = el.querySelector("#mine");
    try {
      const data = await api.get("/users/me/products", { status: statusFilter || undefined, size: 50 }, { auth: "required" });
      if (!data.items.length) {
        box.innerHTML = emptyState("등록한 상품이 없어요", "서랍 속 장비, 누군가에겐 업그레이드예요.", `<a class="btn" href="#/sell">${icon("plus", 16)} 판매 등록하기</a>`, "package");
        return;
      }
      box.innerHTML = `<div class="mine-list">${data.items
        .map((p) => `
          <div class="mine-row">
            <a class="mine-thumb" ${p.status === "hidden" ? "" : `href="#/product/${p.id}"`}>${productImage(p)}</a>
            <div class="mine-main"><a ${p.status === "hidden" ? "" : `href="#/product/${p.id}"`} class="mine-title">${esc(p.title)}</a>
              <p class="muted small">${money(p.price)}원 · 조회 ${p.view_count} · 찜 ${p.favorite_count} · ${formatDate(p.created_at)}</p></div>
            <select data-pstatus="${p.id}" aria-label="판매 상태">${Object.entries(PRODUCT_STATUS).map(([k, v]) => `<option value="${k}" ${k === p.status ? "selected" : ""}>${v}</option>`).join("")}</select>
          </div>`)
        .join("")}</div>`;
    } catch (err) {
      box.innerHTML = errorState(err);
    }
  }

  el.addEventListener("click", async (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.matches("[data-logout]")) {
      await api.logout(false);
      toast("로그아웃했어요.", "success");
      return navigate("/");
    }
    if (t.matches("[data-logout-all]")) {
      if (!confirm("이 기기를 포함해 로그인된 모든 기기에서 로그아웃할까요?")) return;
      await api.logout(true);
      toast("모든 기기에서 로그아웃했어요.", "success");
      return navigate("/");
    }
    if (t.matches("[data-retry]")) {
      loadMe();
      loadStats();
      loadMine();
    }
  });
  el.addEventListener("change", async (e) => {
    if (e.target.matches("[data-filter]")) {
      statusFilter = e.target.value;
      return loadMine();
    }
    if (e.target.matches("[data-pstatus]")) {
      const s = e.target;
      const ok = await busy(s, () => api.patch(`/products/${s.dataset.pstatus}/status`, { status: s.value }, { auth: "required" }));
      if (ok) toast(`상태를 '${PRODUCT_STATUS[s.value]}'(으)로 바꿨어요.`, "success");
      loadMine(); // on 409 (reserved by a trade) this restores the real status
    }
  });

  loadMe();
  loadStats();
  loadMine();
  return { el };
}
