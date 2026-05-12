"""GeminiPlannerAdapter — wraps google.genai for the planner role."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from rich.console import Console

from rdf.adapters.base import AsyncToolDispatcher, PlanResult, ToolDeclaration
from rdf.config import Config
from rdf.core.cache import get_or_create_cache

console = Console(highlight=False, legacy_windows=False)


def _to_gemini_tools(declarations: list[ToolDeclaration]) -> list:
    """Convert generic ToolDeclaration list to Gemini FunctionDeclarations."""
    from google.genai import types  # type: ignore

    def _schema(params: dict) -> "types.Schema":
        props = params.get("properties", {})
        required = params.get("required", [])
        gemini_props = {}
        for name, spec in props.items():
            t = spec.get("type", "string").upper()
            gemini_type = getattr(types.Type, t, types.Type.STRING)
            gemini_props[name] = types.Schema(
                type=gemini_type,
                description=spec.get("description", ""),
            )
        return types.Schema(
            type=types.Type.OBJECT,
            properties=gemini_props,
            required=required or None,
        )

    fds = [
        types.FunctionDeclaration(
            name=d.name,
            description=d.description,
            parameters=_schema(d.parameters),
        )
        for d in declarations
    ]
    return [types.Tool(function_declarations=fds)]


async def _call_with_tools_async(
    client: Any,
    model: str,
    history: list,
    gen_cfg: Any,
    dispatcher: AsyncToolDispatcher | None,
    max_rounds: int = 50,
) -> tuple[str, Any]:
    """Async tool-call loop: generate → dispatch tools → repeat until text."""
    from google.genai import types  # type: ignore

    usage_meta = None
    resp = None
    for _ in range(max_rounds):
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=history,
            config=gen_cfg,
        )
        usage_meta = resp.usage_metadata
        fcs = resp.function_calls or []
        if not fcs:
            return resp.text or "", usage_meta

        history.append(resp.candidates[0].content)
        parts = []
        for fc in fcs:
            console.print(f"[dim]  ↳ tool: {fc.name}({dict(fc.args)})[/dim]")
            if dispatcher is not None:
                result = await dispatcher(fc.name, dict(fc.args))
            else:
                result = f"Tool not available: {fc.name}"
            parts.append(
                types.Part.from_function_response(
                    name=fc.name, response={"result": result}
                )
            )
        history.append(types.Content(role="user", parts=parts))

    return (resp.text or "") if resp else "", usage_meta


class GeminiPlannerAdapter:
    """Planner adapter backed by Google Gemini (google.genai)."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._system_prompt: str | None = None

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tool_declarations: list[ToolDeclaration],
        dispatcher: AsyncToolDispatcher | None = None,
        cache_hint: str | None = None,
    ) -> PlanResult:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        cfg = self._cfg
        client = genai.Client()
        gemini_tools = _to_gemini_tools(tool_declarations)
        cache = get_or_create_cache(
            # cache_hint is the project root path encoded as string
            _hint_to_root(cache_hint),
            cfg,
            system,
            gemini_tools,
        ) if cache_hint else None

        def _role(r: str) -> str:
            return "model" if r == "assistant" else r

        history = [
            types.Content(
                role=_role(m["role"]),
                parts=[types.Part.from_text(text=m["content"])]
                if isinstance(m["content"], str)
                else m["content"],
            )
            for m in messages
        ]

        for attempt in range(3):
            try:
                if cache:
                    gen_cfg = types.GenerateContentConfig(
                        cached_content=cache.name
                    )
                else:
                    gen_cfg = types.GenerateContentConfig(
                        system_instruction=system, tools=gemini_tools
                    )

                text, usage_meta = await _call_with_tools_async(
                    client, cfg.planner_model, history, gen_cfg, dispatcher
                )
                return PlanResult(text=text, usage=usage_meta)

            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    console.print(
                        f"[yellow]Gemini error (retry {attempt + 1}): {e}. "
                        f"Waiting {wait}s...[/yellow]"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("GeminiPlannerAdapter.complete exhausted retries")


def _hint_to_root(hint: str | None):
    """Convert a cache_hint string (the project root path) back to a Path."""
    from pathlib import Path
    return Path(hint) if hint else Path(".")
