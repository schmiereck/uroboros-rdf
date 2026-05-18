"""Orchestrator: the main research loop coordinator."""

from __future__ import annotations

import asyncio
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console
from rich.panel import Panel

from rdf.config import Config
from rdf.iter_id import iter_path, top_level_count
from rdf.state.git import GitManager
from rdf.state.log import append_log, estimate_cost, trim_log_if_needed, usage_tokens
from rdf.state.update import update_state
from rdf.ui.display import iter_overview

console = Console(highlight=False, legacy_windows=False)


# ---------------------------------------------------------------------------
# Project scaffold templates
# ---------------------------------------------------------------------------

_GOAL_TEMPLATE = """\
# Research Goal

<1-3 paragraphs: describe the research goal>

## Success Criteria

- ...

## Constraints

- ...
"""

_STATE_TEMPLATE = """\
# Current Knowledge State

(not yet initialised – bootstrap required)
"""

_LOG_TEMPLATE = """\
# Experiment Log
<!-- Append-only. Entry separator: \\n---\\n between YAML blocks. -->
"""

_CONFIG_TEMPLATE = """\
[roles]
# planner_model    = "qwen/qwen-2.5-72b-instruct"
# planner_adapter  = "openrouter"
planner_model    = "gemini-2.5-pro"
planner_adapter  = "gemini"
executor_adapter = "claude-code"

[claude_code]
allowed_tools = "Read,Write,Edit,Bash"
dangerously_skip_permissions = false

[limits]
max_iterations = 100
max_state_tokens = 8000
planner_timeout_sec = 180
executor_timeout_sec = 14400
max_retries_on_parse_fail = 2
max_retries_on_state_too_long = 2
max_log_entries = 30          # active log window; older entries go to experiment_log_archive.md

[agent_routing]
default_complexity = "medium"
max_depth = 4

[cache]
ttl_hours = 6
min_cache_tokens = 32768

[git]
auto_commit = true
auto_push = false             # set to true to push to remote after every iteration

[ui]
verbose = true
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

_RESEARCH_REQUIREMENTS_TEMPLATE = """\
# Research project dependencies
# Add packages needed by experiments in src/ here.
# Create the venv once with:
#   python -m venv .venv
#   .venv\\Scripts\\activate   # Windows
#   pip install -r requirements.txt
#
# The orchestrator will automatically use this venv for the executor agent
# if .venv/ exists in the project directory.
"""


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------

def _find_interrupted_iterations(root: Path) -> list[dict]:
    """Scan archive/ for checkpoint.yaml files with status=running."""
    interrupted = []
    archive = root / "archive"
    if not archive.exists():
        return []
    # Scan all directories under archive/ for checkpoint.yaml
    for checkpoint_file in sorted(archive.rglob("checkpoint.yaml")):
        try:
            data = yaml.safe_load(checkpoint_file.read_text(encoding="utf-8"))
            if data and data.get("status") == "running":
                interrupted.append({
                    "checkpoint_path": checkpoint_file,
                    "iter_dir": checkpoint_file.parent,
                    "iter_id": data.get("iter_id"),
                    "task": data.get("task", ""),
                    "complexity": data.get("complexity", "medium"),
                })
        except Exception:
            pass
    return interrupted


def _build_resume_context(root: Path, interrupted: list[dict]) -> str:
    lines = []
    for item in interrupted:
        iter_id = item["iter_id"]
        task_preview = item["task"][:200]
        # Use the actual directory where we found the checkpoint
        iter_dir = item["iter_dir"]
        result_path = iter_dir / "result.yaml"
        if result_path.exists():
            result_summary = result_path.read_text(encoding="utf-8")[:500]
            lines.append(
                f"- iter_id={iter_id}: COMPLETED (result.yaml exists)\n"
                f"  Task: {task_preview}\n"
                f"  Result preview:\n{result_summary}"
            )
        else:
            lines.append(
                f"- iter_id={iter_id}: INTERRUPTED (no result.yaml)\n"
                f"  Task: {task_preview}"
            )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    def __init__(
        self,
        root: Path,
        cfg: Config,
        dry_run: bool = False,
        project_mode: bool = False,
    ) -> None:
        self.root = root
        self.cfg = cfg
        self.dry_run = dry_run
        self._project_mode = project_mode
        self.git = GitManager()
        self.session_cost = 0.0

        if dry_run:
            from rdf.agents.planner import MockPlanner
            self.planner = MockPlanner()
        else:
            from rdf.adapters.gemini import GeminiPlannerAdapter
            from rdf.adapters.openrouter import OpenRouterPlannerAdapter
            from rdf.agents.planner import Planner
            from rdf.tools.exec_tools import ExecTools, SubAgentRegistry, make_dispatcher

            self._registry = SubAgentRegistry()
            self._exec_tools = ExecTools(self._registry, root, cfg, git=self.git)

            def _dispatcher_factory(root: Path):
                return make_dispatcher(self._exec_tools, root)

            if cfg.planner_adapter == "openrouter":
                adapter = OpenRouterPlannerAdapter(cfg.planner_model)
            else:
                adapter = GeminiPlannerAdapter(cfg)

            self.planner = Planner(
                adapter=adapter,
                dispatcher_factory=_dispatcher_factory,
                project_mode=project_mode,
            )

    # ── init ──────────────────────────────────────────────────────────────────

    def init_lab(self) -> None:
        console.print("[bold green]Initialising RDF lab...[/bold green]")
        self._write_if_missing("goal.md", _GOAL_TEMPLATE)
        self._write_if_missing("current_state.md", _STATE_TEMPLATE)
        self._write_if_missing("experiment_log.md", _LOG_TEMPLATE)
        self._write_if_missing("config.toml", _CONFIG_TEMPLATE)
        self._write_if_missing(".gitignore", _GITIGNORE)
        self._write_if_missing("requirements.txt", _RESEARCH_REQUIREMENTS_TEMPLATE)
        (self.root / "archive").mkdir(exist_ok=True)
        (self.root / "src").mkdir(exist_ok=True)

        if not self.git.is_repo(self.root):
            subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True)

        console.print("\n[bold]goal.md[/bold] has been created with a template.")
        answer = console.input("Open it in your default editor now? [y/N] ").strip().lower()
        if answer == "y":
            import os
            editor = os.environ.get(
                "EDITOR", "notepad" if sys.platform == "win32" else "nano"
            )
            subprocess.run([editor, str(self.root / "goal.md")])

        self.git.commit(self.root, "init: project scaffold")
        console.print(
            "[green]Done. Edit goal.md, then run: "
            "python orchestrator.py --project <dir> run[/green]"
        )

    def _write_if_missing(self, name: str, content: str) -> None:
        p = self.root / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")

    # ── bootstrap ─────────────────────────────────────────────────────────────

    def bootstrap(self) -> None:
        console.print("[bold]Running bootstrap...[/bold]")
        goal = (self.root / "goal.md").read_text(encoding="utf-8")

        if self.dry_run:
            state = (
                f"# Current Knowledge State (Mock Bootstrap)\n\n"
                f"## Goal\n{goal.strip()}\n\n"
                f"## Status\nReady for iteration 1.\n\n"
                f"## Open Questions\n- Mock question A?\n- Mock question B?\n"
            )
        else:
            delta = (
                f"# Bootstrap – Initialise Research State\n\n"
                f"## Research Goal\n{goal}\n\n"
                f"Read the goal carefully. Write an initial current_state.md that "
                f"re-states the goal, lists known constraints, and identifies key "
                f"open questions. Do NOT propose a task or hypothesis yet.\n"
                f"Use the state_update field for the full initial state text; "
                f"populate other fields with plausible placeholders.\n"
            )
            data, _ = self.planner.call(self.root, delta, self.cfg)  # sync ok here (called before loop)
            state = data.get("state_update", goal)

        (self.root / "current_state.md").write_text(state, encoding="utf-8")
        if self.cfg.auto_commit:
            self.git.commit(self.root, "bootstrap: initial state from goal.md")
        console.print("[green]Bootstrap complete.[/green]")

    # ── iteration ─────────────────────────────────────────────────────────────

    def _delta_prompt(
        self,
        n: int,
        hint: Optional[str],
        chosen_q: Optional[str],
        resume_context: Optional[str] = None,
    ) -> str:
        state = (self.root / "current_state.md").read_text(encoding="utf-8")
        log_path = self.root / "experiment_log.md"
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        entries = log.split("\n---\n")
        last3 = "\n---\n".join(entries[-3:]) if entries else ""
        overview = iter_overview(self.root)
        prompt = (
            f"# Iteration {n}\n\n"
            f"## All Iterations (overview)\n{overview}\n\n"
            f"## Current State\n{state}\n\n"
            f"## Recent Log (last 3 entries)\n{last3}\n"
        )
        if hint:
            prompt += f"\n## User Hint\n{hint}\n"
        if chosen_q:
            prompt += f"\n## Focus Question\n{chosen_q}\n"
        if resume_context:
            prompt += (
                f"\n## Interrupted Sub-Agents (Resume Context)\n\n"
                f"The following sub-agents were interrupted and need to be handled:\n\n"
                f"{resume_context}\n\n"
                f"For each interrupted sub-agent:\n"
                f"- If result.yaml exists in its directory, it completed — integrate that result.\n"
                f"- If no result.yaml exists, you may restart it with a new run_agent call.\n"
            )
        return prompt

    def _project_delta_prompt(
        self,
        n: int,
        hint: Optional[str],
        chosen_q: Optional[str],
        resume_context: Optional[str] = None,
    ) -> str:
        """Delta prompt for project mode — emphasises goal decomposition."""
        goal = (self.root / "goal.md").read_text(encoding="utf-8")
        state = (self.root / "current_state.md").read_text(encoding="utf-8")
        log_path = self.root / "experiment_log.md"
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        entries = log.split("\n---\n")
        last3 = "\n---\n".join(entries[-3:]) if entries else ""
        overview = iter_overview(self.root)
        prompt = (
            f"# Research Project – Phase {n}\n\n"
            f"## Research Goal\n{goal}\n\n"
            f"## All Iterations (overview)\n{overview}\n\n"
            f"## Current State\n{state}\n\n"
            f"## Recent Log (last 3 entries)\n{last3}\n\n"
            f"## Decompose and Execute\n"
            f"Plan and execute the next research phase. Break it into sub-tasks:\n"
            f"- run_agent(complexity='planner') — for sub-goals requiring multi-step "
            f"analysis (the inner Planner can itself spawn sub-agents)\n"
            f"- run_agent(complexity='medium'/'high') — for bounded, direct experiments\n"
            f"Run sub-tasks sequentially. Each result informs the next. "
            f"Synthesise all results into your final YAML report.\n"
        )
        if hint:
            prompt += f"\n## User Hint\n{hint}\n"
        if chosen_q:
            prompt += f"\n## Focus Question\n{chosen_q}\n"
        if resume_context:
            prompt += (
                f"\n## Interrupted Sub-Agents (Resume Context)\n\n"
                f"The following sub-agents were interrupted:\n\n"
                f"{resume_context}\n\n"
                f"If result.yaml exists: integrate that result. "
                f"If no result.yaml: restart with run_agent.\n"
            )
        return prompt

    async def _run_iteration(
        self,
        n: int,
        hint: Optional[str],
        chosen_q: Optional[str],
        resume_context: Optional[str] = None,
        delta_override: Optional[str] = None,
        initial_history: Optional[list[dict]] = None,
    ) -> tuple[dict, dict, float, list[dict]]:
        console.rule(f"[bold blue]ITERATION {n:03d}[/bold blue]")
        (self.root / "archive" / f"iter_{n:03d}").mkdir(parents=True, exist_ok=True)
        (self.root / "src").mkdir(exist_ok=True)

        # Tell ExecTools which top-level iteration is active (enables iter_id validation)
        if not self.dry_run:
            self._exec_tools.set_iteration(n)

        # PLANNER — analyses state, calls run_agent internally, returns synthesised YAML
        console.print("[bold]-> PLANNER[/bold]")
        delta = delta_override if delta_override is not None else self._delta_prompt(n, hint, chosen_q, resume_context)
        # When delta_override is used, hint/chosen_q are already embedded in it
        call_hint = None if delta_override is not None else hint
        call_chosen_q = None if delta_override is not None else chosen_q
        planner_log = self.root / "archive" / f"iter_{n:03d}" / "planner_response.txt"
        try:
            with console.status("Calling planner..."):
                sy, usage, messages = await self.planner.call_async(
                    self.root, delta, self.cfg, call_hint, call_chosen_q, 
                    log_path=planner_log, initial_history=initial_history
                )
        except Exception as e:
            from rdf.errors import TokenLimitError
            if isinstance(e, TokenLimitError):
                raise  # propagate to _async_run_loop for user-controlled pause
            console.print(f"[bold red]Planner call failed: {e}[/bold red]")
            sy = {"hypothesis": "strategy_error", "analysis": str(e), "state_update": ""}
            iy: dict = {"status": "code_error", "notes": f"Planner call failed: {e}"}
            cost = 0.0
            append_log(self.root, n, sy, iy, None, cost)
            if self.cfg.auto_commit:
                self.git.commit(self.root, f"iter_{n:03d}: [strategy_error]")
                if self.cfg.auto_push:
                    self.git.push(self.root)
            return sy, iy, cost, []

        hypothesis = sy.get("hypothesis", "")
        console.print(f"[green]Hypothesis:[/green] {hypothesis}")

        # Extract execution result from the Planner's synthesised YAML
        iy = {
            "status": sy.get("status") or "unknown",
            "metrics": sy.get("metrics") or {},
            "experimenter_view": sy.get("experimenter_view") or "",
            "notes": sy.get("notes") or "",
            "artifacts": sy.get("artifacts") or [],
        }
        if iy["status"] == "unknown":
            console.print(
                "[yellow]Warning: no 'status' in planner YAML – "
                "did the planner call run_agent?[/yellow]"
            )

        # Technical enforcement: verify a sub-agent actually ran
        iter_dir = self.root / "archive" / f"iter_{n:03d}"
        sub_iter_dirs = (
            [d for d in iter_dir.iterdir() if d.is_dir() and d.name.startswith("iter_")]
            if iter_dir.exists()
            else []
        )
        if not sub_iter_dirs and iy["status"] not in ("unknown", "no_execution"):
            console.print(
                f"[bold red]ENFORCEMENT: Planner reported results but no sub-iteration "
                f"directories were found under archive/iter_{n:03d}/. "
                f"Possible cause: run_agent was called with an iter_id from a different "
                f"iteration (should start with '{n}.'). "
                f"Fabricated results discarded — status overridden to 'no_execution'.[/bold red]"
            )
            iy = {
                "status": "no_execution",
                "metrics": {},
                "experimenter_view": "",
                "notes": (
                    f"No sub-agent ran for iteration {n}. "
                    "Planner may have used wrong iter_id prefix. Results discarded."
                ),
                "artifacts": [],
            }

        console.print(f"[green]Status:[/green] {iy['status']}")

        # UPDATE
        cost = estimate_cost(usage, self.cfg.planner_model)
        self.session_cost += cost
        append_log(self.root, n, sy, iy, usage, cost)
        trim_log_if_needed(self.root, self.cfg.max_log_entries)
        new_state = sy.get("state_update", "")
        if new_state:
            extra_usages = await update_state(
                self.root, new_state, self.cfg, self.planner.call_async, delta
            )
            for eu in extra_usages:
                eu_cost = estimate_cost(eu, self.cfg.planner_model)
                self.session_cost += eu_cost
                eu_inp, eu_cac, eu_out = usage_tokens(eu)
                console.print(
                    f"[dim]  state-shorten: {eu_inp/1000:.1f}k in (cached {eu_cac/1000:.1f}k), "
                    f"{eu_out/1000:.1f}k out | ~${eu_cost:.4f}[/dim]"
                )

        # GIT COMMIT
        if self.cfg.auto_commit:
            msg = f"iter_{n:03d}: {hypothesis}"
            milestone = (sy.get("milestone_reached") or "").strip()
            if milestone:
                msg += f"\n\n[milestone] {milestone}"
            if hint:
                msg += f"\n\n[hint] {hint}"
            self.git.commit(self.root, msg)
            if milestone:
                tag = "milestone-" + re.sub(
                    r"[^a-z0-9]+", "-", milestone.lower()
                ).strip("-")
                self.git.tag(self.root, tag)
                console.print(f"[bold green]Milestone tagged: {tag}[/bold green]")
            if hypothesis.startswith("[CONVERGED]"):
                self.git.tag(self.root, f"converged-{n:03d}")
                console.print(
                    f"[bold green]Converged – tagged converged-{n:03d}[/bold green]"
                )
            if self.cfg.auto_push:
                self.git.push(self.root)

        inp, cac, out = usage_tokens(usage)
        rounds = getattr(usage, "api_call_rounds", 1)
        console.print(
            f"[dim]Tokens: {inp/1000:.1f}k in (cached {cac/1000:.1f}k), "
            f"{out/1000:.1f}k out | {rounds} API round{'s' if rounds != 1 else ''} | "
            f"~${cost:.4f} | session ~${self.session_cost:.4f}[/dim]"
        )
        return sy, iy, cost, messages

    # ── menu ──────────────────────────────────────────────────────────────────

    # ── menu ──────────────────────────────────────────────────────────────────

    def _menu(
        self, n: int, sy: dict, iy: dict, cost: float
    ) -> tuple[str, Optional[str], Optional[str]]:
        open_qs = sy.get("open_questions", [])
        milestone = (sy.get("milestone_reached") or "").strip()

        state_summary = ""
        state_path = self.root / "current_state.md"
        if state_path.exists():
            for line in state_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    state_summary = stripped[:120] + ("…" if len(stripped) > 120 else "")
                    break

        # Planner's blocking question
        user_q = (sy.get("user_question") or "").strip()
        current_hint: Optional[str] = None
        if user_q:
            console.print(Panel(
                f"[bold magenta]Planner asks:[/bold magenta]\n\n{user_q}\n\n"
                "[dim]Your answer will be passed as a hint to the next iteration.[/dim]",
                title="[bold magenta]── QUESTION ──[/bold magenta]",
                border_style="magenta",
            ))
            answer = console.input(
                "[bold magenta]Your answer[/bold magenta] (Enter = skip): "
            ).strip()
            if answer:
                current_hint = answer

        while True:
            milestone_line = (
                f"\n[bold green]MILESTONE:[/bold green] {milestone}" if milestone else ""
            )
            panel_body = (
                f"[bold]Iteration:[/bold] {n}/{self.cfg.max_iterations}"
                + milestone_line + "\n"
                f"[bold]Hypothesis:[/bold] {sy.get('hypothesis', '')}\n"
                f"[bold]Status:[/bold]    {iy.get('status', 'unknown')}\n"
                f"[bold]Metrics:[/bold]   {iy.get('metrics', {})}\n"
                f"[bold]Cost:[/bold]      ~${cost:.4f} | Session ~${self.session_cost:.4f}\n"
                + (f"[dim]{state_summary}[/dim]" if state_summary else "")
            )
            title_color = "bold green" if milestone else "bold blue"
            console.print()
            console.print(Panel(
                panel_body,
                title=f"[{title_color}]── ITERATION {n:03d} COMPLETE ──[/{title_color}]",
            ))
            if milestone:
                console.print(
                    f"\n[bold green]Milestone reached: {milestone}[/bold green]  "
                    f"(git tag: milestone-"
                    f"{re.sub(r'[^a-z0-9]+', '-', milestone.lower()).strip('-')})"
                )

            if current_hint:
                console.print(Panel(
                    f"[yellow]{current_hint}[/yellow]",
                    title="[bold yellow]── ACTIVE HINT ──[/bold yellow]",
                    border_style="yellow",
                ))

            if open_qs:
                console.print("\n[bold]Research directions the planner wants to explore:[/bold]")
                for i, q in enumerate(open_qs, 1):
                    console.print(f"  [cyan]{i}.[/cyan] {q}")

            o_hint = (
                f"  o1-o{len(open_qs)}  Focus on a research direction (e.g. o2)\n"
                if open_qs
                else ""
            )
            console.print(
                "\n[bold]Actions[/bold] – letter(s) + Enter:\n"
                "  y      Next iteration (planner chooses direction)\n"
                + o_hint +
                "  a      Autonomous mode (pauses on milestone / error / loop)\n"
                "  h      Set/edit hint for the planner\n"
                "  r      Retry current iteration (with hint)\n"
                "  d      git diff --stat HEAD~1\n"
                "  s      Status report (git log)\n"
                "  n      Stop and save\n",
                markup=False,
            )

            raw = console.input("[bold]Input:[/bold] ").strip().lower()
            chosen_q: Optional[str] = None

            m = re.match(r"^o(\d+)$", raw)
            if m and open_qs:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(open_qs):
                    chosen_q = open_qs[idx]
                    console.print(f"[green]Focus:[/green] {chosen_q}")
                    return "y", current_hint, chosen_q
                console.print(f"[yellow]Please enter o1 to o{len(open_qs)}.[/yellow]")
                continue

            if raw == "d":
                console.print(
                    self.git.diff_stat(self.root) or "(no diff)", markup=False
                )
                continue
            if raw == "s":
                console.print(
                    f"\n[bold]git log:[/bold]\n{self.git.log_oneline(self.root)}"
                )
                continue
            if raw == "h":
                extra = console.input("Hint to planner: ").strip()
                current_hint = extra or None
                continue

            if raw in ("y", "r", "n", "a"):
                return raw, current_hint, chosen_q
            console.print("[yellow]Unknown input.[/yellow]")

    # ── startup menu ──────────────────────────────────────────────────────────

    def _startup_menu(self, last_n: int) -> tuple[str, Optional[str]]:
        import re as _re
        last_hypothesis = ""
        last_status = ""
        last_metrics: dict = {}
        log_path = self.root / "experiment_log.md"
        if log_path.exists():
            try:
                blocks = _re.findall(
                    r"```yaml\s*\n(.*?)```",
                    log_path.read_text(encoding="utf-8"),
                    _re.DOTALL,
                )
                if blocks:
                    last_entry = yaml.safe_load(blocks[-1]) or {}
                    last_hypothesis = last_entry.get("hypothesis", "")
                    last_status = last_entry.get("status", "")
                    last_metrics = last_entry.get("metrics", {})
            except Exception:
                pass

        state_summary = ""
        state_path = self.root / "current_state.md"
        if state_path.exists():
            for line in state_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    state_summary = stripped[:120] + ("…" if len(stripped) > 120 else "")
                    break

        status_color = (
            "green"
            if last_status == "ok"
            else ("red" if last_status == "code_error" else "yellow")
        )
        
        hint: Optional[str] = None

        while True:
            console.print()
            console.print(Panel(
                f"[bold]Last iteration:[/bold]  {last_n:03d}/{self.cfg.max_iterations}\n"
                f"[bold]Hypothesis:[/bold]      {last_hypothesis}\n"
                f"[bold]Status:[/bold]          [{status_color}]{last_status}[/{status_color}]\n"
                f"[bold]Metrics:[/bold]         {last_metrics}\n"
                + (f"[dim]{state_summary}[/dim]" if state_summary else ""),
                title="[bold blue]── RDF READY ──[/bold blue]",
            ))
            
            if hint:
                console.print(Panel(
                    f"[yellow]{hint}[/yellow]",
                    title="[bold yellow]── ACTIVE HINT ──[/bold yellow]",
                    border_style="yellow",
                ))

            console.print(
                "\n[bold]Actions[/bold] – letter(s) + Enter:\n"
                "  y      Start next iteration (y201)\n"
                "  r      Retry last iteration (r200)\n"
                "  h      Set/edit hint\n"
                "  a      Autonomous mode (pauses on milestone / error / loop)\n"
                "  s      Show git log\n"
                "  n      Exit\n",
                markup=False,
            )

            raw = console.input("[bold]Input:[/bold] ").strip().lower()
            if raw == "s":
                console.print(f"\n{self.git.log_oneline(self.root)}", markup=False)
                continue
            if raw == "h":
                new_hint = console.input("Hint to planner: ").strip()
                hint = new_hint or None
                continue
            if raw in ("y", "r", "a", "n"):
                return raw, hint
            console.print("[yellow]Unknown input.[/yellow]")

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _async_run_loop(self, project_mode: bool = False) -> None:
        if not (self.root / "goal.md").exists():
            console.print(
                "[red]No goal.md found. Run: "
                "python orchestrator.py --project <dir> init[/red]"
            )
            sys.exit(1)

        state_text = ""
        state_path = self.root / "current_state.md"
        if state_path.exists():
            state_text = state_path.read_text(encoding="utf-8")

        if (
            ("bootstrap required" in state_text.lower()
             or "bootstrap erforderlich" in state_text.lower())
            and top_level_count(self.root) == 0
        ):
            self.bootstrap()

        if not self.dry_run:
            venv_dir = self.root / ".venv"
            req_file = self.root / "requirements.txt"
            if req_file.exists() and not venv_dir.is_dir():
                console.print(
                    "[yellow]Note: requirements.txt found but no .venv/. "
                    "The executor will use the system Python. "
                    "Create a project venv with:[/yellow]\n"
                    f"  python -m venv {self.root / '.venv'}\n"
                    f"  {self.root / '.venv' / ('Scripts' if sys.platform == 'win32' else 'bin') / 'pip'}"
                    f" install -r {req_file}",
                    markup=False,
                )

        hint: Optional[str] = None
        chosen_q: Optional[str] = None
        retry = False
        autonomous_mode = False
        consecutive_errors = 0
        last_hypothesis = ""
        current_history: Optional[list[dict]] = None

        _stop_flag = [False]
        # ... (rest of _handle_sigint omitted for brevity)

        def _handle_sigint(sig, frame):
            if not _stop_flag[0]:
                _stop_flag[0] = True
                console.print(
                    "\n[bold yellow]Ctrl+C – stopping after current iteration "
                    "(if executor is still running it will be allowed to finish).[/bold yellow]"
                )
                if not self.dry_run:
                    self._exec_tools._stop_event.set()

        old_sigint = signal.signal(signal.SIGINT, _handle_sigint)

        if not self.dry_run:
            last_n = top_level_count(self.root)
            if last_n > 0:
                start_choice, hint = self._startup_menu(last_n)
                if start_choice == "n":
                    signal.signal(signal.SIGINT, old_sigint)
                    return
                if start_choice == "r":
                    retry = True
                if start_choice == "a":
                    autonomous_mode = True
                    console.print(
                        "[bold cyan]Autonomous mode – next pause on milestone, "
                        "2 consecutive errors, or hypothesis loop.[/bold cyan]"
                    )

        # Detect interrupted sub-agents from a previous session
        resume_context: Optional[str] = None
        if not self.dry_run:
            interrupted = _find_interrupted_iterations(self.root)
            if interrupted:
                console.print(
                    f"[yellow]Found {len(interrupted)} interrupted sub-agent(s) from previous session.[/yellow]"
                )
                for item in interrupted:
                    has_result = (iter_path(self.root, item["iter_id"]) / "result.yaml").exists()
                    status_str = (
                        "[green]result.yaml exists[/green]"
                        if has_result
                        else "[red]no result.yaml[/red]"
                    )
                    console.print(
                        f"  {item['iter_id']}: {status_str} – {item['task'][:80]}"
                    )
                resume_context = _build_resume_context(self.root, interrupted)

        first_iteration = True

        try:
            for _ in range(self.cfg.max_iterations):
                n = top_level_count(self.root) + (0 if retry else 1)
                iter_resume_context = resume_context if (first_iteration or retry) else None
                first_iteration = False
                try:
                    if project_mode:
                        project_delta = self._project_delta_prompt(
                            n, hint, chosen_q, iter_resume_context
                        )
                        sy, iy, cost, current_history = await self._run_iteration(
                            n, hint, chosen_q, delta_override=project_delta,
                            initial_history=current_history
                        )
                    else:
                        sy, iy, cost, current_history = await self._run_iteration(
                            n, hint, chosen_q, iter_resume_context,
                            initial_history=current_history
                        )
                    # On success, clear the history for the NEXT iteration
                    # (unless we want to keep it? No, usually next iteration starts fresh)
                    current_history = None
                except KeyboardInterrupt:
                    console.print(
                        "\n[bold yellow]Ctrl+C – iteration interrupted. Stopping...[/bold yellow]"
                    )
                    break
                except Exception as e:
                    from rdf.errors import QuotaError, TokenLimitError
                    if not isinstance(e, TokenLimitError):
                        raise
                    
                    # Capture history from the error so we can resume
                    current_history = getattr(e, "history", None)

                    # ── Token limit / quota pause ─────────────────────────────
                    if isinstance(e, QuotaError):
                        console.rule("[bold red]USAGE QUOTA EXCEEDED[/bold red]")
                        console.print(
                            f"[bold red]{e}[/bold red]\n\n"
                            "[yellow]Claude has run out of extra usage — no retries attempted.\n"
                            "The iteration produced no log entry (any sub-agent git commits\n"
                            "made before the quota hit are preserved — check `git log`).\n\n"
                            "What you can do:\n"
                            "  - Wait for the quota to reset (time shown above)\n"
                            "  - Stop with 'n' and resume later\n"
                            "  - Switch to a different Claude plan or API key[/yellow]\n"
                        )
                    else:
                        console.rule("[bold red]TOKEN LIMIT[/bold red]")
                        console.print(
                            f"[bold red]{e}[/bold red]\n\n"
                            "[yellow]The model ran out of tokens. The iteration produced no log "
                            "entry (any sub-agent git commits made before the limit are preserved "
                            "— check `git log` to see them).\n\n"
                            "What you can do:\n"
                            "  - Trim experiment_log.md (archive old entries manually)\n"
                            "  - Trim or compress current_state.md\n"
                            "  - Add a hint asking the planner to write a shorter state update\n"
                            "  - Increase max_output_tokens in config.toml (if available)\n\n"
                            "Retrying the same input would hit the same limit.[/yellow]\n"
                        )
                    if self.dry_run:
                        break
                    console.print(
                        "[bold]Actions[/bold]:\n"
                        "  r   Retry iteration (no hint)\n"
                        "  h   Retry with a hint (e.g. 'write a very short state update')\n"
                        "  n   Stop\n",
                        markup=False,
                    )
                    while True:
                        raw = console.input("[bold]Input:[/bold] ").strip().lower()
                        if raw == "n":
                            console.print("[bold]Stopped.[/bold]")
                            signal.signal(signal.SIGINT, old_sigint)
                            console.print(
                                f"[bold]Session total cost: ~${self.session_cost:.4f}[/bold]"
                            )
                            return
                        if raw in ("r", "c", ""):
                            hint = None
                            break
                        if raw == "h":
                            hint = console.input("Hint to planner: ").strip() or None
                            break
                        console.print("[yellow]Unknown input.[/yellow]")
                    
                    retry = True
                    if not self.dry_run:
                        interrupted = _find_interrupted_iterations(self.root)
                        resume_context = _build_resume_context(self.root, interrupted)
                    chosen_q = None
                    continue  # next loop cycle (same n because retry=True)

                if _stop_flag[0]:
                    console.print("[bold]Stopped by Ctrl+C.[/bold]")
                    break

                if self.dry_run:
                    if n >= 3:
                        console.print(
                            "[bold green]Dry-run complete (3 iterations).[/bold green]"
                        )
                        self._acceptance_report()
                        return
                    hint = None
                    chosen_q = None
                    retry = False
                    continue

                status = iy.get("status", "unknown")
                milestone = (sy.get("milestone_reached") or "").strip()
                hypothesis = sy.get("hypothesis", "")

                if autonomous_mode:
                    consecutive_errors = (
                        consecutive_errors + 1 if status == "code_error" else 0
                    )
                    user_q = (sy.get("user_question") or "").strip()

                    pause_reason: Optional[str] = None
                    if user_q:
                        pause_reason = "[bold magenta]Planner has a question.[/bold magenta]"
                    elif milestone:
                        pause_reason = f"[bold green]Milestone reached: {milestone}[/bold green]"
                    elif consecutive_errors >= 2:
                        pause_reason = (
                            f"[bold red]{consecutive_errors} consecutive errors – "
                            f"please review.[/bold red]"
                        )
                    elif hypothesis and hypothesis == last_hypothesis:
                        pause_reason = (
                            "[bold yellow]Planner is repeating the last hypothesis – "
                            "possible loop, input required.[/bold yellow]"
                        )

                    last_hypothesis = hypothesis

                    if pause_reason is None:
                        hint = None
                        chosen_q = None
                        retry = False
                        continue

                    autonomous_mode = False
                    consecutive_errors = 0
                    console.rule("[bold yellow]AUTONOMOUS MODE PAUSED[/bold yellow]")
                    console.print(pause_reason)

                last_hypothesis = hypothesis
                choice, hint, chosen_q = self._menu(n, sy, iy, cost)
                retry = choice == "r"

                if choice == "a":
                    autonomous_mode = True
                    consecutive_errors = 0
                    retry = False
                    hint = None
                    chosen_q = None
                    console.print(
                        "[bold cyan]Autonomous mode – next pause on milestone, "
                        "2 consecutive errors, or hypothesis loop.[/bold cyan]"
                    )
                    continue

                if choice == "n":
                    console.print("[bold]Stopped.[/bold]")
                    break

                if hypothesis.startswith("[CONVERGED]"):
                    console.print("[bold green]Loop converged.[/bold green]")
                    break

        finally:
            signal.signal(signal.SIGINT, old_sigint)

        console.print(f"[bold]Session total cost: ~${self.session_cost:.4f}[/bold]")

    def run_loop(self) -> None:
        asyncio.run(self._async_run_loop())

    def run_project(self) -> None:
        """Project mode: same loop as run_loop but with decomposition-focused prompting."""
        asyncio.run(self._async_run_loop(project_mode=True))

    # ── acceptance report ─────────────────────────────────────────────────────

    def _acceptance_report(self) -> None:
        console.rule("[bold green]ACCEPTANCE REPORT[/bold green]")

        console.print("\n[bold]1. Created files:[/bold]")
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                console.print(f"  {p.relative_to(self.root)}")

        console.print(
            f"\n[bold]2. git log --oneline:[/bold]\n{self.git.log_oneline(self.root, 10)}"
        )

        console.print("""
[bold]3. Implementation assumptions:[/bold]
  - System prompt: methodology text + 3 few-shot examples (transformer / LR search)
    + appendices. Auto-padded to >= min_cache_tokens chars.
  - Few-shot content: fictional WikiText-103 research run (domain-agnostic).
    For domain-specific context: create system_glossary.md.
  - Gemini cost estimate: 2.5 Pro prices (2025). May differ from actual billing.
  - Executor: Claude Code SDK, async query() API, cwd = src/ (persistent).
  - Token estimate: 1 token = 4 chars (Gemini convention).
""")

        console.print("""[bold]4. TODOs before first real run:[/bold]
  [ ] Export GEMINI_API_KEY: export GEMINI_API_KEY=...
  [ ] Log in to Claude: claude login
  [ ] Fill goal.md with the actual research goal
  [ ] Optional: create system_glossary.md (domain terms for the planner)
  [ ] Optional: adjust config.toml (timeouts, models, ...)
  [ ] Optional: customise the few-shot examples in rdf/core/prompts.py
""")
