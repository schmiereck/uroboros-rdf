#!/usr/bin/env python3
"""Recursive Discovery Framework (RDF) v3 – CLI entry point."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# On Windows, reconfigure stdout/stderr to UTF-8 and disable the legacy
# Windows Console API path in Rich (which is limited to the current codepage).
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console

from rdf.config import Config
from rdf.core.orchestrator import Orchestrator

console = Console(highlight=False, legacy_windows=False)

# Templates used by init and dry-run auto-init
_STATE_TEMPLATE = """\
# Current Knowledge State

(not yet initialised – bootstrap required)
"""

_LOG_TEMPLATE = """\
# Experiment Log
<!-- Append-only. Entry separator: \\n---\\n between YAML blocks. -->
"""

_GITIGNORE = """\
.rdf_cache.json
archive/*/raw/
archive/*/stdout.txt
archive/*/stderr.txt
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
"""


def _auto_init_for_dryrun(root: Path, orch: Orchestrator) -> None:
    """Silent minimal init so --dry-run works without a prior `init` command."""
    from rdf.state.git import GitManager
    git = GitManager()

    def _write_if_missing(name: str, content: str) -> None:
        p = root / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")

    _write_if_missing(
        "goal.md",
        "# Research Goal (Mock)\n\nDry-run research goal.\n\n"
        "## Success Criteria\n- Dry-run completes\n",
    )
    _write_if_missing("current_state.md", _STATE_TEMPLATE)
    _write_if_missing("experiment_log.md", _LOG_TEMPLATE)
    _write_if_missing(".gitignore", _GITIGNORE)
    (root / "archive").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    if not git.is_repo(root):
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True)
    git.commit(root, "init: project scaffold")


def main() -> None:
    parser = argparse.ArgumentParser(description="RDF v3 Orchestrator")
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Path to the research project directory (default: current directory)",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("init", help="Initialise the project directory as an RDF lab")
    rp = sub.add_parser("run", help="Run the research loop")
    rp.add_argument("--dry-run", action="store_true", help="Mock agents, no API calls")
    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        sys.exit(0)

    root = (args.project if args.project else Path(".")).resolve()
    cfg = Config.load(root / "config.toml")
    dry_run = getattr(args, "dry_run", False)
    orch = Orchestrator(root, cfg, dry_run=dry_run)

    if args.cmd == "init":
        orch.init_lab()
    elif args.cmd == "run":
        if dry_run:
            console.print("[yellow]DRY-RUN – no API calls[/yellow]")
            if not (root / "goal.md").exists():
                _auto_init_for_dryrun(root, orch)
        orch.run_loop()


if __name__ == "__main__":
    main()
