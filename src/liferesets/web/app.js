const $ = (selector) => document.querySelector(selector);
const notice = $("#notice");
let workspaceTasks = [];
let dailyPlan = null;
let workspaceProgress = null;
let coreReply = "";
let activeAgentActionId = null;
let awakeningData = null;
let awakeningStepIndex = 0;

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
  const character = rpg.character || {};
  $("#character-title").textContent = character.hunter_name || "Hunter";
  $("#character-callsign").textContent = character.callsign
    ? `Callsign · ${character.callsign}`
    : "Choose a callsign if you want one.";
  $("#character-rank").textContent = rpg.rank || "E";
  $("#character-level").textContent = `Level ${rpg.level}`;
  $("#character-xp-label").textContent = `${rpg.xp_in_level} / ${rpg.xp_per_level} XP`;
  const fill = $("#character-xp-fill");
  fill.style.width = `${rpg.xp_in_level}%`;
  const progress = fill.parentElement;
  progress.setAttribute("aria-valuenow", String(rpg.xp_in_level));
  $("#character-next-rank").textContent = rpg.next_rank
    ? `${rpg.total_xp} total XP · ${rpg.rank_progress_percent}% toward rank ${rpg.next_rank}`
    : "Top listed rank reached. Your progress remains recorded.";
  const milestones = rpg.achievements.map((achievement) => {
    const labels = { first_completed_task: "First action", ten_completed_tasks: "10 actions completed" };
    const item = document.createElement("li");
    item.textContent = labels[achievement] || achievement.replaceAll("_", " ");
    return item;
  });
  $("#character-achievements").replaceChildren(...milestones);
  const rankRows = rpg.ruleset.rank_thresholds.map((rule) => {
    const item = document.createElement("li");
    item.textContent = `${rule.rank} rank · ${rule.minimum_xp} XP`;
    return item;
  });
  $("#rank-rules").replaceChildren(...rankRows);
  const characterForm = $("#character-form");
  characterForm.elements.hunter_name.value = character.hunter_name || "Hunter";
  characterForm.elements.callsign.value = character.callsign || "";
  characterForm.elements.paused.checked = Boolean(character.paused);
  $("#rpg-status").textContent = readPreference("standard-language") === "true"
    ? `Progress level ${rpg.level} · ${rpg.completed_tasks} actions completed`
    : `Rank ${rpg.rank} · Level ${rpg.level} · ${rpg.total_xp} XP · ${rpg.completed_tasks} completed actions`;
}

function renderSkills(skills) {
  const rows = skills.map((skill) => {
    const item = document.createElement("li");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `${skill.name} · Level ${skill.level}`;
    const definition = document.createElement("p");
    definition.textContent = skill.definition;
    const confidence = document.createElement("small");
    confidence.textContent = `${skill.domain ? skill.domain.replaceAll("_", " ") + " · " : ""}${skill.confidence}% confidence · ${skill.evidence.length} evidence item${skill.evidence.length === 1 ? "" : "s"}`;
    const evidenceList = document.createElement("ul");
    evidenceList.className = "record-list";
    for (const record of skill.evidence) {
      const evidenceItem = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = record.summary;
      const note = document.createElement("small");
      note.textContent = `Self-reported · ${record.confidence}% confidence · not independently verified`;
      evidenceItem.append(text, note);
      evidenceList.append(evidenceItem);
    }
    const form = document.createElement("form");
    form.className = "skill-evidence-form";
    form.innerHTML = '<label>Evidence note<textarea name="summary" maxlength="500" rows="2" required></textarea></label><label>Confidence (0–100)<input name="confidence" type="number" min="0" max="100" value="50" required></label><button type="submit" class="quiet">Add evidence</button>';
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const currentForm = event.currentTarget;
      const payload = formObject(currentForm);
      payload.confidence = Number(payload.confidence);
      try {
        await api(`/api/v1/rpg/skills/${skill.id}/evidence`, { method: "POST", body: JSON.stringify(payload) });
        await loadWorkspace();
        showNotice("Evidence added as self-reported.");
      } catch (error) { showNotice(error.message); }
    });
    details.append(summary, definition, confidence, evidenceList, form);
    item.append(details);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "Add a skill you want to build. You choose its level and confidence.";
    rows.push(empty);
  }
  $("#skills").replaceChildren(...rows);
}

function renderChronicle(events) {
  const rows = events.slice(0, 12).map((entry) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = entry.title;
    const note = document.createElement("small");
    const when = new Date(entry.created_at);
    const date = Number.isNaN(when.getTime()) ? "" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(when);
    note.textContent = [entry.detail, date].filter(Boolean).join(" · ");
    item.append(title, note);
    return item;
  });
  $("#chronicle").replaceChildren(...rows);
  $("#chronicle-empty").hidden = rows.length > 0;
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
  const [domains, goals, preview, rpg, insights, inbox, awakening, campaigns, reviews, tasks, currentPlan, recovery, skills, chronicle, agentActions] = await Promise.all([
    api("/api/v1/domains"), api("/api/v1/goals"), api("/api/v1/plans/preview"), api("/api/v1/rpg/status"), api("/api/v1/insights/progress"), api("/api/v1/notifications/inbox"),
    api("/api/v1/onboarding/awakening"), api("/api/v1/campaigns"), api("/api/v1/reviews"), api("/api/v1/tasks"),
    api(`/api/v1/daily-plans/${planDate}`), api(`/api/v1/daily-plans/${planDate}/recovery`),
    api("/api/v1/rpg/skills"), api("/api/v1/rpg/chronicle"), api("/api/v1/agent/actions"),
  ]);
  const domainSelect = $("#goal-form select");
  domainSelect.replaceChildren(...domains.map((domain) => new Option(domain.name, domain.code)));
  $("#skill-domain").replaceChildren(new Option("Choose a domain", ""), ...domains.map((domain) => new Option(domain.name, domain.code)));
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
  renderSkills(skills);
  renderChronicle(chronicle);
  renderAgentActions(agentActions);
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

function renderAwakening(awakening, selectedIndex = null) {
  awakeningData = awakening;
  const unfinished = awakening.steps.findIndex((step) => !["completed", "skipped"].includes(step.status));
  awakeningStepIndex = selectedIndex ?? (unfinished >= 0 ? unfinished : awakening.steps.length - 1);
  const step = awakening.steps[awakeningStepIndex];
  const resolved = awakening.steps.filter((item) => ["completed", "skipped"].includes(item.status)).length;
  const progress = $("#awakening-progress-fill").parentElement;
  $("#awakening-day-label").textContent = `Day ${step.day} of 7 · ${awakening.completed} completed`;
  $("#awakening-progress-fill").style.width = `${(resolved / awakening.steps.length) * 100}%`;
  progress.setAttribute("aria-valuenow", String(resolved));
  $("#awakening-question-title").textContent = step.title;
  $("#awakening-prompt").textContent = step.prompt;
  $("#awakening-answer").value = step.answer || "";
  $("#awakening-consent").checked = awakening.storage_consent;
  $("#awakening-previous").disabled = awakeningStepIndex === 0;
  $("#awakening-save").textContent = awakeningStepIndex === awakening.steps.length - 1 ? "Complete prompt" : "Complete and continue";
  $("#awakening-skip").textContent = step.status === "skipped" ? "Keep skipped" : "Skip this prompt";
  $("#awakening-complete").hidden = resolved !== awakening.steps.length;
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

function renderAgentActions(actions) {
  const rows = actions.slice(0, 8).map((action) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = action.proposal.title;
    const state = document.createElement("small");
    const labels = { proposed: "Awaiting your approval", approved: "Added after your approval", rejected: "Rejected", undone: "Undone" };
    state.textContent = `${labels[action.status] || action.status} · Local task · No external access`;
    item.append(title, state);
    const controls = document.createElement("div");
    controls.className = "item-actions agent-history-actions";
    if (action.status === "proposed") {
      controls.append(
        makePlanItemButton("Approve", () => runAgentAction(action.id, "approve"), "quiet", `proposal ${action.proposal.title}`),
        makePlanItemButton("Reject", () => runAgentAction(action.id, "reject"), "text-button", `proposal ${action.proposal.title}`),
      );
    } else if (action.status === "approved") {
      controls.append(makePlanItemButton("Undo", () => runAgentAction(action.id, "undo"), "quiet", `added action ${action.proposal.title}`));
    }
    if (controls.childElementCount) item.append(controls);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No action proposals yet.";
    rows.push(empty);
  }
  $("#agent-action-history").replaceChildren(...rows);
}

async function runAgentAction(actionId, decision) {
  try {
    const result = await api(`/api/v1/agent/actions/${actionId}/${decision}`, { method: "POST" });
    await loadWorkspace();
    if (decision === "approve") showNotice(`Approved. “${result.task.title}” was added to your actions.`);
    else if (decision === "undo") showNotice("The approved action was undone and kept in your history.");
    else showNotice("Proposal rejected. No task was created.");
  } catch (error) { showNotice(error.message); }
}

function showAgentReview(action) {
  activeAgentActionId = action.id;
  $("#agent-review").hidden = false;
  $("#agent-review-text").textContent = `Review: add “${action.proposal.title}” to “${action.proposal.goal_title}”? It will create one local task and will not contact an external service.`;
  $("#approve-agent-action").disabled = false;
  $("#reject-agent-action").disabled = false;
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); showNotice("Signing in…");
  try { await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) }); await loadWorkspace(); }
  catch (error) { showNotice(error.message); }
});

$("#awakening-previous").addEventListener("click", () => {
  if (awakeningData && awakeningStepIndex > 0) {
    renderAwakening(awakeningData, awakeningStepIndex - 1);
  }
});

$("#awakening-consent").addEventListener("change", async (event) => {
  const checkbox = event.currentTarget;
  try {
    await api("/api/v1/consents", {
      method: "POST",
      body: JSON.stringify({
        purpose: "awakening_storage",
        granted: checkbox.checked,
        policy_version: "v1",
      }),
    });
    if (awakeningData) awakeningData.storage_consent = checkbox.checked;
    showNotice(checkbox.checked
      ? "Awakening answer storage is on for this local account."
      : "New Awakening answers will not be saved. Existing answers remain until deleted.");
  } catch (error) {
    checkbox.checked = !checkbox.checked;
    showNotice(error.message);
  }
});

$("#awakening-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!awakeningData) return;
  const step = awakeningData.steps[awakeningStepIndex];
  const answer = $("#awakening-answer").value.trim();
  try {
    await api(`/api/v1/onboarding/awakening/${step.step}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed", answer: answer || null }),
    });
    await loadWorkspace();
    showNotice("Awakening progress saved. Continue whenever you’re ready.");
  } catch (error) {
    showNotice(error.message);
  }
});

$("#awakening-save-later").addEventListener("click", async () => {
  if (!awakeningData) return;
  const step = awakeningData.steps[awakeningStepIndex];
  const answer = $("#awakening-answer").value.trim();
  try {
    await api(`/api/v1/onboarding/awakening/${step.step}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "in_progress", answer: answer || null }),
    });
    await loadWorkspace();
    showNotice("Your progress is saved. Come back whenever you’re ready.");
  } catch (error) {
    showNotice(error.message);
  }
});

$("#awakening-skip").addEventListener("click", async () => {
  if (!awakeningData) return;
  const step = awakeningData.steps[awakeningStepIndex];
  try {
    await api(`/api/v1/onboarding/awakening/${step.step}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "skipped" }),
    });
    await loadWorkspace();
    showNotice("Prompt skipped. You can return to it later.");
  } catch (error) {
    showNotice(error.message);
  }
});

$("#awakening-delete").addEventListener("click", async () => {
  if (!window.confirm("Delete all saved Awakening answers? This cannot be undone.")) return;
  try {
    const result = await api("/api/v1/onboarding/awakening/answers", { method: "DELETE" });
    await loadWorkspace();
    showNotice(`${result.deleted_answers} saved answer${result.deleted_answers === 1 ? "" : "s"} deleted.`);
  } catch (error) {
    showNotice(error.message);
  }
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

$("#character-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    hunter_name: form.elements.hunter_name.value.trim(),
    callsign: form.elements.callsign.value.trim() || null,
    paused: form.elements.paused.checked,
  };
  try {
    await api("/api/v1/rpg/character", { method: "PATCH", body: JSON.stringify(payload) });
    await loadWorkspace();
    showNotice("Character settings saved.");
  } catch (error) { showNotice(error.message); }
});

$("#skill-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!payload.domain) payload.domain = null;
  payload.level = Number(payload.level);
  payload.confidence = Number(payload.confidence);
  try {
    await api("/api/v1/rpg/skills", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    form.elements.level.value = "1";
    form.elements.confidence.value = "0";
    await loadWorkspace();
    showNotice("Skill added to your character build.");
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
  try {
    const result = await api("/api/v1/core/respond", { method: "POST", body: JSON.stringify(formObject(event.currentTarget)) });
    coreReply = result.answer;
    $("#core-answer").textContent = `${result.answer} Sources: ${result.provenance.join(", ") || "no saved records"}.`;
    $("#speak-answer").disabled = !("speechSynthesis" in window);
  }
  catch (error) { showNotice(error.message); }
});

$("#voice-input").addEventListener("click", async () => {
  const status = $("#voice-status");
  if (!window.isSecureContext) {
    status.textContent = "On-device dictation needs a secure connection. Use the microphone on your iPhone keyboard for now.";
    return;
  }
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition || !("processLocally" in Recognition.prototype) || typeof Recognition.available !== "function") {
    status.textContent = "This browser does not offer confirmed on-device dictation. Use the microphone on your iPhone keyboard; no audio was recorded here.";
    return;
  }
  const language = navigator.language || "en-US";
  status.textContent = `Checking for on-device dictation in ${language}…`;
  const button = $("#voice-input");
  button.disabled = true;
  try {
    const availability = await Recognition.available({ langs: [language], processLocally: true });
    if (availability !== "available") {
      status.textContent = "On-device dictation is not ready for this language. Use the microphone on your iPhone keyboard. No cloud recognition was started.";
      return;
    }
    const recognition = new Recognition();
    recognition.processLocally = true;
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (resultEvent) => {
      const transcript = resultEvent.results?.[0]?.[0]?.transcript || "";
      const input = $("#core-question");
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? input.value.length;
      input.setRangeText(transcript, start, end, "end");
      input.focus();
      status.textContent = "Dictation added. Review and edit the text; it is not saved until you submit.";
    };
    recognition.onerror = (errorEvent) => {
      status.textContent = errorEvent.error === "not-allowed"
        ? "Microphone permission was declined. You can still type or use keyboard dictation."
        : "On-device dictation could not start. You can still type or use keyboard dictation.";
    };
    recognition.onend = () => { button.disabled = false; };
    status.textContent = "Listening on this device. Your transcript will appear here for review.";
    recognition.start();
  } catch {
    status.textContent = "On-device dictation is unavailable right now. Use the microphone on your iPhone keyboard.";
  } finally {
    if (button.disabled) button.disabled = false;
  }
});

$("#speak-answer").addEventListener("click", () => {
  if (!("speechSynthesis" in window) || !coreReply) return;
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    $("#speak-answer").textContent = "Read aloud";
    return;
  }
  const utterance = new SpeechSynthesisUtterance(coreReply);
  utterance.lang = navigator.language || "en-US";
  utterance.onend = () => { $("#speak-answer").textContent = "Read aloud"; };
  utterance.onerror = () => { $("#speak-answer").textContent = "Read aloud"; };
  $("#speak-answer").textContent = "Stop speaking";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
});
$("#agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  try {
    const action = await api("/api/v1/agent/actions", { method: "POST", body: JSON.stringify(payload) });
    form.elements.task_title.value = "";
    $("#agent-proposal").textContent = "The proposed action is saved for review. No task has been created.";
    showAgentReview(action);
    await loadWorkspace();
  } catch (error) { showNotice(error.message); }
});
$("#approve-agent-action").addEventListener("click", () => {
  if (activeAgentActionId) runAgentAction(activeAgentActionId, "approve");
});
$("#reject-agent-action").addEventListener("click", () => {
  if (activeAgentActionId) runAgentAction(activeAgentActionId, "reject");
});
$("#logout").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", { method: "POST" }); }
  finally { $("#workspace").hidden = true; $("#auth").hidden = false; $("#logout").hidden = true; showNotice("Signed out."); }
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
applyDisplayPreferences();
api("/api/v1/auth/me").then(loadWorkspace).catch(() => { $("#auth").hidden = false; });
