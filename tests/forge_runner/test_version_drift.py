"""T050: SDK version drift detection (US6, FR-039).

Imports ``claude_agent_sdk``, reads its version (via ``__version__`` attribute
with an ``importlib.metadata`` fallback), and asserts it equals
``scripts.forge_runner.version.PINNED_SDK_VERSION``.

If the installed SDK version drifts from the pin, this test fails loudly and
points the operator at the research document where the pinning rationale lives.

Reference: specs/003-forge-runner/research.md §10
"""

from __future__ import annotations

import importlib.metadata

import pytest


# ---------------------------------------------------------------------------
# Version retrieval helpers
# ---------------------------------------------------------------------------


def _get_installed_sdk_version() -> str | None:
    """Return the installed claude-agent-sdk version string, or None if not found."""
    try:
        import claude_agent_sdk  # type: ignore[import-untyped]

        ver = getattr(claude_agent_sdk, "__version__", None)
        if ver is not None:
            return str(ver)
    except ImportError:
        pass

    # Fall back to importlib.metadata
    try:
        return importlib.metadata.version("claude-agent-sdk")
    except importlib.metadata.PackageNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVersionDrift:
    def test_pinned_sdk_version_constant_is_set(self) -> None:
        """PINNED_SDK_VERSION must be a non-empty string."""
        from scripts.forge_runner.version import PINNED_SDK_VERSION

        assert isinstance(PINNED_SDK_VERSION, str)
        assert PINNED_SDK_VERSION, "PINNED_SDK_VERSION must not be empty"

    def test_installed_sdk_version_matches_pin(self) -> None:
        """Installed claude-agent-sdk version must match PINNED_SDK_VERSION.

        If this test fails, the SDK was upgraded without updating the pin.
        To fix: install the correct version or update PINNED_SDK_VERSION in
        scripts/forge_runner/version.py and document the change.

        See: specs/003-forge-runner/research.md §10 for version-pinning rationale.
        """
        from scripts.forge_runner.version import PINNED_SDK_VERSION

        installed = _get_installed_sdk_version()

        if installed is None:
            pytest.fail(
                "claude-agent-sdk is not installed or its version cannot be determined. "
                "Run: pip install -r requirements-dev.txt"
            )

        assert installed == PINNED_SDK_VERSION, (
            f"\n\nSDK VERSION DRIFT DETECTED\n"
            f"  Installed : {installed!r}\n"
            f"  Pinned    : {PINNED_SDK_VERSION!r}\n\n"
            f"This mismatch may cause subtle behaviour changes in the forge-runner.\n"
            f"Either:\n"
            f"  (a) Pin the installed version:  "
            f"pip install claude-agent-sdk=={PINNED_SDK_VERSION}\n"
            f"  (b) Update the pin intentionally: edit "
            f"scripts/forge_runner/version.py::PINNED_SDK_VERSION\n\n"
            f"See specs/003-forge-runner/research.md §10 for rationale."
        )

    def test_check_sdk_version_does_not_raise(self) -> None:
        """check_sdk_version() must complete without raising (it only logs)."""
        from scripts.forge_runner.version import check_sdk_version

        # Should not raise regardless of drift state
        check_sdk_version()
