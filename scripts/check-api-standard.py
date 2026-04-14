#!/usr/bin/env python3
"""Run ATLAS API design standard criteria against the live backend.

Loads docs/specs/api-standard-criteria.yaml and probes each criterion
against http://127.0.0.1:8010 (override with ATLAS_API_BASE). Exits 0 if
all criteria pass, 1 otherwise. Used as the gating check for any chunk
that touches backend/routes/ — see CLAUDE.md "API design standard".

Criteria are cross-cutting (orthogonal to V1/V2 slices) and encode
spec §17 (Unified Query Layer) + §18 (Include system) + §20 (API
principles). V2-UQL-AGG is the chunk that must flip these green.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = ROOT / "docs" / "specs" / "api-standard-criteria.yaml"
BASE = os.environ.get("ATLAS_API_BASE", "http://127.0.0.1:8010").rstrip("/")
TIMEOUT = 5.0


def _http(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "atlas-api-standard/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:  # noqa: BLE001
            return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, {"_transport_error": str(exc)[:120]}


def _json_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _first_record(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    for key in ("records", "data", "rows", "items"):
        val = body.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0]
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return None


def probe_http_post(probe: dict[str, Any]) -> tuple[bool, str]:
    url = f"{BASE}{probe['url']}"
    status, body = _http("POST", url, probe.get("payload"))
    want = probe.get("expect_status", 200)
    if status != want:
        return False, f"POST {probe['url']} → {status} (want {want})"
    for key in probe.get("expect_keys_in_first_record", []):
        rec = _first_record(body)
        if rec is None or key not in rec:
            return False, f"missing key '{key}' in first record"
    jp = probe.get("expect_json_path")
    if jp and _json_path(body, jp) is None:
        return False, f"missing JSON path '{jp}'"
    return True, f"POST {probe['url']} → {status}"


def probe_http_get(probe: dict[str, Any]) -> tuple[bool, str]:
    url = f"{BASE}{probe['url']}"
    status, body = _http("GET", url)
    want = probe.get("expect_status", 200)
    if status != want:
        return False, f"GET {probe['url']} → {status} (want {want})"
    jp = probe.get("expect_json_path")
    if jp and _json_path(body, jp) is None:
        return False, f"missing JSON path '{jp}'"
    return True, f"GET {probe['url']} → {status}"


def probe_static_import(probe: dict[str, Any]) -> tuple[bool, str]:
    module_glob = probe["module_glob"]
    importer_path = ROOT / probe["importer"]
    matches = list(ROOT.glob(module_glob)) + list(ROOT.glob(module_glob + ".py"))
    if not matches:
        return False, f"no files match {module_glob}"
    if not importer_path.exists():
        return False, f"importer {probe['importer']} missing"
    text = importer_path.read_text(encoding="utf-8", errors="replace")
    # Convert module_glob to a dotted-path fragment: backend/services/uql* → backend.services.uql
    dotted = re.sub(r"[/\\]", ".", module_glob).rstrip("*").rstrip(".")
    if dotted not in text:
        return False, f"{probe['importer']} does not import {dotted}"
    return True, f"{probe['importer']} imports {dotted}"


PROBES = {
    "http_post": probe_http_post,
    "http_get": probe_http_get,
    "static_import": probe_static_import,
}


def main() -> int:
    if not CRITERIA_PATH.exists():
        print(f"FAIL: {CRITERIA_PATH} not found", file=sys.stderr)
        return 1
    doc = yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8"))
    criteria = doc.get("criteria", [])
    results: list[tuple[str, bool, str, str]] = []
    for c in criteria:
        cid = c["id"]
        probe = c.get("probe", {})
        fn = PROBES.get(probe.get("type", ""))
        if fn is None:
            results.append((cid, False, c["title"], f"unknown probe type {probe.get('type')!r}"))
            continue
        try:
            ok, evidence = fn(probe)
        except Exception as exc:  # noqa: BLE001
            ok, evidence = False, f"probe raised: {str(exc)[:120]}"
        results.append((cid, ok, c["title"], evidence))

    passed = sum(1 for _, ok, *_ in results if ok)
    total = len(results)
    width = max(len(r[0]) for r in results) if results else 0
    print(f"\nATLAS API design standard — {passed}/{total} criteria passing")
    print(f"Source: {doc.get('source', '?')}")
    print(f"Base:   {BASE}\n")
    for cid, ok, title, evidence in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {cid.ljust(width)}  {title}")
        print(f"         └─ {evidence}")
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
