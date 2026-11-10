import { icon } from "./icons.js";

// ------------------------------------------------------------------ safety
// Every piece of user-generated text goes through esc() before it touches innerHTML.
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

export function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ------------------------------------------------------------------ formatting
export const money = (n) => new Intl.NumberFormat("ko-KR").format(n ?? 0);

export function formatDate(value, withTime = false) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const opts = withTime
    ? { timeZone: "Asia/Seoul", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { timeZone: "Asia/Seoul", year: "numeric", month: "short", day: "numeric" };
  return new Intl.DateTimeFormat("ko-KR", opts).format(d);
}

export function timeAgo(value) {
  const d = new Date(value);
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (Number.isNaN(s)) return "";
  if (s < 60) return "방금 전";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}일 전`;
  return formatDate(value);
}

// ------------------------------------------------------------------ domain labels (match backend enums)
export const CATEGORIES = [
  { id: "gpu", name: "그래픽카드", icon: "circuit" },
  { id: "cpu", name: "CPU", icon: "cpu" },
  { id: "ram", name: "메모리", icon: "memory" },
  { id: "storage", name: "저장장치", icon: "drive" },
  { id: "laptop", name: "노트북", icon: "laptop" },
  { id: "desktop", name: "데스크탑", icon: "desktop" },
  { id: "server", name: "서버 부품", icon: "server" },
  { id: "monitor", name: "모니터", icon: "monitor" },
  { id: "keyboard", name: "키보드", icon: "keyboard" },
  { id: "audio", name: "오디오", icon: "headphones" },
  { id: "etc", name: "기타", icon: "box" },
];
export const categoryName = (id) => CATEGORIES.find((c) => c.id === id)?.name || id;
export const categoryIcon = (id) => CATEGORIES.find((c) => c.id === id)?.icon || "box";

export const CONDITIONS = [
  { id: "sealed", name: "미개봉" },
  { id: "like_new", name: "거의 새것" },
  { id: "lightly_used", name: "사용감 적음" },
  { id: "used", name: "사용감 있음" },
  { id: "for_parts", name: "부품용" },
];
export const conditionName = (id) => CONDITIONS.find((c) => c.id === id)?.name || id;

export const PRODUCT_STATUS = { on_sale: "판매중", reserved: "예약중", sold: "판매완료", hidden: "숨김" };
export const TRADE_STATUS = {
  requested: "구매 요청",
  accepted: "예약중",
  rejected: "거절됨",
  canceled: "취소됨",
  completed: "거래 완료",
};

export function specTags(spec, limit = 3) {
  if (!spec) return [];
  const gb = (n) => (n >= 1024 && n % 1024 === 0 ? `${n / 1024}TB` : `${n}GB`);
  return [
    spec.gpu_model,
    spec.cpu_model,
    spec.vram_gb ? `${spec.vram_gb}GB VRAM` : "",
    spec.ram_gb ? `${spec.ram_gb}GB RAM` : "",
    spec.storage_gb ? `${gb(spec.storage_gb)} ${spec.storage_type || "SSD"}` : "",
    spec.cpu_cores ? `${spec.cpu_cores}코어` : "",
    spec.manufacturer,
  ]
    .filter(Boolean)
    .slice(0, limit);
}

// ------------------------------------------------------------------ images
export function placeholder(category, label = "사진 없음") {
  return `<div class="img-placeholder">${icon(categoryIcon(category), 34)}<span>${esc(label)}</span></div>`;
}

export function productImage(p, cls = "") {
  return p.thumbnail_url
    ? `<img class="${cls}" src="${esc(p.thumbnail_url)}" alt="${esc(p.title)}" loading="lazy">`
    : placeholder(p.category);
}

// ------------------------------------------------------------------ product card (original design)
export function productCard(p) {
  const tags = specTags(p.spec);
  const saved = p.is_favorited === true;
  const overlay =
    p.status === "reserved" ? "예약 진행 중" : p.status === "sold" ? "거래 완료" : p.status === "hidden" ? "숨김" : "";
  return `
  <article class="product-card" data-product="${p.id}">
    <div class="product-image">
      <a href="#/product/${p.id}" aria-label="${esc(p.title)}">${productImage(p)}</a>
      <div class="card-badges">
        ${p.is_hot_deal ? `<span class="hot-badge">${icon("zap", 11)} HOT DEAL</span>` : ""}
        <span class="condition-badge ${p.condition === "sealed" ? "mint" : ""}">${esc(conditionName(p.condition))}</span>
      </div>
      <button class="card-heart ${saved ? "saved" : ""}" data-heart="${p.id}" aria-pressed="${saved}"
        aria-label="${saved ? "찜 해제" : "찜하기"}">${icon("heart", 17, saved ? "filled" : "")}</button>
      ${overlay ? `<span class="reserved-overlay">${overlay}</span>` : ""}
    </div>
    <a href="#/product/${p.id}" class="product-info">
      <span class="card-category">${esc(categoryName(p.category))} <span>#${String(p.id).padStart(4, "0")}</span></span>
      <h3 title="${esc(p.title)}">${esc(p.title)}</h3>
      <div class="spec-tags">${
        tags.length ? tags.map((t) => `<span class="spec-tag">${esc(t)}</span>`).join("") : `<span class="spec-tag">${esc(categoryName(p.category))}</span>`
      }</div>
      <div class="card-price"><strong>${money(p.price)}<small>원</small></strong>
        <span class="card-likes" data-likes="${p.id}">${icon("heart", 11)} ${p.favorite_count ?? 0}</span></div>
      <div class="card-meta">
        <span>${esc(p.trade_location || "지역 미정")} · 조회 ${p.view_count ?? 0}</span>
        <span class="meta-status ${p.status !== "on_sale" ? "off" : ""}"><i></i>${PRODUCT_STATUS[p.status] || p.status}</span>
      </div>
    </a>
  </article>`;
}

// ------------------------------------------------------------------ states
export const loading = (label = "불러오는 중이에요") =>
  `<div class="loading-state" role="status">${icon("loader", 22, "spin")} ${esc(label)}</div>`;

export const emptyState = (title, desc, action = "", ic = "search") =>
  `<div class="empty-state">${icon(ic, 36)}<h3>${esc(title)}</h3><p>${esc(desc)}</p>${action}</div>`;

export const errorState = (err, retryLabel = "다시 시도") =>
  `<div class="empty-state" role="alert">${icon("circuit", 36)}<h3>정보를 불러오지 못했어요.</h3>
   <p>${esc(err?.message || "잠시 후 다시 시도해 주세요.")}</p>
   <button class="btn btn-secondary" data-retry>${icon("rotate", 16)} ${esc(retryLabel)}</button></div>`;

// ------------------------------------------------------------------ toast
let toastBox;
export function toast(message, kind = "info", ms = 3200) {
  if (!toastBox) {
    toastBox = el(`<div class="toasts" aria-live="polite"></div>`);
    document.body.appendChild(toastBox);
  }
  const t = el(`<div class="toast ${kind}">${icon(kind === "error" ? "info" : kind === "success" ? "check" : "info", 16)}<span>${esc(message)}</span></div>`);
  toastBox.appendChild(t);
  requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 300);
  }, ms);
}

// Run an async action while disabling a button. Errors become a toast; the call then
// resolves to false (success resolves to the action's result, or true if it returned nothing).
export async function busy(button, fn, label) {
  const original = button?.innerHTML;
  if (button) {
    if (button.disabled) return false; // already running: ignore double clicks
    button.disabled = true;
    if (label) button.innerHTML = `${icon("loader", 15, "spin")} ${esc(label)}`;
  }
  try {
    return (await fn()) ?? true;
  } catch (err) {
    toast(err.message || "요청에 실패했어요.", "error");
    return false;
  } finally {
    if (button && button.isConnected) {
      button.disabled = false;
      if (label) button.innerHTML = original;
    }
  }
}

export function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
