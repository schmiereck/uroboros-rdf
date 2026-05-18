"""Complexity-based agent routing: maps a complexity label to an executor adapter."""

from __future__ import annotations

from pathlib import Path

import yaml

from rdf.adapters import create_adapter
from rdf.adapters.claude_code import ClaudeCodeExecutorAdapter
from rdf.adapters.openrouter import OpenRouterExecutorAdapter
from rdf.agents.executor import Executor
from rdf.config import Config


def model_for_complexity(complexity: str, cfg: Config) -> str:
    """Return the model name for a given complexity label."""
    # Try dynamic config first
    agent_cfg = cfg.agents.get("executor", {}).get(complexity)
    if agent_cfg:
        return agent_cfg.model
    
    # Fallback to legacy hardcoded map
    legacy_map = {
        "low": "qwen/qwen3.6-35b-a3b",
        "medium": "claude-sonnet-4-6",
        "high": "claude-opus-4-7",
    }
    return legacy_map.get(complexity, legacy_map.get(cfg.default_complexity, "claude-sonnet-4-6"))


def make_executor(complexity: str, cfg: Config) -> Executor:
    """Return an Executor configured for the given complexity level."""
    agent_cfg = cfg.agents.get("executor", {}).get(complexity)
    
    if agent_cfg:
        adapter = create_adapter(agent_cfg)
    else:
        # Fallback to legacy logic
        model = model_for_complexity(complexity, cfg)
        if "claude" in model.lower():
            adapter = ClaudeCodeExecutorAdapter(model)
        else:
            adapter = OpenRouterExecutorAdapter(model)

    return Executor(adapter)
