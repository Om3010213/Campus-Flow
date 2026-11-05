"""Benchmark feasibility vs weighted optimization on a temporary seeded catalog."""
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from .database import engine_for, migrate
from .catalog import snapshot
from .seed import seed
from .constraints import validate_snapshot
from .reports import quality_score


def main():
    results = []
    with TemporaryDirectory() as directory:
        engine = engine_for(f"sqlite:///{Path(directory).as_posix()}/benchmark.db")
        migrate(engine)
        with engine.begin() as conn:
            seed(conn)
            base = snapshot(conn)
        for optimize in (False, True):
            payload = {**base, "solver": "cp-sat", "time_limit_seconds": 15, "optimize": optimize}
            started = perf_counter()
            try:
                output = subprocess.run([sys.executable, "-m", "campusflow.product.worker"],
                    input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=20)
                result = json.loads(output.stdout)
            except subprocess.TimeoutExpired:
                result = {"status": "timeout", "lectures": [], "optimal": False}
            row = {"optimize": optimize, "status": result["status"], "generation_seconds": perf_counter() - started,
                   "optimal": result["optimal"], "scheduled_sessions": len(result["lectures"])}
            if result["status"] == "success":
                started = perf_counter()
                checked = validate_snapshot(base["problem"], base["policy"], result["lectures"])
                row.update(validation_seconds=perf_counter() - started, valid=checked["valid"],
                           quality=quality_score(base["policy"], result["lectures"]))
            results.append(row)
            print(json.dumps(row), flush=True)
        engine.dispose()
    destination = Path("benchmarks/product_optimization.json")
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"note": "Single local run per mode, 16 sessions, 15-second solver limit; scores are comparable only for complete valid schedules.", "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
