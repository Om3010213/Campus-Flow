"""Isolated database/server used only by Playwright; never touches user data."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

if __name__ == "__main__":
    with TemporaryDirectory(prefix="campusflow-e2e-") as directory:
        os.environ["CAMPUSFLOW_DATABASE_URL"] = f"sqlite:///{Path(directory).as_posix()}/test.db"
        uvicorn.run("campusflow.api.main:app", host="127.0.0.1", port=8001, log_level="warning")
