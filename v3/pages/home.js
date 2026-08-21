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
    const income = Number(
      dashboard?.income || 0
    );

    const expenses = Number(
      dashboard?.expenses || 0
    );

    const net = Number(
      dashboard?.net || 0
    );

    const transactions = Number(
      dashboard?.transactions || 0
    );

    const categories = Number(
      dashboard?.categories || 0
    );

    const avgCheck = Number(
      dashboard?.avg_check || 0
    );

    const recent =
      Array.isArray(dashboard?.recent)
        ? dashboard.recent
        : [];

    page.innerHTML = `
      <header class="page-header home-header">
        <div class="home-header__content">
          <div class="home-header__eyebrow">
            FINANCEBOT
          </div>

          <h1 class="page-title">
            Финансы
          </h1>

          <div class="page-subtitle">
            Обзор за ${this.getPeriodLabel()}
          </div>
        </div>

        <button
          type="button"
          class="home-header__profile"
          data-action="profile"
          aria-label="Профиль"
        >
          <span>•</span>
        </button>
      </header>

      <section class="card capital-card home-balance-card">
        <div class="capital-label">
          Баланс
        </div>

        <div class="capital-value">
          ${this.formatMoney(net)}
          <span class="capital-currency">
            PLN
          </span>
        </div>

        <div class="capital-change">
          ${
            net >= 0
              ? 'Ваш баланс в плюсе'
              : 'Расходы превышают доходы'
          }
        </div>

        <div class="home-balance-card__decor">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </section>

      <section class="stats-grid home-stats">
        <div
          id="home-income"
          class="card stat-card"
        ></div>

        <div
          id="home-expenses"
          class="card stat-card"
        ></div>

        <div
          id="home-transactions"
          class="card stat-card"
        ></div>
      </section>

      <section class="section home-overview-section">
        <div class="section-header">
          <h2 class="section-title">
            Обзор
          </h2>

          <button
            type="button"
            class="section-action"
            data-action="analytics"
          >
            Подробнее
          </button>
        </div>

        <div class="card home-overview-card">
          <div class="home-overview-row">
            <div>
              <div class="home-overview-label">
                Средний чек
              </div>

              <div class="home-overview-value">
                ${this.formatMoney(avgCheck)}
                <span>PLN</span>
              </div>
            </div>

            <div class="home-overview-icon">
              ≈
            </div>
          </div>

          <div class="home-overview-divider"></div>

          <div class="home-overview-row">
            <div>
              <div class="home-overview-label">
                Категории расходов
              </div>

              <div class="home-overview-value">
                ${categories}
              </div>
            </div>

            <div class="home-overview-icon">
              #
            </div>
          </div>
        </div>
      </section>

      <section class="section home-transactions-section">
        <div class="section-header">
          <h2 class="section-title">
            Последние операции
          </h2>

          <button
            type="button"
            class="section-action"
            data-action="operations"
          >
            Все
          </button>
        </div>

        <div class="card card-padding">
          <div
            id="home-transactions-list"
            class="transaction-list"
          ></div>
        </div>
      </section>

      <button
        type="button"
        class="fab"
        data-action="add"
        aria-label="Добавить операцию"
      >
        +
      </button>
    `;

    this.renderStatCards(
      page,
      income,
      expenses,
      transactions
    );

    this.renderRecentTransactions(
      page,
      recent
    );

    this.bindActions(page);
  },

  renderStatCards(
    page,
    income,
    expenses,
    transactions
  ) {
    const incomeContainer =
      page.querySelector(
        '#home-income'
      );

    const expensesContainer =
      page.querySelector(
        '#home-expenses'
      );

    const transactionsContainer =
      page.querySelector(
        '#home-transactions'
      );

    if (
      !incomeContainer ||
      !expensesContainer ||
      !transactionsContainer
    ) {
      return;
    }

    if (!window.FinancebotStatCard) {
      return;
    }

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

    transactionsContainer.appendChild(
      window.FinancebotStatCard.render({
        label: 'Операции',
        value: transactions,
        suffix: '',
        type: 'default',
        icon: '•',
      })
    );
  },

  renderRecentTransactions(
    page,
    transactions
  ) {
    const list =
      page.querySelector(
        '#home-transactions-list'
      );

    if (!list) return;

    list.innerHTML = '';

    if (!transactions.length) {
      if (window.FinancebotEmptyState) {
        list.appendChild(
          window.FinancebotEmptyState.render({
            title: 'Операций пока нет',

            description:
              'Добавьте первую операцию, чтобы начать вести учёт.',

            actionLabel:
              'Добавить операцию',

            action: () => {
              window.FinancebotRouter?.navigate(
                'add-operation'
              );
            },
          })
        );
      }

      return;
    }

    transactions
      .slice(0, 5)
      .forEach((transaction) => {
        if (
          window.FinancebotTransactionRow
        ) {
          list.appendChild(
            window.FinancebotTransactionRow.render(
              transaction
            )
          );
        }
      });
  },

  renderError(page) {
    page.innerHTML = '';

    if (!window.FinancebotError) {
      return;
    }

    page.appendChild(
      window.FinancebotError.render({
        title:
          'Не удалось загрузить финансы',

        description:
          'Проверьте соединение с Telegram и попробуйте ещё раз.',

        actionLabel:
          'Повторить',

        action: () => {
          this.render(page);
        },
      })
    );
  },

  bindActions(page) {
    const actions = {
      add: 'add-operation',
      operations: 'operations',
      analytics: 'analytics',
      profile: 'profile',
    };

    Object.entries(actions).forEach(
      ([action, route]) => {
        const elements =
          page.querySelectorAll(
            `[data-action="${action}"]`
          );

        elements.forEach((element) => {
          element.addEventListener(
            'click',
            () => {
              window.FinancebotRouter?.navigate(
                route
              );
            }
          );
        });
      }
    );
  },

  getPeriodLabel() {
    const period =
      window.FinancebotState
        ?.getState()
        .period || 'month';

    const labels = {
      day: 'сегодня',
      week: 'эту неделю',
      month: 'этот месяц',
      year: 'этот год',
      all: 'всё время',
    };

    return labels[period] || 'этот месяц';
  },

  formatMoney(value) {
    return new Intl.NumberFormat(
      'pl-PL',
      {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }
    ).format(
      Number(value) || 0
    );
  },
};

window.FinancebotHomePage =
  FinancebotHomePage;
