from flask import Flask, request, jsonify
import mysql.connector

app = Flask(__name__)


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="esp32app",
        password="",
        database="esp32_db"
    )


@app.route("/answer", methods=["POST"])
def receive_answer():

    # =========================
    # 1. NHẬN DỮ LIỆU ESP32
    # =========================

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

        # =========================
        # 2. KIỂM TRA CÂU HIỆN TẠI
        # =========================

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


        # =========================
        # 3. THÊM SINH VIÊN NẾU CHƯA CÓ
        # =========================

        cursor.execute("""
            INSERT INTO students (mssv)
            VALUES (%s)
            ON DUPLICATE KEY UPDATE
                mssv = VALUES(mssv)
        """, (mssv,))


        # =========================
        # 4. LẤY student_id
        # =========================

        cursor.execute("""
            SELECT id
            FROM students
            WHERE mssv = %s
        """, (mssv,))

        student = cursor.fetchone()

        student_id = student["id"]


        # =========================
        # 5. LƯU ĐÁP ÁN
        # =========================

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


app.run(
    host="0.0.0.0",
    port=5000,
    debug=True
)

