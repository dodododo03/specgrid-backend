import * as api from "../api.js";
import { icon } from "../icons.js";
import {
  CATEGORIES, CONDITIONS, debounce, emptyState, errorState, esc, loading, money, productCard, productImage,
} from "../ui.js";
import { bindHearts } from "./common.js";

const PAGE_SIZE = 12;
const MANUFACTURERS = ["Apple", "NVIDIA", "AMD", "Intel", "Samsung", "MSI", "ASUS", "Lenovo", "Dell", "Keychron", "Sony", "Corsair"];
const CPUS = [["M3", "Apple M3"], ["M2", "Apple M2"], ["Intel", "Intel"], ["i7", "Intel Core i7"], ["i9", "Intel Core i9"], ["Ryzen", "AMD Ryzen"]];
const GPUS = ["RTX 4090", "RTX 4080", "RTX 4070", "RTX 3080", "RX 7900"];

const HERO_ART = `
<svg class="hero-art" viewBox="0 0 600 340" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs>
    <pattern id="g" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#244232" stroke-width="1"/></pattern>
    <radialGradient id="glow" cx="62%" cy="48%" r="45%"><stop offset="0" stop-color="#39ff88" stop-opacity=".28"/><stop offset="1" stop-color="#39ff88" stop-opacity="0"/></radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="6"/></filter>
  </defs>
  <rect width="600" height="340" fill="#132018"/><rect width="600" height="340" fill="url(#g)"/><rect width="600" height="340" fill="url(#glow)"/>
  <g stroke="#39ff88" stroke-width="2" fill="none" opacity=".55" class="traces">
    <path d="M40 60h120l30 30h90"/><path d="M60 280h140l40-40h60"/><path d="M560 70h-90l-30 30h-60"/>
    <path d="M580 270h-110l-30-30h-50"/><path d="M300 20v60"/><path d="M330 320v-60"/>
  </g>
  <g fill="#39ff88"><circle cx="40" cy="60" r="4"/><circle cx="60" cy="280" r="4"/><circle cx="560" cy="70" r="4"/><circle cx="580" cy="270" r="4"/><circle cx="300" cy="20" r="4"/><circle cx="330" cy="320" r="4"/></g>
  <g transform="translate(372 170) skewY(-8)">
    <g filter="url(#blur)" opacity=".6" fill="#39ff88"><rect x="-82" y="-82" width="74" height="74"/><rect x="8" y="8" width="74" height="74"/></g>
    <rect x="-82" y="-82" width="74" height="74" fill="#39ff88"/>
    <rect x="8" y="-82" width="74" height="74" fill="#39ff88" opacity=".55"/>
    <rect x="-82" y="8" width="74" height="74" fill="#39ff88" opacity=".35"/>
    <rect x="8" y="8" width="74" height="74" fill="#39ff88"/>
  </g>
</svg>`;

export function renderHome({ query }) {
  const q = (query.q || "").trim();
  const el = document.createElement("div");
  el.className = "page-wrap home";

  const state = {
    category: query.category || "",
    manufacturer: "",
    cpu: "",
    min_cores: "",
    min_ram_gb: "",
    gpu: "",
    min_vram_gb: "",
    min_storage_gb: "",
    max_price: 0,
    condition: [],
    include_sold: false,
    sort: query.sort || "latest",
  };
  let page = 1;
  let items = [];
  let total = 0;
  let seq = 0; // drop responses of superseded requests
  let alive = true;

  el.innerHTML = `
    ${q ? "" : `
    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow"><span class="live-dot"></span> THE NEXT UPGRADE STARTS HERE</div>
        <h1>좋은 장비는,<br><span class="green">다음 주인을 만납니다.</span></h1>
        <p>당신이 찾던 그 스펙, 더 합리적인 가격으로.<br>IT를 아는 사람들의 중고거래, 스펙그리드.</p>
        <button class="btn" data-scroll-market>내 다음 스펙 찾기 ${icon("arrowUpRight", 18)}</button>
        <div class="hero-pager"><span class="green">01</span><span>/ 01</span><i></i></div>
      </div>
      <div class="hero-visual">${HERO_ART}
        <span class="visual-label"><span class="live-dot"></span> HARDWARE. RECONNECTED.</span>
        <span class="visual-cross">+</span>
      </div>
    </section>`}
    <div class="value-strip">
      <span>${icon("sliders", 16)}<b>스펙으로 정확하게</b><small>CPU부터 VRAM까지 정밀 필터</small></span>
      <span>${icon("zap", 16)}<b>기회는 선착순으로</b><small>동시 요청에도 예약은 한 명만</small></span>
      <span>${icon("rotate", 16)}<b>장비의 다음 라이프</b><small>필요한 사람에게, 더 오래</small></span>
    </div>
    ${q ? "" : `<section class="rank-strip" id="rank-strip">${loading("인기 랭킹을 불러오는 중이에요")}</section>`}
    <section class="market-section" id="market">
      <div class="market-heading">
        <div>
          <span class="eyebrow">CURATED FOR YOUR NEXT BUILD</span>
          <h2>${q ? `“${esc(q)}” 검색 결과` : "지금, 당신의 다음 스펙"}</h2>
        </div>
        <span class="heading-note">${q ? `<a href="#/" class="link">검색 지우기 ✕</a>` : "아는 만큼, 좋은 거래."}</span>
      </div>
      <div class="category-tabs" role="group" aria-label="상품 카테고리">
        <button data-cat="" class="${state.category ? "" : "active"}">${icon("layers", 19)}<span>전체</span></button>
        ${CATEGORIES.map((c) => `<button data-cat="${c.id}" class="${state.category === c.id ? "active" : ""}">${icon(c.icon, 19)}<span>${c.name}</span></button>`).join("")}
      </div>
      <div class="market-layout">
        <aside class="filters" id="filters">
          <div class="filter-title"><h3>${icon("sliders", 16)} 스펙 필터</h3>
            <button type="button" data-reset aria-label="필터 초기화">${icon("rotate", 14)} 초기화</button></div>
          <div class="filter-caption">감이 아니라, 스펙으로 고르세요.</div>
          <div class="filter-group"><h4>제조사</h4>
            ${MANUFACTURERS.map((b) => `<label class="checkbox"><input type="checkbox" name="manufacturer" value="${b}"><span>${b}</span></label>`).join("")}
          </div>
          <div class="filter-group"><h4>프로세서 <span>CPU</span></h4>
            <select class="filter-select" name="cpu"><option value="">전체 CPU</option>${CPUS.map(([v, n]) => `<option value="${v}">${n}</option>`).join("")}</select>
            <select class="filter-select" name="min_cores"><option value="">코어 수 전체</option>${[4, 6, 8, 12, 16, 24].map((n) => `<option value="${n}">${n}코어 이상</option>`).join("")}</select>
          </div>
          <div class="filter-group"><h4>메모리 <span>RAM</span></h4>
            <div class="filter-pills" data-pills="min_ram_gb">${[0, 8, 16, 32, 64].map((n) => `<button type="button" data-value="${n || ""}" class="${n ? "" : "active"}">${n ? `${n}GB+` : "전체"}</button>`).join("")}</div>
          </div>
          <div class="filter-group"><h4>그래픽 <span>GPU</span></h4>
            <select class="filter-select" name="gpu"><option value="">전체 GPU</option>${GPUS.map((g) => `<option>${g}</option>`).join("")}</select>
            <select class="filter-select" name="min_vram_gb"><option value="">VRAM 용량 전체</option>${[8, 12, 16, 24].map((n) => `<option value="${n}">${n}GB 이상</option>`).join("")}</select>
          </div>
          <div class="filter-group"><h4>저장장치 <span>SSD</span></h4>
            <select class="filter-select" name="min_storage_gb"><option value="">용량 전체</option>${[256, 512, 1024, 2048].map((n) => `<option value="${n}">${n >= 1024 ? `${n / 1024}TB` : `${n}GB`} 이상</option>`).join("")}</select>
          </div>
          <div class="filter-group"><h4>가격 범위</h4>
            <input type="range" name="max_price" min="0" max="5000000" step="100000" value="0" aria-label="최대 가격">
            <div class="price-range"><span>0원</span><span data-price-label>제한 없음</span></div>
          </div>
          <div class="filter-group"><h4>상품 상태</h4>
            ${CONDITIONS.map((c) => `<label class="checkbox"><input type="checkbox" name="condition" value="${c.id}"><span>${c.name}</span></label>`).join("")}
          </div>
          <div class="filter-group"><label class="checkbox"><input type="checkbox" name="include_sold"><span>예약중·판매완료 포함</span></label></div>
          <div class="filter-tip">${icon("cpu", 20)}<span>내 빌드에 딱 맞는 부품.<br><b>사양을 확인하고 거래하세요.</b></span></div>
        </aside>
        <div class="results">
          <div class="results-toolbar">
            <div><span class="result-count">전체 <b class="green" id="count">—</b>개</span></div>
            <div class="toolbar-right">
              <button class="filter-mobile-btn" type="button" data-toggle-filters>${icon("sliders", 15)} 필터</button>
              <select name="sort" aria-label="상품 정렬">
                <option value="latest">최신 등록순</option><option value="price_asc">가격 낮은순</option>
                <option value="price_desc">가격 높은순</option><option value="popular">조회 많은순</option>
              </select>${icon("chevronDown", 13)}
            </div>
          </div>
          <div class="selected-filters" id="chips"></div>
          <div id="results">${loading("매물을 불러오고 있어요")}</div>
        </div>
      </div>
    </section>
    <section class="seller-banner">
      <div><span class="eyebrow">PASS IT ON. POWER SOMEONE UP.</span>
        <h2>서랍 속 장비, 누군가에겐 업그레이드.</h2>
        <p>스펙을 입력하고, 당신의 장비에 새로운 쓰임을 찾아주세요.</p></div>
      <a href="#/sell" class="btn btn-secondary">내 장비 판매하기 ${icon("arrowRight", 17)}</a>
      <span class="seller-circuit">${icon("circuit", 120)}</span>
    </section>`;

  const $ = (s) => el.querySelector(s);
  $('[name="sort"]').value = state.sort;

  // ---------------------------------------------------------------- data
  function params() {
    return {
      q: q || undefined,
      category: state.category || undefined,
      manufacturer: state.manufacturer || undefined,
      cpu: state.cpu || undefined,
      gpu: state.gpu || undefined,
      min_cores: state.min_cores || undefined,
      min_ram_gb: state.min_ram_gb || undefined,
      min_vram_gb: state.min_vram_gb || undefined,
      min_storage_gb: state.min_storage_gb || undefined,
      max_price: state.max_price || undefined,
      condition: state.condition.length ? state.condition : undefined,
      include_sold: state.include_sold || undefined,
      sort: state.sort,
      page,
      size: PAGE_SIZE,
    };
  }

  async function load(append = false) {
    const my = ++seq;
    const box = $("#results");
    if (!append) {
      page = 1;
      box.innerHTML = loading("매물을 불러오고 있어요");
    }
    try {
      const data = await api.get("/products", params());
      if (my !== seq || !alive) return;
      total = data.total;
      items = append ? items.concat(data.items) : data.items;
      $("#count").textContent = total;
      renderResults(data.has_next);
    } catch (err) {
      if (my !== seq || !alive) return;
      box.innerHTML = errorState(err);
    }
  }

  function renderResults(hasNext) {
    const box = $("#results");
    if (!items.length) {
      box.innerHTML = emptyState(
        "조건에 맞는 상품이 아직 없어요.",
        "예산이나 스펙 조건을 조금 넓혀 보세요.",
        `<button class="btn btn-secondary" data-reset>필터 초기화</button>`,
      );
      return;
    }
    box.innerHTML = `
      <div class="product-grid">${items.map(productCard).join("")}</div>
      ${hasNext ? `<div class="more"><button class="btn btn-secondary" data-more>매물 더 보기 (${items.length} / ${total})</button></div>` : ""}
      <div class="results-end"><span></span><p>${hasNext ? "아래로 더 많은 매물이 있어요." : "모든 매물을 확인했어요. 당신의 다음 업그레이드를 찾아보세요."}</p><span></span></div>`;
  }

  function renderChips() {
    const chips = [];
    if (state.manufacturer) chips.push([state.manufacturer, () => (state.manufacturer = "")]);
    if (state.cpu) chips.push([`CPU ${state.cpu}`, () => (state.cpu = "")]);
    if (state.min_cores) chips.push([`${state.min_cores}코어 이상`, () => (state.min_cores = "")]);
    if (state.min_ram_gb) chips.push([`RAM ${state.min_ram_gb}GB 이상`, () => (state.min_ram_gb = "")]);
    if (state.gpu) chips.push([state.gpu, () => (state.gpu = "")]);
    if (state.min_vram_gb) chips.push([`VRAM ${state.min_vram_gb}GB 이상`, () => (state.min_vram_gb = "")]);
    if (state.min_storage_gb) chips.push([`저장공간 ${state.min_storage_gb}GB 이상`, () => (state.min_storage_gb = "")]);
    if (state.max_price) chips.push([`${money(state.max_price)}원 이하`, () => (state.max_price = 0)]);
    state.condition.forEach((c) => chips.push([CONDITIONS.find((x) => x.id === c)?.name, () => (state.condition = state.condition.filter((x) => x !== c))]));
    if (state.include_sold) chips.push(["예약중·판매완료 포함", () => (state.include_sold = false)]);
    const box = $("#chips");
    box.innerHTML = chips.map(([label], i) => `<button type="button" data-chip="${i}">${esc(label)} ${icon("x", 12)}</button>`).join("");
    box.onclick = (e) => {
      const b = e.target.closest("[data-chip]");
      if (!b) return;
      chips[Number(b.dataset.chip)][1]();
      syncControls();
      changed();
    };
  }

  // Reflect `state` back into the filter controls (after reset / chip removal).
  function syncControls() {
    el.querySelectorAll('input[name="manufacturer"]').forEach((i) => (i.checked = i.value === state.manufacturer));
    el.querySelectorAll('input[name="condition"]').forEach((i) => (i.checked = state.condition.includes(i.value)));
    for (const name of ["cpu", "min_cores", "gpu", "min_vram_gb", "min_storage_gb"]) $(`[name="${name}"]`).value = state[name];
    $('[name="max_price"]').value = state.max_price;
    $("[data-price-label]").textContent = state.max_price ? `${money(state.max_price)}원` : "제한 없음";
    $('[name="include_sold"]').checked = state.include_sold;
    el.querySelectorAll('[data-pills="min_ram_gb"] button').forEach((b) => b.classList.toggle("active", b.dataset.value === String(state.min_ram_gb || "")));
    el.querySelectorAll("[data-cat]").forEach((b) => b.classList.toggle("active", b.dataset.cat === state.category));
  }

  const reloadSoon = debounce(() => load(), 250);
  function changed(immediate = true) {
    renderChips();
    immediate ? load() : reloadSoon();
  }

  function reset() {
    Object.assign(state, {
      category: "", manufacturer: "", cpu: "", min_cores: "", min_ram_gb: "", gpu: "", min_vram_gb: "",
      min_storage_gb: "", max_price: 0, condition: [], include_sold: false,
    });
    syncControls();
    changed();
  }

  // ---------------------------------------------------------------- events
  el.addEventListener("click", (e) => {
    const t = e.target.closest("button, a");
    if (!t) return;
    if (t.matches("[data-cat]")) {
      state.category = t.dataset.cat;
      syncControls();
      return changed();
    }
    if (t.matches("[data-pills] button")) {
      state.min_ram_gb = t.dataset.value;
      syncControls();
      return changed();
    }
    if (t.matches("[data-reset]")) return reset();
    if (t.matches("[data-more]")) {
      t.disabled = true;
      page += 1;
      return load(true);
    }
    if (t.matches("[data-retry]")) return load();
    if (t.matches("[data-toggle-filters]")) return $("#filters").classList.toggle("shown");
    if (t.matches("[data-scroll-market]")) return $("#market").scrollIntoView({ behavior: "smooth" });
  });

  el.addEventListener("change", (e) => {
    const t = e.target;
    if (t.name === "manufacturer") {
      state.manufacturer = t.checked ? t.value : "";
      syncControls(); // single choice, like the original design
    } else if (t.name === "condition") {
      state.condition = [...el.querySelectorAll('input[name="condition"]:checked')].map((i) => i.value);
    } else if (t.name === "include_sold") state.include_sold = t.checked;
    else if (t.name === "sort") state.sort = t.value;
    else if (t.name === "max_price") state.max_price = Number(t.value);
    else if (t.name in state) state[t.name] = t.value;
    else return;
    changed();
  });
  el.addEventListener("input", (e) => {
    if (e.target.name !== "max_price") return;
    state.max_price = Number(e.target.value);
    $("[data-price-label]").textContent = state.max_price ? `${money(state.max_price)}원` : "제한 없음";
    changed(false);
  });

  bindHearts(el);

  // ---------------------------------------------------------------- rankings strip
  async function loadRankings() {
    const box = $("#rank-strip");
    if (!box) return;
    try {
      let kw = await api.get("/rankings/keywords", { period: "day", limit: 10 });
      let kwLabel = "24시간";
      if (!kw.items.length) {
        kw = await api.get("/rankings/keywords", { period: "week", limit: 10 });
        kwLabel = "7일";
      }
      const top = await api.get("/rankings/products", { metric: "views", period: "week", limit: 5 });
      if (!alive) return;
      box.innerHTML = `
        <div class="rank-panel">
          <div class="rank-head"><h3>${icon("trending", 16)} 실시간 인기 검색어</h3><span class="eyebrow">${kwLabel} 기준</span></div>
          ${kw.items.length
            ? `<ol class="kw-list">${kw.items.map((k) => `<li><a href="#/?q=${encodeURIComponent(k.keyword)}"><b>${k.rank}</b><span>${esc(k.keyword)}</span><small>${k.count}</small></a></li>`).join("")}</ol>`
            : `<p class="muted rank-empty">아직 검색 기록이 없어요. 첫 검색어의 주인공이 되어 보세요.</p>`}
        </div>
        <div class="rank-panel">
          <div class="rank-head"><h3>${icon("eye", 16)} 이번 주 많이 본 매물</h3><a class="eyebrow link" href="#/ranking">전체 랭킹 →</a></div>
          ${top.items.length
            ? `<ol class="top-list">${top.items.map((r) => `<li><a href="#/product/${r.product.id}">
                <b>${r.rank}</b><span class="thumb">${productImage(r.product)}</span>
                <span class="t"><span>${esc(r.product.title)}</span><small>${money(r.product.price)}원</small></span>
                <em>${icon("eye", 12)} ${r.count}</em></a></li>`).join("")}</ol>`
            : `<p class="muted rank-empty">이번 주 조회 기록이 아직 없어요.</p>`}
        </div>`;
    } catch {
      box.remove(); // rankings are a bonus; the market still works without them
    }
  }

  renderChips();
  load();
  loadRankings();

  return {
    el,
    destroy() {
      alive = false;
    },
  };
}
