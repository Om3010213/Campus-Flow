from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from . import services
from .schemas import GenerateRequest, TimetableResponse, ValidateRequest

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict:
    from campusflow.product.database import database, schema_versions

    response.headers["Cache-Control"] = "no-store"
    try:
        with database().connect() as conn:
            if conn.scalar(select(schema_versions.c.version).where(schema_versions.c.version == 6)):
                return {"status": "ok"}
    except SQLAlchemyError:
        pass
    response.status_code = 503
    return {"status": "unavailable"}


@router.get("/solvers")
def solvers() -> dict:
    return {"status": "success", "solvers": [
        {"name": "csp", "available": True},
        {"name": "cp-sat", "available": services.cp_sat_available()},
    ]}


@router.post("/timetables/generate", response_model=TimetableResponse)
def generate(request: GenerateRequest, response: Response) -> TimetableResponse:
    result = services.generate(request)
    response.status_code = {"timeout": 504, "unavailable": 503, "busy": 503,
                            "internal_error": 500}.get(result.status, 200)
    return result


@router.post("/timetables/validate", response_model=TimetableResponse)
def validate(request: ValidateRequest) -> TimetableResponse:
    return services.validate(request)
