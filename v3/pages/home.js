/* Financebot 3.0 - Home Page */

const FinancebotHomePage = {
  async render(container) {
    if (!container) return;

    const state =
      window.FinancebotState?.getState() || {};

    container.innerHTML = '';

    const page = document.createElement('main');
    page.className = 'page home-page';

    container.appendChild(page);

    this.renderLoading(page);

    try {
      const dashboard =
        await window.FinancebotApi.getDashboard(
          state.period || 'month'
        );

      window.FinancebotState?.setState({
        dashboard,
        error: null,
      });

      this.renderDashboard(page, dashboard);
    } catch (error) {
      console.error(
        'Financebot Home: dashboard loading failed',
        error
      );

      window.FinancebotState?.setState({
        error:
          error?.message ||
          'Не удалось загрузить данные',
      });

      this.renderError(page);
    }
  },

  renderLoading(page) {
    page.innerHTML = '';

    if (window.FinancebotLoading) {
      page.appendChild(
        window.FinancebotLoading.render({
          label: 'Загружаем финансы...',
        })
      );

      return;
    }

    page.innerHTML = `
      <div class="loading">
        <span class="loading__spinner"></span>
        <span class="loading__label">
          Загружаем финансы...
        </span>
      </div>
    `;
  },

  renderDashboard(page, dashboard) {
    const income = Number(dashboard?.income || 0);
    const expenses = Number(dashboard?.expenses || 0);
    const net = Number(dashboard?.net || 0);
    const transactions = Number(dashboard?.transactions || 0);

    const recent = Array.isArray(dashboard?.recent) ? dashboard.recent : [];

    page.innerHTML = `
      <header class="page-header home-header">
        <div class="home-header__content">
          <div class="home-header__eyebrow">FINANCEBOT</div>

          <h1 class="page-title">Финансы</h1>

          <div class="page-subtitle">Обзор за ${this.getPeriodLabel()}</div>
        </div>

        <button type="button" class="home-header__profile" data-action="profile" aria-label="Профиль">
          <span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="8" r="3"></circle>
              <path d="M5 20c.8-3.5 3.1-5.5 7-5.5s6.2 2 7 5.5"></path>
            </svg>
          </span>
        </button>
      </header>

      <section class="card capital-card home-balance-card">
        <div class="capital-label">Баланс</div>
        <div class="capital-value">${this.formatMoney(net)} <span class="capital-currency">PLN</span></div>
        <div class="capital-change">${net >= 0 ? 'Ваш баланс в плюсе' : 'Расходы превышают доходы'}</div>
        <div class="home-balance-card__decor"><span></span><span></span><span></span></div>
      </section>

      <section class="stats-grid home-stats">
        <div id="home-income" class="card stat-card"></div>
        <div id="home-expenses" class="card stat-card"></div>
      </section>

      <section class="section home-dynamics-section">
        <div class="section-header">
          <h2 class="section-title">Динамика</h2>
          <div class="chart-toggle" role="tablist" aria-label="Переключатель доходы расходы">
            <button id="toggle-income" class="toggle-btn" role="tab" aria-selected="false">Доходы</button>
            <button id="toggle-expense" class="toggle-btn active" role="tab" aria-selected="true">Расходы</button>
          </div>
        </div>

        <div class="card chart-card card-padding">
          <div id="chart-container" class="chart-container">
            <canvas id="dynamics-canvas" class="chart-canvas"></canvas>
          </div>
        </div>
      </section>

      <section class="section home-transactions-section">
        <div class="section-header">
          <h2 class="section-title">Последние операции</h2>
          <button type="button" class="section-action" data-action="operations">Все</button>
        </div>

        <div class="card card-padding">
          <div id="home-transactions-list" class="transaction-list"></div>
        </div>
      </section>

      <button type="button" class="fab" data-action="add" aria-label="Добавить операцию">+</button>
    `;

    // render stat cards (only income and expenses)
    this.renderStatCards(page, income, expenses);

    // bind dynamics chart (must exist and use dashboard.daily)
    this.bindDynamicsHandlers(page, dashboard);

    this.renderRecentTransactions(page, recent);

    this.bindActions(page);
  },

  renderStatCards(page, income, expenses) {
    const incomeContainer = page.querySelector('#home-income');
    const expensesContainer = page.querySelector('#home-expenses');

    if (!incomeContainer || !expensesContainer) return;

    if (!window.FinancebotStatCard) return;

    incomeContainer.appendChild(
      window.FinancebotStatCard.render({
        label: 'Доходы',
        value: income,
        suffix: 'PLN',
        type: 'income',
        icon: '↗',
      })
    );

    expensesContainer.appendChild(
      window.FinancebotStatCard.render({
        label: 'Расходы',
        value: expenses,
        suffix: 'PLN',
        type: 'expense',
        icon: '↘',
      })
    );
  },

  renderRecentTransactions(page, transactions) {
    const list = page.querySelector('#home-transactions-list');
    if (!list) return;

    list.innerHTML = '';

    if (!transactions.length) {
      if (window.FinancebotEmptyState) {
        list.appendChild(
          window.FinancebotEmptyState.render({
            title: 'Операций пока нет',
            description: 'Добавьте первую операцию, чтобы начать вести учёт.',
            actionLabel: 'Добавить операцию',
            action: () => { window.FinancebotRouter?.navigate('add-operation'); },
          })
        );
      }
      return;
    }

    transactions.slice(0, 5).forEach((transaction) => {
      if (window.FinancebotTransactionRow) {
        list.appendChild(window.FinancebotTransactionRow.render(transaction));
      }
    });
  },

  // --- Dynamics chart helpers ---
  getMonthRangeDates() {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    return { start, end };
  },

  prepareMonthlyData(daily) {
    const { start, end } = this.getMonthRangeDates();
    const map = {};
    (daily || []).forEach(r => { map[r.date] = { income: Number(r.income || 0), expenses: Number(r.expenses || 0) }; });
    const result = [];
    let cursor = new Date(start);
    while (cursor < end) {
      const y = cursor.getFullYear();
      const m = String(cursor.getMonth() + 1).padStart(2, '0');
      const d = String(cursor.getDate()).padStart(2, '0');
      const key = `${y}-${m}-${d}`;
      result.push({ date: key, income: map[key]?.income || 0, expenses: map[key]?.expenses || 0 });
      cursor.setDate(cursor.getDate() + 1);
    }
    return result;
  },

  renderDynamicsChart(container, daily, mode = 'expenses') {
    const canvas = container.querySelector('#dynamics-canvas');
    if (!canvas) return;

    // ensure CSS controls visual height; make canvas pixel-perfect using DPR
    const rect = container.getBoundingClientRect();
    const width = Math.max(1, rect.width || container.clientWidth || 1);
    const cssHeight = parseInt(getComputedStyle(canvas).height, 10) || 220;
    const DPR = window.devicePixelRatio || 1;

    // set pixel size
    canvas.width = Math.round(width * DPR);
    canvas.height = Math.round(cssHeight * DPR);

    const ctx = canvas.getContext('2d');
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, width, cssHeight);

    // prepare data
    const monthly = this.prepareMonthlyData(daily || []);
    const labels = monthly.map(r => r.date);
    const incomes = monthly.map(r => r.income);
    const expenses = monthly.map(r => r.expenses);
    const values = mode === 'income' ? incomes : expenses;

    // drawing area
    const padding = { left: 36, right: 12, top: 12, bottom: 36 };
    const w = width - padding.left - padding.right;
    const h = cssHeight - padding.top - padding.bottom;

    const maxVal = Math.max(1, ...values);
    const minVal = 0;

    const xFor = i => padding.left + (i / Math.max(1, values.length - 1)) * w;
    const yFor = v => padding.top + h - ((v - minVal) / (maxVal - minVal || 1)) * h;

    // Build points array: exact X for each calendar day, exact Y for each day's value.
const points = values.map((v, i) => ({
  x: xFor(i),
  y: yFor(v),
  v: Number(v) || 0,
  i
}));

const baseY = padding.top + h;

// Segment by consecutive non-zero days.
const segments = [];
let curSeg = [];

for (let i = 0; i < points.length; i++) {
  const p = points[i];

  if (p.v > 0) {
    curSeg.push(p);
  } else {
    if (curSeg.length) {
      segments.push(curSeg);
      curSeg = [];
    }
  }
}

if (curSeg.length) {
  segments.push(curSeg);
}

// Visual parameters
const perDay = w / Math.max(1, values.length);
const bumpRadius = Math.max(
  10,
  Math.min(28, Math.round(perDay * 1.0))
);

const fillColor =
  mode === 'income'
    ? 'rgba(53,169,104,0.12)'
    : 'rgba(239,107,112,0.08)';

const strokeColor =
  mode === 'income'
    ? 'rgba(53,169,104,1)'
    : 'rgba(239,107,112,1)';

ctx.lineWidth = 2;
ctx.lineJoin = 'round';
ctx.lineCap = 'round';

const clamp = (v, a, b) =>
  Math.max(a, Math.min(b, v));

// Draw every segment independently.
for (const seg of segments) {

  // One active day = isolated bump
  if (seg.length === 1) {

    const p = seg[0];
    const x = p.x;
    const y = p.y;
    const r = bumpRadius;

    // Fill bump
    ctx.beginPath();
    ctx.moveTo(x - r, baseY);

    ctx.quadraticCurveTo(
      x - r / 2,
      y + (baseY - y) * 0.6,
      x,
      y
    );

    ctx.quadraticCurveTo(
      x + r / 2,
      y + (baseY - y) * 0.6,
      x + r,
      baseY
    );

    ctx.closePath();

    ctx.fillStyle = fillColor;
    ctx.fill();

    // Stroke bump
    ctx.beginPath();

    ctx.moveTo(
      x - r / 2,
      y + (baseY - y) * 0.6
    );

    ctx.quadraticCurveTo(
      x,
      y,
      x + r / 2,
      y + (baseY - y) * 0.6
    );

    ctx.strokeStyle = strokeColor;
    ctx.stroke();

  } else {

    // Multiple consecutive active days.
    // Catmull-Rom -> cubic Bezier.

    const coords = seg.map(p => ({
      x: p.x,
      y: p.y
    }));

    // Fill
    ctx.beginPath();
    ctx.moveTo(
      coords[0].x,
      coords[0].y
    );

    for (let i = 0; i < coords.length - 1; i++) {

      const p0 =
        i === 0
          ? coords[0]
          : coords[i - 1];

      const p1 = coords[i];
      const p2 = coords[i + 1];

      const p3 =
        i + 2 < coords.length
          ? coords[i + 2]
          : coords[coords.length - 1];

      const cp1x =
        p1.x + (p2.x - p0.x) / 6;

      const cp1y =
        p1.y + (p2.y - p0.y) / 6;

      const cp2x =
        p2.x - (p3.x - p1.x) / 6;

      const cp2y =
        p2.y - (p3.y - p1.y) / 6;

      const ys = [
        p0.y,
        p1.y,
        p2.y,
        p3.y
      ];

      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      const safeCp1y =
        clamp(cp1y, minY, maxY);

      const safeCp2y =
        clamp(cp2y, minY, maxY);

      ctx.bezierCurveTo(
        cp1x,
        safeCp1y,
        cp2x,
        safeCp2y,
        p2.x,
        p2.y
      );
    }

    // Close fill to baseline
    const firstX = coords[0].x;
    const lastX =
      coords[coords.length - 1].x;

    ctx.lineTo(lastX, baseY);
    ctx.lineTo(firstX, baseY);
    ctx.closePath();

    ctx.fillStyle = fillColor;
    ctx.fill();

    // Stroke curve
    ctx.beginPath();

    ctx.moveTo(
      coords[0].x,
      coords[0].y
    );

    for (let i = 0; i < coords.length - 1; i++) {

      const p0 =
        i === 0
          ? coords[0]
          : coords[i - 1];

      const p1 = coords[i];
      const p2 = coords[i + 1];

      const p3 =
        i + 2 < coords.length
          ? coords[i + 2]
          : coords[coords.length - 1];

      const cp1x =
        p1.x + (p2.x - p0.x) / 6;

      const cp1y =
        p1.y + (p2.y - p0.y) / 6;

      const cp2x =
        p2.x - (p3.x - p1.x) / 6;

      const cp2y =
        p2.y - (p3.y - p1.y) / 6;

      const ys = [
        p0.y,
        p1.y,
        p2.y,
        p3.y
      ];

      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      const safeCp1y =
        clamp(cp1y, minY, maxY);

      const safeCp2y =
        clamp(cp2y, minY, maxY);

      ctx.bezierCurveTo(
        cp1x,
        safeCp1y,
        cp2x,
        safeCp2y,
        p2.x,
        p2.y
      );
    }

    ctx.strokeStyle = strokeColor;
    ctx.stroke();
  }
}

    // x-axis labels: approx 7 ticks
    const ticks = Math.min(7, labels.length);
    const step = Math.max(1, Math.ceil(labels.length / ticks));
    ctx.fillStyle = 'rgba(32,37,34,0.6)';
    ctx.font = '12px Inter, system-ui, -apple-system';
    ctx.textAlign = 'center';
    for (let i = 0; i < labels.length; i += step) {
      const date = labels[i];
      const parts = date.split('-');
      const day = String(Number(parts[2]));
      const month = parts[1];
      const label = `${day}.${month}`;
      ctx.fillText(label, xFor(i), padding.top + h + 20);
    }

    // store last render state for redraw on resize
    canvas._last = { daily: daily, mode: mode };
  },

  bindDynamicsHandlers(page, dashboard) {
    const container = page.querySelector('#chart-container');
    if (!container) return;

    const canvas = container.querySelector('#dynamics-canvas');
    if (!canvas) return;

    // ensure CSS height is set if not already
    if (!canvas.style.height) canvas.style.height = '220px';

    const render = (mode) => this.renderDynamicsChart(container, dashboard?.daily || [], mode);

    // initial render with expenses
    render('expenses');

    const btnIncome = page.querySelector('#toggle-income');
    const btnExpense = page.querySelector('#toggle-expense');

    const setActive = (mode) => {
      if (btnIncome) btnIncome.classList.toggle('active', mode === 'income');
      if (btnExpense) btnExpense.classList.toggle('active', mode === 'expenses');
      render(mode);
    };

    btnIncome?.addEventListener('click', () => setActive('income'));
    btnExpense?.addEventListener('click', () => setActive('expenses'));

    // handle resize: debounced
    const resizeHandler = () => {
      const mode = (btnExpense && btnExpense.classList.contains('active')) ? 'expenses' : 'income';
      render(mode);
    };

    let resizeTimer = null;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(resizeHandler, 120); };

    window.addEventListener('resize', onResize);

    // store to allow cleanup if needed
    canvas._resizeListener = onResize;
  },

  renderError(page) {
    page.innerHTML = '';

    if (!window.FinancebotError) {
      return;
    }

    page.appendChild(
      window.FinancebotError.render({
        title: 'Не удалось загрузить финансы',
        description: 'Проверьте соединение с Telegram и попробуйте ещё раз.',
        actionLabel: 'Повторить',
        action: () => { this.render(page); },
      })
    );
  },

  bindActions(page) {
    const actions = { add: 'add-operation', operations: 'operations', analytics: 'analytics', profile: 'profile' };

    Object.entries(actions).forEach(([action, route]) => {
      const elements = page.querySelectorAll(`[data-action="${action}"]`);
      elements.forEach((element) => {
        element.addEventListener('click', () => { window.FinancebotRouter?.navigate(route); });
      });
    });
  },

  getPeriodLabel() {
    const period = window.FinancebotState?.getState().period || 'month';
    const labels = { day: 'сегодня', week: 'эту неделю', month: 'этот месяц', year: 'этот год', all: 'всё время' };
    return labels[period] || 'этот месяц';
  },

  formatMoney(value) {
    return new Intl.NumberFormat('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);
  },
};

window.FinancebotHomePage = FinancebotHomePage;
