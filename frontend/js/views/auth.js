import * as api from "../api.js";
import { icon } from "../icons.js";
import { esc, toast } from "../ui.js";
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

// Password input with a show/hide (eye) button.
function passwordInput(name, autocomplete, attrs = "") {
  return `<div class="pw-wrap">
    <input id="f-${name}" name="${name}" type="password" autocomplete="${autocomplete}" ${attrs}>
    <button type="button" class="pw-toggle" data-pw-toggle="${name}" aria-label="비밀번호 보기" aria-pressed="false" title="비밀번호 보기">${icon("eye", 17)}</button>
  </div>`;
}

function bindPasswordToggles(el) {
  el.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-pw-toggle]");
    if (!btn) return;
    const input = el.querySelector(`input[name="${btn.dataset.pwToggle}"]`);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.innerHTML = icon(show ? "eyeOff" : "eye", 17);
    btn.setAttribute("aria-pressed", String(show));
    btn.setAttribute("aria-label", show ? "비밀번호 숨기기" : "비밀번호 보기");
    btn.title = btn.getAttribute("aria-label");
    const pos = input.value.length; // keep typing at the end
    input.focus();
    try {
      input.setSelectionRange(pos, pos);
    } catch {
      /* some input types don't support selection */
    }
  });
  // Hide any revealed password on submit so it isn't left on screen or saved as plain text.
  el.querySelector("form").addEventListener(
    "submit",
    () => {
      el.querySelectorAll("[data-pw-toggle]").forEach((b) => {
        if (el.querySelector(`input[name="${b.dataset.pwToggle}"]`).type === "text") b.click();
      });
    },
    true,
  );
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
      <div class="field"><label for="f-password">비밀번호</label>${passwordInput("password", "current-password", 'required placeholder="비밀번호"')}</div>
      <p class="form-error" data-error role="alert" hidden></p>
      <button class="btn full" type="submit">로그인 ${icon("arrowRight", 16)}</button>
    </form>`,
    `아직 계정이 없나요? <a class="link" href="#/signup?next=${encodeURIComponent(next)}">회원가입</a>`,
  );
  const form = el.querySelector("form");
  bindPasswordToggles(el);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!email || !password) return setError(el, "이메일과 비밀번호를 입력해 주세요.");
    const btn = form.querySelector('button[type="submit"]');
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
      <div class="field"><label for="f-email">이메일</label>
        <div class="check-row"><input id="f-email" name="email" type="email" autocomplete="email" required maxlength="255" placeholder="you@example.com" aria-describedby="hint-email">
          <button type="button" class="btn btn-secondary" data-check="email">중복 확인</button></div>
        <p class="field-hint" id="hint-email" data-hint="email" aria-live="polite"></p></div>
      <div class="field"><label for="f-nickname">닉네임 <em class="muted">2~30자, 한글·영문·숫자·_</em></label>
        <div class="check-row"><input id="f-nickname" name="nickname" autocomplete="nickname" required minlength="2" maxlength="30" placeholder="예: 그래픽카드장인" aria-describedby="hint-nickname">
          <button type="button" class="btn btn-secondary" data-check="nickname">중복 확인</button></div>
        <p class="field-hint" id="hint-nickname" data-hint="nickname" aria-live="polite"></p></div>
      <div class="field"><label for="f-password">비밀번호 <em class="muted">8자 이상, 영문+숫자</em></label>${passwordInput("password", "new-password", 'required minlength="8" maxlength="128"')}</div>
      <div class="field"><label for="f-password2">비밀번호 확인</label>${passwordInput("password2", "new-password", "required")}</div>
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
  bindPasswordToggles(el);

  // ---- 중복 확인 (email / nickname)
  // confirmed[field] = the exact value the server said is available; editing the field clears it.
  const confirmed = { email: null, nickname: null };
  const normalize = { email: (v) => v.trim().toLowerCase(), nickname: (v) => v.trim() };

  function showHint(field, ok, msg) {
    const hint = el.querySelector(`[data-hint="${field}"]`);
    hint.className = `field-hint ${ok === true ? "ok" : ok === false ? "bad" : ""}`;
    hint.innerHTML = msg ? `${ok === true ? icon("check", 12) : ""} ${esc(msg)}` : "";
  }

  async function checkField(field) {
    const value = normalize[field](form[field].value);
    if (!value) {
      showHint(field, false, field === "email" ? "이메일을 입력해 주세요." : "닉네임을 입력해 주세요.");
      return false;
    }
    if (confirmed[field] === value) return true;
    const btn = el.querySelector(`[data-check="${field}"]`);
    btn.disabled = true;
    showHint(field, null, "확인 중…");
    try {
      const r = await api.get("/auth/availability", { [field]: value }, { auth: "none" });
      if (normalize[field](form[field].value) !== value) return false; // edited while we waited
      confirmed[field] = r.available ? value : null;
      showHint(field, r.available, r.message);
      return r.available;
    } catch (err) {
      showHint(field, false, err.message);
      return false;
    } finally {
      if (btn.isConnected) btn.disabled = false;
    }
  }

  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-check]");
    if (b) checkField(b.dataset.check);
  });
  for (const field of ["email", "nickname"]) {
    form[field].addEventListener("input", () => {
      if (confirmed[field] !== normalize[field](form[field].value)) {
        confirmed[field] = null;
        showHint(field, null, "");
      }
    });
    // Check automatically when leaving the field (only if something was typed).
    form[field].addEventListener("blur", (e) => {
      // Focus moving to a button (submit, 중복 확인, eye): don't insert a hint line now — it would push
      // that button down mid-click so the click misses. Submit and 중복 확인 run the check themselves.
      if (e.relatedTarget?.closest?.("button")) return;
      if (form[field].value.trim() && confirmed[field] !== normalize[field](form[field].value)) checkField(field);
    });
  }

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
    const [emailOk, nickOk] = await Promise.all([checkField("email"), checkField("nickname")]);
    if (!emailOk || !nickOk) {
      setError(el, !emailOk ? "이메일 중복 확인을 통과하지 못했어요." : "닉네임 중복 확인을 통과하지 못했어요.");
      form[!emailOk ? "email" : "nickname"].focus();
      return;
    }
    const btn = form.querySelector('button[type="submit"]');
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
