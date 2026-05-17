"""Execution tools exposed to the planner: run_agent, poll_agent, stop_agent.

These tools allow the planner to spawn sub-agents, monitor them, and stop them.
Strict sequentiality: at most one sub-agent runs at a time within a session.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from rdf.config import Config
from rdf.iter_id import IterID, iter_depth, iter_path

console = Console(highlight=False, legacy_windows=False)


class SubAgentRegistry:
    """Tracks running sub-agent asyncio tasks."""

    def __init__(self) -> None:
        self._running: dict[IterID, asyncio.Task] = {}
        self._start_time: dict[IterID, float] = {}
        self._estimated_runtime: dict[IterID, int] = {}
        self._result: dict[IterID, dict] = {}
        self._output: dict[IterID, list[str]] = {}

    def any_running(self) -> bool:
        return bool(self._running)

    def start(self, iter_id: IterID, task: asyncio.Task, estimated_runtime_sec: int) -> None:
        self._running[iter_id] = task
        self._start_time[iter_id] = time.monotonic()
        self._estimated_runtime[iter_id] = estimated_runtime_sec
        self._output[iter_id] = []

    def estimated_runtime(self, iter_id: IterID) -> int:
        return self._estimated_runtime.get(iter_id, 60)

    def elapsed(self, iter_id: IterID) -> float:
        return time.monotonic() - self._start_time.get(iter_id, time.monotonic())

    def is_done(self, iter_id: IterID) -> bool:
        task = self._running.get(iter_id)
        return task is None or task.done()

    def collect_result(self, iter_id: IterID) -> dict | None:
        task = self._running.get(iter_id)
        if task is None:
            return self._result.get(iter_id)
        if task.done():
            try:
                res = task.result()
            except Exception as exc:
                del self._running[iter_id]
                from rdf.errors import TokenLimitError
                if isinstance(exc, TokenLimitError):
                    raise  # caller must write result.yaml, clean up, then re-raise
                res = {"status": "code_error", "notes": str(exc), "metrics": {}, "artifacts": []}
                self._result[iter_id] = res
                return res
            del self._running[iter_id]
            self._result[iter_id] = res
            return res
        return None

    def cleanup(self, iter_id: IterID) -> None:
        self._running.pop(iter_id, None)
        self._start_time.pop(iter_id, None)
        self._estimated_runtime.pop(iter_id, None)


async def _run_planner_subagent(
    iter_id: IterID,
    task: str,
    root: Path,
    cfg: Config,
    git: Any = None,
) -> dict:
    """Spawn an inner Planner (Gemini) as a sub-agent.

    The inner planner gets its own isolated ExecTools/SubAgentRegistry so it
    can call run_agent for its own sub-tasks (forming deeper iter_ids such as
    105.1.1, 105.1.2, …).  Its synthesised YAML is written to result.yaml in
    the iter directory and returned as the final_result dict.
    """
    from rdf.adapters.gemini import GeminiPlannerAdapter
    from rdf.agents.planner import Planner

    depth = iter_depth(iter_id)
    delta = (
        f"# Sub-Planner Task (depth {depth})\n\n"
        f"Your iter_id context is `{iter_id}`. When spawning sub-agents via "
        f"run_agent, form their IDs as `{iter_id}.1`, `{iter_id}.2`, etc.\n\n"
        f"## Goal\n\n{task}\n"
    )

    inner_registry = SubAgentRegistry()
    inner_exec = ExecTools(inner_registry, root, cfg, git=git, parent_id=iter_id)

    def _factory(r: Path):
        return make_dispatcher(inner_exec, r)

    inner_planner = Planner(
        adapter=GeminiPlannerAdapter(cfg),
        dispatcher_factory=_factory,
    )

    try:
        data, _, _ = await inner_planner.call_async(root, delta, cfg)
    except Exception as e:
        from rdf.errors import TokenLimitError
        if isinstance(e, TokenLimitError):
            raise  # propagate — outer run_agent will record result and clean up
        return {
            "status": "code_error",
            "metrics": {},
            "experimenter_view": "",
            "notes": f"Planner sub-agent failed: {e}",
            "analysis": str(e),
        }

    d = iter_path(root, iter_id)
    (d / "result.yaml").write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    return {
        "status": data.get("status") or "unknown",
        "metrics": data.get("metrics") or {},
        "experimenter_view": data.get("experimenter_view") or "",
        "notes": data.get("notes") or "",
        "analysis": data.get("analysis") or "",
        "state_update": data.get("state_update") or "",
    }


class ExecTools:
    """Async implementations of the planner's execution tools."""

    def __init__(
        self,
        registry: SubAgentRegistry,
        root: Path,
        cfg: Config,
        git: Any = None,
        parent_id: IterID | None = None,
    ) -> None:
        self._registry = registry
        self._root = root
        self._cfg = cfg
        self._stop_event: asyncio.Event = asyncio.Event()
        self._git = git
        self._parent_id = parent_id
        self._current_top_level: int | None = None  # set by orchestrator before each iteration

    def set_iteration(self, n: int) -> None:
        """Tell top-level ExecTools which top-level iteration is running.

        Enables iter_id prefix validation for the outer planner (parent_id=None),
        preventing it from accidentally using a previous iteration's number.
        """
        self._current_top_level = n

    def _src_dir(self) -> Path:
        return self._root / "src"

    def _on_token_limit(self, iter_id: IterID, d: Path, state: str, exc: Exception) -> None:
        """Write token_limit result.yaml and git-commit before caller re-raises.
        
        Note: checkpoint.yaml is PRESERVED so the orchestrator can find it
        on retry and include it in the resume_context.
        """
        result = {
            "status": "token_limit",
            "notes": str(exc),
            "metrics": {},
            "artifacts": [],
            "log_excerpt": state[-500:] if state else "",
        }
        (d / "result.yaml").write_text(yaml.dump(result, allow_unicode=True), encoding="utf-8")
        # checkpoint_path = d / "checkpoint.yaml"
        # if checkpoint_path.exists():
        #     checkpoint_path.unlink()
        self._registry.cleanup(iter_id)
        if self._git and self._cfg.auto_commit:
            self._git.commit(self._root, f"iter_{iter_id}: complete [token_limit]")

    def _collect_state(self, iter_id: IterID) -> str:
        """Return stdout excerpt + file listing for an iteration directory."""
        d = iter_path(self._root, iter_id)
        parts: list[str] = []
        stdout_file = d / "stdout.txt"
        if stdout_file.exists():
            txt = stdout_file.read_text(encoding="utf-8", errors="replace")
            parts.append(f"=== stdout (last 2000 chars) ===\n{txt[-2000:]}")
        if d.exists():
            files = sorted(f for f in d.rglob("*") if f.is_file())
            if files:
                listing = "\n".join(
                    f"  {f.relative_to(d).as_posix()} ({f.stat().st_size:,} B)"
                    for f in files
                )
                parts.append(f"=== files in iter_{iter_id}/ ===\n{listing}")
        return "\n\n".join(parts) or "(no output yet)"

    async def run_agent(
        self,
        iter_id: IterID,
        task: str,
        complexity: str,
        estimated_runtime_sec: int,
        timeout_sec: int | None = None,
    ) -> dict:
        if self._stop_event.is_set():
            return {"error": "Stop requested. No new sub-agents will start."}

        if self._registry.any_running():
            return {
                "error": (
                    "A sub-agent is still running. "
                    "Call poll_agent or stop_agent first."
                )
            }

        depth = iter_depth(iter_id)
        if depth >= self._cfg.max_depth:
            return {
                "error": (
                    f"Maximum recursion depth {self._cfg.max_depth} reached. "
                    f"iter_id '{iter_id}' is at depth {depth}."
                )
            }

        # Enforce iter_id prefix so planners can't accidentally use a wrong iteration number.
        if self._parent_id is not None:
            # Sub-planner: iter_ids must start with the sub-planner's own id.
            expected_prefix = self._parent_id + "."
            if not iter_id.startswith(expected_prefix):
                return {
                    "error": (
                        f"Invalid iter_id '{iter_id}'. "
                        f"Sub-agents of '{self._parent_id}' must use ids like "
                        f"'{self._parent_id}.1', '{self._parent_id}.2', etc."
                    )
                }
        elif self._current_top_level is not None:
            # Top-level planner: iter_ids must start with "<current_iteration>.".
            expected_prefix = f"{self._current_top_level}."
            if not iter_id.startswith(expected_prefix):
                return {
                    "error": (
                        f"Wrong iter_id '{iter_id}' for iteration {self._current_top_level}. "
                        f"Use ids like '{self._current_top_level}.1', "
                        f"'{self._current_top_level}.2', etc. "
                        f"(not numbers from a previous or future iteration)."
                    )
                }

        d = iter_path(self._root, iter_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "task.md").write_text(task, encoding="utf-8")

        # Commit task.md before the agent starts (captures intent)
        if self._git and self._cfg.auto_commit:
            self._git.commit(self._root, f"iter_{iter_id}: start ({complexity})")

        # Write checkpoint AFTER the start-commit (keeps it out of git history)
        checkpoint_path = d / "checkpoint.yaml"
        checkpoint_data = {
            "iter_id": iter_id,
            "task": task,
            "complexity": complexity,
            "estimated_runtime_sec": estimated_runtime_sec,
            "started_at": datetime.now().isoformat(),
            "status": "running",
        }
        checkpoint_path.write_text(
            yaml.dump(checkpoint_data, allow_unicode=True), encoding="utf-8"
        )

        task_preview = task.replace("\n", " ")[:80] + ("…" if len(task) > 80 else "")

        if complexity == "planner":
            console.print(
                f"[bold]  Sub-planner[/bold] [cyan]{iter_id}[/cyan] | "
                f"model: [dim]{self._cfg.planner_model}[/dim] | "
                f"ETA: {estimated_runtime_sec}s\n"
                f"[dim]  {task_preview}[/dim]"
            )

            async def _run_p():
                return await _run_planner_subagent(iter_id, task, self._root, self._cfg, self._git)

            task_obj = asyncio.create_task(_run_p())
        else:
            from rdf.agents.router import make_executor, model_for_complexity

            model_name = model_for_complexity(complexity, self._cfg)
            console.print(
                f"[bold]  Sub-agent[/bold] [cyan]{iter_id}[/cyan] | "
                f"complexity: {complexity} → [dim]{model_name}[/dim] | "
                f"ETA: {estimated_runtime_sec}s\n"
                f"[dim]  {task_preview}[/dim]"
            )
            executor = make_executor(complexity, self._cfg)

            async def _run():
                return await executor.run(task, d, self._src_dir(), self._cfg)

            task_obj = asyncio.create_task(_run())

        self._registry.start(iter_id, task_obj, estimated_runtime_sec)

        done, _ = await asyncio.wait({task_obj}, timeout=float(estimated_runtime_sec))

        elapsed = self._registry.elapsed(iter_id)
        state = self._collect_state(iter_id)

        if task_obj in done:
            try:
                result = self._registry.collect_result(iter_id)
            except Exception as exc:
                from rdf.errors import TokenLimitError
                if isinstance(exc, TokenLimitError):
                    # Use role-based name for reporting
                    role = f"Executor-{complexity}" if complexity != "planner" else "Planner-sub"
                    self._on_token_limit(iter_id, d, state, exc)
                    result = {
                        "status": "token_limit",
                        "notes": f"{role}: {exc}",
                        "metrics": {},
                        "artifacts": [],
                        "log_excerpt": state[-500:] if state else "",
                    }
                    return {
                        "started": True,
                        "iter_id": iter_id,
                        "done": True,
                        "final_result": result,
                        "intermediate_state": state,
                        "elapsed_sec": elapsed,
                    }
                raise
            checkpoint_path = d / "checkpoint.yaml"
            if checkpoint_path.exists():
                checkpoint_path.unlink()
            if self._git and self._cfg.auto_commit:
                status_str = (result or {}).get("status", "unknown")
                self._git.commit(self._root, f"iter_{iter_id}: complete [{status_str}]")
            return {
                "started": True,
                "iter_id": iter_id,
                "done": True,
                "final_result": result,
                "intermediate_state": state,
                "elapsed_sec": elapsed,
            }

        return {
            "started": True,
            "iter_id": iter_id,
            "done": False,
            "final_result": None,
            "intermediate_state": state,
            "elapsed_sec": elapsed,
        }

    async def poll_agent(self, iter_id: IterID) -> dict:
        task_obj = self._registry._running.get(iter_id)
        if task_obj and not task_obj.done():
            wait_sec = self._registry.estimated_runtime(iter_id) / 3
            console.print(
                f"[dim]  poll_agent({iter_id}): waiting {wait_sec:.0f}s "
                f"(1/3 of estimated runtime)[/dim]"
            )
            await asyncio.wait({task_obj}, timeout=wait_sec)

        elapsed = self._registry.elapsed(iter_id)
        state = self._collect_state(iter_id)

        if self._registry.is_done(iter_id):
            d = iter_path(self._root, iter_id)
            try:
                result = self._registry.collect_result(iter_id)
            except Exception as exc:
                from rdf.errors import TokenLimitError
                if isinstance(exc, TokenLimitError):
                    self._on_token_limit(iter_id, d, state, exc)
                    result = {
                        "status": "token_limit",
                        "notes": str(exc),
                        "metrics": {},
                        "artifacts": [],
                        "log_excerpt": state[-500:] if state else "",
                    }
                    return {
                        "done": True,
                        "final_result": result,
                        "intermediate_state": state,
                        "elapsed_sec": elapsed,
                    }
                raise
            self._registry.cleanup(iter_id)
            checkpoint_path = d / "checkpoint.yaml"
            if checkpoint_path.exists():
                checkpoint_path.unlink()
            if self._git and self._cfg.auto_commit:
                status_str = (result or {}).get("status", "unknown")
                self._git.commit(self._root, f"iter_{iter_id}: complete [{status_str}]")
            return {
                "done": True,
                "final_result": result,
                "intermediate_state": state,
                "elapsed_sec": elapsed,
            }

        return {
            "done": False,
            "final_result": None,
            "intermediate_state": state,
            "elapsed_sec": elapsed,
        }

    async def stop_agent(self, iter_id: IterID, reason: str = "") -> dict:
        task_obj = self._registry._running.pop(iter_id, None)
        partial = self._collect_state(iter_id)
        if task_obj and not task_obj.done():
            task_obj.cancel()
            try:
                await asyncio.shield(task_obj)
            except (asyncio.CancelledError, Exception):
                pass
            if reason:
                d = iter_path(self._root, iter_id)
                stderr = d / "stderr.txt"
                existing = stderr.read_text(encoding="utf-8") if stderr.exists() else ""
                stderr.write_text(
                    existing + f"\n[stopped by planner: {reason}]", encoding="utf-8"
                )
        self._registry.cleanup(iter_id)
        checkpoint_path = iter_path(self._root, iter_id) / "checkpoint.yaml"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        return {"stopped": True, "partial_output": partial}


def make_dispatcher(exec_tools: ExecTools, root: Path) -> Any:
    """Build an async tool dispatcher combining read and exec tools."""
    from rdf.tools.read_tools import (
        list_iterations,
        read_campaign,
        read_iteration,
        read_result_file,
    )

    async def dispatch(name: str, args: dict) -> str:
        # Read tools (sync, wrapped in to_thread for safety)
        if name == "list_iterations":
            return await asyncio.to_thread(list_iterations, root)
        if name == "read_iteration":
            return await asyncio.to_thread(
                read_iteration, root, int(args.get("iter_num", 0))
            )
        if name == "read_result_file":
            return await asyncio.to_thread(
                read_result_file,
                root,
                int(args.get("iter_num", 0)),
                str(args.get("filename", "")),
            )
        if name == "read_campaign":
            return await asyncio.to_thread(
                read_campaign, root, str(args.get("campaign_name", ""))
            )
        # Exec tools (async)
        if name == "run_agent":
            result = await exec_tools.run_agent(
                iter_id=str(args.get("iter_id", "")),
                task=str(args.get("task", "")),
                complexity=str(args.get("complexity", "medium")),
                estimated_runtime_sec=int(args.get("estimated_runtime_sec", 60)),
                timeout_sec=args.get("timeout_sec"),
            )
            import json
            return json.dumps(result)
        if name == "poll_agent":
            result = await exec_tools.poll_agent(str(args.get("iter_id", "")))
            import json
            return json.dumps(result)
        if name == "stop_agent":
            result = await exec_tools.stop_agent(
                str(args.get("iter_id", "")), str(args.get("reason", ""))
            )
            import json
            return json.dumps(result)
        return f"Unknown tool: {name}"

    return dispatch
