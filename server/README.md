# Classroom Response server

The Flask app now keeps the ESP32 contract unchanged: `POST /answer` with JSON fields `mssv` and `answer`. The server associates that answer with the active session and current question.

## Presentation and reporting upgrade (v3)

For an existing v2 installation, run only the following additive migration with
a database account that can create tables, then restart Flask:

```sh
mariadb -u DB_ADMIN_USER -p esp32_db < server/database/migration_v3.sql
python3 tools/run_server.py
```

Run these commands from the project root. `migration_v3.sql` can be run again;
it creates only `presentation_state` and does not change existing quiz data.
For a fresh legacy installation, apply v2 once first, then v3. **Do not run v2
again on an existing v2 database.**

### Classroom presentation

1. Start a quiz and select **Mở trình chiếu** on the live dashboard.
2. Move the new tab to the classroom display; select **Toàn màn hình**.
3. Keep the teacher dashboard on your own screen to move between questions.
4. Select **Công bố đáp án và khóa trả lời** to show the correct choice and
   response distribution. The server also rejects subsequent ESP32 answers.
5. **Ẩn đáp án trên trình chiếu** hides the answer without reopening submissions.
   Moving to another question hides its answer and enables submissions.

The audience endpoint omits student identities, correct/incorrect statistics,
answer distribution, and the correct choice until publication (only the latter
two are added after publication). Publication is saved in MariaDB and survives
refreshes and server restarts. The presentation updates every 1.5 seconds and
retries after a connection failure. The existing ESP32 firmware already supports
the `accepting_answers` field and `ANSWERS_CLOSED` response.

### Reports and exports

Open **Kết quả → Xem kết quả** to see:

- MSSV search and participation filters: all, no answers, partial, or complete.
- Score out of 10: correct answers / all quiz questions × 10.
- Accuracy: correct answers / submitted answers × 100%. A dash means no answers;
  a missing answer scores zero and is counted separately from a wrong answer.
- Question statistics with A–D counts in exports, lowest accuracy first, and
  a **Câu khó** marker below 50% correct among submitted answers. Questions with
  no responses have unknown difficulty and sort last.
- A per-question list of students who have not answered, opened by clicking
  the **Chưa trả lời** count.
- CSV student and question exports (UTF-8 BOM), and a real `.xlsx` workbook
  with five sheets: overview, students, questions, no participation, and
  unanswered questions by student. No extra Python packages are required.

Student filters also apply to the workbook's student, no-participation, and
unanswered sheets. Overview and question statistics always describe the entire
session. Export to XLSX to preserve leading zeroes in MSSV. CSV neutralizes
spreadsheet formulas; XLSX stores user-entered strings as text.

The roster is reconstructed from class memberships added no later than session
end (or now for active sessions), plus all actual respondents. Existing data has
no immutable membership snapshot: manually deleting old memberships can change
the historical list of students who never answered. No student is labelled
absent solely because they skipped an individual question.

### Question numbers on the website and OLED

Display numbers use the position in the quiz sorted by `question_order, id`,
starting at 1. Database IDs and stored ordering keys are not display numbers;
legacy rows with ordering keys 2 and 9 therefore appear as questions 1 and 2.
The live page, overview, projector, `/device/state`, reports, and exports all
use `question_number` for this position. Existing keys and answers are preserved.

After updating this fix, restart Flask and reload the dashboard with Ctrl+Shift+R.
No additional migration or firmware flash is required for the existing firmware,
which already displays `question_number` from the API and polls every second.
To inspect the state seen by an ESP32, run:

```sh
curl -sS 'http://127.0.0.1:5000/device/state?mssv=99000001'
```

An answer submitted with curl for the same MSSV, session, and question is also
that student's real saved answer. An ESP32 retry receives `ALREADY_ANSWERED`
and displays that saved choice; use a different MSSV or a new session to test
another submission independently.

### Verification

```sh
server/.venv/bin/python -m unittest discover -s server/tests -v
```

The tests use a disposable SQLite database and Flask's test client. They cover
scoring, skipped answers, roster inclusion, exports, presentation publication,
closed submissions, stale publication requests, and the existing ESP32 payload.
The test adapter translates MySQL locking/upsert syntax; MariaDB transaction
locking and a real projector/device still require verification on the host.

## One-time database upgrade

The current schema was inspected in MariaDB `esp32_db`. Before starting this version, take a database backup and run `database/migration_v2.sql` exactly once against that database. The migration creates backup copies of `students`, `questions`, `responses`, and `quiz_state`, adds the class/quiz/session tables, and archives existing questions and answers without deleting the legacy data. It leaves `answers_backup` untouched.

Example:

```sh
mariadb -u DB_ADMIN_USER -p esp32_db < server/database/migration_v2.sql
```

Run that from the project root, or change the path if you are already in `server/`. The configured `esp32app` account currently has data-only privileges, so use an account allowed to create and alter tables for this one-time migration.

## Start

```sh
cd server
. venv/bin/activate
python server.py
```

Database defaults match the existing installation. They can be overridden with `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`. The server listens on port 5000. Set `FLASK_DEBUG=1` only for local development.

## Main routes

- `GET /` — Vietnamese classroom dashboard
- `GET, POST /api/classes` — list and create classes
- `GET /api/classes/<id>` — class details, students, quizzes, and session history
- `POST /api/classes/<id>/quizzes` — create a quiz with ordered questions
- `GET, PUT /api/quizzes/<id>` — view or edit an unused quiz
- `POST /api/quizzes/<id>/sessions` — start a new quiz session
- `GET /api/sessions/<id>` — live question and response statistics
- `POST /api/sessions/<id>/control` — `previous`, `next`, `go`, `reveal`, `hide`, or `end`; publication requires the current `question_id`
- `GET /sessions/<id>/present` — classroom presentation page
- `GET /api/sessions/<id>/presentation` — audience data, with answers hidden until publication
- `GET /api/sessions/<id>/results` — session totals and student scores
- `GET /api/sessions/<id>/results/export?format=xlsx` — Excel workbook; `format=csv&section=students|questions|summary` for CSV, with optional `mssv` and `participation=all|none|partial|complete` filters
- `POST /answer` — ESP32 response endpoint, unchanged payload

Compatibility routes `/api/dashboard`, `/quiz-state`, and `/questions` remain registered for older browser integrations; the new dashboard uses the versioned class, quiz, and session APIs.
