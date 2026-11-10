import * as api from "../api.js";
import { icon } from "../icons.js";
import { CATEGORIES, errorState, esc, formatDate, loading, money, productImage, specTags } from "../ui.js";
import { section } from "./common.js";

const PERIODS = [["day", "24시간"], ["week", "7일"], ["month", "30일"], ["all", "전체 기간"]];

export function renderRanking() {
  const el = section();
  const state = { kwPeriod: "day", metric: "views", period: "week", category: "" };
  let alive = true;

  el.innerHTML = `
    <div class="ws-head"><p class="eyebrow"><span class="live-dot"></span> LIVE RANKING</p>
      <h1 class="page-title">인기 랭킹</h1>
      <p class="muted">지금 사람들이 가장 많이 찾고, 보고, 찜한 장비. 같은 사람의 반복 조회·검색은 한 번만 세요.</p></div>
    <div class="ranking-grid">
      <section class="panel">
        <div class="panel-head row"><h2>${icon("trending", 18)} 인기 검색어</h2>
          <div class="seg small" data-group="kwPeriod">${PERIODS.slice(0, 3).map(([v, n]) => `<button data-v="${v}" class="${v === state.kwPeriod ? "active" : ""}">${n}</button>`).join("")}</div></div>
        <div id="kw">${loading()}</div>
      </section>
      <section class="panel">
        <div class="panel-head row wrap"><h2>${icon("eye", 18)} 인기 상품</h2>
          <div class="seg small" data-group="metric"><button data-v="views" class="active">많이 본</button><button data-v="favorites">찜 많은</button></div></div>
        <div class="rank-filters">
          <div class="seg small" data-group="period">${PERIODS.map(([v, n]) => `<button data-v="${v}" class="${v === state.period ? "active" : ""}">${n}</button>`).join("")}</div>
          <select data-category aria-label="카테고리"><option value="">전체 카테고리</option>${CATEGORIES.map((c) => `<option value="${c.id}">${c.name}</option>`).join("")}</select>
        </div>
        <div id="products">${loading()}</div>
      </section>
    </div>`;

  async function loadKeywords() {
    const box = el.querySelector("#kw");
    box.innerHTML = loading();
    try {
      const r = await api.get("/rankings/keywords", { period: state.kwPeriod, limit: 20 });
      if (!alive) return;
      box.innerHTML = r.items.length
        ? `<ol class="kw-list big">${r.items.map((k) => `<li><a href="#/?q=${encodeURIComponent(k.keyword)}"><b>${k.rank}</b><span>${esc(k.keyword)}</span><small>${k.count}회</small></a></li>`).join("")}</ol>
           <p class="muted small">집계 ${formatDate(r.generated_at, true)} · 최대 1분 캐시</p>`
        : `<p class="muted rank-empty">이 기간에는 검색 기록이 없어요.</p>`;
    } catch (err) {
      box.innerHTML = errorState(err);
    }
  }

  async function loadProducts() {
    const box = el.querySelector("#products");
    box.innerHTML = loading();
    try {
      const r = await api.get("/rankings/products", {
        metric: state.metric, period: state.period, category: state.category || undefined, limit: 20,
      });
      if (!alive) return;
      const unit = state.metric === "views" ? "조회" : "찜";
      box.innerHTML = r.items.length
        ? `<ol class="rank-products">${r.items.map((it) => `
            <li><a href="#/product/${it.product.id}">
              <b class="rank-no ${it.rank <= 3 ? "top" : ""}">${it.rank}</b>
              <span class="thumb">${productImage(it.product)}</span>
              <span class="t"><span>${esc(it.product.title)}</span>
                <small>${specTags(it.product.spec, 2).map(esc).join(" · ") || "&nbsp;"}</small></span>
              <span class="r"><strong>${money(it.product.price)}원</strong><em>${unit} ${it.count}</em></span>
            </a></li>`).join("")}</ol>`
        : `<p class="muted rank-empty">조건에 맞는 인기 상품이 아직 없어요.</p>`;
    } catch (err) {
      box.innerHTML = errorState(err);
    }
  }

  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-group] button");
    if (b) {
      const group = b.parentElement.dataset.group;
      state[group] = b.dataset.v;
      b.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      return group === "kwPeriod" ? loadKeywords() : loadProducts();
    }
    if (e.target.closest("[data-retry]")) {
      loadKeywords();
      loadProducts();
    }
  });
  el.addEventListener("change", (e) => {
    if (!e.target.matches("[data-category]")) return;
    state.category = e.target.value;
    loadProducts();
  });

  loadKeywords();
  loadProducts();
  return { el, destroy: () => (alive = false) };
}
