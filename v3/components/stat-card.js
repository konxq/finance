/* Financebot 3.0 - Stat Card */

const FinancebotStatCard = {
  render({
    label = '',
    value = 0,
    suffix = 'PLN',
    icon = '',
    type = 'default',
    change = null,
  } = {}) {
    const card = document.createElement('div');

    card.className = `stat-card stat-card--${type}`;

    const formattedValue = this.formatMoney(value);

    let changeMarkup = '';

    if (change !== null && change !== undefined) {
      const numericChange = Number(change) || 0;
      const changeClass =
        numericChange >= 0
          ? 'stat-card__change--positive'
          : 'stat-card__change--negative';

      const sign = numericChange >= 0 ? '+' : '';

      changeMarkup = `
        <span class="stat-card__change ${changeClass}">
          ${sign}${numericChange.toFixed(1)}%
        </span>
      `;
    }

    card.innerHTML = `
      <div class="stat-card__top">
        <span class="stat-card__label">
          ${this.escape(label)}
        </span>

        ${
          icon
            ? `<span class="stat-card__icon">${this.escape(icon)}</span>`
            : ''
        }
      </div>

      <div class="stat-card__value">
        <span>${formattedValue}</span>
        ${
          suffix
            ? `<small>${this.escape(suffix)}</small>`
            : ''
        }
      </div>

      ${
        changeMarkup
          ? `<div class="stat-card__footer">${changeMarkup}</div>`
          : ''
      }
    `;

    return card;
  },

  formatMoney(value) {
    return new Intl.NumberFormat('pl-PL', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(Number(value) || 0));
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

window.FinancebotStatCard = FinancebotStatCard;
