import * as api from "../api.js";
import { icon } from "../icons.js";
import { CATEGORIES, CONDITIONS, busy, categoryName, esc, money, toast } from "../ui.js";
import { navigate } from "../app.js";
import { section, workspaceHeader } from "./common.js";
import { drawMap, loadKakaoMaps } from "../kakao.js";

const MAX_FILES = 10;
const MAX_MB = 10;

export function renderSell() {
  const el = section();
  const files = []; // {file, url}
  let point = null; // {lat, lng} picked on the map, or null = text-only location
  let kakao = null; // SDK, once loaded
  let pin = null; // {map, marker}
  let alive = true;

  el.innerHTML = `
    ${workspaceHeader("SELL ON SPECGRID", "상품 판매하기", "좋은 장비를 기다리는 사람과 연결해 보세요.", "sell")}
    <form class="sell-layout" novalidate>
      <div class="stack">
        <section class="panel">
          <div class="panel-head"><p class="eyebrow">01 / BASIC INFO</p><h2>어떤 제품을 판매하시나요?</h2><p class="muted">정확한 정보는 더 빠른 거래로 이어져요.</p></div>
          <div class="form-stack">
            <label class="field"><span>상품명 *</span><input name="title" required minlength="2" maxlength="100" placeholder="예: NVIDIA RTX 4090 그래픽카드"></label>
            <div class="form-grid">
              <label class="field"><span>카테고리 *</span><select name="category">${CATEGORIES.map((c) => `<option value="${c.id}">${c.name}</option>`).join("")}</select></label>
              <label class="field"><span>상품 상태 *</span><select name="condition">${CONDITIONS.map((c) => `<option value="${c.id}" ${c.id === "like_new" ? "selected" : ""}>${c.name}</option>`).join("")}</select></label>
              <label class="field"><span>판매 가격 (원) *</span><input name="price" type="number" inputmode="numeric" min="0" max="1000000000" step="1" required placeholder="0"></label>
            </div>
            <div class="field meetup-field"><span>거래 장소 <em class="muted" data-place-hint></em></span>
              <div class="place-search">
                <input name="trade_location" maxlength="100" placeholder="예: 강남역, 서울 강남구" autocomplete="off" aria-label="거래 장소">
                <button type="button" class="btn btn-secondary" data-place-search hidden>${icon("search", 16)} 지도에서 찾기</button>
              </div>
              <ul class="place-results" data-place-results hidden></ul>
              <div class="pin-bar" data-pin-bar hidden>
                <span>${icon("mapPin", 14)} 지도 위치가 지정됐어요. 지도를 눌러 위치를 옮길 수 있어요.</span>
                <button type="button" class="link" data-pin-clear>위치 지우기</button>
              </div>
              <div class="meetup-map" data-sell-map hidden></div>
            </div>
            <label class="field"><span>상품 설명 * <em class="muted" data-count>0 / 5000</em></span>
              <textarea name="description" required minlength="10" maxlength="5000" placeholder="구매 시기, 사용 상태, 구성품 등을 자세히 알려주세요. (10자 이상)"></textarea></label>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><p class="eyebrow">02 / SPECIFICATIONS</p><h2>상세 스펙</h2><p class="muted">해당하는 항목만 입력하세요. 스펙을 입력하면 정밀 필터 검색에 노출돼요.</p></div>
          <div class="form-grid">
            <label class="field"><span>제조사</span><input name="manufacturer" maxlength="100" placeholder="예: NVIDIA, Apple, AMD"></label>
            <label class="field"><span>모델명</span><input name="model_name" maxlength="150" placeholder="예: Founders Edition"></label>
            <label class="field"><span>CPU</span><input name="cpu_model" maxlength="120" placeholder="예: AMD Ryzen 7 7800X3D"></label>
            <label class="field"><span>CPU 코어 수</span><input name="cpu_cores" type="number" min="1" max="1024" placeholder="예: 8"></label>
            <label class="field"><span>메모리 RAM (GB)</span><input name="ram_gb" type="number" min="1" max="65536" placeholder="예: 32"></label>
            <label class="field"><span>GPU</span><input name="gpu_model" maxlength="120" placeholder="예: RTX 4090"></label>
            <label class="field"><span>그래픽 메모리 VRAM (GB)</span><input name="vram_gb" type="number" min="1" max="1024" placeholder="예: 24"></label>
            <label class="field"><span>저장 공간 (GB)</span><input name="storage_gb" type="number" min="1" max="10000000" placeholder="예: 1024"></label>
            <label class="field"><span>저장장치 종류</span><input name="storage_type" maxlength="20" placeholder="예: NVMe SSD"></label>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><p class="eyebrow">03 / PHOTOS</p><h2>상품 사진</h2><p class="muted">JPG·PNG·WebP, 장당 ${MAX_MB}MB, 최대 ${MAX_FILES}장. 첫 번째 사진이 대표 사진이 돼요. 위치정보(GPS)는 서버에서 자동으로 지워요.</p></div>
          <label class="dropzone">${icon("image", 26)}<span>사진을 선택하거나 여기로 끌어다 놓으세요</span>
            <input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple hidden></label>
          <div class="photo-list" data-photos></div>
        </section>
      </div>
      <aside class="panel preview">
        <p class="eyebrow">LISTING PREVIEW</p>
        <div class="product-plate preview-plate" data-preview-img><span class="muted center">${icon("image", 32)}<br>사진을 등록하면 여기에 보여요.</span></div>
        <p class="muted small" data-pv-cat>${categoryName("gpu")}</p>
        <p class="pv-title" data-pv-title>상품명을 입력해 주세요</p>
        <p class="pv-price" data-pv-price>가격 미입력</p>
        <p class="form-error" data-error role="alert" hidden></p>
        <button class="btn full" type="submit">상품 등록하기 ${icon("arrowRight", 16)}</button>
        <p class="muted small note">${icon("info", 15)} 등록 후 상품 상세 페이지에서 사진을 더 추가하거나 상태를 바꿀 수 있어요.</p>
      </aside>
    </form>`;

  const form = el.querySelector("form");
  const $ = (s) => el.querySelector(s);

  function renderPhotos() {
    $("[data-photos]").innerHTML = files
      .map((f, i) => `<div class="photo-item"><img src="${f.url}" alt=""><button type="button" data-remove="${i}" aria-label="사진 빼기">${icon("x", 12)}</button>${i === 0 ? '<span class="cover">대표</span>' : ""}</div>`)
      .join("");
    $("[data-preview-img]").innerHTML = files.length
      ? `<img src="${files[0].url}" alt="미리보기">`
      : `<span class="muted center">${icon("image", 32)}<br>사진을 등록하면 여기에 보여요.</span>`;
  }

  function addFiles(list) {
    for (const file of list) {
      if (files.length >= MAX_FILES) {
        toast(`사진은 최대 ${MAX_FILES}장까지 올릴 수 있어요.`, "error");
        break;
      }
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
        toast(`${file.name}: JPG, PNG, WebP만 올릴 수 있어요.`, "error");
        continue;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast(`${file.name}: ${MAX_MB}MB 이하만 올릴 수 있어요.`, "error");
        continue;
      }
      files.push({ file, url: URL.createObjectURL(file) });
    }
    renderPhotos();
  }

  function updatePreview() {
    $("[data-pv-cat]").textContent = categoryName(form.category.value);
    $("[data-pv-title]").textContent = form.title.value.trim() || "상품명을 입력해 주세요";
    $("[data-pv-price]").textContent = form.price.value ? `${money(Number(form.price.value))}원` : "가격 미입력";
    $("[data-count]").textContent = `${form.description.value.length} / 5000`;
  }

  function showError(msg) {
    const box = $("[data-error]");
    box.textContent = msg || "";
    box.hidden = !msg;
  }

  function validate() {
    const title = form.title.value.trim();
    const desc = form.description.value.trim();
    const price = form.price.value.trim();
    if (title.length < 2) return ["title", "상품명을 2자 이상 입력해 주세요."];
    if (!price || !/^\d+$/.test(price)) return ["price", "가격을 숫자로 입력해 주세요."];
    if (Number(price) > 1_000_000_000) return ["price", "가격은 10억 원 이하로 입력해 주세요."];
    if (desc.length < 10) return ["description", "상품 설명을 10자 이상 입력해 주세요."];
    for (const name of ["cpu_cores", "ram_gb", "vram_gb", "storage_gb"]) {
      const v = form[name].value.trim();
      if (v && (!/^\d+$/.test(v) || Number(v) < 1)) return [name, "스펙 숫자 항목은 1 이상의 정수로 입력해 주세요."];
    }
    return null;
  }

  function payload() {
    const text = (n) => form[n].value.trim() || undefined;
    const num = (n) => (form[n].value.trim() ? Number(form[n].value) : undefined);
    const spec = {
      manufacturer: text("manufacturer"), model_name: text("model_name"), cpu_model: text("cpu_model"),
      cpu_cores: num("cpu_cores"), ram_gb: num("ram_gb"), gpu_model: text("gpu_model"), vram_gb: num("vram_gb"),
      storage_gb: num("storage_gb"), storage_type: text("storage_type"),
    };
    const hasSpec = Object.values(spec).some((v) => v !== undefined);
    return {
      title: form.title.value.trim(),
      category: form.category.value,
      condition: form.condition.value,
      price: Number(form.price.value),
      trade_location: text("trade_location"),
      trade_point: point && text("trade_location") ? point : undefined,
      description: form.description.value.trim(),
      spec: hasSpec ? spec : undefined,
    };
  }

  // ------------------------------------------------------------ trade place (Kakao Maps)
  const results = $("[data-place-results]");

  function setPoint(next) {
    point = next;
    $("[data-pin-bar]").hidden = !point;
    const box = $("[data-sell-map]");
    box.hidden = !point;
    if (!point) return;
    if (!pin) {
      pin = drawMap(kakao, box, point);
      kakao.maps.event.addListener(pin.map, "click", (ev) => {
        const ll = ev.latLng;
        pin.marker.setPosition(ll);
        point = { lat: ll.getLat(), lng: ll.getLng() };
      });
    } else {
      const ll = new kakao.maps.LatLng(point.lat, point.lng);
      pin.map.relayout(); // the box may have been hidden
      pin.map.setCenter(ll);
      pin.marker.setPosition(ll);
    }
  }

  function searchPlaces() {
    const q = form.trade_location.value.trim();
    if (!kakao) return;
    if (q.length < 2) {
      toast("장소 이름을 2자 이상 입력해 주세요.", "error");
      return form.trade_location.focus();
    }
    new kakao.maps.services.Places().keywordSearch(q, (data, status) => {
      if (!alive) return;
      results.hidden = false;
      if (status !== kakao.maps.services.Status.OK) {
        results.innerHTML = `<li class="muted">${status === kakao.maps.services.Status.ZERO_RESULT ? "검색 결과가 없어요. 다른 이름으로 찾아보세요." : "검색하지 못했어요. 잠시 후 다시 시도해 주세요."}</li>`;
        return;
      }
      results.innerHTML = data
        .map((d, i) => `<li><button type="button" data-place="${i}"><strong>${esc(d.place_name)}</strong><span class="muted">${esc(d.road_address_name || d.address_name)}</span></button></li>`)
        .join("");
      results._data = data;
    }, { size: 6 });
  }

  loadKakaoMaps()
    .then((k) => {
      if (!alive) return;
      kakao = k;
      $("[data-place-search]").hidden = false;
      $("[data-place-hint]").textContent = "검색해서 고르면 지도에 표시돼요";
    })
    .catch(() => {}); // no key / SDK blocked: the field stays a plain text input

  form.trade_location.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && kakao) {
      e.preventDefault(); // search instead of submitting the whole form
      searchPlaces();
    }
  });
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-place-search]")) return searchPlaces();
    if (e.target.closest("[data-pin-clear]")) return setPoint(null);
    const pick = e.target.closest("[data-place]");
    if (pick) {
      const d = results._data[Number(pick.dataset.place)];
      form.trade_location.value = d.place_name.slice(0, 100);
      results.hidden = true;
      setPoint({ lat: Number(d.y), lng: Number(d.x) });
    }
  });

  el.addEventListener("input", updatePreview);
  el.addEventListener("change", (e) => {
    if (e.target.name === "photos") {
      addFiles([...e.target.files]);
      e.target.value = "";
    }
    updatePreview();
  });
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-remove]");
    if (!b) return;
    const [removed] = files.splice(Number(b.dataset.remove), 1);
    URL.revokeObjectURL(removed.url);
    renderPhotos();
  });
  const zone = $(".dropzone");
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    addFiles([...e.dataTransfer.files]);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const problem = validate();
    if (problem) {
      showError(problem[1]);
      form[problem[0]].focus();
      return;
    }
    showError("");
    const btn = form.querySelector('[type="submit"]');
    const created = await busy(btn, async () => {
      const product = await api.post("/products", payload(), { auth: "required" });
      if (files.length) {
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f.file));
        try {
          await api.request("POST", `/products/${product.id}/images`, { form: fd, auth: "required" });
        } catch (err) {
          // The listing exists; only the photos failed. Say so instead of pretending all is well.
          toast(`상품은 등록됐지만 사진을 올리지 못했어요: ${err.message} 상세 페이지에서 다시 추가해 주세요.`, "error", 6000);
        }
      }
      return product;
    }, files.length ? "등록하고 사진 올리는 중" : "등록 중");
    if (!created) return;
    files.forEach((f) => URL.revokeObjectURL(f.url));
    toast("상품을 등록했어요!", "success");
    navigate(`/product/${created.id}`);
  });

  return {
    el,
    destroy() {
      alive = false;
      files.forEach((f) => URL.revokeObjectURL(f.url));
    },
  };
}
