"""Tests for V1 completion validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestValidateV1Completion:
    """Tests for the validation script."""

    def test_script_exists(self) -> None:
        script = ROOT / "scripts" / "validate-v1-completion.py"
        assert script.exists(), "validate-v1-completion.py not found"

    def test_criteria_yaml_exists(self) -> None:
        path = ROOT / "docs" / "specs" / "v1-criteria.yaml"
        assert path.exists(), "v1-criteria.yaml not found"

    def test_criteria_yaml_has_15_entries(self) -> None:
        import yaml

        path = ROOT / "docs" / "specs" / "v1-criteria.yaml"
        data = yaml.safe_load(path.read_text())
        assert len(data["criteria"]) == 15

    def test_product_dim_is_gating(self) -> None:
        if str(ROOT / ".quality") not in sys.path:
            sys.path.insert(0, str(ROOT / ".quality"))
        from dimensions.product import dim_product

        result = dim_product()
        assert result.gating is True, "Product dim must be gating=True"

    def test_criteria_use_7day_interval(self) -> None:
        """v1-07 and v1-12 must use 7-day window, not 1-day."""
        import yaml

        path = ROOT / "docs" / "specs" / "v1-criteria.yaml"
        data = yaml.safe_load(path.read_text())
        criteria_by_id = {c["id"]: c for c in data["criteria"]}

        c07 = criteria_by_id["v1-07"]["check"]["query"]
        c12 = criteria_by_id["v1-12"]["check"]["query"]
        assert "interval '7 days'" in c07, f"v1-07 must use 7-day interval, got: {c07}"
        assert "interval '7 days'" in c12, f"v1-12 must use 7-day interval, got: {c12}"

    def test_plan_yaml_product_gating_true(self) -> None:
        """orchestrator/plan.yaml must have product: true in gating section."""
        import yaml

        path = ROOT / "orchestrator" / "plan.yaml"
        data = yaml.safe_load(path.read_text())
        gating = data["settings"]["quality"]["gating"]
        assert gating["product"] is True, "plan.yaml gating.product must be true"
        assert gating["backend"] is True, "plan.yaml gating.backend must be true"


class TestEmbeddingFaultTolerance:
    """Test that store_finding works without embedding service."""

    def test_store_finding_handles_embedding_error(self) -> None:
        """Verify the embedding fault-tolerance code path exists in store_finding."""
        import inspect

        from backend.services.intelligence import store_finding

        source = inspect.getsource(store_finding)
        assert "EmbeddingError" in source, "store_finding must handle EmbeddingError"
        assert "embedding_unavailable" in source, "store_finding must log embedding_unavailable"
        assert "embedding_vector is not None" in source, (
            "store_finding must conditionally skip embedding UPDATE"
        )

    def test_embedding_error_is_imported(self) -> None:
        """EmbeddingError must be importable from intelligence module's imports."""
        import inspect

        import backend.services.intelligence as intel_mod

        source = inspect.getsource(intel_mod)
        assert "from backend.services.embedding import EmbeddingError, embed" in source, (
            "EmbeddingError must be explicitly imported"
        )
