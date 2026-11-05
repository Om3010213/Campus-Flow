"""Private subprocess entry point; request/response JSON travels over stdio."""

import sys

from .schemas import GenerateRequest
from .services import solve_in_worker


if __name__ == "__main__":
    request = GenerateRequest.model_validate_json(sys.stdin.read())
    print(solve_in_worker(request).model_dump_json())
