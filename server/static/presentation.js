const presentationRoot = document.getElementById('presentation');
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let lastPresentation = '', presentationTimer;

function drawPresentation(data) {
  const session = data.session, question = data.current_question;
  document.getElementById('session-title').textContent = `${session.class_name} · ${session.quiz_title}`;
  const snapshot = JSON.stringify(data);
  if (snapshot === lastPresentation) return;
  lastPresentation = snapshot;
  if (!question) {
    presentationRoot.innerHTML = '<p class="message">Phiên chưa có câu hỏi hiện tại.</p>';
    return;
  }
  const revealed = session.answer_revealed;
  const status = session.status === 'completed' ? 'Phiên kiểm tra đã kết thúc.' :
    revealed ? `Đáp án đúng: ${question.correct_answer} · Đã khóa nhận trả lời` :
    session.accepting_answers ? 'Chọn đáp án trên thiết bị ESP32 của bạn.' : 'Đã khóa nhận trả lời.';
  presentationRoot.innerHTML = `
    <div class="meta"><span class="question-number">CÂU ${data.question_number} / ${data.question_count}</span>
      <span class="counter">${data.answered} lượt trả lời</span></div>
    <h1>${escapeText(question.question_text)}</h1>
    <div class="choices">${[...'ABCD'].map(letter => `
      <div class="choice ${revealed && question.correct_answer === letter ? 'correct' : ''}">
        <b>${letter}.</b><div class="choice-text">${escapeText(question['option_' + letter.toLowerCase()])}
        ${revealed ? `<span class="distribution">${data.options[letter]} lượt · ${data.answered ? Math.round(data.options[letter] * 100 / data.answered) : 0}%${question.correct_answer === letter ? ' · ✓ Đáp án đúng' : ''}</span>` : ''}</div>
      </div>`).join('')}</div>
    <div class="answer-status ${revealed ? 'revealed' : ''}">${escapeText(status)}</div>`;
}

async function refreshPresentation() {
  try {
    const response = await fetch(`/api/sessions/${presentationSessionId}/presentation`, {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || 'Không tải được phiên.');
    drawPresentation(data);
    document.body.classList.remove('disconnected');
    const status = document.getElementById('connection');
    status.className = '';
    status.textContent = data.session.status === 'completed' ? 'Phiên đã kết thúc' : 'Đã kết nối · ' + new Date().toLocaleTimeString('vi-VN');
    if (data.session.status === 'completed') return;
  } catch (error) {
    document.body.classList.add('disconnected');
    // Hide stale answers while disconnected; a teacher may have moved questions.
    presentationRoot.innerHTML = '<p class="message">Mất kết nối. Đang đồng bộ lại câu hỏi…</p>';
    lastPresentation = '';
    const status = document.getElementById('connection');
    status.className = 'offline';
    status.textContent = error.message + ' · Tự động thử lại';
  }
  presentationTimer = setTimeout(refreshPresentation, 1500);
}

document.getElementById('fullscreen').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch {
    document.getElementById('connection').textContent = 'Có thể dùng F11 để trình chiếu toàn màn hình.';
  }
});
document.addEventListener('fullscreenchange', () => {
  document.getElementById('fullscreen').textContent = document.fullscreenElement ? 'Thoát toàn màn hình' : 'Toàn màn hình';
});
window.addEventListener('pagehide', () => clearTimeout(presentationTimer));
refreshPresentation();
