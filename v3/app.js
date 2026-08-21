/* Financebot 3.0 - Application */

const FinancebotApp = {
  version: '3.0',

  initialized: false,

  init() {
    if (this.initialized) {
      return;
    }

    this.initialized = true;

    this.initTelegram();
    this.initRouter();
    this.bindState();
    this.render();
  },

  initTelegram() {
    if (window.FinancebotTelegram) {
      window.FinancebotTelegram.init();
    }
  },

  initRouter() {
    if (window.FinancebotRouter) {
      window.FinancebotRouter.init();
    }
  },

  bindState() {
    if (!window.FinancebotState) {
      return;
    }

    window.FinancebotState.subscribe(() => {
      this.render();
    });
  },

  render() {
    const app = document.querySelector('#app');

    if (!app) {
      console.error(
        'Financebot 3.0: #app container not found'
      );

      return;
    }

    const page =
      window.FinancebotRouter?.getCurrentPage() ||
      'home';

    app.innerHTML = '';

    const shell = document.createElement('div');

    shell.className = 'app-shell';

    const content = document.createElement('div');

    content.className = 'app-content';

    shell.appendChild(content);

    const bottomNav = document.createElement('div');

    bottomNav.className = 'app-bottom-nav';

    shell.appendChild(bottomNav);

    app.appendChild(shell);

    this.renderPage(
      content,
      page
    );

    if (window.FinancebotBottomNav) {
      window.FinancebotBottomNav.render(
        bottomNav
      );
    }
  },

  async renderPage(
    container,
    page
  ) {
    switch (page) {
      case 'home':
        if (window.FinancebotHomePage) {
          await window.FinancebotHomePage.render(
            container
          );
        }
        break;

      case 'operations':
      case 'analytics':
      case 'accounts':
      case 'profile':
      case 'add-operation':
      case 'operation-details':
      case 'budget':
      case 'goals':
      case 'categories':
        this.renderPlaceholder(
          container,
          page
        );
        break;

      default:
        window.FinancebotRouter?.navigate(
          'home',
          {
            replaceHistory: true,
          }
        );
        break;
    }
  },

  renderPlaceholder(
    container,
    page
  ) {
    const labels = {
      operations: 'Операции',
      analytics: 'Аналитика',
      accounts: 'Счета',
      profile: 'Профиль',
      'add-operation': 'Добавить операцию',
      'operation-details': 'Операция',
      budget: 'Бюджет',
      goals: 'Цели',
      categories: 'Категории',
    };

    const title =
      labels[page] || 'Раздел';

    container.innerHTML = `
      <main class="page placeholder-page">
        <header class="page-header">
          <div>
            <h1 class="page-title">
              ${this.escape(title)}
            </h1>

            <div class="page-subtitle">
              Этот раздел появится позже
            </div>
          </div>
        </header>

        <section class="card card-padding">
          <div class="placeholder-content">
            <div class="placeholder-icon">
              •
            </div>

            <h2 class="placeholder-title">
              В разработке
            </h2>

            <p class="placeholder-text">
              Мы постепенно собираем
              Financebot 3.0.
            </p>
          </div>
        </section>
      </main>
    `;
  },

  escape(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },
};

window.FinancebotApp = FinancebotApp;

document.addEventListener(
  'DOMContentLoaded',
  () => {
    FinancebotApp.init();
  }
);
