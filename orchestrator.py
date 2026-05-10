#!/usr/bin/env python3
"""Recursive Discovery Framework (RDF) v3 – Orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console
from rich.panel import Panel

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        print("ERROR: Install tomli (`pip install tomli`) or use Python ≥ 3.11")
        sys.exit(1)

# On Windows, reconfigure stdout/stderr to UTF-8 and disable the legacy
# Windows Console API path in Rich (which is limited to the current codepage).
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(highlight=False, legacy_windows=False)


def _patch_claude_sdk() -> None:
    """Make claude_code_sdk yield None for unknown message types (e.g. rate_limit_event)
    instead of raising MessageParseError, so the stream continues uninterrupted.

    client.py imports parse_message with 'from .message_parser import parse_message',
    creating its own reference. We must patch BOTH the module attribute AND the name
    in client's namespace for the replacement to take effect.
    """
    try:
        from claude_code_sdk._internal import message_parser, client as _sdk_client  # type: ignore
        from claude_code_sdk._errors import MessageParseError  # type: ignore
        _orig = message_parser.parse_message

        def _safe_parse(data: dict) -> Any:
            try:
                return _orig(data)
            except MessageParseError:
                return None  # Unknown type – caller skips None

        message_parser.parse_message = _safe_parse
        _sdk_client.parse_message = _safe_parse  # overwrite the already-imported reference
    except Exception:
        pass  # Fail silently if SDK internals change


_patch_claude_sdk()


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT  (padded to ≥ min_cache_tokens for Gemini context caching)
# ─────────────────────────────────────────────────────────────────────────────

_CORE = """\
# Research Strategy Agent – System Instructions

You are a highly experienced scientific research advisor specialising in
empirical, iterative experimentation. Your role is to guide a research
workflow where each iteration tests exactly ONE falsifiable hypothesis using
the smallest experiment that can confirm or refute it.

## Core Principle: Minimal Validating Step

A "minimal validating step" is not the simplest thing you could do; it is the
smallest intervention that produces falsifiable evidence.

Good minimal steps:
  - "Run with n=100 samples to check if variance < 0.01" (concrete, measurable)
  - "Test gradient clipping at 1.0 vs 5.0 on the first 10 k steps"

Bad minimal steps:
  - "Improve the model" (not falsifiable)
  - "Try different hyperparameters" (too broad, no clear criterion)

## Hypothesis Quality

A hypothesis has three parts:
  1. Claim – a specific, testable assertion.
  2. Prediction – the measurable outcome if the claim is true.
  3. Falsification – the result that would prove the claim wrong.

## Open Questions

Maintain an explicit list of open questions (3–7). They should be:
  - Specific enough to be answerable in one or two iterations
  - Independent of each other where possible
  - Ordered by expected information gain

## State Management

`current_state.md` should capture everything a new researcher needs to
understand where you are and why. Update it every iteration to reflect:
  - What has been confirmed (with evidence, iter_NNN)
  - What has been refuted (with evidence, iter_NNN)
  - The current best result
  - What remains unknown

Never let the state grow stale. Negative results are facts too.

## Scientific Integrity

  - Never cherry-pick metrics. Report what the experiment actually showed.
  - Distinguish correlation from causation.
  - Propose the simplest clean experiment over a complex one.

---

## Methodology: Iterative Discovery Phases

### Phase 1 – Orientation (iterations 1–5)
Establish baselines. Avoid optimisation; focus on measurement. Every
experiment should produce numbers comparable in future iterations.

### Phase 2 – Focused Exploration (iterations 6–20)
Systematically vary the most promising factors using ablation studies to
isolate individual effects.

### Phase 3 – Convergence (iterations 20+)
When experiments consistently confirm predictions, synthesise results. The
hypothesis in this phase should be: "[CONVERGED] We have sufficient evidence
to conclude X."

---

## Output Format

You MUST end every response with a YAML block in this exact schema:

```yaml
analysis: |
  Your analysis of current state and recent results.
open_questions:
  - "Question 1"
  - "Question 2"
  - "Question 3"
chosen_direction: "Which question/direction and why"
hypothesis: "One-line falsifiable hypothesis (becomes git commit message)"
rationale: "Why this hypothesis is the right next step"
task_for_implementer: |
  Concrete, executable task for the implementation agent.
  Include: what files to create/modify in src/, what to run, what metrics to collect.
  Results go to archive/iter_NNN/results/. Working directory is src/ (persistent).
expected_outcome: "What would confirm/refute this hypothesis"
success_criteria:
  - "Measurable criterion 1"
  - "Measurable criterion 2"
milestone_reached: ""  # Optional. If this iteration completes a milestone from the
                       # research goal (e.g. "Phase 1: 1D-Symmetrie-Sieber"), write
                       # its exact name here. Leave empty string if no milestone.
state_update: |
  Complete replacement text for current_state.md. Self-contained.
  Start with a one-line "Phase: <current phase name>" for easy scanning.
  Keep concise (≤ MAX_STATE_TOKENS).
```

Milestone detection: After each iteration, compare your `state_update` against the
milestones listed in the research goal. If all success criteria for a milestone are
met by the accumulated evidence, set `milestone_reached` to the milestone's name.
This triggers a git tag and a highlighted summary for the researcher.

---

## Few-Shot Example – Iteration 1

Context: Goal = find optimal LR schedule for a transformer on WikiText-103.
Success: val_loss < 2.5 after 10 k steps. No experiments run yet.

Prose analysis:
No baseline numbers exist. Before exploring schedules, we need to confirm
the training loop is correct and get an anchor value. lr=1e-4 with cosine is
the canonical transformer default—ideal for a baseline.

```yaml
analysis: |
  No experiments completed. Orientation phase. Need a reproducible baseline
  before exploring LR schedules.
open_questions:
  - "Is our training loop bug-free and reproducible across seeds?"
  - "What val_loss does cosine-LR lr=1e-4 achieve at 10k steps?"
  - "What is the maximum stable learning rate?"
  - "Does warmup duration significantly affect final performance?"
  - "Is gradient clipping necessary for this architecture?"
chosen_direction: "Establish reproducible baseline with cosine-LR lr=1e-4"
hypothesis: "baseline: cosine-LR lr=1e-4 achieves val_loss < 3.5 at 10k steps"
rationale: |
  Before testing schedules we need a number to beat. lr=1e-4 is the
  well-tested default; this validates the pipeline and anchors comparisons.
task_for_implementer: |
  Create src/train.py that trains a 6-layer transformer
  (d_model=256, nhead=8, ffn=1024) on WikiText-103 (HuggingFace datasets),
  AdamW lr=1e-4 weight_decay=0.01, cosine LR, 10 000 steps, batch=32,
  seq_len=512, seed=42. Log val_loss every 500 steps to val_loss.csv.
  Write final val_loss to archive/iter_001/results/val_loss.csv and include it
  in the required YAML block at the end of your response.
expected_outcome: "val_loss between 2.8–3.5. Smooth decreasing loss curve."
success_criteria:
  - "val_loss is finite (no NaN/Inf)"
  - "Loss decreasing in first 5k steps"
  - "result.yaml present with final val_loss"
state_update: |
  # Current Research State
  ## Goal
  val_loss < 2.5 after 10k steps, WikiText-103, 6-layer transformer.
  ## Status
  ORIENTATION. No experiments completed.
  ## Architecture
  6-layer transformer, d_model=256, nhead=8, ffn=1024
  AdamW, cosine LR, 10k steps, batch=32, seq_len=512
  ## Pending
  - iter_001: baseline cosine-LR lr=1e-4
```

---

## Few-Shot Example – Iteration 2

Context: iter_001 result: val_loss=3.21, stable training, smooth loss curve.
Pipeline confirmed correct.

Prose analysis:
Baseline confirmed at 3.21. Now test warmup—the most common first improvement
over a fixed cosine schedule. lr=1e-4 is already stable, so warmup will
likely give a small improvement by helping early steps.

```yaml
analysis: |
  Baseline: val_loss=3.21 with cosine-LR lr=1e-4 (iter_001). Training stable.
  Next: does 500-step linear warmup improve final val_loss?
open_questions:
  - "Does 500-step warmup improve val_loss vs no warmup?"
  - "What is the optimal warmup duration?"
  - "Can we increase lr above 1e-4 with warmup?"
  - "Does weight decay matter significantly at this scale?"
chosen_direction: "Test 500-step linear warmup with peak lr=1e-4"
hypothesis: "warmup-500: 500-step warmup reduces val_loss by ≥2% vs baseline"
rationale: |
  Warmup is well-established for transformers. The baseline is stable so
  warmup may give a small improvement. 500 steps (5% of training) is a
  common default.
task_for_implementer: |
  Copy archive/iter_001/code/train.py to archive/iter_002/code/train.py.
  Add 500-step linear warmup before cosine decay. All other hyperparameters
  identical. Record val_loss every 500 steps. Compare final val_loss to
  baseline (3.21) in result.yaml.
expected_outcome: "val_loss < 3.15 (≥2% improvement). If ≥3.21: warmup ineffective."
success_criteria:
  - "val_loss < 3.15 (≥2% improvement vs baseline)"
  - "Training completes without NaN"
  - "Warmup phase visible in LR schedule log"
state_update: |
  # Current Research State
  ## Goal
  val_loss < 2.5 after 10k steps, WikiText-103.
  ## Confirmed
  - BASELINE: val_loss=3.21, cosine-LR lr=1e-4, no warmup (iter_001)
  - Pipeline: correct, reproducible with seed=42
  ## In Progress
  - iter_002: 500-step linear warmup with lr=1e-4
  ## Open Questions
  1. Does warmup help at this LR?
  2. What is optimal warmup duration?
  3. Can we push LR higher with warmup?
```

---

## Few-Shot Example – Iteration 3

Context: iter_002 result: val_loss=3.09 with 500-step warmup. Improvement
(3.21-3.09)/3.21 = 3.7% — criterion ≥2% met.

Prose analysis:
Warmup hypothesis confirmed (3.7% improvement). The early training
stabilisation suggests headroom for a higher peak LR. lr=2e-4 (2×) is the
natural next step; if stable, we could approach val_loss < 3.0.

```yaml
analysis: |
  Warmup confirmed: val_loss 3.21->3.09 (3.7%, criterion ≥2% met, iter_002).
  Stable early training suggests headroom for higher LR.
open_questions:
  - "Does lr=2e-4 with 500-step warmup achieve val_loss < 3.00?"
  - "What is the maximum stable LR with warmup?"
  - "Should warmup duration scale with LR?"
  - "Has architecture size become the bottleneck?"
chosen_direction: "Test peak lr=2e-4 with 500-step warmup"
hypothesis: "lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.00"
rationale: |
  Warmup stabilises early training, creating headroom for higher LR. 2e-4 is
  a natural first step. If stable, a big improvement toward the 2.5 goal.
task_for_implementer: |
  Copy archive/iter_002/code/train.py to archive/iter_003/code/train.py.
  Change lr=2e-4 (was 1e-4). Keep warmup=500, all else identical. Record
  val_loss per 500 steps, LR curve, gradient norm (first 1k steps). Stop
  early if loss > 10 or NaN; report the step.
expected_outcome: "val_loss < 3.00 if stable. If >3.09: LR too high, needs clipping."
success_criteria:
  - "val_loss < 3.00"
  - "No NaN/divergence"
  - "Gradient norms stay below 5.0"
state_update: |
  # Current Research State
  ## Goal
  val_loss < 2.5 after 10k steps, WikiText-103.
  ## Confirmed
  - BASELINE: val_loss=3.21, cosine-LR lr=1e-4, no warmup (iter_001)
  - WARMUP HELPS: val_loss=3.09 with 500-step warmup lr=1e-4 (+3.7%, iter_002)
  - Best: val_loss=3.09
  ## In Progress
  - iter_003: lr=2e-4 with 500-step warmup
  ## Open Questions
  1. Can we use lr=2e-4 safely with warmup?
  2. What is the maximum stable LR?
  3. Does architecture size limit performance at 10k steps?
```

---

## Appendix: Scientific Rigour in Computational Research

### A. Observation Before Hypothesis
Run the baseline system first. Record behaviour across at least two random
seeds before forming hypotheses. Many research failures trace to bugs in
training infrastructure, not the research idea itself.

### B. Controlled Experiments
Only one variable should change between the baseline and each test run.
Exception: if strong prior evidence shows two factors are independent (e.g.
from published ablations), a combined test can save time. Document the
assumption explicitly.

### C. Documenting Negative Results
A refuted hypothesis is valuable. When an experiment fails:
  1. Document precisely why (e.g. "diverged at step 423, gradient norm 847").
  2. Update the state to reflect what is now known.
  3. Propose a follow-up that explains the failure mechanism.
  4. Never retry the exact same experiment without a specific reason.

### D. Recognising Convergence
Propose convergence when:
  - The last 3+ iterations showed improvements < 1% on the primary metric, OR
  - You have evidence the goal cannot be met without architectural changes, OR
  - All high-value open questions have been answered.

Convergence is not "gave up." It is "sufficient evidence for a grounded
conclusion."

### E. State Hygiene
Write `current_state.md` for a researcher joining for the first time.
Avoid "as mentioned before." Structure:
  1. Goal (unchanged from goal.md)
  2. Confirmed findings (with iter_NNN evidence)
  3. Refuted hypotheses (with iter_NNN evidence)
  4. Current best result + configuration
  5. In progress (current iteration)
  6. Open questions

### F. Multi-Factor Experiments
Avoid testing multiple factors simultaneously. If you test "LR=2e-4 AND
batch_size=64 AND a new optimiser" and performance improves, you cannot
attribute the gain to any single factor. Keep experiments single-variable.

### G. Token Efficiency
Your responses are cached for efficiency. Avoid repeating in `analysis`
what is already in `state_update`. Each field has a distinct role:
  - `analysis`: your reasoning (chain-of-thought)
  - `task_for_implementer`: concrete executable instructions
  - `state_update`: distilled facts for future context

---

## Appendix: Common Research Failure Modes

1. **Hypothesis Drift** – starting with hypothesis A but testing B because
   it seemed easier. Always implement exactly what you proposed.

2. **Metric Gaming** – optimising a proxy metric instead of the target. Verify
   that what you are improving is what actually matters.

3. **Insufficient Baseline** – exploring before a reliable, reproducible
   baseline exists. Always run a baseline first.

4. **Scope Creep** – adding "just one more thing" to an experiment. One
   variable per iteration.

5. **State Staleness** – failing to update state after a negative result. A
   stale state will mislead all future iterations.

6. **Premature Convergence** – declaring convergence after reaching the
   success criterion without exploring whether much better solutions exist.

7. **Catastrophic Forgetting** – writing a state_update that omits confirmed
   findings from earlier iterations. State accumulates knowledge; it does not
   discard it.

8. **Result Anchoring** – over-fitting interpretation to the first successful
   result. Always ask: could another configuration explain this better?

9. **Confound Blindness** – attributing a result to the intervention when an
   uncontrolled variable (hardware, dataset version, library update) caused it.

10. **Vague Success Criteria** – writing criteria that cannot be measured
    objectively. "Model works better" is not a criterion. "val_loss < 2.5" is.

---

## Appendix: Interpreting the Implementer's Output

The `experimenter_view` field in the implementer's response contains
qualitative observations that may not be captured in numerical metrics.

Pay attention to:
  - **Unexpected behaviours**: if the training curve looked unusual, investigate.
  - **Resource constraints**: slower-than-expected training may affect validity.
  - **Implementation deviations**: if the plan had to be modified, note it.
  - **Suggestions**: the implementer reads the output closely; consider them.

The implementer's role is faithful execution and careful observation.
Your role is interpretation and direction. Both are essential.

---

## Appendix: Managing Long Research Runs (20+ iterations)

1. **Archive old findings**: move stable older findings to a "Confirmed Archive"
   section at the bottom of the state. Keep only the most relevant findings in
   the active section.

2. **Track the decision tree**: keep a brief record of which directions were
   explored and why. This prevents re-exploring dead ends.

3. **Maintain a "current best" record**: always know what the best result is
   and what configuration achieved it.

4. **Budget awareness**: with few iterations left, avoid long exploration and
   focus on refining the best configuration.

---

## Appendix: Domain Glossary (edit system_glossary.md to extend)

ablation study – experiment where one component is removed to measure its
  individual contribution.

baseline – performance of the system with no modifications; reference for all
  subsequent experiments.

confound – a variable that affects the outcome but is not measured or
  controlled.

convergence – state where additional iterations are unlikely to produce
  significant improvements.

falsifiable hypothesis – a hypothesis that can be proven wrong by a specific
  experimental result.

hyperparameter – a parameter controlling the training process but not learned
  from data (e.g. learning rate, batch size).

null hypothesis – the hypothesis that the intervention has no effect.

oracle – a reference result known to be correct, used to verify experiment
  design.

overfitting – performing well on training data but poorly on validation data.

probe – a lightweight experiment measuring a specific property without full
  training.

reproducibility – the ability to re-run the same experiment and get the same
  result.

sensitivity analysis – measuring how much the outcome changes as a single
  hyperparameter is varied.

warmup – gradually increasing the learning rate from a small value to the
  target over a specified number of steps.

variance – the spread of outcomes across runs with different random seeds.

---
"""

# Additional padding block cycled until min_cache_tokens is reached
_PAD_BLOCK = """\

## Methodology Checklist (reference copy)

Before submitting your YAML, verify:
  [ ] Is the hypothesis falsifiable with a specific outcome?
  [ ] Is exactly one variable changing from the baseline?
  [ ] Are success criteria measurable and unambiguous?
  [ ] Is the experiment the smallest that answers the question?
  [ ] Does the state_update reflect ALL confirmed/refuted findings?
  [ ] Does task_for_implementer include exact file paths and output formats?
  [ ] Have you listed 3–7 open questions covering the full possibility space?
  [ ] Does the hypothesis make a quantitative prediction where possible?
  [ ] Have you considered whether the experiment could be confounded?
  [ ] Is the expected_outcome specific enough to evaluate after the run?

"""


def _build_system_prompt(root: Path, min_chars: int) -> str:
    parts = [_CORE]
    glossary = root / "system_glossary.md"
    if glossary.exists():
        parts.append(f"\n\n# User Domain Glossary\n{glossary.read_text(encoding='utf-8')}\n")
    prompt = "".join(parts)
    while len(prompt) < min_chars:
        prompt += _PAD_BLOCK
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    strategy_model: str = "gemini-2.5-pro"
    implementation_cli: str = "claude"
    allowed_tools: str = "Read,Write,Edit,Bash"
    dangerously_skip_permissions: bool = False
    max_iterations: int = 100
    max_state_tokens: int = 8000
    strategy_timeout_sec: int = 180
    experiment_timeout_sec: Optional[int] = 14400
    max_retries_on_parse_fail: int = 2
    max_retries_on_state_too_long: int = 2
    cache_ttl_hours: int = 6
    min_cache_tokens: int = 32768
    auto_commit: bool = True
    verbose: bool = True

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            d = tomllib.load(f)
        c = cls()
        m = d.get("models", {})
        c.strategy_model = m.get("strategy", c.strategy_model)
        c.implementation_cli = m.get("implementation_cli", c.implementation_cli)
        cc = d.get("claude_code", {})
        c.allowed_tools = cc.get("allowed_tools", c.allowed_tools)
        c.dangerously_skip_permissions = cc.get("dangerously_skip_permissions", c.dangerously_skip_permissions)
        lim = d.get("limits", {})
        c.max_iterations = lim.get("max_iterations", c.max_iterations)
        c.max_state_tokens = lim.get("max_state_tokens", c.max_state_tokens)
        c.strategy_timeout_sec = lim.get("strategy_timeout_sec", c.strategy_timeout_sec)
        c.experiment_timeout_sec = lim.get("experiment_timeout_sec", c.experiment_timeout_sec)
        c.max_retries_on_parse_fail = lim.get("max_retries_on_parse_fail", c.max_retries_on_parse_fail)
        c.max_retries_on_state_too_long = lim.get("max_retries_on_state_too_long", c.max_retries_on_state_too_long)
        ch = d.get("cache", {})
        c.cache_ttl_hours = ch.get("ttl_hours", c.cache_ttl_hours)
        c.min_cache_tokens = ch.get("min_cache_tokens", c.min_cache_tokens)
        g = d.get("git", {})
        c.auto_commit = g.get("auto_commit", c.auto_commit)
        u = d.get("ui", {})
        c.verbose = u.get("verbose", c.verbose)
        return c


# ─────────────────────────────────────────────────────────────────────────────
# YAML UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def parse_yaml_block(text: str) -> dict:
    """Extract and parse the last ```yaml...``` block from text."""
    matches = re.findall(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    if not matches:
        raise yaml.YAMLError("No yaml block found in response")
    return yaml.safe_load(matches[-1])


# ─────────────────────────────────────────────────────────────────────────────
# CACHE MANAGER (Gemini)
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_FILE = Path(".rdf_cache.json")


def _stable_payload(root: Path, system_prompt: str) -> str:
    goal = (root / "goal.md").read_text(encoding="utf-8")
    log_path = root / "experiment_log.md"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    entries = log.split("\n---\n")
    older = "\n---\n".join(entries[:-3]) if len(entries) > 3 else ""
    return f"{system_prompt}\n\n# GOAL\n{goal}\n\n# OLDER LOG\n{older}"


def _usage_tokens(usage: Any) -> tuple[int, int, int]:
    """Return (input, cached, output) tokens – compatible with old and new Gemini SDK."""
    inp = getattr(usage, "prompt_token_count", None) or getattr(usage, "input_token_count", 0)
    cac = getattr(usage, "cached_content_token_count", 0)
    out = getattr(usage, "candidates_token_count", None) or getattr(usage, "output_token_count", 0)
    return inp or 0, cac or 0, out or 0


def _get_or_create_cache(root: Path, cfg: Config, system_prompt: str) -> Any:
    """Return a google.genai CachedContent or None (silent fallback)."""
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        return None

    goal = (root / "goal.md").read_text(encoding="utf-8")
    log_path = root / "experiment_log.md"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    entries = log.split("\n---\n")
    older = "\n---\n".join(entries[:-3]) if len(entries) > 3 else ""
    stable_content = f"# GOAL\n{goal}\n\n# OLDER LOG\n{older}"

    # Check minimum size: system_prompt + stable_content
    if len(system_prompt) + len(stable_content) < cfg.min_cache_tokens * 4:
        return None

    h = hashlib.sha256((system_prompt + stable_content).encode()).hexdigest()[:16]
    state: dict = {}
    if _CACHE_FILE.exists():
        try:
            state = json.loads(_CACHE_FILE.read_text())
        except Exception:
            pass

    client = genai.Client()

    if state.get("hash") == h:
        try:
            return client.caches.get(name=state["cache_name"])
        except Exception:
            pass

    try:
        cache = client.caches.create(
            model=cfg.strategy_model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=stable_content)],
                )],
                ttl=f"{cfg.cache_ttl_hours * 3600}s",
                display_name=f"rdf-{root.name}-{h}",
            ),
        )
        _CACHE_FILE.write_text(json.dumps({"hash": h, "cache_name": cache.name}))
        return cache
    except Exception as e:
        console.print(f"[yellow]Cache creation failed (uncached fallback): {e}[/yellow]")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY AGENT
# ─────────────────────────────────────────────────────────────────────────────

class StrategyAgent:
    def __init__(self) -> None:
        self._system_prompt: Optional[str] = None

    def _prompt(self, root: Path, cfg: Config) -> str:
        if self._system_prompt is None:
            self._system_prompt = _build_system_prompt(root, cfg.min_cache_tokens * 4)
        return self._system_prompt

    def call(
        self, root: Path, delta: str, cfg: Config,
        hint: Optional[str] = None, chosen_q: Optional[str] = None,
    ) -> tuple[dict, Any]:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        system_prompt = self._prompt(root, cfg)
        if hint:
            delta += f"\n\n## User Hint\n{hint}"
        if chosen_q:
            delta += f"\n\n## Focus Question\n{chosen_q}"

        cache = _get_or_create_cache(root, cfg, system_prompt)
        client = genai.Client()

        for attempt in range(3):
            try:
                if cache:
                    gen_cfg = types.GenerateContentConfig(cached_content=cache.name)
                else:
                    gen_cfg = types.GenerateContentConfig(system_instruction=system_prompt)

                resp = client.models.generate_content(
                    model=cfg.strategy_model,
                    contents=delta,
                    config=gen_cfg,
                )
                # YAML retry loop
                text = resp.text
                for parse_attempt in range(cfg.max_retries_on_parse_fail + 1):
                    try:
                        return parse_yaml_block(text), resp.usage_metadata
                    except yaml.YAMLError:
                        if parse_attempt >= cfg.max_retries_on_parse_fail:
                            raise
                        console.print("[yellow]YAML parse failed – retrying with correction prompt[/yellow]")
                        fix_resp = client.models.generate_content(
                            model=cfg.strategy_model,
                            contents=(
                                "Your previous response did not contain a valid ```yaml``` block. "
                                "Please respond again with the exact YAML schema specified."
                            ),
                            config=gen_cfg,
                        )
                        text = fix_resp.text
            except yaml.YAMLError:
                raise
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    console.print(f"[yellow]Gemini error (retry {attempt + 1}): {e}. Waiting {wait}s...[/yellow]")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("StrategyAgent.call exhausted retries")


class MockStrategyAgent:
    _HYPS = [
        "[mock] baseline: cosine-LR lr=1e-4 achieves val_loss < 3.5 at 1k steps",
        "[mock] warmup-500: adding 500-step warmup reduces val_loss by ≥2%",
        "[mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0",
    ]

    def call(
        self, root: Path, delta: str, cfg: Config,
        hint: Optional[str] = None, chosen_q: Optional[str] = None,
    ) -> tuple[dict, Any]:
        n = _read_iter_num(root) + 1
        hyp = self._HYPS[min(n - 1, len(self._HYPS) - 1)]
        data = {
            "analysis": f"[Mock] Iteration {n}. All systems nominal.",
            "open_questions": ["Mock question A?", "Mock question B?", "Mock question C?"],
            "chosen_direction": "Mock direction",
            "hypothesis": hyp,
            "rationale": "[Mock] This is the most promising direction.",
            "task_for_implementer": (
                f"Create archive/iter_{n:03d}/code/run.py that prints "
                f"'hello from iter {n}' and exits 0."
            ),
            "expected_outcome": "Script runs successfully.",
            "success_criteria": ["Script exits with code 0", "result.yaml present"],
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


# ─────────────────────────────────────────────────────────────────────────────
# IMPLEMENT AGENT  (Claude Agent SDK)
# ─────────────────────────────────────────────────────────────────────────────

import contextlib
import os as _os


@contextlib.contextmanager
def _project_venv(project_root: Path):
    """Temporarily prepend the project's .venv/bin (or Scripts on Windows) to
    PATH and set VIRTUAL_ENV so that any subprocess Claude Code spawns uses the
    project's own Python interpreter instead of the orchestrator's venv."""
    venv_dir = project_root / ".venv"
    if not venv_dir.is_dir():
        yield
        return

    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    old_path = _os.environ.get("PATH", "")
    old_venv = _os.environ.get("VIRTUAL_ENV")
    old_home = _os.environ.get("PYTHONHOME")

    _os.environ["PATH"] = str(bin_dir) + _os.pathsep + old_path
    _os.environ["VIRTUAL_ENV"] = str(venv_dir)
    _os.environ.pop("PYTHONHOME", None)
    try:
        yield
    finally:
        _os.environ["PATH"] = old_path
        if old_venv is not None:
            _os.environ["VIRTUAL_ENV"] = old_venv
        else:
            _os.environ.pop("VIRTUAL_ENV", None)
        if old_home is not None:
            _os.environ["PYTHONHOME"] = old_home


class ImplementAgent:
    async def run(self, task_text: str, iter_dir: Path, src_dir: Path, cfg: Config) -> dict:
        from claude_code_sdk import query, ClaudeCodeOptions  # type: ignore

        src_dir.mkdir(parents=True, exist_ok=True)

        tools = [t.strip() for t in cfg.allowed_tools.split(",")]
        kwargs: dict[str, Any] = {"allowed_tools": tools, "cwd": src_dir}
        if cfg.dangerously_skip_permissions:
            kwargs["permission_mode"] = "bypassPermissions"
        options = ClaudeCodeOptions(**kwargs)

        collected: list[str] = []
        errors: list[str] = []

        async def _stream() -> None:
            async for msg in query(prompt=task_text, options=options):
                if msg is None:
                    continue  # rate_limit_event or other unknown type – patched to None
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            collected.append(block.text)
                if getattr(msg, "is_error", False):
                    errors.append(str(getattr(msg, "error", msg)))

        project_root = src_dir.parent
        try:
            with _project_venv(project_root):
                timeout = cfg.experiment_timeout_sec
                if timeout:
                    await asyncio.wait_for(_stream(), timeout=float(timeout))
                else:
                    await _stream()
        except asyncio.TimeoutError:
            errors.append(f"Timeout after {cfg.experiment_timeout_sec}s")

        full_output = "\n".join(collected)
        (iter_dir / "stdout.txt").write_text(full_output, encoding="utf-8")
        (iter_dir / "stderr.txt").write_text("\n".join(errors), encoding="utf-8")

        try:
            result = parse_yaml_block(full_output)
        except yaml.YAMLError:
            # Fallback: Claude may have written result.yaml directly to iter_dir
            result_file = iter_dir / "result.yaml"
            if result_file.exists():
                try:
                    existing = yaml.safe_load(result_file.read_text(encoding="utf-8"))
                    if isinstance(existing, dict) and existing.get("status") not in (None, "code_error"):
                        return existing  # Use Claude's file; do not overwrite it
                except Exception:
                    pass
            result = {
                "status": "code_error",
                "artifacts": [],
                "metrics": {},
                "log_excerpt": full_output[-2000:],
                "experimenter_view": "No yaml block in output – check stdout.txt",
                "notes": "Parse failed",
            }

        (iter_dir / "result.yaml").write_text(yaml.dump(result, allow_unicode=True), encoding="utf-8")
        return result


class MockImplementAgent:
    async def run(self, task_text: str, iter_dir: Path, src_dir: Path, cfg: Config) -> dict:
        src_dir.mkdir(parents=True, exist_ok=True)
        n = int(re.search(r"\d+", iter_dir.name).group())

        script = src_dir / f"run_iter_{n:03d}.py"
        script.write_text(f'print("hello from iter {n}")\n', encoding="utf-8")

        result = {
            "status": "ok",
            "artifacts": [f"archive/iter_{n:03d}/code/run.py"],
            "metrics": {"mock_value": round(n * 1.5, 3)},
            "log_excerpt": f"hello from iter {n}",
            "experimenter_view": f"[Mock] Iteration {n} completed. No real computation.",
            "notes": "[Mock] dry-run",
        }
        (iter_dir / "stdout.txt").write_text(result["log_excerpt"], encoding="utf-8")
        (iter_dir / "stderr.txt").write_text("", encoding="utf-8")
        (iter_dir / "result.yaml").write_text(yaml.dump(result, allow_unicode=True), encoding="utf-8")
        await asyncio.sleep(0.05)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# GIT MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class GitManager:
    def _git(self, args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=check)

    def is_repo(self, root: Path) -> bool:
        return self._git(["rev-parse", "--is-inside-work-tree"], root, check=False).returncode == 0

    def commit(self, root: Path, message: str) -> None:
        self._git(["add", "-A"], root)
        r = self._git(["commit", "-m", message], root, check=False)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            console.print(f"[yellow]git commit warning: {r.stderr.strip()}[/yellow]")

    def tag(self, root: Path, name: str) -> None:
        self._git(["tag", name], root, check=False)

    def log_oneline(self, root: Path, n: int = 5) -> str:
        return self._git(["log", "--oneline", f"-{n}"], root, check=False).stdout.strip()

    def diff_stat(self, root: Path) -> str:
        return self._git(["diff", "--stat", "HEAD~1"], root, check=False).stdout.strip()


# ─────────────────────────────────────────────────────────────────────────────
# STATE & LOG
# ─────────────────────────────────────────────────────────────────────────────

def _read_iter_num(root: Path) -> int:
    archive = root / "archive"
    if not archive.exists():
        return 0
    nums = [
        int(d.name.split("_")[1])
        for d in archive.iterdir()
        if d.is_dir() and re.fullmatch(r"iter_\d+", d.name)
    ]
    return max(nums, default=0)


def _tokens(text: str) -> int:
    return len(text) // 4


def _append_log(
    root: Path, n: int, sy: dict, iy: dict, usage: Any, cost: float
) -> None:
    entry_yaml = yaml.dump({
        "iter": n,
        "hypothesis": sy.get("hypothesis", ""),
        "status": iy.get("status", "unknown"),
        "metrics": iy.get("metrics", {}),
        "cost_usd": round(cost, 5),
        "input_tokens": _usage_tokens(usage)[0],
        "cached_tokens": _usage_tokens(usage)[1],
        "output_tokens": _usage_tokens(usage)[2],
    }, allow_unicode=True)

    body = (
        f"## iter_{n:03d}: {sy.get('hypothesis', '')}\n\n"
        f"**Analysis:** {sy.get('analysis', '').strip()}\n\n"
        f"**Task:** {sy.get('task_for_implementer', '').strip()}\n\n"
        f"**Status:** {iy.get('status', 'unknown')}\n\n"
        f"**Experimenter view:** {iy.get('experimenter_view', '')}\n\n"
        f"**Metrics:** `{iy.get('metrics', {})}`\n"
    )
    with open(root / "experiment_log.md", "a", encoding="utf-8") as f:
        f.write(f"\n---\n```yaml\n{entry_yaml}```\n\n{body}\n")


def _update_state(
    root: Path, new_state: str, cfg: Config,
    strategy: StrategyAgent | MockStrategyAgent, delta: str,
) -> None:
    state_path = root / "current_state.md"
    if _tokens(new_state) <= cfg.max_state_tokens:
        state_path.write_text(new_state, encoding="utf-8")
        return

    for _ in range(cfg.max_retries_on_state_too_long):
        shorten = (
            f"{delta}\n\nThe proposed state_update has {_tokens(new_state)} tokens "
            f"(max {cfg.max_state_tokens}). Please provide a shorter version "
            f"that preserves all key findings."
        )
        try:
            data, _ = strategy.call(root, shorten, cfg)
            new_state = data.get("state_update", new_state)
            if _tokens(new_state) <= cfg.max_state_tokens:
                state_path.write_text(new_state, encoding="utf-8")
                return
        except Exception:
            break

    truncated = new_state[: cfg.max_state_tokens * 4] + "\n\n[truncated]"
    state_path.write_text(truncated, encoding="utf-8")
    console.print("[yellow]WARNING: current_state.md truncated to fit token limit.[/yellow]")


def _estimate_cost(usage: Any, model: str) -> float:
    inp, cac, out = _usage_tokens(usage)
    if "2.5-pro" in model:
        ip, cp, op = 3.50e-6, 0.875e-6, 10.50e-6
    else:
        ip, cp, op = 1.00e-6, 0.25e-6, 3.00e-6
    return max(0, inp - cac) * ip + cac * cp + out * op


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

_GOAL_TEMPLATE = """\
# Forschungsziel

<1-3 Absätze: Beschreibe das Forschungsziel>

## Erfolgskriterien

- ...

## Beschränkungen

- ...
"""

_STATE_TEMPLATE = """\
# Aktueller Wissensstand

(noch nicht initialisiert – Bootstrap erforderlich)
"""

_LOG_TEMPLATE = """\
# Experiment Log
<!-- Append-only. Eintragstrenner: \\n---\\n zwischen YAML-Blöcken. -->
"""

_CONFIG_TEMPLATE = """\
[models]
strategy = "gemini-2.5-pro"
implementation_cli = "claude"

[claude_code]
allowed_tools = "Read,Write,Edit,Bash"
dangerously_skip_permissions = false

[limits]
max_iterations = 100
max_state_tokens = 8000
strategy_timeout_sec = 180
experiment_timeout_sec = 14400
max_retries_on_parse_fail = 2
max_retries_on_state_too_long = 2

[cache]
ttl_hours = 6
min_cache_tokens = 32768

[git]
auto_commit = true
session_branch = false

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
# The orchestrator will automatically use this venv for the Claude agent
# if .venv/ exists in the project directory.
"""


class Orchestrator:
    def __init__(self, root: Path, cfg: Config, dry_run: bool = False) -> None:
        self.root = root
        self.cfg = cfg
        self.dry_run = dry_run
        self.git = GitManager()
        self.session_cost = 0.0
        self.strategy: StrategyAgent | MockStrategyAgent = (
            MockStrategyAgent() if dry_run else StrategyAgent()
        )
        self.implement: ImplementAgent | MockImplementAgent = (
            MockImplementAgent() if dry_run else ImplementAgent()
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
            editor = os.environ.get("EDITOR", "notepad" if sys.platform == "win32" else "nano")
            subprocess.run([editor, str(self.root / "goal.md")])

        self.git.commit(self.root, "init: project scaffold")
        console.print("[green]OK Done. Edit goal.md, then run: python orchestrator.py --project <dir> run[/green]")

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
                f"# Aktueller Wissensstand (Mock Bootstrap)\n\n"
                f"## Ziel\n{goal.strip()}\n\n"
                f"## Status\nBereit für Iteration 1.\n\n"
                f"## Offene Fragen\n- Mock-Frage A?\n- Mock-Frage B?\n"
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
            data, _ = self.strategy.call(self.root, delta, self.cfg)
            state = data.get("state_update", goal)

        (self.root / "current_state.md").write_text(state, encoding="utf-8")
        if self.cfg.auto_commit:
            self.git.commit(self.root, "bootstrap: initial state from goal.md")
        console.print("[green]OK Bootstrap complete.[/green]")

    # ── iteration ─────────────────────────────────────────────────────────────

    def _delta_prompt(self, n: int, hint: Optional[str], chosen_q: Optional[str]) -> str:
        state = (self.root / "current_state.md").read_text(encoding="utf-8")
        log_path = self.root / "experiment_log.md"
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        entries = log.split("\n---\n")
        last3 = "\n---\n".join(entries[-3:]) if entries else ""
        prompt = (
            f"# Iteration {n}\n\n"
            f"## Current State\n{state}\n\n"
            f"## Recent Log (last 3 entries)\n{last3}\n"
        )
        if hint:
            prompt += f"\n## User Hint\n{hint}\n"
        if chosen_q:
            prompt += f"\n## Focus Question\n{chosen_q}\n"
        return prompt

    async def _run_iteration(
        self, n: int, hint: Optional[str], chosen_q: Optional[str]
    ) -> tuple[dict, dict, float]:
        console.rule(f"[bold blue]ITERATION {n:03d}[/bold blue]")
        iter_dir = self.root / "archive" / f"iter_{n:03d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        src_dir = self.root / "src"
        src_dir.mkdir(exist_ok=True)

        # STRATEGY
        console.print("[bold]-> STRATEGY (Gemini)[/bold]")
        delta = self._delta_prompt(n, hint, chosen_q)
        with console.status("Calling Gemini..."):
            sy, usage = self.strategy.call(self.root, delta, self.cfg, hint, chosen_q)

        hypothesis = sy.get("hypothesis", "")
        console.print(f"[green]Hypothesis:[/green] {hypothesis}")

        task_path = iter_dir / "task.md"
        task_path.write_text(
            f"# Task – iter_{n:03d}\n\n"
            f"**Hypothesis:** {hypothesis}\n\n"
            f"## Working Directory\n\n"
            f"Your working directory is `src/` – a **persistent** directory shared across all "
            f"iterations. Build on code from previous iterations; do not start from scratch each time.\n"
            f"Write results and data files to `archive/iter_{n:03d}/results/` "
            f"(relative to the project root).\n\n"
            f"## Task\n\n{sy.get('task_for_implementer', '')}\n\n"
            f"## Success Criteria\n\n"
            + "\n".join(f"- {c}" for c in sy.get("success_criteria", []))
            + "\n\n## Required Output\n\n"
            "You MUST end your final response with a ```yaml``` code block in this exact schema "
            "(the orchestrator reads it to determine success):\n\n"
            "```yaml\n"
            "status: ok  # or experiment_failed or code_error\n"
            "artifacts:\n"
            "  - path/to/created/file  # relative to the project root\n"
            "metrics:\n"
            "  key: value  # any numeric results\n"
            "log_excerpt: |  # last ~20 lines of relevant output\n"
            "  ...\n"
            "experimenter_view: |  # your qualitative observations\n"
            "  ...\n"
            "notes: brief technical remark\n"
            "```\n",
            encoding="utf-8",
        )

        # IMPLEMENT
        console.print("[bold]-> IMPLEMENT (Claude Code)[/bold]")
        with console.status("Running Claude Code..."):
            iy = await self.implement.run(task_path.read_text(encoding="utf-8"), iter_dir, src_dir, self.cfg)
        console.print(f"[green]Status:[/green] {iy.get('status', 'unknown')}")

        # UPDATE
        cost = _estimate_cost(usage, self.cfg.strategy_model)
        self.session_cost += cost
        _append_log(self.root, n, sy, iy, usage, cost)
        new_state = sy.get("state_update", "")
        if new_state:
            _update_state(self.root, new_state, self.cfg, self.strategy, delta)

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
                tag = "milestone-" + re.sub(r"[^a-z0-9]+", "-", milestone.lower()).strip("-")
                self.git.tag(self.root, tag)
                console.print(f"[bold green]Milestone tagged: {tag}[/bold green]")
            if hypothesis.startswith("[CONVERGED]"):
                self.git.tag(self.root, f"converged-{n:03d}")
                console.print(f"[bold green]Converged – tagged converged-{n:03d}[/bold green]")

        inp, cac, out = _usage_tokens(usage)
        console.print(
            f"[dim]Tokens: {inp/1000:.1f}k in (cached {cac/1000:.1f}k), "
            f"{out/1000:.1f}k out | ~${cost:.4f} | session ~${self.session_cost:.4f}[/dim]"
        )
        return sy, iy, cost

    # ── menu ──────────────────────────────────────────────────────────────────

    def _menu(
        self, n: int, sy: dict, iy: dict, cost: float
    ) -> tuple[str, Optional[str], Optional[str]]:
        open_qs = sy.get("open_questions", [])
        milestone = (sy.get("milestone_reached") or "").strip()

        # Read first non-empty paragraph from current_state.md for the status line
        state_summary = ""
        state_path = self.root / "current_state.md"
        if state_path.exists():
            raw_state = state_path.read_text(encoding="utf-8")
            for line in raw_state.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    state_summary = stripped[:120] + ("…" if len(stripped) > 120 else "")
                    break

        milestone_line = (
            f"\n[bold green]MILESTONE:[/bold green] {milestone}" if milestone else ""
        )
        panel_body = (
            f"[bold]Iteration:[/bold] {n}/{self.cfg.max_iterations}"
            + milestone_line + "\n"
            f"[bold]Hypothese:[/bold] {sy.get('hypothesis', '')}\n"
            f"[bold]Status:[/bold]    {iy.get('status', 'unknown')}\n"
            f"[bold]Metriken:[/bold]  {iy.get('metrics', {})}\n"
            f"[bold]Kosten:[/bold]    ~${cost:.4f} | Session ~${self.session_cost:.4f}\n"
            + (f"[dim]{state_summary}[/dim]" if state_summary else "")
        )
        title_color = "bold green" if milestone else "bold blue"
        console.print()
        console.print(Panel(panel_body,
            title=f"[{title_color}]── ITERATION {n:03d} ABGESCHLOSSEN ──[/{title_color}]",
        ))
        if milestone:
            console.print(
                f"\n[bold green]Milestone erreicht: {milestone}[/bold green]  "
                f"(git tag: milestone-{re.sub(r'[^a-z0-9]+', '-', milestone.lower()).strip('-')})"
            )
        if open_qs:
            console.print("\n[bold]Forschungsrichtungen, die Gemini erkunden will:[/bold]")
            for i, q in enumerate(open_qs, 1):
                console.print(f"  [cyan]{i}.[/cyan] {q}")

        o_hint = f"  o1-o{len(open_qs)}  Forschungsrichtung als Fokus (z.B. o2)\n" if open_qs else ""
        console.print(
            "\n[bold]Aktionen[/bold] – Buchstabe(n) + Enter:\n"
            "  y      Naechste Iteration (Gemini waehlt Richtung)\n"
            + o_hint +
            "  h      Hinweis an Gemini fuer naechste Iteration\n"
            "  r      Iteration wiederholen (mit neuem Hinweis)\n"
            "  d      git diff --stat HEAD~1\n"
            "  s      Status-Bericht (git log)\n"
            "  n      Stoppen und speichern\n",
            markup=False,
        )

        while True:
            raw = console.input("[bold]Eingabe:[/bold] ").strip().lower()

            hint: Optional[str] = None
            chosen_q: Optional[str] = None

            # o<N>: one-step research direction focus
            m = re.match(r"^o(\d+)$", raw)
            if m and open_qs:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(open_qs):
                    chosen_q = open_qs[idx]
                    console.print(f"[green]Fokus:[/green] {chosen_q}")
                    return "y", hint, chosen_q
                console.print(f"[yellow]Bitte o1 bis o{len(open_qs)} eingeben.[/yellow]")
                continue

            if raw == "d":
                console.print(self.git.diff_stat(self.root) or "(kein Diff)", markup=False)
                continue
            if raw == "s":
                console.print(f"\n[bold]git log:[/bold]\n{self.git.log_oneline(self.root)}")
                continue
            if raw in ("h", "r"):
                hint = console.input("Hinweis an Gemini: ").strip()
                if raw == "h":
                    raw = "y"
            if raw in ("y", "r", "n"):
                return raw, hint, chosen_q
            console.print("[yellow]Unbekannte Eingabe.[/yellow]")

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _async_run_loop(self) -> None:
        if not (self.root / "goal.md").exists():
            console.print("[red]No goal.md. Run: python orchestrator.py --project <dir> init[/red]")
            sys.exit(1)

        state_text = ""
        state_path = self.root / "current_state.md"
        if state_path.exists():
            state_text = state_path.read_text(encoding="utf-8")

        if "Bootstrap erforderlich" in state_text and _read_iter_num(self.root) == 0:
            self.bootstrap()

        # Warn if project has requirements.txt but no .venv yet
        if not self.dry_run:
            venv_dir = self.root / ".venv"
            req_file = self.root / "requirements.txt"
            if req_file.exists() and not venv_dir.is_dir():
                console.print(
                    "[yellow]Hinweis: requirements.txt gefunden, aber kein .venv/. "
                    "Der Experimentator nutzt das System-Python. "
                    "Eigenes venv anlegen mit:[/yellow]\n"
                    f"  python -m venv {self.root / '.venv'}\n"
                    f"  {self.root / '.venv' / ('Scripts' if sys.platform == 'win32' else 'bin') / 'pip'}"
                    f" install -r {req_file}",
                    markup=False,
                )

        hint: Optional[str] = None
        chosen_q: Optional[str] = None
        retry = False

        for _ in range(self.cfg.max_iterations):
            n = _read_iter_num(self.root) + (0 if retry else 1)
            sy, iy, cost = await self._run_iteration(n, hint, chosen_q)

            if self.dry_run:
                if n >= 3:
                    console.print("[bold green]Dry-run complete (3 iterations).[/bold green]")
                    self._acceptance_report()
                    return
                # auto-advance without menu
                hint = None
                chosen_q = None
                retry = False
                continue

            choice, hint, chosen_q = self._menu(n, sy, iy, cost)
            retry = choice == "r"

            if choice == "n":
                console.print("[bold]Gestoppt.[/bold]")
                break

            if sy.get("hypothesis", "").startswith("[CONVERGED]"):
                console.print("[bold green]Loop konvergiert.[/bold green]")
                break

        console.print(f"[bold]Session-Gesamtkosten: ~${self.session_cost:.4f}[/bold]")

    def run_loop(self) -> None:
        asyncio.run(self._async_run_loop())

    # ── acceptance report ─────────────────────────────────────────────────────

    def _acceptance_report(self) -> None:
        console.rule("[bold green]ABNAHME-SIGNAL[/bold green]")

        console.print("\n[bold]1. Erstellte Dateien:[/bold]")
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                console.print(f"  {p.relative_to(self.root)}")

        console.print(f"\n[bold]2. git log --oneline:[/bold]\n{self.git.log_oneline(self.root, 10)}")

        console.print("""
[bold]3. Implementierungsannahmen:[/bold]
  - System-Prompt: Methodik-Text + 3 Few-Shot-Beispiele (Transformer/LR-Suche)
    + Anhänge. Wird automatisch auf ≥ min_cache_tokens Zeichen aufgefüllt.
  - Few-Shot-Inhalte: fiktiver WikiText-103 Forschungslauf (domainagnostisch).
    Für Domänen-Spezifik: system_glossary.md anlegen.
  - Gemini-Kosten-Schätzung: 2.5 Pro Preise (Stand 2025). Kann abweichen.
  - Claude Agent SDK: async query()-API, cwd = src/ (persistent across iterations).
    permission_mode "bypassPermissions" nur bei dangerously_skip_permissions=true.
  - Token-Schätzung: 1 Token ≈ 4 Zeichen (Gemini-Konvention).
""")

        console.print("""[bold]4. TODOs vor dem ersten echten Lauf:[/bold]
  [ ] GEMINI_API_KEY exportieren: export GEMINI_API_KEY=...
  [ ] Claude Code anmelden: claude login
  [ ] goal.md mit dem echten Forschungsziel befüllen
  [ ] Optional: system_glossary.md anlegen (Domain-Begriffe für Gemini)
  [ ] Optional: config.toml anpassen (Timeouts, Modelle, ...)
  [ ] Optional: Few-Shot-Beispiele im System-Prompt auf die Domain zuschneiden
      (_CORE in orchestrator.py)
""")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _auto_init_for_dryrun(root: Path, orch: Orchestrator) -> None:
    """Minimal silent init so dry-run works without prior `init`."""
    orch._write_if_missing("goal.md",
        "# Forschungsziel (Mock)\n\nDry-run Forschungsziel.\n\n"
        "## Erfolgskriterien\n- Dry-run läuft durch\n")
    orch._write_if_missing("current_state.md", _STATE_TEMPLATE)
    orch._write_if_missing("experiment_log.md", _LOG_TEMPLATE)
    orch._write_if_missing(".gitignore", _GITIGNORE)
    (root / "archive").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    if not orch.git.is_repo(root):
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True)
    orch.git.commit(root, "init: project scaffold")


def main() -> None:
    parser = argparse.ArgumentParser(description="RDF v3 Orchestrator")
    parser.add_argument(
        "--project", type=Path, default=None,
        help="Path to research project directory (default: current directory)",
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
            console.print("[yellow]DRY-RUN – keine API-Calls[/yellow]")
            if not (root / "goal.md").exists():
                _auto_init_for_dryrun(root, orch)
        orch.run_loop()


if __name__ == "__main__":
    main()
