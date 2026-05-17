"""System prompt management for the planner agent."""

from __future__ import annotations

import os
from pathlib import Path

# Paths to the externalised prompt files
_PROMPT_DIR = Path(__file__).parent / "prompts"
_ITERATIVE_PROMPT_PATH = _PROMPT_DIR / "iterative.md"
_PROJECT_PROMPT_PATH = _PROMPT_DIR / "project.md"


def _load_prompt(path: Path) -> str:
    """Load a prompt from a file, with a fallback for development."""
    if not path.exists():
        # This should only happen if the deployment is incomplete
        return f"# Error\nPrompt file not found at {path}"
    return path.read_text(encoding="utf-8")


def build_system_prompt(root: Path, project_mode: bool = False) -> str:
    """Build the system prompt, loading from external files and embedding glossary."""
    prompt_path = _PROJECT_PROMPT_PATH if project_mode else _ITERATIVE_PROMPT_PATH
    core = _load_prompt(prompt_path)
    
    parts = [core]
    glossary = root / "system_glossary.md"
    if glossary.exists():
        parts.append(
            f"\n\n# User Domain Glossary\n{glossary.read_text(encoding='utf-8')}\n"
        )
    
    full_prompt = "".join(parts)
    
    # Optional: Ensure minimum length for Gemini context caching if needed
    # (padding could be added here if necessary, but usually the prompts are long enough)
    
    return full_prompt
