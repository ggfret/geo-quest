// Shared play loop for the quizzes: ask → answer (typed or multiple choice) → explain → next.
// Uses the helpers in common.js ($, esc, api, celebrate).
const slug = $("play").dataset.game;

let current = null;   // { item_id, prompt } being asked now
let upcoming = null;  // next question, fetched early so "Next" is instant
let session = { right: 0, total: 0 };

async function fetchQuestion() {
  const question = await api(`/api/${slug}/next`);
  if (question.prompt.image) new Image().src = question.prompt.image; // preload
  return question;
}

function renderPrompt(prompt) {
  const box = $("prompt");
  box.innerHTML = "";
  if (prompt.image) {
    const img = document.createElement("img");
    img.src = prompt.image;
    img.alt = prompt.text ? `Flag of ${prompt.text}` : "Flag to guess";
    img.className = prompt.small ? "flag small" : "flag";
    box.append(img);
  }
  if (prompt.shape) {
    const { path, w, h } = prompt.shape;
    const pad = Math.max(w, h) * 0.03;
    box.innerHTML = `<svg class="shape" viewBox="${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}" role="img" aria-label="Country outline to guess"><path d="${path}"/></svg>`;
  }
  if (prompt.bars) {
    const list = document.createElement("div");
    list.className = "bars";
    const max = Math.max(...prompt.bars.map((b) => b.pct));
    for (const b of prompt.bars) {
      const row = document.createElement("div");
      row.className = "bar-row" + (b.hidden ? " hidden-name" : "");
      row.innerHTML = `<span class="bar-label"></span><span class="bar-track"><span class="bar-fill" style="width:${(b.pct / max) * 100}%"></span></span><span class="bar-pct">${b.pct}%</span>`;
      row.querySelector(".bar-label").textContent = b.label;
      list.append(row);
    }
    box.append(list);
  }
  if (prompt.sentence) {
    const p = document.createElement("div");
    p.className = "sentence";
    p.dir = "auto"; // right-to-left for Arabic, Hebrew, ...
    p.textContent = prompt.sentence;
    box.append(p);
  }
  if (prompt.text) {
    const h = document.createElement("div");
    h.className = "prompt-text";
    h.textContent = prompt.text;
    box.append(h);
  }
}

async function ask() {
  current = upcoming || (await fetchQuestion());
  upcoming = null;
  renderPrompt(current.prompt);
  feedbackContext = { game: slug, question: current.item_id, ...(current.prompt.context !== undefined && { sentence: current.prompt.context }) };
  $("reveal").hidden = true;
  const choices = current.prompt.choices;
  $("answer-form").hidden = !!choices;
  $("choices").hidden = !choices;
  if (choices) {
    $("choices").innerHTML = "";
    choices.forEach((name, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "choice";
      b.innerHTML = `<kbd>${i + 1}</kbd> ${esc(name)}`;
      b.dataset.name = name;
      b.addEventListener("click", () => submit(false, name));
      $("choices").append(b);
    });
  } else {
    $("guess").value = "";
    $("guess").focus();
  }
}

let answering = false;
async function submit(skip = false, choice = null) {
  const guess = choice ?? $("guess").value.trim();
  if ((!skip && !guess) || answering) return;
  answering = true;
  $("answer-form").hidden = true;
  document.querySelectorAll(".choice").forEach((b) => (b.disabled = true));

  const r = await api(`/api/${slug}/answer`, { item_id: current.item_id, guess, skip, context: current.prompt.context });
  answering = false;
  showResult(r, guess);
  celebrate(r);
  fetchQuestion().then((q) => (upcoming = q));
}

function showResult(r, guess) {
  session.total += 1;
  if (r.correct) session.right += 1;
  $("session").textContent = `${session.right} / ${session.total}`;
  $("streak-count").textContent = r.streak;

  const verdict = $("verdict");
  verdict.className = "verdict " + (r.correct ? "good" : "bad");
  if (r.correct) {
    verdict.innerHTML = `✓ ${esc(r.answer)} <span class="xp-pop">+${r.xp} XP</span>`;
    if (r.typo) verdict.innerHTML += `<small>Close enough. It's spelled <b>${esc(r.answer)}</b>.</small>`;
  } else if (r.skipped) {
    verdict.innerHTML = `It was <b>${esc(r.answer)}</b>`;
  } else {
    const yours = r.guessed ? `You said ${esc(r.guessed)}.` : `You typed “${esc(guess)}”.`;
    verdict.innerHTML = `✗ It was <b>${esc(r.answer)}</b><small>${yours}</small>`;
  }

  document.querySelectorAll(".choice").forEach((b) => {
    if (b.dataset.name === r.answer) b.classList.add("right");
    else if (b.dataset.name === guess) b.classList.add("wrong");
  });

  $("tip").hidden = !r.tip;
  $("tip").className = "tip" + (r.tip_is_mixup ? " mixup" : "");
  $("tip").textContent = r.tip || "";
  if (r.bars) renderPrompt({ bars: r.bars }); // reveal the hidden group names
  showLocator(r.locator, r.guessed_locator);
  $("fact").textContent = r.fact || "";
  $("info").textContent = r.info || "";
  $("reveal").hidden = false;
  $("next").focus();
}

// Mini world map, zoomed to the answer (and to your wrong guess, if you named another country).
const LOCATOR_NS = "http://www.w3.org/2000/svg";
const worldMap = fetch("/static/world.svg").then((r) => r.text());

async function showLocator(places, guessed = []) {
  const box = $("locator");
  box.hidden = !places.length;
  if (!places.length) return;
  box.innerHTML = await worldMap;
  const svg = box.querySelector("svg");
  const [, , mapW, mapH] = svg.getAttribute("viewBox").split(" ").map(Number);

  const add = (tag, attrs) => {
    const el = document.createElementNS(LOCATOR_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.append(el);
  };
  // Zoom: fit the answer (and guess), with plenty of surroundings for context.
  const boxes = [...places, ...guessed].map((p) => p.box);
  const x0 = Math.min(...boxes.map((b) => b[0])), y0 = Math.min(...boxes.map((b) => b[1]));
  const x1 = Math.max(...boxes.map((b) => b[2])), y1 = Math.max(...boxes.map((b) => b[3]));
  const viewW = Math.min(mapW, Math.max(120, (x1 - x0) * 2.2, (y1 - y0) * 2.2 * 1.8));
  const viewH = Math.min(mapH, viewW / 1.8);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const vx = clamp((x0 + x1) / 2 - viewW / 2, 0, mapW - viewW);
  const vy = clamp((y0 + y1) / 2 - viewH / 2, 0, mapH - viewH);
  svg.setAttribute("viewBox", `${vx} ${vy} ${viewW} ${viewH}`);

  for (const [list, cls] of [[guessed, "loc-guess"], [places, "loc-answer"]]) {
    for (const p of list) {
      if (p.path) add("path", { d: p.path, class: cls });
      const tiny = p.box[2] - p.box[0] < viewW * 0.04 && p.box[3] - p.box[1] < viewW * 0.04;
      if (tiny) add("circle", { cx: p.cx, cy: p.cy, r: viewW * 0.025, class: cls + " ring" });
    }
  }
}

$("answer-form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
$("skip").addEventListener("click", () => submit(true));
$("next").addEventListener("click", ask);
document.addEventListener("keydown", (e) => {
  if (e.target.closest("dialog")) return;  // typing in the feedback box
  const n = Number(e.key);
  const buttons = document.querySelectorAll(".choice:not(:disabled)");
  if (n >= 1 && n <= buttons.length) buttons[n - 1].click();
});

ask();
