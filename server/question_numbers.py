"""Display positions are independent of stored ordering keys and database IDs."""


def number_questions(ordered_rows):
    """Rows must be ordered by question_order, id within a single quiz."""
    return [{**row, "question_number": number}
            for number, row in enumerate(ordered_rows, 1)]


def question_position(cursor, quiz_id, question_id):
    cursor.execute("SELECT id FROM questions WHERE quiz_id=%s ORDER BY question_order,id", (quiz_id,))
    questions = number_questions(cursor.fetchall())
    return (next((q["question_number"] for q in questions if q["id"] == question_id), None),
            len(questions))
