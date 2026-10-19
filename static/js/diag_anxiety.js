(function () {
  const form = document.getElementById('anxiety-form');
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    const fd = new FormData(form);
    const answers = {};
    fd.forEach((v, k) => { answers[k] = v; });
    fetch('/api/diagnostics/anxiety', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: answers })
    })
      .then(r => r.json())
      .then(() => { window.location.href = '/diagnostics/result'; })
      .catch(() => alert('Ошибка отправки. Попробуйте ещё раз.'));
  });
})();
