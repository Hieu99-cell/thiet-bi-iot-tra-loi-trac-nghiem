"""Exercise Flask routes with a disposable database; never touch classroom data.

SQLite handles the report SQL directly. The adapter translates MySQL locking /
upsert syntax for control-route behavior checks, not MariaDB lock semantics.
"""
import csv
import io
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from reports import csv_bytes


class Cursor:
    def __init__(self, connection):
        self.raw = connection.cursor()

    def execute(self, query, params=()):
        query = query.replace('%s', '?').replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE')
        if 'ON DUPLICATE KEY UPDATE revealed_question_id=VALUES(revealed_question_id)' in query:
            query = query.replace('ON DUPLICATE KEY UPDATE revealed_question_id=VALUES(revealed_question_id)',
                                  'ON CONFLICT(session_id) DO UPDATE SET revealed_question_id=excluded.revealed_question_id')
        query = query.replace('ON DUPLICATE KEY UPDATE mssv=VALUES(mssv)', 'ON CONFLICT(mssv) DO NOTHING')
        self.raw.execute(query, params)

    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]

    def close(self):
        self.raw.close()


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        pass


class ClassroomTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.create_function('IF', 3, lambda condition, yes, no: yes if condition else no)
        self.db.executescript('''
            CREATE TABLE classes(id INTEGER PRIMARY KEY,class_name TEXT,class_code TEXT);
            CREATE TABLE quizzes(id INTEGER PRIMARY KEY,class_id INTEGER,title TEXT);
            CREATE TABLE students(id INTEGER PRIMARY KEY,mssv TEXT UNIQUE,name TEXT);
            CREATE TABLE class_students(class_id INTEGER,student_id INTEGER,joined_at TEXT,PRIMARY KEY(class_id,student_id));
            CREATE TABLE questions(id INTEGER PRIMARY KEY,quiz_id INTEGER,question_order INTEGER,question_text TEXT,
                option_a TEXT,option_b TEXT,option_c TEXT,option_d TEXT,correct_answer TEXT);
            CREATE TABLE quiz_sessions(id INTEGER PRIMARY KEY,class_id INTEGER,quiz_id INTEGER,current_question_id INTEGER,
                status TEXT,accepting_answers INTEGER,started_at TEXT,ended_at TEXT);
            CREATE TABLE quiz_state(id INTEGER PRIMARY KEY,active_session_id INTEGER,current_question_id INTEGER,accepting_answers INTEGER);
            CREATE TABLE responses(id INTEGER PRIMARY KEY,session_id INTEGER,student_id INTEGER,question_id INTEGER,answer TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(session_id,student_id,question_id));
            CREATE TABLE presentation_state(session_id INTEGER PRIMARY KEY,revealed_question_id INTEGER);
            INSERT INTO classes VALUES(1,'Lớp IoT','IOT');
            INSERT INTO quizzes VALUES(1,1,'Mạng & thiết bị');
            INSERT INTO students VALUES(1,'0001','Nguyễn An'),(2,'0002','Bình'),(3,'0003','Châu'),(4,'0004','Thêm sau phiên'),(5,'0005','Người gửi ngoài danh sách');
            INSERT INTO class_students VALUES(1,1,'2026-01-01'),(1,2,'2026-01-01'),(1,3,'2026-01-01'),(1,4,'2026-12-31');
            INSERT INTO questions VALUES(11,1,1,'Wi-Fi là gì?','A & một','B','C','D','A'),(12,1,2,'Giao thức?','A','B','C','D','C');
            INSERT INTO quiz_sessions VALUES(1,1,1,11,'active',1,'2026-01-02','2026-01-03');
            INSERT INTO quiz_state VALUES(1,1,11,1);
            INSERT INTO responses(session_id,student_id,question_id,answer) VALUES(1,1,11,'A'),(1,2,11,'B'),(1,2,12,'A'),(1,5,11,'A');
        ''')
        server._device_state_seen.clear()
        self.patch = patch.object(server, 'db_cursor', side_effect=lambda dictionary=True: (Connection(self.db), Cursor(self.db)))
        self.patch.start()
        self.client = server.app.test_client()

    def tearDown(self):
        self.patch.stop()
        self.db.close()

    def get_report(self):
        response = self.client.get('/api/sessions/1/results')
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_scores_include_absent_students_and_keep_leading_zero_mssv(self):
        data = self.get_report()
        self.assertEqual(data['summary']['roster_count'], 4)
        self.assertEqual(data['summary']['participant_count'], 3)
        self.assertEqual(data['summary']['absent_count'], 1)
        students = {s['mssv']: s for s in data['students']}
        self.assertNotIn('0004', students)
        self.assertEqual(students['0001']['score'], 5)
        self.assertEqual(students['0001']['accuracy'], 100)
        self.assertEqual(students['0001']['unanswered'], 1)
        self.assertEqual(students['0003']['score'], 0)
        self.assertIsNone(students['0003']['accuracy'])
        self.assertEqual(students['0003']['participation'], 'none')

    def test_difficulty_and_unanswered_per_question(self):
        questions = self.get_report()['questions']
        self.assertEqual(questions[0]['accuracy'], 66.7)
        self.assertEqual(questions[1]['accuracy'], 0)
        self.assertEqual(questions[1]['unanswered_student_ids'], [1, 3, 5])
        self.assertEqual(questions[0]['options'], {'A': 2, 'B': 1, 'C': 0, 'D': 0})

    def test_empty_session_has_unknown_accuracy(self):
        self.db.execute('DELETE FROM responses')
        data = self.get_report()
        self.assertIsNone(data['summary']['accuracy'])
        self.assertTrue(all(q['accuracy'] is None for q in data['questions']))
        self.assertEqual(data['summary']['absent_count'], 3)

    def test_csv_filters_and_excel_utf8(self):
        response = self.client.get('/api/sessions/1/results/export?format=csv&mssv=0003&participation=none')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], '0003')
        self.assertEqual(rows[1][1], 'Châu')
        self.assertEqual(rows[1][-2:], ['', '0.0'])

    def test_xlsx_is_valid_package_with_text_mssv_and_filtered_sheets(self):
        response = self.client.get('/api/sessions/1/results/export?format=xlsx&participation=none')
        self.assertEqual(response.status_code, 200)
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertIsNone(archive.testzip())
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            self.assertEqual(len(workbook.findall('s:sheets/s:sheet', ns)), 5)
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
            rows = sheet.findall('s:sheetData/s:row', ns)
            self.assertEqual(len(rows), 2)
            first = rows[1].find('s:c', ns)
            self.assertEqual(first.attrib['t'], 'inlineStr')
            self.assertEqual(first.find('s:is/s:t', ns).text, '0003')

    def test_export_rejects_invalid_filters_and_missing_sessions(self):
        for query in ('format=pdf', 'participation=invalid', 'section=unknown'):
            self.assertEqual(self.client.get('/api/sessions/1/results/export?' + query).status_code, 400)
        self.assertEqual(self.client.get('/api/sessions/999/results').status_code, 404)
        self.assertEqual(self.client.get('/api/sessions/999/results/export').status_code, 404)

    def test_spreadsheet_formulas_stay_text(self):
        rows = list(csv.reader(io.StringIO(csv_bytes([['=1+1', '  @SUM(A1)', '0001']]).decode('utf-8-sig'))))
        self.assertEqual(rows[0], ["'=1+1", "'  @SUM(A1)", '0001'])
        self.db.execute("UPDATE students SET name='=1+1' WHERE id=1")
        response = self.client.get('/api/sessions/1/results/export?format=xlsx')
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertNotIn(b'<f>', archive.read('xl/worksheets/sheet2.xml'))

    def test_presentation_hides_answers_identities_and_statistics_before_reveal(self):
        response = self.client.get('/api/sessions/1/presentation')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        data = response.get_json()
        self.assertNotIn('correct_answer', data['current_question'])
        self.assertNotIn('responses', data)
        self.assertNotIn('questions', data)
        self.assertNotIn('options', data)
        self.assertNotIn('stats', data)
        self.assertNotIn('0001', response.get_data(as_text=True))
        self.assertEqual(data['answered'], 3)

    def test_reveal_persists_locks_answers_and_next_hides_again(self):
        result = self.client.post('/api/sessions/1/control', json={'action': 'reveal', 'question_id': 11})
        self.assertEqual(result.status_code, 200)
        for _ in range(2):
            data = self.client.get('/api/sessions/1/presentation').get_json()
            self.assertTrue(data['session']['answer_revealed'])
            self.assertEqual(data['current_question']['correct_answer'], 'A')
            self.assertFalse(data['session']['accepting_answers'])
        device = self.client.get('/device/state?mssv=0003').get_json()
        self.assertFalse(device['accepting_answers'])
        answer = self.client.post('/answer', json={'mssv': '0003', 'answer': 'A'})
        self.assertEqual(answer.status_code, 409)
        self.assertEqual(answer.get_json()['code'], 'ANSWERS_CLOSED')
        self.assertEqual(self.client.post('/api/sessions/1/control', json={'action': 'next'}).status_code, 200)
        data = self.client.get('/api/sessions/1/presentation').get_json()
        self.assertFalse(data['session']['answer_revealed'])
        self.assertTrue(data['session']['accepting_answers'])
        self.assertNotIn('correct_answer', data['current_question'])
        self.assertEqual(data['question_number'], 2)

    def test_hide_does_not_reopen_and_stale_reveal_is_rejected(self):
        self.client.post('/api/sessions/1/control', json={'action': 'reveal', 'question_id': 11})
        self.assertEqual(self.client.post('/api/sessions/1/control', json={'action': 'hide', 'question_id': 11}).status_code, 200)
        data = self.client.get('/api/sessions/1/presentation').get_json()
        self.assertNotIn('correct_answer', data['current_question'])
        self.assertFalse(data['session']['accepting_answers'])
        self.client.post('/api/sessions/1/control', json={'action': 'next'})
        response = self.client.post('/api/sessions/1/control', json={'action': 'reveal', 'question_id': 11})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post('/api/sessions/1/control', json={'action':'reveal'}).status_code, 400)

    def test_selecting_same_question_keeps_publication_and_lock(self):
        self.client.post('/api/sessions/1/control', json={'action': 'reveal', 'question_id': 11})
        self.assertEqual(self.client.post('/api/sessions/1/control', json={'action': 'go', 'question_id': 11}).status_code, 200)
        self.assertEqual(self.client.post('/quiz-state', json={'question_id': 11}).status_code, 200)
        data = self.client.get('/api/sessions/1/presentation').get_json()
        self.assertTrue(data['session']['answer_revealed'])
        self.assertFalse(data['session']['accepting_answers'])

    def test_question_details_distinguish_unanswered_from_wrong(self):
        rows = self.client.get('/api/sessions/1/students/1').get_json()
        self.assertEqual(rows[0]['result'], 'Dung')
        self.assertIsNone(rows[1]['result'])
        self.assertIsNone(rows[1]['answer'])

    def test_esp32_answer_contract_still_works(self):
        self.assertEqual(self.client.get('/device/state?mssv=0003').status_code, 200)
        answer = self.client.post('/answer', json={'mssv': '0003', 'answer': 'A'})
        self.assertEqual(answer.status_code, 200)
        repeated = self.client.post('/answer', json={'mssv': '0003', 'answer': 'B'})
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.get_json()['code'], 'ALREADY_ANSWERED')

    def test_device_uses_position_when_stored_orders_start_at_two(self):
        # Legacy/imported questions can have non-contiguous ordering values.
        self.db.execute('UPDATE questions SET question_order=2 WHERE id=11')
        self.db.execute('UPDATE questions SET question_order=9 WHERE id=12')
        device = self.client.get('/device/state?mssv=0001').get_json()
        presentation = self.client.get('/api/sessions/1/presentation').get_json()
        self.assertEqual(device['question_id'], presentation['current_question']['id'])
        self.assertEqual(device['question_number'], presentation['question_number'])
        self.assertEqual(device['question_number'], 1)
        self.assertEqual(self.client.get('/device/state?mssv=0001').headers['Cache-Control'], 'no-store')
        session = self.client.get('/api/sessions/1').get_json()
        self.assertEqual(session['session']['question_number'], 1)
        self.assertEqual(session['current_question']['question_number'], 1)
        self.assertEqual([q['question_number'] for q in session['questions']], [1, 2])
        overview = self.client.get('/api/overview').get_json()['active_session']
        self.assertEqual(overview['question_number'], 1)
        self.assertEqual(overview['question_count'], 2)
        self.assertEqual([q['question_number'] for q in self.get_report()['questions']], [1, 2])
        details = self.client.get('/api/sessions/1/students/1').get_json()
        self.assertEqual([q['question_number'] for q in details], [1, 2])
        self.client.post('/api/sessions/1/control', json={'action': 'next'})
        device = self.client.get('/device/state?mssv=0001').get_json()
        self.assertEqual(device['question_id'], 12)
        self.assertEqual(device['question_number'], 2)
        self.assertEqual(self.client.get('/api/sessions/1/presentation').get_json()['question_number'], 2)
        # Previous answers still belong to their database identity, not the label.
        response = self.client.post('/answer', json={'mssv':'0001','answer':'C'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['question_id'], 12)
        saved = self.db.execute('SELECT question_id,answer FROM responses WHERE student_id=1 ORDER BY question_id').fetchall()
        self.assertEqual([tuple(row) for row in saved], [(11, 'A'), (12, 'C')])

    def test_equal_order_keys_are_numbered_by_id_within_quiz(self):
        self.db.execute('UPDATE questions SET question_order=7')
        self.db.execute("INSERT INTO questions VALUES(10,2,1,'Other quiz','A','B','C','D','A')")
        for action, expected_id, expected_number in (('go', 11, 1), ('go', 12, 2), ('go', 11, 1)):
            self.client.post('/api/sessions/1/control', json={'action':action,'question_id':expected_id})
            device = self.client.get('/device/state?mssv=0001').get_json()
            self.assertEqual((device['question_id'], device['question_number']), (expected_id, expected_number))

    def test_curl_answer_from_same_mssv_is_a_real_existing_submission(self):
        self.db.execute('UPDATE questions SET question_order=2 WHERE id=11')
        self.client.get('/device/state?mssv=0003')
        self.assertEqual(self.client.post('/answer', json={'mssv':'0003','answer':'A'}).status_code, 200)
        self.client.get('/device/state?mssv=0003')
        response = self.client.post('/answer', json={'mssv':'0003','answer':'B'})
        self.assertEqual(response.get_json()['code'], 'ALREADY_ANSWERED')
        self.assertEqual(response.get_json()['answer'], 'A')
        device = self.client.get('/device/state?mssv=0003').get_json()
        self.assertEqual(device['question_number'], 1)

    def test_numbering_fix_does_not_rewrite_historical_order_keys_or_exports(self):
        self.db.execute('UPDATE questions SET question_order=2 WHERE id=11')
        self.db.execute('UPDATE questions SET question_order=9 WHERE id=12')
        self.client.get('/device/state?mssv=0001')
        response = self.client.get('/api/sessions/1/results/export?format=csv&section=questions')
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual([row[0] for row in rows[1:]], ['1','2'])
        stored = self.db.execute('SELECT question_order FROM questions ORDER BY question_order,id').fetchall()
        self.assertEqual([row[0] for row in stored], [2,9])

    def test_templates_and_assets_render(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        response = self.client.get('/sessions/1/present')
        self.assertEqual(response.status_code, 200)
        self.assertIn('presentationSessionId = 1', response.get_data(as_text=True))
        for filename in ('presentation.js', 'presentation.css', 'dashboard-reports.js', 'dashboard-reports.css', 'dashboard-live.js'):
            response = self.client.get('/static/' + filename)
            self.assertEqual(response.status_code, 200)
            response.close()


if __name__ == '__main__':
    unittest.main()
