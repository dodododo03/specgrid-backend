import * as api from "../api.js";
import * as rt from "../realtime.js";
import { icon } from "../icons.js";
import {
  PRODUCT_STATUS, TRADE_STATUS, busy, categoryName, conditionName, errorState, esc, formatDate, loading, money,
  placeholder, specTags, toast,
} from "../ui.js";
import { markOwnTradeAction, navigate } from "../app.js";
import { bindHearts, goLogin } from "./common.js";
import { directionsUrl, drawMap, loadKakaoMaps, placeUrl } from "../kakao.js";

export function renderProduct({ id }) {
  const el = document.createElement("section");
  el.className = "page-wrap detail";
  el.innerHTML = loading("상품 정보를 불러오는 중이에요");
  let product = null;
  let myTrade = null; // my open (requested/accepted) trade on this product, if any
  let imageIndex = 0;
  let alive = true;

  async function load() {
    el.innerHTML = loading("상품 정보를 불러오는 중이에요");
    try {
      product = await api.get(`/products/${id}`);
      myTrade = null;
      const me = api.currentUser();
      if (me && me.id !== product.seller.id) {
        const r = await api.get("/trades", { role: "buyer", product_id: id, size: 5 }, { auth: "required" });
        myTrade = r.items.find((t) => t.status === "requested" || t.status === "accepted") || null;
      }
      if (alive) render();
    } catch (err) {
      if (!alive) return;
      el.innerHTML =
        err.status === 404
          ? `<div class="empty-state">${icon("search", 36)}<h3>상품을 찾을 수 없어요.</h3><p>삭제되었거나 숨김 처리된 상품이에요.</p><a class="btn btn-secondary" href="#/">상품 목록으로</a></div>`
          : errorState(err);
    }
  }

  function specRows(spec) {
    if (!spec) return [];
    const gb = (n) => (n >= 1024 && n % 1024 === 0 ? `${n / 1024} TB` : `${n} GB`);
    const rows = [
      ["제조사", spec.manufacturer],
      ["모델명", spec.model_name],
      ["CPU", spec.cpu_model],
      ["코어", spec.cpu_cores && `${spec.cpu_cores} 코어`],
      ["메모리", spec.ram_gb && `${spec.ram_gb} GB`],
      ["GPU", spec.gpu_model],
      ["VRAM", spec.vram_gb && `${spec.vram_gb} GB`],
      ["저장 공간", spec.storage_gb && `${gb(spec.storage_gb)}${spec.storage_type ? ` · ${spec.storage_type}` : ""}`],
    ];
    for (const [k, v] of Object.entries(spec.extra_specs || {})) rows.push([k, typeof v === "object" ? JSON.stringify(v) : String(v)]);
    return rows.filter(([, v]) => v);
  }

  function actionsHtml() {
    const me = api.currentUser();
    const isOwner = me && me.id === product.seller.id;
    if (isOwner) {
      return `
        <div class="owner-box panel">
          <p class="eyebrow">MY LISTING</p>
          <h3>내 상품 관리</h3>
          <label class="field"><span>판매 상태</span>
            <select data-status>${Object.entries(PRODUCT_STATUS).map(([k, v]) => `<option value="${k}" ${k === product.status ? "selected" : ""}>${v}</option>`).join("")}</select>
          </label>
          <p class="muted small">예약·판매완료는 보통 <a class="link" href="#/trades">거래 내역</a>에서 수락/완료하면 자동으로 바뀌어요.</p>
          <div class="row-actions">
            <label class="btn btn-secondary file-btn">${icon("image", 16)} 사진 추가<input type="file" data-upload accept="image/jpeg,image/png,image/webp" multiple hidden></label>
            <a class="btn btn-secondary" href="#/trades">${icon("repeat", 16)} 들어온 요청 보기</a>
            <button class="btn btn-danger" data-delete>${icon("trash", 16)} 삭제</button>
          </div>
        </div>`;
    }
    let tradeBtn;
    if (myTrade) {
      tradeBtn = `<a class="btn" href="#/trades">${icon("check", 16)} ${TRADE_STATUS[myTrade.status]} · 거래 내역 보기</a>`;
    } else if (product.status !== "on_sale") {
      tradeBtn = `<button class="btn" disabled>${PRODUCT_STATUS[product.status]}</button>`;
    } else {
      tradeBtn = `<button class="btn" data-trade>구매 요청하기 ${icon("arrowRight", 16)}</button>`;
    }
    const saved = product.is_favorited === true;
    return `
      <div class="buy-actions">
        ${tradeBtn}
        <button class="btn btn-secondary" data-chat ${product.status === "sold" ? "disabled" : ""}>${icon("chat", 17)} 채팅하기</button>
        <button class="btn btn-secondary heart-btn card-heart-lg ${saved ? "saved" : ""}" data-heart="${product.id}" aria-pressed="${saved}" aria-label="${saved ? "찜 해제" : "찜하기"}">${icon("heart", 19, saved ? "filled" : "")}</button>
      </div>
      <form class="trade-form" data-trade-form hidden>
        <label class="field"><span>판매자에게 남길 말 (선택)</span>
          <textarea name="message" maxlength="200" rows="3" placeholder="예: 오늘 저녁 강남역 직거래 가능할까요?"></textarea></label>
        <div class="row-actions"><button class="btn" type="submit">요청 보내기</button><button class="btn btn-secondary" type="button" data-trade-cancel>닫기</button></div>
      </form>
      <p class="muted small note">${icon("shield", 15)} 구매 요청은 결제가 아니에요. 판매자가 수락하면 상품이 예약중으로 바뀌어요.</p>`;
  }

  function render() {
    const p = product;
    const imgs = p.images || [];
    imageIndex = Math.min(imageIndex, Math.max(0, imgs.length - 1));
    const me = api.currentUser();
    const isOwner = me && me.id === p.seller.id;
    const rows = specRows(p.spec);
    el.innerHTML = `
      <a href="#/" class="back-link muted">${icon("arrowLeft", 16)} 상품 목록으로</a>
      <div class="detail-grid">
        <div class="gallery">
          <div class="product-plate main-image">
            ${imgs.length ? `<img src="${esc(imgs[imageIndex].url)}" alt="${esc(p.title)}">` : placeholder(p.category, "등록된 사진이 없어요")}
            ${p.status !== "on_sale" ? `<span class="plate-status">${PRODUCT_STATUS[p.status]}</span>` : ""}
          </div>
          ${imgs.length > 1 || (isOwner && imgs.length) ? `<div class="thumbs">${imgs.map((im, i) => `
            <div class="thumb-wrap">
              <button class="thumb ${i === imageIndex ? "active" : ""}" data-img="${i}" aria-label="사진 ${i + 1}"><img src="${esc(im.thumbnail_url)}" alt=""></button>
              ${isOwner ? `<button class="thumb-del" data-del-img="${im.id}" aria-label="사진 삭제">${icon("x", 12)}</button>` : ""}
            </div>`).join("")}</div>` : ""}
        </div>
        <div class="detail-info">
          <div class="badges"><span class="eyebrow">${esc(categoryName(p.category))}</span>
            <span class="badge">${PRODUCT_STATUS[p.status]}</span>
            ${p.is_hot_deal ? `<span class="badge hot">${icon("zap", 11)} HOT DEAL</span>` : ""}</div>
          <h1 class="detail-title">${esc(p.title)}</h1>
          <div class="spec-tags lg">${specTags(p.spec, 6).map((t) => `<span class="spec-tag">${esc(t)}</span>`).join("")}</div>
          <div class="price-box">
            <p class="price">${money(p.price)}<span>원</span></p>
            <p class="muted">${esc(conditionName(p.condition))} · ${PRODUCT_STATUS[p.status]}</p>
          </div>
          <div class="info-grid">
            <div><p class="muted">판매자</p><p>${esc(p.seller.nickname)}${isOwner ? ' <span class="badge">나</span>' : ""}</p></div>
            <div><p class="muted">거래 지역</p><p>${icon("mapPin", 14)} ${esc(p.trade_location || "미정")}</p></div>
            <div><p class="muted">조회 · 찜</p><p>${icon("eye", 14)} ${p.view_count} · <span data-likes="${p.id}">${icon("heart", 11)} ${p.favorite_count}</span></p></div>
            <div><p class="muted">등록일</p><p>${formatDate(p.created_at)}</p></div>
          </div>
          <div id="actions">${actionsHtml()}</div>
        </div>
      </div>
      <section class="detail-sections">
        <div><p class="eyebrow">PRODUCT DETAILS</p><h2>상품 설명</h2><p class="description">${esc(p.description)}</p></div>
        <div><p class="eyebrow">SPECIFICATIONS</p><h2>상세 스펙</h2>
          ${rows.length ? `<dl class="spec-table">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>` : `<p class="muted">입력된 스펙이 없어요.</p>`}
        </div>
      </section>
      ${meetupHtml(p)}`;
    mountMap(p);
  }

  function meetupHtml(p) {
    if (!p.trade_point) return "";
    return `
      <section class="meetup">
        <div class="meetup-head">
          <div><p class="eyebrow">MEET-UP SPOT</p><h2>거래 장소</h2><p class="muted">${icon("mapPin", 14)} ${esc(p.trade_location)}</p></div>
          <div class="row-actions">
            <a class="btn" data-directions href="${esc(directionsUrl(p.trade_location, p.trade_point))}" target="_blank" rel="noopener">${icon("arrowUpRight", 16)} 길찾기</a>
            <a class="btn btn-secondary" href="${esc(placeUrl(p.trade_location, p.trade_point))}" target="_blank" rel="noopener">카카오맵에서 보기</a>
          </div>
        </div>
        <div class="meetup-map lg" data-detail-map><p class="muted center">지도를 불러오는 중이에요…</p></div>
        <p class="muted small note">${icon("info", 15)} 길찾기를 누르면 카카오맵이 열려요. 출발지를 정하고 자동차·대중교통·도보 중에서 고를 수 있어요.</p>
      </section>`;
  }

  async function mountMap(p) {
    const box = el.querySelector("[data-detail-map]");
    if (!box) return;
    try {
      const kakao = await loadKakaoMaps();
      if (!alive || !box.isConnected) return; // re-rendered meanwhile: the new box mounts its own map
      box.innerHTML = "";
      drawMap(kakao, box, p.trade_point, { level: 3 });
    } catch {
      if (box.isConnected) box.innerHTML = `<p class="muted center">${icon("mapPin", 22)}<br>지도를 표시할 수 없어요. 위의 버튼으로 카카오맵에서 확인해 주세요.</p>`;
    }
  }

  // ---------------------------------------------------------------- actions
  el.addEventListener("click", async (e) => {
    const t = e.target.closest("button, [data-retry]");
    if (!t) return;
    if (t.matches("[data-retry]")) return load();
    if (t.matches("[data-img]")) {
      imageIndex = Number(t.dataset.img);
      return render();
    }
    if (t.matches("[data-trade]")) {
      if (!api.isLoggedIn()) return goLogin();
      const form = el.querySelector("[data-trade-form]");
      form.hidden = false;
      form.querySelector("textarea").focus();
      return;
    }
    if (t.matches("[data-trade-cancel]")) {
      el.querySelector("[data-trade-form]").hidden = true;
      return;
    }
    if (t.matches("[data-chat]")) {
      if (!api.isLoggedIn()) return goLogin();
      const room = await busy(t, () => api.post("/chat/rooms", { product_id: product.id }, { auth: "required" }));
      if (room) navigate(`/chat/${room.id}`);
      return;
    }
    if (t.matches("[data-delete]")) {
      if (!confirm("이 상품을 삭제할까요? 삭제하면 목록과 검색에서 사라져요.")) return;
      const ok = await busy(t, () => api.del(`/products/${product.id}`, { auth: "required" }), "삭제 중");
      if (ok) {
        toast("상품을 삭제했어요.", "success");
        navigate("/profile");
      }
      return;
    }
    if (t.matches("[data-del-img]")) {
      if (!confirm("이 사진을 삭제할까요?")) return;
      const updated = await busy(t, () => api.del(`/products/${product.id}/images/${t.dataset.delImg}`, { auth: "required" }));
      if (updated) {
        product = updated;
        imageIndex = 0;
        render();
      }
    }
  });

  el.addEventListener("submit", async (e) => {
    if (!e.target.matches("[data-trade-form]")) return;
    e.preventDefault();
    const btn = e.target.querySelector('[type="submit"]');
    const message = e.target.message.value.trim() || undefined;
    const trade = await busy(btn, () => api.post("/trades", { product_id: product.id, message }, { auth: "required" }), "요청 중");
    if (!trade) return load(); // e.g. someone reserved it meanwhile -> show fresh state
    markOwnTradeAction(trade.id, "requested");
    toast("구매 요청을 보냈어요. 판매자가 수락하면 알려드릴게요.", "success");
    myTrade = trade;
    el.querySelector("#actions").innerHTML = actionsHtml();
  });

  el.addEventListener("change", async (e) => {
    if (e.target.matches("[data-status]")) {
      const select = e.target;
      const previous = product.status;
      const updated = await busy(select, () => api.patch(`/products/${product.id}/status`, { status: select.value }, { auth: "required" }));
      if (updated) {
        product = updated;
        toast(`상태를 '${PRODUCT_STATUS[updated.status]}'(으)로 바꿨어요.`, "success");
        if (updated.status === "hidden") return navigate("/profile"); // hidden products have no public page
        render();
      } else select.value = previous;
      return;
    }
    if (e.target.matches("[data-upload]")) {
      const files = [...e.target.files];
      e.target.value = "";
      if (!files.length) return;
      const bad = files.find((f) => !["image/jpeg", "image/png", "image/webp"].includes(f.type) || f.size > 10 * 1024 * 1024);
      if (bad) return toast(`${bad.name}: JPG/PNG/WebP, 10MB 이하만 올릴 수 있어요.`, "error");
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      toast("사진을 올리는 중이에요…", "info", 1500);
      try {
        product = await api.request("POST", `/products/${product.id}/images`, { form, auth: "required" });
        toast(`사진 ${files.length}장을 추가했어요.`, "success");
        render();
      } catch (err) {
        toast(err.message, "error");
      }
    }
  });

  bindHearts(el, (pid, r) => (product.is_favorited = r.favorited));
  // Someone accepted/completed/canceled a trade on this product: show the new status live.
  const offs = [
    rt.on("trade", (e) => e.trade.product.id === id && !el.querySelector("[data-trade-form]:not([hidden])") && load()),
    rt.on("resync", () => load()),
  ];
  load();
  return {
    el,
    destroy() {
      alive = false;
      offs.forEach((f) => f());
    },
  };
}
