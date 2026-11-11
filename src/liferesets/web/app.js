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
  const [domains, goals, plan, rpg, insights, inbox, awakening, campaigns, reviews] = await Promise.all([
    api("/api/v1/domains"), api("/api/v1/goals"), api("/api/v1/plans/preview"), api("/api/v1/rpg/status"), api("/api/v1/insights/progress"), api("/api/v1/notifications/inbox"),
    api("/api/v1/onboarding/awakening"), api("/api/v1/campaigns"), api("/api/v1/reviews"),
  ]);
  const domainSelect = $("#goal-form select");
  domainSelect.replaceChildren(...domains.map((domain) => new Option(domain.name, domain.code)));
  const activeGoals = goals.filter((goal) => goal.status === "active");
  $("#agent-goal").replaceChildren(...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#agent-form button").disabled = activeGoals.length === 0;
  $("#goals").replaceChildren(...goals.map((goal) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = goal.title;
    const meta = document.createElement("small"); meta.textContent = `${goal.domain.replaceAll("_", " ")} · ${goal.status}${goal.target_date ? ` · target ${goal.target_date}` : ""}`;
    item.append(title, meta); return item;
  }));
  renderPlan(plan);
  $("#rpg-status").textContent = `Level ${rpg.level} · ${rpg.total_xp} XP · ${rpg.completed_tasks} completed tasks`;
  renderInsights(insights);
  renderInbox(inbox);
  renderAwakening(awakening);
  renderCampaigns(campaigns);
  renderReviews(reviews);
  showNotice("Your private workspace is ready.");
}

function renderAwakening(awakening) {
  const rows = awakening.steps.map((step) => {
    const item = document.createElement("li");
    const label = document.createElement("label"); label.textContent = `Step ${step.step} · ${step.status.replaceAll("_", " ")}`;
    const select = document.createElement("select");
    for (const status of ["in_progress", "completed", "skipped"]) select.add(new Option(status.replaceAll("_", " "), status));
    select.value = step.status === "not_started" ? "in_progress" : step.status;
    select.setAttribute("aria-label", `Update Awakening step ${step.step}`);
    select.addEventListener("change", async () => {
      try { await api(`/api/v1/onboarding/awakening/${step.step}`, { method: "PATCH", body: JSON.stringify({ status: select.value }) }); showNotice(`Step ${step.step} updated.`); }
      catch (error) { showNotice(error.message); }
    });
    item.append(label, select); return item;
  });
  $("#awakening").replaceChildren(...rows);
}

function renderCampaigns(campaigns) {
  const rows = campaigns.map((campaign) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = campaign.title;
    const detail = document.createElement("small"); detail.textContent = `${campaign.starts_on} to ${campaign.ends_on} · ${campaign.status}`;
    item.append(title, detail); return item;
  });
  $("#campaigns").replaceChildren(...rows);
}

function renderReviews(reviews) {
  const rows = reviews.map((review) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = `${review.cadence} review · ${review.period_start} to ${review.period_end}`;
    const detail = document.createElement("small"); detail.textContent = review.status;
    item.append(title, detail); return item;
  });
  $("#reviews").replaceChildren(...rows);
}

function renderInbox(inbox) {
  const rows = inbox.items.map((reminder) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = reminder.title;
    const due = document.createElement("small"); due.textContent = `Due ${reminder.due_date}`;
    item.append(title, due); return item;
  });
  if (!rows.length) { const empty = document.createElement("li"); empty.textContent = "No tasks due in the next week."; rows.push(empty); }
  $("#inbox").replaceChildren(...rows);
}

function renderInsights(insights) {
  const rows = [];
  for (const goal of insights.goals) for (const metric of goal.metrics) {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = `${goal.title} · ${metric.name}`;
    const progress = metric.progress_percent === null ? "Add baseline and current values to compare" : `${metric.progress_percent}% of stated range`;
    const meta = document.createElement("small"); meta.textContent = `${metric.current_value ?? "—"} / ${metric.target_value} ${metric.unit} · ${progress} · ${metric.source}`;
    item.append(title, meta); rows.push(item);
  }
  if (!rows.length) { const empty = document.createElement("li"); empty.textContent = "Add a goal with a metric to see progress."; rows.push(empty); }
  $("#insights").replaceChildren(...rows);
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

$("#campaign-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await api("/api/v1/campaigns", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) }); event.currentTarget.reset(); await loadWorkspace(); showNotice("90-day campaign saved."); }
  catch (error) { showNotice(error.message); }
});

$("#review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await api("/api/v1/reviews", { method: "POST", body: JSON.stringify({ ...formObject(event.currentTarget), status: "draft" }) }); await loadWorkspace(); showNotice("Review draft started."); }
  catch (error) { showNotice(error.message); }
});

$("#refresh-goals").addEventListener("click", () => loadWorkspace().catch((error) => showNotice(error.message)));
$("#refresh-plan").addEventListener("click", async () => {
  try { renderPlan(await api("/api/v1/plans/preview")); showNotice("Plan preview refreshed. Nothing was saved."); }
  catch (error) { showNotice(error.message); }
});
$("#refresh-insights").addEventListener("click", async () => {
  try { renderInsights(await api("/api/v1/insights/progress")); }
  catch (error) { showNotice(error.message); }
});
$("#refresh-inbox").addEventListener("click", async () => {
  try { renderInbox(await api("/api/v1/notifications/inbox")); }
  catch (error) { showNotice(error.message); }
});
$("#core-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const result = await api("/api/v1/core/respond", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) }); $("#core-answer").textContent = `${result.answer} Sources: ${result.provenance.join(", ") || "no saved records"}.`; }
  catch (error) { showNotice(error.message); }
});
$("#agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/v1/agent/proposals/next-task", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) });
    $("#agent-proposal").textContent = `${result.proposal.title} — approval required; no task was created.`;
  } catch (error) { showNotice(error.message); }
});
$("#logout").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", { method: "POST" }); }
  finally { $("#workspace").hidden = true; $("#auth").hidden = false; $("#logout").hidden = true; showNotice("Signed out."); }
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
api("/api/v1/auth/me").then(loadWorkspace).catch(() => { $("#auth").hidden = false; });
