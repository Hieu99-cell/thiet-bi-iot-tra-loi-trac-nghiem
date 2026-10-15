let resultReport = null;

const percentage = value => value == null ? '—' : `${value}%`;

async function renderResult() {
  const sessionId = route.sessionId;
  const data = await api(`/api/sessions/${sessionId}/results`);
  if (route.page !== 'result' || route.sessionId !== sessionId) return;
  resultReport = data;
  const summary = data.summary;
  appRoot.innerHTML = `
    <div class="panel-head"><div>
      <button class="btn outline sm" onclick="navigate('results')">← Danh sách kết quả</button>
      <div class="muted small" style="margin-top:10px">${esc(summary.class_name)} · ${esc(summary.quiz_title)}</div>
      <h2 style="margin:4px 0">Báo cáo phiên kiểm tra</h2>
      <div class="muted small">${esc(summary.started_at)}${summary.ended_at ? ' → ' + esc(summary.ended_at) : ''}</div>
    </div><span class="pill ${summary.status === 'completed' ? 'closed' : ''}">${summary.status === 'completed' ? 'Đã kết thúc' : 'Đang diễn ra'}</span></div>
    <div class="grid stats-grid">
      ${statCard('♙', 'Có trả lời / danh sách lớp', `${summary.participant_count} / ${summary.roster_count}`)}
      ${statCard('○', 'Chưa trả lời câu nào', summary.absent_count)}
      ${statCard('✓', 'Điểm trung bình toàn lớp / 10', summary.average_score.toFixed(2))}
      ${statCard('%', 'Tỷ lệ đúng / lượt trả lời', percentage(summary.accuracy))}
    </div>
    <div class="notice report-explanation">
      <strong>Điểm toàn bài / 10</strong> = số câu đúng ÷ tổng ${summary.question_count} câu × 10; câu chưa trả lời không có điểm.<br>
      <strong>Tỷ lệ đúng / đã trả lời</strong> = số câu đúng ÷ số câu đã trả lời × 100%; “—” khi chưa trả lời.<br>
      Danh sách lớp dựa trên thành viên được thêm trước khi phiên kết thúc và những người đã gửi đáp án.
      Tổng quan và thống kê câu hỏi luôn dùng toàn phiên; bộ lọc áp dụng cho bảng sinh viên và phần sinh viên trong file xuất.
    </div>
    <div class="panel">
      <div class="panel-head"><h2>Kết quả sinh viên</h2><div class="report-toolbar">
        <button class="btn primary sm" onclick="downloadReport('xlsx')">Xuất Excel (.xlsx)</button>
        <button class="btn outline sm" onclick="downloadReport('csv','students')">CSV sinh viên</button>
      </div></div>
      <div class="report-filters">
        <div><label for="report-mssv">Tìm MSSV</label><input id="report-mssv" class="field" type="search" placeholder="Nhập một phần MSSV…" oninput="renderReportStudents()"></div>
        <div><label for="report-participation">Mức độ trả lời</label><select id="report-participation" class="field" onchange="renderReportStudents()">
          <option value="all">Tất cả sinh viên</option><option value="none">Chưa trả lời câu nào</option>
          <option value="partial">Trả lời chưa đủ câu</option><option value="complete">Đã trả lời đủ câu</option>
        </select></div>
        <button class="btn secondary" onclick="resetReportFilters()">Xóa bộ lọc</button>
      </div>
      <div id="report-student-count" class="report-count" aria-live="polite"></div>
      <div id="report-students"></div>
    </div>
    <div class="panel report-section">
      <div class="panel-head"><h2>Thống kê câu hỏi và câu khó</h2><button class="btn outline sm" onclick="downloadReport('csv','questions')">CSV câu hỏi</button></div>
      <div class="report-difficulty"><label for="report-question-order">Sắp xếp</label>
        <select id="report-question-order" class="field" onchange="renderReportQuestions()"><option value="difficulty">Tỷ lệ đúng thấp nhất trước</option><option value="order">Theo thứ tự câu hỏi</option></select>
      </div>
      <p class="muted small">Đánh dấu câu khó khi dưới 50% lượt trả lời đúng. Câu chưa có lượt trả lời được để riêng ở cuối. Bấm số “Chưa trả lời” để xem danh sách theo câu.</p>
      <div id="report-questions"></div>
    </div>`;
  renderReportStudents();
  renderReportQuestions();
}

function reportFilters() {
  return {mssv: document.getElementById('report-mssv').value.trim(), participation: document.getElementById('report-participation').value};
}

function filteredReportStudents() {
  const filters = reportFilters();
  return resultReport.students.filter(student => student.mssv.toLowerCase().includes(filters.mssv.toLowerCase()) &&
    (filters.participation === 'all' || filters.participation === student.participation));
}

function renderReportStudents() {
  const students = filteredReportStudents();
  document.getElementById('report-student-count').textContent = `Hiển thị ${students.length} / ${resultReport.students.length} sinh viên`;
  document.getElementById('report-students').innerHTML = students.length ? table(
    ['MSSV', 'Họ tên', 'Đã trả lời', 'Đúng', 'Sai', 'Chưa trả lời', 'Tỷ lệ đúng / đã trả lời', 'Điểm / 10', ''],
    students.map(student => [esc(student.mssv), esc(student.name || '—'), nfmt(student.answered), nfmt(student.correct), nfmt(student.wrong),
      nfmt(student.unanswered), percentage(student.accuracy), `<span class="report-score">${student.score.toFixed(2)}</span>`,
      `<button class="btn outline sm" onclick="showStudent(${resultReport.summary.id},${student.student_id})">Chi tiết</button>`])
  ) : empty('Không có sinh viên phù hợp', 'Thử thay đổi MSSV hoặc mức độ trả lời.');
}

function resetReportFilters() {
  document.getElementById('report-mssv').value = '';
  document.getElementById('report-participation').value = 'all';
  renderReportStudents();
}

function renderReportQuestions() {
  const questions = [...resultReport.questions];
  if (document.getElementById('report-question-order').value === 'difficulty') {
    questions.sort((a, b) => (a.accuracy ?? Infinity) - (b.accuracy ?? Infinity) || a.question_number - b.question_number);
  }
  document.getElementById('report-questions').innerHTML = questions.length ? table(
    ['Câu', 'Nội dung', 'Đáp án', 'Đã trả lời', 'Đúng', 'Sai', 'Chưa trả lời', 'Tỷ lệ đúng', 'Đánh giá'],
    questions.map(question => [question.question_number, `<div class="report-question">${esc(question.question_text)}</div>`, esc(question.correct_answer),
      question.answered, question.correct, question.wrong,
      `<button class="report-link" onclick="showUnanswered(${question.id})" aria-label="Xem sinh viên chưa trả lời câu ${question.question_number}">${question.unanswered}</button>`,
      percentage(question.accuracy), question.accuracy == null ? '<span class="muted small">Chưa có dữ liệu</span>' :
        question.accuracy < 50 ? '<span class="badge bad">Câu khó</span>' : '<span class="badge">Từ 50% đúng</span>'])
  ) : empty('Chưa có câu hỏi', '');
}

function showUnanswered(questionId) {
  const question = resultReport.questions.find(item => item.id === questionId);
  const students = resultReport.students.filter(student => question.unanswered_student_ids.includes(student.student_id));
  document.getElementById('overlay').innerHTML = `
    <div class="modal-backdrop" onclick="if(event.target===this)closeModal()"><div class="modal report-modal" role="dialog" aria-modal="true" aria-label="Sinh viên chưa trả lời">
      <div class="panel-head"><h2>Chưa trả lời câu ${question.question_number} (${students.length})</h2><button class="btn outline sm" onclick="closeModal()">Đóng</button></div>
      <p class="report-question">${esc(question.question_text)}</p>
      ${students.length ? table(['MSSV', 'Họ tên'], students.map(student => [esc(student.mssv), esc(student.name || '—')])) : empty('Tất cả sinh viên đã trả lời câu này', '')}
    </div></div>`;
}

function downloadReport(format, section='students') {
  const params = new URLSearchParams({...reportFilters(), format, section});
  const link = document.createElement('a');
  link.href = `/api/sessions/${resultReport.summary.id}/results/export?${params}`;
  link.download = '';
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function showStudent(sessionId, studentId) {
  try {
    const rows = await api(`/api/sessions/${sessionId}/students/${studentId}`);
    const student = resultReport?.students.find(item => item.student_id === studentId);
    document.getElementById('overlay').innerHTML = `
      <div class="modal-backdrop" onclick="if(event.target===this)closeModal()"><div class="modal report-modal" role="dialog" aria-modal="true" aria-label="Chi tiết câu trả lời">
        <div class="panel-head"><h2>Chi tiết câu trả lời ${student ? '· ' + esc(student.mssv) : ''}</h2><button class="btn outline sm" onclick="closeModal()">Đóng</button></div>
        ${table(['Câu hỏi', 'Đáp án', 'Đáp án đúng', 'Kết quả'], rows.map(row => [
          `<div class="report-question">${row.question_number}. ${esc(row.question_text)}</div>`, esc(row.answer || '—'), esc(row.correct_answer),
          row.answer == null ? '<span class="muted">Chưa trả lời</span>' : `<span class="badge ${row.result === 'Dung' ? '' : 'bad'}">${row.result === 'Dung' ? 'Đúng' : 'Sai'}</span>`]))}
      </div></div>`;
  } catch (error) { toast(error.message); }
}
