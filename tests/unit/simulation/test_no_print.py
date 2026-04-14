"""AST scan: no print() calls in simulation production code."""

from __future__ import annotations

import ast
from pathlib import Path

SIMULATION_SERVICE_DIR = Path("backend/services/simulation")
SIMULATION_MODELS = Path("backend/models/simulation.py")
SIMULATION_ROUTES = Path("backend/routes/simulate.py")


def _find_print_calls(path: Path) -> list[str]:
    """Return list of 'file:line' where print() is called."""
    violations: list[str] = []
    for py_file in [path] if path.is_file() else path.rglob("*.py"):
        source = py_file.read_text()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(f"{py_file}:{node.lineno}")
    return violations


def test_no_print_in_simulation_service() -> None:
    """backend/services/simulation/ must not contain print()."""
    violations = _find_print_calls(SIMULATION_SERVICE_DIR)
    assert violations == [], f"print() found: {violations}"


def test_no_print_in_simulation_models() -> None:
    """backend/models/simulation.py must not contain print()."""
    violations = _find_print_calls(SIMULATION_MODELS)
    assert violations == [], f"print() found: {violations}"


def test_no_print_in_simulation_routes() -> None:
    """backend/routes/simulate.py must not contain print()."""
    violations = _find_print_calls(SIMULATION_ROUTES)
    assert violations == [], f"print() found: {violations}"
