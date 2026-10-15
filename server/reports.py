"""Session reports and dependency-free CSV / Office Open XML exports."""
import csv
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree.ElementTree import Element, SubElement, tostring
from question_numbers import number_questions


def build_report(cursor, session_id):
    cursor.execute("""
        SELECT s.id,s.status,s.started_at,s.ended_at,s.class_id,s.quiz_id,
               c.class_name,q.title AS quiz_title
        FROM quiz_sessions s JOIN classes c ON c.id=s.class_id
        JOIN quizzes q ON q.id=s.quiz_id WHERE s.id=%s
    """, (session_id,))
    summary = cursor.fetchone()
    if not summary:
        return None
    # Membership at the end of the session (or now), plus all actual respondents.
    cursor.execute("""
        SELECT st.id AS student_id,st.mssv,st.name
        FROM students st WHERE st.id IN (
            SELECT cs.student_id FROM class_students cs WHERE cs.class_id=%s
                AND cs.joined_at <= COALESCE(%s,CURRENT_TIMESTAMP)
            UNION SELECT r.student_id FROM responses r WHERE r.session_id=%s
        ) ORDER BY st.mssv
    """, (summary["class_id"], summary["ended_at"], session_id))
    roster = cursor.fetchall()
    cursor.execute("""
        SELECT id,question_order,question_text,correct_answer
        FROM questions WHERE quiz_id=%s ORDER BY question_order,id
    """, (summary["quiz_id"],))
    questions = number_questions(cursor.fetchall())
    cursor.execute("""
        SELECT student_id,question_id,answer FROM responses WHERE session_id=%s
    """, (session_id,))
    answers = {(r["student_id"], r["question_id"]): r["answer"] for r in cursor.fetchall()}
    count = len(questions)
    students = []
    for st in roster:
        answered = sum((st["student_id"], q["id"]) in answers for q in questions)
        correct = sum(answers.get((st["student_id"], q["id"])) == q["correct_answer"] for q in questions)
        students.append({**st, "answered": answered, "correct": correct,
                         "wrong": answered-correct, "unanswered": count-answered,
                         "accuracy": round(correct*100/answered, 1) if answered else None,
                         "score": round(correct*10/count, 2) if count else 0,
                         "score_percent": round(correct*100/count, 1) if count else 0,
                         "participation": "none" if not answered else "complete" if answered == count else "partial"})
    for q in questions:
        given = [answers[(st["student_id"], q["id"])] for st in roster
                 if (st["student_id"], q["id"]) in answers]
        q.update(answered=len(given), correct=given.count(q["correct_answer"]),
                 wrong=len(given)-given.count(q["correct_answer"]),
                 unanswered=len(roster)-len(given),
                 accuracy=round(given.count(q["correct_answer"])*100/len(given), 1) if given else None,
                 unanswered_student_ids=[st["student_id"] for st in roster if (st["student_id"], q["id"]) not in answers],
                 options={a: given.count(a) for a in "ABCD"})
    total = sum(st["answered"] for st in students)
    correct = sum(st["correct"] for st in students)
    summary.update(question_count=count, roster_count=len(roster),
                   participant_count=sum(st["answered"] > 0 for st in students),
                   absent_count=sum(st["answered"] == 0 for st in students),
                   response_count=total, correct_count=correct,
                   accuracy=round(correct*100/total, 1) if total else None,
                   average_score=round(sum(st["score"] for st in students)/len(students), 2) if students else 0)
    for key in ("started_at", "ended_at"):
        summary[key] = str(summary[key]) if summary[key] else None
    return {"summary": summary, "students": students, "questions": questions}


def filter_students(report, mssv="", participation="all"):
    students = [st for st in report["students"] if mssv.casefold() in st["mssv"].casefold()]
    if participation != "all":
        students = [st for st in students if st["participation"] == participation]
    return students


def report_sheets(report, students):
    s = report["summary"]
    return [
        ("Tổng quan", [["Lớp", s["class_name"]], ["Bài kiểm tra", s["quiz_title"]],
                       ["Phiên", s["id"]], ["Bắt đầu", s["started_at"]], ["Kết thúc", s["ended_at"]],
                       ["Số câu", s["question_count"]], ["Sinh viên trong danh sách", s["roster_count"]],
                       ["Có trả lời", s["participant_count"]], ["Chưa trả lời câu nào", s["absent_count"]],
                       ["Điểm TB toàn danh sách / 10", s["average_score"]],
                       ["Tỷ lệ đúng trên lượt trả lời (%)", s["accuracy"]],
                       ["Cách tính", "Điểm = số đúng / tổng câu × 10. Tỷ lệ đúng = số đúng / số đã trả lời."],
                       ["Phạm vi", "Tổng quan và thống kê câu hỏi dùng toàn phiên; bảng sinh viên theo bộ lọc."]]),
        ("Sinh viên", [["MSSV", "Họ tên", "Đã trả lời", "Đúng", "Sai", "Chưa trả lời", "Tỷ lệ đúng / đã trả lời (%)", "Điểm toàn bài / 10"]]
         + [[st["mssv"], st["name"] or "", st["answered"], st["correct"], st["wrong"], st["unanswered"], st["accuracy"], st["score"]] for st in students]),
        ("Câu hỏi", [["Câu", "Nội dung", "Đáp án đúng", "Đã trả lời", "Đúng", "Sai", "Chưa trả lời", "Tỷ lệ đúng / đã trả lời (%)", "A", "B", "C", "D"]]
         + [[q["question_number"], q["question_text"], q["correct_answer"], q["answered"], q["correct"], q["wrong"], q["unanswered"], q["accuracy"], *[q["options"][a] for a in "ABCD"]] for q in report["questions"]]),
        ("Chưa tham gia", [["MSSV", "Họ tên"]] + [[st["mssv"], st["name"] or ""] for st in students if not st["answered"]]),
        ("Chưa trả lời theo câu", [["Câu", "MSSV", "Họ tên"]]
         + [[q["question_number"], st["mssv"], st["name"] or ""] for q in report["questions"] for st in students if st["student_id"] in q["unanswered_student_ids"]]),
    ]


def csv_bytes(rows):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    for row in rows:
        # Treat user-controlled spreadsheet formulas as text.
        writer.writerow(["'"+v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for v in row])
    return stream.getvalue().encode("utf-8-sig")


def xlsx_bytes(sheets):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    typesns = "http://schemas.openxmlformats.org/package/2006/content-types"
    clean = lambda value: "".join(c for c in str(value) if c in "\t\n\r" or ord(c) >= 32)[:32767]
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as archive:
        def write(path, root):
            archive.writestr(path, tostring(root, encoding="utf-8", xml_declaration=True))
        types = Element("Types", xmlns=typesns)
        SubElement(types, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
        SubElement(types, "Default", Extension="xml", ContentType="application/xml")
        SubElement(types, "Override", PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
        rootrels = Element("Relationships", xmlns=relns)
        SubElement(rootrels, "Relationship", Id="rId1", Type=office+"/officeDocument", Target="xl/workbook.xml")
        write("_rels/.rels", rootrels)
        workbook = Element("workbook", xmlns=ns)
        sheet_nodes = SubElement(workbook, "sheets")
        rels = Element("Relationships", xmlns=relns)
        for i, (name, rows) in enumerate(sheets, 1):
            SubElement(sheet_nodes, "sheet", name=name, sheetId=str(i), attrib={"{"+office+"}id": f"rId{i}"})
            SubElement(rels, "Relationship", Id=f"rId{i}", Type=office+"/worksheet", Target=f"worksheets/sheet{i}.xml")
            SubElement(types, "Override", PartName=f"/xl/worksheets/sheet{i}.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
            sheet = Element("worksheet", xmlns=ns)
            views = SubElement(sheet, "sheetViews")
            view = SubElement(views, "sheetView", workbookViewId="0")
            SubElement(view, "pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
            data = SubElement(sheet, "sheetData")
            for row in rows:
                node = SubElement(data, "row")
                for value in row:
                    if isinstance(value, (int, float)):
                        SubElement(SubElement(node, "c"), "v").text = str(value)
                    else:
                        cell = SubElement(node, "c", t="inlineStr")
                        SubElement(SubElement(cell, "is"), "t", attrib={"{http://www.w3.org/XML/1998/namespace}space": "preserve"}).text = clean(value) if value is not None else ""
            write(f"xl/worksheets/sheet{i}.xml", sheet)
        write("xl/workbook.xml", workbook)
        write("xl/_rels/workbook.xml.rels", rels)
        write("[Content_Types].xml", types)
    return out.getvalue()
