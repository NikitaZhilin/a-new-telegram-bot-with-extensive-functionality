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
  driverPresets: [],
  fuelEntries: [],
  driverExpenses: [],
  driverDocuments: [],
  selectedListId: null,
  selectedVehicleId: null,
  editingListId: null,
  editingItemId: null,
  editingReminderId: null,
  editingMedicationId: null,
  editingVehicleId: null,
  editingFuelId: null,
  editingExpenseId: null,
  editingDocumentId: null,
  serviceVehicleId: null,
  adminUsers: [],
  adminFilters: {
    days: 7,
    userId: "",
  },
};

const titles = {
  dashboard: ["Сводка", "Текущие данные бота в web-версии."],
  lists: ["Списки", "Создание, просмотр и отметка пунктов."],
  reminders: ["Напоминания", "Активные напоминания пользователя."],
  medications: ["Лекарства", "Приемы, важность и ежедневное расписание."],
  driver: ["Водитель", "Автомобили, заправки, расходы и документы."],
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
    ["Автомобили", stats.driver?.vehicles_count ?? 0, `заправок: ${stats.driver?.fuel_entries_count ?? 0}; документов: ${stats.driver?.documents_active_count ?? 0}`],
    ["Расходы на авто", formatMoney(stats.driver?.driver_total_cost ?? stats.driver?.fuel_total_cost ?? 0), `топливо: ${formatMoney(stats.driver?.fuel_total_cost ?? 0)}; прочее: ${formatMoney(stats.driver?.expense_total_cost ?? 0)}`],
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
        `Прочие расходы: ${formatMoney(stats.driver?.expense_total_cost ?? 0)}`,
        `Документы: ${stats.driver?.documents_active_count ?? 0}, скоро истекают: ${stats.driver?.documents_expiring_soon_count ?? 0}`,
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

function formatExpenseCategory(value) {
  return {
    service: "ТО и ремонт",
    parts: "Запчасти",
    wash: "Мойка",
    insurance: "Страховка",
    parking: "Парковка",
    fine: "Штраф",
    other: "Другое",
  }[value] || value || "Другое";
}

function formatDocumentType(value) {
  return {
    insurance: "ОСАГО/КАСКО",
    license: "Права",
    diagnostic: "Диагностика",
    tax: "Налог",
    fine: "Штраф",
    other: "Другое",
  }[value] || value || "Другое";
}

function formatVehicleName(vehicleId) {
  const vehicle = (state.driver?.vehicles || []).find((item) => Number(item.id) === Number(vehicleId));
  return vehicle ? vehicle.title : "без привязки к авто";
}

function fuelTypeLabel(value) {
  return {
    petrol: "бензин",
    diesel: "дизель",
    hybrid: "гибрид",
    electric: "электро",
    lpg: "газ",
  }[value] || value || "не указано";
}

function transmissionLabel(value) {
  return {
    manual: "МКПП",
    automatic: "АКПП",
    robot: "робот",
    cvt: "вариатор",
  }[value] || value || "не указано";
}

function driveTypeLabel(value) {
  return {
    fwd: "передний",
    rwd: "задний",
    awd: "полный",
  }[value] || value || "не указано";
}

function formatExpectedConsumption(item) {
  const city = item.expected_consumption_city_l_per_100 ?? item.consumption_city_l_per_100;
  const highway = item.expected_consumption_highway_l_per_100 ?? item.consumption_highway_l_per_100;
  const mixed = item.expected_consumption_mixed_l_per_100 ?? item.consumption_mixed_l_per_100;
  const parts = [];
  if (city) parts.push(`город ${Number(city).toFixed(1)}`);
  if (highway) parts.push(`трасса ${Number(highway).toFixed(1)}`);
  if (mixed) parts.push(`смешанный ${Number(mixed).toFixed(1)}`);
  return parts.length ? `${parts.join(", ")} л/100 км` : "не указан";
}

function findVehiclePreset(slug) {
  return state.driverPresets.find((item) => item.slug === slug) || null;
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

function formatMedicationMarkState(item) {
  if (!item.is_active) return "Препарат в архиве.";
  if (item.can_mark_now) return "Можно отметить прием сейчас.";
  if (item.marked_at_utc) {
    return `Прием уже отмечен: ${formatDate(item.marked_at_utc)}.`;
  }
  if (item.next_available_at_utc) {
    return `Следующая отметка будет доступна: ${formatDate(item.next_available_at_utc)}.`;
  }
  return "Сейчас отметка недоступна.";
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

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showMessage("Скопировано.");
  } catch {
    showMessage("Не удалось скопировать автоматически. Выделите текст ссылки вручную.", true);
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

function renderListRenameForm(item) {
  return `
    <form class="stack inline-edit-form list-rename-form" data-id="${item.id}">
      <input name="title" type="text" value="${escapeHtml(item.title)}" placeholder="Название списка" required>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-list-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderListItemEditForm(item) {
  return `
    <form class="stack inline-edit-form list-item-edit-form" data-id="${item.id}">
      <textarea name="text" rows="3" placeholder="Текст пункта" required>${escapeHtml(item.text || "")}</textarea>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-list-item-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderVehicleOptions(selectedId = null, includeEmpty = true) {
  const empty = includeEmpty ? `<option value="">Без привязки к авто</option>` : "";
  const options = (state.driver?.vehicles || []).map((vehicle) => `
    <option value="${vehicle.id}" ${Number(selectedId) === Number(vehicle.id) ? "selected" : ""}>${escapeHtml(vehicle.title)}</option>
  `).join("");
  return empty + options;
}

function renderExpenseEditForm(item) {
  return `
    <form class="stack inline-edit-form expense-edit-form" data-id="${item.id}">
      <select name="vehicle_id">${renderVehicleOptions(item.vehicle_id)}</select>
      <input name="title" type="text" value="${escapeHtml(item.title)}" placeholder="Название" required>
      <select name="category">
        ${["service", "parts", "wash", "insurance", "parking", "fine", "other"].map((value) => `
          <option value="${value}" ${item.category === value ? "selected" : ""}>${formatExpenseCategory(value)}</option>
        `).join("")}
      </select>
      <input name="amount" type="number" min="0.01" step="0.01" value="${item.amount}" placeholder="Сумма" required>
      <input name="spent_at_local" type="datetime-local" value="${escapeHtml(toLocalInputFromIso(item.spent_at_utc))}">
      <textarea name="note" rows="2" placeholder="Комментарий">${escapeHtml(item.note || "")}</textarea>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-expense-edit">Отмена</button>
      </div>
    </form>
  `;
}

function renderDocumentEditForm(item) {
  const expires = item.expires_at_utc ? new Date(item.expires_at_utc).toISOString().slice(0, 10) : "";
  return `
    <form class="stack inline-edit-form document-edit-form" data-id="${item.id}">
      <select name="vehicle_id">${renderVehicleOptions(item.vehicle_id)}</select>
      <input name="title" type="text" value="${escapeHtml(item.title)}" placeholder="Название" required>
      <select name="document_type">
        ${["insurance", "license", "diagnostic", "tax", "fine", "other"].map((value) => `
          <option value="${value}" ${item.document_type === value ? "selected" : ""}>${formatDocumentType(value)}</option>
        `).join("")}
      </select>
      <input name="identifier" type="text" value="${escapeHtml(item.identifier || "")}" placeholder="Номер или пометка">
      <input name="expires_at_local" type="date" value="${escapeHtml(expires)}">
      <input name="remind_before_days" type="number" min="0" value="${item.remind_before_days}" placeholder="Напомнить за дней">
      <textarea name="note" rows="2" placeholder="Комментарий">${escapeHtml(item.note || "")}</textarea>
      <label class="checkbox-row">
        <input name="is_active" type="checkbox" ${item.is_active ? "checked" : ""}>
        <span>Активен</span>
      </label>
      <div class="button-row">
        <button class="small action-save" type="submit">Сохранить</button>
        <button class="secondary small action-cancel" type="button" data-action="cancel-document-edit">Отмена</button>
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
        ${state.editingListId === item.id ? renderListRenameForm(item) : `
          <div class="item-actions">
            <button class="small action-open" data-action="open-list" data-id="${item.id}">Открыть</button>
            ${canManage ? `
              <button class="secondary small action-edit" data-action="rename-list" data-id="${item.id}">Переименовать</button>
              <button class="danger small action-danger" data-action="delete-list" data-id="${item.id}">Удалить</button>
            ` : ""}
          </div>
        `}
      </article>
    `;
    }).join("")
    : `<div class="item-meta">Списков пока нет.</div>`;
  $$(".list-rename-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleListRename(event).catch((error) => showMessage(error.message, true)));
  });
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
          <div class="list-item-content">
            ${state.editingItemId === item.id ? renderListItemEditForm(item) : `<span>${escapeHtml(item.text)}</span>`}
          </div>
          ${state.editingItemId === item.id ? "" : `
            <div class="actions">
              ${canEdit ? `
                <button class="secondary small action-edit" data-action="edit-item" data-id="${item.id}">Изменить</button>
                <button class="danger small action-danger" data-action="delete-item" data-id="${item.id}">Удалить</button>
              ` : ""}
            </div>
          `}
        </div>
      `).join("") : `<div class="item-meta">Пунктов пока нет.</div>`}
    </div>
  `;
  $("#listItemCreateForm")?.addEventListener("submit", handleListItemCreate);
  $$(".list-item-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleListItemUpdate(event).catch((error) => showMessage(error.message, true)));
  });
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
    ? state.medications.map((item) => {
      const canMark = Boolean(item.is_active && item.can_mark_now);
      return `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.name)}</div>
            <div class="item-meta">${formatImportance(item.importance)} · ${item.is_active ? "активно" : "архив"}</div>
          </div>
        </div>
        <div class="item-text">${escapeHtml([item.dosage, item.instructions].filter(Boolean).join("\n"))}</div>
        <div class="item-meta">Время: ${escapeHtml(item.daily_times_local?.join(", ") || "не задано")}</div>
        <div class="item-meta">${escapeHtml(formatMedicationMarkState(item))}</div>
        ${state.editingMedicationId === item.id ? renderMedicationEditForm(item) : `
          <div class="item-actions">
            ${item.is_active ? `
              <button class="small action-done" data-action="taken-medication" data-id="${item.id}" ${canMark ? "" : "disabled"}>Принял</button>
              <button class="secondary small action-skip" data-action="skipped-medication" data-id="${item.id}" ${canMark ? "" : "disabled"}>Пропустил</button>
            ` : ""}
            <button class="secondary small action-edit" data-action="edit-medication" data-id="${item.id}">Изм.</button>
            ${item.is_active ? `<button class="danger small action-danger" data-action="archive-medication" data-id="${item.id}">Архив</button>` : ""}
          </div>
        `}
      </article>
    `;
    }).join("")
    : `<div class="item-meta">Лекарств пока нет.</div>`;
  $$(".medication-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleMedicationUpdate(event).catch((error) => showMessage(error.message, true)));
  });
}

function renderDriver() {
  const vehicles = state.driver?.vehicles || [];
  renderDriverOverview();
  renderVehiclePresetSelect();
  $("#vehiclesContainer").innerHTML = vehicles.length
    ? vehicles.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${item.current_mileage_km} км · ТО каждые ${item.service_interval_km} км / ${item.service_interval_months} мес.</div>
            ${(item.make || item.model || item.engine_volume_l || item.expected_consumption_mixed_l_per_100) ? `
              <div class="item-meta">
                ${escapeHtml([item.make, item.model, item.year].filter(Boolean).join(" ")) || "Параметры авто"}
                ${item.body_type ? ` · ${escapeHtml(item.body_type)}` : ""}
              </div>
              <div class="item-meta">
                ${item.engine_volume_l ? `${Number(item.engine_volume_l).toFixed(1)} л` : "объем не указан"}
                ${item.engine_power_hp ? ` · ${item.engine_power_hp} л.с.` : ""}
                · ${escapeHtml(fuelTypeLabel(item.fuel_type))}
                · ${escapeHtml(transmissionLabel(item.transmission))}
                · ${escapeHtml(driveTypeLabel(item.drive_type))}
              </div>
              <div class="item-meta">Ориентир расхода: ${escapeHtml(formatExpectedConsumption(item))}</div>
            ` : ""}
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
  $("#expenseCreateForm select[name='vehicle_id']").innerHTML = renderVehicleOptions();
  $("#documentCreateForm select[name='vehicle_id']").innerHTML = renderVehicleOptions();
  const vehicleIds = new Set(vehicles.map((item) => Number(item.id)));
  if (state.selectedVehicleId && !vehicleIds.has(Number(state.selectedVehicleId))) {
    state.selectedVehicleId = null;
  }
  if (!state.selectedVehicleId && vehicles[0]) {
    state.selectedVehicleId = vehicles[0].id;
  }
  if (state.selectedVehicleId) {
    select.value = String(state.selectedVehicleId);
  }
}

function renderDriverOverview() {
  const overview = state.driver?.overview || {};
  const cards = [
    ["Авто", overview.vehicles_count ?? 0, `максимальный пробег: ${overview.max_mileage_km ?? 0} км`],
    ["Заправки", overview.fuel_entries_count ?? 0, `топливо: ${formatMoney(overview.fuel_total_cost ?? 0)}`],
    ["Расходы", formatMoney(overview.driver_total_cost ?? overview.fuel_total_cost ?? 0), `прочие: ${formatMoney(overview.expense_total_cost ?? 0)}`],
    ["Документы", overview.documents_active_count ?? 0, `скоро истекают: ${overview.documents_expiring_soon_count ?? 0}`],
  ];
  $("#driverOverview").innerHTML = cards.map(([label, value, detail]) => `
    <article class="metric">
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-detail">${escapeHtml(detail)}</div>
    </article>
  `).join("");
}

function renderVehiclePresetSelect() {
  const select = $("#vehicleCreateForm select[name='preset_slug']");
  if (!select) return;
  const currentValue = select.value;
  select.innerHTML = [
    `<option value="">Выбрать из справочника или ввести вручную</option>`,
    ...state.driverPresets.map((preset) => (
      `<option value="${escapeHtml(preset.slug)}">${escapeHtml(preset.label)}</option>`
    )),
  ].join("");
  select.value = currentValue;
  renderVehiclePresetDetails();
}

function renderVehiclePresetDetails() {
  const form = $("#vehicleCreateForm");
  const target = $("#vehiclePresetDetails");
  if (!form || !target) return;
  const preset = findVehiclePreset(form.preset_slug.value);
  if (!preset) {
    target.innerHTML = "Можно выбрать готовый вариант или заполнить поля вручную.";
    return;
  }
  target.innerHTML = `
    <strong>${escapeHtml(preset.label)}</strong><br>
    ${escapeHtml(preset.body_type)} · ${preset.year || "год уточняется вручную"} ·
    ${Number(preset.engine_volume_l).toFixed(1)} л${preset.engine_power_hp ? ` · ${preset.engine_power_hp} л.с.` : ""}
    · ${escapeHtml(fuelTypeLabel(preset.fuel_type))}
    · ${escapeHtml(transmissionLabel(preset.transmission))}
    · ${escapeHtml(driveTypeLabel(preset.drive_type))}<br>
    Ориентир расхода: ${escapeHtml(formatExpectedConsumption(preset))}<br>
    ${escapeHtml(preset.note)}
  `;
}

function applyVehiclePresetToCreateForm() {
  const form = $("#vehicleCreateForm");
  const preset = findVehiclePreset(form.preset_slug.value);
  renderVehiclePresetDetails();
  if (!preset) return;
  form.title.value = preset.title;
  form.service_interval_km.value = preset.service_interval_km || 10000;
  form.service_interval_months.value = preset.service_interval_months || 12;
  form.expected_consumption_mixed_l_per_100.value = preset.consumption_mixed_l_per_100 || "";
}

async function loadDriver() {
  if (!state.driverPresets.length) {
    state.driverPresets = await api("/me/driver/vehicle-presets");
  }
  state.driver = await api("/me/driver");
  state.driverExpenses = state.driver.expenses || [];
  state.driverDocuments = state.driver.documents || [];
  renderDriver();
  renderExpenses();
  renderDocuments();
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

function renderExpenses() {
  $("#expensesContainer").innerHTML = state.driverExpenses.length
    ? state.driverExpenses.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${formatMoney(item.amount)} · ${formatExpenseCategory(item.category)} · ${formatDate(item.spent_at_utc)}</div>
            <div class="item-meta">${escapeHtml(formatVehicleName(item.vehicle_id))}</div>
          </div>
        </div>
        <details ${state.editingExpenseId === item.id ? "open" : ""}>
          <summary>Детали расхода</summary>
          ${item.note ? `<div class="item-text">${escapeHtml(item.note)}</div>` : ""}
          ${state.editingExpenseId === item.id ? renderExpenseEditForm(item) : `
            <div class="item-actions">
              <button class="secondary small action-edit" data-action="edit-expense" data-id="${item.id}">Изменить</button>
              <button class="danger small action-danger" data-action="delete-expense" data-id="${item.id}">Удалить</button>
            </div>
          `}
        </details>
      </article>
    `).join("")
    : `<div class="item-meta">Ручных расходов пока нет.</div>`;
  $$(".expense-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleExpenseUpdate(event).catch((error) => showMessage(error.message, true)));
  });
}

function renderDocuments() {
  $("#documentsContainer").innerHTML = state.driverDocuments.length
    ? state.driverDocuments.map((item) => `
      <article class="item-card">
        <div class="item-card-header">
          <div>
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-meta">${formatDocumentType(item.document_type)} · ${item.is_active ? "активен" : "архив"}</div>
            <div class="item-meta">${item.expires_at_utc ? `действует до ${formatDate(item.expires_at_utc)}` : "срок не указан"} · ${escapeHtml(formatVehicleName(item.vehicle_id))}</div>
          </div>
        </div>
        <details ${state.editingDocumentId === item.id ? "open" : ""}>
          <summary>Детали документа</summary>
          ${item.identifier ? `<div class="item-meta">Номер/пометка: ${escapeHtml(item.identifier)}</div>` : ""}
          <div class="item-meta">Напомнить за ${item.remind_before_days} дн.</div>
          ${item.note ? `<div class="item-text">${escapeHtml(item.note)}</div>` : ""}
          ${state.editingDocumentId === item.id ? renderDocumentEditForm(item) : `
            <div class="item-actions">
              <button class="secondary small action-edit" data-action="edit-document" data-id="${item.id}">Изменить</button>
              <button class="danger small action-danger" data-action="delete-document" data-id="${item.id}">Удалить</button>
            </div>
          `}
        </details>
      </article>
    `).join("")
    : `<div class="item-meta">Документов пока нет.</div>`;
  $$(".document-edit-form").forEach((form) => {
    form.addEventListener("submit", (event) => handleDocumentUpdate(event).catch((error) => showMessage(error.message, true)));
  });
}

async function loadAdmin() {
  if (!state.auth.adminToken) {
    $("#adminActivity").innerHTML = `<div class="item-meta">Нужен admin token.</div>`;
    $("#adminFunnels").innerHTML = "";
    $("#adminActivityOverview").innerHTML = "";
    return;
  }
  if (!state.adminUsers.length) {
    const users = await adminApi("/admin/users?page_size=100");
    state.adminUsers = users.users || [];
    const selected = state.adminFilters.userId;
    $("#adminActivityFilterForm select[name='user_id']").innerHTML = `
      <option value="">Все пользователи</option>
      ${state.adminUsers.map((user) => `
        <option value="${user.id}" ${String(user.id) === String(selected) ? "selected" : ""}>
          ${escapeHtml(user.first_name || user.username || `user ${user.telegram_id}`)} · ${user.telegram_id}
        </option>
      `).join("")}
    `;
  }
  $("#adminActivityFilterForm select[name='days']").value = String(state.adminFilters.days);
  $("#adminActivityFilterForm select[name='user_id']").value = state.adminFilters.userId;
  const params = new URLSearchParams({ days: String(state.adminFilters.days) });
  if (state.adminFilters.userId) {
    params.set("user_id", state.adminFilters.userId);
  }
  const [activity, funnels] = await Promise.all([
    adminApi(`/admin/activity?${params}`),
    adminApi(`/admin/funnels?${params}`),
  ]);
  $("#adminActivityOverview").innerHTML = [
    ["События за 24 часа", activity.events_24h, "по выбранному фильтру"],
    [`События за ${activity.period_days} дн.`, activity.events_period, "все действия без текстов сообщений"],
    ["Активных других пользователей", activity.active_other_users_period, "кроме вашего admin-пользователя"],
  ].map(([label, value, detail]) => `
    <article class="metric">
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-detail">${escapeHtml(detail)}</div>
    </article>
  `).join("");
  $("#adminActivity").innerHTML = `
    <h3>Самые используемые разделы</h3>
    ${(activity.top_domains || []).map((item) => `
      <article class="item-card">
        <div class="item-title">${escapeHtml(item.label || item.domain || "Раздел")}</div>
        <div class="item-meta">${item.count} событий за выбранный период</div>
      </article>
    `).join("") || `<div class="item-meta">По разделам пока нет данных.</div>`}
    <h3>Самые частые действия</h3>
    ${(activity.top_actions || []).map((item) => `
      <article class="item-card">
        <div class="item-title">${escapeHtml(formatActionLabel(item))}</div>
        <div class="item-meta">${escapeHtml(item.domain_label || "раздел не определен")} · ${item.count} событий</div>
      </article>
    `).join("") || `<div class="item-meta">По действиям пока нет данных.</div>`}
  `;
  $("#adminFunnels").innerHTML = (funnels.funnels || []).map((funnel) => `
    <article class="item-card">
      <div class="item-title">${escapeHtml(funnel.label || funnel.name || "Сценарий")}</div>
      ${(funnel.stages || []).map((stage) => `
        <div class="item-meta">${escapeHtml(stage.label || stage.name || "шаг")}: ${stage.count}${stage.conversion_from_previous !== null && stage.conversion_from_previous !== undefined ? ` · ${stage.conversion_from_previous}% от прошлого шага` : ""}</div>
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

async function handleListRename(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const listId = form.dataset.id;
  await api(`/me/lists/${listId}`, {
    method: "PATCH",
    body: JSON.stringify({ title: form.title.value }),
  });
  state.editingListId = null;
  await loadLists();
  if (Number(state.selectedListId) === Number(listId)) {
    await openList(listId);
  }
  await loadSummary();
  showMessage("Список переименован.");
}

async function handleListItemUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api(`/me/lists/items/${form.dataset.id}`, {
    method: "PATCH",
    body: JSON.stringify({ text: form.text.value }),
  });
  state.editingItemId = null;
  await openList(state.selectedListId);
  await loadLists();
  showMessage("Пункт обновлен.");
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
  const preset = findVehiclePreset(form.preset_slug.value);
  const expectedMixed = form.expected_consumption_mixed_l_per_100.value
    ? Number(form.expected_consumption_mixed_l_per_100.value)
    : preset?.consumption_mixed_l_per_100 || null;
  await api("/me/driver/vehicles", {
    method: "POST",
    body: JSON.stringify({
      title: form.title.value,
      current_mileage_km: Number(form.current_mileage_km.value || 0),
      service_interval_km: Number(form.service_interval_km.value || 10000),
      service_interval_months: Number(form.service_interval_months.value || 12),
      preset_slug: preset?.slug || null,
      make: preset?.make || null,
      model: preset?.model || null,
      year: preset?.year || null,
      body_type: preset?.body_type || null,
      engine_volume_l: preset?.engine_volume_l || null,
      engine_power_hp: preset?.engine_power_hp || null,
      fuel_type: preset?.fuel_type || null,
      transmission: preset?.transmission || null,
      drive_type: preset?.drive_type || null,
      expected_consumption_city_l_per_100: preset?.consumption_city_l_per_100 || null,
      expected_consumption_highway_l_per_100: preset?.consumption_highway_l_per_100 || null,
      expected_consumption_mixed_l_per_100: expectedMixed,
      vehicle_specs_note: preset?.note || null,
    }),
  });
  form.reset();
  renderVehiclePresetDetails();
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

function dateInputToLocalDatetime(value) {
  return value ? `${value}T12:00` : null;
}

async function handleExpenseCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/driver/expenses", {
    method: "POST",
    body: JSON.stringify({
      vehicle_id: form.vehicle_id.value ? Number(form.vehicle_id.value) : null,
      title: form.title.value,
      category: form.category.value,
      amount: Number(form.amount.value),
      spent_at_local: form.spent_at_local.value || null,
      note: form.note.value || null,
    }),
  });
  form.reset();
  form.spent_at_local.value = toDatetimeLocal(new Date());
  await loadDriver();
  await loadSummary();
  showMessage("Расход сохранен.");
}

async function handleExpenseUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api(`/me/driver/expenses/${form.dataset.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      vehicle_id: form.vehicle_id.value ? Number(form.vehicle_id.value) : null,
      title: form.title.value,
      category: form.category.value,
      amount: Number(form.amount.value),
      spent_at_local: form.spent_at_local.value || null,
      note: form.note.value || null,
    }),
  });
  state.editingExpenseId = null;
  await loadDriver();
  await loadSummary();
  showMessage("Расход обновлен.");
}

async function handleDocumentCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api("/me/driver/documents", {
    method: "POST",
    body: JSON.stringify({
      vehicle_id: form.vehicle_id.value ? Number(form.vehicle_id.value) : null,
      title: form.title.value,
      document_type: form.document_type.value,
      identifier: form.identifier.value || null,
      expires_at_local: dateInputToLocalDatetime(form.expires_at_local.value),
      remind_before_days: Number(form.remind_before_days.value || 0),
      note: form.note.value || null,
      is_active: true,
    }),
  });
  form.reset();
  form.remind_before_days.value = 14;
  await loadDriver();
  await loadSummary();
  showMessage("Документ сохранен.");
}

async function handleDocumentUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await api(`/me/driver/documents/${form.dataset.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      vehicle_id: form.vehicle_id.value ? Number(form.vehicle_id.value) : null,
      title: form.title.value,
      document_type: form.document_type.value,
      identifier: form.identifier.value || null,
      expires_at_local: dateInputToLocalDatetime(form.expires_at_local.value),
      remind_before_days: Number(form.remind_before_days.value || 0),
      note: form.note.value || null,
      is_active: form.is_active.checked,
    }),
  });
  state.editingDocumentId = null;
  await loadDriver();
  await loadSummary();
  showMessage("Документ обновлен.");
}

async function handleAction(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;
  const needsSecondClick = new Set(["delete-list", "delete-item", "delete-reminder", "archive-medication", "delete-vehicle", "delete-fuel", "delete-expense", "delete-document", "remove-member"]);
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
      state.editingListId = Number(id);
      await loadLists();
    } else if (action === "cancel-list-edit") {
      state.editingListId = null;
      await loadLists();
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
      state.editingItemId = Number(id);
      await openList(state.selectedListId);
    } else if (action === "cancel-list-item-edit") {
      state.editingItemId = null;
      await openList(state.selectedListId);
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
      const result = await api(`/me/medications/${id}/taken`, { method: "POST" });
      await loadMedications();
      await loadSummary();
      showMessage(result.ok ? "Прием отмечен." : "Этот прием уже отмечен или сейчас недоступен.", !result.ok);
    } else if (action === "skipped-medication") {
      const result = await api(`/me/medications/${id}/skipped`, { method: "POST" });
      await loadMedications();
      await loadSummary();
      showMessage(result.ok ? "Пропуск отмечен." : "Этот прием уже отмечен или сейчас недоступен.", !result.ok);
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
    } else if (action === "edit-expense") {
      state.editingExpenseId = Number(id);
      await loadDriver();
    } else if (action === "cancel-expense-edit") {
      state.editingExpenseId = null;
      renderExpenses();
    } else if (action === "delete-expense") {
      await api(`/me/driver/expenses/${id}`, { method: "DELETE" });
      await loadDriver();
      await loadSummary();
    } else if (action === "edit-document") {
      state.editingDocumentId = Number(id);
      await loadDriver();
    } else if (action === "cancel-document-edit") {
      state.editingDocumentId = null;
      renderDocuments();
    } else if (action === "delete-document") {
      await api(`/me/driver/documents/${id}`, { method: "DELETE" });
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
  $("#expenseCreateForm").addEventListener("submit", (event) => handleExpenseCreate(event).catch((error) => showMessage(error.message, true)));
  $("#documentCreateForm").addEventListener("submit", (event) => handleDocumentCreate(event).catch((error) => showMessage(error.message, true)));
  $("#adminActivityFilterForm").addEventListener("submit", (event) => {
    event.preventDefault();
    state.adminFilters.days = Number(event.currentTarget.days.value || 7);
    state.adminFilters.userId = event.currentTarget.user_id.value || "";
    loadAdmin().catch((error) => showMessage(error.message, true));
  });
  document.body.addEventListener("click", handleAction);
  $("#vehicleCreateForm select[name='preset_slug']").addEventListener("change", applyVehiclePresetToCreateForm);
  $("#fuelCreateForm select[name='vehicle_id']").addEventListener("change", (event) => loadFuel(event.target.value).catch((error) => showMessage(error.message, true)));
}

async function boot() {
  document.documentElement.dataset.theme = localStorage.getItem("rememberme.theme") || "light";
  $("#reminderCreateForm input[name='remind_at_local']").value = defaultReminderTime();
  $("#expenseCreateForm input[name='spent_at_local']").value = toDatetimeLocal(new Date());
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
