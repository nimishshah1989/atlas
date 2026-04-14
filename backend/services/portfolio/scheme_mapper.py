"""Scheme name → mstar_id fuzzy mapper.

Pipeline:
1. Check atlas_scheme_mapping_overrides for exact match (short-circuit)
2. Fetch JIP MF universe from de_mf_master (read-only, via JIPMFService)
3. Use rapidfuzz token_sort_ratio for fuzzy matching
4. Holdings with confidence >= 0.70 → mapping_status='mapped'
5. Holdings with confidence < 0.70 → mapping_status='pending' (needs_review)
6. Override matches → confidence=1.0, mapping_status='manual_override'

NEVER writes to any de_* table.
All confidence values are Decimal, never float.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import structlog
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_mf_service import JIPMFService
from backend.db.models import AtlasSchemeMappingOverride
from backend.models.portfolio import MappingStatus

log = structlog.get_logger()

# Minimum confidence score to auto-map (inclusive)
CONFIDENCE_THRESHOLD = Decimal("0.70")


@dataclass
class MappedHolding:
    """Scheme mapping result for a single holding."""

    scheme_name: str
    mstar_id: Optional[str]
    confidence: Decimal
    mapping_status: MappingStatus
    matched_fund_name: Optional[str] = None


def _normalize(name: str) -> str:
    """Normalize a fund name for comparison: lowercase + collapse whitespace."""
    return " ".join(name.lower().split())


def _rapidfuzz_score(query: str, candidate: str) -> Decimal:
    """Compute token_sort_ratio between two normalized strings.

    Args:
        query: scheme name to match
        candidate: fund_name from JIP universe

    Returns:
        Decimal in [0, 1] — NOT the raw 0-100 int from rapidfuzz
    """
    raw_score = fuzz.token_sort_ratio(_normalize(query), _normalize(candidate))
    return Decimal(str(round(raw_score))) / Decimal("100")


async def _load_overrides(session: AsyncSession) -> dict[str, str]:
    """Load all active scheme mapping overrides from DB.

    Returns:
        dict mapping normalized scheme_name_pattern → mstar_id
    """
    stmt = select(AtlasSchemeMappingOverride).where(
        AtlasSchemeMappingOverride.is_deleted.is_(False)
    )
    query_result = await session.execute(stmt)
    overrides = query_result.scalars().all()

    return {_normalize(row.scheme_name_pattern): row.mstar_id for row in overrides}


def _best_fuzzy_match(
    name: str,
    candidates: list[tuple[str, str, str]],
) -> MappedHolding:
    """Find best fuzzy match for a scheme name against the JIP candidate list.

    Args:
        name: original scheme name
        candidates: list of (mstar_id, fund_name, normalized_fund_name)

    Returns:
        MappedHolding with status='mapped' if confidence>=threshold, else 'pending'
    """
    norm_name = _normalize(name)
    best_score = Decimal("0")
    best_mstar_id: Optional[str] = None
    best_fund_name: Optional[str] = None

    for mstar_id, fund_name, norm_candidate in candidates:
        score = _rapidfuzz_score(norm_name, norm_candidate)
        if score > best_score:
            best_score = score
            best_mstar_id = mstar_id
            best_fund_name = fund_name

    mapped = best_score >= CONFIDENCE_THRESHOLD
    return MappedHolding(
        scheme_name=name,
        mstar_id=best_mstar_id if mapped else None,
        confidence=best_score,
        mapping_status=MappingStatus.mapped if mapped else MappingStatus.pending,
        matched_fund_name=best_fund_name if mapped else None,
    )


class SchemeMapper:
    """Maps CAMS scheme names to JIP mstar_ids."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jip = JIPMFService(session)

    async def map_holdings(
        self,
        scheme_names: list[str],
    ) -> list[MappedHolding]:
        """Map a list of scheme names to mstar_ids.

        Args:
            scheme_names: scheme names from CAMS parse (may contain duplicates)

        Returns:
            One MappedHolding per input scheme name, in the same order
        """
        if not scheme_names:
            return []

        overrides = await _load_overrides(self._session)
        log.info("scheme_overrides_loaded", count=len(overrides))

        needs_fuzzy: list[str] = []
        override_results: dict[str, MappedHolding] = {}

        for name in scheme_names:
            if _normalize(name) in overrides:
                override_results[name] = MappedHolding(
                    scheme_name=name,
                    mstar_id=overrides[_normalize(name)],
                    confidence=Decimal("1.0"),
                    mapping_status=MappingStatus.manual_override,
                )
            else:
                needs_fuzzy.append(name)

        log.info("scheme_override_hits", hits=len(override_results), needs_fuzzy=len(needs_fuzzy))

        fuzzy_results: dict[str, MappedHolding] = {}
        if needs_fuzzy:
            universe = await self._jip.get_mf_universe(active_only=False)
            candidates = [
                (row["mstar_id"], row["fund_name"], _normalize(str(row["fund_name"])))
                for row in universe
                if row.get("fund_name") and row.get("mstar_id")
            ]
            log.info("jip_universe_loaded", count=len(candidates))
            for name in needs_fuzzy:
                fuzzy_results[name] = _best_fuzzy_match(name, candidates)

        results = [
            override_results[n] if n in override_results else fuzzy_results[n] for n in scheme_names
        ]
        log.info(
            "scheme_mapping_complete",
            total=len(results),
            mapped=sum(1 for r in results if r.mapping_status == MappingStatus.mapped),
            overrides=sum(1 for r in results if r.mapping_status == MappingStatus.manual_override),
            pending=sum(1 for r in results if r.mapping_status == MappingStatus.pending),
        )
        return results
