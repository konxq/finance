/* Financebot 3.0 - Transaction Row */

const FinancebotTransactionRow = {
  render(transaction = {}) {
    const {
      date = '',
      label = 'Операция',
      amount = 0,
      note = '',
      kind = 'expense',
      category = '',
    } = transaction;

    const isIncome = kind === 'income';

    const amountValue = Number(amount) || 0;
    const amountText = `${isIncome ? '+' : '−'}${this.formatMoney(amountValue)}`;

    const icon = isIncome ? '↗' : '↘';
    const amountClass = isIncome
      ? 'transaction__amount--income'
      : 'transaction__amount--expense';

    const subtitle = category || note || this.formatDate(date);

    const row = document.createElement('button');

    row.type = 'button';
    row.className = 'transaction';
    row.dataset.kind = kind;

    row.innerHTML = `
      <span class="transaction__icon transaction__icon--${kind}">
        ${icon}
      </span>

      <span class="transaction__content">
        <span class="transaction__title">
          ${this.escape(label)}
        </span>

        <span class="transaction__meta">
          ${this.escape(subtitle)}
        </span>
      </span>

      <span class="transaction__right">
        <span class="transaction__amount ${amountClass}">
          ${amountText}
        </span>

        <span class="transaction__date">
          ${this.escape(this.formatDate(date))}
        </span>
      </span>
    `;

    row.addEventListener('click', () => {
      if (!window.FinancebotRouter) {
        return;
      }

      if (transaction.id) {
        window.FinancebotState?.setState({
          selectedOperation: transaction,
        });

        window.FinancebotRouter.navigate('operation-details');
      }
    });

    return row;
  },

  formatMoney(value) {
    return new Intl.NumberFormat('pl-PL', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(value));
  },

  formatDate(date) {
    if (!date) {
      return '';
    }

    const parsed = new Date(date);

    if (Number.isNaN(parsed.getTime())) {
      return date;
    }

    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: 'short',
    }).format(parsed);
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

window.FinancebotTransactionRow = FinancebotTransactionRow;
