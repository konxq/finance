/* Financebot 3.0 - Empty State */

const FinancebotEmptyState = {
  render({
    title = 'Пока здесь пусто',
    description = 'Добавьте первую операцию, чтобы начать вести учёт финансов.',
    icon = '＋',
    actionLabel = 'Добавить операцию',
    action = null,
  } = {}) {
    const container = document.createElement('div');

    container.className = 'empty-state';

    container.innerHTML = `
      <div class="empty-state__icon" aria-hidden="true">
        ${this.escape(icon)}
      </div>

      <h3 class="empty-state__title">
        ${this.escape(title)}
      </h3>

      <p class="empty-state__description">
        ${this.escape(description)}
      </p>

      ${
        actionLabel
          ? `
            <button
              type="button"
              class="primary-button empty-state__action"
            >
              ${this.escape(actionLabel)}
            </button>
          `
          : ''
      }
    `;

    const button = container.querySelector(
      '.empty-state__action'
    );

    if (button && typeof action === 'function') {
      button.addEventListener('click', action);
    }

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

window.FinancebotEmptyState = FinancebotEmptyState;
