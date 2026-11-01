/* Create payment form — only amount + expiry are shown.
   Customer details (name/email/phone/agent) travel in hidden fields and are
   prefilled when the link is created from the Data Center. */

(function () {
  const form = document.getElementById('paymentForm');
  const nameEl = document.getElementById('customer_name');
  const emailEl = document.getElementById('customer_email');
  const phoneEl = document.getElementById('phone_number');
  const agentEl = document.getElementById('agent_name');
  const amountEl = document.getElementById('amount');
  const expiresEl = document.getElementById('expires_in_minutes');
  const alertBox = document.getElementById('alert-box');
  const customerHint = document.getElementById('customerHint');
  const submitBtn = document.getElementById('submitBtn');

  let lastPaymentUrl = '';

  // Datos precargados desde el Data Center: viajan ocultos, el agente solo
  // escribe el monto. Se muestra un aviso para que sepa a quién va el link.
  (function prefillFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const map = { name: nameEl, email: emailEl, phone: phoneEl, agent: agentEl };
    Object.entries(map).forEach(([param, el]) => {
      const value = params.get(param);
      if (value && el) el.value = value;
    });

    const name = params.get('name');
    if (name) {
      customerHint.className = 'alert alert-success';
      customerHint.textContent =
        `Customer loaded from Data Center: ${name}. Set the amount — once they pay, their card is saved for future charges.`;
    }
  })();

  function setError(id, msg) {
    const el = document.getElementById(id);
    if (el) el.textContent = msg;
    const input = form.querySelector(`[name="${id.replace('err-', '')}"]`);
    if (input) input.classList.toggle('error', !!msg);
  }

  function validate() {
    let valid = true;

    const amt = parseFloat(amountEl.value);
    if (!amt || amt <= 0) { setError('err-amount', 'Amount must be greater than $0'); valid = false; }
    else setError('err-amount', '');

    if (!expiresEl.value) { setError('err-expires', 'Select an expiry time'); valid = false; }
    else setError('err-expires', '');

    return valid;
  }

  function showAlert(type, msg) {
    alertBox.className = `alert alert-${type}`;
    alertBox.textContent = msg;
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    submitBtn.querySelector('span').textContent = loading ? 'Generating…' : 'Generate Link';
    submitBtn.querySelector('i').className = loading ? 'fas fa-spinner fa-spin' : 'fas fa-link';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    alertBox.className = 'alert hidden';

    const payload = {
      customer_name: nameEl.value.trim() || undefined,
      customer_email: emailEl.value.trim() || null,
      phone_number: phoneEl.value.trim() || null,
      amount: parseFloat(amountEl.value),
      expires_in_minutes: parseInt(expiresEl.value),
      agent_name: agentEl.value.trim() || undefined,
    };

    try {
      const res = await fetch('/api/payments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (res.ok && data.success) {
        lastPaymentUrl = data.payment_url;
        document.getElementById('modal-url').textContent = data.payment_url;
        document.getElementById('successModal').classList.remove('hidden');
      } else {
        const detail = data.detail || JSON.stringify(data);
        showAlert('error', `Error: ${detail}`);
      }
    } catch (err) {
      showAlert('error', 'Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  });

  window.copyLink = function () {
    navigator.clipboard.writeText(lastPaymentUrl).then(() => {
      const btn = document.querySelector('.modal-actions .btn-outline');
      btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
      setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i> Copy Link'; }, 2000);
    });
  };

  window.resetForm = function () {
    document.getElementById('successModal').classList.add('hidden');
    amountEl.value = '';
    amountEl.focus();
  };
})();
