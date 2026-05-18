"""ClaudeCodeExecutorAdapter — wraps the claude_code_sdk for the executor role."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from rdf.adapters.base import ExecResult


def _patch_claude_sdk() -> None:
    """Yield None for unknown message types (e.g. rate_limit_event) instead of
    raising MessageParseError, so the stream continues uninterrupted.

    client.py imports parse_message with 'from .message_parser import parse_message',
    creating its own reference. Both the module attribute and the already-imported
    name in client's namespace must be patched.
    """
    try:
        from claude_code_sdk._internal import message_parser, client as _sdk_client  # type: ignore
        from claude_code_sdk._errors import MessageParseError  # type: ignore

        _orig = message_parser.parse_message

        def _safe_parse(data: dict) -> Any:
            try:
                return _orig(data)
            except MessageParseError:
                return None

        message_parser.parse_message = _safe_parse
        _sdk_client.parse_message = _safe_parse
    except Exception:
        pass


_patch_claude_sdk()

_RESULT_YAML_REMINDER = """

---

REQUIRED: The very last thing in your response MUST be this YAML block — no
exceptions. Do not end with Markdown prose, bullet points, or a summary.
The orchestrator reads ONLY this block to record the result; without it the
iteration is marked as code_error even if the experiment succeeded.

```yaml
status: ok              # ok | experiment_failed | code_error
artifacts: []           # list of relative file paths written (e.g. src/foo.py)
metrics: {}             # numeric results as key: value pairs
log_excerpt: |          # last ~20 lines of relevant terminal output
  ...
experimenter_view: |    # qualitative observations and key findings
  ...
notes: one-line remark
```
"""


@contextlib.contextmanager
def _project_venv(project_root: Path):
    """Temporarily prepend the project's .venv to PATH."""
    venv_dir = project_root / ".venv"
    if not venv_dir.is_dir():
        yield
        return

    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    old_path = os.environ.get("PATH", "")
    old_venv = os.environ.get("VIRTUAL_ENV")
    old_home = os.environ.get("PYTHONHOME")

    os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
    os.environ["VIRTUAL_ENV"] = str(venv_dir)
    os.environ.pop("PYTHONHOME", None)
    try:
        yield
    finally:
        os.environ["PATH"] = old_path
        if old_venv is not None:
            os.environ["VIRTUAL_ENV"] = old_venv
        else:
            os.environ.pop("VIRTUAL_ENV", None)
        if old_home is not None:
            os.environ["PYTHONHOME"] = old_home


def _parse_yaml_block(text: str) -> dict:
    import re
    matches = re.findall(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return yaml.safe_load(matches[0])
    opens = list(re.finditer(r"```yaml\s*\n", text))
    if opens:
        return yaml.safe_load(text[opens[0].end():])
    raise yaml.YAMLError("No yaml block found in response")


class ClaudeCodeExecutorAdapter:
    """Runs tasks via the Claude Code SDK (claude_code_sdk.query)."""

    def __init__(self, model: str = "claude-sonnet-4-6", **kwargs) -> None:
        self.model = model

    @property
    def role_name(self) -> str:
        """Return a role-based name for reporting (e.g. Executor-medium)."""
        m = self.model.lower()
        if "sonnet" in m:
            return "Executor-medium"
        if "opus" in m:
            return "Executor-high"
        return "Executor-claude"

    async def execute(
        self,
        task: str,
        cwd: Path,
        allowed_tools: list[str],
        model_override: str | None = None,
        timeout_sec: float | None = None,
    ) -> ExecResult:
        from claude_code_sdk import query, ClaudeCodeOptions  # type: ignore

        cwd.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {"allowed_tools": allowed_tools, "cwd": cwd}
        if model_override:
            kwargs["model"] = model_override
        else:
            kwargs["model"] = self.model
        full_task = task + _RESULT_YAML_REMINDER

        collected: list[str] = []
        errors: list[str] = []

        async def _stream() -> None:
            try:
                async for msg in query(prompt=full_task, options=options):
                    if msg is None:
                        continue
                    if hasattr(msg, "content"):
                        for block in msg.content:
                            if hasattr(block, "text"):
                                collected.append(block.text)
                    if getattr(msg, "is_error", False):
                        # Prefer msg.result (quota/billing errors land there, not msg.error)
                        result_text = getattr(msg, "result", None) or ""
                        error_text = str(getattr(msg, "error", None) or msg)
                        errors.append(result_text if result_text else error_text)
                    # Detect token limit via stop_reason on result messages
                    stop_reason = getattr(msg, "stop_reason", None)
                    if stop_reason == "max_tokens":
                        errors.append(
                            "TOKEN_LIMIT: Claude hit output token limit "
                            "(stop_reason=max_tokens). Context may be too large."
                        )
            except Exception as exc:
                errors.append(f"SDK error: {exc}")

        # The project root is cwd (standardised to self._root in exec_tools)
        project_root = cwd
        try:
            with _project_venv(project_root):
                if timeout_sec:
                    await asyncio.wait_for(_stream(), timeout=float(timeout_sec))
                else:
                    await _stream()
        except asyncio.TimeoutError:
            errors.append(f"Timeout after {timeout_sec}s")

        output = "\n".join(collected)

        # Surface usage quota errors before generic token limit check
        _QUOTA_PATTERNS = ("out of extra usage", "quota exceeded", "usage limit exceeded")
        quota_err = next(
            (e for e in errors if any(p in e.lower() for p in _QUOTA_PATTERNS)), None
        )
        if quota_err:
            import re as _re
            m = _re.search(r'result="([^"]+)"', quota_err)
            detail = m.group(1) if m else quota_err[:300]
            from rdf.errors import QuotaError
            raise QuotaError(self.role_name, detail)

        # Surface output token limit as a proper exception so the orchestrator can pause
        token_limit_msgs = [e for e in errors if e.startswith("TOKEN_LIMIT:")]
        if token_limit_msgs:
            from rdf.errors import TokenLimitError
            raise TokenLimitError(self.role_name, token_limit_msgs[0][len("TOKEN_LIMIT: "):])

        try:
            result = _parse_yaml_block(output)
        except yaml.YAMLError:
            result = {
                "status": "code_error",
                "artifacts": [],
                "metrics": {},
                "log_excerpt": output[-2000:],
                "experimenter_view": "No yaml block in output – check stdout.txt",
                "notes": "Parse failed",
            }

        return ExecResult(output=output, errors=errors, result=result)
