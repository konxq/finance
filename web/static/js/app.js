/* Extracted JS from original index.html */

/* =========================================================
   TELEGRAM WEB APP
========================================================= */

const tg = window.Telegram?.WebApp || null;

function initTelegram() {
  if (!tg) {
    console.warn('Telegram WebApp SDK not available');
    return;
  }

  try {
    tg.ready();
    tg.expand();
  } catch (error) {
    console.error('Telegram init error:', error);
  }

  try {
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    if (bg) {
      tg.setHeaderColor?.(bg);
      tg.setBackgroundColor?.(bg);
    }
  } catch (_) {}
}

initTelegram();

/* =========================================================
   STATE
========================================================= */

let dailyChart = null;
let incomeChart = null;
let expenseChart = null;

let currentData = null;

/* =========================================================
   HELPERS
========================================================= */

const money = value => {
  const n = Number(value || 0);
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) + ' zł';
};

const number = value => {
  const n = Number(value || 0);
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n);
};

const esc = value => {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
};

const periodNames = { day: 'сегодня', week: 'текущую неделю', month: 'текущий месяц', year: 'текущий год', all: 'всё время' };

function destroyCharts() {
  if (dailyChart) { dailyChart.destroy(); dailyChart = null; }
  if (incomeChart) { incomeChart.destroy(); incomeChart = null; }
  if (expenseChart) { expenseChart.destroy(); expenseChart = null; }
}

function dateToLabel(dateString) {
  if (!dateString) return '';
  const parts = dateString.split('-');
  if (parts.length !== 3) return dateString;
  return parts[2] + '.' + parts[1];
}

function dateToShort(dateString) { return dateToLabel(dateString); }

function getDateRange(period) {
  const now = new Date(); now.setHours(0,0,0,0);
  let start = new Date(now); let end = new Date(now);

  if (period === 'day') { end.setDate(end.getDate() + 1); }
  else if (period === 'week') {
    const day = start.getDay();
    const mondayOffset = day === 0 ? -6 : 1 - day;
    start.setDate(start.getDate() + mondayOffset);
    end = new Date(start); end.setDate(end.getDate() + 7);
  } else if (period === 'month') {
    start = new Date(now.getFullYear(), now.getMonth(), 1);
    end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  } else if (period === 'year') {
    start = new Date(now.getFullYear(), 0, 1);
    end = new Date(now.getFullYear() + 1, 0, 1);
  } else { return null; }

  return { start, end };
}

function localISO(date) {
  const y = date.getFullYear(); const m = String(date.getMonth() + 1).padStart(2, '0'); const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function completeDailyData(rows, period) {
  if (period === 'all') return rows || [];
  const range = getDateRange(period);
  if (!range) return rows || [];
  const map = {};
  (rows || []).forEach(row => { map[row.date] = { income: Number(row.income || 0), expenses: Number(row.expenses || 0) }; });
  const result = [];
  let cursor = new Date(range.start);
  while (cursor < range.end) {
    const key = localISO(cursor);
    result.push({ date: key, income: map[key]?.income || 0, expenses: map[key]?.expenses || 0 });
    cursor.setDate(cursor.getDate() + 1);
  }
  return result;
}

/* =========================================================
   TELEGRAM AUTH DIAGNOSTICS
========================================================= */
function getTelegramInitData() {
  if (!tg) return '';
  const initData = typeof tg.initData === 'string' ? tg.initData : '';
  return initData;
}

/* =========================================================
   LOAD
========================================================= */

async function load() {
  const period = document.getElementById('period').value;
  const refreshButton = document.getElementById('refresh');
  refreshButton.classList.remove('loading');
  refreshButton.disabled = true;

  try {
    const initData = getTelegramInitData();
    if (!initData) throw new Error('Открой приложение через Telegram-бота');

    const res = await fetch(`/api/dashboard?period=${encodeURIComponent(period)}`, {
      headers: { 'X-Telegram-Init-Data': initData },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentData = data;
    render(data, period);
  } catch (err) {
    showError(err);
  } finally {
    refreshButton.classList.remove('loading');
    refreshButton.disabled = false;
  }
}

function showError(err) {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="error">Ошибка при загрузке данных<div class="error-code">${esc(err && err.message ? err.message : String(err))}</div></div>`;
}

function render(data, period) {
  const app = document.getElementById('app');
  // Keep rendering simple: reuse existing DOM structure
  // Build main content

  const balanceClass = (data.net >= 0) ? 'hero-balance positive' : 'hero-balance negative';

  const html = `
  <div class="hero">
    <div class="hero-label">Баланс</div>
    <div class="${balanceClass}">${money(data.net)}</div>
    <div class="hero-period">за ${periodNames[period] || ''}</div>
    <div class="hero-stats">
      <div class="hero-stat">
        <div class="hero-stat-label">Доход</div>
        <div class="hero-stat-value">${money(data.income)}</div>
      </div>
      <div class="hero-stat">
        <div class="hero-stat-label">Расход</div>
        <div class="hero-stat-value">${money(data.expenses)}</div>
      </div>
    </div>
  </div>

  <div class="quick-grid">
    <div class="quick-card">
      <div class="quick-icon">💳</div>
      <div class="quick-label">Транзакций</div>
      <div class="quick-value">${number(data.transactions)}</div>
    </div>
    <div class="quick-card">
      <div class="quick-icon">📈</div>
      <div class="quick-label">Категорий</div>
      <div class="quick-value">${number(data.categories)}</div>
    </div>
    <div class="quick-card">
      <div class="quick-icon">⚖️</div>
      <div class="quick-label">Средний чек</div>
      <div class="quick-value">${money(data.avg_check)}</div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Динамика</h3>
      <div class="card-subtitle">по дням</div>
    </div>
    <div class="chart-wrap" id="dailyChartWrap">
      <canvas id="dailyChartCanvas"></canvas>
    </div>
  </div>

  <div class="two-columns">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">По доходам</h3>
        <div class="card-subtitle">категории</div>
      </div>
      <div class="chart-wrap small" id="incomeChartWrap">
        <canvas id="incomeChartCanvas"></canvas>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">По расходам</h3>
        <div class="card-subtitle">категории</div>
      </div>
      <div class="chart-wrap small" id="expenseChartWrap">
        <canvas id="expenseChartCanvas"></canvas>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Последние транзакции</h3>
      <div class="card-subtitle">за выбранный период</div>
    </div>
    <div class="list">
      ${ (data.recent || []).map(t => {
        const signedAmount = t.kind === 'income' ? t.amount : -t.amount;
        return `
        <div class="row">
          <div class="row-left">
            <div class="row-title">${esc(t.label)}</div>
            <div class="row-sub">${esc(t.note || '')}${t.note ? ' • ' : ''}${dateToShort(t.date)}</div>
          </div>
          <div class="row-right">
            <div class="amount ${signedAmount >= 0 ? 'income' : 'expense'}">${signedAmount >= 0 ? '+' : '−'}${money(Math.abs(signedAmount))}</div>
          </div>
        </div>
      `; }).join('') || '<div class="empty">За этот период операций пока нет.</div>' }
    </div>
  </div>
  `;

  app.innerHTML = html;

  // Render charts
  try {
    destroyCharts();

    const daily = completeDailyData(data.daily || [], period);
    const labels = daily.map(r => dateToLabel(r.date));
    const incomes = daily.map(r => r.income);
    const expenses = daily.map(r => r.expenses);

    const ctx = document.getElementById('dailyChartCanvas').getContext('2d');
    dailyChart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: [{ label: 'Доход', data: incomes, borderColor: 'rgba(53,199,89,0.9)', backgroundColor: 'rgba(53,199,89,0.08)' }, { label: 'Расход', data: expenses, borderColor: 'rgba(255,69,58,0.9)', backgroundColor: 'rgba(255,69,58,0.06)' }] },
      options: { responsive: true, maintainAspectRatio: false }
    });

    // Pie charts for income/expense categories
    const incomeCtx = document.getElementById('incomeChartCanvas').getContext('2d');
    incomeChart = new Chart(incomeCtx, { type: 'doughnut', data: { labels: (data.income_by_source || []).map(c => c.label), datasets: [{ data: (data.income_by_source || []).map(c => c.value), backgroundColor: ['#0a84ff','#35c759','#ff9f0a','#7c5cff'] }] }, options: { responsive: true, maintainAspectRatio: false } });

    const expenseCtx = document.getElementById('expenseChartCanvas').getContext('2d');
    expenseChart = new Chart(expenseCtx, { type: 'doughnut', data: { labels: (data.expenses_by_category || []).map(c => c.label), datasets: [{ data: (data.expenses_by_category || []).map(c => c.value), backgroundColor: ['#ff453a','#ff9f0a','#7c5cff','#0a84ff'] }] }, options: { responsive: true, maintainAspectRatio: false } });

  } catch (err) {
    console.error('Chart render error', err);
  }
}

// Attach handlers
window.addEventListener('load', () => {
  const refreshButton = document.getElementById('refresh');
  refreshButton.addEventListener('click', () => { refreshButton.classList.add('loading'); load(); });
  document.getElementById('period').addEventListener('change', load);
  load();
});
