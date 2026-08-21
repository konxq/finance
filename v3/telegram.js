/* Financebot 3.0 Telegram integration */

const Telegram = {
  webApp: window.Telegram?.WebApp || null,

  init() {
    if (!this.webApp) {
      console.warn('Telegram WebApp SDK not available');
      return;
    }

    try {
      this.webApp.ready();
      this.webApp.expand();
    } catch (error) {
      console.error('Telegram initialization error:', error);
    }
  },

  getInitData() {
    return this.webApp?.initData || '';
  },

  getUser() {
    return this.webApp?.initDataUnsafe?.user || null;
  }
};

Telegram.init();

window.FinancebotTelegram = Telegram;
