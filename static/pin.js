// 📍 Pin it: drop a pin where you think the country is, then see how close you were.
const map = new WorldMap($("map"), { zoomable: true, label: "World map: click where the country is" });
const session = { right: 0, total: 0 };
let current = null;   // { item_id, name, flag }
let point = null;     // where the pin is, in map coordinates
let pinEl = null;
let answered = false;

async function next() {
  current = await api("/api/pin/next");
  answered = false;
  point = null;
  pinEl = null;
  map.clear();
  map.reset();
  $("prompt-name").textContent = current.name;
  $("prompt-flag").src = current.flag;
  $("prompt-flag").alt = `Flag of ${current.name}`;
  $("prompt-flag").hidden = false;
  $("confirm").disabled = true;
  $("ask").hidden = false;
  $("banner").hidden = true;
  $("reveal").hidden = true;
}

map.onPick = (p) => {
  if (answered || !current) return;
  map.remove(pinEl);
  pinEl = map.pin(p.x, p.y, "pin");
  point = p;
  $("confirm").disabled = false;
  $("confirm").focus({ preventScroll: true });
};

async function confirmPin() {
  if (!point || answered) return;
  answered = true;
  $("confirm").disabled = true;
  const r = await api("/api/pin/answer", { item_id: current.item_id, x: point.x, y: point.y });
  show(r);
  celebrate(r);
}

function show(r) {
  session.total += 1;
  if (r.correct) session.right += 1;
  $("session").textContent = `${session.right} / ${session.total}`;
  $("streak-count").textContent = r.streak;

  // Draw on the copy of the world nearest to the answer, so a line never goes the long way round.
  const target = r.target;
  const cx = (target.box[0] + target.box[2]) / 2;
  const clickX = map.closestCopy(r.click[0], cx);
  map.mark(target.id, "hit");
  if (r.clicked_place) map.mark(r.clicked_place.id, "miss");
  if (!r.correct) map.line(clickX, r.click[1], map.closestCopy(r.nearest[0], clickX), r.nearest[1]);
  map.fit([target.box, [clickX, r.click[1], clickX, r.click[1]]], { pad: 2.5, minW: 150, animate: true });

  const km = r.distance_km.toLocaleString();
  const verdict = $("verdict");
  verdict.className = "verdict " + (r.correct ? "good" : "bad");
  if (r.correct) {
    const how = r.distance_km === 0 ? "Right on target!" : `Close enough: ${km} km from its border.`;
    verdict.innerHTML = `✓ ${esc(r.answer)}<small>${how}</small>`;
  } else {
    const where = r.clicked ? `You pinned ${esc(r.clicked)}.` : "Your pin landed in the sea.";
    verdict.innerHTML = `✗ ${km} km off<small>${where} ${esc(r.answer)} is in green.</small>`;
  }
  $("banner").className = "map-banner " + (r.correct ? "good" : "bad");
  $("banner").hidden = false;
  setTimeout(() => floatXp(r.xp, r.click), 520);  // once the map has glided to the answer

  $("fact").textContent = r.fact || "";
  $("info").textContent = r.info || "";
  $("ask").hidden = true;
  $("reveal").hidden = false;
  $("next").focus({ preventScroll: true });
}

// "+14 XP" rising from the pin, or a short miss note when there's no XP.
function floatXp(xp, [x, y]) {
  const el = document.createElement("div");
  el.className = "xp-float" + (xp ? "" : " none");
  el.textContent = xp ? `+${xp} XP` : "+0 XP";
  const pos = map.toScreen(x, y);
  el.style.left = `${pos.left}px`;
  el.style.top = `${pos.top}px`;
  $("map").append(el);
  setTimeout(() => el.remove(), 1600);
}

$("confirm").addEventListener("click", confirmPin);
$("next").addEventListener("click", next);
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (!answered && point) confirmPin();
  else if (answered && document.activeElement !== $("next")) next();
});

map.load().then(next);
