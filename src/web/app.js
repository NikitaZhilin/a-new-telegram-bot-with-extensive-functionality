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
  fuelEntries: [],
  selectedListId: null,
  selectedVehicleId: null,
  editingReminderId: null,
  editingMedicationId: null,
  editingVehicleId: null,
  editingFuelId: null,
  serviceVehicleId: null,
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
  closeMobileMenu();
  if (state.user) {
    loadSection(section).catch((error) => showMessage(error.message, true));
  }
}

function openMobileMenu() {
  $(".sidebar").classList.add("open");
  $("#menuBackdrop").classList.add("open");
  $("#menuBackdrop").hidden = false;
  $("#menuToggle").setAttribute("aria-expanded", "true");
}

function closeMobileMenu() {
  $(".sidebar").classList.remove("open");
  $("#menuBackdrop").classList.remove("open");
  $("#menuBackdrop").hidden = true;
  $("#menuToggle").setAttribute("aria-expanded", "false");
}

function toggleMobileMenu() {
  if ($(".sidebar").classList.contains("open")) {
    closeMobileMenu();
  } else {
    openMobileMenu();
  }
}

function renderMetrics() {
  const stats = state.summary?.stats || {};
  const cards = [
    ["Списки", stats.lists?.owned ?? 0, `общих списков с вашим доступом: ${stats.lists?.shared ?? 0}`],
    ["Активные напоминания", stats.reminders?.active ?? 0, `выполнено: ${stats.reminders?.done ?? 0}; отменено: ${stats.reminders?.canceled ?? 0}`],
    ["Лекарства", stats.medications?.active ?? 0, `в архиве: ${stats.medications?.archived ?? 0}`],
    ["Автомобили", stats.driver?.vehicles_count ?? 0, `заправок: ${stats.driver?.fuel_entries_count ?? 0}`],
    ["Расходы на топливо", formatMoney(stats.driver?.fuel_total_cost ?? 0), "сумма по всем заправкам"],
    ["Тариф", state.summary?.access?.plan_title || formatPlan(state.summary?.access?.plan), `статус: ${formatSubscriptionStatus(state.summary?.access?.subscription_status)}`],
  ];
  $("#dashboardCards").innerHTML = cards.map(([label, value, detail]) => `
    <article class="metric">
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-detail">${escapeHtml(detail || "")}</div>
    </article>
  `).join("");
  renderDashboardDetails(stats);
}

function renderDashboardDetails(stats) {
  const access = state.summary?.access || {};
  const rows = [
    {
      title: "Рабочие разделы",
      lines: [
        `Личные списки: ${stats.lists?.owned ?? 0}`,
        `Общие списки: ${stats.lists?.shared ?? 0}`,
        `Активные лекарства: ${stats.medications?.active ?? 0}`,
        `Автомобили: ${stats.driver?.vehicles_count ?? 0}`,
      ],
    },
    {
      title: "Напоминания",
      lines: [
        `Активные: ${stats.reminders?.active ?? 0}`,
        `Выполненные: ${stats.reminders?.done ?? 0}`,
        `Отмененные: ${stats.reminders?.canceled ?? 0}`,
        `Пропущенные: ${stats.reminders?.missed ?? 0}`,
      ],
    },
    {
      title: "Водитель",
      lines: [
        `Заправок: ${stats.driver?.fuel_entries_count ?? 0}`,
        `Расходы на топливо: ${formatMoney(stats.driver?.fuel_total_cost ?? 0)}`,
        `Средний расход: ${stats.driver?.avg_consumption ? `${Number(stats.driver.avg_consumption).toFixed(1)} л/100 км` : "пока не рассчитан"}`,
      ],
    },
    {
      title: "Доступ",
      lines: [
        `Тариф: ${access.plan_title || formatPlan(access.plan)}`,
        `Статус подписки: ${formatSubscriptionStatus(access.subscription_status)}`,
        `Админский доступ: ${access.is_admin ? "да" : "нет"}`,
      ],
    },
  ];
  $("#dashboardDetails").innerHTML = rows.map((block) => `
    <article class="panel">
      <h2>${escapeHtml(block.title)}</h2>
      <div class="item-list">
        ${block.lines.map((line) => `<div class="item-meta">${escapeHtml(line)}</div>`).join("")}
      </div>
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

function formatRole(value) {
  return {
    owner: "владелец",
    editor: "редактор",
    viewer: "просмотр",
  }[value] || value || "просмотр";
}

function formatReminderStatus(value) {
  return {
    active: "активно",
    done: "выполнено",
    canceled: "отменено",
    missed: "пропущено",
  }[value] || value || "";
}

function formatRepeat(value) {
  return {
    none: "без повтора",
    daily: "каждый день",
    weekly: "каждую неделю",
    monthly: "каждый месяц",
  }[value] || value || "";
}

function formatImportance(value) {
  return {
    supplement: "БАД",
    normal: "обычное",
    important: "важное",
    critical: "критичное",
  }[value] || value || "обычное";
}

function formatPlan(value) {
  return {
    free: "Базовый",
    plus: "Plus",
    pro: "Pro",
  }[value] || value || "Базовый";
}

function formatSubscriptionStatus(value) {
  return {
    active: "активна",
    inactive: "не активна",
    canceled: "отменена",
    expired: "истекла",
  }[value] || value || "не активна";
}

function formatActionLabel(item) {
  return item.label || item.event_label || item.event_name || "действие";
}

function formatServicePlan(plan) {
  if (!plan) return "ТО пока не отмечалось";
  const parts = [];
  if (plan.remaining_km !== null && plan.remaining_km !== undefined) {
    parts.push(`до ТО ${plan.remaining_km} км`);
  }
  if (plan.days_left !== null && plan.days_left !== undefined) {
    parts.push(`по сроку ${plan.days_left} дн.`);
  }
  return parts.length ? parts.join(" · ") : "ТО пока не отмечалось";
}

function toLocalInputFromIso(value) {
  if (!value) return "";
  return toDatetimeLocal(new Date(value));
}

function boolFromPrompt(value, fallback = true) {
  if (value === null) return null;
  const normalized = String(value).trim().toLowerCase();
  if (!normalized) return fallback;
  return ["1", "да", "yes", "y", "true", "полный"].includes(normalized);
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showMessage("Скопировано.");
  } catch {
    window.prompt("Скопируйте вручную", text);
  }
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

function renderMedicationEditForm(item) {
  return `
    <form class="stack inline-edit-form medication-edit-form" data-id="${item.id}">
      <input name="name" type="text" value="${escapeHtml(item.name)}" placeholder="Название" required>
      <input name="dosage" type="text" value="${escapeHtml(item.dosage || "")}" placeholder="Дозировка">
      <textarea name="instructions" rows="3" placeholder="Комментарий">${escapeHtml(item.instructions || "")}</textarea>
      <select name="importance">
        <option value="supplement" ${item.importance === "supplement" ? "selected" : ""}>БАД</option>
        <option value="normal" ${item.importance === "normal" ? "selected" : ""}>Обычное</option>
        <option value="important" ${item.importance === "important" ? "selected" : ""}>Важное</option>
        <option value="critical" ${item.importance === "critical" ? "selected" : ""}>Критичное</option>
      </select>
      <input name="daily_times_local" type="text" value="${escapeHtml(item.daily_times_local?.join(", ") || "")}" placeholder="Время: 09:00, 21:00">
      <div class="item-actions">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-medication-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderReminderEditForm(item) {
  return `
    <form class="stack inline-edit-form reminder-edit-form" data-id="${item.id}">
      <input name="title" type="text" value="${escapeHtml(item.title || "")}" placeholder="Заголовок">
      <textarea name="text" rows="3" placeholder="Текст напоминания" required>${escapeHtml(item.text || "")}</textarea>
      <input name="remind_at_local" type="datetime-local" value="${escapeHtml(toLocalInputFromIso(item.remind_at_utc))}" required>
      <select name="repeat_rule">
        <option value="none" ${item.repeat_rule === "none" ? "selected" : ""}>Без повтора</option>
        <option value="daily" ${item.repeat_rule === "daily" ? "selected" : ""}>Каждый день</option>
        <option value="weekly" ${item.repeat_rule === "weekly" ? "selected" : ""}>Каждую неделю</option>
        <option value="monthly" ${item.repeat_rule === "monthly" ? "selected" : ""}>Каждый месяц</option>
      </select>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-reminder-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderVehicleEditForm(item) {
  return `
    <form class="stack inline-edit-form vehicle-edit-form" data-id="${item.id}">
      <input name="title" type="text" value="${escapeHtml(item.title)}" placeholder="Название авто" required>
      <input name="current_mileage_km" type="number" min="0" value="${item.current_mileage_km}" placeholder="Пробег, км" required>
      <input name="service_interval_km" type="number" min="1" value="${item.service_interval_km}" placeholder="Интервал ТО, км" required>
      <input name="service_interval_months" type="number" min="1" value="${item.service_interval_months}" placeholder="Интервал ТО, месяцев" required>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-vehicle-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderServiceDoneForm(item) {
  return `
    <form class="stack inline-edit-form service-done-form" data-id="${item.id}">
      <input name="service_mileage_km" type="number" min="0" value="${item.current_mileage_km}" placeholder="Пробег при ТО" required>
      <div class="button-row">
        <button class="small action-done" type="submit">Зафиксировать ТО</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-service-done">Отмена</button>
      </div>
    </form>
  `;
}

function renderFuelEditForm(item) {
  return `
    <form class="stack inline-edit-form fuel-edit-form" data-id="${item.id}">
      <input name="mileage_km" type="number" min="0" value="${item.mileage_km}" placeholder="Пробег, км" required>
      <input name="liters" type="number" min="0.01" step="0.01" value="${item.liters}" placeholder="Литры" required>
      <input name="total_cost" type="number" min="0.01" step="0.01" value="${item.total_cost}" placeholder="Сумма" required>
      <input name="station" type="text" value="${escapeHtml(item.station || "")}" placeholder="АЗС">
      <textarea name="note" rows="2" placeholder="Комментарий">${escapeHtml(item.note || "")}</textarea>
      <label class="checkbox-row">
        <input name="is_full_tank" type="checkbox" ${item.is_full_tank ? "checked" : ""}>
        <span>Полный бак</span>
      </label>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-fuel-edit">Отмена</button>
      </div>
    </form>
  `;
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
    ? state.lists.map((item) => {
      const canManage = item.access_role === "owner";
      return `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${item.items_done}/${item.items_total} выполнено · ${formatRole(item.access_role)}</div>
          </div>
        </div>
        <div class="item-actions">
          <button class="small action-open" data-action="open-list" data-id="${item.id}">Открыть</button>
          ${canManage ? `
            <button class="secondary small action-edit" data-action="rename-list" data-id="${item.id}" data-title="${escapeHtml(item.title)}">Переименовать</button>
            <button class="danger small action-danger" data-action="delete-list" data-id="${item.id}">Удалить</button>
          ` : ""}
        </div>
      </article>
    `;
    }).join("")
    : `<div class="item-meta">Списков пока нет.</div>`;
}

async function openList(listId) {
  const detail = await api(`/me/lists/${listId}`);
  state.selectedListId = detail.id;
  const canEdit = detail.access_role === "owner" || detail.access_role === "editor";
  const canManage = detail.access_role === "owner";
  $("#listDetailPanel").classList.remove("hidden");
  $("#listDetailPanel").innerHTML = `
    <h2>${escapeHtml(detail.title)}</h2>
    <div class="item-meta">${detail.items_done}/${detail.items_total} выполнено · ${formatRole(detail.access_role)}</div>
    ${canManage ? `
      <div class="item-actions">
        <button class="secondary small action-share" data-action="share-list" data-id="${detail.id}">Ссылки доступа</button>
        <button class="secondary small action-open" data-action="refresh-members" data-id="${detail.id}">Участники</button>
      </div>
      <div id="listSharePanel" class="subpanel hidden"></div>
      <div id="listMembersPanel" class="subpanel hidden"></div>
    ` : ""}
    ${canEdit ? `<form id="listItemCreateForm" class="stack" data-list-id="${detail.id}">
      <textarea name="text" rows="3" placeholder="Новый пункт или несколько строк" required></textarea>
      <button class="action-save" type="submit">Добавить</button>
    </form>` : `<div class="item-meta">У вас доступ только на просмотр.</div>`}
    <div class="item-list">
      ${detail.items.length ? detail.items.map((item) => `
        <div class="list-item-row">
          <input type="checkbox" data-action="toggle-item" data-id="${item.id}" ${item.is_completed ? "checked" : ""} ${canEdit ? "" : "disabled"}>
          <span>${escapeHtml(item.text)}</span>
          <div class="actions">
            ${canEdit ? `
              <button class="secondary small action-edit" data-action="edit-item" data-id="${item.id}" data-text="${escapeHtml(item.text)}">Изм.</button>
              <button class="danger small action-danger" data-action="delete-item" data-id="${item.id}">Удалить</button>
            ` : ""}
          </div>
        </div>
      `).join("") : `<div class="item-meta">Пунктов пока нет.</div>`}
    </div>
  `;
  $("#listItemCreateForm")?.addEventListener("submit", handleListItemCreate);
}

function renderListSharePanel(data) {
  const panel = $("#listSharePanel");
  if (!panel) return;
  panel.classList.remove("hidden");
  const rows = [
    ["Копия списка", data.copy_link, data.import_command],
    ["Редактор", data.editor_link, data.editor_join_command],
    ["Просмотр", data.viewer_link, data.viewer_join_command],
  ];
  panel.innerHTML = `
    <h3>Доступ к списку</h3>
    <div class="item-list">
      ${rows.map(([label, link, command]) => `
        <article class="compact-row">
          <div>
            <div class="item-title">${escapeHtml(label)}</div>
            <div class="item-meta">${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">Открыть ссылку</a>` : escapeHtml(command)}</div>
          </div>
          <button class="secondary small action-share" data-action="copy-share-text" data-text="${escapeHtml(link || command)}">Копировать</button>
        </article>
      `).join("")}
    </div>
  `;
}

function renderListMembersPanel(members) {
  const panel = $("#listMembersPanel");
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <h3>Участники</h3>
    <div class="item-list">
      ${members.length ? members.map((member) => `
        <article class="compact-row">
          <div>
            <div class="item-title">${escapeHtml(member.display_name)}</div>
            <div class="item-meta">${formatRole(member.role)} · user ${member.user_id}</div>
          </div>
          ${member.role === "owner" ? "" : `
            <div class="item-actions no-margin">
              <button class="secondary small action-edit" data-action="set-member-role" data-id="${member.member_id}" data-role="${member.role === "editor" ? "viewer" : "editor"}">
                ${member.role === "editor" ? "Сделать viewer" : "Сделать editor"}
              </button>
              <button class="danger small action-danger" data-action="remove-member" data-id="${member.member_id}">Убрать</button>
            </div>
          `}
        </article>
      `).join("") : `<div class="item-meta">Участников пока нет.</div>`}
    </div>
  `;
}

async function loadReminders() {
  state.reminders = await api("/me/reminders?active_only=false");
  $("#remindersContainer").innerHTML = state.reminders.length
    ? state.reminders.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title || "Напоминание")}</div>
            <div class="item-meta">${formatDate(item.remind_at_utc)} · ${formatRepeat(item.repeat_rule)} · ${formatReminderStatus(item.status)}</div>
          </div>
        </div>
        <details>
          <summary>Детали и действия</summary>
          <div class="item-text">${escapeHtml(item.text)}</div>
          ${state.editingReminderId === item.id ? renderReminderEditForm(item) : `
            <div class="item-actions">
              <button class="small action-done" data-action="done-reminder" data-id="${item.id}">Выполнено</button>
              <button class="secondary small action-edit" data-action="edit-reminder" data-id="${item.id}">Изменить</button>
              <button class="secondary small action-cancel" data-action="cancel-reminder" data-id="${item.id}">Отменить</button>
              <button class="danger small action-danger" data-action="delete-reminder" data-id="${item.id}">Удалить</button>
            </div>
          `}
        </details>
      </article>
    `).join("")
    : `<div class="item-meta">Напоминаний пока нет.</div>`;
  $$(".reminder-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleReminderUpdate(event).catch((error) => showMessage(error.message, true)));
  });
}

async function loadMedications() {
  state.medications = await api("/me/medications?active_only=false");
  $("#medicationsContainer").innerHTML = state.medications.length
    ? state.medications.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.name)}</div>
            <div class="item-meta">${formatImportance(item.importance)} · ${item.is_active ? "активно" : "архив"}</div>
          </div>
        </div>
        <div class="item-text">${escapeHtml([item.dosage, item.instructions].filter(Boolean).join("\n"))}</div>
        <div class="item-meta">Время: ${escapeHtml(item.daily_times_local?.join(", ") || "не задано")}</div>
        ${state.editingMedicationId === item.id ? renderMedicationEditForm(item) : `
          <div class="item-actions">
            <button class="small action-done" data-action="taken-medication" data-id="${item.id}">Принял</button>
            <button class="secondary small action-skip" data-action="skipped-medication" data-id="${item.id}">Пропустил</button>
            <button class="secondary small action-edit" data-action="edit-medication" data-id="${item.id}">Изм.</button>
            <button class="danger small action-danger" data-action="archive-medication" data-id="${item.id}">Архив</button>
          </div>
        `}
      </article>
    `).join("")
    : `<div class="item-meta">Лекарств пока нет.</div>`;
  $$(".medication-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleMedicationUpdate(event).catch((error) => showMessage(error.message, true)));
  });
}

function renderDriver() {
  const vehicles = state.driver?.vehicles || [];
  $("#vehiclesContainer").innerHTML = vehicles.length
    ? vehicles.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${item.current_mileage_km} км · ТО каждые ${item.service_interval_km} км / ${item.service_interval_months} мес.</div>
            <div class="item-meta">${escapeHtml(formatServicePlan(item.service_plan))}</div>
          </div>
        </div>
        <details ${state.selectedVehicleId === item.id ? "open" : ""}>
          <summary>Детали автомобиля</summary>
          ${state.editingVehicleId === item.id ? renderVehicleEditForm(item) : ""}
          ${state.serviceVehicleId === item.id ? renderServiceDoneForm(item) : ""}
          <div class="item-actions">
            <button class="small action-open" data-action="select-vehicle" data-id="${item.id}">Показать заправки</button>
            <button class="secondary small action-edit" data-action="edit-vehicle" data-id="${item.id}">Изменить</button>
            <button class="secondary small action-done" data-action="service-done" data-id="${item.id}">ТО сделано</button>
            <button class="danger small action-danger" data-action="delete-vehicle" data-id="${item.id}">Удалить</button>
          </div>
        </details>
      </article>
    `).join("")
    : `<div class="item-meta">Авто пока нет.</div>`;

  $$(".vehicle-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleVehicleUpdate(event).catch((error) => showMessage(error.message, true)));
  });
  $$(".service-done-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleServiceDone(event).catch((error) => showMessage(error.message, true)));
  });

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
  state.fuelEntries = entries;
  $("#fuelContainer").innerHTML = entries.length
    ? entries.map((item) => `
      <article class="item-card">
        <div class="item-title">${item.mileage_km} км · ${item.liters} л · ${formatMoney(item.total_cost)}</div>
        <div class="item-meta">${escapeHtml(item.station || "АЗС не указана")} · ${formatDate(item.filled_at_utc)}</div>
        <div class="item-meta">${item.consumption_l_per_100 ? `${item.consumption_l_per_100.toFixed(1)} л/100 км` : "расход пока не рассчитан"}</div>
        <details ${state.editingFuelId === item.id ? "open" : ""}>
          <summary>Детали заправки</summary>
          <div class="item-meta">Цена за литр: ${item.price_per_liter ? formatMoney(item.price_per_liter) : "не рассчитана"}</div>
          <div class="item-meta">Стоимость километра: ${item.cost_per_km ? formatMoney(item.cost_per_km) : "не рассчитана"}</div>
          <div class="item-meta">Тип заправки: ${item.is_full_tank ? "полный бак" : "частичная"}</div>
          ${item.note ? `<div class="item-text">${escapeHtml(item.note)}</div>` : ""}
          ${state.editingFuelId === item.id ? renderFuelEditForm(item) : `
            <div class="item-actions">
              <button class="secondary small action-edit" data-action="edit-fuel" data-id="${item.id}">Изменить</button>
              <button class="danger small action-danger" data-action="delete-fuel" data-id="${item.id}">Удалить</button>
            </div>
          `}
        </details>
      </article>
    `).join("")
    : `<div class="item-meta">Заправок пока нет.</div>`;
  $$(".fuel-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleFuelUpdate(event).catch((error) => showMessage(error.message, true)));
  });
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
        <div class="item-title">${escapeHtml(formatActionLabel(item))}</div>
        <div class="item-meta">${escapeHtml(item.domain_label || "раздел не определен")} · ${item.count} событий</div>
      </article>
    `).join("")}
  `;
  $("#adminFunnels").innerHTML = (funnels.funnels || []).map((funnel) => `
    <article class="item-card">
      <div class="item-title">${escapeHtml(funnel.label || funnel.name || "Сценарий")}</div>
      ${(funnel.stages || []).map((stage) => `
        <div class="item-meta">${escapeHtml(stage.label || stage.name || "шаг")}: ${stage.count}</div>
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

async function handleReminderUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const reminderId = form.dataset.id;
  await api(`/me/reminders/${reminderId}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: form.title.value,
      text: form.text.value,
      remind_at_local: form.remind_at_local.value,
      repeat_rule: form.repeat_rule.value,
    }),
  });
  state.editingReminderId = null;
  await loadReminders();
  await loadSummary();
  showMessage("Напоминание обновлено.");
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
  state.editingMedicationId = null;
  await loadMedications();
  await loadSummary();
}

async function handleMedicationUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const medicationId = form.dataset.id;
  await api(`/me/medications/${medicationId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: form.name.value,
      dosage: form.dosage.value,
      instructions: form.instructions.value,
      importance: form.importance.value,
      daily_times_local: parseTimes(form.daily_times_local.value),
    }),
  });
  state.editingMedicationId = null;
  await loadMedications();
  await loadSummary();
  showMessage("Лекарство обновлено.");
}

async function handleVehicleCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/driver/vehicles", {
    method: "POST",
    body: JSON.stringify({
      title: form.title.value,
      current_mileage_km: Number(form.current_mileage_km.value || 0),
      service_interval_km: Number(form.service_interval_km.value || 10000),
      service_interval_months: Number(form.service_interval_months.value || 12),
    }),
  });
  form.reset();
  await loadDriver();
  await loadSummary();
}

async function handleVehicleUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const vehicleId = form.dataset.id;
  await api(`/me/driver/vehicles/${vehicleId}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: form.title.value,
      current_mileage_km: Number(form.current_mileage_km.value),
      service_interval_km: Number(form.service_interval_km.value),
      service_interval_months: Number(form.service_interval_months.value),
    }),
  });
  state.editingVehicleId = null;
  await loadDriver();
  await loadSummary();
  showMessage("Автомобиль обновлен.");
}

async function handleServiceDone(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const vehicleId = form.dataset.id;
  await api(`/me/driver/vehicles/${vehicleId}/service-done`, {
    method: "POST",
    body: JSON.stringify({ service_mileage_km: Number(form.service_mileage_km.value) }),
  });
  state.serviceVehicleId = null;
  await loadDriver();
  await loadSummary();
  showMessage("ТО зафиксировано.");
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

async function handleFuelUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const entryId = form.dataset.id;
  await api(`/me/driver/fuel/${entryId}`, {
    method: "PATCH",
    body: JSON.stringify({
      mileage_km: Number(form.mileage_km.value),
      liters: Number(form.liters.value),
      total_cost: Number(form.total_cost.value),
      station: form.station.value,
      is_full_tank: form.is_full_tank.checked,
      note: form.note.value,
    }),
  });
  state.editingFuelId = null;
  await loadDriver();
  await loadSummary();
  showMessage("Заправка обновлена.");
}

async function handleAction(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;
  const needsSecondClick = new Set(["delete-list", "delete-item", "delete-reminder", "archive-medication", "delete-vehicle", "delete-fuel", "remove-member"]);
  if (needsSecondClick.has(action) && target.dataset.confirmed !== "1") {
    target.dataset.originalText = target.textContent;
    target.dataset.confirmed = "1";
    target.textContent = "Нажмите еще раз";
    window.setTimeout(() => {
      target.dataset.confirmed = "0";
      target.textContent = target.dataset.originalText || target.textContent;
    }, 3500);
    return;
  }
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
      await api(`/me/lists/${id}`, { method: "DELETE" });
      $("#listDetailPanel").classList.add("hidden");
      await loadLists();
      await loadSummary();
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
    } else if (action === "share-list") {
      const data = await api(`/me/lists/${id}/share`, { method: "POST" });
      renderListSharePanel(data);
    } else if (action === "refresh-members") {
      const members = await api(`/me/lists/${id}/members`);
      renderListMembersPanel(members);
    } else if (action === "set-member-role") {
      await api(`/me/lists/${state.selectedListId}/members/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: target.dataset.role }),
      });
      const members = await api(`/me/lists/${state.selectedListId}/members`);
      renderListMembersPanel(members);
    } else if (action === "remove-member") {
      await api(`/me/lists/${state.selectedListId}/members/${id}`, { method: "DELETE" });
      const members = await api(`/me/lists/${state.selectedListId}/members`);
      renderListMembersPanel(members);
    } else if (action === "copy-share-text") {
      await copyText(target.dataset.text);
    } else if (action === "done-reminder") {
      await api(`/me/reminders/${id}/done`, { method: "POST" });
      await loadReminders();
      await loadSummary();
    } else if (action === "cancel-reminder") {
      await api(`/me/reminders/${id}/cancel`, { method: "POST" });
      await loadReminders();
      await loadSummary();
    } else if (action === "delete-reminder") {
      await api(`/me/reminders/${id}`, { method: "DELETE" });
      await loadReminders();
      await loadSummary();
    } else if (action === "edit-reminder") {
      state.editingReminderId = Number(id);
      await loadReminders();
    } else if (action === "cancel-reminder-edit") {
      state.editingReminderId = null;
      await loadReminders();
    } else if (action === "taken-medication") {
      await api(`/me/medications/${id}/taken`, { method: "POST" });
      showMessage("Отметка сохранена.");
    } else if (action === "skipped-medication") {
      await api(`/me/medications/${id}/skipped`, { method: "POST" });
      showMessage("Пропуск сохранен.");
    } else if (action === "edit-medication") {
      state.editingMedicationId = Number(id);
      await loadMedications();
    } else if (action === "cancel-medication-edit") {
      state.editingMedicationId = null;
      await loadMedications();
    } else if (action === "archive-medication") {
      await api(`/me/medications/${id}`, { method: "DELETE" });
      await loadMedications();
      await loadSummary();
    } else if (action === "select-vehicle") {
      await loadFuel(id);
    } else if (action === "edit-vehicle") {
      state.editingVehicleId = Number(id);
      state.serviceVehicleId = null;
      await loadDriver();
    } else if (action === "cancel-vehicle-edit") {
      state.editingVehicleId = null;
      await loadDriver();
    } else if (action === "service-done") {
      state.serviceVehicleId = Number(id);
      state.editingVehicleId = null;
      await loadDriver();
    } else if (action === "cancel-service-done") {
      state.serviceVehicleId = null;
      await loadDriver();
    } else if (action === "delete-vehicle") {
      await api(`/me/driver/vehicles/${id}`, { method: "DELETE" });
      state.selectedVehicleId = null;
      await loadDriver();
      await loadSummary();
    } else if (action === "edit-fuel") {
      state.editingFuelId = Number(id);
      await loadFuel(state.selectedVehicleId);
    } else if (action === "cancel-fuel-edit") {
      state.editingFuelId = null;
      await loadFuel(state.selectedVehicleId);
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
  $("#menuToggle").addEventListener("click", toggleMobileMenu);
  $("#menuBackdrop").addEventListener("click", closeMobileMenu);
  $$(".nav-button").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.section)));
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("rememberme.theme", next);
  });
  $("#reloadButton").addEventListener("click", () => loadSection(state.section)
    .then(() => showMessage("Данные обновлены."))
    .catch((error) => showMessage(error.message, true)));
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
