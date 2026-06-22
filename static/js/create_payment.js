/* Create payment form — validation, preview, submit */

(function () {
  const form = document.getElementById('paymentForm');
  const nameEl = document.getElementById('customer_name');
  const emailEl = document.getElementById('customer_email');
  const phoneEl = document.getElementById('phone_number');
  const amountEl = document.getElementById('amount');
  const expiresEl = document.getElementById('expires_in_minutes');
  const descEl = document.getElementById('description');
  const agentEl = document.getElementById('agent_name');
  const alertBox = document.getElementById('alert-box');
  const submitBtn = document.getElementById('submitBtn');

  // Saved payment URL for the success modal
  let lastPaymentUrl = '';

  // Live SMS preview
  function updatePreview() {
    const name = nameEl.value.trim();
    const amount = parseFloat(amountEl.value) || 0;
    const minutes = parseInt(expiresEl.value) || 0;
    document.getElementById('prev-name').textContent = name.split(' ')[0] || 'Customer';
    document.getElementById('prev-amount').textContent = '$' + amount.toFixed(2);
    document.getElementById('prev-expires').textContent = formatExpiry(minutes);
  }

  function formatExpiry(mins) {
    if (!mins) return '—';
    if (mins < 60) return `${mins} minutes`;
    if (mins === 60) return '1 hour';
    if (mins < 1440) return `${mins / 60} hours`;
    return `${mins / 1440} day(s)`;
  }

  [nameEl, amountEl, expiresEl].forEach(el => el.addEventListener('input', updatePreview));
  expiresEl.addEventListener('change', updatePreview);

  // Phone number formatting
  phoneEl.addEventListener('input', () => {
    let digits = phoneEl.value.replace(/\D/g, '');
    if (digits.startsWith('1') && digits.length > 10) digits = digits.slice(1);
    digits = digits.slice(0, 10);
    if (digits.length > 6) {
      phoneEl.value = `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    } else if (digits.length > 3) {
      phoneEl.value = `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    } else if (digits.length > 0) {
      phoneEl.value = `(${digits}`;
    }
  });

  // Validation helpers
  function setError(id, msg) {
    const el = document.getElementById(id);
    if (el) el.textContent = msg;
    const input = form.querySelector(`[name="${id.replace('err-', '')}"]`);
    if (input) input.classList.toggle('error', !!msg);
  }

  function validate() {
    let valid = true;
    if (!nameEl.value.trim()) { setError('err-name', 'Customer name is required'); valid = false; }
    else setError('err-name', '');

    const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRe.test(emailEl.value.trim())) { setError('err-email', 'Enter a valid email address'); valid = false; }
    else setError('err-email', '');

    // El teléfono es opcional; solo se valida si lo escriben
    const digits = phoneEl.value.replace(/\D/g, '');
    if (digits.length > 0 && digits.length !== 10) { setError('err-phone', 'Enter a valid 10-digit US number'); valid = false; }
    else setError('err-phone', '');

    const amt = parseFloat(amountEl.value);
    if (!amt || amt <= 0) { setError('err-amount', 'Amount must be greater than $0'); valid = false; }
    else setError('err-amount', '');

    if (!expiresEl.value) { setError('err-expires', 'Select an expiry time'); valid = false; }
    else setError('err-expires', '');

    if (!descEl.value.trim()) { setError('err-desc', 'Description is required'); valid = false; }
    else setError('err-desc', '');

    return valid;
  }

  function showAlert(type, msg) {
    alertBox.className = `alert alert-${type}`;
    alertBox.textContent = msg;
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    submitBtn.querySelector('span').textContent = loading ? 'Sending…' : 'Generate & Send Link';
    submitBtn.querySelector('i').className = loading ? 'fas fa-spinner fa-spin' : 'fas fa-paper-plane';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    alertBox.className = 'alert hidden';

    const payload = {
      customer_name: nameEl.value.trim(),
      customer_email: emailEl.value.trim(),
      phone_number: phoneEl.value.trim() || null,
      amount: parseFloat(amountEl.value),
      description: descEl.value.trim(),
      expires_in_minutes: parseInt(expiresEl.value),
      agent_name: agentEl.value.trim() || 'Agent',
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
    form.reset();
    updatePreview();
  };
})();
