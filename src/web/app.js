const state = {
  section: "dashboard",
  auth: {
    initData: "",
    webLoginToken: localStorage.getItem("rememberme.webLoginToken") || "",
    adminToken: localStorage.getItem("rememberme.adminToken") || "",
    telegramId: localStorage.getItem("rememberme.telegramId") || "",
    firstName: localStorage.getItem("rememberme.firstName") || "",
  },
  user: null,
  summary: null,
  lists: [],
  reminders: [],
  medications: [],
  driver: null,
  selectedListId: null,
  selectedVehicleId: null,
};

const titles = {
  dashboard: ["Сводка", "Текущие данные бота в web-версии."],
  lists: ["Списки", "Создание, просмотр и отметка пунктов."],
  reminders: ["Напоминания", "Активные напоминания пользователя."],
  medications: ["Лекарства", "Приемы, важность и ежедневное расписание."],
  driver: ["Водитель", "Автомобили, пробег и заправки."],
  admin: ["Админ", "Активность и воронки тестового проекта."],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showMessage(text, isError = false) {
  const node = $("#message");
  node.textContent = text;
  node.classList.remove("hidden");
  node.style.borderColor = isError ? "var(--danger)" : "var(--line)";
  node.style.color = isError ? "var(--danger)" : "var(--text)";
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => node.classList.add("hidden"), 4500);
}

function authHeaders() {
  if (state.auth.initData) {
    return { "X-Telegram-Init-Data": state.auth.initData };
  }
  if (state.auth.webLoginToken) {
    return { "X-Web-Login-Token": state.auth.webLoginToken };
  }
  return {
    "X-Admin-Token": state.auth.adminToken,
    "X-Web-Test-Telegram-Id": state.auth.telegramId,
    "X-Web-Test-First-Name": state.auth.firstName || "Web user",
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep default detail.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function adminApi(path) {
  const response = await fetch(path, {
    headers: { "X-Admin-Token": state.auth.adminToken },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function saveAuth() {
  localStorage.setItem("rememberme.webLoginToken", state.auth.webLoginToken);
  localStorage.setItem("rememberme.adminToken", state.auth.adminToken);
  localStorage.setItem("rememberme.telegramId", state.auth.telegramId);
  localStorage.setItem("rememberme.firstName", state.auth.firstName);
}

function clearAuth() {
  state.auth.initData = "";
  state.auth.webLoginToken = "";
  state.auth.adminToken = "";
  state.auth.telegramId = "";
  state.auth.firstName = "";
  localStorage.removeItem("rememberme.webLoginToken");
  localStorage.removeItem("rememberme.adminToken");
  localStorage.removeItem("rememberme.telegramId");
  localStorage.removeItem("rememberme.firstName");
  state.user = null;
  state.summary = null;
  updateAuthUi();
}

function updateAuthUi() {
  $("#webLoginTokenInput").value = state.auth.webLoginToken;
  $("#adminTokenInput").value = state.auth.adminToken;
  $("#telegramIdInput").value = state.auth.telegramId;
  $("#firstNameInput").value = state.auth.firstName;
  $("#loginPanel").classList.toggle("hidden", Boolean(state.user));
  $("#logoutButton").classList.toggle("hidden", !state.user);
  $("#authStatus").textContent = state.user
    ? `${state.user.first_name || state.user.username || "user"} · ${state.user.telegram_id}`
    : "не подключено";
  $("#authStatus").classList.toggle("muted", !state.user);
}

function setSection(section) {
  state.section = section;
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.section === section));
  $$(".section").forEach((node) => node.classList.toggle("active", node.id === section));
  const [title, subtitle] = titles[section] || titles.dashboard;
  $("#sectionTitle").textContent = title;
  $("#sectionSubtitle").textContent = subtitle;
  if (state.user) {
    loadSection(section).catch((error) => showMessage(error.message, true));
  }
}

function renderMetrics() {
  const stats = state.summary?.stats || {};
  const cards = [
    ["Списки", stats.lists?.owned ?? 0],
    ["Напоминания", stats.reminders?.active ?? 0],
    ["Лекарства", stats.medications?.active ?? 0],
    ["Авто", stats.driver?.vehicles_count ?? 0],
    ["Заправки", stats.driver?.fuel_entries_count ?? 0],
    ["Расходы на топливо", formatMoney(stats.driver?.fuel_total_cost ?? 0)],
    ["План", state.summary?.access?.plan_code || "free"],
    ["Статус", state.summary?.access?.status || "active"],
  ];
  $("#dashboardCards").innerHTML = cards.map(([label, value]) => `
    <article class="metric">
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
    </article>
  `).join("");
}

function formatDate(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function formatMoney(value) {
  const number = Number(value || 0);
  return number.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
}

function toDatetimeLocal(value) {
  const offset = value.getTimezoneOffset();
  const local = new Date(value.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

function defaultReminderTime() {
  const value = new Date(Date.now() + 60 * 60 * 1000);
  value.setMinutes(0, 0, 0);
  return toDatetimeLocal(value);
}

function parseTimes(value) {
  return String(value || "")
    .split(/[,\n;]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

async function loadSummary() {
  state.summary = await api("/me/summary");
  state.user = state.summary.user;
  updateAuthUi();
  renderMetrics();
}

async function loadLists() {
  state.lists = await api("/me/lists");
  $("#listsContainer").innerHTML = state.lists.length
    ? state.lists.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${item.items_done}/${item.items_total} выполнено · ${escapeHtml(item.access_role)}</div>
          </div>
        </div>
        <div class="item-actions">
          <button class="small" data-action="open-list" data-id="${item.id}">Открыть</button>
          <button class="secondary small" data-action="rename-list" data-id="${item.id}" data-title="${escapeHtml(item.title)}">Переименовать</button>
          <button class="danger small" data-action="delete-list" data-id="${item.id}">Удалить</button>
        </div>
      </article>
    `).join("")
    : `<div class="item-meta">Списков пока нет.</div>`;
}

async function openList(listId) {
  const detail = await api(`/me/lists/${listId}`);
  state.selectedListId = detail.id;
  $("#listDetailPanel").classList.remove("hidden");
  $("#listDetailPanel").innerHTML = `
    <h2>${escapeHtml(detail.title)}</h2>
    <div class="item-meta">${detail.items_done}/${detail.items_total} выполнено</div>
    <form id="listItemCreateForm" class="stack" data-list-id="${detail.id}">
      <textarea name="text" rows="3" placeholder="Новый пункт или несколько строк" required></textarea>
      <button type="submit">Добавить</button>
    </form>
    <div class="item-list">
      ${detail.items.length ? detail.items.map((item) => `
        <div class="list-item-row">
          <input type="checkbox" data-action="toggle-item" data-id="${item.id}" ${item.is_completed ? "checked" : ""}>
          <span>${escapeHtml(item.text)}</span>
          <div class="actions">
            <button class="secondary small" data-action="edit-item" data-id="${item.id}" data-text="${escapeHtml(item.text)}">Изм.</button>
            <button class="danger small" data-action="delete-item" data-id="${item.id}">Удалить</button>
          </div>
        </div>
      `).join("") : `<div class="item-meta">Пунктов пока нет.</div>`}
    </div>
  `;
  $("#listItemCreateForm").addEventListener("submit", handleListItemCreate);
}

async function loadReminders() {
  state.reminders = await api("/me/reminders?active_only=false");
  $("#remindersContainer").innerHTML = state.reminders.length
    ? state.reminders.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title || "Напоминание")}</div>
            <div class="item-meta">${formatDate(item.remind_at_utc)} · ${escapeHtml(item.repeat_rule)} · ${escapeHtml(item.status)}</div>
          </div>
        </div>
        <div class="item-text">${escapeHtml(item.text)}</div>
        <div class="item-actions">
          <button class="secondary small" data-action="done-reminder" data-id="${item.id}">Выполнено</button>
          <button class="danger small" data-action="delete-reminder" data-id="${item.id}">Удалить</button>
        </div>
      </article>
    `).join("")
    : `<div class="item-meta">Напоминаний пока нет.</div>`;
}

async function loadMedications() {
  state.medications = await api("/me/medications?active_only=false");
  $("#medicationsContainer").innerHTML = state.medications.length
    ? state.medications.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.name)}</div>
            <div class="item-meta">${escapeHtml(item.importance)} · ${item.is_active ? "активно" : "архив"}</div>
          </div>
        </div>
        <div class="item-text">${escapeHtml([item.dosage, item.instructions].filter(Boolean).join("\n"))}</div>
        <div class="item-meta">Время: ${escapeHtml(item.daily_times_local?.join(", ") || "не задано")}</div>
        <div class="item-actions">
          <button class="small" data-action="taken-medication" data-id="${item.id}">Принял</button>
          <button class="secondary small" data-action="skipped-medication" data-id="${item.id}">Пропустил</button>
          <button class="danger small" data-action="archive-medication" data-id="${item.id}">Архив</button>
        </div>
      </article>
    `).join("")
    : `<div class="item-meta">Лекарств пока нет.</div>`;
}

function renderDriver() {
  const vehicles = state.driver?.vehicles || [];
  $("#vehiclesContainer").innerHTML = vehicles.length
    ? vehicles.map((item) => `
      <article class="item-card">
        <div class="item-title">${escapeHtml(item.title)}</div>
        <div class="item-meta">${item.current_mileage_km} км · ТО каждые ${item.service_interval_km} км</div>
        <div class="item-actions">
          <button class="small" data-action="select-vehicle" data-id="${item.id}">Выбрать</button>
          <button class="danger small" data-action="delete-vehicle" data-id="${item.id}">Удалить</button>
        </div>
      </article>
    `).join("")
    : `<div class="item-meta">Авто пока нет.</div>`;

  const select = $("#fuelCreateForm select[name='vehicle_id']");
  select.innerHTML = vehicles.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  if (!state.selectedVehicleId && vehicles[0]) {
    state.selectedVehicleId = vehicles[0].id;
  }
  if (state.selectedVehicleId) {
    select.value = String(state.selectedVehicleId);
  }
}

async function loadDriver() {
  state.driver = await api("/me/driver");
  renderDriver();
  if (state.selectedVehicleId) {
    await loadFuel(state.selectedVehicleId);
  } else {
    $("#fuelContainer").innerHTML = `<div class="item-meta">Выберите авто.</div>`;
  }
}

async function loadFuel(vehicleId) {
  state.selectedVehicleId = Number(vehicleId);
  const entries = await api(`/me/driver/vehicles/${vehicleId}/fuel`);
  $("#fuelContainer").innerHTML = entries.length
    ? entries.map((item) => `
      <article class="item-card">
        <div class="item-title">${item.mileage_km} км · ${item.liters} л · ${formatMoney(item.total_cost)}</div>
        <div class="item-meta">${escapeHtml(item.station || "АЗС не указана")} · ${formatDate(item.filled_at_utc)}</div>
        <div class="item-actions">
          <button class="danger small" data-action="delete-fuel" data-id="${item.id}">Удалить</button>
        </div>
      </article>
    `).join("")
    : `<div class="item-meta">Заправок пока нет.</div>`;
}

async function loadAdmin() {
  if (!state.auth.adminToken) {
    $("#adminActivity").innerHTML = `<div class="item-meta">Нужен admin token.</div>`;
    $("#adminFunnels").innerHTML = "";
    return;
  }
  const [activity, funnels] = await Promise.all([
    adminApi("/admin/activity"),
    adminApi("/admin/funnels"),
  ]);
  $("#adminActivity").innerHTML = `
    <article class="item-card">
      <div class="item-title">События за 24 часа: ${activity.events_24h}</div>
      <div class="item-meta">За период: ${activity.events_period}; активных пользователей: ${activity.active_other_users_period}</div>
    </article>
    ${(activity.top_actions || []).map((item) => `
      <article class="item-card">
        <div class="item-title">${escapeHtml(item.event_name)}</div>
        <div class="item-meta">${item.count} событий</div>
      </article>
    `).join("")}
  `;
  $("#adminFunnels").innerHTML = (funnels.funnels || []).map((funnel) => `
    <article class="item-card">
      <div class="item-title">${escapeHtml(funnel.name)}</div>
      ${(funnel.stages || []).map((stage) => `
        <div class="item-meta">${escapeHtml(stage.name)}: ${stage.count}</div>
      `).join("")}
    </article>
  `).join("") || `<div class="item-meta">Данных пока нет.</div>`;
}

async function loadSection(section) {
  if (!state.user && section !== "dashboard") return;
  if (section === "dashboard") {
    await loadSummary();
  } else if (section === "lists") {
    await loadLists();
  } else if (section === "reminders") {
    await loadReminders();
  } else if (section === "medications") {
    await loadMedications();
  } else if (section === "driver") {
    await loadDriver();
  } else if (section === "admin") {
    await loadAdmin();
  }
}

async function handleLogin() {
  state.auth.webLoginToken = $("#webLoginTokenInput").value.trim();
  state.auth.adminToken = $("#adminTokenInput").value.trim();
  state.auth.telegramId = $("#telegramIdInput").value.trim();
  state.auth.firstName = $("#firstNameInput").value.trim();
  if (!state.auth.webLoginToken && (!state.auth.adminToken || !state.auth.telegramId)) {
    showMessage("Вставьте web-ключ из Telegram или укажите admin token и Telegram ID.", true);
    return;
  }
  saveAuth();
  await loadSummary();
  await loadSection(state.section);
  showMessage("Вход выполнен.");
}

async function handleListCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/lists", {
    method: "POST",
    body: JSON.stringify({ title: form.title.value }),
  });
  form.reset();
  await loadLists();
  await loadSummary();
}

async function handleListItemCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api(`/me/lists/${form.dataset.listId}/items`, {
    method: "POST",
    body: JSON.stringify({ text: form.text.value }),
  });
  form.reset();
  await openList(form.dataset.listId);
  await loadLists();
}

async function handleReminderCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/reminders", {
    method: "POST",
    body: JSON.stringify({
      title: form.title.value,
      text: form.text.value,
      remind_at_local: form.remind_at_local.value,
      repeat_rule: form.repeat_rule.value,
    }),
  });
  form.reset();
  form.remind_at_local.value = defaultReminderTime();
  await loadReminders();
  await loadSummary();
}

async function handleMedicationCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/medications", {
    method: "POST",
    body: JSON.stringify({
      name: form.name.value,
      dosage: form.dosage.value,
      instructions: form.instructions.value,
      importance: form.importance.value,
      daily_times_local: parseTimes(form.daily_times_local.value),
    }),
  });
  form.reset();
  await loadMedications();
  await loadSummary();
}

async function handleVehicleCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/driver/vehicles", {
    method: "POST",
    body: JSON.stringify({
      title: form.title.value,
      current_mileage_km: Number(form.current_mileage_km.value || 0),
    }),
  });
  form.reset();
  await loadDriver();
  await loadSummary();
}

async function handleFuelCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const vehicleId = form.vehicle_id.value;
  if (!vehicleId) {
    showMessage("Сначала добавьте авто.", true);
    return;
  }
  await api(`/me/driver/vehicles/${vehicleId}/fuel`, {
    method: "POST",
    body: JSON.stringify({
      mileage_km: Number(form.mileage_km.value),
      liters: Number(form.liters.value),
      total_cost: Number(form.total_cost.value),
      station: form.station.value,
      is_full_tank: form.is_full_tank.checked,
    }),
  });
  form.reset();
  form.is_full_tank.checked = true;
  await loadDriver();
  await loadSummary();
}

async function handleAction(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;
  try {
    if (action === "open-list") {
      await openList(id);
    } else if (action === "rename-list") {
      const title = window.prompt("Новое название", target.dataset.title || "");
      if (title) {
        await api(`/me/lists/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
        await loadLists();
        await openList(id);
      }
    } else if (action === "delete-list") {
      if (window.confirm("Удалить список?")) {
        await api(`/me/lists/${id}`, { method: "DELETE" });
        $("#listDetailPanel").classList.add("hidden");
        await loadLists();
        await loadSummary();
      }
    } else if (action === "toggle-item") {
      await api(`/me/lists/items/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_completed: target.checked }),
      });
      await openList(state.selectedListId);
      await loadLists();
    } else if (action === "edit-item") {
      const text = window.prompt("Текст пункта", target.dataset.text || "");
      if (text) {
        await api(`/me/lists/items/${id}`, { method: "PATCH", body: JSON.stringify({ text }) });
        await openList(state.selectedListId);
        await loadLists();
      }
    } else if (action === "delete-item") {
      await api(`/me/lists/items/${id}`, { method: "DELETE" });
      await openList(state.selectedListId);
      await loadLists();
    } else if (action === "done-reminder") {
      await api(`/me/reminders/${id}/done`, { method: "POST" });
      await loadReminders();
      await loadSummary();
    } else if (action === "delete-reminder") {
      await api(`/me/reminders/${id}`, { method: "DELETE" });
      await loadReminders();
      await loadSummary();
    } else if (action === "taken-medication") {
      await api(`/me/medications/${id}/taken`, { method: "POST" });
      showMessage("Отметка сохранена.");
    } else if (action === "skipped-medication") {
      await api(`/me/medications/${id}/skipped`, { method: "POST" });
      showMessage("Пропуск сохранен.");
    } else if (action === "archive-medication") {
      await api(`/me/medications/${id}`, { method: "DELETE" });
      await loadMedications();
      await loadSummary();
    } else if (action === "select-vehicle") {
      await loadFuel(id);
    } else if (action === "delete-vehicle") {
      if (window.confirm("Удалить автомобиль и его заправки?")) {
        await api(`/me/driver/vehicles/${id}`, { method: "DELETE" });
        state.selectedVehicleId = null;
        await loadDriver();
        await loadSummary();
      }
    } else if (action === "delete-fuel") {
      await api(`/me/driver/fuel/${id}`, { method: "DELETE" });
      await loadDriver();
      await loadSummary();
    }
  } catch (error) {
    showMessage(error.message, true);
  }
}

function bindEvents() {
  $$(".nav-button").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.section)));
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("rememberme.theme", next);
  });
  $("#reloadButton").addEventListener("click", () => loadSection(state.section).catch((error) => showMessage(error.message, true)));
  $("#logoutButton").addEventListener("click", clearAuth);
  $("#loginButton").addEventListener("click", () => handleLogin().catch((error) => showMessage(error.message, true)));
  $("#listCreateForm").addEventListener("submit", (event) => handleListCreate(event).catch((error) => showMessage(error.message, true)));
  $("#reminderCreateForm").addEventListener("submit", (event) => handleReminderCreate(event).catch((error) => showMessage(error.message, true)));
  $("#medicationCreateForm").addEventListener("submit", (event) => handleMedicationCreate(event).catch((error) => showMessage(error.message, true)));
  $("#vehicleCreateForm").addEventListener("submit", (event) => handleVehicleCreate(event).catch((error) => showMessage(error.message, true)));
  $("#fuelCreateForm").addEventListener("submit", (event) => handleFuelCreate(event).catch((error) => showMessage(error.message, true)));
  document.body.addEventListener("click", handleAction);
  $("#fuelCreateForm select[name='vehicle_id']").addEventListener("change", (event) => loadFuel(event.target.value).catch((error) => showMessage(error.message, true)));
}

async function boot() {
  document.documentElement.dataset.theme = localStorage.getItem("rememberme.theme") || "light";
  $("#reminderCreateForm input[name='remind_at_local']").value = defaultReminderTime();
  const url = new URL(window.location.href);
  const tokenFromLink = url.searchParams.get("token");
  if (tokenFromLink) {
    state.auth.webLoginToken = tokenFromLink.trim();
    localStorage.setItem("rememberme.webLoginToken", state.auth.webLoginToken);
    url.searchParams.delete("token");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }
  const telegram = window.Telegram?.WebApp;
  if (telegram?.initData) {
    state.auth.initData = telegram.initData;
    telegram.ready?.();
  }
  bindEvents();
  updateAuthUi();
  if (state.auth.initData || state.auth.webLoginToken || (state.auth.adminToken && state.auth.telegramId)) {
    try {
      await loadSummary();
      await loadSection(state.section);
    } catch (error) {
      showMessage(error.message, true);
      updateAuthUi();
    }
  }
}

boot();
