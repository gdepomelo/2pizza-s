(function () {
  const area = document.getElementById('practice-area');
  const startBtn = document.getElementById('start-btn');
  const progressBar = document.getElementById('p-bar');
  const progressEl = document.getElementById('p-progress');
  const summaryEl = document.getElementById('summary');

  let state = null;

  startBtn.addEventListener('click', startBlock);

  function startBlock() {
    fetch('/api/practice/start', { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          area.innerHTML = '<p>Сначала пройдите диагностику.</p>';
          return;
        }
        state = {
          blockId: data.block_id,
          plan: data.plan,
          params: data.params,
          index: 0,
          t0: 0
        };
        startBtn.style.display = 'none';
        summaryEl.style.display = 'none';
        area.style.display = '';
        nextExercise();
      });
  }

  function nextExercise() {
    if (!state || state.index >= state.plan.length) return finishBlock();
    const item = state.plan[state.index];
    progressEl.textContent = (state.index + 1) + ' / ' + state.plan.length;
    progressBar.style.width = (state.index / state.plan.length) * 100 + '%';
    fetch('/api/practice/exercise?word_id=' + encodeURIComponent(item.word_id) +
          '&kind=' + encodeURIComponent(item.kind))
      .then(r => r.json())
      .then(ex => {
        state.current = ex;
        state.t0 = Date.now();
        renderExercise(ex);
      });
  }

  function renderExercise(ex) {
    area.innerHTML = '';
    const card = document.createElement('div');
    card.className = 'exercise-card';

    if (ex.kind === 'card') {
      const h = document.createElement('div');
      h.className = 'ex-word';
      h.innerHTML = escapeHtml(ex.word) + ' <span class="muted">(' + escapeHtml(ex.pos) + ')</span>';
      card.appendChild(h);

      const speak = document.createElement('button');
      speak.className = 'btn btn-small';
      speak.textContent = 'Произношение';
      speak.onclick = () => {
        if (window.speechSynthesis) {
          const u = new SpeechSynthesisUtterance(ex.word);
          u.lang = 'en-US';
          speechSynthesis.speak(u);
        }
      };
      card.appendChild(speak);

      const exBlock = document.createElement('p');
      exBlock.className = 'ex-example';
      exBlock.innerHTML = '<em>' + escapeHtml(ex.example) + '</em>' +
        (ex.example_ru ? '<br><span class="muted">' + escapeHtml(ex.example_ru) + '</span>' : '');
      card.appendChild(exBlock);

      const flipBtn = document.createElement('button');
      flipBtn.className = 'btn btn-primary';
      flipBtn.textContent = 'Показать перевод';
      card.appendChild(flipBtn);

      const answerArea = document.createElement('div');
      answerArea.style.display = 'none';
      card.appendChild(answerArea);

      flipBtn.onclick = () => {
        answerArea.style.display = '';
        flipBtn.style.display = 'none';
        const tr = document.createElement('div');
        tr.className = 'ex-translation';
        tr.innerHTML = '<strong>' + escapeHtml(ex.translation) + '</strong><br><span class="muted">' + escapeHtml(ex.definition) + '</span>';
        answerArea.appendChild(tr);

        if (state.params && state.params.new_words !== undefined) { /* nothing */ }
        const fresh = document.createElement('button');
        fresh.className = 'btn btn-small';
        fresh.textContent = 'Новый пример от ИИ';
        fresh.onclick = () => {
          fresh.disabled = true;
          fresh.textContent = 'Готовим…';
          fetch('/api/practice/example', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_id: ex.word_id })
          }).then(r => r.json()).then(data => {
            if (data.example) {
              exBlock.innerHTML = '<em>' + escapeHtml(data.example) + '</em>' +
                (data.example_ru ? '<br><span class="muted">' + escapeHtml(data.example_ru) + '</span>' : '') +
                (data.source === 'ai' ? ' <span class="badge">ИИ</span>' : ' <span class="badge">банк</span>');
            }
            fresh.remove();
          });
        };
        answerArea.appendChild(fresh);

        const row = document.createElement('div');
        row.className = 'btn-row';
        const knew = document.createElement('button');
        knew.className = 'btn btn-primary';
        knew.textContent = 'Помню';
        const forgot = document.createElement('button');
        forgot.className = 'btn';
        forgot.textContent = 'Забыл';
        row.appendChild(knew);
        row.appendChild(forgot);
        answerArea.appendChild(row);
        knew.onclick = () => submitAnswer(ex, true, ex.translation, 'Помню');
        forgot.onclick = () => submitAnswer(ex, false, ex.translation, 'Забыл');
      };
    }

    if (ex.kind === 'choice') {
      const h = document.createElement('div');
      h.className = 'ex-prompt';
      h.textContent = 'Выберите слово для пропуска:';
      card.appendChild(h);
      const s = document.createElement('div');
      s.className = 'ex-sentence';
      s.textContent = ex.sentence;
      card.appendChild(s);
      if (ex.hint_letter) {
        const hint = document.createElement('p');
        hint.className = 'muted';
        hint.textContent = 'Подсказка: начинается на «' + ex.hint_letter + '», букв: ' + ex.hint_len;
        card.appendChild(hint);
      }
      const opts = document.createElement('div');
      opts.className = 'quiz-options';
      ex.options.forEach(o => {
        const b = document.createElement('button');
        b.className = 'option-btn';
        b.textContent = o;
        b.onclick = () => {
          const ok = o === ex.answer;
          submitAnswer(ex, ok, ex.answer, o);
        };
        opts.appendChild(b);
      });
      card.appendChild(opts);
    }

    if (ex.kind === 'fill') {
      const h = document.createElement('div');
      h.className = 'ex-prompt';
      h.textContent = 'Впишите пропущенное слово:';
      card.appendChild(h);
      const s = document.createElement('div');
      s.className = 'ex-sentence';
      s.textContent = ex.sentence;
      card.appendChild(s);
      if (ex.hint_letter) {
        const hint = document.createElement('p');
        hint.className = 'muted';
        hint.textContent = 'Подсказка: начинается на «' + ex.hint_letter + '», букв: ' + ex.hint_len;
        card.appendChild(hint);
      }
      const input = document.createElement('input');
      input.type = 'text';
      input.autocomplete = 'off';
      input.className = 'memory-input';
      card.appendChild(input);
      const btn = document.createElement('button');
      btn.className = 'btn btn-primary';
      btn.textContent = 'Ответить';
      card.appendChild(btn);
      const go = () => {
        const val = input.value.trim().toLowerCase();
        if (!val) return;
        const norm = s => s.trim().toLowerCase().replace(/s$/, '');
        const ok = norm(val) === norm(ex.answer);
        submitAnswer(ex, ok, ex.answer, val, !!ex.hint_letter && ex.hints >= 2);
      };
      btn.onclick = go;
      input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
      setTimeout(() => input.focus(), 50);
    }

    area.appendChild(card);
  }

  function submitAnswer(ex, correct, correctAnswer, given, hintUsed) {
    const t1 = Date.now();
    const rt = t1 - state.t0;
    fetch('/api/practice/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word_id: ex.word_id,
        kind: ex.kind,
        correct: correct,
        response_time_ms: rt,
        hint_used: hintUsed || false,
        block_id: state.blockId
      })
    }).then(() => {
      fetch('/api/practice/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          word_id: ex.word_id,
          kind: ex.kind,
          correct: correct,
          mode: window.FEEDBACK_MODE || 'brief',
          given: String(given || ''),
          correct_answer: correctAnswer
        })
      }).then(r => r.json()).then(fb => {
        showFeedback(fb, correctAnswer);
      });
    });
  }

  function showFeedback(fb, correctAnswer) {
    const box = document.createElement('div');
    box.className = 'feedback ' + (fb.correct ? 'ok' : 'bad');
    let html = '<strong>' + (fb.correct ? 'Верно' : 'Неверно') + '</strong>';
    if (!fb.correct) html += '. Правильный ответ: <strong>' + escapeHtml(correctAnswer) + '</strong>';
    html += '<br>' + escapeHtml(fb.translation || '');
    if (fb.explanation && fb.explanation.explanation) {
      html += '<br>' + escapeHtml(fb.explanation.explanation);
      if (fb.explanation.source === 'ai') html += ' <span class="badge">ИИ</span>';
    } else if (!fb.correct && fb.example) {
      html += '<br><em>' + escapeHtml(fb.example) + '</em>';
    }
    box.innerHTML = html;
    area.appendChild(box);

    const next = document.createElement('button');
    next.className = 'btn btn-primary';
    next.textContent = state.index + 1 >= state.plan.length ? 'Завершить блок' : 'Дальше';
    next.onclick = () => {
      state.index++;
      nextExercise();
    };
    area.appendChild(next);
  }

  function finishBlock() {
    fetch('/api/practice/finish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: state.blockId })
    })
      .then(r => r.json())
      .then(data => {
        area.style.display = 'none';
        progressBar.style.width = '100%';
        progressEl.textContent = state.plan.length + ' / ' + state.plan.length;
        summaryEl.style.display = '';
        let html = '<h2>Блок завершён</h2>';
        html += '<p>Верных ответов: <strong>' + data.correct + ' из ' + data.total + '</strong>';
        if (data.avg_time_ms) html += ' · среднее время ' + Math.round(data.avg_time_ms / 100) / 10 + ' с';
        html += '</p>';
        if (data.fatigue && data.fatigue_message) {
          html += '<div class="feedback warn">' + escapeHtml(data.fatigue_message) + '</div>';
        }
        if (data.recommendation) {
          html += '<div class="feedback info">' + escapeHtml(data.recommendation) + '</div>';
        }
        html += '<button class="btn btn-primary" id="again-btn">Новый блок</button>';
        summaryEl.innerHTML = html;
        document.getElementById('again-btn').onclick = () => {
          summaryEl.style.display = 'none';
          area.style.display = '';
          startBtn.style.display = 'none';
          fetch('/api/practice/start', { method: 'POST' })
            .then(r => r.json())
            .then(d => {
              state = { blockId: d.block_id, plan: d.plan, params: d.params, index: 0, t0: 0 };
              nextExercise();
            });
        };
      });
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
