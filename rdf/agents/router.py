"""Complexity-based agent routing: maps a complexity label to an executor adapter."""

from __future__ import annotations

from rdf.adapters.claude_code import ClaudeCodeExecutorAdapter
from rdf.agents.executor import Executor
from rdf.config import Config

_MODEL_MAP: dict[str, str] = {
    "low": "claude-haiku-4-5-20251001",
    "medium": "claude-sonnet-4-6",
    "high": "claude-opus-4-7",
}


def model_for_complexity(complexity: str, cfg: Config) -> str:
    """Return the model name for a given complexity label."""
    return _MODEL_MAP.get(complexity, _MODEL_MAP.get(cfg.default_complexity, "claude-sonnet-4-6"))


def make_executor(complexity: str, cfg: Config) -> Executor:
    """Return an Executor configured for the given complexity level."""
    model = _MODEL_MAP.get(complexity, _MODEL_MAP[cfg.default_complexity])
    adapter = ClaudeCodeExecutorAdapter()
    # ClaudeCodeExecutorAdapter.execute() accepts model_override; store here
    # so Executor.run() can pass it through.
    adapter._default_model_override = model  # type: ignore[attr-defined]

    class _OverridingExecutor(Executor):
        """Executor that always passes its model override to the adapter."""

        async def run(self, task_text, iter_dir, src_dir, cfg):  # type: ignore[override]
            from pathlib import Path
            import yaml

            src_dir.mkdir(parents=True, exist_ok=True)
            iter_dir.mkdir(parents=True, exist_ok=True)
            tools = [t.strip() for t in cfg.allowed_tools.split(",")]

            result = await self._adapter.execute(
                task=task_text,
                cwd=src_dir,
                allowed_tools=tools,
                model_override=model,
                timeout_sec=float(cfg.executor_timeout_sec)
                if cfg.executor_timeout_sec
                else None,
            )

            (iter_dir / "stdout.txt").write_text(result.output, encoding="utf-8")
            (iter_dir / "stderr.txt").write_text(
                "\n".join(result.errors), encoding="utf-8"
            )

            final_result = result.result
            if final_result.get("status") == "code_error":
                result_file = iter_dir / "result.yaml"
                if result_file.exists():
                    try:
                        existing = yaml.safe_load(
                            result_file.read_text(encoding="utf-8")
                        )
                        if isinstance(existing, dict) and existing.get(
                            "status"
                        ) not in (None, "code_error"):
                            return existing
                    except Exception:
                        pass

            (iter_dir / "result.yaml").write_text(
                yaml.dump(final_result, allow_unicode=True), encoding="utf-8"
            )
            return final_result

    return _OverridingExecutor(adapter)
