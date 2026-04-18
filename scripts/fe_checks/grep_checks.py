"""
grep_checks — Static pattern-matching checks for frontend criteria.

Implements: grep_forbid, grep_require, kill_list, i18n_indian
All file paths are resolved relative to PROJECT_ROOT.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_files(spec: dict[str, Any]) -> list[Path]:
    """Resolve file patterns (space-separated globs) from spec to Path list."""
    patterns_str = spec.get("files", "")
    file_single = spec.get("file", "")
    all_patterns: list[str] = []
    if patterns_str:
        all_patterns.extend(patterns_str.split())
    if file_single:
        all_patterns.append(file_single)
    resolved: list[Path] = []
    for pattern in all_patterns:
        matched = glob.glob(str(PROJECT_ROOT / pattern))
        for m in matched:
            p = Path(m)
            if p.is_file():
                resolved.append(p)
    return resolved


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def grep_forbid(spec: dict[str, Any]) -> tuple[bool, str]:
    """Pattern P across files F must return 0 matches.

    Supports exceptions_files list.
    """
    pattern = spec.get("pattern", "")
    if not pattern:
        return False, "grep_forbid: no pattern specified"

    files = _resolve_files(spec)
    if not files:
        return True, "SKIP: no files matched"

    exceptions = set(spec.get("exceptions_files", []))
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return False, f"grep_forbid: invalid regex: {e}"

    hits: list[str] = []
    for f in files:
        if f.name in exceptions:
            continue
        content = _read_file(f)
        matches = regex.findall(content)
        if matches:
            hits.append(f"{f.name}: {len(matches)} match(es)")

    if hits:
        return False, "Pattern found (must be absent): " + "; ".join(hits[:5])
    return True, f"Pattern absent in {len(files)} file(s)"


def grep_require(spec: dict[str, Any]) -> tuple[bool, str]:
    """Pattern P (or patterns list) across files F must return >=N matches.

    Supports min_matches, min_matches_each, multiline, pages_from.
    """
    pattern_single = spec.get("pattern", "")
    patterns_list = spec.get("patterns", [])
    file_single = spec.get("file", "")

    # Build patterns list
    if pattern_single and not patterns_list:
        patterns_list = [pattern_single]
    if not patterns_list:
        return False, "grep_require: no pattern(s) specified"

    # Resolve files — handle single file too
    if file_single and not spec.get("files"):
        spec = dict(spec)
        spec["files"] = file_single
    files = _resolve_files(spec)
    if not files:
        return True, "SKIP: no files matched"

    flags = re.DOTALL if spec.get("multiline") else 0
    min_matches = spec.get("min_matches", 1)
    min_matches_each = spec.get("min_matches_each", None)

    results: list[str] = []
    all_passed = True

    for patt in patterns_list:
        try:
            regex = re.compile(patt, flags)
        except re.error as e:
            return False, f"grep_require: invalid regex {patt!r}: {e}"

        total = 0
        for f in files:
            content = _read_file(f)
            total += len(regex.findall(content))

        threshold = min_matches_each if min_matches_each is not None else min_matches
        if total < threshold:
            results.append(f"Pattern {patt!r}: found {total}, need {threshold}")
            all_passed = False
        else:
            results.append(f"Pattern {patt!r}: {total} match(es)")

    if all_passed:
        return True, "; ".join(results[:5])
    fail_msgs = "; ".join(r for r in results if r.startswith("Pattern") and "need" in r)
    return False, ("FAIL — " + fail_msgs)[:300]


def kill_list(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check that patterns list + files have 0 matches.

    Supports exceptions_files and exceptions_selectors (excluded by text context).
    Also supports extra_patterns merged into patterns list.
    Also supports single file via `file` key.
    Note: selector-level exceptions are complex; we do text-context exclusion
    by stripping content inside exception selector blocks (rough heuristic).
    """
    patterns: list[str] = list(spec.get("patterns", []))
    extra = spec.get("extra_patterns", [])
    if extra:
        patterns.extend(extra)
    if not patterns:
        return False, "kill_list: no patterns specified"

    # Handle single file
    file_single = spec.get("file", "")
    if file_single and not spec.get("files"):
        spec = dict(spec)
        spec["files"] = file_single

    files = _resolve_files(spec)
    if not files:
        return True, "SKIP: no files matched"

    exceptions_files = set(spec.get("exceptions_files", []))
    exceptions_selectors = spec.get("exceptions_selectors", [])

    hits: list[str] = []
    for f in files:
        if f.name in exceptions_files:
            continue
        content = _read_file(f)

        # Strip content inside exception selectors (simple heuristic using class names)
        working_content = content
        for exc_sel in exceptions_selectors:
            # Extract class name from selector like ".rec-slot"
            class_match = re.match(r"\.([a-zA-Z0-9_-]+)", exc_sel)
            if class_match:
                cls = class_match.group(1)
                # Remove blocks with that class
                working_content = re.sub(
                    r'<[^>]+class="[^"]*' + re.escape(cls) + r'[^"]*"[^>]*>.*?</[^>]+>',
                    "",
                    working_content,
                    flags=re.DOTALL,
                )

        for patt in patterns:
            try:
                regex = re.compile(patt)
            except re.error:
                continue
            matches = regex.findall(working_content)
            if matches:
                hits.append(f"{f.name}: {patt!r} ({len(matches)} match)")

    if hits:
        return False, "Forbidden patterns found: " + "; ".join(hits[:5])
    return True, f"All patterns absent in {len(files)} file(s)"


def i18n_indian(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check Indian i18n: forbidden patterns must not appear in files.

    Supports allowed_in_fixtures flag — if True, skip .json files.
    """
    forbidden_patterns: list[str] = spec.get("forbidden_patterns", [])
    if not forbidden_patterns:
        return False, "i18n_indian: no forbidden_patterns specified"

    files = _resolve_files(spec)
    if not files:
        return True, "SKIP: no files matched"

    allowed_in_fixtures = spec.get("allowed_in_fixtures", False)

    hits: list[str] = []
    for f in files:
        # Skip fixture JSON files if allowed_in_fixtures is set
        if allowed_in_fixtures and f.suffix == ".json":
            continue
        content = _read_file(f)
        for patt in forbidden_patterns:
            try:
                regex = re.compile(patt, re.IGNORECASE)
            except re.error:
                continue
            matches = regex.findall(content)
            if matches:
                hits.append(f"{f.name}: {patt!r} ({len(matches)} match)")

    if hits:
        return False, "Forbidden i18n patterns found: " + "; ".join(hits[:5])
    return True, f"Indian i18n OK in {len(files)} file(s)"
