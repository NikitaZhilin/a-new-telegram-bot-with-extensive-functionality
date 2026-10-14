"""Minimal browser UI for admin diagnostics."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/admin/ui", response_class=HTMLResponse, include_in_schema=False)
async def admin_ui() -> str:
    """Serve a static admin diagnostics page; data calls still require token."""
    return """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RememberMe Admin</title>
  <style>
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #f6f7f9; color: #111827; }
    main { max-width: 980px; margin: 0 auto; padding: 24px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 20px; }
    h1 { margin: 0; font-size: 28px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    .panel { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .metric { padding: 14px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fbfdff; }
    .metric b { display: block; font-size: 24px; margin-top: 4px; }
    label { display: block; font-size: 13px; color: #4b5563; margin-bottom: 6px; }
    input { width: min(420px, 100%); padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 6px; }
    button { padding: 10px 14px; border: 0; border-radius: 6px; background: #2563eb; color: white; cursor: pointer; }
    button.secondary { background: #4b5563; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid #e5e7eb; padding: 9px 6px; font-size: 14px; }
    .muted { color: #6b7280; }
    .error { color: #b91c1c; white-space: pre-wrap; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
    .toolbar select, .toolbar label { font-size: 14px; }
    .toolbar label { display: inline-flex; gap: 6px; align-items: center; margin: 0; }
    button.small { padding: 5px 9px; font-size: 13px; }
    button.ok { background: #059669; }
    pre.tb { white-space: pre-wrap; word-break: break-word; background: #111827; color: #e5e7eb; padding: 10px; border-radius: 6px; font-size: 12px; max-height: 420px; overflow: auto; }
    .badge { display: inline-block; padding: 1px 7px; border-radius: 10px; background: #fee2e2; color: #991b1b; font-size: 12px; }
    .badge.done { background: #d1fae5; color: #065f46; }
    .scroll { overflow-x: auto; }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>RememberMe Admin</h1>
      <div class="muted">Ошибки, обращения пользователей, активность. Токен хранится только в браузере.</div>
    </div>
    <button class="secondary" onclick="refresh()">Обновить</button>
  </header>

  <section class="panel">
    <label for="token">X-Admin-Token</label>
    <input id="token" type="password" autocomplete="off" placeholder="Введите admin token" />
    <button onclick="saveToken()">Сохранить</button>
    <div id="status" class="muted"></div>
  </section>

  <section class="panel">
    <h2>🧯 Журнал ошибок</h2>
    <div class="toolbar">
      <select id="errSection"><option value="">Все разделы</option></select>
      <label><input type="checkbox" id="errResolved" /> показывать решённые</label>
      <button class="small secondary" onclick="loadErrors()">Показать</button>
      <button class="small ok" onclick="resolveAll()">Отметить все решёнными</button>
    </div>
    <div id="errSummary" class="muted"></div>
    <div class="scroll"><table><thead><tr><th>№</th><th>Последний раз</th><th>Раздел</th><th>Ошибка</th><th>Раз</th><th>Что делали</th><th></th></tr></thead><tbody id="errors"></tbody></table></div>
    <div id="errDetail"></div>
  </section>

  <section class="panel">
    <h2>📬 Обращения пользователей</h2>
    <div id="fbSummary" class="muted"></div>
    <div class="scroll"><table><thead><tr><th>№</th><th>Когда</th><th>Тип</th><th>От кого</th><th>Текст</th><th>Статус</th><th></th></tr></thead><tbody id="feedback"></tbody></table></div>
  </section>

  <section class="grid">
    <div class="metric">Событий за 24 часа <b id="events24">-</b></div>
    <div class="metric">Событий за период <b id="eventsPeriod">-</b></div>
    <div class="metric">Активных других пользователей 24ч <b id="users24">-</b></div>
    <div class="metric">Активных других пользователей за период <b id="usersPeriod">-</b></div>
  </section>

  <section class="panel">
    <h2>Топ разделов</h2>
    <table><thead><tr><th>Раздел</th><th>Событий</th></tr></thead><tbody id="domains"></tbody></table>
  </section>

  <section class="panel">
    <h2>Топ действий</h2>
    <table><thead><tr><th>Действие</th><th>Раздел</th><th>Событий</th></tr></thead><tbody id="actions"></tbody></table>
  </section>

  <section class="panel">
    <h2>Воронки</h2>
    <div id="funnels"></div>
  </section>

  <section class="panel">
    <h2>Ошибки загрузки страницы</h2>
    <div id="error" class="error muted">Нет</div>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
tokenInput.value = localStorage.getItem('rememberme_admin_token') || '';

function saveToken() {
  localStorage.setItem('rememberme_admin_token', tokenInput.value);
  document.getElementById('status').textContent = 'Токен сохранен локально.';
  refresh();
}

function currentToken() {
  return tokenInput.value || localStorage.getItem('rememberme_admin_token') || '';
}

async function getJson(path) {
  const response = await fetch(path, { headers: { 'X-Admin-Token': currentToken() } });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'X-Admin-Token': currentToken(), 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-';
}

const SECTIONS = {
  reminders: 'Напоминания', notes: 'Заметки', medications: 'Лекарства', lists: 'Списки', checklists: 'Чек-листы',
  driver: 'Автомобиль', settings: 'Настройки', navigation: 'Меню и навигация', web: 'Веб-кабинет', api: 'API и админка',
  worker: 'Рассылка напоминаний', telegram: 'Связь с Telegram', database: 'База данных', feedback: 'Обратная связь', other: 'Прочее',
};
const sectionSelect = document.getElementById('errSection');
sectionSelect.innerHTML += Object.entries(SECTIONS).map(([key, label]) => `<option value="${key}">${label}</option>`).join('');

async function loadErrors() {
  const params = new URLSearchParams({ days: '90' });
  if (sectionSelect.value) params.set('section', sectionSelect.value);
  if (document.getElementById('errResolved').checked) params.set('include_resolved', 'true');
  const data = await getJson('/admin/errors?' + params.toString());
  const s = data.summary;
  document.getElementById('errSummary').textContent =
    `Открытых видов ошибок: ${s.open_kinds} · за 24 ч: ${s.kinds_seen_24h}` +
    (s.by_section.length ? ' · ' + s.by_section.map(item => `${item.label}: ${item.occurrences}`).join(', ') : '');
  document.getElementById('errors').innerHTML = data.errors.map(item => `
    <tr>
      <td>${item.id}</td>
      <td>${when(item.last_seen_at)}</td>
      <td>${esc(item.section_label)}<div class="muted">${esc(item.service)}</div></td>
      <td><b>${esc(item.error_type)}</b><div class="muted">${esc((item.message || '').slice(0, 160))}</div></td>
      <td>${item.count}</td>
      <td>${esc(item.context || '')}${item.telegram_id ? `<div class="muted">ID ${item.telegram_id}</div>` : ''}</td>
      <td>
        <button class="small secondary" onclick="showError(${item.id})">Подробнее</button>
        ${item.resolved_at ? '<span class="badge done">решена</span>' : `<button class="small ok" onclick="resolveError(${item.id})">Решено</button>`}
      </td>
    </tr>`).join('') || '<tr><td colspan="7" class="muted">Ошибок нет</td></tr>';
}

async function showError(id) {
  const item = await getJson(`/admin/errors/${id}`);
  document.getElementById('errDetail').innerHTML = `
    <h3>Ошибка №${item.id} · ${esc(item.section_label)}</h3>
    <div class="muted">Где: ${esc(item.location || '-')} · первая ${when(item.first_seen_at)} · последняя ${when(item.last_seen_at)} · повторов ${item.count}</div>
    <p><b>${esc(item.error_type)}</b>: ${esc(item.message)}</p>
    ${item.traceback ? `<pre class="tb">${esc(item.traceback)}</pre>` : ''}`;
}

async function resolveError(id) {
  await postJson(`/admin/errors/${id}/resolve`);
  await loadErrors();
}

async function resolveAll() {
  if (!window.confirm('Отметить все открытые ошибки решёнными?')) return;
  await postJson('/admin/errors/resolve-all');
  await loadErrors();
}

const FB_STATUS = { new: 'новое', read: 'прочитано', answered: 'отвечено' };

async function loadFeedback() {
  const data = await getJson('/admin/feedback');
  document.getElementById('fbSummary').textContent = `Новых: ${data.new}. Ответить пользователю можно из бота кнопкой «Ответить».`;
  document.getElementById('feedback').innerHTML = data.feedback.map(item => `
    <tr>
      <td>${item.id}</td>
      <td>${when(item.created_at)}</td>
      <td>${esc(item.kind_label)}</td>
      <td>${esc(item.first_name || '')}${item.username ? ' @' + esc(item.username) : ''}<div class="muted">ID ${item.telegram_id}</div></td>
      <td style="white-space: pre-wrap">${esc(item.text)}${item.has_photo ? '<div class="muted">📎 скриншот (в Telegram)</div>' : ''}${item.admin_reply ? `<div class="muted">↩️ ${esc(item.admin_reply)}</div>` : ''}</td>
      <td>${item.status === 'new' ? '<span class="badge">новое</span>' : FB_STATUS[item.status]}</td>
      <td>${item.status === 'new' ? `<button class="small secondary" onclick="markRead(${item.id})">Прочитано</button>` : ''}</td>
    </tr>`).join('') || '<tr><td colspan="7" class="muted">Обращений пока нет</td></tr>';
}

async function markRead(id) {
  await postJson(`/admin/feedback/${id}/status`, { status: 'read' });
  await loadFeedback();
}

function rows(target, items, render) {
  document.getElementById(target).innerHTML = items.map(render).join('') || '<tr><td colspan="3" class="muted">Нет данных</td></tr>';
}

async function refresh() {
  document.getElementById('error').textContent = 'Нет';
  try {
    await Promise.all([loadErrors(), loadFeedback()]);
    const [activity, funnels] = await Promise.all([
      getJson('/admin/activity'),
      getJson('/admin/funnels'),
    ]);
    document.getElementById('events24').textContent = activity.events_24h;
    document.getElementById('eventsPeriod').textContent = activity.events_period;
    document.getElementById('users24').textContent = activity.active_other_users_24h;
    document.getElementById('usersPeriod').textContent = activity.active_other_users_period;
    rows('domains', activity.top_domains, item => `<tr><td>${item.label}</td><td>${item.count}</td></tr>`);
    rows('actions', activity.top_actions, item => `<tr><td>${item.label}</td><td>${item.domain_label}</td><td>${item.count}</td></tr>`);
    document.getElementById('funnels').innerHTML = funnels.funnels.map(funnel => {
      const stageRows = funnel.stages.map(stage => (
        `<tr><td>${stage.label}</td><td>${stage.count}</td><td>${stage.conversion_from_previous ?? '-'}</td><td>${stage.drop_from_previous ?? '-'}</td></tr>`
      )).join('');
      return `<h3>${esc(funnel.label)}</h3><table><thead><tr><th>Этап</th><th>Событий</th><th>Конверсия, %</th><th>Потери</th></tr></thead><tbody>${stageRows}</tbody></table>`;
    }).join('');
  } catch (error) {
    document.getElementById('error').textContent = String(error);
  }
}

if (tokenInput.value) refresh();
</script>
</body>
</html>
"""
