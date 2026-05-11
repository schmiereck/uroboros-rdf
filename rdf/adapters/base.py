"""Abstract adapter interfaces for planner and executor roles.

PlannerAdapter wraps a model used for strategy/orchestration (long context,
tool calling, structured output).

ExecutorAdapter wraps a model used for implementation (file system access,
code execution, streaming output).

Adding a new model backend means implementing one or both protocols and
registering it in rdf/agents/router.py — no changes elsewhere.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------

@dataclass
class ToolDeclaration:
    """Model-agnostic description of a tool that the planner can call."""
    name: str
    description: str
    parameters: dict  # JSON Schema for the parameters object


@dataclass
class UsageStats:
    """Token usage reported by a planner call."""
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0


@dataclass
class PlanResult:
    """Result of a single planner completion (after all tool rounds finish)."""
    text: str
    usage: Any = None  # raw model-specific metadata; pass to UsageStats helpers


@dataclass
class ExecResult:
    """Result of an executor run."""
    output: str = ""
    errors: list[str] = field(default_factory=list)
    result: dict = field(default_factory=dict)  # parsed YAML from executor output


# ---------------------------------------------------------------------------
# Tool dispatcher type
# ---------------------------------------------------------------------------

# A dispatcher is an async callable: (tool_name, args_dict) → result_string.
# The planner adapter calls this during its internal tool-call loop.
AsyncToolDispatcher = Callable[[str, dict], "asyncio.Future[str]"]


# ---------------------------------------------------------------------------
# Adapter protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class PlannerAdapter(Protocol):
    """Adapter for a model in the planning / orchestration role.

    Required model capabilities: tool calling, long context, structured output.

    The adapter is responsible for running the full tool-call loop internally:
    it calls the model, dispatches any tool calls via *dispatcher*, appends
    results, and repeats until the model produces a final text response.
    """

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tool_declarations: list[ToolDeclaration],
        dispatcher: AsyncToolDispatcher | None = None,
        cache_hint: str | None = None,
    ) -> PlanResult:
        """Run a completion, handling tool calls internally.

        Args:
            system: System prompt / instruction text.
            messages: Conversation history (role/content dicts).
            tool_declarations: Tools the model may call.
            dispatcher: Async callable for tool execution. If None, tool
                calls from the model are ignored and the text is returned as-is.
            cache_hint: Opaque string the adapter may use to identify a cached
                context (e.g. a Gemini cache name hash). Ignored if the adapter
                does not support caching.
        """
        ...


@runtime_checkable
class ExecutorAdapter(Protocol):
    """Adapter for a model in the execution / implementation role.

    Required model capabilities: file system access, code execution, streaming.
    """

    async def execute(
        self,
        task: str,
        cwd: Path,
        allowed_tools: list[str],
        model_override: str | None = None,
        timeout_sec: float | None = None,
    ) -> ExecResult:
        """Run an implementation task.

        Args:
            task: Full task description / prompt.
            cwd: Working directory for the executor process.
            allowed_tools: Tool names the executor is permitted to use.
            model_override: Optional model identifier overriding the adapter's
                default (useful for complexity routing).
            timeout_sec: Hard timeout; None means unlimited.
        """
        ...
