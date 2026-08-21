/* Financebot 3.0 - Loading State */

const FinancebotLoading = {
  render({
    label = 'Загрузка...',
    inline = false,
  } = {}) {
    const container = document.createElement('div');

    container.className = inline
      ? 'loading loading--inline'
      : 'loading';

    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');

    container.innerHTML = `
      <span class="loading__spinner" aria-hidden="true"></span>

      <span class="loading__label">
        ${this.escape(label)}
      </span>
    `;

    return container;
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

window.FinancebotLoading = FinancebotLoading;
