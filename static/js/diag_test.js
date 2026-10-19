(function () {
  const words = window.DIAG_WORDS.slice();
  const byId = {};
  words.forEach(w => { byId[w.id] = w; });

  let phase = 1;
  let idx = 0;
  const knownIds = new Set();
  const items = words.map(w => ({
    word_id: w.id,
    recognition_correct: false,
    usage_correct: false
  }));
  const usagePool = [];
  let usageOrder = [];

  const wordEl = document.getElementById('quiz-word');
  const optionsEl = document.getElementById('quiz-options');
  const barEl = document.getElementById('progress-bar');
  const phaseEl = document.getElementById('phase-label');

  function shuffle(a) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function setProgress() {
    const total = phase === 1 ? words.length : usageOrder.length;
    const done = phase === 1 ? idx : idx;
    barEl.style.width = (total ? (done / total) * 100 : 0) + '%';
  }

  function renderRecognition() {
    setProgress();
    if (idx >= words.length) {
      phase = 2;
      idx = 0;
      shuffle(usagePool);
      usageOrder = usagePool.slice(0, 10);
      if (usageOrder.length === 0) { submitAll(); return; }
      phaseEl.textContent = 'Фаза 2 из 2: употребление в контексте. Выберите слово для пропуска.';
      renderUsage();
      return;
    }
    const w = words[idx];
    wordEl.textContent = w.word;
    const others = words.filter(x => x.id !== w.id);
    shuffle(others);
    const opts = [{ id: '__none__', text: 'Не знаю' }].concat(
      others.slice(0, 3).map(o => ({ id: o.id, text: o.translation }))
    );
    shuffle(opts);
    optionsEl.innerHTML = '';
    opts.forEach(o => {
      const b = document.createElement('button');
      b.className = 'option-btn';
      b.textContent = o.text;
      b.onclick = () => {
        const item = items.find(it => it.word_id === w.id);
        if (o.id === w.id) {
          item.recognition_correct = true;
          knownIds.add(w.id);
          usagePool.push(w);
        }
        idx++;
        renderRecognition();
      };
      optionsEl.appendChild(b);
    });
  }

  function renderUsage() {
    setProgress();
    if (idx >= usageOrder.length) { submitAll(); return; }
    const w = usageOrder[idx];
    let sentence = w.example;
    const re = new RegExp(w.word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
    if (re.test(sentence)) sentence = sentence.replace(re, '_____');
    else sentence = 'The team discussed the _____ during the meeting.';
    wordEl.innerHTML = '<div class="usage-sentence">' + escapeHtml(sentence) + '</div>';
    const others = words.filter(x => x.id !== w.id);
    shuffle(others);
    const opts = shuffle([
      { id: w.id, text: w.word },
      ...others.slice(0, 3).map(o => ({ id: o.id, text: o.word }))
    ]);
    optionsEl.innerHTML = '';
    opts.forEach(o => {
      const b = document.createElement('button');
      b.className = 'option-btn';
      b.textContent = o.text;
      b.onclick = () => {
        const item = items.find(it => it.word_id === w.id);
        if (o.id === w.id) item.usage_correct = true;
        idx++;
        renderUsage();
      };
      optionsEl.appendChild(b);
    });
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function submitAll() {
    wordEl.textContent = 'Отправляем результат…';
    optionsEl.innerHTML = '';
    fetch('/api/diagnostics/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: items })
    })
      .then(r => r.json())
      .then(() => { window.location.href = '/diagnostics/tapping'; })
      .catch(() => { wordEl.textContent = 'Ошибка отправки. Обновите страницу.'; });
  }

  renderRecognition();
})();
