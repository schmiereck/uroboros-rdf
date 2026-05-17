"""Experiment log management: append, trim, read, and overview generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from rdf.config import Config

console = Console(highlight=False, legacy_windows=False)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


def usage_tokens(usage: Any) -> tuple[int, int, int]:
    """Return (input, cached, output) tokens from any SDK usage object."""
    inp = getattr(usage, "prompt_token_count", None) or getattr(
        usage, "input_token_count", 0
    )
    cac = getattr(usage, "cached_content_token_count", 0)
    out = getattr(usage, "candidates_token_count", None) or getattr(
        usage, "output_token_count", 0
    )
    return inp or 0, cac or 0, out or 0


def estimate_cost(usage: Any, model: str) -> float:
    inp, cac, out = usage_tokens(usage)
    m = model.lower()
    if "2.5-pro" in m:
        ip, cp, op = 3.50e-6, 0.875e-6, 10.50e-6
    elif "qwen" in m:
        ip, cp, op = 0.10e-6, 0.0, 0.10e-6
    elif "sonnet" in m:
        ip, cp, op = 3.00e-6, 0.0, 15.00e-6
    elif "opus" in m:
        ip, cp, op = 15.00e-6, 0.0, 75.00e-6
    else:
        ip, cp, op = 1.00e-6, 0.25e-6, 3.00e-6
    return max(0, inp - cac) * ip + cac * cp + out * op


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------

def append_log(
    root: Path, n: int, sy: dict, iy: dict, usage: Any, cost: float
) -> None:
    entry: dict = {
        "iter": n,
        "hypothesis": sy.get("hypothesis", ""),
        "status": iy.get("status", "unknown"),
        "metrics": iy.get("metrics", {}),
        "cost_usd": round(cost, 5),
        "input_tokens": usage_tokens(usage)[0],
        "cached_tokens": usage_tokens(usage)[1],
        "output_tokens": usage_tokens(usage)[2],
    }
    for key in ("campaign", "campaign_status", "campaign_summary"):
        val = (sy.get(key) or "").strip()
        if val:
            entry[key] = val

    entry_yaml = yaml.dump(entry, allow_unicode=True)
    body = (
        f"## iter_{n:03d}: {sy.get('hypothesis', '')}\n\n"
        f"**Analysis:** {sy.get('analysis', '').strip()[:400]}\n\n"
        f"**Status:** {iy.get('status', 'unknown')}\n\n"
        f"**Metrics:** `{iy.get('metrics', {})}`\n\n"
        f"**Experimenter view:** {iy.get('experimenter_view', '').strip()[:400]}\n\n"
        f"**Notes:** {iy.get('notes', '').strip()}\n"
    )
    with open(root / "experiment_log.md", "a", encoding="utf-8") as f:
        f.write(f"\n---\n```yaml\n{entry_yaml}```\n\n{body}\n")


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

def trim_log_if_needed(root: Path, max_entries: int) -> None:
    if max_entries <= 0:
        return
    log_path = root / "experiment_log.md"
    if not log_path.exists():
        return
    text = log_path.read_text(encoding="utf-8")
    parts = text.split("\n---\n")
    header, entries = parts[0], parts[1:]
    if len(entries) <= max_entries:
        return
    to_archive, to_keep = entries[:-max_entries], entries[-max_entries:]
    archive_path = root / "experiment_log_archive.md"
    with open(archive_path, "a", encoding="utf-8") as f:
        if not archive_path.exists() or archive_path.stat().st_size == 0:
            f.write("# Experiment Log Archive\n")
        for e in to_archive:
            f.write(f"\n---\n{e}")
    log_path.write_text(
        header + "\n---\n" + "\n---\n".join(to_keep), encoding="utf-8"
    )
    n = len(to_archive)
    console.print(f"[dim]Log trimmed: {n} {'entry' if n == 1 else 'entries'} archived.[/dim]")


# ---------------------------------------------------------------------------
# Read / overview
# ---------------------------------------------------------------------------

def read_log_rows(root: Path) -> list[dict]:
    """Parse all YAML log entries from both log files, sorted by iter number."""
    rows: list[dict] = []
    for log_path in [root / "experiment_log_archive.md", root / "experiment_log.md"]:
        if not log_path.exists():
            continue
        for block in re.findall(
            r"```yaml\s*\n(.*?)```",
            log_path.read_text(encoding="utf-8"),
            re.DOTALL,
        ):
            try:
                data = yaml.safe_load(block)
                if isinstance(data, dict) and "iter" in data:
                    rows.append(data)
            except Exception:
                pass
    rows.sort(key=lambda x: x.get("iter", 0))
    return rows


def iter_overview(root: Path) -> str:
    """Campaign-grouped overview embedded in every planner delta prompt."""
    rows = read_log_rows(root)
    if not rows:
        return "(no iterations yet)"

    ungrouped: list[dict] = []
    campaign_order: list[str] = []
    campaigns: dict[str, dict] = {}

    for r in rows:
        camp = (r.get("campaign") or "").strip()
        if not camp:
            ungrouped.append(r)
        else:
            if camp not in campaigns:
                campaign_order.append(camp)
                campaigns[camp] = {"rows": [], "completed": False, "summary": ""}
            campaigns[camp]["rows"].append(r)
            if (r.get("campaign_status") or "").strip() == "completed":
                campaigns[camp]["completed"] = True
                campaigns[camp]["summary"] = (r.get("campaign_summary") or "").strip()

    lines: list[str] = []

    if ungrouped:
        lines.append("[ungrouped]")
        lines.append("  iter | status          | hypothesis")
        lines.append("  -----|-----------------|----------")
        for r in ungrouped:
            lines.append(
                f"  {r['iter']:03d}  | {str(r.get('status', '')):<16}| {r.get('hypothesis', '')}"
            )
        lines.append("")

    for name in campaign_order:
        c = campaigns[name]
        camp_rows = c["rows"]
        first_i, last_i = camp_rows[0]["iter"], camp_rows[-1]["iter"]
        if c["completed"]:
            lines.append(
                f"[{name}] COMPLETED  (iter {first_i:03d}–{last_i:03d}, "
                f"{len(camp_rows)} iterations)"
            )
            for line in c["summary"].split("\n"):
                lines.append(f"  {line}")
            lines.append(f'  → read_campaign("{name}") to see all iterations')
        else:
            lines.append(f"[{name}] active")
            lines.append("  iter | status          | hypothesis")
            lines.append("  -----|-----------------|----------")
            for r in camp_rows:
                lines.append(
                    f"  {r['iter']:03d}  | {str(r.get('status', '')):<16}| {r.get('hypothesis', '')}"
                )
        lines.append("")

    return "\n".join(lines).rstrip()
