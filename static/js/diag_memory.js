(function () {
  const conf = window.MEM_CONF || { min_span: 3, max_span: 7, trials_per_span: 2 };
  const display = document.getElementById('memory-display');
  const input = document.getElementById('memory-input');
  const btn = document.getElementById('memory-btn');
  const status = document.getElementById('memory-status');

  let span = conf.min_span;
  let trial = 0;
  let successBySpan = {};
  let bestSpan = 0;

  function randSeq(n) {
    const a = [];
    for (let i = 0; i < n; i++) a.push(Math.floor(Math.random() * 10));
    return a;
  }

  function showTrial() {
    const seq = randSeq(span);
    status.textContent = 'Запоминайте: длина ' + span + ' (попытка ' + (trial + 1) + '/' + conf.trials_per_span + ')';
    display.textContent = seq.join(' ');
    input.style.display = 'none';
    btn.style.display = 'none';
    const showMs = Math.max(2000, seq.length * 900);
    setTimeout(() => {
      display.textContent = '';
      input.style.display = '';
      input.value = '';
      input.focus();
      btn.style.display = '';
      btn.textContent = 'Ответить';
      btn.onclick = () => check(seq);
    }, showMs);
  }

  function check(seq) {
    const given = input.value.replace(/\s+/g, '');
    const answer = seq.join('');
    const ok = given === answer;
    if (ok) {
      if (!successBySpan[span]) successBySpan[span] = 0;
      successBySpan[span]++;
      bestSpan = Math.max(bestSpan, span);
    }
    trial++;
    const needMore = successBySpan[span] < conf.trials_per_span && trial < conf.trials_per_span;
    if (!ok && successBySpan[span] === 0 && trial >= 1 && span === conf.min_span) {
      return finish();
    }
    if (trial >= conf.trials_per_span) {
      if (!ok && successBySpan[span] === 0) return finish();
      span++;
      trial = 0;
      if (span > conf.max_span) return finish();
    }
    btn.onclick = null;
    btn.textContent = 'Показать';
    btn.onclick = () => { btn.onclick = null; btn.textContent = 'Ответить'; showTrial(); };
    status.textContent = ok ? 'Верно!' : 'Мимо. Показываю следующую попытку.';
  }

  function finish() {
    status.textContent = 'Диапазон памяти: ' + bestSpan + '. Отправляем…';
    display.textContent = '';
    input.style.display = 'none';
    btn.style.display = 'none';
    fetch('/api/diagnostics/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ span: bestSpan })
    })
      .then(r => r.json())
      .then(() => { window.location.href = '/diagnostics/anxiety'; });
  }

  btn.onclick = () => { btn.onclick = null; showTrial(); };
})();
