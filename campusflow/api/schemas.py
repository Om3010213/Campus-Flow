"""HTTP schemas delegate academic validation to the existing domain models."""

from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from campusflow.models import Lecture, Weekday
from campusflow.scheduling import Availability, Faculty, LectureRequirement, SchedulingProblem, TimeSlot

Solver = Literal["csp", "cp-sat"]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class FacultyInput(Schema):
    name: Name
    subjects: list[Name] = Field(max_length=100)


class SlotInput(Schema):
    start: time
    end: time

    @model_validator(mode="after")
    def valid_interval(self):
        TimeSlot(self.start, self.end)
        return self


class AvailabilityInput(SlotInput):
    day: Weekday


class RequirementInput(Schema):
    id: Name
    subject: Name
    faculty: Name
    batch: Name
    weekly_sessions: int = Field(strict=True, gt=0, le=500)
    duration_minutes: int = Field(strict=True, gt=0, le=1439)


class ProblemInput(Schema):
    faculty: list[FacultyInput] = Field(max_length=200)
    batches: list[Name] = Field(max_length=100)
    classrooms: list[Name] = Field(max_length=50)
    working_days: list[Weekday] = Field(max_length=7)
    time_slots: list[SlotInput] = Field(max_length=48)
    requirements: list[RequirementInput] = Field(max_length=500)
    faculty_availability: dict[Name, list[AvailabilityInput]] = Field(default_factory=dict, max_length=200)
    classroom_availability: dict[Name, list[AvailabilityInput]] = Field(default_factory=dict, max_length=50)

    def to_domain(self) -> SchedulingProblem:
        return SchedulingProblem(
            faculty=tuple(Faculty(**f.model_dump()) for f in self.faculty),
            batches=tuple(self.batches), classrooms=tuple(self.classrooms),
            working_days=tuple(self.working_days),
            time_slots=tuple(TimeSlot(**s.model_dump()) for s in self.time_slots),
            requirements=tuple(LectureRequirement(**r.model_dump()) for r in self.requirements),
            faculty_availability={key: tuple(Availability(**w.model_dump()) for w in windows)
                                  for key, windows in self.faculty_availability.items()},
            classroom_availability={key: tuple(Availability(**w.model_dump()) for w in windows)
                                    for key, windows in self.classroom_availability.items()},
        )

    @model_validator(mode="after")
    def valid_problem(self):
        if sum(r.weekly_sessions for r in self.requirements) > 500:
            raise ValueError("API supports at most 500 required sessions")
        if any(len(windows) > 96 for mapping in (self.faculty_availability, self.classroom_availability)
               for windows in mapping.values()):
            raise ValueError("At most 96 availability windows per resource")
        self.to_domain()
        return self


class LectureInput(SlotInput):
    id: str = Field(min_length=1, max_length=210)
    subject: Name
    faculty: Name
    classroom: Name
    batch: Name
    day: Weekday

    def to_domain(self) -> Lecture:
        return Lecture(**self.model_dump())


class GenerateRequest(Schema):
    problem: ProblemInput
    solver: Solver = "csp"
    time_limit_seconds: float = Field(default=15, gt=0, le=30, allow_inf_nan=False)


class ValidateRequest(Schema):
    problem: ProblemInput
    lectures: list[LectureInput] = Field(max_length=500)


class ValidationOutput(Schema):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class TimetableResponse(Schema):
    status: Literal["success", "invalid_input", "infeasible", "timeout", "internal_error",
                    "unavailable", "busy", "valid", "invalid"]
    solver: Solver | None = None
    lectures: list[LectureInput] = Field(default_factory=list)
    validation: ValidationOutput | None = None
    message: str = ""
    errors: list[str] = Field(default_factory=list)
