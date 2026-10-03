// 📍 Pin it: click the country you think it is (it lights up), confirm, and see how close you were.
const map = new WorldMap($("map"), { zoomable: true, label: "World map: click the country" });
const session = { right: 0, total: 0 };
let current = null;   // { item_id, name, flag }
let picked = null;    // the country you've selected
let point = null;     // where you clicked, in map coordinates
let answered = false;
const HELP = $("map-help").textContent;

async function next() {
  current = await api("/api/pin/next");
  answered = false;
  picked = point = null;
  map.clear();
  map.reset();
  $("prompt-name").textContent = current.name;
  feedbackContext = { game: "pin", question: current.item_id };
  $("prompt-flag").src = current.flag;
  $("prompt-flag").alt = `Flag of ${current.name}`;
  $("prompt-flag").hidden = false;
  $("confirm").disabled = true;
  $("ask").hidden = false;
  $("banner").hidden = true;
  $("reveal").hidden = true;
  $("map-help").textContent = HELP;
}

// Select the country you clicked (no name: that would give it away). Click another to change your mind.
map.onPick = (p) => {
  if (answered || !current) return;
  const id = map.countryAt(p);
  if (!id) {
    $("map-help").textContent = "That's the sea: click on a country. Tiny ones: zoom in, or click just next to them.";
    return;
  }
  $("map-help").textContent = HELP;
  map.unmark("picked");
  map.mark(id, "picked");
  picked = id;
  point = p;
  $("confirm").disabled = false;
  $("confirm").focus({ preventScroll: true });
};

async function confirmPin() {
  if (!picked || answered) return;
  answered = true;
  $("confirm").disabled = true;
  const r = await api("/api/pin/answer", { item_id: current.item_id, pick: picked, x: point.x, y: point.y });
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
  map.unmark("picked");
  map.mark(target.id, "hit");
  const boxes = [target.box];
  if (!r.correct) {
    map.mark(r.picked_place.id, "miss");
    const [x0, y0, x1, y1] = r.picked_place.box;
    const shift = map.closestCopy((x0 + x1) / 2, cx) - (x0 + x1) / 2;
    boxes.push([x0 + shift, y0, x1 + shift, y1]);
    if (r.line) {
      const [ax, ay, bx, by] = r.line;
      const lineX = map.closestCopy(ax, cx);
      map.line(lineX, ay, map.closestCopy(bx, lineX), by);
    }
  }
  map.fit(boxes, { pad: 1.2, minW: 150, animate: true });

  const verdict = $("verdict");
  verdict.className = "verdict " + (r.correct ? "good" : "bad");
  if (r.correct) {
    verdict.innerHTML = `✓ ${esc(r.answer)}<small>Right on target!</small>`;
  } else {
    const how = r.neighbour ? "right next door" : `${r.distance_km.toLocaleString()} km away`;
    verdict.innerHTML = `✗ That's ${esc(r.picked)}<small>${how}. ${esc(r.answer)} is in green.</small>`;
  }
  $("banner").className = "map-banner " + (r.correct ? "good" : "bad");
  $("banner").hidden = false;
  setTimeout(() => floatXp(r.xp, [point.x, point.y]), 520);  // once the map has glided to the answer

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
  if (e.target.closest("dialog")) return;  // typing in the feedback box
  if (e.key !== "Enter") return;
  if (!answered && point) confirmPin();
  else if (answered && document.activeElement !== $("next")) next();
});

map.load().then(next);
