import * as api from "../api.js";
import { icon } from "../icons.js";
import { toast } from "../ui.js";

export function goLogin() {
  const here = location.hash.replace(/^#/, "") || "/";
  location.hash = `/login?next=${encodeURIComponent(here)}`;
}

// Heart buttons anywhere inside `root` ([data-heart="<product id>"]).
// The button state flips immediately and rolls back if the server says no.
export function bindHearts(root, onChange) {
  root.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-heart]");
    if (!btn || !root.contains(btn)) return;
    e.preventDefault();
    e.stopPropagation();
    if (!api.isLoggedIn()) return goLogin();
    if (btn.dataset.pending) return;
    const id = Number(btn.dataset.heart);
    const wasSaved = btn.classList.contains("saved");
    btn.dataset.pending = "1";
    setHeart(root, id, !wasSaved);
    try {
      const r = wasSaved
        ? await api.del(`/products/${id}/favorite`, { auth: "required" })
        : await api.put(`/products/${id}/favorite`, undefined, { auth: "required" });
      setHeart(root, id, r.favorited, r.favorite_count);
      toast(r.favorited ? "찜 목록에 담았어요." : "찜을 해제했어요.", "success", 1800);
      onChange?.(id, r);
    } catch (err) {
      setHeart(root, id, wasSaved);
      toast(err.message, "error");
    } finally {
      delete btn.dataset.pending;
    }
  });
}

function setHeart(root, id, saved, count) {
  root.querySelectorAll(`[data-heart="${id}"]`).forEach((b) => {
    b.classList.toggle("saved", saved);
    b.setAttribute("aria-pressed", String(saved));
    b.setAttribute("aria-label", saved ? "찜 해제" : "찜하기");
    b.querySelector("svg")?.classList.toggle("filled", saved);
  });
  if (count !== undefined) {
    root.querySelectorAll(`[data-likes="${id}"]`).forEach((s) => {
      s.innerHTML = `${icon("heart", 11)} ${count}`;
    });
  }
}

export function section(cls = "page-wrap workspace") {
  const el = document.createElement("section");
  el.className = cls;
  return el;
}

export function workspaceHeader(eyebrow, title, subtitle, activeTab) {
  const tabs = [
    ["sell", "판매 등록", "#/sell"],
    ["trades", "거래 내역", "#/trades"],
    ["chat", "채팅", "#/chat"],
    ["favorites", "찜 목록", "#/favorites"],
    ["profile", "프로필", "#/profile"],
  ];
  return `
    <div class="ws-head">
      <p class="eyebrow">${eyebrow}</p>
      <h1 class="page-title">${title}</h1>
      <p class="muted">${subtitle}</p>
    </div>
    <nav class="tabs" aria-label="마이페이지 메뉴">
      ${tabs.map(([k, label, href]) => `<a href="${href}" class="${k === activeTab ? "active" : ""}" ${k === activeTab ? 'aria-current="page"' : ""}>${label}</a>`).join("")}
    </nav>`;
}
