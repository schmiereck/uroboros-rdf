"""OpenRouter adapters for planner and executor roles."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from rdf.adapters.base import (
    AsyncToolDispatcher,
    ExecResult,
    PlanResult,
    ToolDeclaration,
)

console = Console(highlight=False, legacy_windows=False)


class OpenRouterAdapter:
    """Base class for OpenRouter API interaction."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"

    async def _post(self, endpoint: str, payload: dict) -> dict:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/google/gemini-cli",  # OpenRouter requirement
            "X-Title": "Uroboros-RDF",
        }

        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{self.base_url}/{endpoint}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()


class OpenRouterPlannerAdapter(OpenRouterAdapter):
    """Planner adapter using OpenRouter (OpenAI-compatible)."""

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tool_declarations: list[ToolDeclaration],
        dispatcher: AsyncToolDispatcher | None = None,
        cache_hint: str | None = None,
    ) -> PlanResult:
        # OpenRouter/OpenAI tool format
        tools = []
        for d in tool_declarations:
            tools.append({
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                }
            })

        history = [{"role": "system", "content": system}]
        for m in messages:
            history.append(m)

        total_inp = 0
        total_out = 0

        while True:
            payload = {
                "model": self.model,
                "messages": history,
                "tools": tools if tools else None,
            }
            
            resp_data = await self._post("chat/completions", payload)
            
            choice = resp_data["choices"][0]
            msg = choice["message"]
            history.append(msg)
            
            usage = resp_data.get("usage", {})
            total_inp += usage.get("prompt_tokens", 0)
            total_out += usage.get("completion_tokens", 0)

            if not msg.get("tool_calls"):
                break

            for tc in msg["tool_calls"]:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                console.print(f"[dim]  ↳ tool: {name}[/dim]")
                
                if dispatcher:
                    result = await dispatcher(name, args)
                else:
                    result = f"Tool not available: {name}"
                
                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result,
                })

        class _Usage:
            def __init__(self, inp, out):
                self.prompt_token_count = inp
                self.candidates_token_count = out
                self.cached_content_token_count = 0
                self.api_call_rounds = 1 # simplified

        return PlanResult(
            text=history[-1]["content"] if history[-1]["role"] == "assistant" else "",
            usage=_Usage(total_inp, total_out)
        )


class OpenRouterExecutorAdapter(OpenRouterAdapter):
    """Executor adapter using OpenRouter models.
    
    Implements a basic agentic loop for file operations and bash commands.
    """

    @property
    def role_name(self) -> str:
        """Return a role-based name for reporting (e.g. Executor-low)."""
        m = self.model.lower()
        if "qwen" in m:
            return "Executor-low"
        return f"Executor-openrouter-{self.model}"

    async def execute(
        self,
        task: str,
        cwd: Path,
        allowed_tools: list[str],
        model_override: str | None = None,
        timeout_sec: float | None = None,
    ) -> ExecResult:
        model = model_override or self.model
        # ... rest of method logic ...
        
        # We need a system prompt that defines the tools available to the executor
        system_prompt = f"""You are an autonomous research executor.
Your goal is to complete the task by writing code, running commands, and analyzing results.
Working directory: {cwd.absolute()}
Allowed tools: {", ".join(allowed_tools)}

Tools available via function calling:
- read_file(path: str)
- write_file(path: str, content: str)
- list_dir(path: str) -> list of files/directories
- bash(command: str) -> stdout, stderr, exit_code

{self._result_yaml_reminder()}
"""
        
        history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]
        
        # Tools for the executor
        tools = []
        if "Read" in allowed_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read content of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]
                    }
                }
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "List files and directories in a path",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]
                    }
                }
            })
        if "Write" in allowed_tools or "Edit" in allowed_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write or overwrite a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["path", "content"]
                    }
                }
            })
        if "Bash" in allowed_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"]
                    }
                }
            })

        collected_output = []
        errors = []

        try:
            for _ in range(20): # Max steps
                payload = {
                    "model": model,
                    "messages": history,
                    "tools": tools if tools else None,
                }
                
                resp_data = await self._post("chat/completions", payload)
                choice = resp_data["choices"][0]
                msg = choice["message"]
                history.append(msg)
                
                if msg.get("content"):
                    collected_output.append(msg["content"])
                
                if not msg.get("tool_calls"):
                    break
                
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    
                    # Log full tool call to stdout file
                    tc_log = f"\n[Tool Call: {name}({args})]\n"
                    collected_output.append(tc_log)
                    
                    # Log simplified tool call to console
                    if name in ("read_file", "list_dir", "write_file"):
                        console.print(f"[dim]    ↳ {name}({args.get('path', '')})[/dim]")
                    elif name == "bash":
                        cmd = args.get("command", "")
                        cmd_short = cmd[:50] + ("..." if len(cmd) > 50 else "")
                        console.print(f"[dim]    ↳ bash({cmd_short})[/dim]")
                    else:
                        console.print(f"[dim]    ↳ {name}[/dim]")
                    
                    result = ""
                    try:
                        if name == "read_file":
                            p = cwd / args["path"]
                            result = p.read_text(encoding="utf-8")
                        elif name == "list_dir":
                            p = cwd / args["path"]
                            if p.is_dir():
                                items = sorted(p.iterdir())
                                result = "\n".join(
                                    f"{'[DIR] ' if i.is_dir() else '      '}{i.name}"
                                    for i in items
                                )
                            else:
                                result = f"Error: {args['path']} is not a directory"
                        elif name == "write_file":
                            p = cwd / args["path"]
                            p.parent.mkdir(parents=True, exist_ok=True)
                            p.write_text(args["content"], encoding="utf-8")
                            result = f"Successfully wrote to {args['path']}"
                        elif name == "bash":
                            proc = await asyncio.create_subprocess_shell(
                                args["command"],
                                cwd=cwd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            stdout, stderr = await proc.communicate()
                            result = f"exit_code: {proc.returncode}\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
                    except Exception as e:
                        result = f"Error: {e}"
                        errors.append(result)

                    # Log tool result to stdout
                    collected_output.append(f"[Tool Result: {result[:500]}{'...' if len(result)>500 else ''}]\n")

                    history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": name,
                        "content": result,
                    })
        except Exception as e:
            errors.append(f"Loop error: {e}")

        output = "\n".join(collected_output)
        
        # Try to find a YAML block in the entire output (even if mixed with text)
        result_yaml = None
        try:
            from rdf.adapters.claude_code import _parse_yaml_block
            result_yaml = _parse_yaml_block(output)
        except Exception:
            # Fallback: check if ANY message in history has a yaml block
            for h_msg in reversed(history):
                content = h_msg.get("content")
                if content and "```yaml" in content:
                    try:
                        result_yaml = _parse_yaml_block(content)
                        break
                    except Exception:
                        pass
        
        if not result_yaml:
            result_yaml = {
                "status": "code_error",
                "notes": "Failed to parse YAML block from Qwen output",
                "log_excerpt": output[-1000:]
            }

        return ExecResult(output=output, errors=errors, result=result_yaml)

    def _result_yaml_reminder(self) -> str:
        from rdf.adapters.claude_code import _RESULT_YAML_REMINDER
        return _RESULT_YAML_REMINDER
