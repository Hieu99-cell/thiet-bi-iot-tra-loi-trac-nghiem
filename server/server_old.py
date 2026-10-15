from flask import Flask, request, jsonify, render_template
import mysql.connector

app = Flask(__name__)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="esp32app",
        password="",
        database="esp32_db"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# =========================================================
# ESP32 GỬI ĐÁP ÁN
# =========================================================

@app.route("/answer", methods=["POST"])
def receive_answer():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "message": "Khong co du lieu"
        }), 400

    mssv = str(data.get("mssv", "")).strip()
    answer = str(data.get("answer", "")).strip().upper()

    if not mssv:
        return jsonify({
            "status": "error",
            "message": "Thieu MSSV"
        }), 400

    if answer not in ["A", "B", "C", "D"]:
        return jsonify({
            "status": "error",
            "message": "Dap an khong hop le"
        }), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # -----------------------------------------
        # Lấy câu hỏi hiện tại
        # -----------------------------------------

        cursor.execute("""
            SELECT
                current_question_id,
                accepting_answers
            FROM quiz_state
            WHERE id = 1
        """)

        state = cursor.fetchone()

        if state is None:
            return jsonify({
                "status": "error",
                "message": "Khong tim thay quiz_state"
            }), 500

        if not state["accepting_answers"]:
            return jsonify({
                "status": "error",
                "message": "Hien tai khong nhan dap an"
            }), 403

        question_id = state["current_question_id"]

        if question_id is None:
            return jsonify({
                "status": "error",
                "message": "Chua co cau hoi hien tai"
            }), 400


        # -----------------------------------------
        # Thêm sinh viên nếu chưa có
        # -----------------------------------------

        cursor.execute("""
            INSERT IGNORE INTO students (mssv)
            VALUES (%s)
        """, (mssv,))


        # -----------------------------------------
        # Lấy student_id
        # -----------------------------------------

        cursor.execute("""
            SELECT id
            FROM students
            WHERE mssv = %s
        """, (mssv,))

        student = cursor.fetchone()

        student_id = student["id"]


        # -----------------------------------------
        # Lưu / cập nhật đáp án
        # -----------------------------------------

        cursor.execute("""
            INSERT INTO responses (
                student_id,
                question_id,
                answer
            )
            VALUES (%s, %s, %s)

            ON DUPLICATE KEY UPDATE
                answer = VALUES(answer),
                updated_at = CURRENT_TIMESTAMP
        """, (
            student_id,
            question_id,
            answer
        ))

        conn.commit()

        print(
            f"MSSV: {mssv} | "
            f"Cau: {question_id} | "
            f"Dap an: {answer}"
        )

        return jsonify({
            "status": "success",
            "mssv": mssv,
            "question_id": question_id,
            "answer": answer
        }), 200

    except Exception as e:

        conn.rollback()

        print("ERROR:", e)

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    finally:

        cursor.close()
        conn.close()


# =========================================================
# API DỮ LIỆU DASHBOARD
# =========================================================

@app.route("/api/dashboard")
def dashboard_data():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # -----------------------------------------
        # Trạng thái quiz
        # -----------------------------------------

        cursor.execute("""
            SELECT
                qs.current_question_id,
                qs.accepting_answers,
                q.question_text,
                q.correct_answer
            FROM quiz_state qs
            LEFT JOIN questions q
                ON q.id = qs.current_question_id
            WHERE qs.id = 1
        """)

        state = cursor.fetchone()


        # -----------------------------------------
        # Danh sách câu hỏi
        # -----------------------------------------

        cursor.execute("""
            SELECT
                id,
                question_text,
                correct_answer
            FROM questions
            ORDER BY id
        """)

        questions = cursor.fetchall()


        if state is None or state["current_question_id"] is None:

            return jsonify({
                "state": state,
                "questions": questions,

                "stats": {
                    "total": 0,
                    "correct": 0,
                    "wrong": 0,
                    "correct_percent": 0
                },

                "options": {
                    "A": 0,
                    "B": 0,
                    "C": 0,
                    "D": 0
                },

                "responses": []
            })


        question_id = state["current_question_id"]


        # -----------------------------------------
        # Thống kê đúng / sai
        # -----------------------------------------

        cursor.execute("""
            SELECT
                COUNT(r.id) AS total,

                COALESCE(
                    SUM(r.answer = q.correct_answer),
                    0
                ) AS correct,

                COALESCE(
                    SUM(r.answer <> q.correct_answer),
                    0
                ) AS wrong

            FROM questions q

            LEFT JOIN responses r
                ON r.question_id = q.id

            WHERE q.id = %s

            GROUP BY q.id
        """, (question_id,))

        stats = cursor.fetchone()

        if stats is None:
            stats = {
                "total": 0,
                "correct": 0,
                "wrong": 0
            }

        total = int(stats["total"] or 0)
        correct = int(stats["correct"] or 0)
        wrong = int(stats["wrong"] or 0)

        if total > 0:
            correct_percent = round(
                correct * 100 / total,
                2
            )
        else:
            correct_percent = 0


        # -----------------------------------------
        # Thống kê A/B/C/D
        # -----------------------------------------

        option_counts = {
            "A": 0,
            "B": 0,
            "C": 0,
            "D": 0
        }

        cursor.execute("""
            SELECT
                answer,
                COUNT(*) AS total
            FROM responses
            WHERE question_id = %s
            GROUP BY answer
        """, (question_id,))

        for row in cursor.fetchall():

            option_counts[row["answer"]] = int(
                row["total"]
            )


        # -----------------------------------------
        # Danh sách sinh viên trả lời
        # -----------------------------------------

        cursor.execute("""
            SELECT
                s.mssv,
                r.answer,
                q.correct_answer,

                IF(
                    r.answer = q.correct_answer,
                    'Dung',
                    'Sai'
                ) AS result,

                DATE_FORMAT(
                    r.updated_at,
                    '%%Y-%%m-%%d %%H:%%i:%%s'
                ) AS updated_at

            FROM responses r

            JOIN students s
                ON s.id = r.student_id

            JOIN questions q
                ON q.id = r.question_id

            WHERE r.question_id = %s

            ORDER BY r.updated_at DESC
        """, (question_id,))

        responses = cursor.fetchall()


        return jsonify({

            "state": {
                "current_question_id":
                    state["current_question_id"],

                "accepting_answers":
                    bool(state["accepting_answers"]),

                "question_text":
                    state["question_text"],

                "correct_answer":
                    state["correct_answer"]
            },

            "questions": questions,

            "stats": {
                "total": total,
                "correct": correct,
                "wrong": wrong,
                "correct_percent":
                    correct_percent
            },

            "options": option_counts,

            "responses": responses
        })

    finally:

        cursor.close()
        conn.close()


# =========================================================
# GIẢNG VIÊN CHỌN CÂU HIỆN TẠI
# =========================================================

@app.route("/quiz-state", methods=["POST"])
def update_quiz_state():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error"
        }), 400

    try:
        question_id = int(
            data.get("question_id")
        )

    except (TypeError, ValueError):

        return jsonify({
            "status": "error",
            "message": "question_id khong hop le"
        }), 400


    accepting = bool(
        data.get(
            "accepting_answers",
            False
        )
    )


    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # Kiểm tra câu hỏi có tồn tại không
        cursor.execute("""
            SELECT id
            FROM questions
            WHERE id = %s
        """, (question_id,))

        if cursor.fetchone() is None:

            return jsonify({
                "status": "error",
                "message": "Cau hoi khong ton tai"
            }), 404


        cursor.execute("""
            UPDATE quiz_state
            SET
                current_question_id = %s,
                accepting_answers = %s
            WHERE id = 1
        """, (
            question_id,
            accepting
        ))

        conn.commit()

        return jsonify({
            "status": "success",
            "question_id": question_id,
            "accepting_answers": accepting
        })

    finally:

        cursor.close()
        conn.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )from flask import Flask, request, jsonify, render_template
import mysql.connector

app = Flask(__name__)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="esp32app",
        password="",
        database="esp32_db"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# =========================================================
# ESP32 GỬI ĐÁP ÁN
# =========================================================

@app.route("/answer", methods=["POST"])
def receive_answer():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "message": "Khong co du lieu"
        }), 400

    mssv = str(data.get("mssv", "")).strip()
    answer = str(data.get("answer", "")).strip().upper()

    if not mssv:
        return jsonify({
            "status": "error",
            "message": "Thieu MSSV"
        }), 400

    if answer not in ["A", "B", "C", "D"]:
        return jsonify({
            "status": "error",
            "message": "Dap an khong hop le"
        }), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # -----------------------------------------
        # Lấy câu hỏi hiện tại
        # -----------------------------------------

        cursor.execute("""
            SELECT
                current_question_id,
                accepting_answers
            FROM quiz_state
            WHERE id = 1
        """)

        state = cursor.fetchone()

        if state is None:
            return jsonify({
                "status": "error",
                "message": "Khong tim thay quiz_state"
            }), 500

        if not state["accepting_answers"]:
            return jsonify({
                "status": "error",
                "message": "Hien tai khong nhan dap an"
            }), 403

        question_id = state["current_question_id"]

        if question_id is None:
            return jsonify({
                "status": "error",
                "message": "Chua co cau hoi hien tai"
            }), 400


        # -----------------------------------------
        # Thêm sinh viên nếu chưa có
        # -----------------------------------------

        cursor.execute("""
            INSERT IGNORE INTO students (mssv)
            VALUES (%s)
        """, (mssv,))


        # -----------------------------------------
        # Lấy student_id
        # -----------------------------------------

        cursor.execute("""
            SELECT id
            FROM students
            WHERE mssv = %s
        """, (mssv,))

        student = cursor.fetchone()

        student_id = student["id"]


        # -----------------------------------------
        # Lưu / cập nhật đáp án
        # -----------------------------------------

        cursor.execute("""
            INSERT INTO responses (
                student_id,
                question_id,
                answer
            )
            VALUES (%s, %s, %s)

            ON DUPLICATE KEY UPDATE
                answer = VALUES(answer),
                updated_at = CURRENT_TIMESTAMP
        """, (
            student_id,
            question_id,
            answer
        ))

        conn.commit()

        print(
            f"MSSV: {mssv} | "
            f"Cau: {question_id} | "
            f"Dap an: {answer}"
        )

        return jsonify({
            "status": "success",
            "mssv": mssv,
            "question_id": question_id,
            "answer": answer
        }), 200

    except Exception as e:

        conn.rollback()

        print("ERROR:", e)

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    finally:

        cursor.close()
        conn.close()


# =========================================================
# API DỮ LIỆU DASHBOARD
# =========================================================

@app.route("/api/dashboard")
def dashboard_data():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # -----------------------------------------
        # Trạng thái quiz
        # -----------------------------------------

        cursor.execute("""
            SELECT
                qs.current_question_id,
                qs.accepting_answers,
                q.question_text,
                q.correct_answer
            FROM quiz_state qs
            LEFT JOIN questions q
                ON q.id = qs.current_question_id
            WHERE qs.id = 1
        """)

        state = cursor.fetchone()


        # -----------------------------------------
        # Danh sách câu hỏi
        # -----------------------------------------

        cursor.execute("""
            SELECT
                id,
                question_text,
                correct_answer
            FROM questions
            ORDER BY id
        """)

        questions = cursor.fetchall()


        if state is None or state["current_question_id"] is None:

            return jsonify({
                "state": state,
                "questions": questions,

                "stats": {
                    "total": 0,
                    "correct": 0,
                    "wrong": 0,
                    "correct_percent": 0
                },

                "options": {
                    "A": 0,
                    "B": 0,
                    "C": 0,
                    "D": 0
                },

                "responses": []
            })


        question_id = state["current_question_id"]


        # -----------------------------------------
        # Thống kê đúng / sai
        # -----------------------------------------

        cursor.execute("""
            SELECT
                COUNT(r.id) AS total,

                COALESCE(
                    SUM(r.answer = q.correct_answer),
                    0
                ) AS correct,

                COALESCE(
                    SUM(r.answer <> q.correct_answer),
                    0
                ) AS wrong

            FROM questions q

            LEFT JOIN responses r
                ON r.question_id = q.id

            WHERE q.id = %s

            GROUP BY q.id
        """, (question_id,))

        stats = cursor.fetchone()

        if stats is None:
            stats = {
                "total": 0,
                "correct": 0,
                "wrong": 0
            }

        total = int(stats["total"] or 0)
        correct = int(stats["correct"] or 0)
        wrong = int(stats["wrong"] or 0)

        if total > 0:
            correct_percent = round(
                correct * 100 / total,
                2
            )
        else:
            correct_percent = 0


        # -----------------------------------------
        # Thống kê A/B/C/D
        # -----------------------------------------

        option_counts = {
            "A": 0,
            "B": 0,
            "C": 0,
            "D": 0
        }

        cursor.execute("""
            SELECT
                answer,
                COUNT(*) AS total
            FROM responses
            WHERE question_id = %s
            GROUP BY answer
        """, (question_id,))

        for row in cursor.fetchall():

            option_counts[row["answer"]] = int(
                row["total"]
            )


        # -----------------------------------------
        # Danh sách sinh viên trả lời
        # -----------------------------------------

        cursor.execute("""
            SELECT
                s.mssv,
                r.answer,
                q.correct_answer,

                IF(
                    r.answer = q.correct_answer,
                    'Dung',
                    'Sai'
                ) AS result,

                DATE_FORMAT(
                    r.updated_at,
                    '%%Y-%%m-%%d %%H:%%i:%%s'
                ) AS updated_at

            FROM responses r

            JOIN students s
                ON s.id = r.student_id

            JOIN questions q
                ON q.id = r.question_id

            WHERE r.question_id = %s

            ORDER BY r.updated_at DESC
        """, (question_id,))

        responses = cursor.fetchall()


        return jsonify({

            "state": {
                "current_question_id":
                    state["current_question_id"],

                "accepting_answers":
                    bool(state["accepting_answers"]),

                "question_text":
                    state["question_text"],

                "correct_answer":
                    state["correct_answer"]
            },

            "questions": questions,

            "stats": {
                "total": total,
                "correct": correct,
                "wrong": wrong,
                "correct_percent":
                    correct_percent
            },

            "options": option_counts,

            "responses": responses
        })

    finally:

        cursor.close()
        conn.close()


# =========================================================
# GIẢNG VIÊN CHỌN CÂU HIỆN TẠI
# =========================================================

@app.route("/quiz-state", methods=["POST"])
def update_quiz_state():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error"
        }), 400

    try:
        question_id = int(
            data.get("question_id")
        )

    except (TypeError, ValueError):

        return jsonify({
            "status": "error",
            "message": "question_id khong hop le"
        }), 400


    accepting = bool(
        data.get(
            "accepting_answers",
            False
        )
    )


    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:

        # Kiểm tra câu hỏi có tồn tại không
        cursor.execute("""
            SELECT id
            FROM questions
            WHERE id = %s
        """, (question_id,))

        if cursor.fetchone() is None:

            return jsonify({
                "status": "error",
                "message": "Cau hoi khong ton tai"
            }), 404


        cursor.execute("""
            UPDATE quiz_state
            SET
                current_question_id = %s,
                accepting_answers = %s
            WHERE id = 1
        """, (
            question_id,
            accepting
        ))

        conn.commit()

        return jsonify({
            "status": "success",
            "question_id": question_id,
            "accepting_answers": accepting
        })

    finally:

        cursor.close()
        conn.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
