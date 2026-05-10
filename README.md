# Uroboros-RDF

**Recursive Discovery Framework v3** — an autonomous research orchestrator that pairs two AI agents in an iterative experiment loop:

- **Gemini 2.5 Pro** (strategy) — analyses results, forms falsifiable hypotheses, and plans the next experiment
- **Claude Code** (implementation) — executes the experiment: writes code, runs simulations, collects metrics

Each iteration produces a git commit. The loop runs until a research milestone is reached or you stop it.

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│  STRATEGY  Gemini 2.5 Pro (context-cached system prompt)    │
│  · analyses current state + last 3 log entries              │
│  · proposes one falsifiable hypothesis                       │
│  · writes a concrete task for the implementer               │
└──────────────────────┬──────────────────────────────────────┘
                       │ task.md
┌──────────────────────▼──────────────────────────────────────┐
│  IMPLEMENT  Claude Code SDK (cwd = project/src/)            │
│  · reads task, writes/modifies code in src/                 │
│  · runs experiments, saves results to archive/iter_NNN/     │
│  · reports metrics + status in a YAML block                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ result.yaml
┌──────────────────────▼──────────────────────────────────────┐
│  COMMIT  git commit + optional push                         │
│  · milestone_reached → git tag milestone-<name>             │
│  · [CONVERGED] hypothesis → git tag converged-NNN           │
└─────────────────────────────────────────────────────────────┘
```

After each iteration the menu lets you:

| Key | Action |
|-----|--------|
| `y` | Next iteration (Gemini chooses direction freely) |
| `a` | Autonomous mode — runs until milestone, 2 consecutive errors, or a hypothesis loop |
| `o2` | Steer Gemini toward open question 2 |
| `h` | Give Gemini a hint for the next iteration |
| `r` | Repeat the current iteration with a new hint |
| `n` | Stop and save |

Gemini can also pause autonomous mode itself by setting `user_question` in its output — a magenta prompt appears and your answer is passed back as context.

---

## Project layout (two repos)

| Repo | Purpose |
|------|---------|
| `uroboros-rdf/` | **This repo** — the tool: `orchestrator.py`, `docs/`, `requirements.txt` |
| `rdf_digital_physic/` | Research project — `goal.md`, `src/`, `archive/`, `config.toml` |

Code written by the Claude agent lives in `project/src/` and persists across all iterations. Per-iteration metadata (task, result, results data) goes to `project/archive/iter_NNN/`.

---

## Setup

**Requirements:** Python 3.11+, a Gemini API key, Claude Code CLI logged in.

```bash
# 1. Clone and create the tool venv
git clone https://github.com/schmiereck/uroboros-rdf
cd uroboros-rdf
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. Set your Gemini API key
set GEMINI_API_KEY=your-key-here   # Windows
# export GEMINI_API_KEY=...        # Linux / macOS

# 3. Authenticate Claude Code
claude login
```

---

## Creating a new research project

```bash
# Initialise a project directory
python orchestrator.py --project path\to\my_project init

# Edit goal.md with your research objective, then run
python orchestrator.py --project path\to\my_project run
```

The project directory gets its own `requirements.txt` and optionally its own `.venv/` for experiment dependencies. If `project/.venv/` exists the orchestrator activates it automatically for the Claude agent.

### Dry-run (no API keys needed)

```bash
python orchestrator.py --project path\to\my_project run --dry-run
```

Runs 3 mock iterations with fake agents to verify the pipeline end-to-end.

---

## Example research project

**Digital Physics / Bit-Grid Universe** — exploring whether physical phenomena like mass, gravity, and time dilation can emerge from minimal reversible rules on a discrete lattice.

→ [schmiereck/rdf_digital_physic](https://github.com/schmiereck/rdf_digital_physic)

Phase 1 result: 22 of 33 reversible bit-conserving rules produce stable gliders in a 1D 3-bit cellular automaton.

---

## Configuration (`config.toml` in the project directory)

```toml
[models]
strategy = "gemini-2.5-pro"

[claude_code]
allowed_tools = "Read,Write,Edit,Bash"
dangerously_skip_permissions = false

[limits]
max_iterations = 100
experiment_timeout_sec = 14400   # 4 h per Claude run; null = unlimited

[git]
auto_commit = true
auto_push = false   # set to true to push to GitHub after every iteration

[cache]
ttl_hours = 6
min_cache_tokens = 32768   # Gemini context cache minimum
```
