/* Data Center — cobrar de nuevo una tarjeta ya guardada */

let currentCard = null;

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : text;
  return div.innerHTML;
}

function money(value) {
  return '$' + Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function errorMessage(data, fallback) {
  const detail = data && data.detail;
  if (!detail) return fallback;
  // FastAPI devuelve una lista de errores cuando falla la validación del body.
  if (Array.isArray(detail)) return detail[0].msg || fallback;
  return detail;
}

/* ---------- Tabla ---------- */

function filterCards() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  document.querySelectorAll('#cardsTable tbody tr[data-search]').forEach((row) => {
    row.style.display = !q || row.dataset.search.includes(q) ? '' : 'none';
  });
}

/* ---------- Recuperar clientes anteriores ---------- */

async function runBackfill() {
  const btn = document.getElementById('backfillBtn');
  const label = document.getElementById('backfillText');
  const alertBox = document.getElementById('backfillAlert');

  btn.disabled = true;
  label.textContent = 'Recovering…';
  alertBox.classList.add('hidden');

  try {
    const res = await fetch('/api/data-center/backfill', { method: 'POST' });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      alertBox.className = 'alert alert-error';
      alertBox.textContent = errorMessage(data, 'Could not recover the history.');
      btn.disabled = false;
      label.textContent = 'Recover past customers';
      return;
    }

    const found = data.updated + data.imported;
    alertBox.className = 'alert alert-success';
    alertBox.textContent = found
      ? `${found} customer card(s) recovered from ${data.scanned} past payments. ` +
        `They are view-only — use "Send link" to let a customer save their card for future charges.`
      : `Nothing new to recover (${data.scanned} past payments already up to date).`;

    if (found) setTimeout(() => location.reload(), 2200);
    else {
      btn.disabled = false;
      label.textContent = 'Recover past customers';
    }
  } catch (err) {
    alertBox.className = 'alert alert-error';
    alertBox.textContent = 'Connection error. Please try again.';
    btn.disabled = false;
    label.textContent = 'Recover past customers';
  }
}

/* ---------- Modal de cobro ---------- */

function cardSummary(card) {
  return `
    <div class="charge-target-card">
      <i class="fas fa-credit-card"></i>
      <div>
        <strong>${escapeHtml(card.name)}</strong>
        <span>${escapeHtml(card.brand)} •••• ${escapeHtml(card.last4)}</span>
      </div>
    </div>`;
}

function openChargeModal(btn) {
  currentCard = {
    id: btn.dataset.id,
    name: btn.dataset.name,
    brand: btn.dataset.brand,
    last4: btn.dataset.last4,
  };

  document.getElementById('chargePaymentId').value = currentCard.id;
  document.getElementById('chargeTarget').innerHTML = cardSummary(currentCard);
  document.getElementById('chargeAmount').value = '';
  document.getElementById('chargeDescription').value = btn.dataset.description || '';
  document.getElementById('chargeAgent').value = btn.dataset.agent || '';
  document.getElementById('chargeErrAmount').textContent = '';
  document.getElementById('chargeAlert').classList.add('hidden');
  setSubmitting(false);

  document.getElementById('chargeModal').classList.remove('hidden');
  document.getElementById('chargeAmount').focus();
}

function closeChargeModal() {
  document.getElementById('chargeModal').classList.add('hidden');
}

function setAmount(value) {
  document.getElementById('chargeAmount').value = value.toFixed(2);
  document.getElementById('chargeErrAmount').textContent = '';
}

function setSubmitting(isSubmitting) {
  const btn = document.getElementById('chargeSubmit');
  const label = document.getElementById('chargeSubmitText');
  btn.disabled = isSubmitting;
  label.textContent = isSubmitting ? 'Processing…' : 'Charge card';
}

function showChargeAlert(type, message) {
  const box = document.getElementById('chargeAlert');
  box.className = `alert alert-${type}`;
  box.textContent = message;
}

document.getElementById('chargeForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const amount = parseFloat(document.getElementById('chargeAmount').value);
  const errEl = document.getElementById('chargeErrAmount');

  if (!amount || amount <= 0) {
    errEl.textContent = 'Enter an amount greater than $0.';
    return;
  }
  if (amount > 50000) {
    errEl.textContent = 'Amount cannot exceed $50,000.';
    return;
  }
  errEl.textContent = '';

  const confirmed = confirm(
    `Charge ${money(amount)} to the card ending in ${currentCard.last4} (${currentCard.name})?`
  );
  if (!confirmed) return;

  setSubmitting(true);
  document.getElementById('chargeAlert').classList.add('hidden');

  try {
    const res = await fetch(`/api/data-center/${currentCard.id}/charge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount: amount,
        description: document.getElementById('chargeDescription').value.trim() || null,
        agent_name: document.getElementById('chargeAgent').value.trim() || null,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (res.ok) {
      showChargeAlert('success', `${money(amount)} charged successfully.`);
      setTimeout(() => location.reload(), 1600);
    } else {
      showChargeAlert('error', errorMessage(data, 'The charge could not be processed.'));
      setSubmitting(false);
    }
  } catch (err) {
    showChargeAlert('error', 'Connection error. Please try again.');
    setSubmitting(false);
  }
});

/* ---------- Modal de historial ---------- */

async function openHistoryModal(btn) {
  const modal = document.getElementById('historyModal');
  const body = document.getElementById('historyBody');

  document.getElementById('historyTarget').innerHTML = '';
  body.innerHTML = '<p class="history-empty">Loading…</p>';
  modal.classList.remove('hidden');

  try {
    const res = await fetch(`/api/data-center/${btn.dataset.id}/charges`);
    if (!res.ok) throw new Error('request failed');
    const data = await res.json();

    document.getElementById('historyTarget').innerHTML = cardSummary({
      name: data.customer_name,
      brand: 'Card',
      last4: data.card_last4 || '····',
    });

    if (!data.charges.length) {
      body.innerHTML = '<p class="history-empty">No repeat charges for this card yet.</p>';
      return;
    }

    body.innerHTML = data.charges.map(renderCharge).join('');
  } catch (err) {
    body.innerHTML = '<p class="history-empty">Could not load the history.</p>';
  }
}

function renderCharge(charge) {
  const date = new Date(charge.created_at + 'Z');
  const note = charge.failure_message
    ? `<div class="history-note">${escapeHtml(charge.failure_message)}</div>`
    : '';

  return `
    <div class="history-item">
      <div class="history-main">
        <span class="history-amount">${money(charge.amount)}</span>
        <span class="badge badge-${charge.status.toLowerCase()}">${charge.status.replace('_', ' ')}</span>
      </div>
      <div class="history-meta">
        ${date.toLocaleString('en-US')} · ${escapeHtml(charge.agent_name || 'Agent')}
      </div>
      <div class="history-desc">${escapeHtml(charge.description || '')}</div>
      ${note}
    </div>`;
}

function closeHistoryModal() {
  document.getElementById('historyModal').classList.add('hidden');
}

/* ---------- Atajos ---------- */

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeChargeModal();
    closeHistoryModal();
  }
});

document.querySelectorAll('.modal-overlay').forEach((overlay) => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.add('hidden');
  });
});
