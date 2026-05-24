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
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>RememberMe Admin</h1>
      <div class="muted">Активность и воронки. Токен хранится только в браузере.</div>
    </div>
    <button class="secondary" onclick="refresh()">Обновить</button>
  </header>

  <section class="panel">
    <label for="token">X-Admin-Token</label>
    <input id="token" type="password" autocomplete="off" placeholder="Введите admin token" />
    <button onclick="saveToken()">Сохранить</button>
    <div id="status" class="muted"></div>
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
    <h2>Ошибки</h2>
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

async function getJson(path) {
  const token = tokenInput.value || localStorage.getItem('rememberme_admin_token') || '';
  const response = await fetch(path, { headers: { 'X-Admin-Token': token } });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function rows(target, items, render) {
  document.getElementById(target).innerHTML = items.map(render).join('') || '<tr><td colspan="3" class="muted">Нет данных</td></tr>';
}

async function refresh() {
  document.getElementById('error').textContent = 'Нет';
  try {
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
      return `<h3>${funnel.label}</h3><table><thead><tr><th>Этап</th><th>Событий</th><th>Конверсия, %</th><th>Потери</th></tr></thead><tbody>${stageRows}</tbody></table>`;
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
