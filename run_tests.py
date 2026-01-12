# run_tests.py

import pytest
import sys

if __name__ == "__main__":
    exit_code = pytest.main([
        "tests/",
        "--tb=short",
        "--cov",
        "--cov-report=term",      # ← Красивая таблица БЕЗ колонки Missing
    ])
    sys.exit(exit_code)