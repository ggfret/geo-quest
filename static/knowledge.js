// My Knowledge page: mastery map per game, language chips, accuracy-by-continent table.
const $ = (id) => document.getElementById(id);
const data = JSON.parse($("stats").textContent);
const LEVELS = ["Struggling", "Shaky", "Learning", "Getting there", "Known", "Mastered"];
const SVG_NS = "http://www.w3.org/2000/svg";
const COUNTRY_GAMES = ["flags", "capitals", "outlines", "ethnicities"];

const mapData = fetch("/api/map").then((r) => r.json());

function describe(game, id) {
  const m = (data.mastery[game] || {})[id];
  if (!data.pools[game].includes(id)) return "Not part of this game";
  if (!m) return "Not seen yet";
  const [box, seen, correct] = m;
  return `${LEVELS[box]} · ${correct} of ${seen} right`;
}

// ---------- Map ----------
async function drawMap(game) {
  const { width, height, paths } = await mapData;
  const box = $("k-map");
  box.querySelector("svg")?.remove();
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `World map coloured by how well you know each country in ${game}`);
  const mastery = data.mastery[game] || {};
  for (const [id, d] of Object.entries(paths)) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    const m = mastery[id];
    path.setAttribute("class", m ? `m${m[0]}` : data.pools[game].includes(id) ? "unseen" : "outside");
    path.dataset.id = id;
    svg.append(path);
  }
  box.prepend(svg);

  const tip = $("tooltip");
  svg.addEventListener("mousemove", (e) => {
    const id = e.target.dataset?.id;
    if (!id) return (tip.hidden = true);
    tip.hidden = false;
    tip.innerHTML = `<b></b><span></span>`;
    tip.querySelector("b").textContent = data.names[id] || id;
    tip.querySelector("span").textContent = describe(game, id);
    const r = box.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    tip.style.left = `${Math.min(x + 12, r.width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${y + 16}px`;
  });
  svg.addEventListener("mouseleave", () => (tip.hidden = true));
}

// ---------- Languages (not on a map: chips grouped by writing system) ----------
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
      chip.className = "chip " + (m ? `m${m[0]}` : "unseen");
      chip.textContent = lang;
      chip.title = describe("languages", lang);
      row.querySelector(".chips").append(chip);
    }
    box.append(row);
  }
}

function showGame(game) {
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
  const byKey = {};
  for (const a of data.areas) byKey[`${a.game}|${a.region}`] = a;
  const regions = [...new Set(data.areas.filter((a) => COUNTRY_GAMES.includes(a.game)).map((a) => a.region))].sort();
  const heads = ["", ...COUNTRY_GAMES.map((g) => g[0].toUpperCase() + g.slice(1))];
  table.innerHTML = `<thead><tr>${heads.map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const region of regions) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th scope="row"></th>`;
    tr.querySelector("th").textContent = region;
    for (const game of COUNTRY_GAMES) {
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

drawTable();
let start = "flags";
try { start = localStorage.getItem("knowledge-tab") || start; } catch {}
showGame(data.pools[start] ? start : "flags");
