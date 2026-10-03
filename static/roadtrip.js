// 🚗 Road trip: name the countries between two others. Green is on a shortest route, yellow a detour, red no use.
const map = new WorldMap($("map"), { zoomable: true, label: "Map of the trip and the countries you've named" });
const mapReady = map.load();
const MAP_CLASS = { green: "hit", yellow: "detour", red: "miss" };
const LOG_CLASS = { green: "", yellow: "detour", red: "bad" };
const SIGN = { green: "✓", yellow: "↝", red: "✗" };
let run = null;
let finished = false;

// Start a trip at a level, or (no level) pick up an unfinished one; with nothing to pick up, show the levels.
async function begin(level) {
  const r = await api("/api/roadtrip/start", level ? { level } : {});
  await mapReady;
  if (!r.run_id) {
    $("chooser").hidden = false;
    return;
  }
  run = r;
  finished = false;
  feedbackContext = { game: "roadtrip", round: r.run_id, trip: `${r.start.name} → ${r.end.name}`, level: r.level };
  $("chooser").hidden = true;
  $("board").hidden = false;
  map.measure();
  map.clear();
  render(r);
  map.fit([r.view], { pad: 0.5, minW: 120 });
  $("message").textContent = level ? "" : "Welcome back! Carry on where you left off.";
  $("message").className = "message";
  $("guess-form").hidden = false;
  $("reveal").hidden = true;
  $("guess").value = "";
  $("guess").focus({ preventScroll: true });
}

function render(r) {
  for (const end of ["start", "end"]) {
    $(`${end}-name`).textContent = r[end].name;
    $(`${end}-flag`).src = r[end].flag;
    $(`${end}-flag`).alt = `Flag of ${r[end].name}`;
  }
  $("level-label").textContent = r.level_name;
  const left = r.max_guesses - r.guesses.length;
  $("summary").innerHTML = `Shortest route: <b>${r.between}</b> countries in between · ` +
    `Guesses left: <b>${left}</b> of ${r.max_guesses}`;
  for (const cls of ["target", ...Object.values(MAP_CLASS)]) map.unmark(cls);
  map.mark(r.start.id, "target");
  map.mark(r.end.id, "target");
  for (const g of r.guesses) map.mark(g.id, MAP_CLASS[g.colour]);
  $("log").innerHTML = [...r.guesses].reverse()
    .map((g) => `<li class="${LOG_CLASS[g.colour]}">${esc(g.name)} <small>${esc(g.why)}</small></li>`)
    .join("");
}

// If a guess is off screen (Japan, say), widen the view so you can see where it is.
function showOnMap(id) {
  const b = map.box(id);
  if (!b) return;
  const { x, y, w, h } = map.view;
  const half = (b[2] - b[0]) / 2, cx = map.closestCopy(b[0] + half, x + w / 2);
  if (cx + half > x && cx - half < x + w && b[3] > y && b[1] < y + h) return;  // some of it is in view
  const shift = map.closestCopy((b[0] + b[2]) / 2, (run.view[0] + run.view[2]) / 2) - (b[0] + b[2]) / 2;
  map.fit([run.view, [b[0] + shift, b[1], b[2] + shift, b[3]]], { pad: 0.3, animate: true });
}

// A round can end on the server while the page still shows it (e.g. in another tab): say so and move on.
async function send(url, body) {
  try {
    return await api(url, body);
  } catch (e) {
    if (e.status !== 409) throw e;
    finished = true;
    $("message").textContent = "That trip has already ended.";
    $("verdict").textContent = "";
    $("routes").textContent = "";
    $("guess-form").hidden = true;
    $("reveal").hidden = false;
    $("again").focus();
    return null;
  }
}

async function guess(e) {
  e.preventDefault();
  const text = $("guess").value.trim();
  if (!text || finished) return;
  $("guess").value = "";
  const r = await send("/api/roadtrip/guess", { run_id: run.run_id, guess: text });
  if (!r) return;
  const v = r.verdict;
  const messages = {
    unknown: `“${esc(text)}” isn't a country I know.`,
    endpoint: `${esc(r.name)} is where the trip starts or ends: name the countries in between.`,
    repeat: `You already said ${esc(r.name)}.`,
    guess: v && `${SIGN[v.colour]} ${esc(v.name)}: ${esc(v.why)}${r.typo ? " (spelling forgiven)" : ""}`,
  };
  $("message").innerHTML = messages[r.status] || "";
  $("message").className = "message " + (v ? `says-${v.colour}` : "");
  render(r);
  if (v) showOnMap(v.id);
  if (r.finished) end(r);
  else $("guess").focus({ preventScroll: true });
}

async function giveUp() {
  if (finished || !run) return;
  const r = await send("/api/roadtrip/give-up", { run_id: run.run_id });
  if (!r) return;
  render(r);
  end(r);
}

function end(r) {
  finished = true;
  // The shortest routes you didn't take, in light green.
  const named = new Set(r.guesses.map((g) => g.id));
  for (const id of r.on_shortest) if (!named.has(id)) map.mark(id, "route");
  map.fit([r.route_view], { pad: 0.4, minW: 120, animate: true });

  const xp = r.xp ? ` <span class="xp-pop">+${r.xp} XP</span>` : "";
  const shortestYours = r.your_route && r.your_route.length === r.between;
  const verdict = $("verdict");
  verdict.className = "verdict " + (r.won ? "good" : "bad");
  if (r.perfect) verdict.innerHTML = `🎉 Perfect! The shortest route without a single wasted guess.${xp}`;
  else if (shortestYours) verdict.innerHTML = `✓ You found a shortest route in ${r.used} guesses.${xp}<small>The fewest possible is ${r.between}.</small>`;
  else if (r.won) verdict.innerHTML = `✓ You made it in ${r.used} guesses.${xp}<small>But there's a shorter way: ${r.between} countries in between instead of ${r.your_route.length}.</small>`;
  else verdict.innerHTML = `${r.status === "gave_up" ? "Trip abandoned." : "Out of guesses."}${xp}`;

  const chain = (route) => [run.start, ...route, run.end].map((c) => esc(c.name)).join(" → ");
  const others = r.other_routes ? ` There ${r.other_routes === 1 ? "is 1 other route" : `are ${r.other_routes} other routes`} as short.` : "";
  const unnamed = r.on_shortest.some((id) => !named.has(id)) ? "<br><small>Light green on the map: countries on a shortest route that you didn't name.</small>" : "";
  $("routes").innerHTML = (r.your_route ? `Your route: ${chain(r.your_route)}.<br>` : "") +
    (shortestYours ? others.trim() : `Shortest: ${chain(r.shortest_route)}.${others}`) + unnamed;
  $("message").textContent = "";
  $("guess-form").hidden = true;
  $("reveal").hidden = false;
  $("again").focus();
  celebrate(r);
}

$("guess-form").addEventListener("submit", guess);
$("give-up").addEventListener("click", giveUp);
$("again").addEventListener("click", () => begin(run.level));
$("choose").addEventListener("click", () => {
  $("board").hidden = true;
  $("chooser").hidden = false;
});
document.querySelectorAll("[data-level]").forEach((b) => b.addEventListener("click", () => begin(b.dataset.level)));

begin();
