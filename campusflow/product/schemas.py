from datetime import time
from typing import Literal
from pydantic import Field, model_validator
from campusflow.api.schemas import Schema, Name, AvailabilityInput, SlotInput, LectureInput
from campusflow.models import Weekday


class FacultyRecord(Schema):
    id: Name
    name: Name
    department: Name
    subject_ids: list[Name] = Field(default_factory=list, max_length=100)
    availability: list[AvailabilityInput] = Field(default_factory=list, max_length=96)
    restricted: bool = False
    preferred_start: time = time(9)
    preferred_end: time = time(16)
    max_daily_minutes: int = Field(default=360, gt=0, le=1440, strict=True)

    @model_validator(mode="after")
    def hours(self):
        SlotInput(start=self.preferred_start, end=self.preferred_end)
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("Assigned subjects must be unique")
        return self


class SubjectRecord(Schema):
    id: Name
    name: Name
    department: Name
    semester: int = Field(ge=1, le=12, strict=True)
    weekly_sessions: int = Field(default=3, ge=1, le=30, strict=True)
    duration_minutes: int = Field(default=60, ge=1, le=720, strict=True)
    kind: Literal["theory", "lab"] = "theory"


class RoomRecord(Schema):
    id: Name
    name: Name
    kind: Literal["theory", "lab"] = "theory"
    capacity: int = Field(ge=1, le=2000, strict=True)
    availability: list[AvailabilityInput] = Field(default_factory=list, max_length=96)
    restricted: bool = False


class BatchRecord(Schema):
    id: Name
    department: Name
    semester: int = Field(ge=1, le=12, strict=True)
    division: Name
    student_count: int = Field(ge=1, le=2000, strict=True)


class RequirementRecord(Schema):
    id: Name
    subject_id: Name
    faculty_id: Name
    batch_id: Name
    weekly_sessions: int = Field(ge=1, le=30, strict=True)
    duration_minutes: int = Field(ge=1, le=720, strict=True)


class AcademicSettings(Schema):
    working_days: list[Weekday] = Field(default_factory=lambda: list(Weekday)[:6], min_length=1, max_length=7)
    start: time = time(9)
    end: time = time(16)
    slot_minutes: int = Field(default=60, ge=5, le=240, strict=True)
    breaks: list[SlotInput] = Field(default_factory=lambda: [SlotInput(start=time(12), end=time(13))], max_length=10)

    @model_validator(mode="after")
    def valid(self):
        SlotInput(start=self.start, end=self.end)
        if len(set(self.working_days)) != len(self.working_days):
            raise ValueError("Working days must be unique")
        ordered = sorted(self.breaks, key=lambda x: x.start)
        if any(b.start < self.start or b.end > self.end for b in ordered):
            raise ValueError("Breaks must be inside working hours")
        if any(a.end > b.start for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Breaks must not overlap")
        return self


class JobRequest(Schema):
    name: Name = "Weekly timetable"
    scope: Name = "College"
    solver: Literal["auto", "csp", "cp-sat"] = "auto"
    time_limit_seconds: float = Field(default=15, gt=0, le=30, allow_inf_nan=False)
    optimize: bool = False


class EditRequest(Schema):
    revision: int = Field(ge=1)
    lectures: list[LectureInput] = Field(max_length=500)


class RevisionRequest(Schema):
    revision: int = Field(ge=1)


class RescheduleRequest(Schema):
    faculty_id: Name
    day: Weekday
    time_limit_seconds: float = Field(default=15, gt=0, le=30)


RECORDS = {"faculty": FacultyRecord, "subjects": SubjectRecord, "rooms": RoomRecord,
           "batches": BatchRecord, "requirements": RequirementRecord}
