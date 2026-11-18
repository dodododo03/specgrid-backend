// REST client for the SpecGrid API (same origin: the FastAPI server also serves this frontend).
//
// Tokens live in localStorage so a page reload keeps you logged in. When a request gets 401,
// we use the refresh token once (rotation: the server hands back a NEW refresh token) and retry.
// All concurrent 401s share ONE refresh call — sending the same refresh token twice would look
// like token theft to the server and log the user out everywhere.

const API = "/api/v1";
const KEY = "specgrid.auth";

let tokens = load();
let me = null; // cached /users/me
const listeners = new Set();
let refreshing = null;

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function save(next) {
  tokens = next;
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next));
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: tokens just live in memory */
  }
}

export class ApiError extends Error {
  constructor(status, code, message, detail) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const FIELD_NAMES = {
  email: "이메일", password: "비밀번호", nickname: "닉네임", title: "상품명", description: "상품 설명",
  price: "가격", category: "카테고리", condition: "상품 상태", trade_location: "거래 장소", trade_point: "지도 위치",
  content: "메시지", message: "메시지", cpu_cores: "CPU 코어 수", ram_gb: "RAM", vram_gb: "VRAM",
  storage_gb: "저장 공간", manufacturer: "제조사", model_name: "모델명", cpu_model: "CPU", gpu_model: "GPU",
  storage_type: "저장장치 종류", files: "사진",
};

function validationMessage(detail) {
  // FastAPI 422: [{loc: ["body", "price"], msg: "..."}]
  if (!Array.isArray(detail) || !detail.length) return "입력값을 확인해 주세요.";
  const first = detail[0];
  const field = [...(first.loc || [])].reverse().find((p) => typeof p === "string" && p !== "body");
  const name = FIELD_NAMES[field] || field;
  let msg = (first.msg || "").replace(/^Value error, /, "");
  const rules = [
    [/at least (\d+) character/, (n) => `${n}자 이상 입력해 주세요.`],
    [/at most (\d+) character/, (n) => `${n}자 이하로 입력해 주세요.`],
    [/greater than or equal to (\d+)/, (n) => `${n} 이상이어야 합니다.`],
    [/less than or equal to (\d+)/, (n) => `${n} 이하여야 합니다.`],
    [/valid email/, () => "올바른 이메일 형식이 아닙니다."],
    [/valid integer/, () => "숫자를 입력해 주세요."],
    [/Field required/, () => "필수 항목입니다."],
  ];
  for (const [re, fmt] of rules) {
    const m = msg.match(re);
    if (m) {
      msg = fmt(m[1]);
      break;
    }
  }
  return name ? `${name}: ${msg}` : msg;
}

async function parse(res) {
  if (res.status === 204) return null;
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (res.ok) return body;
  if (res.status === 422) throw new ApiError(422, "validation", validationMessage(body?.detail), body?.detail);
  const message =
    body?.message ||
    (res.status >= 500 ? "서버에 문제가 생겼어요. 잠시 후 다시 시도해 주세요." : `요청에 실패했어요 (${res.status})`);
  throw new ApiError(res.status, body?.code || "error", message, body);
}

function notify() {
  listeners.forEach((fn) => {
    try {
      fn(me);
    } catch (e) {
      console.error(e);
    }
  });
}

export function onAuthChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const isLoggedIn = () => Boolean(tokens?.access_token);
export const currentUser = () => me;

/** Replace the cached /users/me (e.g. after a profile-photo change) and refresh the header. */
export function setMe(user) {
  me = user;
  notify();
}
export const accessToken = () => tokens?.access_token || null;

export async function refreshTokens() {
  if (!tokens?.refresh_token) throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  if (!refreshing) {
    const sent = tokens.refresh_token;
    refreshing = fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: sent }),
    })
      .then(parse)
      .then((t) => {
        save(t);
        return t;
      })
      .catch((err) => {
        // Only drop the session if nobody else rotated the token meanwhile (e.g. another tab).
        if (tokens?.refresh_token === sent) clearSession();
        throw err;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

function clearSession() {
  const was = isLoggedIn();
  save(null);
  me = null;
  if (was) notify();
}

/**
 * request("GET", "/products", {query, body, form, auth})
 *  - auth: "auto" (send token if we have one), "required", or "none"
 */
export async function request(method, path, { query, body, form, auth = "auto", retry = true } = {}) {
  let url = API + path;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "" || v === false) continue;
      if (Array.isArray(v)) v.forEach((item) => qs.append(k, item));
      else qs.append(k, v);
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const headers = {};
  let payload;
  if (form) payload = form; // multipart: the browser sets the boundary header itself
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const useToken = auth !== "none" && tokens?.access_token;
  if (auth === "required" && !useToken) throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  if (useToken) headers.Authorization = `Bearer ${tokens.access_token}`;

  let res;
  try {
    res = await fetch(url, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "network", "서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.");
  }
  if (res.status === 401 && useToken && retry && tokens?.refresh_token) {
    try {
      await refreshTokens();
    } catch {
      throw new ApiError(401, "unauthorized", "로그인이 만료되었어요. 다시 로그인해 주세요.");
    }
    return request(method, path, { query, body, form, auth, retry: false });
  }
  if (res.status === 401 && useToken) clearSession();
  return parse(res);
}

export const get = (path, query, opts = {}) => request("GET", path, { ...opts, query });
export const post = (path, body, opts = {}) => request("POST", path, { ...opts, body });
export const put = (path, body, opts = {}) => request("PUT", path, { ...opts, body });
export const patch = (path, body, opts = {}) => request("PATCH", path, { ...opts, body });
export const del = (path, opts = {}) => request("DELETE", path, opts);
export const putForm = (path, form, opts = {}) => request("PUT", path, { ...opts, form });

// ------------------------------------------------------------------ auth flows

export async function loadMe() {
  if (!isLoggedIn()) {
    me = null;
    return null;
  }
  try {
    me = await get("/users/me", null, { auth: "required" });
  } catch (err) {
    if (err.status === 401) clearSession();
    else throw err;
  }
  notify();
  return me;
}

export async function login(email, password) {
  const t = await post("/auth/login", { email, password }, { auth: "none" });
  save(t);
  return loadMe();
}

export async function signup(email, password, nickname, consent) {
  await post("/auth/signup", { email, password, nickname, ...consent }, { auth: "none" });
  return login(email, password);
}

export async function logout(everywhere = false) {
  try {
    if (everywhere) await post("/auth/logout-all", undefined, { auth: "required", retry: false });
    else await post("/auth/logout", { refresh_token: tokens?.refresh_token }, { auth: "required", retry: false });
  } catch {
    /* token already invalid: logging out locally is all that's left */
  }
  clearSession();
}

/** Drop the local session without calling the server (e.g. after 회원 탈퇴 revoked every token). */
export function forgetSession() {
  clearSession();
}

// Another tab logged in/out: follow it.
window.addEventListener("storage", (e) => {
  if (e.key !== KEY) return;
  tokens = load();
  loadMe().catch(() => {});
});
