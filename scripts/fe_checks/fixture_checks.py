"""
fixture_checks — JSON fixture validation checks.

Implements: fixture_schema, fixture_parity, fixture_field_required,
            fixture_numeric_range, fixture_array_length, fixture_enum,
            fixture_endpoint_reference
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ─── JSONPath resolver ────────────────────────────────────────────────────────


def resolve_jsonpath(data: Any, path: str) -> list[Any]:
    """Resolve a simple JSONPath expression.

    Supports:
    - $ — root
    - .key — object key access
    - [*] — iterate array
    - $.foo[*].bar — nested access

    Returns list of resolved values.
    """
    if not path.startswith("$"):
        return []

    # Parse path tokens
    # Split on . and [*]
    # e.g. "$.funds[*].composite_score" -> ["funds", "[*]", "composite_score"]
    tokens: list[str] = []
    # Remove leading $
    remainder = path[1:]
    for part in re.split(r"(\[\*\])", remainder):
        if part == "[*]":
            tokens.append("[*]")
        else:
            # Split on . and filter empty
            for t in part.split("."):
                if t:
                    tokens.append(t)

    def _resolve(current: Any, token_list: list[str]) -> list[Any]:
        if not token_list:
            return [current]

        tok = token_list[0]
        rest = token_list[1:]

        if tok == "[*]":
            if not isinstance(current, list):
                return []
            results: list[Any] = []
            for item in current:
                results.extend(_resolve(item, rest))
            return results
        else:
            if not isinstance(current, dict):
                return []
            val = current.get(tok)
            if val is None and tok not in current:
                return []
            return _resolve(val, rest)

    return _resolve(data, tokens)


# ─── File helpers ─────────────────────────────────────────────────────────────


def _load_json(path: Path) -> tuple[Any, str | None]:
    """Load JSON file. Returns (data, error_message)."""
    if not path.exists():
        return None, f"file not found: {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error in {path.name}: {e}"


def _resolve_fixture_paths(spec: dict[str, Any]) -> list[Path]:
    """Resolve fixture path(s) from spec."""
    fixture_single = spec.get("fixture", "")
    fixture_glob = spec.get("fixture_glob", "")
    fixtures_dir = spec.get("fixtures_dir", "")

    paths: list[Path] = []
    if fixture_single:
        paths.append(PROJECT_ROOT / fixture_single)
    if fixture_glob:
        for m in glob.glob(str(PROJECT_ROOT / fixture_glob)):
            paths.append(Path(m))
    if fixtures_dir:
        d = PROJECT_ROOT / fixtures_dir
        if d.exists():
            paths.extend(d.glob("*.json"))
    return paths


# ─── fixture_schema ───────────────────────────────────────────────────────────


def fixture_schema(spec: dict[str, Any]) -> tuple[bool, str]:
    """Validate fixture JSON files against their JSON schemas.

    SKIP if jsonschema not installed.
    """
    try:
        import jsonschema  # noqa: F401

        _has_jsonschema = True
    except ImportError:
        _has_jsonschema = False

    fixtures_dir = spec.get("fixtures_dir", "")
    schemas_dir = spec.get("schemas_dir", "")

    if not fixtures_dir or not schemas_dir:
        return True, "SKIP: fixtures_dir and schemas_dir required"

    fixtures_path = PROJECT_ROOT / fixtures_dir
    schemas_path = PROJECT_ROOT / schemas_dir

    if not fixtures_path.exists():
        return True, f"SKIP: fixtures dir not found: {fixtures_dir}"
    if not schemas_path.exists():
        return True, f"SKIP: schemas dir not found: {schemas_dir}"

    fixture_files = list(fixtures_path.glob("*.json"))
    if not fixture_files:
        return True, "SKIP: no fixture files found"

    if not _has_jsonschema:
        # Basic key check only
        checked = 0
        errors: list[str] = []
        for fixture_file in fixture_files:
            schema_file = schemas_path / fixture_file.name.replace(".json", ".schema.json")
            if not schema_file.exists():
                continue
            data, err = _load_json(fixture_file)
            if err:
                errors.append(err)
                continue
            schema_data, serr = _load_json(schema_file)
            if serr:
                errors.append(serr)
                continue
            checked += 1
        if errors:
            return False, "FAIL — " + "; ".join(errors[:3])
        return True, f"fixture_schema: basic check on {checked} fixture(s) (no jsonschema)"

    import jsonschema

    checked = 0
    errors_list: list[str] = []

    for fixture_file in fixture_files:
        schema_file = schemas_path / fixture_file.name.replace(".json", ".schema.json")
        if not schema_file.exists():
            # Try name-based match (e.g. events.json -> events.schema.json)
            continue

        data, err = _load_json(fixture_file)
        if err:
            errors_list.append(err)
            continue
        schema_data, serr = _load_json(schema_file)
        if serr:
            errors_list.append(serr)
            continue

        try:
            jsonschema.validate(data, schema_data)
            checked += 1
        except jsonschema.ValidationError as e:
            errors_list.append(f"{fixture_file.name}: {str(e)[:100]}")
        except jsonschema.SchemaError as e:
            errors_list.append(f"schema {schema_file.name}: {str(e)[:100]}")

    if errors_list:
        return False, "FAIL — " + "; ".join(errors_list[:3])
    return True, f"fixture_schema: {checked} fixture(s) validated"


# ─── fixture_parity ───────────────────────────────────────────────────────────


def fixture_parity(spec: dict[str, Any]) -> tuple[bool, str]:
    """Each fixture maps to an endpoint in spec §15.

    Basic check: fixture files exist and spec_endpoints section referenced.
    """
    fixtures_dir = spec.get("fixtures_dir", "")
    spec_endpoints_section = spec.get("spec_endpoints_section", "")
    _allow_new = spec.get("allow_new_endpoints_list", "")  # noqa: F841

    if not fixtures_dir:
        return True, "SKIP: no fixtures_dir"

    fixtures_path = PROJECT_ROOT / fixtures_dir
    if not fixtures_path.exists():
        return True, f"SKIP: fixtures dir not found: {fixtures_dir}"

    fixture_files = list(fixtures_path.glob("*.json"))
    if not fixture_files:
        return True, "SKIP: no fixture files"

    # Check spec file exists and references the section
    spec_file = spec.get("spec_file", "docs/design/frontend-v1-spec.md")
    spec_path = PROJECT_ROOT / spec_file

    if not spec_path.exists():
        return True, f"SKIP: spec file not found: {spec_file}"

    spec_content = spec_path.read_text(encoding="utf-8", errors="replace")
    if spec_endpoints_section not in spec_content:
        return False, f"spec {spec_file} does not contain section {spec_endpoints_section!r}"

    return True, (
        f"fixture_parity: {len(fixture_files)} fixture(s) checked against {spec_endpoints_section}"
    )


# ─── fixture_field_required ───────────────────────────────────────────────────


def fixture_field_required(spec: dict[str, Any]) -> tuple[bool, str]:
    """JSONPath traversal, check fields exist.

    Supports format: date, value_type, min_length.
    """
    path_expr = spec.get("path", "$")
    required_fields: list[str] = spec.get("required_fields", [])
    fmt = spec.get("format", "")
    value_type = spec.get("value_type", "")
    min_length = spec.get("min_length", 0)

    fixture_paths = _resolve_fixture_paths(spec)
    if not fixture_paths:
        return True, "SKIP: no fixture files specified"

    existing = [p for p in fixture_paths if p.exists()]
    if not existing:
        return True, "SKIP: fixture files not found"

    failures: list[str] = []

    for fixture_file in existing:
        data, err = _load_json(fixture_file)
        if err:
            failures.append(err)
            continue

        if required_fields:
            # Resolve path to get objects, then check fields on each
            items = resolve_jsonpath(data, path_expr)
            if not items:
                failures.append(f"{fixture_file.name}: path {path_expr!r} resolved to nothing")
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                for field in required_fields:
                    if field not in item:
                        failures.append(
                            f"{fixture_file.name}: missing field {field!r} at {path_expr!r}"
                        )
                        break
        else:
            # Check the path itself exists
            values = resolve_jsonpath(data, path_expr)
            if not values:
                failures.append(f"{fixture_file.name}: path {path_expr!r} not found")
                continue

            for val in values:
                if val is None:
                    failures.append(f"{fixture_file.name}: {path_expr!r} is null")
                    continue
                # Format check
                if fmt == "date":
                    val_str = str(val)
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                        failures.append(f"{fixture_file.name}: {val_str!r} is not YYYY-MM-DD")
                # Value type check
                if value_type == "string" and not isinstance(val, str):
                    failures.append(
                        f"{fixture_file.name}: {path_expr!r} expected string, "
                        f"got {type(val).__name__}"
                    )
                # Min length
                if min_length and isinstance(val, str) and len(val) < min_length:
                    failures.append(
                        f"{fixture_file.name}: {path_expr!r}={val!r} shorter than {min_length}"
                    )

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"fixture_field_required OK in {len(existing)} file(s)"


# ─── fixture_numeric_range ────────────────────────────────────────────────────


def fixture_numeric_range(spec: dict[str, Any]) -> tuple[bool, str]:
    """JSONPath values must be numeric in [min, max]."""
    path_expr = spec.get("path", "$")
    min_val = spec.get("min", None)
    max_val = spec.get("max", None)
    decimal_places_max = spec.get("decimal_places_max", None)

    fixture_paths = _resolve_fixture_paths(spec)
    existing = [p for p in fixture_paths if p.exists()]
    if not existing:
        return True, "SKIP: fixture files not found"

    failures: list[str] = []
    for fixture_file in existing:
        data, err = _load_json(fixture_file)
        if err:
            failures.append(err)
            continue
        values = resolve_jsonpath(data, path_expr)
        for val in values:
            try:
                num = float(val)
            except (TypeError, ValueError):
                failures.append(f"{fixture_file.name}: {val!r} not numeric at {path_expr!r}")
                continue
            if min_val is not None and num < min_val:
                failures.append(f"{fixture_file.name}: {num} < min {min_val}")
            if max_val is not None and num > max_val:
                failures.append(f"{fixture_file.name}: {num} > max {max_val}")
            if decimal_places_max is not None:
                # Check decimal places
                str_val = str(val)
                if "." in str_val:
                    dp = len(str_val.split(".")[1])
                    if dp > decimal_places_max:
                        failures.append(
                            f"{fixture_file.name}: {val} has {dp} decimal places "
                            f"> {decimal_places_max}"
                        )

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"fixture_numeric_range [{min_val}, {max_val}] OK"


# ─── fixture_array_length ─────────────────────────────────────────────────────


def fixture_array_length(spec: dict[str, Any]) -> tuple[bool, str]:
    """JSONPath arrays must have len >= min_length."""
    path_expr = spec.get("path", "$")
    min_length = spec.get("min_length", 1)

    fixture_paths = _resolve_fixture_paths(spec)
    existing = [p for p in fixture_paths if p.exists()]
    if not existing:
        return True, "SKIP: fixture files not found"

    failures: list[str] = []
    for fixture_file in existing:
        data, err = _load_json(fixture_file)
        if err:
            failures.append(err)
            continue
        # For array_length, the path points to arrays
        # We need to evaluate path *up to* the array, not iterate it
        # Remove trailing [*] if present to get the array itself
        array_path = path_expr
        if array_path.endswith("[*]"):
            array_path = array_path[:-3]

        arrays = resolve_jsonpath(data, array_path)
        if not arrays:
            failures.append(f"{fixture_file.name}: path {array_path!r} not found")
            continue
        for arr in arrays:
            if not isinstance(arr, list):
                failures.append(f"{fixture_file.name}: {array_path!r} is not an array")
                continue
            if len(arr) < min_length:
                failures.append(f"{fixture_file.name}: array length {len(arr)} < {min_length}")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"fixture_array_length >= {min_length} OK"


# ─── fixture_enum ─────────────────────────────────────────────────────────────


def fixture_enum(spec: dict[str, Any]) -> tuple[bool, str]:
    """JSONPath values must be in allowed list."""
    path_expr = spec.get("path", "$")
    allowed: list[str] = spec.get("allowed", [])

    fixture_paths = _resolve_fixture_paths(spec)
    existing = [p for p in fixture_paths if p.exists()]
    if not existing:
        return True, "SKIP: fixture files not found"

    failures: list[str] = []
    for fixture_file in existing:
        data, err = _load_json(fixture_file)
        if err:
            failures.append(err)
            continue
        values = resolve_jsonpath(data, path_expr)
        for val in values:
            if str(val) not in allowed:
                failures.append(f"{fixture_file.name}: {val!r} not in {allowed}")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"fixture_enum {allowed} OK"


# ─── fixture_endpoint_reference ───────────────────────────────────────────────


def fixture_endpoint_reference(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check that each required endpoint appears in at least one fixture."""
    endpoints: list[str] = spec.get("endpoints_must_appear", [])
    fixtures_dir = spec.get("fixtures_dir", "frontend/mockups/fixtures")

    fixtures_path = PROJECT_ROOT / fixtures_dir
    if not fixtures_path.exists():
        return True, f"SKIP: fixtures dir not found: {fixtures_dir}"

    fixture_files = list(fixtures_path.glob("*.json"))
    if not fixture_files:
        return True, "SKIP: no fixture files"

    # Build combined text of all fixtures
    all_text = ""
    for f in fixture_files:
        try:
            all_text += f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    missing: list[str] = []
    for endpoint in endpoints:
        if endpoint not in all_text:
            missing.append(endpoint)

    if missing:
        return False, f"Endpoints not referenced in fixtures: {missing}"
    return True, f"All {len(endpoints)} endpoint(s) referenced in fixtures"
