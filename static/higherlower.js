// ⬆️ Higher or Lower: is country B's number higher or lower than country A's?
let run = null;
let variant = null;
let busy = false;

function fillCard(id, country, value, label) {
  const card = $(id);
  card.querySelector("img").src = country.flag;
  card.querySelector("img").alt = `Flag of ${country.name}`;
  card.querySelector(".hl-name").textContent = country.name;
  card.querySelector(".hl-value").textContent = value;
  const labelEl = card.querySelector(".hl-label");
  if (labelEl) labelEl.textContent = label;
  card.classList.remove("right", "wrong");
}

function showPair(p) {
  fillCard("card-a", p.a, p.a.value, p.label);
  fillCard("card-b", p.b, "?", p.label);
  $("question").innerHTML = `<b>${esc(p.b.name)}</b>: higher or lower ${esc(p.phrase)} than <b>${esc(p.a.name)}</b>?`;
  $("streak-count").textContent = p.streak;
  feedbackContext = { game: "higherlower", stat: p.label, a: p.a.name, b: p.b.name };
  $("higher").disabled = $("lower").disabled = false;
}

async function start(chosen) {
  variant = chosen;
  run = await api("/api/higherlower/start", { variant });
  $("chooser").hidden = true;
  $("result").hidden = true;
  $("game").hidden = false;
  $("note").textContent = "";
  showPair(run);
}

async function guess(choice) {
  if (busy || !run) return;
  busy = true;
  $("higher").disabled = $("lower").disabled = true;
  const r = await api("/api/higherlower/guess", { run_id: run.run_id, choice });
  const cardB = $("card-b");
  cardB.querySelector(".hl-value").textContent = r.reveal.value;
  cardB.classList.add(r.correct ? "right" : "wrong");
  $("note").textContent = r.reveal.note || "";
  celebrate(r);

  if (r.correct) {
    setTimeout(() => { showPair(r.next); busy = false; }, 1100);
    return;
  }
  const verdict = $("verdict");
  verdict.className = "verdict bad";
  verdict.innerHTML = `Streak over: <b>${r.streak}</b> in a row.
    <small>${r.new_best ? "🏆 New personal best!" : r.best_before !== null ? `Your best: ${r.best_before}.` : ""}</small>`;
  $("result").hidden = false;
  $("again").focus();
  run = null;
  busy = false;
}

$("higher").addEventListener("click", () => guess("higher"));
$("lower").addEventListener("click", () => guess("lower"));
$("again").addEventListener("click", () => start(variant));
$("choose").addEventListener("click", () => location.reload());
document.querySelectorAll(".variant").forEach((b) => b.addEventListener("click", () => start(b.dataset.variant)));
document.addEventListener("keydown", (e) => {
  if (e.target.closest("dialog")) return;  // typing in the feedback box
  if (e.key === "ArrowUp") { e.preventDefault(); guess("higher"); }
  if (e.key === "ArrowDown") { e.preventDefault(); guess("lower"); }
});
