/* Financebot 3.0 - Error State */

const FinancebotError = {
  render({
    title = 'Что-то пошло не так',
    description = 'Не удалось загрузить данные. Попробуйте ещё раз.',
    actionLabel = 'Повторить',
    action = null,
  } = {}) {
    const container = document.createElement('div');

    container.className = 'error-state';

    container.setAttribute('role', 'alert');

    container.innerHTML = `
      <div class="error-state__icon" aria-hidden="true">
        !
      </div>

      <h3 class="error-state__title">
        ${this.escape(title)}
      </h3>

      <p class="error-state__description">
        ${this.escape(description)}
      </p>

      ${
        actionLabel
          ? `
            <button
              type="button"
              class="secondary-button error-state__action"
            >
              ${this.escape(actionLabel)}
            </button>
          `
          : ''
      }
    `;

    const button = container.querySelector(
      '.error-state__action'
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

window.FinancebotError = FinancebotError;
