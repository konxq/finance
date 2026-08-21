/* Financebot 3.0 - Frontend Router */

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
    if (
      !Object.values(this.routes).includes(page)
    ) {
      console.warn(
        `Financebot Router: unknown page "${page}"`
      );

      return;
    }

    const currentPage =
      window.FinancebotState
        ?.getState()
        .currentPage || 'home';

    if (currentPage === page) {
      return;
    }

    window.FinancebotState?.setState({
      previousPage: currentPage,
      currentPage: page,
    });

    const method =
      options.replaceHistory
        ? 'replaceState'
        : 'pushState';

    window.history[method](
      { page },
      '',
      `#${page}`
    );

    this.render();
  },

  back() {
    const state =
      window.FinancebotState?.getState();

    if (state?.previousPage) {
      this.navigate(
        state.previousPage
      );

      return;
    }

    this.navigate(
      'home',
      {
        replaceHistory: true,
      }
    );
  },

  getCurrentPage() {
    return (
      window.FinancebotState
        ?.getState()
        .currentPage || 'home'
    );
  },

  render() {
    if (
      window.FinancebotApp &&
      typeof window.FinancebotApp.render ===
        'function'
    ) {
      window.FinancebotApp.render();
    }
  },

  init() {
    const hash =
      window.location.hash.replace(
        '#',
        ''
      );

    const initialPage =
      Object.values(this.routes).includes(
        hash
      )
        ? hash
        : 'home';

    window.FinancebotState?.setState({
      currentPage: initialPage,
      previousPage: null,
    });

    window.addEventListener(
      'popstate',
      (event) => {
        const page =
          event.state?.page ||
          window.location.hash.replace(
            '#',
            ''
          ) ||
          'home';

        if (
          !Object.values(
            this.routes
          ).includes(page)
        ) {
          return;
        }

        window.FinancebotState?.setState({
          currentPage: page,
        });

        this.render();
      }
    );
  },
};

window.FinancebotRouter =
  FinancebotRouter;
