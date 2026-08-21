/* Financebot 3.0 - Bottom Navigation */

const FinancebotBottomNav = {
  items: [
    {
      id: 'home',
      label: 'Главная',
      icon: '⌂',
    },
    {
      id: 'operations',
      label: 'Операции',
      icon: '↕',
    },
    {
      id: 'budget',
      label: 'Бюджет',
      icon: '▣',
    },
    {
      id: 'goals',
      label: 'Цели',
      icon: '◎',
    },
    {
      id: 'profile',
      label: 'Профиль',
      icon: '○',
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
        const isActive = button.dataset.page === currentPage;

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
