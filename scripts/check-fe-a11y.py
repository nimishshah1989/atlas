#!/usr/bin/env python3
"""
ATLAS Frontend Accessibility Checker

Validates static HTML mockup files for WCAG-level accessibility issues
using stdlib-only regex-based parsing (consistent with the project's
approach for mockup checks in scripts/fe_checks/).

Usage:
    python scripts/check-fe-a11y.py
    python scripts/check-fe-a11y.py --files "frontend/mockups/*.html"

Exit codes:
    0 — no critical a11y issues (warnings are OK)
    1 — at least one critical a11y failure
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / ".forge" / "a11y-report.json"

# Pages that are reference/showcase — apply lenient checks
LENIENT_PAGES = {
    "styleguide.html",
    "components.html",
    "frontend-v1-spec.html",
    "breadth-simulator-v8.html",
    "explorer.html",
}

# Regex patterns (stdlib-only, no HTML parser)
_IMG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HEADING_RE = re.compile(r"<(h[1-6])\b[^>]*>", re.IGNORECASE)
_HTML_LANG_RE = re.compile(r"<html\b[^>]*\blang\s*=\s*[\"'][^\"']+[\"']", re.IGNORECASE)
# Match id= but NOT data-*-id= or slot-id= etc. Only the bare `id` attribute.
_ID_ATTR_RE = re.compile(r'(?<![a-zA-Z0-9_-])\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_TH_RE = re.compile(r"<th\b", re.IGNORECASE)
_TABLE_ARIA_RE = re.compile(r'\baria-label\s*=\s*["\'][^"\']+["\']', re.IGNORECASE)
_VIEWPORT_RE = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*["\']viewport["\'][^>]*>',
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(r'\b([a-zA-Z_:][a-zA-Z0-9_:\-\.]*)\s*=\s*["\']([^"\']*)["\']')
_LABEL_FOR_RE = re.compile(r'<label\b[^>]*\bfor\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_ARIA_LABELLEDBY_RE = re.compile(r'\baria-labelledby\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_ARIA_LABEL_RE = re.compile(r'\baria-label\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_INNER_TEXT_RE = re.compile(r">([^<]+)<", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _now_ist() -> str:
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).isoformat()


def _parse_attrs(attr_str: str) -> dict[str, str]:
    """Parse HTML attribute string into dict."""
    result: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attr_str):
        result[m.group(1).lower()] = m.group(2)
    # Boolean attrs without value
    for word in re.findall(r"\b(alt|aria-hidden|disabled|required)\b", attr_str):
        if word not in result:
            result[word] = ""
    return result


def _strip_comments(html: str) -> str:
    """Remove HTML comments to avoid false positives."""
    return _COMMENT_RE.sub("", html)


def check_img_alt(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """All <img> tags must have alt attribute."""
    issues: list[dict[str, Any]] = []
    for m in _IMG_RE.finditer(html):
        attrs = _parse_attrs(m.group(1))
        if "alt" not in attrs:
            src = attrs.get("src", "?")[:50]
            issues.append(
                {
                    "check": "img_alt",
                    "severity": "warning" if lenient else "critical",
                    "message": f"<img> missing alt attribute (src={src!r})",
                }
            )
    return issues


def check_input_labels(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """All <input> elements should have associated labels."""
    issues: list[dict[str, Any]] = []
    # Collect label[for] targets
    label_for_targets: set[str] = set()
    for m in _LABEL_FOR_RE.finditer(html):
        label_for_targets.add(m.group(1))

    for m in _INPUT_RE.finditer(html):
        attrs = _parse_attrs(m.group(1))
        itype = attrs.get("type", "text").lower()
        # hidden inputs don't need labels
        if itype == "hidden":
            continue
        input_id = attrs.get("id", "")
        # Check: id in label[for] targets, or has aria-label/aria-labelledby
        has_label = (
            (input_id and input_id in label_for_targets)
            or "aria-label" in attrs
            or "aria-labelledby" in attrs
            or "placeholder" in attrs  # acceptable in mockups
        )
        if not has_label:
            issues.append(
                {
                    "check": "input_label",
                    "severity": "warning",  # warning-level in mockups
                    "message": f"<input type={itype!r}> lacks label association (id={input_id!r})",
                }
            )
    return issues


def check_heading_hierarchy(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """Heading levels should not skip (h1→h3 without h2 is a skip)."""
    issues: list[dict[str, Any]] = []
    headings = [int(m.group(1)[1]) for m in _HEADING_RE.finditer(html)]
    if not headings:
        return issues
    prev = headings[0]
    for level in headings[1:]:
        if level > prev + 1:
            issues.append(
                {
                    "check": "heading_hierarchy",
                    "severity": "warning",  # downgrade: component islands may legitimately skip
                    "message": f"Heading level skipped: h{prev} → h{level} in {fname}",
                }
            )
        prev = level
    return issues


def check_anchor_text(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """All <a> tags should have text content or aria-label."""
    issues: list[dict[str, Any]] = []
    for m in _ANCHOR_RE.finditer(html):
        attrs = _parse_attrs(m.group(1))
        inner = m.group(2)
        # Strip HTML tags from inner content to get text
        text = re.sub(r"<[^>]+>", "", inner).strip()
        has_aria = bool(_ARIA_LABEL_RE.search(m.group(1)))
        if not text and not has_aria and "aria-hidden" not in attrs:
            href = attrs.get("href", "?")[:40]
            issues.append(
                {
                    "check": "anchor_text",
                    "severity": "warning",
                    "message": f"<a href={href!r}> has no text or aria-label",
                }
            )
    return issues


def check_html_lang(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """<html> must have lang attribute."""
    if not _HTML_LANG_RE.search(html):
        return [
            {
                "check": "html_lang",
                "severity": "critical",
                "message": f"{fname}: <html> missing lang attribute",
            }
        ]
    return []


def check_duplicate_ids(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """No duplicate id attributes on the same page."""
    issues: list[dict[str, Any]] = []
    id_counts: dict[str, int] = {}
    for m in _ID_ATTR_RE.finditer(html):
        id_val = m.group(1)
        id_counts[id_val] = id_counts.get(id_val, 0) + 1
    dupes = [k for k, v in id_counts.items() if v > 1]
    if dupes:
        issues.append(
            {
                "check": "duplicate_ids",
                "severity": "critical" if not lenient else "warning",
                "message": f"{fname}: duplicate id(s): {dupes[:5]}",
            }
        )
    return issues


def check_table_headers(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """Tables should have <th> headers or aria-label."""
    issues: list[dict[str, Any]] = []
    for m in _TABLE_RE.finditer(html):
        table_html = m.group(0)
        has_th = bool(_TH_RE.search(table_html))
        has_aria = bool(_TABLE_ARIA_RE.search(table_html))
        if not has_th and not has_aria:
            issues.append(
                {
                    "check": "table_headers",
                    "severity": "warning",
                    "message": f"{fname}: table missing <th> or aria-label",
                }
            )
    return issues


def check_viewport_meta(html: str, fname: str, lenient: bool) -> list[dict[str, Any]]:
    """Viewport meta tag must be present."""
    if not _VIEWPORT_RE.search(html):
        return [
            {
                "check": "viewport_meta",
                "severity": "critical",
                "message": f"{fname}: missing viewport meta tag",
            }
        ]
    return []


CHECKS = [
    check_img_alt,
    check_input_labels,
    check_heading_hierarchy,
    check_anchor_text,
    check_html_lang,
    check_duplicate_ids,
    check_table_headers,
    check_viewport_meta,
]


def check_file(path: Path) -> dict[str, Any]:
    """Run all checks on one HTML file. Return per-file result dict."""
    fname = path.name
    lenient = fname in LENIENT_PAGES
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "file": fname,
            "error": str(e),
            "issues": [],
            "pass": False,
            "critical_count": 1,
            "warning_count": 0,
        }

    # Strip comments to avoid false positives from commented-out code
    html_clean = _strip_comments(html)

    all_issues: list[dict[str, Any]] = []
    for fn in CHECKS:
        all_issues.extend(fn(html_clean, fname, lenient))

    critical = [i for i in all_issues if i["severity"] == "critical"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    return {
        "file": fname,
        "lenient": lenient,
        "issues": all_issues,
        "pass": len(critical) == 0,
        "critical_count": len(critical),
        "warning_count": len(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ATLAS frontend a11y checker")
    parser.add_argument(
        "--files",
        default="frontend/mockups/*.html",
        help="Glob pattern for HTML files to check (default: frontend/mockups/*.html)",
    )
    args = parser.parse_args()

    pattern = args.files
    if not pattern.startswith("/"):
        pattern = str(ROOT / pattern)

    all_paths = sorted(Path(p) for p in glob.glob(pattern) if Path(p).is_file())

    # Skip partial files (those starting with _)
    main_paths = [p for p in all_paths if not p.name.startswith("_")]

    if not main_paths:
        print("ERROR: no HTML files matched", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    warn_count = 0
    critical_count = 0

    for path in main_paths:
        result = check_file(path)
        results.append(result)
        if result["pass"]:
            pass_count += 1
        else:
            fail_count += 1
        critical_count += result["critical_count"]
        warn_count += result["warning_count"]

    # Print summary
    print("=" * 60)
    print(" ATLAS FRONTEND ACCESSIBILITY REPORT")
    print("=" * 60)
    print(f"  Files checked:     {len(main_paths)}")
    print(f"  Pass:              {pass_count}")
    print(f"  Fail (critical):   {fail_count}")
    print(f"  Warnings:          {warn_count}")
    print(f"  Total critical:    {critical_count}")
    print("=" * 60)

    if fail_count > 0:
        print("\nCRITICAL ISSUES:")
        for r in results:
            for issue in r["issues"]:
                if issue["severity"] == "critical":
                    print(f"  [{r['file']}] {issue['check']}: {issue['message']}")

    if warn_count > 0 and warn_count < 50:
        print("\nWARNINGS (informational):")
        shown = 0
        for r in results:
            for issue in r["issues"]:
                if issue["severity"] == "warning" and shown < 20:
                    print(f"  [{r['file']}] {issue['check']}: {issue['message']}")
                    shown += 1
        if warn_count > 20:
            print(f"  ... and {warn_count - 20} more warnings")

    # Write JSON report
    report = {
        "generated_at": _now_ist(),
        "files_checked": len(main_paths),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "warning_count": warn_count,
        "critical_count": critical_count,
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {REPORT_PATH}")

    if fail_count > 0:
        print("\nRESULT: FAIL — critical a11y issues found")
        return 1
    print("\nRESULT: PASS — no critical a11y issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
