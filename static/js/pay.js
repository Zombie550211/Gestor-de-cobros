/* Payment page — Stripe Elements + countdown timer */

(async function () {
  // Countdown timer
  function startTimer() {
    const el = document.getElementById('countdown');
    if (!el) return;

    function tick() {
      const now = new Date();
      const diff = Math.max(0, Math.floor((EXPIRES_AT - now) / 1000));
      if (diff === 0) {
        el.textContent = 'EXPIRED';
        el.classList.add('urgent');
        const btn = document.getElementById('pay-btn');
        if (btn) btn.disabled = true;
        return;
      }
      const mins = Math.floor(diff / 60);
      const secs = diff % 60;
      el.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
      if (diff < 300) el.classList.add('urgent');
      setTimeout(tick, 1000);
    }
    tick();
  }
  startTimer();

  // Stripe initialization
  if (!STRIPE_KEY || STRIPE_KEY === 'pk_test_placeholder') {
    document.getElementById('payment-element').innerHTML =
      '<p style="color:#94A3B8;text-align:center;padding:20px">Stripe not configured yet. Add your STRIPE_PUBLISHABLE_KEY to .env</p>';
    return;
  }

  const stripe = Stripe(STRIPE_KEY);
  const elements = stripe.elements({ clientSecret: CLIENT_SECRET });
  const paymentElement = elements.create('payment', {
    layout: 'tabs',
  });
  paymentElement.mount('#payment-element');

  // Track when customer starts entering payment info
  paymentElement.on('change', () => {
    fetch(`/api/payments/${TOKEN}/activity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'processing' }),
    }).catch(() => {});
  });

  // Track time spent
  const startTime = Date.now();
  window.addEventListener('beforeunload', () => {
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    fetch(`/api/payments/${TOKEN}/activity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ time_spent: elapsed }),
      keepalive: true,
    }).catch(() => {});
  });

  const form = document.getElementById('payment-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const btn = document.getElementById('pay-btn');
    const btnText = document.getElementById('pay-btn-text');
    const btnSpinner = document.getElementById('pay-btn-spinner');
    const errEl = document.getElementById('payment-errors');

    btn.disabled = true;
    btnText.classList.add('hidden');
    btnSpinner.classList.remove('hidden');
    errEl.classList.add('hidden');

    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: RETURN_URL },
    });

    if (error) {
      errEl.textContent = error.message;
      errEl.classList.remove('hidden');
      btn.disabled = false;
      btnText.classList.remove('hidden');
      btnSpinner.classList.add('hidden');
    }
  });
})();
