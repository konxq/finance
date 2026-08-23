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
  const statusText = (data.net >= 0) ? 'Ваш баланс в плюсе' : 'Ваш баланс в минусе';

  const html = `
  <div class="hero">
    <div class="hero-label">Баланс</div>
    <div class="${balanceClass}">${money(data.net)}</div>
    <div class="hero-status">${esc(statusText)}</div>
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

  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Динамика</h3>
      <div class="chart-toggle" role="tablist" aria-label="Переключатель доходы расходы">
        <button id="toggle-income" class="toggle-btn" role="tab" aria-selected="false">Доходы</button>
        <button id="toggle-expense" class="toggle-btn active" role="tab" aria-selected="true">Расходы</button>
      </div>
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
    // Do not destroy income/expense pies here; we'll manage dailyChart separately
    if (dailyChart) { dailyChart.destroy(); dailyChart = null; }

    // Use existing helper to prepare month data (chart should show current month)
    const monthly = completeDailyData(data.daily || [], 'month');
    const labels = monthly.map(r => dateToLabel(r.date));
    const incomes = monthly.map(r => r.income);
    const expenses = monthly.map(r => r.expenses);

    // Create daily chart with toggle between income/expenses
    function createDailyChart(mode) {
      if (dailyChart) { dailyChart.destroy(); dailyChart = null; }
      const values = (mode === 'income') ? incomes : expenses;
      const isIncome = mode === 'income';
      const color = isIncome ? 'rgba(53,199,89,0.95)' : 'rgba(255,69,58,0.95)';
      const bg = isIncome ? 'rgba(53,199,89,0.12)' : 'rgba(255,69,58,0.08)';

      const ctx = document.getElementById('dailyChartCanvas').getContext('2d');
      dailyChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: isIncome ? 'Доход' : 'Расход',
            data: values,
            borderColor: color,
            backgroundColor: bg,
            fill: 'start',
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 6,
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid: { display: false },
              ticks: { autoSkip: true, maxTicksLimit: 7 }
            },
            y: {
              grid: { color: 'rgba(8,15,26,0.05)' },
              beginAtZero: true
            }
          },
          interaction: { intersect: false, mode: 'index' },
          elements: { point: { hoverRadius: 6 } }
        }
      });
    }

    // Default to expenses per requirement
    createDailyChart('expenses');

    // Setup toggle handlers
    const btnIncome = document.getElementById('toggle-income');
    const btnExpense = document.getElementById('toggle-expense');
    function setActive(mode) {
      if (!btnIncome || !btnExpense) return;
      btnIncome.classList.toggle('active', mode === 'income');
      btnIncome.setAttribute('aria-selected', mode === 'income' ? 'true' : 'false');
      btnExpense.classList.toggle('active', mode === 'expenses');
      btnExpense.setAttribute('aria-selected', mode === 'expenses' ? 'true' : 'false');
      createDailyChart(mode);
    }
    btnIncome?.addEventListener('click', () => setActive('income'));
    btnExpense?.addEventListener('click', () => setActive('expenses'));

    // Pie charts for income/expense categories (existing)
    const incomeCtx = document.getElementById('incomeChartCanvas').getContext('2d');
    incomeChart = new Chart(incomeCtx, { type: 'doughnut', data: { labels: (data.income_by_source || []).map(c => c.label), datasets: [{ data: (data.income_by_source || []).map(c => c.value), backgroundColor: (data.income_by_source || []).map((_,i)=>['#35c759','#7ccf8f','#a6f5c9','#bde7d0'][i%4]) }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } } });

    const expenseCtx = document.getElementById('expenseChartCanvas').getContext('2d');
    expenseChart = new Chart(expenseCtx, { type: 'doughnut', data: { labels: (data.expenses_by_category || []).map(c => c.label), datasets: [{ data: (data.expenses_by_category || []).map(c => c.value), backgroundColor: (data.expenses_by_category || []).map((_,i)=>['#ff6b6b','#ff9b9b','#ffc9c9','#ffd6d6'][i%4]) }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } } });

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
