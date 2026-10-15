let liveLoading = false;

async function renderLive() {
  await loadLive();
  if (route.page === 'live' && liveData?.session?.status === 'active') {
    liveTimer = setInterval(() => loadLive(true), 1800);
  }
}

async function loadLive(silent=false) {
  if (liveLoading || route.page !== 'live') return;
  liveLoading = true;
  const sessionId = route.sessionId;
  try {
    const data = await api(`/api/sessions/${sessionId}`);
    if (route.page !== 'live' || route.sessionId !== sessionId) return;
    liveData = data;
    route.className = data.session.class_name;
    route.classId = data.session.class_id;
    setHeader();
    const session = data.session, question = data.current_question;
    const index = data.questions.findIndex(item => item.id === session.current_question_id);
    const completed = session.status === 'completed';
    if (completed && liveTimer) { clearInterval(liveTimer); liveTimer = null; }
    appRoot.innerHTML = `
      <div class="row between" style="margin-bottom:16px"><div>
        <div class="muted small">${esc(session.class_name)} · ${esc(session.quiz_title)}</div>
        <div style="margin-top:6px"><span class="pill ${session.accepting_answers ? '' : 'closed'}"><i class="dot"></i>${completed ? 'Đã kết thúc' : session.accepting_answers ? 'Đang nhận đáp án' : 'Đã khóa nhận đáp án'}</span></div>
      </div><div class="actions">
        <a class="btn outline sm" href="/sessions/${session.id}/present" target="_blank" rel="noopener">↗ Mở trình chiếu</a>
        ${completed ? `<button class="btn primary" onclick="navigate('result',{sessionId:${session.id}})">Xem kết quả</button>` : '<button class="btn danger" onclick="endSession()">Kết thúc phiên</button>'}
      </div></div>
      <div id="live-connection" class="report-alert" role="status"></div>
      <div class="live-layout"><div>
        <div class="panel question-live">${question ? `
          <div class="question-number">CÂU ${question.question_number} / ${data.questions.length}</div>
          <h2>${esc(question.question_text)}</h2>
          ${[...'ABCD'].map(letter => `<div class="answer-choice"><b>${letter}.</b>${esc(question['option_'+letter.toLowerCase()])}${session.answer_revealed && question.correct_answer === letter ? ' ✓' : ''}</div>`).join('')}
          <div class="notice">${session.answer_revealed ? `Đã công bố đáp án đúng: <strong>${esc(question.correct_answer)}</strong>. Câu này đã khóa nhận trả lời.` : 'Đáp án đang ẩn trên màn hình trình chiếu.'}</div>
          ${!completed ? `<div class="actions presentation-actions" data-live-controls>
            <button class="btn ${session.answer_revealed ? 'secondary' : 'primary'}" onclick="publishAnswer('${session.answer_revealed ? 'hide' : 'reveal'}',${question.id})">${session.answer_revealed ? 'Ẩn đáp án trên trình chiếu' : 'Công bố đáp án và khóa trả lời'}</button>
          </div><p class="muted small">Công bố sẽ khóa nhận trả lời câu hiện tại. Ẩn lại không mở khóa. Chuyển câu sẽ ẩn đáp án và nhận trả lời cho câu được chọn.</p>` : ''}
        ` : empty('Chưa có câu hiện tại','Chọn một câu hỏi để tiếp tục.')}</div>
        ${!completed ? `<div class="panel"><div class="live-controls" data-live-controls>
          <button class="btn secondary" onclick="control('previous')" ${index <= 0 ? 'disabled' : ''}>← Câu trước</button>
          <button class="btn secondary" onclick="control('next')" ${index >= data.questions.length-1 ? 'disabled' : ''}>Câu tiếp →</button>
          <select class="field" style="width:auto" aria-label="Chọn câu hỏi" onchange="control('go',this.value)">${data.questions.map(item => `<option value="${item.id}" ${item.id === session.current_question_id ? 'selected' : ''}>Câu ${item.question_number}</option>`).join('')}</select>
        </div><div class="muted small" style="margin-top:12px">Chuyển câu sẽ cập nhật thiết bị ESP32 và màn hình trình chiếu.</div></div>` : ''}
      </div><div>
        <div class="grid stats-grid" style="grid-template-columns:1fr 1fr">
          ${statCard('↗','Đã trả lời',data.stats.total)}${statCard('✓','Đúng',data.stats.correct)}
          ${statCard('×','Sai',data.stats.wrong)}${statCard('%','Tỷ lệ đúng',`${data.stats.correct_percent}%`)}
        </div>
        <div class="panel"><h2>Phân bố đáp án</h2>${[...'ABCD'].map(letter => {
          const count = data.options[letter] || 0, percent = data.stats.total ? Math.round(count*100/data.stats.total) : 0;
          return `<div class="bar-row"><strong>${letter}</strong><div class="bar-track"><div class="bar-fill" style="width:${percent}%"></div></div><div class="bar-count">${count} · ${percent}%</div></div>`;
        }).join('')}</div>
      </div></div>
      <div class="panel"><div class="panel-head"><h2>Danh sách sinh viên trả lời</h2><span class="muted small">Tự cập nhật mỗi 2 giây</span></div>
        ${data.responses.length ? table(['MSSV','Đáp án','Kết quả','Thời gian'],data.responses.map(response => [
          esc(response.mssv), `<strong>${esc(response.answer)}</strong>`, `<span class="badge ${response.result === 'Dung' ? '' : 'bad'}">${response.result === 'Dung' ? 'Đúng' : 'Sai'}</span>`, esc(response.updated_at)
        ])) : empty('Chưa có câu trả lời','Sinh viên trả lời trên thiết bị khi câu hỏi đang mở.')}
      </div>`;
  } catch (error) {
    if (route.page !== 'live' || route.sessionId !== sessionId) return;
    if (!silent) throw error;
    const message = document.getElementById('live-connection');
    if (message) message.textContent = 'Mất đồng bộ với server. Đang thử lại…';
    document.querySelectorAll('[data-live-controls] button,[data-live-controls] select').forEach(element => element.disabled = true);
  } finally { liveLoading = false; }
}

async function control(action, questionId) {
  try {
    await api(`/api/sessions/${route.sessionId}/control`, {method:'POST',body:JSON.stringify({action,question_id:questionId ? Number(questionId) : undefined})});
    await loadLive();
  } catch (error) { toast(error.message); }
}

async function publishAnswer(action, questionId) {
  const sessionId = route.sessionId;
  try {
    await api(`/api/sessions/${sessionId}/control`, {method:'POST',body:JSON.stringify({action,question_id:questionId})});
    if (route.page === 'live' && route.sessionId === sessionId) await loadLive();
    toast(action === 'reveal' ? 'Đã công bố đáp án và khóa nhận trả lời' : 'Đã ẩn đáp án; câu hỏi vẫn khóa nhận trả lời');
  } catch (error) { toast(error.message); }
}
