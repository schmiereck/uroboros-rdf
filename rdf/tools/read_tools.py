"""Read-only tools exposed to the planner: list_iterations, read_iteration,
read_result_file, read_campaign."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from rdf.iter_id import top_level_count

_MAX_RESULT_FILE_BYTES = 50_000


def list_iterations(root: Path) -> str:
    """Return a compact table of all completed iterations."""
    rows: list[dict] = []
    for log_path in [root / "experiment_log_archive.md", root / "experiment_log.md"]:
        if not log_path.exists():
            continue
        text = log_path.read_text(encoding="utf-8")
        for block in re.findall(r"```yaml\s*\n(.*?)```", text, re.DOTALL):
            try:
                data = yaml.safe_load(block)
                if isinstance(data, dict) and "iter" in data:
                    rows.append(data)
            except Exception:
                pass
    if not rows:
        return "No iterations completed yet."
    rows.sort(key=lambda x: x.get("iter", 0))
    lines = ["iter | status          | hypothesis", "-----|-----------------|----------"]
    for r in rows:
        lines.append(
            f"{r['iter']:03d}  | {str(r.get('status', '')):<16}| {r.get('hypothesis', '')}"
        )
    return "\n".join(lines)


def read_iteration(root: Path, iter_num: int) -> str:
    """Return the full log record for a past iteration plus a file listing."""
    record = ""
    for log_path in [root / "experiment_log.md", root / "experiment_log_archive.md"]:
        if not log_path.exists():
            continue
        for entry in log_path.read_text(encoding="utf-8").split("\n---\n"):
            m = re.search(r"```yaml\s*\n(.*?)```", entry, re.DOTALL)
            if m:
                try:
                    data = yaml.safe_load(m.group(1))
                    if isinstance(data, dict) and data.get("iter") == iter_num:
                        record = entry.strip()
                        break
                except Exception:
                    pass
        if record:
            break

    if not record:
        iter_dir = root / "archive" / f"iter_{iter_num:03d}"
        parts = []
        for fname in ("task.md", "result.yaml"):
            p = iter_dir / fname
            if p.exists():
                parts.append(f"## {fname}\n{p.read_text(encoding='utf-8')}")
        record = (
            "\n\n".join(parts) if parts else f"No record found for iteration {iter_num}."
        )

    # List ALL files recursively under archive/iter_NNN/ so the planner knows
    # which files can be accessed via read_result_file.
    iter_dir_path = root / "archive" / f"iter_{iter_num:03d}"
    if iter_dir_path.is_dir():
        skip = {"task.md", "result.yaml"}
        all_files = sorted(
            p for p in iter_dir_path.rglob("*")
            if p.is_file() and p.name not in skip
        )
        if all_files:
            lines = [f"\n\n## Files in archive/iter_{iter_num:03d}/"]
            for f in all_files:
                rel = f.relative_to(iter_dir_path)
                lines.append(f"  {rel.as_posix()}  ({f.stat().st_size:,} bytes)")
            record += "\n".join(lines)

    return record


def read_result_file(root: Path, iter_num: int, filename: str) -> str:
    """Read a file from archive/iter_NNN/. filename may be a sub-path."""
    iter_dir = root / "archive" / f"iter_{iter_num:03d}"
    try:
        target = (iter_dir / filename).resolve()
        base = iter_dir.resolve()
    except Exception:
        return "Error: invalid path."
    sep = "\\" if "\\" in str(base) else "/"
    if not str(target).startswith(str(base) + sep):
        return "Error: path traversal outside iteration directory is not allowed."
    if not target.exists():
        return f"File not found: archive/iter_{iter_num:03d}/{filename}"
    if not target.is_file():
        return "Error: not a regular file."
    raw = target.read_bytes()
    if b"\x00" in raw[:512]:
        return f"'{filename}' appears to be binary and cannot be read as text."
    text = raw.decode("utf-8", errors="replace")
    if len(raw) > _MAX_RESULT_FILE_BYTES:
        return (
            text[:_MAX_RESULT_FILE_BYTES]
            + f"\n\n[truncated – file is {len(raw):,} bytes, "
            f"showing first {_MAX_RESULT_FILE_BYTES:,}]"
        )
    return text


def read_campaign(root: Path, campaign_name: str) -> str:
    """Return all log entries for a named campaign."""
    found: list[str] = []
    for log_path in [root / "experiment_log_archive.md", root / "experiment_log.md"]:
        if not log_path.exists():
            continue
        for entry in log_path.read_text(encoding="utf-8").split("\n---\n"):
            m = re.search(r"```yaml\s*\n(.*?)```", entry, re.DOTALL)
            if m:
                try:
                    data = yaml.safe_load(m.group(1))
                    if isinstance(data, dict) and (
                        data.get("campaign") or ""
                    ).strip() == campaign_name:
                        found.append(entry.strip())
                except Exception:
                    pass
    if not found:
        return f'No iterations found for campaign "{campaign_name}".'
    return "\n\n---\n\n".join(found)
