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
      phaseEl.textContent = 'Фаза 2 из 2: употребление в контексте. Выберите слово для пропуска (клавиши 1–4).';
      renderUsage();
      return;
    }
    const w = words[idx];
    wordEl.textContent = w.word;
    const others = words.filter(x => x.id !== w.id);
    shuffle(others);
    
    // Формируем варианты: правильный ответ + 3 неправильных + "Не знаю"
    const opts = [
      { id: w.id, text: w.translation },
      ...others.slice(0, 3).map(o => ({ id: o.id, text: o.translation })),
      { id: '__none__', text: 'Не знаю' }
    ];
    shuffle(opts);
    // «Не знаю» всегда последним
    opts.sort((a, b) => (a.id === '__none__') - (b.id === '__none__'));
    optionsEl.innerHTML = '';
    opts.forEach((o, i) => {
      const b = optionButton(i, o.text);
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
    opts.forEach((o, i) => {
      const b = optionButton(i, o.text);
      b.onclick = () => {
        const item = items.find(it => it.word_id === w.id);
        if (o.id === w.id) item.usage_correct = true;
        idx++;
        renderUsage();
      };
      optionsEl.appendChild(b);
    });
  }

  function optionButton(i, text) {
    const b = document.createElement('button');
    b.className = 'option-btn';
    const k = document.createElement('kbd');
    k.textContent = String(i + 1);
    b.appendChild(k);
    b.appendChild(document.createTextNode(' ' + text));
    return b;
  }

  // Ответ с клавиатуры: цифры 1–5 выбирают вариант.
  document.addEventListener('keydown', e => {
    if (e.repeat || e.ctrlKey || e.altKey || e.metaKey) return;
    const n = parseInt(e.key, 10);
    if (!n) return;
    const btns = optionsEl.querySelectorAll('.option-btn');
    if (btns[n - 1]) { e.preventDefault(); btns[n - 1].click(); }
  });

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
      .then(d => { window.location.href = d.next || '/diagnostics'; })
      .catch(() => { wordEl.textContent = 'Ошибка отправки. Обновите страницу.'; });
  }

  renderRecognition();
})();
