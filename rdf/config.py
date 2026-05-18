"""RDF configuration — loaded from config.toml in the project directory."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        print("ERROR: Install tomli (`pip install tomli`) or use Python >= 3.11")
        sys.exit(1)


@dataclass
class AgentConfig:
    """Configuration for a specific agent role/complexity."""
    adapter: str
    model: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    # --- dynamic agents ---
    # maps "role" -> { "complexity" -> AgentConfig }
    # e.g. agents["executor"]["low"]
    agents: Dict[str, Dict[str, AgentConfig]] = field(default_factory=dict)

    # --- roles (legacy/defaults) ---
    planner_model: str = "gemini-2.5-pro"
    planner_adapter: str = "gemini"
    executor_adapter: str = "claude-code"

    # --- executor (claude-code) ---
    allowed_tools: str = "Read,Write,Edit,Bash"
    dangerously_skip_permissions: bool = False

    # --- limits ---
    max_iterations: int = 100
    max_state_tokens: int = 8000
    planner_timeout_sec: int = 180
    executor_timeout_sec: Optional[int] = 14400
    max_retries_on_parse_fail: int = 2
    max_retries_on_state_too_long: int = 2
    max_log_entries: int = 30

    # --- agent routing ---
    default_complexity: str = "medium"
    max_depth: int = 4

    # --- cache ---
    cache_ttl_hours: int = 6
    min_cache_tokens: int = 32768

    # --- git ---
    auto_commit: bool = True
    auto_push: bool = False

    # --- ui ---
    verbose: bool = True

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            d = tomllib.load(f)
        c = cls()

        # [agents] section (Dynamic configuration)
        # Structure: [agents.<role>.<complexity>]
        agents_data = d.get("agents", {})
        for role, complexities in agents_data.items():
            if not isinstance(complexities, dict):
                continue
            c.agents[role] = {}
            for comp, data in complexities.items():
                if not isinstance(data, dict):
                    continue
                adapter = data.get("adapter")
                model = data.get("model")
                if adapter and model:
                    # Extract all other keys as params
                    params = {k: v for k, v in data.items() if k not in ("adapter", "model")}
                    c.agents[role][comp] = AgentConfig(
                        adapter=adapter,
                        model=model,
                        params=params
                    )

        # [roles] section (Legacy / Top-level fallback)
        roles = d.get("roles", {})
        c.planner_model = roles.get("planner_model", c.planner_model)
        c.planner_adapter = roles.get("planner_adapter", c.planner_adapter)
        c.executor_adapter = roles.get("executor_adapter", c.executor_adapter)

        # [models] section (Phase 1 backward-compat alias)
        m = d.get("models", {})
        c.planner_model = m.get("strategy", c.planner_model)
        # implementation_cli kept as alias — maps to executor_adapter
        if "implementation_cli" in m:
            c.executor_adapter = m["implementation_cli"]

        # [claude_code] section
        cc = d.get("claude_code", {})
        c.allowed_tools = cc.get("allowed_tools", c.allowed_tools)
        c.dangerously_skip_permissions = cc.get(
            "dangerously_skip_permissions", c.dangerously_skip_permissions
        )

        # [limits] section
        lim = d.get("limits", {})
        c.max_iterations = lim.get("max_iterations", c.max_iterations)
        c.max_state_tokens = lim.get("max_state_tokens", c.max_state_tokens)
        c.planner_timeout_sec = lim.get("planner_timeout_sec", c.planner_timeout_sec)
        c.executor_timeout_sec = lim.get("executor_timeout_sec", c.executor_timeout_sec)
        c.max_retries_on_parse_fail = lim.get(
            "max_retries_on_parse_fail", c.max_retries_on_parse_fail
        )
        c.max_retries_on_state_too_long = lim.get(
            "max_retries_on_state_too_long", c.max_retries_on_state_too_long
        )
        c.max_log_entries = lim.get("max_log_entries", c.max_log_entries)

        # [agent_routing] section
        ar = d.get("agent_routing", {})
        c.default_complexity = ar.get("default_complexity", c.default_complexity)
        c.max_depth = ar.get("max_depth", c.max_depth)

        # [cache] section
        ch = d.get("cache", {})
        c.cache_ttl_hours = ch.get("ttl_hours", c.cache_ttl_hours)
        c.min_cache_tokens = ch.get("min_cache_tokens", c.min_cache_tokens)

        # [git] section
        g = d.get("git", {})
        c.auto_commit = g.get("auto_commit", c.auto_commit)
        c.auto_push = g.get("auto_push", c.auto_push)

        # [ui] section
        u = d.get("ui", {})
        c.verbose = u.get("verbose", c.verbose)

        return c
