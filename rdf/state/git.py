"""Git operations wrapper for RDF project repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitManager:
    def _git(
        self, args: list[str], cwd: Path, check: bool = True
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, check=check
        )

    def is_repo(self, root: Path) -> bool:
        return (
            self._git(
                ["rev-parse", "--is-inside-work-tree"], root, check=False
            ).returncode
            == 0
        )

    def commit(self, root: Path, message: str) -> None:
        from rich.console import Console
        console = Console(highlight=False, legacy_windows=False)
        self._git(["add", "-A"], root)
        r = self._git(["commit", "-m", message], root, check=False)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            console.print(f"[yellow]git commit warning: {r.stderr.strip()}[/yellow]")

    def push(self, root: Path) -> None:
        from rich.console import Console
        console = Console(highlight=False, legacy_windows=False)
        r = self._git(["push", "--follow-tags"], root, check=False)
        if r.returncode != 0:
            console.print(f"[yellow]git push warning: {r.stderr.strip()}[/yellow]")

    def tag(self, root: Path, name: str) -> None:
        self._git(["tag", name], root, check=False)

    def log_oneline(self, root: Path, n: int = 5) -> str:
        return self._git(["log", "--oneline", f"-{n}"], root, check=False).stdout.strip()

    def diff_stat(self, root: Path) -> str:
        return self._git(["diff", "--stat", "HEAD~1"], root, check=False).stdout.strip()
