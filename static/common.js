// Helpers shared by every page: shortcuts, talking to the server, the header, and pop-up messages.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// Simplify a typed name exactly like answers.normalize() on the server:
// "Côte d'Ivoire" -> "cote divoire", "St. Lucia" -> "saint lucia", "The Gambia" -> "gambia".
function normalize(text) {
  let s = text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  s = s.replace(/&/g, " and ").replace(/['’]/g, "").replace(/[^a-z0-9]+/g, " ");
  let words = s.split(" ").filter(Boolean);
  if (words[0] === "the") words = words.slice(1);
  return words.map((w) => (w === "st" ? "saint" : w)).join(" ");
}

// GET (no body) or POST JSON. If the login has expired, go log in and come back.
async function api(url, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(url, options);
  if (res.status === 401) {
    location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    throw new Error("Not logged in");
  }
  if (!res.ok) {
    const error = new Error(`${url} failed (${res.status})`);
    error.status = res.status;  // 409 = that round is already over
    throw error;
  }
  return res.json();
}

// Anything that goes wrong without being handled: say so, instead of silently doing nothing.
window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.message !== "Not logged in") toast("Something went wrong. Try reloading the page.", "error");
});

const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

// ---------- Pop-up messages ----------
function toast(text, kind = "") {
  let box = $("toasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  box.append(el);
  setTimeout(() => el.remove(), kind === "badge" ? 5000 : 3000);
}

// ---------- Header: level, XP bar, day streak and daily goal ----------
const header = { level: null, title: null, today: null };

function updateHeader(me) {
  const box = $("xpbox");
  if (!me || !box) return;
  const set = (id, fn) => { const el = $(id); if (el) fn(el); };  // skip anything a page doesn't have
  set("lvl", (el) => (el.textContent = `Lv ${me.level}`));
  set("title", (el) => (el.textContent = me.title));
  set("xptext", (el) => (el.textContent = `${me.into} / ${me.need} XP`));
  set("xpbar", (el) => (el.style.width = `${(me.into / me.need) * 100}%`));
  set("streak-days", (el) => (el.textContent = me.streak));
  set("streak", (el) => el.classList.toggle("done", me.played_today));
  set("goal-text", (el) => (el.textContent = `${Math.min(me.today_xp, me.daily_goal)}/${me.daily_goal}`));
  set("goal-ring", (ring) => {
    const length = ring.getTotalLength ? ring.getTotalLength() : 56.5;
    ring.style.strokeDasharray = length;
    ring.style.strokeDashoffset = length * (1 - Math.min(1, me.today_xp / me.daily_goal));
  });
  set("goal", (el) => el.classList.toggle("done", me.today_xp >= me.daily_goal));

  if (header.level !== null && me.level > header.level) {
    toast(`⭐ Level ${me.level}!${me.title !== header.title ? ` You're now a ${me.title}.` : ""}`, "level");
  }
  if (header.today !== null && header.today < me.daily_goal && me.today_xp >= me.daily_goal) toast("✅ Daily goal reached!", "level");
  header.level = me.level;
  header.title = me.title;
  header.today = me.today_xp;
}

// Every game answer returns `me` (header numbers) and `unlocked` (new badges).
function celebrate(result) {
  updateHeader(result.me);
  for (const a of result.unlocked || []) toast(`${a.icon} Badge unlocked: ${a.name} · +${a.xp} XP`, "badge");
}

document.addEventListener("DOMContentLoaded", () => {
  const box = $("xpbox");
  if (box) updateHeader(JSON.parse(box.dataset.me));
});
