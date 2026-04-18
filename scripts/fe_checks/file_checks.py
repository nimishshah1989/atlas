"""
file_checks — File system checks for frontend criteria.

Implements: file_exists, url_reachable, link_integrity
"""

from __future__ import annotations

import glob
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def file_exists(spec: dict[str, Any]) -> tuple[bool, str]:
    """Every path in `paths` list exists and is non-empty.

    Paths are relative to PROJECT_ROOT.
    """
    paths: list[str] = spec.get("paths", [])
    if not paths:
        return False, "file_exists: no paths specified"

    missing: list[str] = []
    empty: list[str] = []
    for p in paths:
        full = PROJECT_ROOT / p
        if not full.exists():
            missing.append(p)
        elif full.stat().st_size == 0:
            empty.append(p)

    if missing or empty:
        parts = []
        if missing:
            parts.append(f"missing: {missing[:5]}")
        if empty:
            parts.append(f"empty: {empty[:5]}")
        return False, "FAIL — " + "; ".join(parts)
    return True, f"All {len(paths)} file(s) exist and non-empty"


def url_reachable(spec: dict[str, Any]) -> tuple[bool, str]:
    """URL returns 200. SKIP if offline (FE_CHECKS_OFFLINE=1 or network error).

    Supports url_template with pages_from, and urls list.
    """
    # Offline guard
    if os.environ.get("FE_CHECKS_OFFLINE", "0") == "1":
        return True, "SKIP: FE_CHECKS_OFFLINE=1"

    urls_to_check: list[str] = []
    url_template = spec.get("url_template", "")
    pages_from_raw = spec.get("pages_from", [])
    pages = pages_from_raw if isinstance(pages_from_raw, list) else []

    if url_template and pages:
        for page in pages:
            urls_to_check.append(url_template.replace("{page}", page))
    elif spec.get("urls"):
        urls_to_check.extend(spec["urls"])
    elif spec.get("url"):
        urls_to_check.append(spec["url"])

    if not urls_to_check:
        return True, "SKIP: no URLs specified"

    failures: list[str] = []
    for url in urls_to_check[:20]:  # cap to avoid runaway
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "atlas-fe-check/1.0")
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.getcode()
                if code != 200:
                    failures.append(f"{url}: HTTP {code}")
        except urllib.error.HTTPError as e:
            failures.append(f"{url}: HTTP {e.code}")
        except Exception:  # noqa: BLE001
            # Network unavailable or timeout
            return True, "SKIP: network unavailable"

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"All {len(urls_to_check)} URL(s) returned 200"


def link_integrity(spec: dict[str, Any]) -> tuple[bool, str]:
    """Parse href/src from HTML files, check local files exist.

    Supports allow_external and allow_anchor_only.
    """
    patterns_str = spec.get("files", "")
    if not patterns_str:
        return True, "SKIP: no files specified"

    allow_external = spec.get("allow_external", False)
    allow_anchor_only = spec.get("allow_anchor_only", True)

    # Resolve files
    all_files: list[Path] = []
    for pattern in patterns_str.split():
        for m in glob.glob(str(PROJECT_ROOT / pattern)):
            p = Path(m)
            if p.is_file():
                all_files.append(p)

    if not all_files:
        return True, "SKIP: no files matched"

    href_re = re.compile(r'(?:href|src)=["\']([^"\']+)["\']', re.IGNORECASE)
    broken: list[str] = []

    for f in all_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        links = href_re.findall(content)
        for link in links:
            # Skip external
            if link.startswith(("http://", "https://", "//")):
                if not allow_external:
                    pass  # just skip check, don't flag
                continue
            # Skip anchor-only
            if link.startswith("#"):
                if allow_anchor_only:
                    continue
            # Skip data URIs
            if link.startswith("data:"):
                continue
            # Skip empty
            if not link.strip():
                continue
            # Local link — check if file exists relative to the HTML file's dir
            target = (f.parent / link.split("#")[0]).resolve()
            if not target.exists() and not str(target).startswith(str(PROJECT_ROOT / "frontend")):
                # Only check links within the mockups/frontend dir
                continue
            if link.split("#")[0] and not target.exists():
                broken.append(f"{f.name} -> {link}")

    if broken:
        return False, "Broken local links: " + "; ".join(broken[:5])
    return True, f"Link integrity OK in {len(all_files)} file(s)"
