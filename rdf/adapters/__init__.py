"""Adapter registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Type

from .gemini import GeminiPlannerAdapter
from .claude_code import ClaudeCodeExecutorAdapter
from .openrouter import OpenRouterPlannerAdapter, OpenRouterExecutorAdapter

if TYPE_CHECKING:
    from rdf.config import AgentConfig


ADAPTER_CLASSES: Dict[str, Type[Any]] = {
    "GeminiPlannerAdapter": GeminiPlannerAdapter,
    "ClaudeCodeExecutorAdapter": ClaudeCodeExecutorAdapter,
    "OpenRouterPlannerAdapter": OpenRouterPlannerAdapter,
    "OpenRouterExecutorAdapter": OpenRouterExecutorAdapter,
}


def create_adapter(config: AgentConfig) -> Any:
    """Create and initialize an adapter instance from an AgentConfig."""
    cls = ADAPTER_CLASSES.get(config.adapter)
    if not cls:
        raise ValueError(f"Unknown adapter class: {config.adapter}")
    
    # Instantiate with model and any extra params from the config
    return cls(model=config.model, **config.params)
