"""Planner agent: calls the PlannerAdapter and handles YAML parsing with retry."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from rdf.adapters.base import AsyncToolDispatcher, PlanResult
from rdf.config import Config
from rdf.core.prompts import build_system_prompt
from rdf.iter_id import top_level_count

console = Console(highlight=False, legacy_windows=False)


def _parse_yaml_block(text: str) -> dict:
    """Extract and parse the first ```yaml...``` block from text.

    Prefers the first match (planner is instructed to put YAML first).
    Falls back to parsing from the first opening fence when truncated.
    """
    matches = re.findall(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return yaml.safe_load(matches[0])
    opens = list(re.finditer(r"```yaml\s*\n", text))
    if opens:
        return yaml.safe_load(text[opens[0].end():])
    raise yaml.YAMLError("No yaml block found in response")


class Planner:
    """Wraps a PlannerAdapter with YAML parsing, retry logic, and tool dispatch."""

    def __init__(self, adapter: Any, dispatcher_factory: Any = None) -> None:
        self._adapter = adapter
        self._dispatcher_factory = dispatcher_factory
        self._system_prompt: str | None = None

    def _prompt(self, root: Path, cfg: Config) -> str:
        if self._system_prompt is None:
            self._system_prompt = build_system_prompt(root, cfg.min_cache_tokens * 4)
        return self._system_prompt

    def call(
        self,
        root: Path,
        delta: str,
        cfg: Config,
        hint: str | None = None,
        chosen_q: str | None = None,
    ) -> tuple[dict, Any]:
        """Synchronous wrapper — runs call_async in a thread if a loop is running."""
        import asyncio
        import concurrent.futures
        try:
            asyncio.get_running_loop()
            # Inside a running loop: run in a background thread with its own loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run, self.call_async(root, delta, cfg, hint, chosen_q)
                ).result()
        except RuntimeError:
            return asyncio.run(self.call_async(root, delta, cfg, hint, chosen_q))

    async def call_async(
        self,
        root: Path,
        delta: str,
        cfg: Config,
        hint: str | None = None,
        chosen_q: str | None = None,
    ) -> tuple[dict, Any]:
        from rdf.tools.declarations import ALL_TOOL_DECLARATIONS, READ_TOOL_DECLARATIONS

        system_prompt = self._prompt(root, cfg)
        if hint:
            delta += f"\n\n## User Hint\n{hint}"
        if chosen_q:
            delta += f"\n\n## Focus Question\n{chosen_q}"

        dispatcher = (
            self._dispatcher_factory(root) if self._dispatcher_factory else None
        )
        tool_declarations = ALL_TOOL_DECLARATIONS if dispatcher else READ_TOOL_DECLARATIONS

        messages = [{"role": "user", "content": delta}]

        for attempt in range(3):
            try:
                plan_result = await self._adapter.complete(
                    system=system_prompt,
                    messages=messages,
                    tool_declarations=tool_declarations,
                    dispatcher=dispatcher,
                    cache_hint=str(root),
                )

                text = plan_result.text
                usage_meta = plan_result.usage

                for parse_attempt in range(cfg.max_retries_on_parse_fail + 1):
                    try:
                        return _parse_yaml_block(text), usage_meta
                    except yaml.YAMLError as ye:
                        if parse_attempt >= cfg.max_retries_on_parse_fail:
                            raise
                        console.print(
                            "[yellow]YAML parse failed – retrying with correction prompt[/yellow]"
                        )
                        console.print(f"[dim]  Reason: {str(ye)[:200]}[/dim]")
                        tail = (text or "")[-800:]
                        console.print(
                            f"[dim]  Response tail (last 800 chars):\n{tail}[/dim]"
                        )
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": (
                            "Your previous response did not contain a valid ```yaml``` block. "
                            "Please respond again starting immediately with the YAML block "
                            "(```yaml ... ```) as the very first thing in your response."
                        )})
                        plan_result = await self._adapter.complete(
                            system=system_prompt,
                            messages=messages,
                            tool_declarations=tool_declarations,
                            dispatcher=dispatcher,
                            cache_hint=str(root),
                        )
                        text = plan_result.text
                        usage_meta = plan_result.usage

            except yaml.YAMLError:
                raise
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    console.print(
                        f"[yellow]Planner error (retry {attempt + 1}): {e}. "
                        f"Waiting {wait}s...[/yellow]"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("Planner.call_async exhausted retries")


class MockPlanner:
    """Dry-run planner returning hardcoded hypotheses."""

    _HYPS = [
        "[mock] baseline: cosine-LR lr=1e-4 achieves val_loss < 3.5 at 1k steps",
        "[mock] warmup-500: adding 500-step warmup reduces val_loss by >=2%",
        "[mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0",
    ]

    async def call_async(
        self,
        root: Path,
        delta: str,
        cfg: Config,
        hint: str | None = None,
        chosen_q: str | None = None,
    ) -> tuple[dict, Any]:
        return await self._mock_data(root)

    def call(
        self,
        root: Path,
        delta: str,
        cfg: Config,
        hint: str | None = None,
        chosen_q: str | None = None,
    ) -> tuple[dict, Any]:
        import concurrent.futures
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.call_async(root, delta, cfg, hint, chosen_q)).result()
        except RuntimeError:
            return asyncio.run(self.call_async(root, delta, cfg, hint, chosen_q))

    async def _mock_data(self, root: Path) -> tuple[dict, Any]:
        n = top_level_count(root) + 1
        hyp = self._HYPS[min(n - 1, len(self._HYPS) - 1)]

        # Simulate executor running (write stub script)
        src_dir = root / "src"
        src_dir.mkdir(exist_ok=True)
        script = src_dir / f"run_iter_{n:03d}.py"
        script.write_text(f'print("hello from iter {n}")\n', encoding="utf-8")

        data = {
            "analysis": f"[Mock] Iteration {n}. All systems nominal.",
            "open_questions": [
                "Mock question A?",
                "Mock question B?",
                "Mock question C?",
            ],
            "chosen_direction": "Mock direction",
            "hypothesis": hyp,
            "rationale": "[Mock] This is the most promising direction.",
            "status": "ok",
            "metrics": {"mock_value": round(n * 1.5, 3)},
            "experimenter_view": f"[Mock] Iteration {n} executed successfully.",
            "notes": "[Mock] dry-run",
            "artifacts": [f"src/run_iter_{n:03d}.py"],
            "state_update": (
                f"# Current State (Mock)\n\nIteration {n} complete.\n"
                f"Best mock_value: {n * 1.5}\n"
            ),
        }

        class _Usage:
            input_token_count = 1000
            cached_content_token_count = 0
            output_token_count = 500

        return data, _Usage()
