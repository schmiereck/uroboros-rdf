"""Tool declarations for the planner (model-agnostic format).

Each declaration is a ToolDeclaration instance that any PlannerAdapter can
convert to its native format (Gemini FunctionDeclaration, Anthropic Tool, etc.).
"""

from __future__ import annotations

from rdf.adapters.base import ToolDeclaration

# ---------------------------------------------------------------------------
# Read tools (Phase 1 — unchanged)
# ---------------------------------------------------------------------------

LIST_ITERATIONS = ToolDeclaration(
    name="list_iterations",
    description=(
        "Returns a compact table of all completed iterations with iter number, "
        "status, and one-line hypothesis. Call this first to identify which "
        "past iteration is relevant, then use read_iteration for the full record."
    ),
    parameters={"type": "object", "properties": {}},
)

READ_ITERATION = ToolDeclaration(
    name="read_iteration",
    description=(
        "Returns the full record of a past iteration: hypothesis, analysis, "
        "task, implementation status, metrics, experimenter observations, "
        "and a list of ALL files available anywhere under archive/iter_NNN/ "
        "(including subdirectories such as population/, checkpoints/, etc.)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "iter_num": {
                "type": "integer",
                "description": "The iteration number to read (e.g. 3 for iter_003).",
            }
        },
        "required": ["iter_num"],
    },
)

READ_RESULT_FILE = ToolDeclaration(
    name="read_result_file",
    description=(
        "Reads a text file from anywhere under archive/iter_NNN/. "
        "filename may be a plain filename ('rules.csv') or a relative "
        "sub-path ('population/rule_001.json'). "
        "Use read_iteration first to see which files are available. "
        "Binary files (images, pickles) cannot be read this way. "
        "Files larger than 50 KB are truncated."
    ),
    parameters={
        "type": "object",
        "properties": {
            "iter_num": {
                "type": "integer",
                "description": "The iteration number (e.g. 3 for iter_003).",
            },
            "filename": {
                "type": "string",
                "description": (
                    "Relative path within archive/iter_NNN/ "
                    "(e.g. 'rules.csv' or 'population/rule_001.json')."
                ),
            },
        },
        "required": ["iter_num", "filename"],
    },
)

READ_CAMPAIGN = ToolDeclaration(
    name="read_campaign",
    description=(
        "Returns all iteration records for a named campaign. "
        "Use when you need to review the full history of a completed "
        "(collapsed) campaign shown in the overview."
    ),
    parameters={
        "type": "object",
        "properties": {
            "campaign_name": {
                "type": "string",
                "description": "Exact campaign name as shown in the overview.",
            }
        },
        "required": ["campaign_name"],
    },
)

# ---------------------------------------------------------------------------
# Execution tools (Phase 2 — new)
# ---------------------------------------------------------------------------

RUN_AGENT = ToolDeclaration(
    name="run_agent",
    description=(
        "Starts a sub-agent to execute a task and waits up to estimated_runtime_sec. "
        "Returns immediately with done=True and final_result when the agent finishes "
        "before the timeout. Returns done=False with intermediate_state if still running. "
        "Only one sub-agent may run at a time — call poll_agent or stop_agent first "
        "if another is already running."
    ),
    parameters={
        "type": "object",
        "properties": {
            "iter_id": {
                "type": "string",
                "description": (
                    "Dot-separated iteration ID for the sub-agent's output directory "
                    "(e.g. '001.1' for the first sub-task of iter_001)."
                ),
            },
            "task": {
                "type": "string",
                "description": "Full task description / prompt for the sub-agent.",
            },
            "complexity": {
                "type": "string",
                "description": (
                    "Task complexity — controls agent type and model selection. "
                    "'low' (Haiku), 'medium' (Sonnet), 'high' (Opus) spawn an "
                    "Executor (Claude Code). "
                    "'planner' spawns a full inner Planner (Gemini) that can "
                    "itself call run_agent, forming a recursive hierarchy."
                ),
            },
            "estimated_runtime_sec": {
                "type": "integer",
                "description": (
                    "Expected runtime in seconds. The tool returns after this many "
                    "seconds even if the agent is still running."
                ),
            },
            "timeout_sec": {
                "type": "integer",
                "description": "Hard timeout after which the agent is forcibly stopped.",
            },
        },
        "required": ["iter_id", "task", "complexity", "estimated_runtime_sec"],
    },
)

POLL_AGENT = ToolDeclaration(
    name="poll_agent",
    description=(
        "Check whether a previously started sub-agent has finished. "
        "Returns done=True with final_result when complete. "
        "Returns done=False with latest intermediate_state when still running."
    ),
    parameters={
        "type": "object",
        "properties": {
            "iter_id": {
                "type": "string",
                "description": "The iter_id passed to run_agent.",
            }
        },
        "required": ["iter_id"],
    },
)

STOP_AGENT = ToolDeclaration(
    name="stop_agent",
    description=(
        "Forcibly stop a running sub-agent. After this call a new run_agent "
        "may be started."
    ),
    parameters={
        "type": "object",
        "properties": {
            "iter_id": {
                "type": "string",
                "description": "The iter_id of the agent to stop.",
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for stopping (logged to stderr.txt).",
            },
        },
        "required": ["iter_id"],
    },
)

# ---------------------------------------------------------------------------
# Convenience groups
# ---------------------------------------------------------------------------

READ_TOOL_DECLARATIONS: list[ToolDeclaration] = [
    LIST_ITERATIONS,
    READ_ITERATION,
    READ_RESULT_FILE,
    READ_CAMPAIGN,
]

EXEC_TOOL_DECLARATIONS: list[ToolDeclaration] = [
    RUN_AGENT,
    POLL_AGENT,
    STOP_AGENT,
]

ALL_TOOL_DECLARATIONS: list[ToolDeclaration] = (
    READ_TOOL_DECLARATIONS + EXEC_TOOL_DECLARATIONS
)
