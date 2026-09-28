// My Knowledge page: XP chart, mastery map per game, language chips, accuracy-by-continent table.
const data = JSON.parse($("stats").textContent);
const LEVELS = ["Struggling", "Shaky", "Learning", "Getting there", "Known", "Mastered"];
const gameName = (slug) => data.game_names[data.game_slugs.indexOf(slug)] || slug;

function describe(game, id) {
  const m = (data.mastery[game] || {})[id];
  if (!data.pools[game].includes(id)) return "Not part of this game";
  if (!m) return "Not seen yet";
  const [box, seen, correct, due] = m;
  return `${LEVELS[box]} · ${correct} of ${seen} right${due ? " · due for review" : ""}`;
}

// ---------- XP per day ----------
function drawChart() {
  const days = data.daily;
  const W = 600, H = 170, left = 30, bottom = 22, top = 8;
  const max = Math.max(data.goal * 1.25, ...days.map((d) => d.xp));
  const y = (v) => H - bottom - (v / max) * (H - bottom - top);
  const slot = (W - left) / days.length;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Bar chart of XP earned per day over the last 30 days" });

  for (const v of [0, Math.round(max / 2), Math.round(max)]) {
    svg.append(svgEl("line", { x1: left, x2: W, y1: y(v), y2: y(v), class: "grid" }));
    const label = svgEl("text", { x: left - 6, y: y(v) + 4, class: "axis", "text-anchor": "end" });
    label.textContent = v;
    svg.append(label);
  }
  days.forEach((d, i) => {
    const x = left + i * slot + 1;
    const g = svgEl("g", { class: "day" });
    g.append(svgEl("rect", { x: x - 1, y: top, width: slot, height: H - bottom - top, class: "hit-area" }));
    if (d.xp > 0) {
      g.append(svgEl("rect", { x, y: y(d.xp), width: slot - 2, height: H - bottom - y(d.xp), rx: 2, class: "bar-xp" }));
    }
    const title = svgEl("title");
    title.textContent = `${new Date(d.date + "T00:00:00Z").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}: ${d.xp} XP`;
    g.append(title);
    svg.append(g);
    if (i % 7 === days.length % 7 || i === days.length - 1) {
      const last = i === days.length - 1;
      const label = svgEl("text", { x: last ? W : x + slot / 2 - 1, y: H - 6, class: "axis", "text-anchor": last ? "end" : "middle" });
      label.textContent = last ? "Today" : new Date(d.date + "T00:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
      svg.append(label);
    }
  });
  svg.append(svgEl("line", { x1: left, x2: W, y1: y(data.goal), y2: y(data.goal), class: "goal-line" }));
  $("xp-chart").append(svg);
}

// ---------- Mastery map ----------
const map = new WorldMap($("k-map"), { label: "World map coloured by how well you know each country" });
const mapReady = map.load().then(() => {
  const tip = $("tooltip");
  map.svg.addEventListener("mousemove", (e) => {
    const id = e.target.dataset?.id;
    if (!id || !current || current === "languages") return (tip.hidden = true);
    tip.hidden = false;
    tip.innerHTML = "<b></b><span></span>";
    tip.querySelector("b").textContent = data.names[id] || id;
    tip.querySelector("span").textContent = describe(current, id);
    const r = $("k-map").getBoundingClientRect();
    tip.style.left = `${Math.min(e.clientX - r.left + 12, r.width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${e.clientY - r.top + 16}px`;
  });
  map.svg.addEventListener("mouseleave", () => (tip.hidden = true));
});
let current = null;

async function drawMap(game) {
  await mapReady;
  const mastery = data.mastery[game] || {};
  const pool = new Set(data.pools[game]);
  for (const [id, path] of Object.entries(map.paths)) {
    const m = mastery[id];
    const cls = m ? `m${m[0]}` : pool.has(id) ? "unseen" : "outside";
    path.setAttribute("class", `country ${cls}${m && m[3] ? " due" : ""}`);
  }
}

function drawLanguages() {
  const box = $("k-langs");
  box.innerHTML = "";
  const mastery = data.mastery.languages || {};
  for (const [group, langs] of Object.entries(data.lang_groups)) {
    const row = document.createElement("div");
    row.className = "k-lang-group";
    row.innerHTML = `<h3></h3><div class="chips"></div>`;
    row.querySelector("h3").textContent = group;
    for (const lang of langs) {
      const chip = document.createElement("span");
      const m = mastery[lang];
      chip.className = "chip " + (m ? `m${m[0]}` : "unseen") + (m && m[3] ? " due" : "");
      chip.textContent = lang;
      chip.title = describe("languages", lang);
      row.querySelector(".chips").append(chip);
    }
    box.append(row);
  }
}

function showGame(game) {
  current = game;
  document.querySelectorAll("#map-tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.game === game));
  const isLang = game === "languages";
  $("k-map").hidden = isLang;
  $("k-langs").hidden = !isLang;
  if (isLang) drawLanguages();
  else drawMap(game);
  try { localStorage.setItem("knowledge-tab", game); } catch {}
}

document.querySelectorAll("#map-tabs button").forEach((b) => b.addEventListener("click", () => showGame(b.dataset.game)));

// ---------- Accuracy by continent ----------
function drawTable() {
  const table = $("k-table");
  const games = data.country_games.filter((g) => data.areas.some((a) => a.game === g));
  const byKey = {};
  for (const a of data.areas) byKey[`${a.game}|${a.region}`] = a;
  const regions = [...new Set(data.areas.filter((a) => games.includes(a.game)).map((a) => a.region))].sort();
  const heads = ["", ...games.map(gameName)];
  table.innerHTML = `<thead><tr>${heads.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const region of regions) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th scope="row"></th>`;
    tr.querySelector("th").textContent = region;
    for (const game of games) {
      const a = byKey[`${game}|${region}`];
      const td = document.createElement("td");
      if (a && a.answered >= 5) {
        const pct = Math.round(a.accuracy * 100);
        td.innerHTML = `<span class="cell-num">${pct}%</span><span class="cell-bar"><span style="width:${pct}%"></span></span>`;
        td.title = `${a.answered} answers`;
      } else {
        td.innerHTML = `<span class="muted">—</span>`;
        if (a) td.title = `Only ${a.answered} answer${a.answered === 1 ? "" : "s"} so far`;
      }
      tr.append(td);
    }
    body.append(tr);
  }
  if (!regions.length) body.innerHTML = `<tr><td class="muted">Play a country game to fill this in.</td></tr>`;
  table.append(body);
}

drawChart();
drawTable();
let start = "flags";
try { start = localStorage.getItem("knowledge-tab") || start; } catch {}
showGame(data.pools[start] ? start : "flags");
