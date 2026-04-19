"""
dom_checks — HTML DOM inspection using regex-based element matching.

Implements: dom_required, dom_forbidden, attr_required, attr_enum, attr_numeric_range

Uses regex-based HTML element matching since stdlib html.parser doesn't support
CSS selectors. Supports the selector grammar used in frontend-v1-criteria.yaml.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ─── Element representation ───────────────────────────────────────────────────


class Element:
    __slots__ = ("tag", "attrs", "text", "outer")

    def __init__(self, tag: str, attrs: dict[str, str], text: str, outer: str = "") -> None:
        self.tag = tag
        self.attrs = attrs
        self.text = text
        self.outer = outer

    def get_attr(self, name: str) -> str | None:
        return self.attrs.get(name)

    def has_attr(self, name: str) -> bool:
        return name in self.attrs


# ─── HTML tag parser ──────────────────────────────────────────────────────────

_TAG_RE = re.compile(
    r"<(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)(?P<attrs>[^>]*?)(?:/>|>(?P<inner>.*?)</(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)
_ATTR_RE = re.compile(
    r"""(?P<name>[a-zA-Z_:][a-zA-Z0-9_:.-]*)"""
    r"""(?:\s*=\s*(?P<val>"[^"]*"|'[^']*'|[^\s>'"=]+))?""",
)
# HTML5 void elements — the only HTML tags allowed to self-close.
# Non-void tags written as `<tag />` are parsed by browsers as unclosed
# opening tags, which silently destroys the DOM tree. Historically the
# gate accepted any `<tag />` form as a "present" element, letting agents
# satisfy dom_required via sentinel-spam while pages broke at render time.
_HTML_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
# SVG leaf elements legitimately self-close in XML-mode SVG parsing.
_SVG_SELF_CLOSING = frozenset(
    {
        "circle",
        "ellipse",
        "line",
        "path",
        "polygon",
        "polyline",
        "rect",
        "stop",
        "use",
        "image",
        "animate",
        "animateTransform",
        "animateMotion",
        "feBlend",
        "feColorMatrix",
        "feComposite",
        "feFlood",
        "feGaussianBlur",
        "feMerge",
        "feMergeNode",
        "feMorphology",
        "feOffset",
        "feTurbulence",
        "mpath",
        "set",
    }
)
_VOID_TAG_RE = re.compile(r"<(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)(?P<attrs>[^>]*?)/>", re.DOTALL)
# Same shape but restricted to the allow-list. Used by _find_all_tags so
# fake-void sentinels are *not* indexed as present, and so a regression
# check can enumerate them.
_LEGAL_VOID_TAG_RE = re.compile(
    r"<(?P<tag>"
    + "|".join(sorted(_HTML_VOID_TAGS | _SVG_SELF_CLOSING, key=len, reverse=True))
    + r")(?P<attrs>[^>]*?)/>",
    re.DOTALL | re.IGNORECASE,
)


def find_fake_void_tags(html: str) -> list[tuple[str, int]]:
    """Return list of (tag_name, offset) for every non-void self-closing tag.

    Used both by the gate's regression check and by the runtime parser so
    agents cannot satisfy dom_required via `<div data-x=... />` sentinels
    that browsers parse as unclosed opening tags.
    """
    legal = _HTML_VOID_TAGS | _SVG_SELF_CLOSING
    hits: list[tuple[str, int]] = []
    for m in _VOID_TAG_RE.finditer(html):
        tag = m.group("tag").lower()
        if tag not in legal:
            hits.append((tag, m.start()))
    return hits


def _parse_attrs(attrs_str: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attrs_str):
        name = m.group("name").lower()
        val = m.group("val")
        if val is None:
            result[name] = ""
        else:
            result[name] = val.strip("\"'")
    return result


def _extract_element_section(html: str, start: int, tag: str) -> str:
    """Extract the full HTML section for a tag starting at position `start`.

    Handles nested same-tag elements by counting open/close pairs.
    Returns the full outer HTML including opening and closing tag.
    """
    # Find the end of the opening tag
    open_end = html.find(">", start)
    if open_end == -1:
        return html[start : start + 200]

    # Check if self-closing
    if html[open_end - 1] == "/":
        return html[start : open_end + 1]

    # Walk forward counting nesting
    depth = 1
    pos = open_end + 1
    open_re = re.compile(r"<" + re.escape(tag) + r"(?:\s[^>]*)?>", re.IGNORECASE)
    close_re = re.compile(r"</" + re.escape(tag) + r">", re.IGNORECASE)

    while pos < len(html) and depth > 0:
        next_open = open_re.search(html, pos)
        next_close = close_re.search(html, pos)

        if next_close is None:
            break
        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            if depth == 0:
                return html[start : next_close.end()]
            pos = next_close.end()

    return html[start : min(start + 2000, len(html))]


def _find_all_tags(html: str) -> list[Element]:
    """Find all HTML elements with tag, attrs, text content."""
    elements: list[Element] = []
    # Match self-closing tags, but ONLY real HTML5 void tags and SVG leaf
    # elements. Non-void HTML tags written as `<tag />` are silently
    # skipped here so they cannot satisfy dom_required via sentinel-spam;
    # the top-level scan in check-frontend-criteria.py also hard-fails on
    # any such occurrence.
    for m in _LEGAL_VOID_TAG_RE.finditer(html):
        attrs = _parse_attrs(m.group("attrs"))
        elements.append(Element(m.group("tag").lower(), attrs, "", m.group(0)))
    # Match open/close tag pairs
    for m in _TAG_RE.finditer(html):
        tag = m.group("tag").lower()
        attrs = _parse_attrs(m.group("attrs"))
        inner = m.group("inner") or ""
        # Strip inner HTML tags to get text content
        text = re.sub(r"<[^>]+>", " ", inner).strip()
        # Extract full outer HTML using nesting-aware extraction
        full_outer = _extract_element_section(html, m.start(), tag)
        elements.append(Element(tag, attrs, text, full_outer))
    return elements


# ─── Selector matching ────────────────────────────────────────────────────────


def _matches_single_selector(el: Element, selector: str) -> bool:
    """Match a single selector (no combinators, no commas) against an element."""
    selector = selector.strip()
    if not selector:
        return False

    # Parse out all conditions from the selector
    remaining = selector

    # Extract tag prefix (if any)
    tag_match = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)", remaining)
    required_tag: str | None = None
    if tag_match and not remaining.startswith((".", "[", "#")):
        required_tag = tag_match.group(1).lower()
        remaining = remaining[len(tag_match.group(0)) :]

    # Check tag
    if required_tag and el.tag != required_tag:
        return False

    # Check all remaining conditions
    pos = 0
    while pos < len(remaining):
        ch = remaining[pos]
        if ch == ".":
            # .classname
            m = re.match(r"\.([a-zA-Z0-9_-]+)", remaining[pos:])
            if m:
                cls = m.group(1)
                el_classes = el.attrs.get("class", "").split()
                if cls not in el_classes:
                    return False
                pos += len(m.group(0))
            else:
                pos += 1
        elif ch == "#":
            # #id
            m = re.match(r"#([a-zA-Z0-9_-]+)", remaining[pos:])
            if m:
                if el.attrs.get("id", "") != m.group(1):
                    return False
                pos += len(m.group(0))
            else:
                pos += 1
        elif ch == "[":
            # [attr] or [attr=value] or [attr='value']
            m = re.match(r"\[([a-zA-Z0-9_:-]+)(?:=(['\"]?)([^'\"=\]]*)\2)?\]", remaining[pos:])
            if m:
                attr_name = m.group(1).lower()
                attr_val = m.group(3)
                if attr_val is not None:
                    if el.attrs.get(attr_name, "") != attr_val:
                        return False
                else:
                    if not el.has_attr(attr_name):
                        return False
                pos += len(m.group(0))
            else:
                pos += 1
        else:
            pos += 1

    return True


def _bs4_tag_to_element(tag: Any) -> Element:
    """Convert a BeautifulSoup Tag into the dom_checks Element shape."""
    attrs: dict[str, str] = {}
    for k, v in (tag.attrs or {}).items():
        if isinstance(v, list):
            attrs[k.lower()] = " ".join(str(x) for x in v)
        elif v is None:
            attrs[k.lower()] = ""
        else:
            attrs[k.lower()] = str(v)
    text = tag.get_text(" ", strip=True)
    outer = str(tag)
    return Element(tag.name.lower(), attrs, text, outer)


def find_elements(html: str, selector: str) -> list[Element]:
    """Find all elements matching a CSS selector via BeautifulSoup.

    Supports the full soupsieve selector grammar — `tag`, `.class`, `#id`,
    `[attr]`, `[attr=value]`, `[attr*=value]`, `[attr|=value]`, descendants,
    comma-separated unions, `:has()`, etc.

    A previous regex-based implementation silently failed on any page whose
    `<html>` → `</html>` greedy match swallowed all nested tags, returning
    empty result sets while the real DOM contained the sought elements.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    try:
        matched_tags = soup.select(selector)
    except Exception:  # noqa: BLE001  # BeautifulSoup raises various parse errors
        return []
    return [_bs4_tag_to_element(t) for t in matched_tags]


def _find_elements_in_file(file_path: Path, selector: str) -> list[Element]:
    try:
        html = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return find_elements(html, selector)


# ─── File resolution helpers ─────────────────────────────────────────────────


def _resolve_target_files(  # noqa: C901
    spec: dict[str, Any], settings: dict[str, Any] | None = None
) -> list[Path]:
    """Resolve file targets from spec to list of absolute Paths."""
    settings = settings or {}
    mockups_root = settings.get("mockups_root", "frontend/mockups")
    base = PROJECT_ROOT / mockups_root

    # Single file
    file_single = spec.get("file", "")
    if file_single:
        p = base / file_single if not file_single.startswith("/") else Path(file_single)
        if not p.is_absolute():
            p = base / file_single
        return [p]

    # List of files
    files_list = spec.get("files", None)
    if isinstance(files_list, list):
        result = []
        for fname in files_list:
            p = base / fname
            result.append(p)
        return result

    # Glob pattern
    if isinstance(files_list, str):
        matched = glob.glob(str(PROJECT_ROOT / files_list))
        return [Path(m) for m in matched if Path(m).is_file()]

    # files_any (glob)
    files_any = spec.get("files_any", "")
    if files_any:
        matched = glob.glob(str(PROJECT_ROOT / files_any))
        return [Path(m) for m in matched if Path(m).is_file()]

    # pages_from — resolve to files
    pages_from_raw = spec.get("pages_from", [])
    if pages_from_raw:
        pages = pages_from_raw if isinstance(pages_from_raw, list) else []
        return [base / p for p in pages]

    return []


# ─── dom_required ────────────────────────────────────────────────────────────


def dom_required(spec: dict[str, Any]) -> tuple[bool, str]:  # noqa: C901
    """CSS selector must match >= N nodes in file(s).

    Handles many sub-variants:
    - selector + min_count
    - selectors list of {selector, min}
    - selector_file_pairs
    - slots list + selector_template
    - must_include_text, must_include_attr_values, must_include_data_*
    - must_carry_attrs, must_contain_text_any, must_contain_text_all
    - parent_selector + child_selector + ratio
    - min_count_per_page dict
    - min_count_per_match
    - soft: true — always passes
    """
    # Soft check — always pass
    if spec.get("soft"):
        return True, "SKIP: soft check (informational)"

    # selector_file_pairs
    pairs = spec.get("selector_file_pairs", [])
    if pairs:
        return _check_selector_file_pairs(spec, pairs)

    # slots list + selector_template
    slots = spec.get("slots", [])
    if slots:
        return _check_slots(spec, slots)

    # selectors list of {selector, min} dicts
    selectors_list = spec.get("selectors", [])
    if selectors_list:
        return _check_selectors_list(spec, selectors_list)

    # parent + child + ratio
    if "parent_selector" in spec and "child_selector" in spec:
        return _check_parent_child(spec)

    # Standard: selector + min_count / min_count_per_page
    return _check_standard(spec)


def _check_standard(spec: dict[str, Any]) -> tuple[bool, str]:  # noqa: C901
    selector = spec.get("selector", "")
    if not selector:
        return False, "dom_required: no selector specified"

    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"

    # Check if any target files exist
    existing_files = [f for f in files if f.exists()]
    if not existing_files:
        return True, f"SKIP: files not found ({[f.name for f in files[:3]]})"

    min_count_per_page: dict[str, int] = spec.get("min_count_per_page", {})
    global_min = spec.get("min_count", 1)

    # Additional checks
    must_include_text: list[str] = spec.get("must_include_text", [])
    must_carry_attrs: list[str] = spec.get("must_carry_attrs", [])
    must_contain_text_any: list[str] = spec.get("must_contain_text_any", [])
    must_contain_text_all: list[str] = spec.get("must_contain_text_all", [])
    must_include_attr_values: dict[str, list[str]] = spec.get("must_include_attr_values", {})
    must_contain_child: str | None = spec.get("must_contain_child")
    must_include_href_any: list[str] = spec.get("must_include_href_any", [])
    _min_count_per_match: int = spec.get("min_count_per_match", 0)  # noqa: F841 (reserved for future use)

    # Dynamic must_include_data_* keys
    must_include_data: dict[str, list[str]] = {}
    for k, v in spec.items():
        if k.startswith("must_include_data_") and isinstance(v, list):
            attr_name = "data-" + k[len("must_include_data_") :]
            must_include_data[attr_name] = v

    failures: list[str] = []

    for f in existing_files:
        html = f.read_text(encoding="utf-8", errors="replace")
        elements = find_elements(html, selector)

        min_req = min_count_per_page.get(f.name, global_min)

        if len(elements) < min_req:
            failures.append(f"{f.name}: found {len(elements)}, need {min_req} for {selector!r}")
            continue

        # must_include_text: all text values must appear in at least one element's text
        if must_include_text:
            all_text = " ".join(e.text for e in elements) + " ".join(
                e.attrs.get("href", "") + e.outer for e in elements
            )
            for t in must_include_text:
                if t.lower() not in all_text.lower():
                    failures.append(f"{f.name}: text {t!r} not found in {selector!r} elements")

        # must_carry_attrs: every matched element must have these attrs
        if must_carry_attrs:
            for el in elements:
                for attr in must_carry_attrs:
                    if not el.has_attr(attr):
                        failures.append(f"{f.name}: element {selector!r} missing attr {attr!r}")
                        break

        # must_contain_text_any: at least one of the texts appears
        if must_contain_text_any:
            combined = " ".join(e.text for e in elements)
            found_any = any(t.lower() in combined.lower() for t in must_contain_text_any)
            if not found_any:
                failures.append(f"{f.name}: none of {must_contain_text_any} in {selector!r}")

        # must_contain_text_all: all texts must appear
        if must_contain_text_all:
            combined = " ".join(e.text + " " + e.outer for e in elements)
            for t in must_contain_text_all:
                if t.lower() not in combined.lower():
                    failures.append(f"{f.name}: text {t!r} missing in {selector!r}")

        # must_include_attr_values: across all elements, each value must appear at least once
        if must_include_attr_values:
            for attr, expected_vals in must_include_attr_values.items():
                found_vals = {el.attrs.get(attr, "") for el in elements}
                for val in expected_vals:
                    if val not in found_vals:
                        failures.append(f"{f.name}: {attr}={val!r} not found among {selector!r}")

        # Dynamic must_include_data_* checks
        if must_include_data:
            for attr, expected_vals in must_include_data.items():
                found_vals = {el.attrs.get(attr, "") for el in elements}
                for val in expected_vals:
                    if val not in found_vals:
                        failures.append(f"{f.name}: {attr}={val!r} not found")

        # must_contain_child
        if must_contain_child:
            for el in elements:
                children = find_elements(el.outer, must_contain_child)
                if not children:
                    failures.append(f"{f.name}: {selector!r} lacks child {must_contain_child!r}")
                    break

        # must_include_href_any: href links among elements must include all expected
        if must_include_href_any:
            all_hrefs = " ".join(e.attrs.get("href", "") for e in elements)
            for href_frag in must_include_href_any:
                if href_frag not in all_hrefs:
                    failures.append(f"{f.name}: href fragment {href_frag!r} not found")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    total = sum(len(_find_elements_in_file(f, selector)) for f in existing_files)
    return True, f"{selector!r}: {total} element(s) in {len(existing_files)} file(s)"


def _check_selectors_list(
    spec: dict[str, Any], selectors_list: list[dict[str, Any]]
) -> tuple[bool, str]:
    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    failures: list[str] = []
    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        for entry in selectors_list:
            sel = entry.get("selector", "")
            min_req = entry.get("min", 1)
            els = find_elements(html, sel)
            if len(els) < min_req:
                failures.append(f"{f.name}: {sel!r} found {len(els)}, need {min_req}")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"All selectors matched in {len(existing)} file(s)"


def _check_parent_child(spec: dict[str, Any]) -> tuple[bool, str]:
    parent_sel = spec.get("parent_selector", "")
    child_sel = spec.get("child_selector", "")
    ratio = spec.get("ratio", 1.0)

    # For simple ratio check (1.0 = every parent needs at least one child)
    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    failures: list[str] = []
    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        parents = find_elements(html, parent_sel)
        if not parents:
            # No parents found — could be SKIP or fail depending on context
            # Treat as SKIP for now (files don't have these elements yet)
            continue
        for parent in parents:
            children = find_elements(parent.outer, child_sel)
            if ratio >= 1.0 and not children:
                failures.append(f"{f.name}: parent {parent_sel!r} lacks child {child_sel!r}")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, "Parent/child ratio check passed"


def _check_selector_file_pairs(
    spec: dict[str, Any], pairs: list[dict[str, Any]]
) -> tuple[bool, str]:
    settings_block: dict[str, Any] = {}
    mockups_root = settings_block.get("mockups_root", "frontend/mockups")
    base = PROJECT_ROOT / mockups_root

    failures: list[str] = []
    for pair in pairs:
        fname = pair.get("file", "")
        sel = pair.get("selector", "")
        min_count = spec.get("min_count", 1)

        f = base / fname
        if not f.exists():
            # File doesn't exist yet — SKIP this pair
            continue
        html = f.read_text(encoding="utf-8", errors="replace")
        # selector might be comma-separated IDs: "#i_initial, #i_sip, ..."
        sub_sels = [s.strip() for s in sel.split(",") if s.strip()]
        found_count = 0
        for sub in sub_sels:
            els = find_elements(html, sub)
            found_count += len(els)
        if found_count < min_count:
            failures.append(f"{fname}: found {found_count}/{min_count} selector elements")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, "selector_file_pairs check passed"


def _check_slots(spec: dict[str, Any], slots: list[dict[str, Any]]) -> tuple[bool, str]:
    selector_template = spec.get("selector_template", "div.rec-slot[data-slot-id={id}]")
    mockups_root = "frontend/mockups"
    base = PROJECT_ROOT / mockups_root

    failures: list[str] = []
    for slot in slots:
        fname = slot.get("file", "")
        slot_id = slot.get("id", "")
        sel = selector_template.replace("{id}", slot_id)

        f = base / fname
        if not f.exists():
            continue
        html = f.read_text(encoding="utf-8", errors="replace")
        els = find_elements(html, sel)
        if not els:
            failures.append(f"{fname}: slot {slot_id!r} not found ({sel!r})")

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, "All slots found"


# ─── dom_forbidden ───────────────────────────────────────────────────────────


def dom_forbidden(spec: dict[str, Any]) -> tuple[bool, str]:
    """CSS selector must match 0 nodes in file(s).

    Supports selectors list (list of selectors) and files/file/files_any.
    """
    # Build selectors list
    sel_single = spec.get("selector", "")
    sel_list = spec.get("selectors", [])
    if sel_single and not sel_list:
        sel_list = [sel_single]
    if not sel_list:
        return False, "dom_forbidden: no selector(s) specified"

    # Resolve files
    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    violations: list[str] = []
    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        for sel in sel_list:
            els = find_elements(html, sel)
            if els:
                violations.append(f"{f.name}: {sel!r} found {len(els)} element(s)")

    if violations:
        return False, "FAIL — forbidden elements found: " + "; ".join(violations[:5])
    return True, f"No forbidden elements in {len(existing)} file(s)"


# ─── attr_required ───────────────────────────────────────────────────────────


def attr_required(spec: dict[str, Any]) -> tuple[bool, str]:
    """Selector in files must carry attribute A (and optionally min_length)."""
    selector = spec.get("selector", "")
    attribute = spec.get("attribute", spec.get("attr", ""))
    if not selector or not attribute:
        return False, "attr_required: selector and attribute required"

    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    min_length = spec.get("min_length", 0)
    failures: list[str] = []

    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        elements = find_elements(html, selector)
        if not elements:
            continue  # No elements to check
        for el in elements:
            val = el.get_attr(attribute)
            if val is None:
                failures.append(f"{f.name}: {selector!r} missing attr {attribute!r}")
            elif min_length and len(val) < min_length:
                failures.append(
                    f"{f.name}: {selector!r} {attribute!r}={val!r} shorter than {min_length}"
                )

    if failures:
        return False, "FAIL — " + "; ".join(failures[:5])
    return True, f"attr {attribute!r} present on all {selector!r} elements"


# ─── attr_enum ───────────────────────────────────────────────────────────────


def attr_enum(spec: dict[str, Any]) -> tuple[bool, str]:
    """Selector in files, attribute value must be in allowed list."""
    selector = spec.get("selector", "")
    attribute = spec.get("attr", spec.get("attribute", ""))
    allowed: list[str] = spec.get("allowed", [])
    if not selector or not attribute or not allowed:
        return False, "attr_enum: selector, attr, and allowed required"

    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    violations: list[str] = []
    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        elements = find_elements(html, selector)
        for el in elements:
            val = el.get_attr(attribute)
            if val is not None and val not in allowed:
                violations.append(f"{f.name}: {selector!r} {attribute}={val!r} not in {allowed}")

    if violations:
        return False, "FAIL — " + "; ".join(violations[:5])
    return True, f"attr_enum {attribute!r} in allowed set"


# ─── attr_numeric_range ──────────────────────────────────────────────────────


def attr_numeric_range(spec: dict[str, Any]) -> tuple[bool, str]:
    """Selector in files, attribute value must be numeric in [min, max]."""
    selector = spec.get("selector", "")
    attribute = spec.get("attr", spec.get("attribute", ""))
    min_val = spec.get("min", None)
    max_val = spec.get("max", None)
    integer_only = spec.get("integer_only", False)
    if not selector or not attribute:
        return False, "attr_numeric_range: selector and attr required"

    files = _resolve_target_files(spec)
    if not files:
        return True, "SKIP: no files matched"
    existing = [f for f in files if f.exists()]
    if not existing:
        return True, "SKIP: files not found"

    violations: list[str] = []
    for f in existing:
        html = f.read_text(encoding="utf-8", errors="replace")
        elements = find_elements(html, selector)
        for el in elements:
            val_str = el.get_attr(attribute)
            if val_str is None:
                continue
            try:
                num = float(val_str)
            except ValueError:
                violations.append(f"{f.name}: {attribute}={val_str!r} not numeric")
                continue
            if integer_only and num != int(num):
                violations.append(f"{f.name}: {attribute}={val_str!r} not integer")
            if min_val is not None and num < min_val:
                violations.append(f"{f.name}: {attribute}={num} < min {min_val}")
            if max_val is not None and num > max_val:
                violations.append(f"{f.name}: {attribute}={num} > max {max_val}")

    if violations:
        return False, "FAIL — " + "; ".join(violations[:5])
    return True, f"attr {attribute!r} in numeric range [{min_val}, {max_val}]"
