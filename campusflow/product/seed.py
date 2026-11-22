"""Explicit, non-destructive fictional demonstration catalog."""
from sqlalchemy import select
from . import database as db
from .catalog import save_record, save_settings, transaction, ProductError


def seed(conn):
    from campusflow.auth.onboarding_tables import institutions
    from campusflow.tenancy import institution_id
    kind = conn.execute(select(institutions.c.institution_type).where(institutions.c.institution_id == institution_id())).scalar_one()
    if kind == "SCHOOL":
        return seed_school(conn)
    if any(conn.execute(select(t.c.id).limit(1)).first() for t in db.TABLES.values()):
        raise ProductError("Demo data can only be loaded into an empty catalog.", 409)
    for code, name, kind, duration in [("CS201", "Data Structures", "theory", 60),
                                      ("MA201", "Discrete Mathematics", "theory", 60),
                                      ("CS205L", "Database Lab", "lab", 120)]:
        save_record(conn, "subjects", {"id": code, "name": name, "department": "Computer Science", "semester": 3,
            "weekly_sessions": 2, "duration_minutes": duration, "kind": kind})
    for code, name, subjects in [("F101", "Dr. Asha Mehta", ["CS201"]),
                                 ("F102", "Dr. Vikram Rao", ["MA201", "CS201"]),
                                 ("F103", "Dr. Nisha Shah", ["CS205L"])]:
        save_record(conn, "faculty", {"id": code, "name": name, "department": "Computer Science",
            "subject_ids": subjects, "max_daily_minutes": 240, "preferred_start": "09:00", "preferred_end": "13:00"})
    for code, kind, capacity in [("C101", "theory", 60), ("C102", "theory", 60), ("LAB1", "lab", 60)]:
        save_record(conn, "rooms", {"id": code, "name": "Computing Lab" if kind == "lab" else f"Classroom {code}",
                                    "kind": kind, "capacity": capacity})
    for division in ("A", "B"):
        batch = f"CSE-3{division}"
        save_record(conn, "batches", {"id": batch, "department": "Computer Science", "semester": 3,
                                      "division": division, "student_count": 48})
        for subject, faculty, duration, count in [("CS201", "F101", 60, 3), ("MA201", "F102", 60, 3), ("CS205L", "F103", 120, 2)]:
            save_record(conn, "requirements", {"id": f"{subject}-{division}", "subject_id": subject,
                "faculty_id": faculty, "batch_id": batch, "weekly_sessions": count, "duration_minutes": duration})
    save_settings(conn, {"working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
                         "start": "09:00", "end": "16:00", "slot_minutes": 60,
                         "breaks": [{"start": "12:00", "end": "13:00"}]})


def seed_school(conn):
    if any(conn.execute(select(t.c.id).limit(1)).first() for t in db.TABLES.values()):
        raise ProductError("Demo data can only be loaded into an empty catalog.",409)
    save_settings(conn,{"working_days":["Monday","Tuesday","Wednesday","Thursday","Friday"],"start":"09:00","end":"14:00","slot_minutes":40,
        "breaks":[{"start":"10:20","end":"10:40"},{"start":"12:00","end":"12:40"}]})
    for code,name,kind,duration in [("MATH","Mathematics","theory",40),("ENG","English","theory",40),("SCI","Science practical","lab",80),("ACT","Activity","activity",40)]:
        save_record(conn,"subjects",{"id":code,"name":name,"department":"School","semester":7,"kind":kind,"duration_minutes":duration})
        save_record(conn,"faculty",{"id":"T-"+code,"name":"Teacher "+name,"department":"School","subject_ids":[code]})
    for code,kind in [("R1","theory"),("R2","theory"),("LAB","lab")]:
        save_record(conn,"rooms",{"id":code,"name":code,"kind":kind,"capacity":40})
    for section in ("A","B"):
        batch="7-"+section
        save_record(conn,"batches",{"id":batch,"department":"School","semester":7,"division":section,"class_number":7,"class_teacher_id":"T-MATH","student_count":30})
        for code,count,duration in [("MATH",3,40),("ENG",2,40),("SCI",1,80),("ACT",1,40)]:
            save_record(conn,"requirements",{"id":code+"-"+section,"subject_id":code,"faculty_id":"T-"+code,"batch_id":batch,"weekly_sessions":count,"duration_minutes":duration})


if __name__ == "__main__":
    db.migrate()
    with transaction() as conn:
        seed(conn)
    print("Fictional academic catalog seeded. No timetable results are pre-generated.")
