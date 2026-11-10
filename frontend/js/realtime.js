// One WebSocket per logged-in tab: /api/v1/chat/ws pushes "message", "read" and "trade" events.
// - auth is the first message (not the URL), as the server requires
// - 4401 (token expired / logged out) -> refresh the token and reconnect, or stop if that fails
// - other drops -> reconnect with backoff; on reconnect, views refetch what they missed
import { accessToken, isLoggedIn, refreshTokens } from "./api.js";

const handlers = new Map(); // type -> Set<fn>
let ws = null;
let wanted = false;
let attempt = 0;
let timer = null;
let pingTimer = null;
let status = "off";

export function on(type, fn) {
  if (!handlers.has(type)) handlers.set(type, new Set());
  handlers.get(type).add(fn);
  return () => handlers.get(type)?.delete(fn);
}

function emit(type, data) {
  handlers.get(type)?.forEach((fn) => {
    try {
      fn(data);
    } catch (e) {
      console.error(e);
    }
  });
}

function setStatus(s) {
  status = s;
  emit("status", s);
}
export const connectionStatus = () => status;

export function start() {
  wanted = true;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  connect();
}

export function stop() {
  wanted = false;
  clearTimeout(timer);
  clearInterval(pingTimer);
  if (ws) {
    ws.onclose = null;
    ws.close(1000);
    ws = null;
  }
  setStatus("off");
}

function connect() {
  if (!wanted || !isLoggedIn()) return;
  clearTimeout(timer);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const sock = new WebSocket(`${proto}://${location.host}/api/v1/chat/ws`);
  ws = sock;
  setStatus("connecting");

  sock.onopen = () => sock.send(JSON.stringify({ type: "auth", token: accessToken() }));

  sock.onmessage = (e) => {
    let data;
    try {
      data = JSON.parse(e.data);
    } catch {
      return;
    }
    if (data.type === "ready") {
      const reconnected = attempt > 0;
      attempt = 0;
      setStatus("live");
      clearInterval(pingTimer);
      pingTimer = setInterval(() => sock.readyState === WebSocket.OPEN && sock.send('{"type":"ping"}'), 25000);
      if (reconnected) emit("resync", null); // views fetch anything pushed while we were offline
      return;
    }
    if (data.type === "pong" || data.type === "error") return;
    emit(data.type, data);
  };

  sock.onclose = async (e) => {
    clearInterval(pingTimer);
    if (ws !== sock) return; // replaced by a newer socket
    ws = null;
    if (!wanted) return setStatus("off");
    setStatus("reconnecting");
    if (e.code === 4401) {
      try {
        await refreshTokens(); // access token expired: get a new one, then reconnect right away
        attempt = 1;
        return connect();
      } catch {
        return setStatus("off"); // refresh failed -> logged out (api.js notifies the app)
      }
    }
    attempt += 1;
    const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)) + Math.random() * 500;
    timer = setTimeout(connect, delay);
  };
}

// Laptop wakes up / network returns: try immediately instead of waiting out the backoff.
window.addEventListener("online", () => wanted && !ws && connect());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && wanted && !ws) connect();
});
