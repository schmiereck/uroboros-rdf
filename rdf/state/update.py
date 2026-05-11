"""State file management: read and update current_state.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Awaitable

from rich.console import Console

from rdf.config import Config
from rdf.state.log import tokens

console = Console(highlight=False, legacy_windows=False)

# Type alias for the async planner call injected by the Orchestrator
AsyncPlannerCall = Callable[..., Awaitable[tuple[dict, Any]]]


async def update_state(
    root: Path,
    new_state: str,
    cfg: Config,
    planner_call: AsyncPlannerCall,
    delta: str,
) -> None:
    """Write *new_state* to current_state.md.

    If the text exceeds cfg.max_state_tokens, call the planner to produce a
    shorter version. Hard-truncates with a [truncated] marker as last resort.

    *planner_call* is an async callable with signature
    ``async (root, prompt, cfg) -> (data_dict, usage)``.
    """
    state_path = root / "current_state.md"
    if tokens(new_state) <= cfg.max_state_tokens:
        state_path.write_text(new_state, encoding="utf-8")
        return

    for _ in range(cfg.max_retries_on_state_too_long):
        shorten = (
            f"{delta}\n\nThe proposed state_update has {tokens(new_state)} tokens "
            f"(max {cfg.max_state_tokens}). Please provide a shorter version "
            f"that preserves all key findings."
        )
        try:
            data, _ = await planner_call(root, shorten, cfg)
            new_state = data.get("state_update", new_state)
            if tokens(new_state) <= cfg.max_state_tokens:
                state_path.write_text(new_state, encoding="utf-8")
                return
        except Exception:
            break

    truncated = new_state[: cfg.max_state_tokens * 4] + "\n\n[truncated]"
    state_path.write_text(truncated, encoding="utf-8")
    console.print("[yellow]WARNING: current_state.md truncated to fit token limit.[/yellow]")
