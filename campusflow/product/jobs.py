"""Small persistent job ledger with bounded local execution (single API process)."""
import json
import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import BoundedSemaphore
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select, update

from campusflow.api.services import cp_sat_available
from . import database as db
from .catalog import ProductError, transaction

pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="campusflow")
capacity = BoundedSemaphore(2)


def now():
    return datetime.now(timezone.utc).isoformat()


def select_solver(request, count):
    if request.solver == "auto":
        solver = "cp-sat" if (count >= 50 or request.optimize) and cp_sat_available() else "csp"
    else:
        solver = request.solver
    if solver == "cp-sat" and not cp_sat_available():
        raise ProductError("CP-SAT is unavailable. Install the cp-sat extra.", 503)
    if request.optimize and solver != "cp-sat":
        raise ProductError("Weighted optimization requires CP-SAT. Choose CP-SAT or disable optimization.")
    return solver


def start(payload, name, scope):
    if not capacity.acquire(False):
        raise ProductError("Two jobs are already running. Retry when one finishes.", 503)
    identifier = uuid4().hex
    try:
        with transaction() as conn:
            conn.execute(db.jobs.insert().values(id=identifier, state="queued", name=name, scope=scope,
                solver=payload["solver"], created_at=now(), payload=payload))
        pool.submit(run, identifier, payload)
    except Exception:
        capacity.release()
        raise
    return identifier


def run(identifier, payload):
    started = perf_counter()
    try:
        with transaction() as conn:
            conn.execute(update(db.jobs).where(db.jobs.c.id == identifier).values(state="running"))
        try:
            completed = subprocess.run([sys.executable, "-m", "campusflow.product.worker"],
                input=json.dumps(payload), text=True, capture_output=True, check=True,
                timeout=payload["time_limit_seconds"] + 5)
            result = json.loads(completed.stdout)
        except subprocess.TimeoutExpired:
            result = {"status": "timeout", "lectures": [], "message": "Time limit reached; no complete schedule returned."}
        except Exception:
            logging.getLogger(__name__).exception("Product worker failed")
            result = {"status": "internal_error", "lectures": [], "message": "Generation failed. See server log."}
        with transaction() as conn:
            conn.execute(update(db.jobs).where(db.jobs.c.id == identifier).values(
                state=result["status"], result=result, duration_seconds=perf_counter() - started))
    finally:
        capacity.release()


def get(conn, identifier, full=False):
    row = conn.execute(select(db.jobs).where(db.jobs.c.id == identifier)).mappings().first()
    if not row:
        raise ProductError("Job not found", 404)
    result = dict(row)
    if not full:
        result.pop("payload")
    return result


def recover():
    with transaction() as conn:
        conn.execute(update(db.jobs).where(db.jobs.c.state.in_(["queued", "running"])).values(
            state="interrupted", result={"status": "interrupted", "message": "Server restarted. Submit again.", "lectures": []}))
