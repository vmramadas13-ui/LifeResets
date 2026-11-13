const $ = (selector) => document.querySelector(selector);
const notice = $("#notice");
let workspaceTasks = [];
let workspaceDomains = [];
let workspaceGoals = [];
let workspaceQuests = [];
let dailyPlan = null;
let workspaceProgress = null;
let coreReply = "";
let activeAgentActionId = null;
let awakeningData = null;
let awakeningStepIndex = 0;
let reflectionStorageConsent = false;
let importedCalendarPreview = null;

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

function previousDateString(value) {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() - 1);
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

function appendInputField(form, caption, name, type, value = "", settings = {}) {
  const label = document.createElement("label");
  const text = document.createElement("span");
  text.textContent = caption;
  const input = document.createElement("input");
  input.name = name;
  input.type = type;
  input.value = value;
  if (settings.required) input.required = true;
  if (settings.min !== undefined) input.min = String(settings.min);
  if (settings.max !== undefined) input.max = String(settings.max);
  if (settings.step !== undefined) input.step = String(settings.step);
  if (settings.maxLength !== undefined) input.maxLength = settings.maxLength;
  if (settings.disabled) input.disabled = true;
  label.append(text, input);
  form.append(label);
  return input;
}

function renderDomainSettings(domains) {
  const rows = domains.map((domain) => {
    const row = document.createElement("div");
    row.className = "domain-setting-row";
    row.dataset.domainCode = domain.code;
    appendInputField(row, "Life area name", "name", "text", domain.name, {
      required: true,
      maxLength: 80,
    });
    const orderLabel = document.createElement("label");
    const orderText = document.createElement("span");
    orderText.textContent = "Display order";
    const order = document.createElement("select");
    order.name = "sort_order";
    for (let index = 0; index < domains.length; index += 1) {
      order.add(new Option(String(index + 1), String(index)));
    }
    order.value = String(domain.sort_order);
    order.dataset.previousOrder = order.value;
    order.addEventListener("change", () => {
      const previousOrder = order.dataset.previousOrder;
      const duplicate = [...document.querySelectorAll(".domain-setting-row select[name='sort_order']")]
        .find((candidate) => candidate !== order && candidate.value === order.value);
      if (duplicate) {
        duplicate.value = previousOrder;
        duplicate.dataset.previousOrder = duplicate.value;
      }
      order.dataset.previousOrder = order.value;
    });
    orderLabel.append(orderText, order);
    const enabledLabel = document.createElement("label");
    enabledLabel.className = "check-row domain-enabled";
    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.name = "enabled";
    enabled.checked = domain.enabled;
    const enabledText = document.createElement("span");
    enabledText.textContent = "Use for new goals";
    enabledLabel.append(enabled, enabledText);
    row.append(orderLabel, enabledLabel);
    return row;
  });
  $("#domain-settings").replaceChildren(...rows);
}

function renderDomainSubareas(domains) {
  const groups = domains.map((domain) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `${domain.name} · ${domain.subareas.length} subareas`;
    details.append(summary);

    const list = document.createElement("ul");
    list.className = "domain-subarea-list";
    for (const subarea of domain.subareas) {
      const item = document.createElement("li");
      const rename = document.createElement("form");
      rename.className = "domain-subarea-rename";
      appendInputField(rename, "Subarea name", "name", "text", subarea.name, {
        required: true,
        maxLength: 80,
      });
      const save = document.createElement("button");
      save.type = "submit";
      save.textContent = "Rename";
      rename.append(save);
      rename.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await api(`/api/v1/domains/subareas/${subarea.id}`, {
            method: "PATCH",
            body: JSON.stringify({ name: rename.elements.name.value.trim() }),
          });
          await loadWorkspace();
          showNotice("Subarea renamed. Goals remain connected.");
        } catch (error) {
          showNotice(error.message);
        }
      });

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-button";
      remove.textContent = "Delete";
      remove.addEventListener("click", async () => {
        if (!window.confirm("Delete this subarea? Goals will stay in their life area without a subarea.")) return;
        try {
          const result = await api(`/api/v1/domains/subareas/${subarea.id}`, {
            method: "DELETE",
          });
          await loadWorkspace();
          showNotice(`Subarea deleted. ${result.unassigned_goals} goal${result.unassigned_goals === 1 ? "" : "s"} kept in the life area.`);
        } catch (error) {
          showNotice(error.message);
        }
      });
      item.append(rename, remove);
      list.append(item);
    }

    const create = document.createElement("form");
    create.className = "domain-subarea-create";
    appendInputField(create, "Add a subarea", "name", "text", "", {
      required: true,
      maxLength: 80,
    });
    const add = document.createElement("button");
    add.type = "submit";
    add.textContent = "Add subarea";
    create.append(add);
    create.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/domains/${domain.code}/subareas`, {
          method: "POST",
          body: JSON.stringify({ name: create.elements.name.value.trim() }),
        });
        await loadWorkspace();
        showNotice(`${domain.name} subarea added.`);
      } catch (error) {
        showNotice(error.message);
      }
    });
    details.append(list, create);
    return details;
  });
  $("#domain-subareas").replaceChildren(...groups);
}

function updateGoalSubareaOptions() {
  const domainCode = $("#goal-form").elements.domain.value;
  const select = $("#goal-subarea");
  const previous = select.value;
  const domain = workspaceDomains.find((item) => item.code === domainCode);
  const subareas = domain?.subareas || [];
  select.replaceChildren(new Option("No subarea", ""), ...subareas.map(
    (subarea) => new Option(subarea.name, subarea.id),
  ));
  if (subareas.some((item) => item.id === previous)) select.value = previous;
}

function createMetricMeasurementForm(metric) {
  const form = document.createElement("form");
  form.className = "metric-measurement-form";
  appendInputField(form, "Value", "value", "number", "", {
    required: true,
    step: "any",
  });
  appendInputField(form, "Measured on", "measured_on", "date", localDateString(), {
    required: true,
  });
  appendInputField(form, "Confidence (0–100)", "confidence", "number", "50", {
    required: true,
    min: 0,
    max: 100,
    step: 1,
  });
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save measurement";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formObject(form);
    payload.confidence = Number(payload.confidence);
    try {
      await api(`/api/v1/metrics/${metric.id}/measurements`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
      showNotice("Measurement saved to the dated history.");
    } catch (error) {
      showNotice(error.message);
    }
  });
  return form;
}

function createMetricForm(goal) {
  const form = document.createElement("form");
  form.className = "metric-create-form";
  appendInputField(form, "Measure name", "name", "text", "", {
    required: true,
    maxLength: 120,
  });
  appendInputField(form, "Unit", "unit", "text", "", {
    required: true,
    maxLength: 40,
  });
  appendInputField(form, "Starting value (optional)", "baseline_value", "number", "", {
    step: "any",
  });
  appendInputField(form, "Target value", "target_value", "number", "", {
    required: true,
    step: "any",
  });
  appendInputField(form, "Current value (optional)", "current_value", "number", "", {
    step: "any",
  });
  appendInputField(form, "Measured on", "measured_on", "date", localDateString());
  appendInputField(form, "Confidence (0–100)", "confidence", "number", "50", {
    required: true,
    min: 0,
    max: 100,
    step: 1,
  });
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Add measure";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formObject(form);
    payload.confidence = Number(payload.confidence);
    for (const optional of ["baseline_value", "current_value", "measured_on"]) {
      if (!payload[optional]) delete payload[optional];
    }
    try {
      await api(`/api/v1/goals/${goal.id}/metrics`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
      showNotice("Measure added to this goal.");
    } catch (error) {
      showNotice(error.message);
    }
  });
  return form;
}

function createGoalEditForm(goal) {
  const form = document.createElement("form");
  form.className = "goal-edit-form";
  appendInputField(form, "Goal title", "title", "text", goal.title, {
    required: true,
    maxLength: 160,
  });
  const descriptionLabel = document.createElement("label");
  const descriptionCaption = document.createElement("span");
  descriptionCaption.textContent = "Description (optional)";
  const description = document.createElement("textarea");
  description.name = "description";
  description.maxLength = 5000;
  description.value = goal.description || "";
  descriptionLabel.append(descriptionCaption, description);
  form.append(descriptionLabel);

  appendInputField(form, "Priority (1–5)", "priority", "number", goal.priority, {
    required: true,
    min: 1,
    max: 5,
    step: 1,
  });
  const statusLabel = document.createElement("label");
  const statusCaption = document.createElement("span");
  statusCaption.textContent = "Status";
  const status = document.createElement("select");
  status.name = "status";
  for (const value of ["active", "paused", "completed", "archived"]) {
    status.add(new Option(value[0].toUpperCase() + value.slice(1), value));
  }
  status.value = goal.status;
  statusLabel.append(statusCaption, status);
  form.append(statusLabel);
  appendInputField(form, "Target date (optional)", "target_date", "date", goal.target_date || "");

  const subareaLabel = document.createElement("label");
  const subareaCaption = document.createElement("span");
  subareaCaption.textContent = "Subarea (optional)";
  const subarea = document.createElement("select");
  subarea.name = "subarea_id";
  subarea.add(new Option("No subarea", ""));
  const domain = workspaceDomains.find((item) => item.code === goal.domain);
  for (const item of domain?.subareas || []) {
    subarea.add(new Option(item.name, item.id));
  }
  subarea.value = goal.subarea_id || "";
  subareaLabel.append(subareaCaption, subarea);
  form.append(subareaLabel);

  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save goal changes";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formObject(form);
    payload.priority = Number(payload.priority);
    payload.description = payload.description.trim() || null;
    payload.target_date = payload.target_date || null;
    payload.subarea_id = payload.subarea_id || null;
    try {
      await api(`/api/v1/goals/${goal.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
      showNotice("Goal changes saved.");
    } catch (error) {
      showNotice(error.message);
    }
  });
  return form;
}

function createMetricEditForm(metric) {
  const form = document.createElement("form");
  form.className = "metric-edit-form";
  const hasHistory = metric.history.length > 0;
  appendInputField(form, "Measure name", "name", "text", metric.name, {
    required: true,
    maxLength: 120,
  });
  appendInputField(form, "Unit", "unit", "text", metric.unit, {
    required: true,
    maxLength: 40,
    disabled: hasHistory,
  });
  if (hasHistory) {
    const unitHint = document.createElement("p");
    unitHint.className = "field-hint";
    unitHint.textContent = "This measure has dated values, so its unit is locked to keep its history accurate.";
    form.append(unitHint);
  }
  appendInputField(form, "Starting value (optional)", "baseline_value", "number", metric.baseline_value ?? "", {
    step: "any",
  });
  appendInputField(form, "Target value", "target_value", "number", metric.target_value, {
    required: true,
    step: "any",
  });
  appendInputField(form, "Target date (optional)", "target_date", "date", metric.target_date || "");

  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save measure changes";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formObject(form);
    payload.baseline_value = payload.baseline_value || null;
    payload.target_date = payload.target_date || null;
    try {
      await api(`/api/v1/metrics/${metric.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
      showNotice("Measure changes saved. Dated history remains unchanged.");
    } catch (error) {
      showNotice(error.message);
    }
  });
  return form;
}

function renderGoals(goals) {
  const rows = goals.map((goal) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = goal.title;
    const domain = workspaceDomains.find((entry) => entry.code === goal.domain);
    const meta = document.createElement("small");
    meta.textContent = `${domain?.name || goal.domain.replaceAll("_", " ")}${goal.subarea_name ? ` · ${goal.subarea_name}` : ""} · ${goal.status}${goal.target_date ? ` · target ${goal.target_date}` : ""}`;
    item.append(title, meta);
    const editGoal = document.createElement("details");
    const editGoalSummary = document.createElement("summary");
    editGoalSummary.textContent = "Edit goal";
    editGoal.append(editGoalSummary, createGoalEditForm(goal));
    item.append(editGoal);
    if (goal.starting_points?.length) {
      const startingPoints = document.createElement("ul");
      startingPoints.className = "goal-starting-points";
      for (const point of goal.starting_points) {
        const entry = document.createElement("li");
        const value = point.status === "unknown"
          ? "Unknown"
          : `${point.value} ${point.unit}`;
        entry.textContent = `Starting point · ${point.metric_name}: ${value}`;
        startingPoints.append(entry);
      }
      item.append(startingPoints);
    }
    if (goal.metrics.length) {
      const metrics = document.createElement("ul");
      metrics.className = "goal-metrics";
      for (const metric of goal.metrics) {
        const metricItem = document.createElement("li");
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = `${metric.name} · ${metric.current_value ?? "—"} / ${metric.target_value} ${metric.unit}`;
        const confidence = document.createElement("small");
        confidence.textContent = `${metric.confidence}% confidence · ${metric.history.length} dated entr${metric.history.length === 1 ? "y" : "ies"}`;
        const history = document.createElement("ol");
        history.className = "metric-history";
        for (const record of metric.history) {
          const entry = document.createElement("li");
          entry.textContent = `${record.measured_on} · ${record.value} ${metric.unit} · ${record.confidence}% confidence · ${record.source}`;
          history.append(entry);
        }
        if (!metric.history.length) {
          const empty = document.createElement("li");
          empty.textContent = "No dated values recorded yet.";
          history.append(empty);
        }
        const addMeasurement = document.createElement("details");
        const addSummary = document.createElement("summary");
        addSummary.textContent = "Add a measurement";
        addMeasurement.append(addSummary, createMetricMeasurementForm(metric));
        const editMetric = document.createElement("details");
        const editMetricSummary = document.createElement("summary");
        editMetricSummary.textContent = "Edit measure";
        editMetric.append(editMetricSummary, createMetricEditForm(metric));
        details.append(summary, confidence, history, editMetric, addMeasurement);
        metricItem.append(details);
        metrics.append(metricItem);
      }
      item.append(metrics);
    }
    const addMetric = document.createElement("details");
    addMetric.className = "add-goal-metric";
    const addMetricSummary = document.createElement("summary");
    addMetricSummary.textContent = "Add a measure";
    addMetric.append(addMetricSummary, createMetricForm(goal));
    item.append(addMetric);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No goals yet. Add one when you’re ready.";
    rows.push(empty);
  }
  $("#goals").replaceChildren(...rows);
}

function createHabitCheckInForm(habit, latestAllowedDate = localDateString()) {
  const form = document.createElement("form");
  form.className = "habit-check-in-form";
  const dateLabel = document.createElement("label");
  dateLabel.textContent = "Day";
  const date = document.createElement("input");
  date.type = "date";
  date.name = "recorded_on";
  date.value = latestAllowedDate;
  if (habit.start_date) date.min = habit.start_date;
  date.max = habit.end_date && habit.end_date < latestAllowedDate
    ? habit.end_date
    : latestAllowedDate;
  if (date.value > date.max) date.value = date.max;
  date.required = true;
  dateLabel.append(date);
  const reasonLabel = document.createElement("label");
  reasonLabel.textContent = "Optional note";
  const reason = document.createElement("textarea");
  reason.name = "reason";
  reason.maxLength = 500;
  reason.rows = 2;
  reasonLabel.append(reason);
  const actions = document.createElement("div");
  actions.className = "habit-check-in-actions";
  for (const [status, label] of [["completed", "Done"], ["skipped", "Skip"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (status === "skipped") button.className = "quiet";
    button.addEventListener("click", async () => {
      if (!date.value) {
        date.reportValidity();
        return;
      }
      const payload = { status, recorded_on: date.value };
      if (reason.value.trim()) payload.reason = reason.value.trim();
      actions.querySelectorAll("button").forEach((item) => { item.disabled = true; });
      try {
        await api(`/api/v1/habits/${habit.id}/check-ins`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await loadWorkspace();
        showNotice(status === "completed" ? "Routine recorded." : "Skip recorded. You can restart whenever you choose.");
      } catch (error) {
        actions.querySelectorAll("button").forEach((item) => { item.disabled = false; });
        showNotice(error.message);
      }
    });
    actions.append(button);
  }
  form.append(dateLabel, reasonLabel, actions);
  return form;
}

function habitFrequencyLabel(habit) {
  if (habit.frequency === "daily") return "Daily";
  if (habit.frequency === "weekly") {
    const weekdayNames = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return habit.weekdays.length
      ? "Weekly · " + habit.weekdays.map((day) => weekdayNames[day]).join(", ")
      : "Once a week · any day";
  }
  if (habit.interval_days) return "Every " + habit.interval_days + " days";
  return habit.custom_schedule
    ? "Manual schedule · " + habit.custom_schedule
    : "Custom schedule";
}

function renderHabits(habits) {
  const rows = habits.map((habit) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = habit.action;
    const cue = document.createElement("small");
    cue.textContent = habit.cue + " · " + habitFrequencyLabel(habit) + (habit.is_active ? " · Active" : " · Paused");
    const minimum = document.createElement("small");
    minimum.textContent = `Small version: ${habit.minimum_version}`;
    const restart = document.createElement("small");
    restart.textContent = `Restart idea: ${habit.recovery_action}`;
    item.append(title, cue, minimum, restart);
    if (habit.start_date || habit.end_date) {
      const range = document.createElement("small");
      range.textContent = "Schedule dates: " + (habit.start_date || "any start") + " to " + (habit.end_date || "no end date");
      item.append(range);
    }
    if (habit.reminder_preference === "in_app") {
      const reminder = document.createElement("small");
      reminder.textContent = "In-app reminder: shown here when this routine is due.";
      item.append(reminder);
    }

    const controls = document.createElement("div");
    controls.className = "item-actions";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "quiet";
    toggle.textContent = habit.is_active ? "Pause routine" : "Resume routine";
    toggle.addEventListener("click", async () => {
      toggle.disabled = true;
      try {
        await api(`/api/v1/habits/${habit.id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: !habit.is_active }),
        });
        await loadWorkspace();
        showNotice(habit.is_active ? "Routine paused. Its history is kept." : "Routine resumed.");
      } catch (error) {
        toggle.disabled = false;
        showNotice(error.message);
      }
    });
    controls.append(toggle);
    item.append(controls);

    const recentCheckIns = habit.check_ins.slice(0, 7);
    if (habit.is_active) {
      const today = localDateString();
      const todayEntry = habit.check_ins.find((entry) => entry.recorded_on === today);
      const todayStatus = document.createElement("small");
      if (todayEntry) {
        todayStatus.textContent = "Today: " + (todayEntry.status === "completed" ? "Done" : "Skipped") + " · you can update this record.";
      } else if (habit.due_today) {
        todayStatus.textContent = "Due today · check in whenever you’re ready.";
      } else if (habit.next_due_on) {
        todayStatus.textContent = "Next check-in: " + habit.next_due_on;
      } else {
        todayStatus.textContent = "No upcoming check-in in this date range.";
      }
      item.append(todayStatus);
      if (habit.due_today) {
        item.append(createHabitCheckInForm(habit));
      } else {
        const latestPastDate = previousDateString(today);
        const pastDateLimit = habit.end_date && habit.end_date < latestPastDate
          ? habit.end_date
          : latestPastDate;
        if (!habit.start_date || habit.start_date <= pastDateLimit) {
          const pastCheckIn = document.createElement("details");
          const summary = document.createElement("summary");
          summary.textContent = "Log or correct an earlier check-in";
          pastCheckIn.append(
            summary,
            createHabitCheckInForm(habit, pastDateLimit),
          );
          item.append(pastCheckIn);
        }
      }
    } else {
      const paused = document.createElement("small");
      paused.textContent = "Paused. No check-ins are needed until you resume it.";
      item.append(paused);
    }
    if (recentCheckIns.length) {
      const history = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Recent check-ins";
      const entries = document.createElement("ul");
      entries.className = "record-list";
      for (const entry of recentCheckIns) {
        const line = document.createElement("li");
        const label = document.createElement("small");
        label.textContent = `${entry.recorded_on} · ${entry.status === "completed" ? "Done" : "Skipped"}${entry.reason ? ` · ${entry.reason}` : ""}`;
        line.append(label);
        entries.append(line);
      }
      history.append(summary, entries);
      item.append(history);
    }
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No routines yet. Start with a small action you can repeat.";
    rows.push(empty);
  }
  $("#habits").replaceChildren(...rows);
}

async function loadWorkspace() {
  $("#auth").hidden = true;
  $("#workspace").hidden = false;
  $("#logout").hidden = false;
  if (!$("#daily-plan-date").value) $("#daily-plan-date").value = localDateString();
  const planDate = $("#daily-plan-date").value;
  const [domains, goals, habits, preview, rpg, insights, inbox, awakening, campaigns, reviews, consents, tasks, quests, currentPlan, recovery, dailyReflection, skills, chronicle, agentActions] = await Promise.all([
    api("/api/v1/domains"), api("/api/v1/goals"), api("/api/v1/habits"), api("/api/v1/plans/preview"), api("/api/v1/rpg/status"), api("/api/v1/insights/progress"), api("/api/v1/notifications/inbox"),
    api("/api/v1/onboarding/awakening"), api("/api/v1/campaigns"), api("/api/v1/reviews"), api("/api/v1/consents"), api("/api/v1/tasks"),
    api("/api/v1/quests"),
    api(`/api/v1/daily-plans/${planDate}`), api(`/api/v1/daily-plans/${planDate}/recovery`),
    api(`/api/v1/daily-plans/${planDate}/reflection`),
    api("/api/v1/rpg/skills"), api("/api/v1/rpg/chronicle"), api("/api/v1/agent/actions"),
  ]);
  const latestReflectionConsent = consents
    .filter((record) => record.purpose === "reflection_storage")
    .reverse()[0];
  reflectionStorageConsent = Boolean(latestReflectionConsent?.granted);
  $("#reflection-consent").checked = reflectionStorageConsent;
  workspaceDomains = domains;
  workspaceGoals = goals;
  workspaceQuests = quests;
  renderDomainSettings(domains);
  renderDomainSubareas(domains);
  const activeDomains = domains.filter((domain) => domain.enabled);
  const domainSelect = $("#goal-form select[name='domain']");
  domainSelect.replaceChildren(...activeDomains.map((domain) => new Option(domain.name, domain.code)));
  updateGoalSubareaOptions();
  $("#skill-domain").replaceChildren(new Option("Choose a domain", ""), ...activeDomains.map((domain) => new Option(domain.name, domain.code)));
  const activeGoals = goals.filter((goal) => goal.status === "active");
  $("#agent-goal").replaceChildren(...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#task-goal").replaceChildren(new Option("No goal selected", ""), ...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#habit-goal").replaceChildren(new Option("No goal linked", ""), ...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#quest-goal").replaceChildren(new Option("No goal linked", ""), ...activeGoals.map((goal) => new Option(goal.title, goal.id)));
  $("#agent-form button").disabled = activeGoals.length === 0;
  workspaceTasks = tasks;
  dailyPlan = currentPlan;
  workspaceProgress = rpg;
  renderGoals(goals);
  renderQuests(quests);
  renderHabits(habits);
  renderPlan(preview);
  renderDailyPlan(currentPlan);
  renderRecovery(recovery);
  renderDailyReflection(dailyReflection);
  renderProgress(rpg);
  renderInsights(insights);
  renderInbox(inbox);
  renderAwakening(awakening);
  renderCampaigns(campaigns);
  renderReviews(reviews, goals);
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
    const questStep = workspaceQuests.flatMap((quest) => quest.steps.map((step) => ({ quest, step })))
      .find(({ step }) => step.task_id === task.id);
    const metadata = [];
    if (task.due_date) metadata.push(`Due ${task.due_date}`);
    else metadata.push(task.status === "completed" ? "Completed" : "Open action");
    if (questStep) {
      metadata.push(`${questStep.quest.title} · Step ${questStep.step.position + 1} of ${questStep.quest.total_steps}`);
    }
    meta.textContent = metadata.join(" · ");
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
  $("#day-start-time").value = plan.day_start_time || "09:00";
  $("#day-end-time").value = plan.day_end_time || "21:00";
  renderBusyWindowEditor(plan.busy_windows || []);
  const calendarExport = $("#calendar-plan-export");
  const hasTimedActions = plan.items.some((item) =>
    item.status === "planned" && item.suggested_start && item.suggested_end
  );
  calendarExport.href = `/api/v1/daily-plans/${plan.plan_date}/calendar.ics`;
  calendarExport.hidden = !plan.is_saved || !hasTimedActions;
  $("#calendar-plan-export-hint").hidden = !plan.is_saved || !hasTimedActions;
  const energyLabels = { low: "Low energy", medium: "Steady energy", high: "High energy" };
  $("#plan-energy-label").textContent = energyLabels[plan.energy] || "Energy";
  $("#time-block-summary").textContent = plan.is_saved
    ? "Suggested times follow your chosen order and leave busy times clear. Adjust them whenever you need."
    : "Save your choices to see suggested action times.";
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
    const suggestedTime = planItem.suggested_start && planItem.suggested_end
      ? ` · suggested ${planItem.suggested_start}–${planItem.suggested_end}`
      : planItem.status === "planned" ? " · no open time slot fits" : "";
    meta.textContent = `${planItem.planned_minutes} min · ${statusLabels[planItem.status] || planItem.status}${suggestedTime}${planItem.deferred_to ? ` · ${planItem.deferred_to}` : ""}${originalDue}`;
    copy.append(title, meta);
    if (planItem.reschedule_history?.length) {
      const history = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `Reschedule history · ${planItem.reschedule_history.length}`;
      const entries = document.createElement("ol");
      for (const event of planItem.reschedule_history) {
        const entry = document.createElement("li");
        const prior = event.previous_due_date
          ? `previously due ${event.previous_due_date}`
          : "no previous due date";
        const next = event.defer_to
          ? `deferred to ${event.defer_to}`
          : "deferred without a new due date";
        entry.textContent = `${event.plan_date} · ${prior} · ${next}`;
        entries.append(entry);
      }
      history.append(summary, entries);
      copy.append(history);
    }
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

function createBusyWindowRow(window = {}) {
  const row = document.createElement("div");
  row.className = "busy-window-row";
  for (const [caption, name, value] of [
    ["Busy from", "start_time", window.start_time || ""],
    ["Busy until", "end_time", window.end_time || ""],
  ]) {
    const label = document.createElement("label");
    const text = document.createElement("span");
    text.textContent = caption;
    const input = document.createElement("input");
    input.type = "time";
    input.dataset.busyTime = name;
    input.value = value;
    input.required = true;
    label.append(text, input);
    row.append(label);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "text-button";
  remove.textContent = "Remove";
  remove.setAttribute("aria-label", "Remove busy time");
  remove.addEventListener("click", () => row.remove());
  row.append(remove);
  return row;
}

function renderBusyWindowEditor(windows) {
  $("#busy-window-list").replaceChildren(...windows.map(createBusyWindowRow));
}

function mergeTimeWindows(windows) {
  const sorted = windows
    .filter((window) => window.start_time && window.end_time)
    .map((window) => ({ ...window }))
    .sort((left, right) => left.start_time.localeCompare(right.start_time));
  const merged = [];
  for (const window of sorted) {
    const previous = merged.at(-1);
    if (previous && window.start_time <= previous.end_time) {
      if (window.end_time > previous.end_time) previous.end_time = window.end_time;
    } else {
      merged.push(window);
    }
  }
  return merged;
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

function renderDailyReflection(reflection) {
  const form = $("#daily-reflection-form");
  const responses = reflection?.responses || {};
  for (const field of ["wins", "friction", "energy_note", "tomorrow_support"]) {
    form.elements[field].value = responses[field] || "";
    form.elements[field].disabled = !reflection?.storage_consent;
  }
  $("#daily-reflection-save").disabled = !reflection?.storage_consent;
  $("#daily-reflection-delete").disabled = !reflection?.has_reflection;
  if (!reflection?.storage_consent) {
    $("#daily-reflection-state").textContent = reflection?.has_reflection
      ? "Storage permission is off. Your earlier reflection is still saved; you can delete it here."
      : "Turn on reflection storage in Settings before saving a private check-in.";
  } else {
    $("#daily-reflection-state").textContent = reflection.has_reflection
      ? "Saved for this day. You can edit it or delete it."
      : "Nothing is saved until you choose Save reflection.";
  }
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
  $("#awakening-focus").textContent = step.focus;
  $("#awakening-question-title").textContent = step.title;
  $("#awakening-prompt").textContent = step.prompt;
  $("#awakening-answer").value = step.answer || "";
  $("#awakening-consent").checked = awakening.storage_consent;
  $("#awakening-previous").disabled = awakeningStepIndex === 0;
  $("#awakening-save").textContent = awakeningStepIndex === awakening.steps.length - 1 ? "Complete prompt" : "Complete and continue";
  $("#awakening-skip").textContent = step.status === "skipped" ? "Keep skipped" : "Skip this prompt";
  $("#awakening-complete").hidden = resolved !== awakening.steps.length;
  renderAwakeningAssessments(awakening, step);
  renderAwakeningBaselines(awakening, step);
}

const awakeningAssessmentGuidance = {
  career: "Work, skills, opportunities, or changes you want to explore.",
  fitness: "Movement, training, nutrition, and recovery, in terms that suit you.",
  finance: "Money-related routines or goals. Exact amounts are not needed.",
  discipline: "Focus, routines, and follow-through without judging missed days.",
  learning: "Knowledge or skills you have now and would like to develop.",
  mental_wellness: "What supports your wellbeing. This is not a diagnosis or treatment tool.",
  relationships: "Connection, commitments, and boundaries that matter to you.",
  lifestyle: "Sleep, surroundings, and everyday rhythms that shape your life.",
};

function renderAwakeningAssessments(awakening, step) {
  const panel = $("#awakening-assessment-panel");
  const relevantSteps = [2, 5, 6];
  panel.hidden = !relevantSteps.includes(step.day);
  if (panel.hidden) return;

  const allowedCodes = step.day === 5
    ? new Set(["fitness", "mental_wellness", "discipline"])
    : step.day === 6
      ? new Set(["finance", "relationships", "lifestyle"])
      : null;
  const domains = workspaceDomains.filter((domain) => !allowedCodes || allowedCodes.has(domain.code));
  const assessments = new Map((awakening.assessments || []).map((item) => [item.domain, item]));
  const fields = [
    ["current_reality", "Current reality", "What is life like in this area now?"],
    ["desired_direction", "Strength or direction", "What would you like to maintain, develop, or change?"],
    ["experiment", "Small real-world check (optional)", "What low-risk action or observation could help you learn more?"],
  ];
  const consent = Boolean(awakening.storage_consent);
  const rows = domains.map((domain) => {
    const saved = assessments.get(domain.code);
    const details = document.createElement("details");
    details.open = Boolean(saved);
    const summary = document.createElement("summary");
    summary.textContent = saved ? `${domain.name} · notes saved` : domain.name;
    const guidance = document.createElement("p");
    guidance.className = "field-hint assessment-guidance";
    guidance.textContent = awakeningAssessmentGuidance[domain.code] || domain.description;
    const form = document.createElement("form");

    for (const [name, labelText, placeholder] of fields) {
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("textarea");
      input.name = name;
      input.maxLength = 1200;
      input.rows = 3;
      input.placeholder = placeholder;
      input.value = saved?.[name] || "";
      input.disabled = !consent;
      label.append(input);
      form.append(label);
    }

    const save = document.createElement("button");
    save.type = "submit";
    save.textContent = saved ? "Save changes" : "Save area notes";
    save.disabled = !consent;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = Object.fromEntries(fields.map(([name]) => [name, form.elements[name].value]));
      save.disabled = true;
      try {
        const result = await api(`/api/v1/onboarding/awakening/assessments/${domain.code}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        const updated = awakeningData.assessments || [];
        awakeningData.assessments = result.assessment
          ? [...updated.filter((item) => item.domain !== domain.code), result.assessment]
          : updated.filter((item) => item.domain !== domain.code);
        summary.textContent = result.saved ? `${domain.name} · notes saved` : domain.name;
        save.textContent = result.saved ? "Save changes" : "Save area notes";
        save.disabled = !awakeningData.storage_consent;
        showNotice(result.saved ? `${domain.name} notes saved.` : `${domain.name} notes cleared.`);
      } catch (error) {
        save.disabled = !awakeningData.storage_consent;
        showNotice(error.message);
      }
    });

    form.append(save);
    details.append(summary, guidance, form);
    return details;
  });
  const empty = document.createElement("p");
  empty.className = "field-hint";
  empty.textContent = "Allow reflection storage above to save or edit these notes.";
  empty.hidden = consent;
  $("#awakening-assessment-list").replaceChildren(empty, ...rows);
}

function syncAwakeningBaselineForm() {
  const form = $("#awakening-baseline-form");
  const consent = Boolean(awakeningData?.baseline_storage_consent);
  const known = form.elements.status.value === "recorded";
  const fields = $("#awakening-baseline-value-fields");
  fields.hidden = !known;
  for (const input of fields.querySelectorAll("input")) {
    input.disabled = !consent || !known;
    input.required = consent && known && ["value", "unit"].includes(input.name);
  }
  form.elements.domain.disabled = !consent;
  form.elements.metric_name.disabled = !consent;
  form.elements.status.disabled = !consent;
  form.querySelector('button[type="submit"]').disabled = !consent;
}

function renderAwakeningBaselines(awakening, step) {
  const panel = $("#awakening-baseline-panel");
  const relevantSteps = [2, 5, 6];
  panel.hidden = !relevantSteps.includes(step.day);
  if (panel.hidden) return;

  const allowedCodes = step.day === 5
    ? new Set(["fitness", "mental_wellness", "discipline"])
    : step.day === 6
      ? new Set(["finance", "relationships", "lifestyle"])
      : null;
  const domains = workspaceDomains.filter((domain) => !allowedCodes || allowedCodes.has(domain.code));
  $("#awakening-baseline-title").textContent = step.day === 5
    ? "Optional health, sleep, and routine starting points"
    : step.day === 6
      ? "Optional finance, relationships, and lifestyle starting points"
      : "Starting points across your life areas";
  $("#awakening-baseline-intro").textContent = step.day === 2
    ? "Review all your life areas. Add a number you already know, or mark a starting point unknown. No target or overall score is created."
    : step.day === 5
      ? "Optional: add a measure you choose, or mark it unknown. You can skip this section and begin using the app. No diagnosis or health score is created."
      : "Optional: add a measure you choose, or mark it unknown. You can skip this section and begin using the app. No value is assumed.";
  $("#awakening-baseline-consent").checked = Boolean(awakening.baseline_storage_consent);
  const form = $("#awakening-baseline-form");
  const selectedDomain = domains.some((domain) => domain.code === form.elements.domain.value)
    ? form.elements.domain.value
    : domains[0]?.code;
  form.elements.domain.replaceChildren(...domains.map((domain) => new Option(domain.name, domain.code)));
  if (selectedDomain) form.elements.domain.value = selectedDomain;
  syncAwakeningBaselineForm();

  const list = $("#awakening-baselines");
  const records = awakening.baselines || [];
  const rows = domains.map((domain) => {
    const item = document.createElement("li");
    item.className = "baseline-domain-item";
    const title = document.createElement("strong");
    title.textContent = domain.name;
    const domainRecords = records.filter((record) => record.domain === domain.code);
    const detail = document.createElement("small");
    detail.textContent = domainRecords.length
      ? `${domainRecords.length} starting point${domainRecords.length === 1 ? "" : "s"} saved`
      : "No starting point recorded yet";
    item.append(title, detail);

    const history = document.createElement("ul");
    history.className = "baseline-history";
    for (const record of domainRecords) {
      const entry = document.createElement("li");
      const summary = document.createElement("span");
      summary.textContent = record.status === "unknown"
        ? `${record.metric_name}: Unknown`
        : `${record.metric_name}: ${record.value} ${record.unit}`;
      const meta = document.createElement("small");
      const measured = record.measured_on ? `Measured ${record.measured_on}` : "Measurement date not provided";
      meta.textContent = `${measured} · ${record.confidence}% confidence · entered ${new Date(record.recorded_at).toLocaleDateString()}`;
      entry.append(summary, meta);
      if (record.goal_id) {
        const goalLink = document.createElement("small");
        goalLink.textContent = `Linked to goal: ${record.goal_title || "Active goal"}`;
        entry.append(goalLink);
        const unlink = document.createElement("button");
        unlink.type = "button";
        unlink.className = "text-button";
        unlink.textContent = "Unlink from goal";
        unlink.addEventListener("click", async () => {
          const stepIndex = awakeningStepIndex;
          try {
            await api(`/api/v1/onboarding/awakening/baselines/${record.id}/goal-link`, {
              method: "DELETE",
            });
            await loadWorkspace();
            renderAwakening(awakeningData, stepIndex);
            showNotice("Starting point unlinked. Both records are kept.");
          } catch (error) {
            showNotice(error.message);
          }
        });
        entry.append(unlink);
      } else {
        const linkDetails = document.createElement("details");
        const linkSummary = document.createElement("summary");
        linkSummary.textContent = "Link to an active goal";
        linkDetails.append(linkSummary);
        const candidates = workspaceGoals.filter(
          (goal) => goal.status === "active" && goal.domain === domain.code,
        );
        if (!candidates.length) {
          const noGoals = document.createElement("small");
          noGoals.textContent = "Create an active goal in this life area before linking this starting point.";
          linkDetails.append(noGoals);
        } else {
          const goalLabel = document.createElement("label");
          goalLabel.textContent = `Choose an active ${domain.name} goal`;
          const goalSelect = document.createElement("select");
          goalSelect.append(new Option("Choose a goal", ""));
          candidates.forEach((goal) => goalSelect.append(new Option(goal.title, goal.id)));
          goalLabel.append(goalSelect);
          const linkButton = document.createElement("button");
          linkButton.type = "button";
          linkButton.textContent = "Link starting point";
          linkButton.disabled = !awakening.baseline_storage_consent;
          linkButton.addEventListener("click", async () => {
            if (!goalSelect.value) {
              goalSelect.focus();
              showNotice("Choose a goal in this life area first.");
              return;
            }
            const stepIndex = awakeningStepIndex;
            linkButton.disabled = true;
            try {
              await api(`/api/v1/onboarding/awakening/baselines/${record.id}/goal-link`, {
                method: "POST",
                body: JSON.stringify({ goal_id: goalSelect.value }),
              });
              await loadWorkspace();
              renderAwakening(awakeningData, stepIndex);
              showNotice("Starting point linked to the selected goal. No target or score was created.");
            } catch (error) {
              linkButton.disabled = false;
              showNotice(error.message);
            }
          });
          linkDetails.append(goalLabel, linkButton);
        }
        if (!awakening.baseline_storage_consent) {
          const consentHint = document.createElement("small");
          consentHint.textContent = "Grant starting-point storage permission to create a link.";
          linkDetails.append(consentHint);
        }
        entry.append(linkDetails);
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-button";
      remove.textContent = "Delete entry";
      remove.addEventListener("click", async () => {
        const confirmText = record.goal_id
          ? `Delete this starting point and unlink it from ${record.goal_title || "its goal"}? This cannot be undone.`
          : "Delete this starting point from your history? This cannot be undone.";
        if (!window.confirm(confirmText)) return;
        const stepIndex = awakeningStepIndex;
        try {
          await api(`/api/v1/onboarding/awakening/baselines/${record.id}`, { method: "DELETE" });
          await loadWorkspace();
          renderAwakening(awakeningData, stepIndex);
          showNotice("Starting point deleted.");
        } catch (error) {
          showNotice(error.message);
        }
      });
      entry.append(remove);
      history.append(entry);
    }
    if (domainRecords.length) item.append(history);

    const overall = domainRecords
      .filter((record) => record.metric_name === "Overall baseline")
      .at(-1);
    if (overall?.status !== "unknown") {
      const markUnknown = document.createElement("button");
      markUnknown.type = "button";
      markUnknown.className = "quiet baseline-unknown";
      markUnknown.textContent = "Mark overall baseline unknown";
      markUnknown.disabled = !awakening.baseline_storage_consent;
      markUnknown.addEventListener("click", async () => {
        const stepIndex = awakeningStepIndex;
        try {
          await api("/api/v1/onboarding/awakening/baselines", {
            method: "POST",
            body: JSON.stringify({
              domain: domain.code,
              metric_name: "Overall baseline",
              status: "unknown",
              confidence: 50,
            }),
          });
          await loadWorkspace();
          renderAwakening(awakeningData, stepIndex);
          showNotice(`${domain.name} marked unknown. You can add a value later.`);
        } catch (error) {
          showNotice(error.message);
        }
      });
      item.append(markUnknown);
    }
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No active life areas are available for this assessment day.";
    rows.push(empty);
  }
  list.replaceChildren(...rows);
}

function renderCampaigns(campaigns) {
  const rows = campaigns.map((campaign) => {
    const item = document.createElement("li");
    item.className = "campaign-card";
    const title = document.createElement("strong");
    title.textContent = campaign.title;
    const detail = document.createElement("small");
    detail.textContent = `${campaign.starts_on} to ${campaign.ends_on} · ${campaign.status}`;
    const objective = document.createElement("p");
    objective.textContent = campaign.objective;
    const workspace = document.createElement("details");
    workspace.className = "campaign-workspace";
    const summary = document.createElement("summary");
    summary.textContent = "Open 90-day plan";
    workspace.append(summary);

    const campaignForm = document.createElement("form");
    campaignForm.className = "campaign-edit-form";
    appendInputField(campaignForm, "Campaign title", "title", "text", campaign.title, { required: true, maxLength: 160 });
    appendTextareaField(campaignForm, "Objective", "objective", campaign.objective, 2000);
    appendSelectField(campaignForm, "Campaign status", "status", campaign.status, ["active", "paused", "completed", "archived"]);
    appendTextareaField(campaignForm, "Reason for an objective change (optional)", "scope_change_reason", "", 1200);
    addCampaignSubmit(campaignForm, `/api/v1/campaigns/${campaign.id}`, "PATCH", "Campaign updated.");
    workspace.append(campaignForm);

    const arcsHeading = document.createElement("h3");
    arcsHeading.textContent = "Weekly arcs";
    workspace.append(arcsHeading);
    for (const arc of campaign.arcs || []) {
      const arcDetails = document.createElement("details");
      arcDetails.className = "campaign-arc";
      const arcSummary = document.createElement("summary");
      arcSummary.textContent = `Week ${arc.week_number} · ${arc.starts_on} to ${arc.ends_on} · ${arc.status}`;
      const arcForm = document.createElement("form");
      appendInputField(arcForm, "Week title", "title", "text", arc.title, { required: true, maxLength: 160 });
      appendTextareaField(arcForm, "Weekly focus", "focus", arc.focus || "", 2000);
      appendSelectField(arcForm, "Week status", "status", arc.status, ["planned", "active", "completed", "skipped"]);
      addCampaignSubmit(arcForm, `/api/v1/campaigns/${campaign.id}/arcs/${arc.id}`, "PATCH", `Week ${arc.week_number} updated.`);
      arcDetails.append(arcSummary, arcForm);

      const checkpointsHeading = document.createElement("h4");
      checkpointsHeading.textContent = "Checkpoints";
      arcDetails.append(checkpointsHeading);
      const checkpointList = document.createElement("ul");
      checkpointList.className = "campaign-checkpoints";
      for (const checkpoint of arc.checkpoints || []) {
        const checkpointRow = document.createElement("li");
        const checkpointForm = document.createElement("form");
        checkpointForm.className = "campaign-checkpoint-form";
        appendInputField(checkpointForm, "Checkpoint", "title", "text", checkpoint.title, { required: true, maxLength: 160 });
        const dueDate = appendInputField(checkpointForm, "Due date", "due_on", "date", checkpoint.due_on, { required: true });
        dueDate.min = arc.starts_on;
        dueDate.max = arc.ends_on;
        appendSelectField(checkpointForm, "Status", "status", checkpoint.status, ["pending", "completed", "skipped"]);
        addCampaignSubmit(checkpointForm, `/api/v1/campaigns/${campaign.id}/checkpoints/${checkpoint.id}`, "PATCH", "Checkpoint updated.");
        checkpointRow.append(checkpointForm);
        checkpointList.append(checkpointRow);
      }
      if (!arc.checkpoints?.length) {
        const empty = document.createElement("li");
        empty.textContent = "No checkpoints for this week yet.";
        checkpointList.append(empty);
      }
      arcDetails.append(checkpointList);

      const checkpointForm = document.createElement("form");
      checkpointForm.className = "campaign-checkpoint-create";
      const checkpointTitle = appendInputField(checkpointForm, "Add a checkpoint", "title", "text", "", { required: true, maxLength: 160 });
      checkpointTitle.placeholder = "A small, observable milestone";
      const checkpointDate = appendInputField(checkpointForm, "Due date", "due_on", "date", arc.starts_on, { required: true });
      checkpointDate.min = arc.starts_on;
      checkpointDate.max = arc.ends_on;
      addCampaignSubmit(checkpointForm, `/api/v1/campaigns/${campaign.id}/arcs/${arc.id}/checkpoints`, "POST", "Checkpoint added.");
      arcDetails.append(checkpointForm);
      workspace.append(arcDetails);
    }

    const scopeHeading = document.createElement("h3");
    scopeHeading.textContent = "Objective changes";
    workspace.append(scopeHeading);
    const scopeList = document.createElement("ul");
    scopeList.className = "campaign-scope-history";
    for (const change of campaign.scope_changes || []) {
      const entry = document.createElement("li");
      const summaryText = document.createElement("p");
      summaryText.textContent = `${change.previous_objective} → ${change.new_objective}`;
      const reasonText = document.createElement("small");
      reasonText.textContent = change.reason || "No reason recorded.";
      entry.append(summaryText, reasonText);
      scopeList.append(entry);
    }
    if (!campaign.scope_changes?.length) {
      const empty = document.createElement("li");
      empty.textContent = "No objective changes recorded.";
      scopeList.append(empty);
    }
    workspace.append(scopeList);

    const retrospectiveDetails = document.createElement("details");
    retrospectiveDetails.className = "campaign-retrospective";
    const retrospectiveSummary = document.createElement("summary");
    retrospectiveSummary.textContent = "Campaign retrospective";
    const retrospective = campaign.retrospective || {};
    const retrospectiveForm = document.createElement("form");
    for (const [key, label] of [["wins", "What went well?"], ["blockers", "What got in the way?"], ["learnings", "What did you learn?"], ["next_focus", "What will you focus on next?"]]) {
      const field = appendTextareaField(retrospectiveForm, label, key, retrospective[key] || "", 3000);
      field.disabled = !reflectionStorageConsent;
      field.rows = 3;
    }
    const saveRetrospective = document.createElement("button");
    saveRetrospective.type = "submit";
    saveRetrospective.textContent = "Save retrospective";
    saveRetrospective.disabled = !reflectionStorageConsent;
    retrospectiveForm.append(saveRetrospective);
    retrospectiveForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/campaigns/${campaign.id}/retrospective`, { method: "PUT", body: JSON.stringify(formObject(retrospectiveForm)) });
        await loadWorkspace();
        showNotice("Campaign retrospective saved.");
      } catch (error) { showNotice(error.message); }
    });
    const deleteRetrospective = document.createElement("button");
    deleteRetrospective.type = "button";
    deleteRetrospective.className = "quiet";
    deleteRetrospective.textContent = "Delete saved retrospective";
    deleteRetrospective.disabled = !campaign.retrospective;
    deleteRetrospective.addEventListener("click", async () => {
      try {
        await api(`/api/v1/campaigns/${campaign.id}/retrospective`, { method: "DELETE" });
        await loadWorkspace();
        showNotice("Saved retrospective deleted.");
      } catch (error) { showNotice(error.message); }
    });
    const consentHint = document.createElement("p");
    consentHint.className = "hint";
    consentHint.textContent = reflectionStorageConsent
      ? "Saved locally and included in your account export."
      : "Allow reflection storage in Reviews before saving. You can delete saved notes at any time.";
    retrospectiveDetails.append(retrospectiveSummary, retrospectiveForm, deleteRetrospective, consentHint);
    workspace.append(retrospectiveDetails);

    item.append(title, detail, objective, workspace);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "Start a 90-day campaign to set a direction and weekly focus.";
    rows.push(empty);
  }
  $("#campaigns").replaceChildren(...rows);
}

function appendTextareaField(form, caption, name, value = "", maxLength = 1200) {
  const label = document.createElement("label");
  label.textContent = caption;
  const textarea = document.createElement("textarea");
  textarea.name = name;
  textarea.value = value;
  textarea.maxLength = maxLength;
  textarea.rows = 3;
  label.append(textarea);
  form.append(label);
  return textarea;
}

function appendSelectField(form, caption, name, selectedValue, choices) {
  const label = document.createElement("label");
  label.textContent = caption;
  const select = document.createElement("select");
  select.name = name;
  for (const choice of choices) {
    const option = document.createElement("option");
    option.value = choice;
    option.textContent = choice.replaceAll("_", " ");
    option.selected = choice === selectedValue;
    select.append(option);
  }
  label.append(select);
  form.append(label);
  return select;
}

function addCampaignSubmit(form, url, method, successMessage) {
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Save";
  form.append(button);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(url, { method, body: JSON.stringify(formObject(form)) });
      await loadWorkspace();
      showNotice(successMessage);
    } catch (error) { showNotice(error.message); }
  });
}

function renderReviews(reviews, goals) {
  const rows = reviews.map((review) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${review.cadence} review · ${review.period_start} to ${review.period_end}`;
    const detail = document.createElement("small");
    detail.textContent = review.status === "completed" ? "Completed" : "Draft";
    const disclosure = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Open review prompts";
    const form = document.createElement("form");
    form.className = "guided-review-form";
    const responseKeys = ["wins", "blockers", "changes", "next_step"];
    const steps = responseKeys.map((key, index) => {
      const fieldset = document.createElement("fieldset");
      fieldset.className = "guided-review-step";
      const legend = document.createElement("legend");
      legend.textContent = `Prompt ${index + 1} of ${responseKeys.length}`;
      const label = document.createElement("label");
      label.textContent = review.prompts[key];
      const answer = document.createElement("textarea");
      answer.name = key;
      answer.maxLength = 1200;
      answer.rows = 3;
      answer.value = review.responses[key] || "";
      answer.disabled = !reflectionStorageConsent;
      label.append(answer);
      fieldset.append(legend, label);
      form.append(fieldset);
      return fieldset;
    });
    const stepProgress = document.createElement("p");
    stepProgress.className = "review-step-progress";
    stepProgress.setAttribute("aria-live", "polite");
    form.prepend(stepProgress);
    const actions = document.createElement("div");
    actions.className = "review-step-actions";
    let currentStep = 0;
    const previous = document.createElement("button");
    previous.type = "button";
    previous.className = "quiet";
    previous.textContent = "Previous prompt";
    previous.addEventListener("click", () => setReviewStep(currentStep - 1));
    const next = document.createElement("button");
    next.type = "submit";
    next.dataset.reviewAction = "next";
    next.textContent = "Save and continue";
    const save = document.createElement("button");
    save.type = "submit";
    save.dataset.reviewAction = "save";
    save.textContent = "Save for later";
    save.disabled = !reflectionStorageConsent;
    const complete = document.createElement("button");
    complete.type = "submit";
    complete.dataset.reviewAction = "complete";
    complete.className = "quiet";
    complete.textContent = review.status === "completed" ? "Reopen review" : "Complete review";
    actions.append(previous, next, save, complete);
    form.append(actions);
    function setReviewStep(index) {
      currentStep = Math.max(0, Math.min(index, steps.length - 1));
      steps.forEach((step, stepIndex) => { step.hidden = stepIndex !== currentStep; });
      stepProgress.textContent = `Prompt ${currentStep + 1} of ${steps.length}`;
      previous.disabled = currentStep === 0;
      next.hidden = currentStep === steps.length - 1;
      complete.hidden = currentStep !== steps.length - 1;
      if (!reflectionStorageConsent) {
        stepProgress.textContent += " · enable reflection storage to save answers";
      }
    }
    setReviewStep(0);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const action = event.submitter?.dataset.reviewAction || "save";
      const payload = {};
      if (reflectionStorageConsent) {
        payload.responses = Object.fromEntries(
          responseKeys.map((key) => [key, form.elements[key].value.trim() || null]),
        );
      }
      if (action === "next") {
        if (reflectionStorageConsent) {
          try {
            const updated = await api(`/api/v1/reviews/${review.id}`, {
              method: "PATCH",
              body: JSON.stringify({ status: review.status, responses: payload.responses }),
            });
            review.responses = updated.responses;
          } catch (error) {
            showNotice(error.message);
            return;
          }
        }
        setReviewStep(currentStep + 1);
        showNotice(reflectionStorageConsent
          ? "Answer saved. Continue when you’re ready."
          : "You can review each prompt. Enable reflection storage to save answers.");
        return;
      }
      if (action === "save") payload.status = "draft";
      if (action === "complete") {
        payload.status = review.status === "completed" ? "draft" : "completed";
      }
      try {
        const updated = await api(`/api/v1/reviews/${review.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        review.responses = updated.responses;
        review.status = updated.status;
        detail.textContent = review.status === "completed" ? "Completed" : "Draft";
        if (action === "complete") {
          await loadWorkspace();
          showNotice(review.status === "completed"
            ? "Review completed. You can revisit it later."
            : "Review reopened as a draft.");
        } else {
          showNotice("Review saved as a draft.");
        }
      } catch (error) {
        showNotice(error.message);
      }
    });
    if (Object.values(review.responses).some((value) => value.trim())) {
      const deleteAnswers = document.createElement("button");
      deleteAnswers.type = "button";
      deleteAnswers.className = "text-button";
      deleteAnswers.textContent = "Delete saved answers";
      deleteAnswers.addEventListener("click", async () => {
        if (!window.confirm("Delete the saved answers for this review? This cannot be undone.")) return;
        try {
          const result = await api(`/api/v1/reviews/${review.id}/responses`, { method: "DELETE" });
          await loadWorkspace();
          showNotice(`${result.deleted_fields} saved answer${result.deleted_fields === 1 ? "" : "s"} deleted.`);
        } catch (error) {
          showNotice(error.message);
        }
      });
      form.append(deleteAnswers);
    }
    disclosure.append(summary, form);
    const nextStep = (review.responses.next_step || "").trim();
    if ((review.status === "completed" && nextStep) || review.follow_up_task_id) {
      const carryForward = document.createElement("div");
      carryForward.className = "review-carry-forward";
      const explanation = document.createElement("p");
      explanation.className = "field-hint";
      explanation.textContent = "This saves the next step as a separate task. It will not enter a daily plan unless you pick it. Deleting the review answers will not delete this task.";
      carryForward.append(explanation);
      if (review.follow_up_task_id) {
        const saved = document.createElement("small");
        saved.textContent = "This review already has a follow-up task. Choose a day plan if you want to schedule it.";
        const chooseTask = document.createElement("button");
        chooseTask.type = "button";
        chooseTask.className = "quiet";
        const findTaskChoice = () => [...$("#task-options").querySelectorAll("[data-plan-task]")]
          .find((checkbox) => checkbox.dataset.planTask === review.follow_up_task_id);
        const taskChoice = findTaskChoice();
        chooseTask.disabled = !taskChoice;
        chooseTask.textContent = "Choose for the selected day plan";
        chooseTask.addEventListener("click", () => {
          const currentChoice = findTaskChoice();
          if (!currentChoice) {
            showNotice("This follow-up task is no longer open to plan.");
            return;
          }
          if (currentChoice.checked) {
            showNotice("Follow-up is already selected. Save the day plan when you’re ready.");
            $("#today").scrollIntoView({
              behavior: document.documentElement.dataset.reduceMotion === "true" ? "auto" : "smooth",
              block: "start",
            });
            currentChoice.focus();
            return;
          }
          currentChoice.checked = true;
          currentChoice.dispatchEvent(new Event("change", { bubbles: true }));
          $("#today").scrollIntoView({
            behavior: document.documentElement.dataset.reduceMotion === "true" ? "auto" : "smooth",
            block: "start",
          });
          currentChoice.focus();
          showNotice("Follow-up selected. Save the day plan when you’re ready.");
        });
        carryForward.append(saved, chooseTask);
      } else {
        const goalLabel = document.createElement("label");
        goalLabel.textContent = "Link to a goal (optional)";
        const goalSelect = document.createElement("select");
        goalSelect.append(new Option("No goal link", ""));
        goals
          .filter((goal) => goal.status === "active")
          .forEach((goal) => goalSelect.append(new Option(goal.title, goal.id)));
        goalLabel.append(goalSelect);
        const createTask = document.createElement("button");
        createTask.type = "button";
        createTask.textContent = "Turn next step into a task";
        createTask.addEventListener("click", async () => {
          createTask.disabled = true;
          try {
            const result = await api(`/api/v1/reviews/${review.id}/carry-forward`, {
              method: "POST",
              body: JSON.stringify({ goal_id: goalSelect.value || null }),
            });
            await loadWorkspace();
            showNotice(result.created
              ? "Next step saved as a task. Add it to a daily plan when you choose."
              : "This review already has a follow-up task.");
          } catch (error) {
            createTask.disabled = false;
            showNotice(error.message);
          }
        });
        carryForward.append(goalLabel, createTask);
      }
      disclosure.append(carryForward);
    }
    item.append(title, detail, disclosure);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No reviews yet. Start a weekly or monthly check-in when it suits you.";
    rows.push(empty);
  }
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
    const domain = workspaceDomains.find((entry) => entry.code === goal.domain);
    const title = document.createElement("strong"); title.textContent = `${domain?.name || goal.domain.replaceAll("_", " ")} · ${goal.title} · ${metric.name}`;
    const progress = metric.progress_percent === null ? "Add baseline and current values to compare" : `${metric.progress_percent}% of stated range`;
    const meta = document.createElement("small"); meta.textContent = `${metric.current_value ?? "—"} / ${metric.target_value} ${metric.unit} · ${progress} · ${metric.confidence}% confidence · ${metric.source}`;
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

function renderQuests(quests) {
  const rows = quests.map((quest) => {
    const item = document.createElement("li");
    item.className = "quest-card";
    const title = document.createElement("strong");
    title.textContent = quest.title;
    const state = document.createElement("small");
    state.textContent = `${quest.status[0].toUpperCase()}${quest.status.slice(1)} · ${quest.completed_steps} of ${quest.total_steps} steps`;
    item.append(title, state);
    if (quest.description) {
      const description = document.createElement("p");
      description.className = "hint";
      description.textContent = quest.description;
      item.append(description);
    }
    const editDetails = document.createElement("details");
    const editSummary = document.createElement("summary");
    editSummary.textContent = "Edit quest";
    editDetails.append(editSummary, createQuestEditForm(quest));
    item.append(editDetails);

    const progress = document.createElement("progress");
    progress.max = Math.max(quest.total_steps, 1);
    progress.value = quest.completed_steps;
    progress.setAttribute("aria-label", `${quest.completed_steps} of ${quest.total_steps} quest steps complete`);
    item.append(progress);

    const steps = document.createElement("ol");
    steps.className = "quest-steps";
    for (const step of quest.steps) {
      const stepItem = document.createElement("li");
      const row = document.createElement("div");
      row.className = "quest-step-row";
      const copy = document.createElement("div");
      copy.className = "quest-step-copy";
      const stepTitle = document.createElement("strong");
      stepTitle.textContent = step.title;
      const stepMeta = document.createElement("small");
      const labels = { pending: "Ready to plan", completed: "Completed", skipped: "Skipped" };
      stepMeta.textContent = `${labels[step.status] || step.status}${step.due_date ? ` · due ${step.due_date}` : ""}`;
      copy.append(stepTitle, stepMeta);
      row.append(copy);

      if (quest.status !== "archived") {
        const actions = document.createElement("div");
        actions.className = "quest-step-actions";
        if (step.status === "pending") {
          actions.append(
            makePlanItemButton("Add to today", async () => addQuestStepToToday(step), "quiet", step.title),
            makePlanItemButton("Complete step", async () => completeQuestStep(step), "quiet", step.title),
          );
        } else if (step.status === "skipped") {
          actions.append(makePlanItemButton("Return step", async () => reopenQuestStep(step), "quiet", step.title));
        }
        if (actions.children.length) row.append(actions);
      }
      stepItem.append(row);
      steps.append(stepItem);
    }
    item.append(steps);

    const actions = document.createElement("div");
    actions.className = "item-actions";
    const lifecycle = makePlanItemButton(
      quest.status === "archived" ? "Restore quest" : "Archive quest",
      async () => updateQuestStatus(quest, quest.status === "archived" ? "active" : "archived"),
      "quiet",
      quest.title,
    );
    actions.append(lifecycle);
    item.append(actions);
    return item;
  });
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No quests yet. Build one from a few actions when you’re ready.";
    rows.push(empty);
  }
  $("#quest-list").replaceChildren(...rows);
}

function createQuestEditForm(quest) {
  const form = document.createElement("form");
  form.className = "quest-edit-form";
  appendInputField(form, "Quest title", "title", "text", quest.title, {
    required: true,
    maxLength: 160,
  });
  const descriptionLabel = document.createElement("label");
  const descriptionCaption = document.createElement("span");
  descriptionCaption.textContent = "Purpose (optional)";
  const description = document.createElement("textarea");
  description.name = "description";
  description.maxLength = 3000;
  description.rows = 2;
  description.value = quest.description || "";
  descriptionLabel.append(descriptionCaption, description);
  form.append(descriptionLabel);
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save quest changes";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formObject(form);
    payload.description = payload.description.trim() || null;
    try {
      await api(`/api/v1/quests/${quest.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
      showNotice("Quest changes saved.");
    } catch (error) {
      showNotice(error.message);
    }
  });
  return form;
}

async function addQuestStepToToday(step) {
  const checkbox = [...$("#task-options").querySelectorAll("[data-plan-task]")]
    .find((candidate) => candidate.dataset.planTask === step.task_id);
  if (!checkbox) {
    showNotice("This step is not available to add to today’s plan.");
    return;
  }
  if (!checkbox.checked) {
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  }
  $("#today").scrollIntoView({ block: "start" });
  checkbox.focus();
  showNotice("Step added to today’s choices. Save the plan when you’re ready.");
}

async function completeQuestStep(step) {
  await api(`/api/v1/tasks/${step.task_id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "completed" }),
  });
  await loadWorkspace();
  showNotice("Quest step completed.");
}

async function reopenQuestStep(step) {
  await api(`/api/v1/tasks/${step.task_id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "pending" }),
  });
  await loadWorkspace();
  showNotice("Quest step returned to your action list.");
}

async function updateQuestStatus(quest, status) {
  await api(`/api/v1/quests/${quest.id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  await loadWorkspace();
  showNotice(status === "archived" ? "Quest archived. Its steps and history remain." : "Quest restored.");
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

$("#domain-settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const domains = [...$("#domain-settings").querySelectorAll("[data-domain-code]")].map((row) => ({
    code: row.dataset.domainCode,
    name: row.querySelector('input[name="name"]').value.trim(),
    sort_order: Number(row.querySelector('select[name="sort_order"]').value),
    enabled: row.querySelector('input[name="enabled"]').checked,
  }));
  try {
    await api("/api/v1/domains/settings", {
      method: "PUT",
      body: JSON.stringify({ domains }),
    });
    await loadWorkspace();
    showNotice("Life area names, order, and visibility saved.");
  } catch (error) {
    showNotice(error.message);
  }
});

function updateHabitScheduleFields() {
  const frequency = $("#habit-frequency").value;
  const weekly = frequency === "weekly";
  const custom = frequency === "custom";
  $("#habit-weekdays-field").hidden = !weekly;
  $("#habit-custom-schedule-field").hidden = !custom;
  const interval = $("#habit-form").elements.interval_days;
  interval.disabled = !custom;
  interval.required = custom;
}

function updateHabitBuilderPreview() {
  const form = $("#habit-form");
  const value = (name, fallback) => form.elements[name].value.trim() || fallback;
  $("#habit-builder-preview").textContent = `After ${value("cue", "a moment you already notice")}, you can ${value("action", "take one small action")}. Your easiest version: ${value("minimum_version", "a tiny useful step")}. If you miss a day, you can ${value("recovery_action", "begin again with a small step")}.`;
}

$("#habit-frequency").addEventListener("change", updateHabitScheduleFields);
$("#habit-start-date").value = localDateString();
updateHabitScheduleFields();
for (const name of ["cue", "action", "minimum_version", "recovery_action"]) {
  $("#habit-form").elements[name].addEventListener("input", updateHabitBuilderPreview);
}
updateHabitBuilderPreview();

$("#habit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!payload.goal_id) delete payload.goal_id;
  if (!payload.end_date) delete payload.end_date;
  if (payload.frequency === "weekly") {
    payload.weekdays = [...form.querySelectorAll('input[name="weekdays"]:checked')]
      .map((checkbox) => Number(checkbox.value));
  } else {
    delete payload.weekdays;
  }
  if (payload.frequency === "custom") {
    payload.interval_days = Number(payload.interval_days);
  } else {
    delete payload.interval_days;
  }
  try {
    await api("/api/v1/habits", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    $("#habit-start-date").value = localDateString();
    updateHabitScheduleFields();
    updateHabitBuilderPreview();
    await loadWorkspace();
    showNotice("Routine saved. You can check in without keeping a streak.");
  } catch (error) {
    showNotice(error.message);
  }
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
    $("#awakening-assessment-list").querySelectorAll("textarea, button").forEach((input) => {
      input.disabled = !checkbox.checked;
    });
    const empty = $("#awakening-assessment-list").querySelector(".field-hint");
    if (empty) empty.hidden = checkbox.checked;
    showNotice(checkbox.checked
      ? "Awakening reflection and area-note storage is on for this local account."
      : "New answers will not be saved. Existing reflections and area notes remain until deleted.");
  } catch (error) {
    checkbox.checked = !checkbox.checked;
    showNotice(error.message);
  }
});

$("#awakening-baseline-consent").addEventListener("change", async (event) => {
  const checkbox = event.currentTarget;
  const granted = checkbox.checked;
  try {
    await api("/api/v1/consents", {
      method: "POST",
      body: JSON.stringify({
        purpose: "assessment_baseline_storage",
        granted,
        policy_version: "v1",
      }),
    });
    awakeningData.baseline_storage_consent = granted;
    renderAwakeningBaselines(awakeningData, awakeningData.steps[awakeningStepIndex]);
    showNotice(granted
      ? "Baseline storage is on for this local account."
      : "New starting points will not be saved. Existing entries remain until deleted.");
  } catch (error) {
    checkbox.checked = !granted;
    showNotice(error.message);
  }
});

$("#awakening-baseline-form").elements.status.addEventListener("change", syncAwakeningBaselineForm);

$("#awakening-baseline-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const status = form.elements.status.value;
  const payload = {
    domain: form.elements.domain.value,
    metric_name: form.elements.metric_name.value.trim(),
    status,
    confidence: Number(form.elements.confidence.value) || 0,
  };
  if (status === "recorded") {
    payload.value = form.elements.value.value;
    payload.unit = form.elements.unit.value.trim();
    if (form.elements.measured_on.value) payload.measured_on = form.elements.measured_on.value;
  }
  const stepIndex = awakeningStepIndex;
  try {
    await api("/api/v1/onboarding/awakening/baselines", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    form.elements.confidence.value = "50";
    await loadWorkspace();
    renderAwakening(awakeningData, stepIndex);
    showNotice("Starting point saved. Earlier entries remain in the history.");
  } catch (error) {
    showNotice(error.message);
  }
});

$("#reflection-consent").addEventListener("change", async (event) => {
  const checkbox = event.currentTarget;
  const granted = checkbox.checked;
  try {
    await api("/api/v1/consents", {
      method: "POST",
      body: JSON.stringify({
        purpose: "reflection_storage",
        granted,
        policy_version: "v1",
      }),
    });
    reflectionStorageConsent = granted;
    await loadWorkspace();
    showNotice(granted
      ? "Review answers and optional daily reflections can now be saved in this local account."
      : "New reflections will not be saved. Existing review answers and daily reflections can still be deleted.");
  } catch (error) {
    checkbox.checked = !granted;
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
    const deleted = result.deleted_answers + result.deleted_assessments;
    showNotice(`${deleted} saved reflection or area note${deleted === 1 ? "" : "s"} deleted.`);
  } catch (error) {
    showNotice(error.message);
  }
});

$("#goal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!payload.target_date) delete payload.target_date;
  if (!payload.subarea_id) delete payload.subarea_id;
  try { await api("/api/v1/goals", { method: "POST", body: JSON.stringify(payload) }); form.reset(); await loadWorkspace(); showNotice("Goal saved."); }
  catch (error) { showNotice(error.message); }
});

$("#goal-form").elements.domain.addEventListener("change", updateGoalSubareaOptions);

$("#quest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  const steps = payload.steps.split(/\r?\n/).map((title) => title.trim()).filter(Boolean);
  if (steps.length < 2 || steps.length > 12) {
    showNotice("Add between 2 and 12 quest steps, one per line.");
    form.elements.steps.focus();
    return;
  }
  payload.steps = steps.map((title) => ({ title }));
  payload.description = payload.description.trim() || null;
  payload.goal_id = payload.goal_id || null;
  try {
    await api("/api/v1/quests", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await loadWorkspace();
    showNotice("Quest saved. Its steps are ready to plan.");
  } catch (error) {
    showNotice(error.message);
  }
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
    day_start_time: $("#day-start-time").value,
    day_end_time: $("#day-end-time").value,
    busy_windows: [...$("#busy-window-list").querySelectorAll(".busy-window-row")].map((row) => ({
      start_time: row.querySelector('[data-busy-time="start_time"]').value,
      end_time: row.querySelector('[data-busy-time="end_time"]').value,
    })),
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

$("#daily-reflection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!reflectionStorageConsent) {
    showNotice("Turn on reflection storage in Settings before saving this check-in.");
    return;
  }
  const form = event.currentTarget;
  const payload = formObject(form);
  if (!Object.values(payload).some((value) => value.trim())) {
    showNotice("Add a note to at least one reflection prompt, or leave it blank.");
    return;
  }
  try {
    const saved = await api(`/api/v1/daily-plans/${$("#daily-plan-date").value}/reflection`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    renderDailyReflection(saved);
    showNotice("Your reflection is saved for this day.");
  } catch (error) { showNotice(error.message); }
});

$("#daily-reflection-delete").addEventListener("click", async () => {
  const planDate = $("#daily-plan-date").value;
  if (!window.confirm(`Delete the saved reflection for ${planDate}?`)) return;
  try {
    await api(`/api/v1/daily-plans/${planDate}/reflection`, { method: "DELETE" });
    renderDailyReflection(await api(`/api/v1/daily-plans/${planDate}/reflection`));
    showNotice("The daily reflection was deleted.");
  } catch (error) { showNotice(error.message); }
});

$("#calendar-import-file").addEventListener("change", () => {
  importedCalendarPreview = null;
  $("#calendar-import-preview-list").replaceChildren();
  $("#calendar-import-apply").disabled = true;
});

$("#calendar-import-preview-button").addEventListener("click", async () => {
  const file = $("#calendar-import-file").files[0];
  const planDate = $("#daily-plan-date").value;
  if (!file || !planDate) {
    showNotice("Choose a calendar file and plan date first.");
    return;
  }
  const button = $("#calendar-import-preview-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/calendar/import-preview", {
      method: "POST",
      body: JSON.stringify({
        plan_date: planDate,
        ics_content: await file.text(),
        day_start_time: $("#day-start-time").value,
        day_end_time: $("#day-end-time").value,
      }),
    });
    if (planDate !== $("#daily-plan-date").value) {
      importedCalendarPreview = null;
      showNotice("The plan date changed. Preview the calendar file again.");
      return;
    }
    importedCalendarPreview = result;
    const rows = result.windows.map((window) => {
      const row = document.createElement("li");
      row.textContent = `Busy ${window.start_time}–${window.end_time}`;
      return row;
    });
    if (!result.windows.length) {
      const empty = document.createElement("li");
      empty.textContent = "No busy times were found for this plan date.";
      rows.push(empty);
    }
    if (result.recurring_events_skipped || result.events_skipped) {
      const note = document.createElement("li");
      note.textContent = `${result.recurring_events_skipped} recurring event${result.recurring_events_skipped === 1 ? " was" : "s were"} and ${result.events_skipped} unreadable event${result.events_skipped === 1 ? " was" : "s were"} skipped.`;
      rows.push(note);
    }
    $("#calendar-import-preview-list").replaceChildren(...rows);
    $("#calendar-import-apply").disabled = !result.can_apply;
    showNotice(result.can_apply
      ? `Preview ready for ${result.plan_date}. Review the busy times, then add them to your plan.`
      : result.too_many_windows
        ? "This date has more than 12 separate busy periods. Import a smaller set or add the times you want manually."
        : "There are no usable busy times to add for this date.");
  } catch (error) {
    importedCalendarPreview = null;
    $("#calendar-import-preview-list").replaceChildren();
    $("#calendar-import-apply").disabled = true;
    showNotice(error.message);
  } finally {
    button.disabled = false;
  }
});

$("#calendar-import-apply").addEventListener("click", () => {
  if (!importedCalendarPreview || importedCalendarPreview.plan_date !== $("#daily-plan-date").value) {
    showNotice("Preview a calendar file for the selected plan date first.");
    return;
  }
  const current = [...$("#busy-window-list").querySelectorAll(".busy-window-row")].map((row) => ({
    start_time: row.querySelector('[data-busy-time="start_time"]').value,
    end_time: row.querySelector('[data-busy-time="end_time"]').value,
  }));
  const merged = mergeTimeWindows([...current, ...importedCalendarPreview.windows]);
  if (merged.length > 12) {
    showNotice("This plan can hold up to 12 separate busy times. Remove a time or import fewer events.");
    return;
  }
  renderBusyWindowEditor(merged);
  $("#calendar-import-apply").disabled = true;
  showNotice("Busy times added to the plan editor. Save today’s plan to keep them.");
});

$("#daily-plan-date").addEventListener("change", () => {
  importedCalendarPreview = null;
  $("#calendar-import-preview-list").replaceChildren();
  $("#calendar-import-apply").disabled = true;
});

["#day-start-time", "#day-end-time"].forEach((selector) => {
  $(selector).addEventListener("change", () => {
    importedCalendarPreview = null;
    $("#calendar-import-preview-list").replaceChildren();
    $("#calendar-import-apply").disabled = true;
  });
});

$("#add-busy-window").addEventListener("click", () => {
  const windows = $("#busy-window-list");
  if (windows.children.length >= 12) {
    showNotice("A daily plan can include up to 12 busy times.");
    return;
  }
  windows.append(createBusyWindowRow());
});

$("#plan-capacity").addEventListener("input", updatePlanSummary);
$("#daily-plan-date").addEventListener("change", async () => {
  const planDate = $("#daily-plan-date").value;
  if (!planDate) return;
  try {
    const [plan, recovery, reflection] = await Promise.all([
      api(`/api/v1/daily-plans/${planDate}`),
      api(`/api/v1/daily-plans/${planDate}/recovery`),
      api(`/api/v1/daily-plans/${planDate}/reflection`),
    ]);
    renderDailyPlan(plan);
    renderRecovery(recovery);
    renderDailyReflection(reflection);
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
