"""Iteration ID utilities and path mapping for RDF v3.

IDs use dot-separated integers: "001", "001.1", "001.1.2".
The first component is always zero-padded to 3 digits; sub-components are
stored as plain integers but formatted the same way when resolving paths.

Directory layout:
  "001"     → archive/iter_001/
  "001.1"   → archive/iter_001/iter_001/
  "001.1.2" → archive/iter_001/iter_001/iter_002/

Existing flat iterations (pre-Phase 2) have depth 0 and map to
archive/iter_NNN/ without any nesting, so backward compatibility is preserved.
"""

from __future__ import annotations

import re
from pathlib import Path

IterID = str  # e.g. "001", "001.1", "001.1.2"


# ---------------------------------------------------------------------------
# Parsing and formatting
# ---------------------------------------------------------------------------

def parse_iter_id(s: IterID) -> tuple[int, ...]:
    """Convert "001.1.2" → (1, 1, 2)."""
    return tuple(int(p) for p in s.split("."))


def format_iter_id(parts: tuple[int, ...]) -> IterID:
    """Convert (1, 1, 2) → "001.1.2"."""
    if not parts:
        raise ValueError("parts must not be empty")
    head = f"{parts[0]:03d}"
    tail = ".".join(str(p) for p in parts[1:])
    return f"{head}.{tail}" if tail else head


def iter_depth(iter_id: IterID) -> int:
    """Return nesting depth: "001" → 0, "001.1" → 1, "001.1.2" → 2."""
    return iter_id.count(".")


# ---------------------------------------------------------------------------
# Path mapping
# ---------------------------------------------------------------------------

def iter_path(root: Path, iter_id: IterID) -> Path:
    """Map an iteration ID to its directory under ``root/archive/``.

    "001"     → root/archive/iter_001/
    "001.1"   → root/archive/iter_001/iter_001/
    "001.1.2" → root/archive/iter_001/iter_001/iter_002/
    """
    parts = parse_iter_id(iter_id)
    p = root / "archive" / f"iter_{parts[0]:03d}"
    for sub in parts[1:]:
        p = p / f"iter_{sub:03d}"
    return p


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def top_level_count(root: Path) -> int:
    """Return the highest top-level iteration number present in archive/.

    Scans only direct children of ``root/archive/`` matching ``iter_NNN``.
    Returns 0 when the archive is empty or missing.
    """
    archive = root / "archive"
    if not archive.is_dir():
        return 0
    nums = []
    for d in archive.iterdir():
        m = re.fullmatch(r"iter_(\d{3})", d.name)
        if m and d.is_dir():
            nums.append(int(m.group(1)))
    return max(nums, default=0)


def child_count(root: Path, parent_id: IterID) -> int:
    """Return the number of direct sub-iteration directories under *parent_id*."""
    parent = iter_path(root, parent_id)
    if not parent.is_dir():
        return 0
    count = 0
    for d in parent.iterdir():
        if re.fullmatch(r"iter_(\d+)", d.name) and d.is_dir():
            count += 1
    return count


def next_top_level_id(root: Path) -> IterID:
    """Return the next unused top-level ID (e.g. "096" when 095 exists)."""
    return format_iter_id((top_level_count(root) + 1,))


def next_child_id(root: Path, parent_id: IterID) -> IterID:
    """Return the next unused sub-iteration ID under *parent_id*.

    E.g. if parent is "001" and iter_001/iter_001/ and iter_001/iter_002/
    already exist, returns "001.3".
    """
    parent = iter_path(root, parent_id)
    if not parent.is_dir():
        next_sub = 1
    else:
        existing = []
        for d in parent.iterdir():
            m = re.fullmatch(r"iter_(\d+)", d.name)
            if m and d.is_dir():
                existing.append(int(m.group(1)))
        next_sub = max(existing, default=0) + 1
    parent_parts = parse_iter_id(parent_id)
    return format_iter_id(parent_parts + (next_sub,))


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def sort_iter_ids(ids: list[IterID]) -> list[IterID]:
    """Sort iteration IDs numerically by component (not lexicographically).

    E.g. ["001.2", "001.10", "001.1"] → ["001.1", "001.2", "001.10"]
    """
    return sorted(ids, key=parse_iter_id)


# ---------------------------------------------------------------------------
# Backward-compat helper
# ---------------------------------------------------------------------------

def id_from_top_level_num(n: int) -> IterID:
    """Convert a plain integer iteration number to a top-level IterID."""
    return format_iter_id((n,))
