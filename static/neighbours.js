// 🤝 Neighbours: name every country bordering the one shown. Three wrong names end the round.
const map = new WorldMap($("map"), { zoomable: true, label: "Map of the country and the neighbours you've found" });
let run = null;
let finished = false;

async function start(fresh = false) {
  const r = await api("/api/neighbours/start", { new: fresh });
  run = r.run_id;
  finished = false;
  map.clear();
  render(r);
  map.fit([r.view], { pad: 0.35, minW: 60 });
  $("message").textContent = r.log.length ? "Welcome back! Carry on where you left off." : "";
  $("guess-form").hidden = false;
  $("reveal").hidden = true;
  $("guess").focus({ preventScroll: true });
}

function render(r) {
  $("country").textContent = r.country.name;
  $("flag").src = r.country.flag;
  $("flag").alt = `Flag of ${r.country.name}`;
  $("flag").hidden = false;
  $("found-count").textContent = `${r.found.length} / ${r.total}`;
  const lives = "●".repeat(r.strikes_left) + "○".repeat(3 - r.strikes_left);
  $("summary").innerHTML = `It has <b>${r.total}</b> neighbour${r.total === 1 ? "" : "s"}. ` +
    `Wrong guesses left: <span class="lives" title="${r.strikes_left} left">${lives}</span>`;
  map.mark(r.target.id, "target");
  for (const f of r.found) map.mark(f.id, "hit");
  for (const w of r.wrong_places) map.mark(w.id, "wrong");  // where your wrong guesses really are
  // Every guess so far, newest first: ✓ for a neighbour, ✗ for a country that isn't one.
  $("log").innerHTML = [...r.log].reverse()
    .map((g) => `<li class="${g.ok ? "ok" : "bad"}">${esc(g.name)}${g.ok ? "" : " <small>doesn't border it</small>"}</li>`)
    .join("");
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
  const r = await send("/api/neighbours/guess", { run_id: run, guess: text });
  if (!r) return;
  const messages = {
    unknown: `“${esc(text)}” isn't a country I know.`,
    self: `That's ${esc(r.name)} itself!`,
    repeat: `You already said ${esc(r.name)}.`,
    found: `✓ ${esc(r.name)}${r.typo ? " (spelling forgiven)" : ""}`,
    wrong: `✗ ${esc(r.name)} doesn't border ${esc(r.country.name)}.`,
  };
  $("message").innerHTML = messages[r.status] || "";
  $("message").className = "message " + (r.status === "found" ? "good" : r.status === "wrong" ? "bad" : "");
  render(r);
  if (r.finished) end(r);
  else $("guess").focus({ preventScroll: true });
}

async function giveUp() {
  if (finished || !run) return;
  const r = await send("/api/neighbours/give-up", { run_id: run });
  if (!r) return;
  render(r);
  end(r);
}

function end(r) {
  finished = true;
  for (const m of r.missed) map.mark(m.id, "miss");
  const verdict = $("verdict");
  verdict.className = "verdict " + (r.won ? "good" : "bad");
  verdict.innerHTML = r.won
    ? `✓ All ${r.total} neighbours! <span class="xp-pop">+${r.xp} XP</span>`
    : `You found ${r.found.length} of ${r.total}.${r.xp ? ` <span class="xp-pop">+${r.xp} XP</span>` : ""}`;
  $("missed").textContent = r.missed.length ? `Missed (red on the map): ${r.missed.map((m) => m.name).join(", ")}.` : "";
  $("info").textContent = r.info || "";
  $("message").textContent = "";
  $("guess-form").hidden = true;
  $("reveal").hidden = false;
  $("again").focus();
  celebrate(r);
}

$("guess-form").addEventListener("submit", guess);
$("give-up").addEventListener("click", giveUp);
$("again").addEventListener("click", () => start(true));

map.load().then(() => start());
