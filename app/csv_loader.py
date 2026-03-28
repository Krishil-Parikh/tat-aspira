"""CSV data loader for laboratory test configurations."""

import csv
import os
from typing import List
from app.models import TestConfig


def load_tests_from_csv(csv_path: str = None) -> List[TestConfig]:
    """Load test configurations from the Aspira Pathlab CSV file.
    
    The CSV has a header on row 1 (title) and column headers on row 2:
    #,state,city,test code,test name,mrp,group,specimen type,method,temp,test schedule,tat,action
    """
    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "Edos List  Aspira Pathlab  Diagnostics Limited.csv"
        )

    tests: List[TestConfig] = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Skip the first line (title), use second line as header
    if len(lines) < 3:
        return tests

    # Parse header
    reader = csv.reader(lines[1:])
    header = next(reader)  # Row 2: #,state,city,...

    # Clean header names
    header = [h.strip().lower() for h in header]

    for row in reader:
        if len(row) < 12:
            continue

        # Clean each cell
        row = [cell.strip() for cell in row]

        # Skip empty rows
        if not row[0] and not row[3] and not row[4]:
            continue

        try:
            mrp_val = float(row[5].replace(",", "")) if row[5] else 0.0
        except (ValueError, IndexError):
            mrp_val = 0.0

        test = TestConfig(
            row_number=int(row[0]) if row[0].isdigit() else 0,
            state=row[1] if len(row) > 1 else "",
            city=row[2] if len(row) > 2 else "",
            test_code=row[3] if len(row) > 3 else "",
            test_name=row[4] if len(row) > 4 else "",
            mrp=mrp_val,
            group=row[6] if len(row) > 6 else "",
            specimen_type=row[7] if len(row) > 7 else "",
            method=row[8] if len(row) > 8 else "",
            temp=row[9] if len(row) > 9 else "",
            test_schedule=row[10] if len(row) > 10 else "",
            tat=row[11] if len(row) > 11 else "",
            action=row[12] if len(row) > 12 else "",
        )

        # Only include tests with a test_code
        if test.test_code:
            tests.append(test)

    return tests


# Build a lookup dict for fast access
_tests_cache: List[TestConfig] = []
_tests_by_code: dict = {}


def get_all_tests() -> List[TestConfig]:
    """Get all test configs (cached)."""
    global _tests_cache, _tests_by_code
    if not _tests_cache:
        _tests_cache = load_tests_from_csv()
        _tests_by_code = {t.test_code: t for t in _tests_cache}
    return _tests_cache


def get_test_by_code(code: str) -> TestConfig | None:
    """Look up a test by its code."""
    get_all_tests()  # Ensure cache is loaded
    return _tests_by_code.get(code)


def search_tests(query: str) -> List[TestConfig]:
    """Search tests by name or code (case-insensitive)."""
    query = query.lower()
    return [
        t for t in get_all_tests()
        if query in t.test_code.lower() or query in t.test_name.lower()
    ]