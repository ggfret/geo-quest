// 🔥 Hot & Cold: guess the mystery country; distance, direction and colour guide you.
const map = new WorldMap($("map"), { zoomable: true, label: "World map with your guesses coloured by how close they are" });
const HEAT = [[500, "heat4"], [1500, "heat3"], [3000, "heat2"], [6000, "heat1"], [Infinity, "heat0"]];
const heat = (km) => HEAT.find(([max]) => km < max)[1];
let run = null;
let finished = false;
const INTRO = $("message").textContent;

// Show the region around a guess: close enough to see the neighbours, far enough to keep your bearings.
function focusOn(g, animate) {
  map.fit([map.box(g.id)], { pad: 3, minW: 280, animate });
}

async function start(fresh = false) {
  const r = await api("/api/hotcold/start", { new: fresh });
  run = r.run_id;
  finished = false;
  map.clear();
  render(r.guesses);
  if (r.guesses.length) focusOn(r.guesses[r.guesses.length - 1], false);
  else map.reset();
  $("message").textContent = r.guesses.length ? "Welcome back! Carry on where you left off." : INTRO;
  $("guess-form").hidden = false;
  $("reveal").hidden = true;
  $("guess").focus({ preventScroll: true });
}

function render(guesses) {
  for (const [, cls] of HEAT) map.unmark(cls);
  for (const g of guesses) map.mark(g.id, heat(g.km));
  $("count").textContent = guesses.length;
  const list = $("guesses");
  list.innerHTML = "";
  for (const g of [...guesses].sort((a, b) => a.km - b.km)) {
    const li = document.createElement("li");
    li.className = heat(g.km);
    li.innerHTML = `
      <span class="g-name"></span>
      <span class="g-km">${g.km.toLocaleString()} km</span>
      <span class="g-arrow" title="Direction from your guess to the mystery country">${g.arrow}</span>
      <span class="g-prox" title="${g.proximity}% of the way there"><span style="width:${g.proximity}%"></span></span>
      ${g.neighbour ? '<span class="badge hot">Neighbour!</span>' : ""}`;
    li.querySelector(".g-name").textContent = g.name;
    list.append(li);
  }
}

// A round can end on the server while the page still shows it (e.g. in another tab): say so and move on.
async function send(url, body) {
  try {
    return await api(url, body);
  } catch (e) {
    if (e.status !== 409) throw e;
    finished = true;
    $("message").textContent = "That round has already ended.";
    $("verdict").textContent = "";
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
  const r = await send("/api/hotcold/guess", { run_id: run, guess: text });
  if (!r) return;
  const msg = $("message");
  if (r.status === "unknown") msg.textContent = `“${text}” isn't a country I know.`;
  else if (r.status === "repeat") msg.textContent = `You already guessed ${r.name}.`;
  else if (r.status === "guess") {
    const last = r.guesses[r.guesses.length - 1];
    render(r.guesses);
    focusOn(last, true);
    msg.textContent = `${last.name}: ${last.km.toLocaleString()} km away, go ${last.arrow}${last.neighbour ? " (it's a neighbour!)" : ""}`;
  } else if (r.status === "solved") end(r, true);
  if (!finished) $("guess").focus({ preventScroll: true });
}

async function giveUp() {
  if (finished || !run) return;
  const r = await send("/api/hotcold/give-up", { run_id: run });
  if (r) end(r, false);
}

function end(r, won) {
  finished = true;
  render(r.guesses);
  $("count").textContent = r.guesses_used;  // including the winning guess
  map.mark(r.target.id, "hit");
  map.fit([r.target.box], { pad: 3, minW: 280, animate: true });
  const verdict = $("verdict");
  verdict.className = "verdict " + (won ? "good" : "bad");
  verdict.innerHTML = won
    ? `✓ It's ${esc(r.answer)}! <span class="xp-pop">+${r.xp} XP</span><small>Found in ${r.guesses_used} guess${r.guesses_used === 1 ? "" : "es"}.</small>`
    : `It was <b>${esc(r.answer)}</b>.`;
  $("message").textContent = "";
  $("fact").textContent = r.fact || "";
  $("info").textContent = r.info || "";
  $("guess-form").hidden = true;
  $("reveal").hidden = false;
  $("again").focus();
  celebrate(r);
}

$("guess-form").addEventListener("submit", guess);
$("give-up").addEventListener("click", giveUp);
$("again").addEventListener("click", () => start(true));

map.load().then(() => start());
