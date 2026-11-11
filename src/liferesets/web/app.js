const $ = (selector) => document.querySelector(selector);
const notice = $("#notice");
let workspaceTasks = [];
let dailyPlan = null;
let workspaceProgress = null;

function readPreference(name, fallback = "false") {
  try { return localStorage.getItem(`lr-${name}`) ?? fallback; }
  catch { return fallback; }
}

function savePreference(name, value) {
  try { localStorage.setItem(`lr-${name}`, value); }
  catch { showNotice("This browser could not save the display preference."); }
}

function applyDisplayPreferences() {
  const root = document.documentElement;
  const dark = readPreference("theme") === "dark";
  const systemMotionPreference = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "true" : "false";
  const reduceMotion = readPreference("reduce-motion", systemMotionPreference) === "true";
  const standardLanguage = readPreference("standard-language") === "true";
  root.dataset.theme = dark ? "dark" : "light";
  root.dataset.reduceMotion = String(reduceMotion);
  $("#theme-toggle").checked = dark;
  $("#motion-toggle").checked = reduceMotion;
  $("#language-toggle").checked = standardLanguage;
  document.querySelectorAll("[data-game-term]").forEach((node) => {
    node.textContent = standardLanguage ? node.dataset.standardTerm : node.dataset.gameTerm;
  });
}

function renderProgress(rpg) {
  if (!rpg) return;
  $("#rpg-status").textContent = readPreference("standard-language") === "true"
    ? `Progress level ${rpg.level} · ${rpg.completed_tasks} actions completed`
    : `Level ${rpg.level} · ${rpg.total_xp} XP · ${rpg.completed_tasks} completed tasks`;
}

function localDateString(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function nextDateString(value) {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + 1);
  return localDateString(date);
}

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
  if (!$("#daily-plan-date").value) $("#daily-plan-date").value = localDateString();
  const planDate = $("#daily-plan-date").value;
  const [domains, goals, preview, rpg, insights, inbox, awakening, campaigns, reviews, tasks, currentPlan, recovery] = await Promise.all([
    api("/api/v1/domains"), api("/api/v1/goals"), api("/api/v1/plans/preview"), api("/api/v1/rpg/status"), api("/api/v1/insights/progress"), api("/api/v1/notifications/inbox"),
    api("/api/v1/onboarding/awakening"), api("/api/v1/campaigns"), api("/api/v1/reviews"), api("/api/v1/tasks"),
    api(`/api/v1/daily-plans/${planDate}`), api(`/api/v1/daily-plans/${planDate}/recovery`),
  ]);
  const domainSelect = $("#goal-form select");
  domainSelect.replaceChildren(...domains.map((domain) => new Option(domain.name, domain.code)));
  const activeGoals = goals.filter((goal) => goal.status === "active");
  $("#agent-goal").replaceChildren(...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#task-goal").replaceChildren(new Option("No goal selected", ""), ...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#agent-form button").disabled = activeGoals.length === 0;
  workspaceTasks = tasks;
  dailyPlan = currentPlan;
  workspaceProgress = rpg;
  $("#goals").replaceChildren(...goals.map((goal) => {
    const item = document.createElement("li");
    const title = document.createElement("strong"); title.textContent = goal.title;
    const meta = document.createElement("small"); meta.textContent = `${goal.domain.replaceAll("_", " ")} · ${goal.status}${goal.target_date ? ` · target ${goal.target_date}` : ""}`;
    item.append(title, meta); return item;
  }));
  renderPlan(preview);
  renderDailyPlan(currentPlan);
  renderRecovery(recovery);
  renderProgress(rpg);
  renderInsights(insights);
  renderInbox(inbox);
  renderAwakening(awakening);
  renderCampaigns(campaigns);
  renderReviews(reviews);
  showNotice("Your private workspace is ready.");
}

function selectedPlanItems() {
  return [...$("#task-options").querySelectorAll("[data-plan-task]:checked")].map((checkbox) => {
    const row = checkbox.closest(".task-option");
    return {
      task_id: checkbox.dataset.planTask,
      planned_minutes: Number(row.querySelector("[data-plan-minutes]").value),
    };
  });
}

function updatePlanSummary() {
  const selected = selectedPlanItems();
  const planned = selected.reduce((total, item) => total + item.planned_minutes, 0);
  const capacity = Number($("#plan-capacity").value) || 0;
  const remaining = capacity - planned;
  $("#plan-time-summary").textContent = `${planned} of ${capacity} min`;
  $("#selection-count").textContent = `${selected.length} selected`;
  $("#capacity-fill").style.width = `${capacity ? Math.min((planned / capacity) * 100, 100) : 0}%`;
  $("#capacity-message").textContent = remaining < 0
    ? `Trim ${Math.abs(remaining)} minutes to fit your available time.`
    : remaining === 0 ? "Your plan uses the time you set." : `${remaining} min left. Leave room for the unexpected.`;
  $("#capacity-fill").classList.toggle("over-capacity", remaining < 0);
  $("#save-daily-plan").disabled = remaining < 0;
  $("#plan-save-state").textContent = remaining < 0 ? "Your selected actions exceed the time available." : "";
}

function renderTaskPicker(plan = dailyPlan) {
  const selectedItems = new Map((plan?.items || []).map((item) => [item.task_id, item]));
  const available = workspaceTasks.filter((task) => task.status === "pending" || selectedItems.get(task.id)?.status === "completed");
  const rows = available.map((task) => {
    const existing = selectedItems.get(task.id);
    const item = document.createElement("li");
    item.className = "task-option";
    const choice = document.createElement("label");
    choice.className = "task-choice";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.planTask = task.id;
    checkbox.checked = existing ? ["planned", "completed"].includes(existing.status) : false;
    checkbox.disabled = task.status === "completed";
    checkbox.setAttribute("aria-label", `Add ${task.title} to the plan`);
    item.classList.toggle("is-selected", checkbox.checked);
    const title = document.createElement("span");
    title.className = "task-choice-copy";
    const strong = document.createElement("strong");
    strong.textContent = task.title;
    const meta = document.createElement("small");
    meta.textContent = task.due_date ? `Due ${task.due_date}` : task.status === "completed" ? "Completed" : "Open action";
    title.append(strong, meta);
    choice.append(checkbox, title);
    const minutesLabel = document.createElement("label");
    minutesLabel.className = "minutes-field";
    minutesLabel.textContent = "Minutes";
    const minutes = document.createElement("input");
    minutes.type = "number";
    minutes.min = "1";
    minutes.max = "1440";
    minutes.step = "1";
    minutes.value = String(existing?.planned_minutes || 15);
    minutes.dataset.planMinutes = "true";
    minutes.setAttribute("aria-label", `Planned minutes for ${task.title}`);
    minutesLabel.append(minutes);
    item.append(choice, minutesLabel);
    checkbox.addEventListener("change", () => {
      item.classList.toggle("is-selected", checkbox.checked);
      document.querySelectorAll("[data-recovery-task]").forEach((button) => {
        if (button.dataset.recoveryTask === checkbox.dataset.planTask) {
          button.disabled = checkbox.checked;
          button.textContent = checkbox.checked ? "Selected · save your plan" : "Add to today’s choices";
        }
      });
      updatePlanSummary();
    });
    minutes.addEventListener("input", updatePlanSummary);
    return item;
  });
  $("#task-options").replaceChildren(...rows);
  $("#task-empty").hidden = rows.length > 0;
  updatePlanSummary();
}

function renderDailyPlan(plan) {
  dailyPlan = plan;
  $("#daily-plan-date").value = plan.plan_date;
  $("#plan-capacity").value = String(plan.capacity_minutes);
  $("#plan-energy").value = plan.energy;
  const energyLabels = { low: "Low energy", medium: "Steady energy", high: "High energy" };
  $("#plan-energy-label").textContent = energyLabels[plan.energy] || "Energy";
  renderTaskPicker(plan);
  const rows = plan.items.map((planItem) => {
    const item = document.createElement("li");
    item.className = `saved-plan-item status-${planItem.status}`;
    const copy = document.createElement("div");
    copy.className = "saved-plan-copy";
    const title = document.createElement("strong");
    title.textContent = planItem.title;
    const meta = document.createElement("span");
    const statusLabels = { planned: "Planned", completed: "Completed", deferred: "Moved to another day", dropped: "Removed from this day" };
    const originalDue = planItem.due_date_at_planning && planItem.deferred_to && planItem.due_date_at_planning !== planItem.deferred_to
      ? ` · originally due ${planItem.due_date_at_planning}`
      : "";
    meta.textContent = `${planItem.planned_minutes} min · ${statusLabels[planItem.status] || planItem.status}${planItem.deferred_to ? ` · ${planItem.deferred_to}` : ""}${originalDue}`;
    copy.append(title, meta);
    item.append(copy);
    if (["planned", "deferred"].includes(planItem.status)) {
      const actions = document.createElement("div");
      actions.className = "item-actions";
      if (planItem.status === "planned") {
        actions.append(makePlanItemButton("Complete", async () => {
          await changePlanItem(planItem, { status: "completed" }, "Action marked complete.");
        }, "quiet", planItem.title));
        const defer = document.createElement("div");
        defer.className = "defer-control";
        const deferDate = document.createElement("input");
        deferDate.type = "date";
        deferDate.min = nextDateString(plan.plan_date);
        deferDate.value = nextDateString(plan.plan_date);
        deferDate.setAttribute("aria-label", `Move ${planItem.title} to a later date`);
        const deferButton = makePlanItemButton("Move", async () => {
          if (!deferDate.value || deferDate.value <= plan.plan_date) {
            showNotice("Choose a date after the plan date.");
            deferDate.focus();
            return;
          }
          await changePlanItem(planItem, { status: "deferred", defer_to: deferDate.value }, "Action moved. You can pick it up when you’re ready.");
        }, "quiet", planItem.title);
        defer.append(deferDate, deferButton);
        actions.append(defer);
      }
      if (planItem.status === "deferred") {
        actions.append(makePlanItemButton("Complete", async () => {
          await changePlanItem(planItem, { status: "completed" }, "Action marked complete.");
        }, "quiet", planItem.title));
      }
      actions.append(makePlanItemButton("Drop", async () => {
        await changePlanItem(planItem, { status: "dropped" }, "Action removed from this plan.");
      }, "text-button", planItem.title));
      item.append(actions);
    }
    return item;
  });
  $("#saved-plan-items").replaceChildren(...rows);
  $("#saved-plan-empty").hidden = rows.length > 0;
}

function makePlanItemButton(label, action, className = "quiet", context = "action") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.setAttribute("aria-label", `${label} ${context}`);
  button.addEventListener("click", () => action().catch((error) => showNotice(error.message)));
  return button;
}

async function changePlanItem(item, changes, message) {
  await api(`/api/v1/daily-plans/${dailyPlan.plan_date}/items/${item.id}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
  await loadWorkspace();
  showNotice(message);
}

function renderRecovery(recovery) {
  const rows = recovery.items.map((suggestion) => {
    const item = document.createElement("li");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = suggestion.title;
    const meta = document.createElement("small");
    meta.textContent = `From ${suggestion.original_plan_date}${suggestion.due_date ? ` · due ${suggestion.due_date}` : ""}`;
    copy.append(title, meta);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet recovery-add";
    button.dataset.recoveryTask = suggestion.task_id;
    const alreadySelected = selectedPlanItems().some((selected) => selected.task_id === suggestion.task_id);
    button.disabled = alreadySelected;
    button.textContent = alreadySelected ? "Selected · save your plan" : "Add to today’s choices";
    button.setAttribute("aria-label", `Choose whether to add ${suggestion.title} to today’s plan`);
    button.addEventListener("click", () => {
      const checkbox = [...$("#task-options").querySelectorAll("[data-plan-task]")]
        .find((candidate) => candidate.dataset.planTask === suggestion.task_id);
      if (!checkbox) {
        showNotice("This action is no longer open to plan.");
        return;
      }
      checkbox.checked = true;
      checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      showNotice("Added to your choices. Save the plan when you’re ready.");
      checkbox.focus();
    });
    item.append(copy, button);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.className = "recovery-empty";
    empty.textContent = "No unfinished actions to revisit for this date.";
    rows.push(empty);
  }
  $("#recovery-list").replaceChildren(...rows);
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
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!payload.target_date) delete payload.target_date;
  try { await api("/api/v1/goals", { method: "POST", body: JSON.stringify(payload) }); form.reset(); await loadWorkspace(); showNotice("Goal saved."); }
  catch (error) { showNotice(error.message); }
});

$("#campaign-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try { await api("/api/v1/campaigns", { method: "POST", body: JSON.stringify(formObject(form)) }); form.reset(); await loadWorkspace(); showNotice("90-day campaign saved."); }
  catch (error) { showNotice(error.message); }
});

$("#review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await api("/api/v1/reviews", { method: "POST", body: JSON.stringify({ ...formObject(event.currentTarget), status: "draft" }) }); await loadWorkspace(); showNotice("Review draft started."); }
  catch (error) { showNotice(error.message); }
});

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!payload.due_date) delete payload.due_date;
  if (!payload.goal_id) delete payload.goal_id;
  try {
    await api("/api/v1/tasks", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await loadWorkspace();
    showNotice("Action added. Choose it when you’re ready to plan.");
  } catch (error) { showNotice(error.message); }
});

$("#daily-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    capacity_minutes: Number($("#plan-capacity").value),
    energy: $("#plan-energy").value,
    items: selectedPlanItems(),
  };
  try {
    const saved = await api(`/api/v1/daily-plans/${$("#daily-plan-date").value}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    renderDailyPlan(saved);
    renderRecovery(await api(`/api/v1/daily-plans/${saved.plan_date}/recovery`));
    showNotice("Your daily plan is saved.");
  } catch (error) { showNotice(error.message); }
});

$("#plan-capacity").addEventListener("input", updatePlanSummary);
$("#daily-plan-date").addEventListener("change", async () => {
  const planDate = $("#daily-plan-date").value;
  if (!planDate) return;
  try {
    const [plan, recovery] = await Promise.all([
      api(`/api/v1/daily-plans/${planDate}`),
      api(`/api/v1/daily-plans/${planDate}/recovery`),
    ]);
    renderDailyPlan(plan);
    renderRecovery(recovery);
  } catch (error) { showNotice(error.message); }
});

$("#refresh-recovery").addEventListener("click", async () => {
  try {
    const recovery = await api(`/api/v1/daily-plans/${$("#daily-plan-date").value}/recovery`);
    renderRecovery(recovery);
    showNotice("Recovery suggestions refreshed. Nothing was moved into your plan.");
  } catch (error) { showNotice(error.message); }
});

$("#theme-toggle").addEventListener("change", (event) => {
  savePreference("theme", event.currentTarget.checked ? "dark" : "light");
  applyDisplayPreferences();
});
$("#motion-toggle").addEventListener("change", (event) => {
  savePreference("reduce-motion", String(event.currentTarget.checked));
  applyDisplayPreferences();
});
$("#language-toggle").addEventListener("change", (event) => {
  savePreference("standard-language", String(event.currentTarget.checked));
  applyDisplayPreferences();
  renderProgress(workspaceProgress);
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
applyDisplayPreferences();
api("/api/v1/auth/me").then(loadWorkspace).catch(() => { $("#auth").hidden = false; });
