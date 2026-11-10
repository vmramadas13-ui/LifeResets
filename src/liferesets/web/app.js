const $ = (selector) => document.querySelector(selector);
const notice = $("#notice");

function csrfToken() {
  return document.cookie.split("; ").find((item) => item.startsWith("lr-csrf="))?.split("=").slice(1).join("=") || "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error?.message || payload.detail?.message || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function showNotice(message) { notice.textContent = message; }
function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }

async function loadWorkspace() {
  $("#auth").hidden = true;
  $("#workspace").hidden = false;
  $("#logout").hidden = false;
  const [domains, goals, plan, rpg] = await Promise.all([
    api("/api/v1/domains"), api("/api/v1/goals"), api("/api/v1/plans/preview"), api("/api/v1/rpg/status"),
  ]);
  const domainSelect = $("#goal-form select");
  domainSelect.replaceChildren(...domains.map((domain) => new Option(domain.name, domain.code)));
  $("#goals").replaceChildren(...goals.map((goal) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = goal.title;
    const meta = document.createElement("small"); meta.textContent = `${goal.domain.replaceAll("_", " ")} · ${goal.status}${goal.target_date ? ` · target ${goal.target_date}` : ""}`;
    item.append(title, meta); return item;
  }));
  renderPlan(plan);
  $("#rpg-status").textContent = `Level ${rpg.level} · ${rpg.total_xp} XP · ${rpg.completed_tasks} completed tasks`;
  showNotice("Your private workspace is ready.");
}

function renderPlan(plan) {
  const list = $("#quests");
  const rows = plan.quests.map((quest) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = quest.title;
    const meta = document.createElement("small"); meta.textContent = quest.due_date ? `Due ${quest.due_date}` : quest.reason;
    item.append(title, meta); return item;
  });
  if (!rows.length) { const empty = document.createElement("li"); empty.textContent = "No pending actions yet. Add a goal to see a next step."; rows.push(empty); }
  list.replaceChildren(...rows);
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); showNotice("Signing in…");
  try { await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) }); await loadWorkspace(); }
  catch (error) { showNotice(error.message); }
});

$("#goal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formObject(event.currentTarget);
  if (!payload.target_date) delete payload.target_date;
  try { await api("/api/v1/goals", { method: "POST", body: JSON.stringify(payload) }); event.currentTarget.reset(); await loadWorkspace(); showNotice("Goal saved."); }
  catch (error) { showNotice(error.message); }
});

$("#refresh-goals").addEventListener("click", () => loadWorkspace().catch((error) => showNotice(error.message)));
$("#refresh-plan").addEventListener("click", async () => {
  try { renderPlan(await api("/api/v1/plans/preview")); showNotice("Plan preview refreshed. Nothing was saved."); }
  catch (error) { showNotice(error.message); }
});
$("#core-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const result = await api("/api/v1/core/respond", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) }); $("#core-answer").textContent = `${result.answer} Sources: ${result.provenance.join(", ") || "no saved records"}.`; }
  catch (error) { showNotice(error.message); }
});
$("#logout").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", { method: "POST" }); }
  finally { $("#workspace").hidden = true; $("#auth").hidden = false; $("#logout").hidden = true; showNotice("Signed out."); }
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
api("/api/v1/auth/me").then(loadWorkspace).catch(() => { $("#auth").hidden = false; });
