"""Executor agent: runs implementation tasks via an ExecutorAdapter."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import yaml
from rich.console import Console

from rdf.adapters.base import ExecResult
from rdf.adapters.claude_code import ClaudeCodeExecutorAdapter
from rdf.config import Config

console = Console(highlight=False, legacy_windows=False)


class Executor:
    """Runs a task via the configured ExecutorAdapter and writes output files."""

    def __init__(self, adapter: ClaudeCodeExecutorAdapter | None = None) -> None:
        self._adapter = adapter or ClaudeCodeExecutorAdapter()

    async def run(
        self, task_text: str, iter_dir: Path, src_dir: Path, cfg: Config
    ) -> dict:
        """Execute a task, write stdout/stderr/result files, return result dict."""
        src_dir.mkdir(parents=True, exist_ok=True)
        iter_dir.mkdir(parents=True, exist_ok=True)

        tools = [t.strip() for t in cfg.allowed_tools.split(",")]

        result = await self._adapter.execute(
            task=task_text,
            cwd=src_dir,
            allowed_tools=tools,
            timeout_sec=float(cfg.executor_timeout_sec) if cfg.executor_timeout_sec else None,
        )

        (iter_dir / "stdout.txt").write_text(result.output, encoding="utf-8")
        (iter_dir / "stderr.txt").write_text(
            "\n".join(result.errors), encoding="utf-8"
        )

        final_result = result.result

        # Fallback: if adapter returned code_error, check if executor wrote result.yaml
        if final_result.get("status") == "code_error":
            result_file = iter_dir / "result.yaml"
            if result_file.exists():
                try:
                    existing = yaml.safe_load(result_file.read_text(encoding="utf-8"))
                    if isinstance(existing, dict) and existing.get("status") not in (
                        None, "code_error"
                    ):
                        return existing
                except Exception:
                    pass

        (iter_dir / "result.yaml").write_text(
            yaml.dump(final_result, allow_unicode=True), encoding="utf-8"
        )
        return final_result


class MockExecutor:
    """Dry-run executor that creates a stub script and returns fixed metrics."""

    async def run(
        self, task_text: str, iter_dir: Path, src_dir: Path, cfg: Config
    ) -> dict:
        src_dir.mkdir(parents=True, exist_ok=True)
        iter_dir.mkdir(parents=True, exist_ok=True)

        # Parse iter number from directory name for the mock script name
        m = re.search(r"\d+", iter_dir.name)
        n = int(m.group()) if m else 0

        script = src_dir / f"run_iter_{n:03d}.py"
        script.write_text(f'print("hello from iter {n}")\n', encoding="utf-8")

        result = {
            "status": "ok",
            "artifacts": [f"src/run_iter_{n:03d}.py"],
            "metrics": {"mock_value": round(n * 1.5, 3)},
            "log_excerpt": f"hello from iter {n}",
            "experimenter_view": f"[Mock] Iteration {n} completed. No real computation.",
            "notes": "[Mock] dry-run",
        }
        (iter_dir / "stdout.txt").write_text(result["log_excerpt"], encoding="utf-8")
        (iter_dir / "stderr.txt").write_text("", encoding="utf-8")
        (iter_dir / "result.yaml").write_text(
            yaml.dump(result, allow_unicode=True), encoding="utf-8"
        )
        await asyncio.sleep(0.05)
        return result
