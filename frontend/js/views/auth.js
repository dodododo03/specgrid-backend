import * as api from "../api.js";
import { icon } from "../icons.js";
import { toast } from "../ui.js";
import { navigate } from "../app.js";
import { section } from "./common.js";

// Only follow in-app paths ("/sell"), never another site ("//evil.com" or "https://...").
function safeNext(next) {
  return typeof next === "string" && /^\/(?!\/)[\w\-/?=&%.]*$/.test(next) ? next : "/";
}

function shell(title, eyebrow, body, foot) {
  const el = section("page-wrap workspace auth-page");
  el.innerHTML = `
    <div class="auth-card panel">
      <div class="auth-brand"><span class="brand-mark"><i></i><i></i><i></i><i></i></span></div>
      <p class="eyebrow">${eyebrow}</p>
      <h1>${title}</h1>
      ${body}
      <p class="auth-foot muted">${foot}</p>
    </div>`;
  return el;
}

function setError(el, msg) {
  const box = el.querySelector("[data-error]");
  box.textContent = msg || "";
  box.hidden = !msg;
}

export function renderLogin({ query }) {
  const next = safeNext(query.next);
  if (api.isLoggedIn()) {
    setTimeout(() => navigate(next));
  }
  const el = shell(
    "다시 오신 걸 환영해요",
    "SIGN IN",
    `<form class="form-stack" novalidate>
      <label class="field"><span>이메일</span><input name="email" type="email" autocomplete="email" required placeholder="you@example.com"></label>
      <label class="field"><span>비밀번호</span><input name="password" type="password" autocomplete="current-password" required placeholder="비밀번호"></label>
      <p class="form-error" data-error role="alert" hidden></p>
      <button class="btn full" type="submit">로그인 ${icon("arrowRight", 16)}</button>
    </form>`,
    `아직 계정이 없나요? <a class="link" href="#/signup?next=${encodeURIComponent(next)}">회원가입</a>`,
  );
  const form = el.querySelector("form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!email || !password) return setError(el, "이메일과 비밀번호를 입력해 주세요.");
    const btn = form.querySelector("button");
    btn.disabled = true;
    setError(el, "");
    try {
      const me = await api.login(email, password);
      toast(`${me?.nickname || ""}님, 반가워요!`, "success");
      navigate(next);
    } catch (err) {
      // 429 = too many failures (account locked for a while), 401 = wrong email/password
      setError(el, err.message);
      form.password.select();
    } finally {
      if (btn.isConnected) btn.disabled = false;
    }
  });
  setTimeout(() => form.email.focus());
  return { el };
}

const NICK_RE = /^[가-힣A-Za-z0-9_]+$/;

export function renderSignup({ query }) {
  const next = safeNext(query.next);
  const el = shell(
    "스펙그리드 시작하기",
    "CREATE ACCOUNT",
    `<form class="form-stack" novalidate>
      <label class="field"><span>이메일</span><input name="email" type="email" autocomplete="email" required placeholder="you@example.com"></label>
      <label class="field"><span>닉네임 <em class="muted">2~30자, 한글·영문·숫자·_</em></span><input name="nickname" autocomplete="nickname" required minlength="2" maxlength="30" placeholder="예: 그래픽카드장인"></label>
      <label class="field"><span>비밀번호 <em class="muted">8자 이상, 영문+숫자</em></span><input name="password" type="password" autocomplete="new-password" required minlength="8" maxlength="128"></label>
      <label class="field"><span>비밀번호 확인</span><input name="password2" type="password" autocomplete="new-password" required></label>
      <ul class="pw-rules" data-rules>
        <li data-rule="len">8자 이상</li><li data-rule="alpha">영문 포함</li><li data-rule="digit">숫자 포함</li><li data-rule="same">확인과 일치</li>
      </ul>
      <p class="form-error" data-error role="alert" hidden></p>
      <button class="btn full" type="submit">가입하고 시작하기 ${icon("arrowRight", 16)}</button>
    </form>`,
    `이미 계정이 있나요? <a class="link" href="#/login?next=${encodeURIComponent(next)}">로그인</a>`,
  );
  const form = el.querySelector("form");
  function rules() {
    const pw = form.password.value;
    const r = {
      len: pw.length >= 8,
      alpha: /[A-Za-z]/.test(pw),
      digit: /\d/.test(pw),
      same: pw.length > 0 && pw === form.password2.value,
    };
    for (const [k, ok] of Object.entries(r)) el.querySelector(`[data-rule="${k}"]`).classList.toggle("ok", ok);
    return r;
  }
  form.addEventListener("input", rules);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = form.email.value.trim();
    const nickname = form.nickname.value.trim();
    const r = rules();
    let problem = "";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) problem = "올바른 이메일을 입력해 주세요.";
    else if (nickname.length < 2 || nickname.length > 30) problem = "닉네임은 2~30자로 입력해 주세요.";
    else if (!NICK_RE.test(nickname)) problem = "닉네임은 한글, 영문, 숫자, _만 쓸 수 있어요.";
    else if (!r.len || !r.alpha || !r.digit) problem = "비밀번호는 8자 이상, 영문과 숫자를 모두 포함해야 해요.";
    else if (!r.same) problem = "비밀번호 확인이 일치하지 않아요.";
    if (problem) return setError(el, problem);
    const btn = form.querySelector("button");
    btn.disabled = true;
    setError(el, "");
    try {
      await api.signup(email, form.password.value, nickname);
      toast(`가입 완료! ${nickname}님, 환영해요.`, "success");
      navigate(next);
    } catch (err) {
      setError(el, err.message); // e.g. 409 "이미 사용 중인 이메일입니다."
    } finally {
      if (btn.isConnected) btn.disabled = false;
    }
  });
  setTimeout(() => form.email.focus());
  return { el };
}
