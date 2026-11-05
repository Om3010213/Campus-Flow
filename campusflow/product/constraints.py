"""Opt-in product rules and independent checks; standalone engine defaults stay intact."""
from collections import defaultdict
from datetime import time

from campusflow.api.schemas import ProblemInput, LectureInput
from campusflow.models import Weekday
from campusflow.scheduling import seconds
from campusflow.validation import validate_timetable
from campusflow.conflicts import detect_conflict
from campusflow.cp_sat_scheduler import DAY, _ticks


def eligible(policy, lecture) -> bool:
    room = next((r for r in policy["rooms"] if r["id"] == lecture.classroom), None)
    subject = next((s for s in policy["subjects"] if s["id"] == lecture.subject), None)
    batch = next((b for b in policy["batches"] if b["id"] == lecture.batch), None)
    return bool(room and subject and batch and room["kind"] == subject["kind"]
                and room["capacity"] >= batch["student_count"])


def accept(policy, lectures, fixed=None) -> bool:
    limits = {f["id"]: f["max_daily_minutes"] for f in policy["faculty"]}
    workload = defaultdict(float)
    for lecture in lectures:
        if not eligible(policy, lecture):
            return False
        if fixed and lecture.id in fixed and LectureInput.model_validate(lecture).model_dump(mode="json") != fixed[lecture.id]:
            return False
        workload[lecture.faculty, lecture.day] += (seconds(lecture.end) - seconds(lecture.start)) / 60
    return all(minutes <= limits.get(faculty, 0) for (faculty, _), minutes in workload.items())


def validate_snapshot(problem, policy, lectures) -> dict:
    domain = ProblemInput.model_validate(problem).to_domain()
    entries = [LectureInput.model_validate(l).to_domain() for l in lectures]
    errors = list(validate_timetable(domain, entries).errors)
    for lecture in entries:
        if not eligible(policy, lecture):
            errors.append(f"{lecture.id}: room {lecture.classroom} must match subject type and batch capacity.")
    limits = {f["id"]: f["max_daily_minutes"] for f in policy["faculty"]}
    workload = defaultdict(float)
    for lecture in entries:
        workload[lecture.faculty, lecture.day.value] += (seconds(lecture.end) - seconds(lecture.start)) / 60
    for (faculty, day), minutes in workload.items():
        if minutes > limits.get(faculty, 0):
            errors.append(f"Faculty {faculty} exceeds daily workload on {day}: {minutes:g} minutes.")
    for i, first in enumerate(entries):
        for second in entries[i + 1:]:
            conflict = detect_conflict(first, second)
            if conflict:
                for resource in conflict.resources:
                    errors.append(f"{resource.value.title()} {getattr(first, resource.value)} is already assigned to "
                                  f"{second.batch} on {second.day.value} from {second.start:%H:%M} to {second.end:%H:%M}.")
    return {"valid": not errors, "errors": errors,
            "missing": [e for e in errors if e.startswith("Missing session:")]}


def configure(policy, problem, *, optimize=False, fixed=None, original=None):
    """Build CP-SAT product constraints and documented integer-weight objectives."""
    def apply(model, assignments, requirements):
        from ortools.sat.python import cp_model
        days = list(Weekday)
        workload = defaultdict(list)
        repeats = defaultdict(list)
        costs = []
        faculty = {f["id"]: f for f in policy["faculty"]}
        for session_id, (start, choices) in assignments.items():
            req = requirements[session_id]
            mock = type("Assignment", (), {"subject": req.subject, "batch": req.batch})()
            for room, present in choices.items():
                mock.classroom = room
                if not eligible(policy, mock):
                    model.add(present == 0)
            if fixed and session_id in fixed:
                value = fixed[session_id]
                tick = days.index(Weekday(value["day"])) * DAY + _ticks(time.fromisoformat(value["start"]))
                model.add(start == tick)
                if value["classroom"] in choices:
                    model.add(choices[value["classroom"]] == 1)
                else:
                    model.add_bool_or([])
            if original and session_id in original:
                value = original[session_id]
                tick = days.index(Weekday(value["day"])) * DAY + _ticks(time.fromisoformat(value["start"]))
                same_time = model.new_bool_var(f"same_time:{session_id}")
                model.add(start == tick).only_enforce_if(same_time)
                model.add(start != tick).only_enforce_if(same_time.Not())
                unchanged = model.new_bool_var(f"unchanged:{session_id}")
                room_choice = choices.get(value["classroom"])
                if room_choice is None:
                    model.add(unchanged == 0)
                else:
                    model.add(unchanged <= same_time)
                    model.add(unchanged <= room_choice)
                    model.add(unchanged >= same_time + room_choice - 1)
                costs.append(1 - unchanged)
            for day in problem.working_days:
                index = days.index(day)
                on_day = model.new_bool_var(f"day:{session_id}:{index}")
                bounds = cp_model.Domain.from_intervals([[index * DAY, (index + 1) * DAY - 1]])
                model.add_linear_expression_in_domain(start, bounds).only_enforce_if(on_day)
                model.add_linear_expression_in_domain(start, bounds.complement()).only_enforce_if(on_day.Not())
                workload[req.faculty, day].append(req.duration_minutes * on_day)
                repeats[req.id, day].append(on_day)
            if optimize and not original:
                person = faculty[req.faculty]
                low, high = time.fromisoformat(person["preferred_start"]), time.fromisoformat(person["preferred_end"])
                intervals = [[i * DAY + _ticks(low), i * DAY + _ticks(high) - req.duration_minutes * 60_000_000]
                             for i in range(7) if _ticks(high) - _ticks(low) >= req.duration_minutes * 60_000_000]
                preferred = model.new_bool_var(f"preferred:{session_id}")
                if intervals:
                    domain = cp_model.Domain.from_intervals(intervals)
                    model.add_linear_expression_in_domain(start, domain).only_enforce_if(preferred)
                    model.add_linear_expression_in_domain(start, domain.complement()).only_enforce_if(preferred.Not())
                else:
                    model.add(preferred == 0)
                costs.append(10 * (1 - preferred))
        daily = []
        for (person, day), values in workload.items():
            total = model.new_int_var(0, 1440, f"load:{person}:{day}")
            model.add(total == sum(values))
            model.add(total <= faculty[person]["max_daily_minutes"])
            daily.append(total)
        if optimize and not original:
            for key, values in repeats.items():
                excess = model.new_int_var(0, len(values), f"repeat:{key}")
                model.add_max_equality(excess, [sum(values) - 1, 0])
                costs.append(30 * excess)
            if daily:
                peak = model.new_int_var(0, 1440, "peak_daily_minutes")
                model.add_max_equality(peak, daily)
                costs.append(peak)
        if costs:
            model.minimize(sum(costs))
    return apply
