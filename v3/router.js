/* Financebot 3.0 frontend router */

const FinancebotRouter = {
  routes: {
    home: 'home',
    operations: 'operations',
    analytics: 'analytics',
    accounts: 'accounts',
    profile: 'profile',

    addOperation: 'add-operation',
    operationDetails: 'operation-details',
    budget: 'budget',
    goals: 'goals',
    categories: 'categories',
  },

  navigate(page, options = {}) {
    if (!this.routes[page] && !Object.values(this.routes).includes(page)) {
      console.warn(`Financebot Router: unknown page "${page}"`);
      return;
    }

    const currentPage =
      window.FinancebotState?.getState().currentPage || 'home';

    if (currentPage !== page) {
      window.FinancebotState?.setState({
        previousPage: currentPage,
        currentPage: page,
      });
    }

    if (options.replaceHistory) {
      window.history.replaceState({ page }, '', `#${page}`);
    } else {
      window.history.pushState({ page }, '', `#${page}`);
    }
  },

  back() {
    const state = window.FinancebotState?.getState();

    if (state?.previousPage) {
      this.navigate(state.previousPage);
      return;
    }

    if (window.Telegram?.WebApp?.BackButton) {
      window.Telegram.WebApp.BackButton.hide();
    }

    this.navigate('home', { replaceHistory: true });
  },

  getCurrentPage() {
    return (
      window.FinancebotState?.getState().currentPage || 'home'
    );
  },

  init() {
    const hash = window.location.hash.replace('#', '');

    const initialPage =
      Object.values(this.routes).includes(hash)
        ? hash
        : 'home';

    window.FinancebotState?.setState({
      currentPage: initialPage,
      previousPage: null,
    });

    window.addEventListener('popstate', (event) => {
      const page =
        event.state?.page ||
        window.location.hash.replace('#', '') ||
        'home';

      window.FinancebotState?.setState({
        currentPage: page,
      });
    });
  },
};

window.FinancebotRouter = FinancebotRouter;
