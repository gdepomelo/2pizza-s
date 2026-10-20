(function () {
  // Адаптивный тест «ошибка → адаптация»: старт со слова среднего уровня;
  // верно — следующее слово сложнее, неверно — чуть проще, но не ниже среднего.
  const words = window.DIAG_WORDS.slice();
  const LEVELS = window.DIAG_LEVELS || 1;
  const QUESTIONS = Math.min(15, words.length);
  const USAGE_MAX = 8;
  const MID = Math.floor((LEVELS - 1) / 2);

  const byLevel = {};
  words.forEach(w => { (byLevel[w.lvl] = byLevel[w.lvl] || []).push(w); });
  Object.values(byLevel).forEach(shuffle);

  let phase = 1;
  let level = MID;
  let asked = 0;
  let usageIdx = 0;
  let usageOrder = [];
  const items = [];
  const usagePool = [];

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

  // Слово нужного уровня; если они кончились — ближайший уровень (не ниже среднего, пока возможно).
  function takeWord(target) {
    const order = [];
    for (let d = 0; d < LEVELS; d++) {
      if (target + d < LEVELS) order.push(target + d);
      if (d && target - d >= MID) order.push(target - d);
    }
    for (let l = MID - 1; l >= 0; l--) order.push(l);
    for (const l of order) {
      if (byLevel[l] && byLevel[l].length) return byLevel[l].pop();
    }
    return null;
  }

  function setProgress(done, total) {
    barEl.style.width = (total ? (done / total) * 100 : 0) + '%';
  }

  function renderRecognition() {
    setProgress(asked, QUESTIONS);
    const w = asked < QUESTIONS ? takeWord(level) : null;
    if (!w) return startUsage();
    wordEl.textContent = w.word;
    const others = shuffle(words.filter(x => x.id !== w.id && x.translation !== w.translation)).slice(0, 3);
    const opts = shuffle([{ id: w.id, text: w.translation }, ...others.map(o => ({ id: o.id, text: o.translation }))]);
    opts.push({ id: '__none__', text: 'Не знаю' });
    optionsEl.innerHTML = '';
    opts.forEach((o, i) => {
      const b = optionButton(i, o.text);
      b.onclick = () => {
        const ok = o.id === w.id;
        items.push({ word_id: w.id, recognition_correct: ok, usage_correct: false, usage_asked: false });
        if (ok) usagePool.push(w);
        level = ok ? Math.min(LEVELS - 1, level + 1) : Math.max(MID, level - 1);
        asked++;
        renderRecognition();
      };
      optionsEl.appendChild(b);
    });
  }

  function startUsage() {
    phase = 2;
    usageOrder = shuffle(usagePool.filter(w => w.gap)).slice(0, USAGE_MAX);
    if (!usageOrder.length) return submitAll();
    phaseEl.textContent = 'Фаза 2 из 2: употребление в контексте. Выберите слово для пропуска (клавиши 1–4).';
    renderUsage();
  }

  function renderUsage() {
    setProgress(usageIdx, usageOrder.length);
    if (usageIdx >= usageOrder.length) return submitAll();
    const w = usageOrder[usageIdx];
    wordEl.innerHTML = '<div class="usage-sentence">' + escapeHtml(w.gap) + '</div>';
    const others = shuffle(words.filter(x => x.id !== w.id)).slice(0, 3);
    const opts = shuffle([{ id: w.id, text: w.word }, ...others.map(o => ({ id: o.id, text: o.word }))]);
    optionsEl.innerHTML = '';
    opts.forEach((o, i) => {
      const b = optionButton(i, o.text);
      b.onclick = () => {
        const item = items.find(it => it.word_id === w.id);
        item.usage_asked = true;
        item.usage_correct = o.id === w.id;
        usageIdx++;
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

  // Ответ с клавиатуры: цифры выбирают вариант.
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
