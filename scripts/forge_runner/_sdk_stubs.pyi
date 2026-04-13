"""Skeleton type stubs for claude_agent_sdk symbols used by forge_runner.

claude_agent_sdk (0.1.58) ships no py.typed marker or bundled stubs.
This file provides minimal type hints so mypy strict mode can resolve
the symbols we import.  Update this file when upgrading the SDK pin
(see version.py::PINNED_SDK_VERSION).

Phase 2 modules (session.py, etc.) will import directly from claude_agent_sdk;
mypy will resolve types via these stubs when checking forge_runner code.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

__version__: str

# ---------------------------------------------------------------------------
# Options / config
# ---------------------------------------------------------------------------

class ClaudeAgentOptions:
    allowed_tools: list[str]
    max_turns: int | None
    cwd: str | None
    permission_mode: str | None
    system_prompt: str | dict[str, Any] | None

    def __init__(
        self,
        *,
        allowed_tools: list[str] | None = ...,
        max_turns: int | None = ...,
        cwd: str | None = ...,
        permission_mode: str | None = ...,
        system_prompt: str | dict[str, Any] | None = ...,
        **kwargs: Any,
    ) -> None: ...

# ---------------------------------------------------------------------------
# Message content blocks
# ---------------------------------------------------------------------------

class TextBlock:
    text: str
    type: str

class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str

class ToolResultBlock:
    tool_use_id: str
    content: str | list[Any]
    type: str

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class AssistantMessage:
    content: list[TextBlock | ToolUseBlock | Any]

class ResultMessage:
    stop_reason: str | None
    usage: Any | None

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ClaudeSDKError(Exception): ...
class CLINotFoundError(ClaudeSDKError): ...
class CLIConnectionError(ClaudeSDKError): ...

class ProcessError(ClaudeSDKError):
    returncode: int | None
    stderr: str | None

# Note: The real SDK (0.1.58) does NOT export AuthenticationError or
# RateLimitError at the top level.  The runner (Phase 2 session.py) will
# detect auth/rate-limit conditions via ProcessError.returncode and
# stderr pattern matching.  These stub names are reserved for forward-
# compat if the SDK adds them in a later version.

class AuthenticationError(ClaudeSDKError): ...
class RateLimitError(ClaudeSDKError): ...

# ---------------------------------------------------------------------------
# Top-level query function
# ---------------------------------------------------------------------------

def query(
    prompt: str,
    options: ClaudeAgentOptions | None = ...,
    **kwargs: Any,
) -> AsyncIterator[AssistantMessage | ResultMessage | Any]: ...
