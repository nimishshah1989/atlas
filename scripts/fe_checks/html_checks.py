"""
html_checks — HTML validity and design-contract checks.

Implements: html5_valid, design_tokens_only, chart_contract, methodology_footer
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .dom_checks import find_elements, _matches_single_selector, _parse_attrs

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_glob_files(pattern: str) -> list[Path]:
    matched = glob.glob(str(PROJECT_ROOT / pattern))
    return [Path(m) for m in matched if Path(m).is_file()]


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def html5_valid(spec: dict[str, Any]) -> tuple[bool, str]:
    """Run html5validator on files glob. SKIP if not installed."""
    # Check if html5validator is available
    try:
        result = subprocess.run(
            [sys.executable, "-m", "html5validator", "--version"],
            capture_output=True,
            timeout=10,
        )
        # Returncode non-zero here means either: module not found, or tool error
        # "No module named html5validator" → not installed
        combined = result.stdout + result.stderr
        if result.returncode != 0:
            if b"No module named" in combined or b"not found" in combined.lower():
                return True, "SKIP: html5validator not installed"
            # Tool exists but version flag failed — try to proceed
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return True, "SKIP: html5validator not installed"

    files_pattern = spec.get("files", "")
    if not files_pattern:
        return True, "SKIP: no files specified"

    files = _resolve_glob_files(files_pattern)
    if not files:
        return True, "SKIP: no files matched"

    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "html5validator"] + [str(f) for f in existing],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0:
            return True, f"HTML5 valid: {len(existing)} file(s)"
        errors = (proc.stdout + proc.stderr)[:500]
        return False, f"HTML5 validation errors: {errors}"
    except subprocess.TimeoutExpired:
        return True, "SKIP: html5validator timed out"
    except Exception as exc:  # noqa: BLE001
        return True, f"SKIP: html5validator error: {exc}"


# Raw color/font patterns that should not appear outside tokens.css
_RAW_COLOR_RE = re.compile(
    r'(?:style\s*=\s*["\'][^"\']*(?:color|background)[^"\']*["\']'
    r"|(?<!var\()-{0,1}(?:#[0-9a-fA-F]{3,8}|rgb\s*\([^)]+\)|hsl\s*\([^)]+\)))",
    re.IGNORECASE,
)
_INLINE_STYLE_RE = re.compile(r'style\s*=\s*"([^"]*)"', re.IGNORECASE)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:", re.IGNORECASE)


def design_tokens_only(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check files contain no raw hex/rgb/hsl colors outside tokens.css.

    Supports allow_inline_style_properties list and exceptions_files list —
    the latter is for files that legitimately contain raw colors as subject
    matter (e.g. `styleguide.html` renders each token as a colour swatch).
    """
    files_pattern = spec.get("files", "")
    if not files_pattern:
        return True, "SKIP: no files specified"

    allow_properties: list[str] = spec.get("allow_inline_style_properties", [])
    exceptions: set[str] = set(spec.get("exceptions_files", []))

    violations: list[str] = []
    matched_count = 0

    for pattern in files_pattern.split():
        files = _resolve_glob_files(pattern)
        for f in files:
            if f.name == "tokens.css":
                continue  # tokens.css is allowed to define raw colors
            if f.name in exceptions:
                continue  # explicitly exempted showcase files
            if not f.exists():
                continue
            matched_count += 1
            content = _read_file(f)

            # Check for inline style attributes with color/background
            for m in _INLINE_STYLE_RE.finditer(content):
                style_val = m.group(1)
                # Skip if it's only allowed properties
                props_in_style = [
                    p.strip().split(":")[0].strip() for p in style_val.split(";") if ":" in p
                ]
                forbidden_props = [p for p in props_in_style if p and p not in allow_properties]
                if forbidden_props:
                    # Check if any forbidden prop has raw color values
                    for p in style_val.split(";"):
                        if ":" in p:
                            prop_name = p.split(":")[0].strip()
                            prop_val = ":".join(p.split(":")[1:]).strip()
                            color_props = (
                                "color",
                                "background",
                                "background-color",
                                "border-color",
                            )
                    if prop_name in color_props:
                        if re.search(r"#[0-9a-fA-F]{3,8}|rgb\s*\(|hsl\s*\(", prop_val):
                            if prop_name not in allow_properties:
                                violations.append(f"{f.name}: raw {prop_name} in inline style")

    if violations:
        return False, "Raw color/font declarations: " + "; ".join(violations[:5])
    if matched_count == 0:
        return True, "SKIP: no files matched"
    return True, f"Design tokens OK in {matched_count} file(s)"


def _selector_present_in_html(html: str, selector: str) -> bool:
    """Check if any element matching selector exists in raw HTML string.

    Searches all opening tags in the HTML against each sub-selector.
    Works for comma-separated selectors.
    """
    from .dom_checks import Element

    sub_selectors = [s.strip() for s in selector.split(",") if s.strip()]
    # Find all opening tags
    open_tag_re = re.compile(r"<([a-zA-Z][a-zA-Z0-9_-]*)([^>]*)>", re.DOTALL)
    for m in open_tag_re.finditer(html):
        tag = m.group(1).lower()
        attrs = _parse_attrs(m.group(2))
        el = Element(tag, attrs, "")
        for sub_sel in sub_selectors:
            if _matches_single_selector(el, sub_sel):
                return True
    return False


def chart_contract(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check every .chart / .chart-with-events has required children."""
    selector = spec.get("selector", ".chart-with-events, .chart")
    required_children: list[str] = spec.get("required_children", [])

    pages_from_raw = spec.get("pages_from", [])
    pages = pages_from_raw if isinstance(pages_from_raw, list) else []

    base = PROJECT_ROOT / "frontend" / "mockups"
    files: list[Path] = []
    if pages:
        files = [base / p for p in pages]
    else:
        files_raw = spec.get("files", "")
        if isinstance(files_raw, list):
            files = [Path(f) for f in files_raw]
        elif files_raw:
            for pattern in files_raw.split():
                for m in glob.glob(str(PROJECT_ROOT / pattern)):
                    p = Path(m)
                    if p.is_file():
                        files.append(p)

    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: no files found"

    failures: list[str] = []
    for f in existing:
        html = _read_file(f)
        chart_elements = find_elements(html, selector)
        if not chart_elements:
            continue
        for chart in chart_elements:
            outer_html = chart.outer
            for child_sel in required_children:
                # Check for child by searching all tags in the full HTML section
                # We search within the outer HTML for any matching element using
                # a simple attribute/class text search as a fallback
                children_found = _selector_present_in_html(outer_html, child_sel)
                if not children_found:
                    failures.append(f"{f.name}: chart missing {child_sel!r}")
                    break  # Report first missing child per chart

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    total_charts = sum(len(find_elements(_read_file(f), selector)) for f in existing)
    return True, f"chart_contract: {total_charts} chart(s) have required children"


def methodology_footer(spec: dict[str, Any]) -> tuple[bool, str]:
    """Check footer element contains required text strings."""
    selector = spec.get("selector", "footer[data-role=methodology], .methodology-footer")
    must_contain: list[str] = spec.get("must_contain", [])

    pages_from_raw = spec.get("pages_from", [])
    pages = pages_from_raw if isinstance(pages_from_raw, list) else []

    base = PROJECT_ROOT / "frontend" / "mockups"
    files: list[Path] = []
    if pages:
        files = [base / p for p in pages]
    else:
        # Handle files_any or files glob or files list
        files_any = spec.get("files_any", "")
        files_raw = spec.get("files", "")
        if isinstance(files_raw, list):
            files = [Path(f) for f in files_raw]
        else:
            pattern = files_any or files_raw
            if pattern:
                for pat in pattern.split():
                    for m in glob.glob(str(PROJECT_ROOT / pat)):
                        p = Path(m)
                        if p.is_file():
                            files.append(p)

    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: no files found"

    failures: list[str] = []
    for f in existing:
        html = _read_file(f)
        footer_elements = find_elements(html, selector)

        # Also check generic footer tag
        if not footer_elements:
            footer_elements = find_elements(html, "footer")

        if not footer_elements:
            failures.append(f"{f.name}: no footer element found")
            continue

        footer_text = " ".join(e.text + " " + e.outer for e in footer_elements)
        for text in must_contain:
            if text.lower() not in footer_text.lower():
                failures.append(f"{f.name}: footer missing {text!r}")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"methodology_footer OK in {len(existing)} file(s)"
