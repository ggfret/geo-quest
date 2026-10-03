// ⏱️ Name them all: type every country of a region before the clock runs out.
const map = new WorldMap($("map"), { zoomable: true, label: "Map of the countries you've named" });
const mapReady = map.load();
let run = null;         // the round from the server: run_id, seconds, targets, view
let variant = null;
let lookup = new Map(); // simplified name -> country id
let found = [];         // ids, in the order you named them
let deadline = 0;
let ticker = null;

async function start(chosen) {
  variant = chosen;
  run = await api("/api/nameall/start", { variant });
  feedbackContext = { game: "nameall", round: run.run_id, region: variant };
  lookup = new Map();
  for (const t of run.targets) for (const n of t.names) lookup.set(n, t.id);
  found = [];
  await mapReady;
  $("chooser").hidden = true;
  $("result").hidden = true;
  $("game").hidden = false;
  $("board").hidden = false;
  map.measure();
  map.clear();
  if (run.view) map.fit([run.view], { pad: 0.08 });
  else map.reset();
  $("run-title").textContent = run.title;
  $("total").textContent = run.total;
  $("score").textContent = 0;
  $("found-list").innerHTML = "";
  $("message").textContent = "Go!";
  $("guess").value = "";
  $("guess").disabled = false;
  $("guess").focus();

  deadline = Date.now() + run.seconds * 1000;
  clearInterval(ticker);
  ticker = setInterval(tick, 250);
  tick();
}

function tick() {
  const left = Math.max(0, (deadline - Date.now()) / 1000);
  $("timer").textContent = formatTime(Math.ceil(left));
  $("timer").classList.toggle("low", left <= 30);
  if (left <= 0) finish();
}

function accept(id, typo = false) {
  if (found.includes(id)) return;
  found.push(id);
  const t = run.targets.find((t) => t.id === id);
  map.mark(id, "hit");
  $("score").textContent = found.length;
  $("found-list").insertAdjacentHTML("afterbegin", `<span class="chip good">${esc(t.name)}</span>`);
  $("message").textContent = `✓ ${t.name}${typo ? " (spelling forgiven)" : ""}`;
  $("guess").value = "";
  if (found.length === run.total) finish();
}

// Accept as soon as a name is complete, unless it's the start of another country still to find
// ("Niger" while "Nigeria" is missing): then wait for Enter.
function startsAnother(text, id) {
  for (const [name, other] of lookup) {
    if (other !== id && !found.includes(other) && name.length > text.length && name.startsWith(text)) return true;
  }
  return false;
}

$("guess").addEventListener("input", () => {
  const text = normalize($("guess").value);
  const id = lookup.get(text);
  if (id && !found.includes(id) && !startsAnother(text, id)) accept(id);
});

$("guess").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const raw = $("guess").value.trim();
  if (!raw) return;
  const id = lookup.get(normalize(raw));
  if (id) {
    if (found.includes(id)) $("message").textContent = `You already have ${run.targets.find((t) => t.id === id).name}.`;
    else accept(id);
    $("guess").value = "";
    return;
  }
  const r = await api("/api/nameall/check", { run_id: run.run_id, guess: raw });
  if (r.ok && !found.includes(r.id)) accept(r.id, r.typo);
  else $("message").textContent = r.ok ? `You already have ${r.name}.` : r.message;
  $("guess").value = "";
});

let finishing = false;
async function finish() {
  if (finishing || !run) return;
  finishing = true;
  clearInterval(ticker);
  $("guess").disabled = true;
  const r = await api("/api/nameall/finish", { run_id: run.run_id, found });
  for (const m of r.missed) map.mark(m.id, "miss");
  if (!run.view) map.reset();

  const all = r.score === r.total;
  const verdict = $("verdict");
  verdict.className = "verdict " + (all ? "good" : "");
  verdict.innerHTML = `${all ? "🎉 All of them! " : ""}You named <b>${r.score}</b> of ${r.total} in ${formatTime(r.seconds)}.
    <span class="xp-pop">+${r.xp} XP</span>
    <small>${r.new_best ? "🏆 New personal best!" : r.best_before ? `Your best: ${r.best_before.score}/${r.total}.` : ""}${r.bonus ? ` Includes a +${r.bonus} XP bonus for naming every one.` : ""}</small>`;
  $("missed").textContent = r.missed.length
    ? `Missed (red on the map): ${r.missed.map((m) => m.name).sort().join(", ")}.`
    : "";
  $("game").hidden = true;
  $("result").hidden = false;
  $("again").focus();
  finishing = false;
  run = null;
  celebrate(r);
}

$("finish").addEventListener("click", finish);
$("again").addEventListener("click", () => start(variant));
$("choose").addEventListener("click", () => location.reload());
document.querySelectorAll(".variant").forEach((b) => b.addEventListener("click", () => start(b.dataset.variant)));
