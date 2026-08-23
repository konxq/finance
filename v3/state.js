/* Financebot 3.0 application state */

const AppState = {
  data: {
    currentPage: 'home',
    previousPage: null,
    period: 'month',
    dashboard: null,
    loading: false,
    error: null,
  },

  listeners: new Set(),

  getState() {
    return { ...this.data };
  },

  setState(patch) {
    this.data = {
      ...this.data,
      ...patch,
    };

    this.listeners.forEach((listener) => {
      listener(this.getState());
    });
  },

  subscribe(listener) {
    this.listeners.add(listener);

    return () => {
      this.listeners.delete(listener);
    };
  },
};

window.FinancebotState = AppState;
