/* Financebot 3.0 - Home Page */

const FinancebotHomePage = {
  async render(container) {
    if (!container) {
      return;
    }

    const state =
      window.FinancebotState?.getState();

    container.innerHTML = '';

    const page = document.createElement('main');

    page.className = 'page home-page';

    container.appendChild(page);

    await this.load(
      page,
      state?.period || 'month'
    );
  },

  async load(page, period = 'month') {
    if (!page) {
      return;
    }

    page.innerHTML = '';

    if (window.FinancebotLoading) {
      page.appendChild(
        window.FinancebotLoading.render({
          label: 'Загружаем финансы...',
        })
      );
    }

    try {
      const dashboard =
        await window.FinancebotApi.getDashboard(
          period
        );

      window.FinancebotState?.setState({
        dashboard,
        error: null,
      });

      this.renderDashboard(
        page,
        dashboard
      );
    } catch (error) {
      console.error(
        'Financebot Home: dashboard loading failed',
        error
      );

      window.FinancebotState?.setState({
        error:
          error.message ||
          'Не удалось загрузить данные',
      });

      this.renderError(page);
    }
  },

  renderDashboard(page, dashboard) {
    const income =
      Number(dashboard?.income || 0);

    const expenses =
      Number(dashboard?.expenses || 0);

    const net =
      Number(dashboard?.net || 0);

    const transactions =
      Number(
        dashboard?.transactions || 0
      );

    page.innerHTML = `
      <header class="page-header">
        <div>
          <h1 class="page-title">
            Главная
          </h1>

          <div class="page-subtitle">
            Финансы за текущий период
          </div>
        </div>
      </header>

      <section class="card capital-card">
        <div class="capital-label">
          Баланс за период
        </div>

        <div class="capital-value">
          ${this.formatMoney(net)}
          <span class="capital-currency">
            PLN
          </span>
        </div>

        <div class="capital-change">
          Доходы − расходы
        </div>
      </section>

      <section class="stats-grid">
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

      <section class="section">
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
    `;

    this.renderStatCards(
      page,
      income,
      expenses,
      transactions
    );

    this.renderRecentTransactions(
      page,
      dashboard?.recent || []
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

    if (!list) {
      return;
    }

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

    transactions.forEach(
      (transaction) => {
        if (
          window.FinancebotTransactionRow
        ) {
          list.appendChild(
            window.FinancebotTransactionRow.render(
              transaction
            )
          );
        }
      }
    );
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
          const period =
            window.FinancebotState
              ?.getState()
              .period || 'month';

          this.load(
            page,
            period
          );
        },
      })
    );
  },

  bindActions(page) {
    const operationsButton =
      page.querySelector(
        '[data-action="operations"]'
      );

    if (!operationsButton) {
      return;
    }

    operationsButton.addEventListener(
      'click',
      () => {
        window.FinancebotRouter?.navigate(
          'operations'
        );
      }
    );
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
