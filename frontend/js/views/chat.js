// 채팅: room list + conversation. New messages arrive over the WebSocket (realtime.js);
// sending goes through REST, exactly as the backend expects.
import * as api from "../api.js";
import * as rt from "../realtime.js";
import { icon } from "../icons.js";
import { PRODUCT_STATUS, avatar, emptyState, errorState, esc, loading, money, productImage, timeAgo, toast } from "../ui.js";
import { refreshUnread } from "../app.js";
import { section, workspaceHeader } from "./common.js";

export function renderChat({ roomId }) {
  const el = section("page-wrap workspace chat-page");
  let rooms = [];
  let room = null;
  let messages = [];
  const seen = new Set(); // message ids already shown (the sender also gets its own message pushed)
  let hasOlder = false;
  let alive = true;
  let partnerReadUpTo = 0; // my messages with id <= this are read

  el.innerHTML = `
    ${workspaceHeader("DIRECT MESSAGES", "채팅", "판매자·구매자와 실시간으로 대화하세요.", "chat")}
    <div class="workspace-split chat-split ${roomId ? "has-room" : ""}">
      <div class="room-list" id="rooms">${loading("채팅방을 불러오는 중이에요")}</div>
      <div class="conversation" id="conv">${roomId ? loading("대화를 불러오는 중이에요") : emptyState("대화를 선택하세요", "왼쪽 목록에서 채팅방을 고르거나, 상품 상세에서 '채팅하기'를 눌러 대화를 시작하세요.", "", "chat")}</div>
    </div>`;
  const roomsBox = el.querySelector("#rooms");
  const conv = el.querySelector("#conv");
  const me = () => api.currentUser();

  // ---------------------------------------------------------------- rooms
  async function loadRooms() {
    try {
      const data = await api.get("/chat/rooms", { size: 50 }, { auth: "required" });
      if (!alive) return;
      rooms = data.items;
      renderRooms();
    } catch (err) {
      if (alive) roomsBox.innerHTML = errorState(err);
    }
  }

  function renderRooms() {
    if (!rooms.length) {
      roomsBox.innerHTML = `<div class="room-empty muted">${icon("chat", 26)}<p>아직 대화가 없어요.<br>상품 상세에서 '채팅하기'를 눌러 보세요.</p></div>`;
      return;
    }
    roomsBox.innerHTML = rooms
      .map((r) => `
        <a href="#/chat/${r.id}" class="list-row ${r.id === roomId ? "active" : ""}">
          ${productImage(r.product)}
          <span class="room-text">
            <span class="room-top"><b>${avatar(r.partner, 18)} ${esc(r.partner.nickname)}</b><small>${r.last_message ? timeAgo(r.last_message.created_at) : ""}</small></span>
            <small class="room-product">${esc(r.product.title)}</small>
            <span class="room-last">${r.last_message ? esc(r.last_message.content) : '<span class="muted">새 대화</span>'}</span>
          </span>
          ${r.unread_count ? `<span class="unread-dot">${r.unread_count}</span>` : ""}
        </a>`)
      .join("");
  }

  // ---------------------------------------------------------------- conversation
  async function openRoom() {
    if (!roomId) return;
    try {
      room = await api.get(`/chat/rooms/${roomId}`, null, { auth: "required" });
      const page = await api.get(`/chat/rooms/${roomId}/messages`, { limit: 30 }, { auth: "required" });
      if (!alive) return;
      messages = page.items;
      hasOlder = page.has_more;
      messages.forEach((m) => seen.add(m.id));
      partnerReadUpTo = Math.max(0, ...messages.filter((m) => m.sender_id === me()?.id && m.is_read).map((m) => m.id));
      renderConversation();
      markRead();
    } catch (err) {
      if (!alive) return;
      conv.innerHTML =
        err.status === 404
          ? emptyState("채팅방을 찾을 수 없어요", "삭제되었거나 참여하지 않은 대화예요.", `<a class="btn btn-secondary" href="#/chat">채팅 목록으로</a>`, "chat")
          : errorState(err);
    }
  }

  function bubble(m) {
    const mine = m.sender_id === me()?.id;
    const read = mine && (m.is_read || m.id <= partnerReadUpTo);
    return `<div class="message ${mine ? "mine" : ""}" data-mid="${m.id}"><span class="msg-text">${esc(m.content)}</span><small>${timeAgo(m.created_at)}${mine ? ` · <span class="${read ? "green" : ""}">${read ? "읽음" : "안 읽음"}</span>` : ""}</small></div>`;
  }

  function renderConversation() {
    const p = room.product;
    const disabled = p.is_deleted || room.partner == null;
    conv.innerHTML = `
      <div class="conv-head">
        <a href="#/chat" class="icon-button back-rooms" aria-label="목록으로">${icon("arrowLeft", 18)}</a>
        <a href="${p.is_deleted ? "#/chat" : `#/product/${p.id}`}" class="conv-product">
          <span class="thumb">${productImage(p)}</span>
          <span><b>${esc(p.title)}</b><small>${money(p.price)}원 · ${p.is_deleted ? "삭제된 상품" : PRODUCT_STATUS[p.status]}</small></span>
        </a>
        <span class="conv-partner">${avatar(room.partner, 22)} ${esc(room.partner.nickname)} <small class="muted">(${room.my_role === "buyer" ? "판매자" : "구매자"})</small></span>
      </div>
      <div class="messages" id="msgs">
        ${hasOlder ? `<button class="btn btn-secondary older" data-older>이전 메시지 보기</button>` : ""}
        ${messages.length ? messages.map(bubble).join("") : `<p class="muted center conv-empty">첫 메시지를 보내 보세요. 예) "안녕하세요, 아직 판매 중인가요?"</p>`}
      </div>
      <form class="composer" data-send>
        <textarea name="content" rows="1" maxlength="1000" placeholder="메시지 입력 (Enter 전송)" title="Enter 전송 · Shift+Enter 줄바꿈" ${disabled ? "disabled" : ""}></textarea>
        <button class="btn" type="submit" aria-label="보내기" ${disabled ? "disabled" : ""}>${icon("send", 16)}</button>
      </form>`;
    scrollToBottom();
    conv.querySelector("textarea")?.focus();
  }

  function scrollToBottom() {
    const box = conv.querySelector("#msgs");
    if (box) box.scrollTop = box.scrollHeight;
  }

  function append(m) {
    if (seen.has(m.id)) return;
    seen.add(m.id);
    messages.push(m);
    const box = conv.querySelector("#msgs");
    if (!box) return;
    box.querySelector(".conv-empty")?.remove();
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    box.insertAdjacentHTML("beforeend", bubble(m));
    if (nearBottom || m.sender_id === me()?.id) scrollToBottom();
  }

  async function markRead() {
    if (!roomId || document.visibilityState !== "visible") return;
    try {
      await api.post(`/chat/rooms/${roomId}/read`, undefined, { auth: "required" });
      const r = rooms.find((x) => x.id === roomId);
      if (r && r.unread_count) {
        r.unread_count = 0;
        renderRooms();
      }
      refreshUnread();
    } catch {
      /* not critical */
    }
  }

  async function loadOlder(btn) {
    btn.disabled = true;
    try {
      const page = await api.get(`/chat/rooms/${roomId}/messages`, { before_id: messages[0].id, limit: 30 }, { auth: "required" });
      const box = conv.querySelector("#msgs");
      const before = box.scrollHeight;
      page.items.forEach((m) => seen.add(m.id));
      messages = page.items.concat(messages);
      hasOlder = page.has_more;
      btn.remove();
      box.insertAdjacentHTML("afterbegin", (hasOlder ? `<button class="btn btn-secondary older" data-older>이전 메시지 보기</button>` : "") + page.items.map(bubble).join(""));
      box.scrollTop = box.scrollHeight - before; // keep the view where it was
    } catch (err) {
      btn.disabled = false;
      toast(err.message, "error");
    }
  }

  // Catch up after a reconnect: anything newer than the last message we have.
  async function resync() {
    loadRooms();
    if (!roomId || !messages.length) return openRoom();
    try {
      const page = await api.get(`/chat/rooms/${roomId}/messages`, { after_id: messages[messages.length - 1].id, limit: 100 }, { auth: "required" });
      page.items.forEach(append);
      markRead();
    } catch {
      /* next event will retry */
    }
  }

  async function send(form) {
    const ta = form.content;
    const content = ta.value.trim();
    if (!content) return;
    const btn = form.querySelector("button");
    btn.disabled = true;
    ta.disabled = true;
    try {
      const m = await api.post(`/chat/rooms/${roomId}/messages`, { content }, { auth: "required" });
      ta.value = "";
      ta.style.height = "";
      append(m);
      bumpRoom(roomId, m);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
      ta.disabled = false;
      ta.focus();
    }
  }

  function bumpRoom(id, m) {
    const r = rooms.find((x) => x.id === id);
    if (!r) return loadRooms();
    r.last_message = m;
    rooms = [r, ...rooms.filter((x) => x !== r)];
    renderRooms();
  }

  // ---------------------------------------------------------------- events
  el.addEventListener("submit", (e) => {
    if (!e.target.matches("[data-send]")) return;
    e.preventDefault();
    send(e.target);
  });
  el.addEventListener("keydown", (e) => {
    if (e.target.name === "content" && e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault(); // isComposing: don't send half-typed Korean (IME) text
      send(e.target.form);
    }
  });
  el.addEventListener("input", (e) => {
    if (e.target.name !== "content") return;
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(140, e.target.scrollHeight)}px`;
  });
  el.addEventListener("click", (e) => {
    const older = e.target.closest("[data-older]");
    if (older) return loadOlder(older);
    if (e.target.closest("[data-retry]")) {
      loadRooms();
      openRoom();
    }
  });

  const offs = [
    rt.on("message", (ev) => {
      if (ev.room_id === roomId) {
        append(ev.message);
        if (ev.message.sender_id !== me()?.id) markRead();
      }
      const r = rooms.find((x) => x.id === ev.room_id);
      if (!r) return loadRooms(); // a brand-new room
      r.last_message = ev.message;
      if (ev.room_id !== roomId && ev.message.sender_id !== me()?.id) r.unread_count += 1;
      rooms = [r, ...rooms.filter((x) => x !== r)];
      renderRooms();
    }),
    rt.on("read", (ev) => {
      if (ev.room_id !== roomId) return;
      partnerReadUpTo = Math.max(partnerReadUpTo, ...messages.map((m) => m.id));
      conv.querySelectorAll(".message.mine small span").forEach((s) => {
        s.textContent = "읽음";
        s.classList.add("green");
      });
    }),
    rt.on("resync", resync),
  ];
  const onVisible = () => document.visibilityState === "visible" && markRead();
  document.addEventListener("visibilitychange", onVisible);

  loadRooms();
  openRoom();
  return {
    el,
    destroy() {
      alive = false;
      offs.forEach((f) => f());
      document.removeEventListener("visibilitychange", onVisible);
    },
  };
}

