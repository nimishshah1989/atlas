"""V3 Simulation Engine criterion callables referenced by docs/specs/v3-criteria.yaml.

Each function returns (passed: bool, evidence: str). Never raises — failure
becomes a False return with a readable reason. These run in-process under
.quality/checks.py, so keep them dependency-light (stdlib only).

Checks:
  check_simulation_no_float  → v3-04 (no ': float' annotations in simulation code)
  check_simulation_no_print  → v3-05 (no print() calls in simulation services)
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _iter_py_files(directory: Path) -> list[Path]:
    """Return all .py files under directory, skipping __pycache__."""
    result: list[Path] = []
    for p in directory.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        result.append(p)
    return sorted(result)


def _has_float_annotation(tree: ast.AST) -> list[str]:
    """Return list of node descriptions where float is used as a type annotation."""
    hits: list[str] = []
    for node in ast.walk(tree):
        # AnnAssign: x: float = ...
        if isinstance(node, ast.AnnAssign):
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "float":
                hits.append(f"line {node.lineno}: AnnAssign -> float")
        # Function argument annotations: def f(x: float)
        elif isinstance(node, ast.arg):
            if (
                node.annotation is not None
                and isinstance(node.annotation, ast.Name)
                and node.annotation.id == "float"
            ):
                hits.append(f"line {node.lineno}: arg annotation -> float")
        # Return annotations: def f() -> float
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            ret = node.returns
            if ret is not None and isinstance(ret, ast.Name) and ret.id == "float":
                hits.append(f"line {node.lineno}: return annotation -> float")
    return hits


def _has_print_calls(tree: ast.AST) -> list[str]:
    """Return list of line descriptions where print() is called."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                hits.append(f"line {node.lineno}: print()")
    return hits


def check_simulation_no_float() -> tuple[bool, str]:
    """v3-04: AST scan of simulation model and services for float annotations.

    Scans backend/models/simulation.py and all .py files in
    backend/services/simulation/. Returns (True, evidence) if zero float
    annotations found.
    """
    scan_targets: list[Path] = []

    model_file = ROOT / "backend" / "models" / "simulation.py"
    if model_file.exists():
        scan_targets.append(model_file)
    else:
        return False, "backend/models/simulation.py not found"

    services_dir = ROOT / "backend" / "services" / "simulation"
    if services_dir.exists():
        scan_targets.extend(_iter_py_files(services_dir))
    else:
        return False, "backend/services/simulation/ directory not found"

    offenders: list[str] = []
    for path in scan_targets:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return False, f"syntax error in {path.relative_to(ROOT)}: {exc}"
        except OSError as exc:
            return False, f"read error in {path.relative_to(ROOT)}: {exc}"

        hits = _has_float_annotation(tree)
        for hit in hits:
            rel = path.relative_to(ROOT)
            offenders.append(f"{rel}: {hit}")

    if offenders:
        sample = "; ".join(offenders[:3])
        return False, f"{len(offenders)} float annotation(s): {sample}"

    return True, f"0 float annotations across {len(scan_targets)} simulation files"


def check_simulation_no_print() -> tuple[bool, str]:
    """v3-05: AST scan of backend/services/simulation/ for print() calls.

    Returns (True, evidence) if zero print() calls found in production services.
    """
    services_dir = ROOT / "backend" / "services" / "simulation"
    if not services_dir.exists():
        return False, "backend/services/simulation/ directory not found"

    py_files = _iter_py_files(services_dir)
    if not py_files:
        return False, "backend/services/simulation/ contains no .py files"

    offenders: list[str] = []
    for path in py_files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return False, f"syntax error in {path.relative_to(ROOT)}: {exc}"
        except OSError as exc:
            return False, f"read error in {path.relative_to(ROOT)}: {exc}"

        hits = _has_print_calls(tree)
        for hit in hits:
            rel = path.relative_to(ROOT)
            offenders.append(f"{rel}: {hit}")

    if offenders:
        sample = "; ".join(offenders[:3])
        return False, f"{len(offenders)} print() call(s): {sample}"

    return True, f"0 print() calls across {len(py_files)} simulation service files"
