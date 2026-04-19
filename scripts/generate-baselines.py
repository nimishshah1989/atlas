#!/usr/bin/env python3
"""
ATLAS Frontend Baseline Screenshot Generator

Generates baseline PNG screenshots for all mockup pages at multiple
viewport sizes using headless Chromium via playwright.

Output directory: tests/e2e/fe_pages/baselines/
Naming convention: {page}_{viewport}.png
  e.g. today.html_desktop.png, today.html_tablet.png, today.html_mobile.png

This script is idempotent: running it twice on the same static files
produces the same screenshots (bit-identical within the same Chromium
version and platform).

Viewports:
  desktop:  1440×900  — all 17 main pages + 2 reference pages (19 files)
  tablet:   768×1024  — all 17 main pages (17 files)
  mobile:   375×812   — all 17 main pages (17 files)
  Total:    53 PNGs

Usage:
    python scripts/generate-baselines.py
    python scripts/generate-baselines.py --output-dir tests/e2e/fe_pages/baselines
    python scripts/generate-baselines.py --viewports desktop
    python scripts/generate-baselines.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MOCKUP_DIR = ROOT / "frontend" / "mockups"
DEFAULT_OUTPUT_DIR = ROOT / "tests" / "e2e" / "fe_pages" / "baselines"

# Main pages for all viewport captures
MAIN_PAGES = [
    "today.html",
    "explore-global.html",
    "explore-country.html",
    "explore-sector.html",
    "stock-detail.html",
    "mf-detail.html",
    "mf-rank.html",
    "breadth.html",
    "portfolios.html",
    "lab.html",
    "index.html",
    "portfolio-detail.html",
    "explorer.html",
    "pulse-breadth.html",
    "pulse-sectors.html",
    "styleguide.html",
    "components.html",
]

# Additional reference pages — desktop only
REFERENCE_PAGES = [
    "frontend-v1-spec.html",
    "breadth-simulator-v8.html",
]

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


def generate_baselines(
    output_dir: Path,
    viewports_to_run: list[str],
    dry_run: bool = False,
) -> int:
    """
    Generate all baseline screenshots. Returns count of generated files.

    Uses playwright sync API with headless Chromium.
    """
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = 0
    skipped = 0
    errors: list[str] = []

    # Build the list of (page, viewport) combinations
    tasks: list[tuple[str, str]] = []
    for viewport_name in viewports_to_run:
        if viewport_name == "desktop":
            # Desktop: main pages + reference pages
            for page in MAIN_PAGES + REFERENCE_PAGES:
                tasks.append((page, viewport_name))
        else:
            # Tablet and mobile: main pages only
            for page in MAIN_PAGES:
                tasks.append((page, viewport_name))

    total = len(tasks)
    print(f"Generating {total} screenshots to {output_dir}")
    print(f"Viewports: {viewports_to_run}")
    print("-" * 60)

    if dry_run:
        for page, viewport_name in tasks:
            fname = f"{page}_{viewport_name}.png"
            print(f"  [DRY-RUN] {fname}")
        print(f"\nTotal (dry-run): {total} files would be generated")
        return total

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for i, (page_name, viewport_name) in enumerate(tasks, 1):
                html_path = MOCKUP_DIR / page_name
                if not html_path.exists():
                    print(f"  [{i:3d}/{total}] SKIP  {page_name} (file not found)")
                    skipped += 1
                    continue

                viewport = VIEWPORTS[viewport_name]
                url = f"file://{html_path}"
                fname = f"{page_name}_{viewport_name}.png"
                out_path = output_dir / fname

                from typing import cast as _cast

                ctx = browser.new_context(
                    viewport=_cast(Any, viewport),
                    reduced_motion="reduce",
                )
                pg = ctx.new_page()
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=15000)
                    pg.screenshot(path=str(out_path), full_page=False)
                    size = out_path.stat().st_size
                    print(f"  [{i:3d}/{total}] OK    {fname} ({size // 1024}KB)")
                    generated += 1
                except Exception as exc:
                    print(f"  [{i:3d}/{total}] ERROR {fname}: {exc}")
                    errors.append(f"{fname}: {exc}")
                finally:
                    pg.close()
                    ctx.close()
        finally:
            browser.close()

    print("-" * 60)
    print(f"Generated: {generated}")
    print(f"Skipped:   {skipped}")
    print(f"Errors:    {len(errors)}")
    if errors:
        print("Error details:")
        for e in errors:
            print(f"  {e}")
    print(f"Output:    {output_dir}")
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ATLAS frontend baseline PNGs")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for PNGs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--viewports",
        default="desktop,tablet,mobile",
        help="Comma-separated viewport names to generate (default: desktop,tablet,mobile)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without taking screenshots",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    viewports = [v.strip() for v in args.viewports.split(",") if v.strip()]
    invalid = [v for v in viewports if v not in VIEWPORTS]
    if invalid:
        print(f"ERROR: invalid viewport names: {invalid}. Valid: {list(VIEWPORTS.keys())}")
        return 1

    count = generate_baselines(output_dir, viewports, dry_run=args.dry_run)
    print(f"\nTotal: {count} screenshots generated")
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
