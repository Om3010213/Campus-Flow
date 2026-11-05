"""Start locally: uvicorn campusflow.api.main:app --host 127.0.0.1 --port 8000."""

import logging
from contextlib import asynccontextmanager
from importlib.util import find_spec

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import router
from .schemas import TimetableResponse

@asynccontextmanager
async def lifespan(app):
    if find_spec("sqlalchemy"):
        from campusflow.product.database import migrate
        from campusflow.product.jobs import recover
        migrate()
        recover()
    yield


app = FastAPI(title="CampusFlow API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"],
)
app.include_router(router)

if find_spec("sqlalchemy"):
    from campusflow.product.routes import router as product_router
    from campusflow.product.catalog import ProductError
    app.include_router(product_router)

    @app.exception_handler(ProductError)
    async def product_error(request: Request, exc: ProductError):
        return JSONResponse(status_code=exc.code, content={"status": "error", "message": exc.message, "errors": exc.errors})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Never serialize raw input or exception contexts into API errors.
    errors = [f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()]
    result = TimetableResponse(status="invalid_input", message="Invalid request data.", errors=errors)
    return JSONResponse(status_code=422, content=result.model_dump(mode="json"))


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).error("Unhandled API error", exc_info=exc)
    result = TimetableResponse(status="internal_error", message="An internal error occurred.")
    return JSONResponse(status_code=500, content=result.model_dump(mode="json"))
