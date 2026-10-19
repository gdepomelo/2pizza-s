(function () {
  const duration = window.TAP_DURATION || 30;
  const btn = document.getElementById('tap-btn');
  const countEl = document.getElementById('tap-count');
  const timeEl = document.getElementById('tap-time');
  let taps = 0;
  let started = false;
  let timer = null;

  btn.disabled = false;
  btn.textContent = 'Нажимайте!';

  btn.addEventListener('click', () => {
    if (!started) {
      started = true;
      let left = duration;
      timeEl.textContent = left;
      timer = setInterval(() => {
        left--;
        timeEl.textContent = left;
        if (left <= 0) finish();
      }, 1000);
    }
    taps++;
    countEl.textContent = taps;
  });

  function finish() {
    clearInterval(timer);
    btn.disabled = true;
    btn.textContent = 'Готово';
    fetch('/api/diagnostics/tapping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ taps: taps, duration: duration })
    })
      .then(r => r.json())
      .then(() => { window.location.href = '/diagnostics/memory'; });
  }
})();
