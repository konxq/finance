/* Financebot 3.0 API */

const FinancebotApi = {
  async getDashboard(period = 'month') {
    const initData = window.FinancebotTelegram?.getInitData();

    if (!initData) {
      throw new Error('Открой приложение через Telegram');
    }

    const response = await fetch(
      `/api/dashboard?period=${encodeURIComponent(period)}`,
      {
        headers: {
          'X-Telegram-Init-Data': initData,
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Ошибка API: ${response.status}`);
    }

    return response.json();
  },
};

window.FinancebotApi = FinancebotApi;
