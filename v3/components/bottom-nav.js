/* Financebot 3.0 - Premium Bottom Navigation */

const FinancebotBottomNav = {
  items: [
    {
      id: 'home',
      label: 'Главная',
      icon: `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 10.5L12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-9.5Z"/>
        </svg>
      `,
    },
    {
      id: 'operations',
      label: 'Операции',
      icon: `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 4v13"/>
          <path d="M4 14l3 3 3-3"/>
          <path d="M17 20V7"/>
          <path d="M14 10l3-3 3 3"/>
        </svg>
      `,
    },
    {
      id: 'budget',
      label: 'Бюджет',
      icon: `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="4" y="4" width="16" height="16" rx="3"/>
          <path d="M8 8h8"/>
          <path d="M8 12h8"/>
          <path d="M8 16h5"/>
        </svg>
      `,
    },
    {
      id: 'goals',
      label: 'Цели',
      icon: `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8"/>
          <circle cx="12" cy="12" r="4"/>
          <circle cx="12" cy="12" r="1.5"/>
        </svg>
      `,
    },
    {
      id: 'profile',
      label: 'Профиль',
      icon: `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="8" r="3"/>
          <path d="M5 20c.8-3.5 3.1-5.5 7-5.5s6.2 2 7 5.5"/>
        </svg>
      `,
    },
  ],

  render(container) {
    if (!container) {
      console.warn('FinancebotBottomNav: container not found');
      return;
    }

    container.innerHTML = '';

    const nav = document.createElement('nav');

    nav.className = 'bottom-nav';
    nav.setAttribute('aria-label', 'Основная навигация');

    this.items.forEach((item) => {
      const button = document.createElement('button');

      button.type = 'button';
      button.className = 'nav-item';
      button.dataset.page = item.id;
      button.setAttribute('aria-label', item.label);

      button.innerHTML = `
        <span class="nav-icon" aria-hidden="true">
          ${item.icon}
        </span>

        <span class="nav-label">
          ${item.label}
        </span>
      `;

      button.addEventListener('click', () => {
        if (window.FinancebotRouter) {
          window.FinancebotRouter.navigate(item.id);
        }
      });

      nav.appendChild(button);
    });

    container.appendChild(nav);

    this.updateActive();
  },

  updateActive() {
    const currentPage =
      window.FinancebotRouter?.getCurrentPage() || 'home';

    document
      .querySelectorAll('.nav-item')
      .forEach((button) => {
        const isActive =
          button.dataset.page === currentPage;

        button.classList.toggle(
          'active',
          isActive
        );

        button.setAttribute(
          'aria-current',
          isActive ? 'page' : 'false'
        );
      });
  },
};

window.FinancebotBottomNav = FinancebotBottomNav;
