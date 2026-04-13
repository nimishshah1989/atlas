#!/usr/bin/env python3
"""plan-to-roadmap.py — append a skeleton chunk entry to orchestrator/roadmap.yaml.

Usage:
    python scripts/plan-to-roadmap.py --chunk C12 --version V2

Behaviour:
- If the chunk already exists under the given version: exits 0 with "already present".
- If the chunk already exists under a DIFFERENT version: exits 1 (conflict).
- Otherwise: appends a skeleton entry under the target version's chunks list.
- Preserves all existing YAML comments and formatting via ruamel.yaml round-trip.
- Idempotent: re-running with the same args is always safe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from orchestrator.roadmap_schema import CHUNK_ID_RE, VERSION_ID_RE  # noqa: E402

ROADMAP_YAML = _REPO_ROOT / "orchestrator" / "roadmap.yaml"


def find_chunk_location(versions: list[Any], chunk_id: str) -> tuple[str | None, int | None]:
    """Return (version_id, chunk_index) if chunk_id is already in any version."""
    for version in versions:
        vid = version.get("id", "")
        chunks = version.get("chunks") or []
        for i, chunk in enumerate(chunks):
            if chunk.get("id") == chunk_id:
                return vid, i
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--chunk", required=True, help="Chunk id, e.g. C12")
    ap.add_argument("--version", required=True, help="Target version, e.g. V2")
    ap.add_argument(
        "--roadmap",
        type=Path,
        default=ROADMAP_YAML,
        help="Path to roadmap.yaml (default: orchestrator/roadmap.yaml)",
    )
    args = ap.parse_args()

    chunk_id: str = args.chunk
    version_id: str = args.version

    # Validate format
    if not CHUNK_ID_RE.match(chunk_id):
        print(
            f"ERROR: chunk id {chunk_id!r} must match C<n> (e.g. C12)",
            file=sys.stderr,
        )
        return 1
    if not VERSION_ID_RE.match(version_id):
        print(
            f"ERROR: version id {version_id!r} must match V<n> (e.g. V2)",
            file=sys.stderr,
        )
        return 1

    roadmap_path: Path = args.roadmap
    if not roadmap_path.exists():
        print(f"ERROR: roadmap not found at {roadmap_path}", file=sys.stderr)
        return 1

    # Load with ruamel.yaml for round-trip (preserves comments + formatting)
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    with open(roadmap_path) as fh:
        data = yaml.load(fh)

    versions = data.get("versions") or []

    # Check if chunk already exists anywhere
    existing_version, _ = find_chunk_location(versions, chunk_id)
    if existing_version is not None:
        if existing_version == version_id:
            print(
                f"already present: chunk {chunk_id!r} is already under {version_id}",
            )
            return 0
        else:
            print(
                f"ERROR: cross-version conflict — chunk {chunk_id!r} already "
                f"assigned to {existing_version}, cannot add to {version_id}",
                file=sys.stderr,
            )
            return 1

    # Find the target version
    target_version = None
    for v in versions:
        if v.get("id") == version_id:
            target_version = v
            break

    if target_version is None:
        print(
            f"ERROR: version {version_id!r} not found in roadmap",
            file=sys.stderr,
        )
        return 1

    # Build skeleton chunk entry
    from ruamel.yaml.comments import CommentedMap

    skeleton = CommentedMap()
    skeleton["id"] = chunk_id
    skeleton["plan_ref"] = True

    # Ensure chunks key exists
    if target_version.get("chunks") is None:
        target_version["chunks"] = CommentedSeq()

    target_version["chunks"].append(skeleton)

    # Write back preserving format
    with open(roadmap_path, "w") as fh:
        yaml.dump(data, fh)

    print(f"Appended chunk {chunk_id!r} skeleton under {version_id} in {roadmap_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
