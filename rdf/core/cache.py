"""Gemini context caching for the planner's system prompt + stable content."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console(highlight=False, legacy_windows=False)

_CACHE_FILE = Path(".rdf_cache.json")


def get_or_create_cache(
    root: Path,
    model: str,
    ttl_hours: int,
    min_cache_tokens: int,
    system_prompt: str,
    tools: list,
) -> Any:
    """Return a Gemini CachedContent (with tools embedded) or None (silent fallback)."""
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        return None

    goal = (root / "goal.md").read_text(encoding="utf-8")
    log_path = root / "experiment_log.md"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    entries = log.split("\n---\n")
    older = "\n---\n".join(entries[:-3]) if len(entries) > 3 else ""
    stable_content = f"# GOAL\n{goal}\n\n# OLDER LOG\n{older}"

    total_chars = len(system_prompt) + len(stable_content)
    threshold_chars = min_cache_tokens * 4
    if total_chars < threshold_chars:
        console.print(
            f"[dim]Cache skipped: {total_chars//4:,} tokens < {min_cache_tokens:,} threshold "
            f"(grows into caching when content exceeds {min_cache_tokens:,} tokens)[/dim]"
        )
        return None

    # "tools_v1" prefix in hash so caches without tools are never reused
    h = hashlib.sha256(
        ("tools_v1" + system_prompt + stable_content).encode()
    ).hexdigest()[:16]

    state: dict = {}
    if _CACHE_FILE.exists():
        try:
            state = json.loads(_CACHE_FILE.read_text())
        except Exception:
            pass

    client = genai.Client()

    if state.get("hash") == h:
        try:
            return client.caches.get(name=state["cache_name"])
        except Exception:
            pass

    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=stable_content)],
                    )
                ],
                tools=tools,
                ttl=f"{ttl_hours * 3600}s",
                display_name=f"rdf-{root.name}-{h}",
            ),
        )
        _CACHE_FILE.write_text(json.dumps({"hash": h, "cache_name": cache.name}))
        # Gemini charges cache storage at ~$4.50/M tokens/hour on top of per-call fees.
        cache_tokens = len(system_prompt + stable_content) // 4
        storage_cost_est = cache_tokens / 1_000_000 * 4.50 * ttl_hours
        console.print(
            f"[dim]Cache created: ~{cache_tokens:,} tokens × {ttl_hours}h TTL "
            f"≈ ~${storage_cost_est:.3f} storage[/dim]"
        )
        return cache
    except Exception as e:
        console.print(
            f"[yellow]Cache creation failed (uncached fallback): {e}[/yellow]"
        )
        return None
