(function () {
  const conf = window.MEM_CONF || { min_span: 3, max_span: 6, trials_per_span: 2 };
  const display = document.getElementById('memory-display');
  const input = document.getElementById('memory-input');
  const btn = document.getElementById('memory-btn');
  const status = document.getElementById('memory-status');

  let span = conf.min_span;
  let trial = 0;
  let bestSpan = 0;
  let seq = '';
  let mode = 'ready'; // ready → showing → answer → ready …, finished

  // Число нельзя скопировать с экрана и вставить в поле.
  ['copy', 'cut', 'contextmenu', 'selectstart', 'dragstart'].forEach(ev =>
    display.addEventListener(ev, e => e.preventDefault()));
  document.addEventListener('copy', e => { if (mode === 'showing') e.preventDefault(); });
  ['paste', 'drop'].forEach(ev => input.addEventListener(ev, e => {
    e.preventDefault();
    status.textContent = 'Вставка отключена — введите число по памяти.';
  }));
  input.addEventListener('input', () => {
    input.value = input.value.replace(/\D/g, '').slice(0, conf.max_span);
  });

  function digits(n) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return n + ' цифра';
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return n + ' цифры';
    return n + ' цифр';
  }

  function randSeq(n) {
    let s = String(1 + Math.floor(Math.random() * 9));
    while (s.length < n) s += Math.floor(Math.random() * 10);
    return s;
  }

  function showTrial() {
    mode = 'showing';
    seq = randSeq(span);
    status.textContent = 'Запоминайте: ' + digits(span) + ' (попытка ' + (trial + 1) + ' из ' + conf.trials_per_span + ')';
    display.textContent = seq;
    input.style.display = 'none';
    btn.style.display = 'none';
    setTimeout(() => {
      mode = 'answer';
      display.textContent = '';
      input.style.display = '';
      input.value = '';
      input.focus();
      btn.style.display = '';
      btn.textContent = 'Ответить (Enter)';
      status.textContent = 'Введите число и нажмите Enter';
    }, Math.max(2000, span * 800));
  }

  function check() {
    const given = input.value.replace(/\D/g, '');
    if (!given) return;
    const ok = given === seq;
    input.style.display = 'none';
    if (ok) {
      bestSpan = span;
      span++;
      trial = 0;
      if (span > conf.max_span) return finish('Верно! Это максимальная длина теста.');
      status.textContent = 'Верно! Дальше — ' + digits(span) + '.';
    } else {
      trial++;
      if (trial >= conf.trials_per_span) return finish('Было: ' + seq + '.');
      status.textContent = 'Мимо, было: ' + seq + '. Ещё одна попытка той же длины.';
    }
    mode = 'ready';
    btn.textContent = 'Показать (Enter)';
  }

  function finish(msg) {
    mode = 'finished';
    status.textContent = msg + ' Ваш результат: ' + digits(bestSpan) + '. Сохраняем…';
    display.textContent = '';
    input.style.display = 'none';
    btn.style.display = 'none';
    fetch('/api/diagnostics/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ span: bestSpan })
    })
      .then(r => r.json())
      .then(d => { window.location.href = d.next || '/diagnostics'; });
  }

  function act() {
    if (mode === 'ready') showTrial();
    else if (mode === 'answer') check();
  }

  btn.addEventListener('click', act);
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || e.repeat) return;
    e.preventDefault();
    act();
  });
})();
