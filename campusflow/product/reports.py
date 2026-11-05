"""Reports and exports derived exclusively from persisted versions."""
import csv
from collections import defaultdict
from datetime import time
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

from campusflow.api.schemas import ProblemInput
from campusflow.models import Weekday
from campusflow.scheduling import seconds, available


def quality_score(policy, lectures):
    """Same weighted objective as the opt-in CP model; lower is better."""
    faculty = {f["id"]: f for f in policy["faculty"]}
    daily, repeated = defaultdict(float), defaultdict(int)
    outside = 0
    for lecture in lectures:
        start, end = time.fromisoformat(lecture["start"]), time.fromisoformat(lecture["end"])
        person = faculty[lecture["faculty"]]
        outside += not (time.fromisoformat(person["preferred_start"]) <= start and end <= time.fromisoformat(person["preferred_end"]))
        daily[lecture["faculty"], lecture["day"]] += (seconds(end) - seconds(start)) / 60
        repeated[lecture["id"].rsplit(":", 1)[0], lecture["day"]] += 1
    repeats = sum(max(0, n - 1) for n in repeated.values())
    peak = max(daily.values(), default=0)
    return {"score": 10 * outside + 30 * repeats + peak, "outside_preferred": outside,
            "same_day_repeats": repeats, "peak_daily_minutes": peak,
            "weights": {"outside_preferred": 10, "same_day_repeats": 30, "peak_daily_minutes": 1}}


def report(version):
    faculty, rooms, daily = defaultdict(float), defaultdict(float), defaultdict(lambda: defaultdict(float))
    for lecture in version["lectures"]:
        minutes = (seconds(time.fromisoformat(lecture["end"])) - seconds(time.fromisoformat(lecture["start"]))) / 60
        faculty[lecture["faculty"]] += minutes
        rooms[lecture["classroom"]] += minutes
        daily[lecture["faculty"]][lecture["day"]] += minutes
    p = ProblemInput.model_validate(version["problem"]).to_domain()
    capacity = {room: sum((seconds(slot.end) - seconds(slot.start)) / 60
                         for day in p.working_days for slot in p.time_slots
                         if available(p.classroom_availability, room, day, slot.start, slot.end)) for room in p.classrooms}
    return {"quality": quality_score(version["policy"], version["lectures"]),
            "scheduled_sessions": len(version["lectures"]),
            "required_sessions": sum(r.weekly_sessions for r in p.requirements),
            "warnings": version["validation"]["errors"],
            "faculty": [{"id": f["id"], "name": f["name"], "minutes": faculty[f["id"]],
                         "daily_minutes": daily[f["id"]]} for f in version["policy"]["faculty"]],
            "rooms": [{"id": r["id"], "name": r["name"], "minutes": rooms[r["id"]],
                       "available_minutes": capacity.get(r["id"], 0),
                       "utilization_percent": round(100 * rooms[r["id"]] / capacity[r["id"]], 1) if capacity.get(r["id"]) else 0}
                      for r in version["policy"]["rooms"]]}


def rows(version):
    subjects = {r["id"]: r["name"] for r in version["policy"]["subjects"]}
    faculty = {r["id"]: r["name"] for r in version["policy"]["faculty"]}
    result = [["Day", "Start", "End", "Batch", "Subject", "Faculty", "Room"]]
    for l in sorted(version["lectures"], key=lambda l: (list(Weekday).index(Weekday(l["day"])), l["start"], l["batch"])):
        result.append([l["day"], l["start"][:5], l["end"][:5], l["batch"],
                       subjects.get(l["subject"], l["subject"]), faculty.get(l["faculty"], l["faculty"]), l["classroom"]])
    return result


def csv_export(version):
    out = StringIO(newline="")
    writer = csv.writer(out)
    # Avoid executing formulas when CSV is opened in spreadsheet applications.
    writer.writerows([["'" + cell if cell.startswith(("=", "+", "-", "@")) else cell for cell in row]
                      for row in rows(version)])
    return out.getvalue().encode("utf-8-sig")


def pdf_export(version):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    out = BytesIO()
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize, body.leading = 9, 12
    data = [[Paragraph(escape(cell), body) for cell in row] for row in rows(version)]
    table = Table(data, colWidths=[72, 42, 42, 80, 190, 165, 80], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ddf3ef")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
    ]))
    def page(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(32, 20, f"CampusFlow | {version['state'].upper()} | Page {doc.page}")
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=36)
    doc.build([Paragraph(escape(version["name"]), styles["Title"]),
               Paragraph(escape(f"{version['scope']} • {version['state']} • {len(version['lectures'])} sessions"), body),
               Spacer(1, 18), table], onFirstPage=page, onLaterPages=page)
    return out.getvalue()
