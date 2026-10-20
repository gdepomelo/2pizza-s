(function () {
  const area = document.getElementById('practice-area');
  const startBtn = document.getElementById('start-btn');
  const progressBar = document.getElementById('p-bar');
  const progressEl = document.getElementById('p-progress');
  const stageEl = document.getElementById('p-stage');

  const STAGES = {
    cards: { num: 1, title: 'Карточки', kind: 'card' },
    gaps: { num: 2, title: 'Fill the gaps', kind: 'choice' }
  };
  const encouraging = window.FEEDBACK_MODE === 'encouraging';

  let block = null;  // { blockId, words: {id: {is_new}}, ids, results: {id: {clean, rt}} }
  let stage = null;  // { key, queue, pile, round, learned, total, misses: {id: n} }
  let keyHandler = null;

  // Один обработчик клавиатуры; каждый экран подставляет свой keyHandler.
  document.addEventListener('keydown', e => {
    if (!keyHandler || e.repeat || e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.target && e.target.tagName === 'INPUT') return;
    if (keyHandler(e) === true) e.preventDefault();
  });

  startBtn.addEventListener('click', () => startBlock());
  keyHandler = e => { if (e.key === 'Enter') { startBlock(); return true; } };
  showDaily(window.DAILY);

  function startBlock(mode) {
    keyHandler = null;
    currentCard = null;
    area.innerHTML = '<p class="muted">Готовим блок…</p>';
    fetch('/api/practice/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: mode || 'auto' })
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          area.innerHTML = '<p>Сначала пройдите диагностику.</p>';
          return;
        }
        block = { blockId: data.block_id, words: {}, ids: [], results: {},
                  kind: data.kind, moduleId: data.module_id, module: data.module };
        data.words.forEach(w => {
          block.words[w.word_id] = w;
          block.ids.push(w.word_id);
          block.results[w.word_id] = { word_id: w.word_id, clean: true, response_time_ms: null };
        });
        startStage('cards');
      });
  }

  function startStage(key) {
    stage = { key: key, queue: shuffle(block.ids.slice()), pile: [], round: 1, learned: 0,
              total: block.ids.length, misses: {} };
    next();
  }

  function updateProgress() {
    const s = STAGES[stage.key];
    const label = block.kind === 'review' ? 'Повторение' : block.kind === 'extra' ? 'Доп. повторение' : block.module;
    stageEl.textContent = (label ? label + ' · ' : '') + 'Этап ' + s.num + ' из 2 · ' + s.title + (stage.round > 1 ? ' · круг ' + stage.round : '');
    progressEl.textContent = 'выучено ' + stage.learned + ' из ' + stage.total +
      (stage.pile.length ? ' · в стопке «Забыл»: ' + stage.pile.length : '');
    progressBar.style.width = (stage.learned / stage.total) * 100 + '%';
  }

  function next() {
    updateProgress();
    if (!stage.queue.length) {
      if (stage.pile.length) return showRoundIntro();
      return showStageSummary();
    }
    const wid = stage.queue.shift();
    keyHandler = null;
    fetch('/api/practice/exercise?word_id=' + encodeURIComponent(wid) +
          '&kind=' + STAGES[stage.key].kind)
      .then(r => r.json())
      .then(ex => {
        ex.t0 = Date.now();
        if (ex.kind === 'card') renderCard(ex); else renderChoice(ex);
        if (document.activeElement) document.activeElement.blur();
      });
  }

  function miss(wid) {
    stage.misses[wid] = (stage.misses[wid] || 0) + 1;
    block.results[wid].clean = false;
    if (stage.pile.indexOf(wid) === -1) stage.pile.push(wid);
  }

  function logAnswer(ex, correct, rt, hintUsed) {
    return fetch('/api/practice/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word_id: ex.word_id, kind: ex.kind, correct: correct,
        response_time_ms: rt, hint_used: !!hintUsed, block_id: block.blockId
      })
    });
  }

  // ---------- Этап 1: карточки-перевёртыши ----------

  // Направление карточек: «слово → перевод» или «перевод → слово» (переключатель над тренировкой).
  const dirToggle = document.getElementById('dir-toggle');
  try { dirToggle.checked = localStorage.getItem('cardReverse') === '1'; } catch (e) { /* без хранилища */ }
  dirToggle.addEventListener('change', () => {
    try { localStorage.setItem('cardReverse', dirToggle.checked ? '1' : '0'); } catch (e) { /* без хранилища */ }
    dirToggle.blur();
    if (currentCard) renderCard(currentCard);
  });
  let currentCard = null;

  function renderCard(ex) {
    currentCard = ex;
    const reverse = dirToggle.checked;
    const isNew = block.words[ex.word_id] && block.words[ex.word_id].is_new;
    const badge = '<span class="badge">' + (isNew ? 'новое слово' : 'повторение') + '</span>';
    const enSide =
      '<div class="ex-word">' + esc(ex.word) + ' <span class="muted">(' + esc(ex.pos) + ')</span></div>' +
      '<p class="ex-example" id="card-example">' + ex.example_html + '</p>';
    const ruSide =
      '<div class="ex-translation">' + esc(ex.translation) + '</div>' +
      '<p class="ex-example">' + ex.example_ru_html + '</p>';
    const sound =
      '<div class="btn-row center-row">' +
        '<button class="btn btn-small" data-say="word">🔊 Слово</button>' +
        '<button class="btn btn-small" data-say="example">🔊 Пример</button>' +
      '</div>';
    const hint = '<p class="muted flip-hint">' +
      (reverse ? 'Вспомните английское слово. Проверить' : 'Проверить перевод') +
      ' — нажмите на карточку или <kbd>Пробел</kbd></p>';
    const front = reverse ? badge + ruSide + hint : badge + enSide + hint;
    const back = reverse
      ? enSide + sound + '<p class="muted">' + esc(ex.definition) + '</p>'
      : ruSide + sound + '<p class="muted">' + esc(ex.definition) + '</p>';

    area.innerHTML =
      '<div class="flip-card" id="flip-card" role="button" tabindex="0" aria-label="Перевернуть карточку">' +
        '<div class="flip-inner">' +
          '<div class="flip-face flip-front' + (reverse ? ' face-ru' : '') + '">' + front + '</div>' +
          '<div class="flip-face flip-back' + (reverse ? ' face-en' : '') + '">' + back + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="btn-row center-row card-answers" id="card-answers">' +
        '<button class="btn btn-forgot" id="btn-forgot"><kbd>←</kbd> Забыл</button>' +
        '<button class="btn btn-primary" id="btn-knew">Помню <kbd>→</kbd></button>' +
      '</div>';

    const card = document.getElementById('flip-card');
    let done = false;

    // Переворот необязателен: «Помню»/«Забыл» можно нажать сразу.
    const flip = () => card.classList.toggle('flipped');
    const answer = remembered => {
      if (done) return;
      done = true;
      currentCard = null;
      const rt = Date.now() - ex.t0;
      if (remembered) stage.learned++; else miss(ex.word_id);
      logAnswer(ex, remembered, rt).then(next);
    };

    card.addEventListener('click', e => {
      const say = e.target.closest('[data-say]');
      if (say) {
        e.stopPropagation();
        say.blur();
        speak(say.dataset.say === 'word' ? ex.word : document.getElementById('card-example').textContent);
        return;
      }
      flip();
    });
    document.getElementById('btn-forgot').onclick = () => answer(false);
    document.getElementById('btn-knew').onclick = () => answer(true);

    keyHandler = e => {
      if (e.key === ' ' || e.key === 'Spacebar') { flip(); return true; }
      if (e.key === 'ArrowLeft') { answer(false); return true; }
      if (e.key === 'ArrowRight') { answer(true); return true; }
    };
  }

  // ---------- Этап 2: Fill the gaps ----------

  function renderChoice(ex) {
    area.innerHTML = '';
    const card = document.createElement('div');
    card.className = 'exercise-card';
    let html = '<div class="ex-prompt">' + esc(ex.prompt) + '</div>' +
      '<div class="ex-sentence">' + esc(ex.sentence) + '</div>';
    if (ex.hint_letter) {
      html += '<p class="muted">Подсказка: начинается на «' + esc(ex.hint_letter) + '», букв: ' + ex.hint_len + '</p>';
    }
    html += '<div class="quiz-options" id="opts"></div>' +
      '<div class="btn-row"><button class="btn btn-primary" id="commit" disabled>Ответить <kbd>Enter</kbd></button></div>' +
      '<div id="fb"></div>';
    card.innerHTML = html;
    area.appendChild(card);

    const optsEl = card.querySelector('#opts');
    const commitBtn = card.querySelector('#commit');
    const fb = card.querySelector('#fb');
    const buttons = [];
    const wrongTried = [];
    let selected = null;
    let finished = false;
    let explainPromise = null;

    const explain = () => {
      if (!explainPromise) {
        explainPromise = fetch('/api/practice/explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word_id: ex.word_id, options: ex.options })
        }).then(r => r.json());
      }
      return explainPromise;
    };

    ex.options.forEach((o, i) => {
      const b = document.createElement('button');
      b.className = 'option-btn';
      b.innerHTML = '<kbd>' + (i + 1) + '</kbd> ' + esc(o);
      b.onclick = () => select(i);
      optsEl.appendChild(b);
      buttons.push(b);
    });

    function select(i) {
      if (finished || !buttons[i] || buttons[i].disabled) return;
      selected = i;
      buttons.forEach((b, j) => b.classList.toggle('selected', j === i));
      commitBtn.disabled = false;
    }

    function commit() {
      if (finished || selected === null) return;
      const given = ex.options[selected];
      const btn = buttons[selected];
      const ok = given.toLowerCase() === ex.answer.toLowerCase();
      const firstAttempt = wrongTried.length === 0;
      const rt = Date.now() - ex.t0;
      if (firstAttempt) {
        block.results[ex.word_id].response_time_ms = rt;
        logAnswer(ex, ok, rt, ex.hints >= 2 && ex.hint_letter);
      }
      selected = null;
      commitBtn.disabled = true;
      btn.classList.remove('selected');
      if (!ok) {
        wrongTried.push(given);
        btn.classList.add('wrong');
        btn.disabled = true;
        explain().then(renderWrong);
        return;
      }
      finished = true;
      btn.classList.add('right');
      buttons.forEach(b => { b.disabled = true; });
      commitBtn.parentNode.remove();
      explain().then(renderRight);
    }

    function optionLine(o, mark) {
      const tr = o.translation ? ' — «' + esc(o.translation) + '»' : '';
      return '<li>' + (mark ? '<span class="tag-bad">ваш ответ</span> ' : '') +
        '<span class="ctx-en">' + o.sentence_html + '</span>' +
        '<div class="ctx-why"><b>' + esc(o.word) + '</b>' + tr + '. ' + esc(capitalize(o.explanation)) +
        (o.source === 'ai' ? ' <span class="badge">ИИ</span>' : '') + '</div></li>';
    }

    // Все неверные попытки — в одном окне, без повторных всплывающих блоков.
    function renderWrong(data) {
      const tried = data.options.filter(o => wrongTried.indexOf(o.word) !== -1);
      fb.innerHTML = '<div class="feedback bad">' +
        '<strong>' + (encouraging ? 'Почти! Попробуйте ещё раз.' : 'Неверно. Попробуйте ещё раз.') + '</strong> ' +
        '<span class="muted">Слово вернётся на повторение в конце этапа.</span>' +
        '<ul class="ctx-list">' + tried.map(o => optionLine(o, false)).join('') + '</ul></div>';
    }

    function renderRight(data) {
      const a = data.answer;
      let head = encouraging ? 'Отлично, получилось!' : 'Верно!';
      if (wrongTried.length) head = 'Верно, с ' + (wrongTried.length + 1) + '-й попытки.';
      fb.innerHTML = '<div class="feedback ok">' +
        '<p><strong>' + head + '</strong> «' + esc(a.word) + '» — это «' + esc(a.translation) + '».</p>' +
        '<p>Обратите внимание на контекст:</p>' +
        '<div class="ctx-box"><div class="ctx-en">' + a.sentence_html + '</div>' +
        '<div class="ctx-ru">' + a.sentence_ru_html + '</div></div>' +
        (data.options.length ? '<p>Другие варианты:</p><ul class="ctx-list">' +
          data.options.map(o => optionLine(o, wrongTried.indexOf(o.word) !== -1)).join('') + '</ul>' : '') +
        (wrongTried.length ? '<p class="muted">Слово отложено в стопку повторения и вернётся в конце этапа.</p>' : '') +
        '</div>' +
        '<div class="btn-row"><button class="btn btn-primary" id="next-btn">Дальше <kbd>Enter</kbd></button></div>';
      document.getElementById('next-btn').onclick = goNext;
    }

    let advanced = false;
    function goNext() {
      if (!finished || advanced || !document.getElementById('next-btn')) return;
      advanced = true;
      if (wrongTried.length) miss(ex.word_id); else stage.learned++;
      next();
    }

    commitBtn.onclick = commit;
    keyHandler = e => {
      const n = parseInt(e.key, 10);
      if (n >= 1 && n <= buttons.length) { select(n - 1); return true; }
      if (e.key === 'Enter') { if (finished) goNext(); else commit(); return true; }
    };
  }

  // ---------- Круги повторения и итоги ----------

  function showRoundIntro() {
    stage.round++;
    stage.queue = shuffle(stage.pile.slice());
    stage.pile = [];
    stage.learned = stage.total - stage.queue.length;
    updateProgress();
    area.innerHTML = '<div class="exercise-card">' +
      '<h2>Круг ' + stage.round + ': стопка «Забыл»</h2>' +
      '<p>Повторяем слова, которые пока не получились (' + stage.queue.length + '). ' +
      'Круги продолжаются, пока стопка не опустеет.</p>' +
      wordList(stage.queue) +
      '<button class="btn btn-primary" id="round-btn">Продолжить <kbd>Enter</kbd></button></div>';
    const go = () => { keyHandler = null; next(); };
    document.getElementById('round-btn').onclick = go;
    keyHandler = e => { if (e.key === 'Enter') { go(); return true; } };
  }

  function stageSummaryHtml() {
    const s = STAGES[stage.key];
    const missed = Object.keys(stage.misses);
    const firstTry = stage.total - missed.length;
    let html = '<h2>Этап ' + s.num + ' «' + s.title + '» завершён</h2>' +
      '<ul class="stat-list">' +
      '<li><span>Слов в блоке</span><strong>' + stage.total + '</strong></li>' +
      '<li><span>С первого раза</span><strong>' + firstTry + '</strong></li>' +
      '<li><span>Пришлось повторять</span><strong>' + missed.length + '</strong></li>' +
      '<li><span>Кругов</span><strong>' + stage.round + '</strong></li></ul>';
    if (missed.length) {
      html += '<p>Слова из стопки «Забыл» (все выучены):</p>' + wordList(missed, stage.misses);
    }
    return html;
  }

  function showStageSummary() {
    progressBar.style.width = '100%';
    if (stage.key === 'cards') {
      area.innerHTML = '<div class="exercise-card">' + stageSummaryHtml() +
        '<button class="btn btn-primary" id="stage-btn">Перейти к Fill the gaps <kbd>Enter</kbd></button></div>';
      const go = () => { keyHandler = null; startStage('gaps'); };
      document.getElementById('stage-btn').onclick = go;
      keyHandler = e => { if (e.key === 'Enter') { go(); return true; } };
      return;
    }
    finishBlock(stageSummaryHtml());
  }

  function finishBlock(stageHtml) {
    keyHandler = null;
    fetch('/api/practice/finish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: block.blockId, results: Object.values(block.results),
                             kind: block.kind, module_id: block.moduleId })
    })
      .then(r => r.json())
      .then(data => {
        const clean = Object.values(block.results).filter(r => r.clean).length;
        let html = '<div class="exercise-card">' + stageHtml + '<hr>' +
          '<h2>Блок завершён</h2>' +
          '<p>Слов без единой ошибки на обоих этапах: <strong>' + clean + ' из ' + block.ids.length + '</strong>';
        if (data.avg_time_ms) html += ' · среднее время ответа ' + Math.round(data.avg_time_ms / 100) / 10 + ' с';
        html += '</p><p class="muted">Слова без ошибок вернутся позже по расписанию, остальные — завтра. ' +
          'Следующий блок возьмёт другие слова.</p>';
        if (data.fatigue && data.fatigue_message) {
          html += '<div class="feedback warn">' + esc(data.fatigue_message) + '</div>';
        }
        if (data.recommendation) {
          html += '<div class="feedback info">' + esc(data.recommendation) + '</div>';
        }
        const d = data.daily;
        if (d) {
          html += '<div class="feedback ' + (d.goal_met ? 'ok' : 'info') + '">' +
            (d.goal_met
              ? '🎯 Цель на сегодня выполнена (' + d.today + ' из ' + d.goal + ')! Серия: ' + days(d.streak) + ' 🔥'
              : 'Цель на сегодня: ' + d.today + ' из ' + d.goal + ' блоков. Ещё ' + (d.goal - d.today) +
                ' — и серия продолжится' + (d.streak ? ' (сейчас ' + days(d.streak) + ')' : '') + '.') +
            '</div>';
        }
        html += '<div class="btn-row"><button class="btn btn-primary" id="again-btn">Новый блок <kbd>Enter</kbd></button>' +
          '<a class="btn" href="/cabinet">Личный кабинет</a></div></div>';
        area.innerHTML = html;
        stageEl.textContent = 'Блок завершён';
        progressEl.textContent = '';
        showDaily(d);
        document.getElementById('again-btn').onclick = () => startBlock();
        keyHandler = e => { if (e.key === 'Enter') { startBlock(); return true; } };
        if (data.module_done) showModuleDone(data.module_done);
      });
  }

  // Модуль завершён: отдельное окно и переход к следующему модулю.
  function showModuleDone(m) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' +
      '<div class="modal-icon">🏁</div>' +
      '<h2>' + esc(m.title) + ' завершён!</h2>' +
      '<p>Все слова модуля изучены. Они будут возвращаться на повторение по расписанию.</p>' +
      (m.next_title
        ? '<p>Следующий модуль: <strong>' + esc(m.next_title) + '</strong></p>' +
          (m.next_topic ? '<p class="muted">Тема: ' + esc(m.next_topic) + '</p>' : '') +
          '<div class="btn-row center-row"><button class="btn btn-primary" id="next-module-btn">Приступить к следующему модулю <kbd>Enter</kbd></button>' +
          '<button class="btn" id="close-modal-btn">Позже</button></div>'
        : '<p><strong>Это был последний модуль.</strong> Дальше — повторения по расписанию.</p>' +
          '<div class="btn-row center-row"><button class="btn btn-primary" id="close-modal-btn">Закрыть <kbd>Enter</kbd></button></div>') +
      '</div>';
    document.body.appendChild(overlay);
    const close = () => {
      overlay.remove();
      keyHandler = e => { if (e.key === 'Enter') { startBlock(); return true; } };
    };
    const go = () => { overlay.remove(); startBlock('new'); };
    document.getElementById('close-modal-btn').onclick = close;
    const nextBtn = document.getElementById('next-module-btn');
    if (nextBtn) nextBtn.onclick = go;
    keyHandler = e => {
      if (e.key === 'Enter') { (nextBtn ? go : close)(); return true; }
      if (e.key === 'Escape') { close(); return true; }
    };
  }

  function showDaily(d) {
    const el = document.getElementById('p-daily');
    if (!el || !d) return;
    el.innerHTML = '🎯 Сегодня: <strong>' + d.today + ' / ' + d.goal + '</strong> блоков' +
      ' · 🔥 Серия: <strong>' + days(d.streak) + '</strong>';
    el.classList.toggle('goal-met', !!d.goal_met);
  }

  function days(n) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return n + ' день';
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return n + ' дня';
    return n + ' дней';
  }

  // ---------- утилиты ----------

  function wordList(ids, counts) {
    return '<ul class="word-pile">' + ids.map(id => {
      const n = counts && counts[id];
      const w = block.words[id] || { word: id, translation: '' };
      return '<li><b>' + esc(w.word) + '</b> — ' + esc(w.translation) +
        (n ? ' <span class="muted">(не получилось: ' + n + ')</span>' : '') + '</li>';
    }).join('') + '</ul>';
  }

  function speak(text) {
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-US';
    speechSynthesis.speak(u);
  }

  function shuffle(a) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function capitalize(s) {
    s = String(s || '');
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
