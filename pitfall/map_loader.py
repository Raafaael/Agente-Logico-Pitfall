"""Random generation and file-based loading of Pitfall maps."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Iterable

from .types import (
    CellType,
    Direction,
    ELEMENT_COUNTS,
    GRID_SIZE,
    Position,
    START_POS,
    orthogonal_neighbors,
)


Grid = list[list[CellType]]


def empty_grid(size: int = GRID_SIZE) -> Grid:
    return [[CellType.EMPTY for _ in range(size)] for _ in range(size)]


def get_cell(grid: Grid, pos: Position) -> CellType:
    r, c = pos
    return grid[r - 1][c - 1]


def set_cell(grid: Grid, pos: Position, ct: CellType) -> None:
    r, c = pos
    grid[r - 1][c - 1] = ct


def all_positions(size: int = GRID_SIZE) -> list[Position]:
    return [(r, c) for r in range(1, size + 1) for c in range(1, size + 1)]


def generate_random_map(
    seed: int | None = None,
    size: int = GRID_SIZE,
    counts: dict[str, int] | None = None,
    ensure_safe_neighbor: bool = True,
) -> Grid:
    """Generate a random valid map.

    The starting cell [1,1] is always EMPTY. By default at least one of [1,1]'s
    orthogonal neighbors is left as EMPTY so that the agent has a viable first
    step (this is not strictly required by the spec but avoids unwinnable runs).
    """
    rng = random.Random(seed)
    counts = counts or ELEMENT_COUNTS
    grid = empty_grid(size)

    free: list[Position] = [p for p in all_positions(size) if p != START_POS]
    rng.shuffle(free)

    if ensure_safe_neighbor:
        reserved = rng.choice(orthogonal_neighbors(START_POS, size))
        free = [p for p in free if p != reserved]

    placement_order = [
        ("pit", CellType.PIT),
        ("teleporter", CellType.TELEPORTER),
        ("enemy_big", CellType.ENEMY_BIG),
        ("enemy_small", CellType.ENEMY_SMALL),
        ("gold", CellType.GOLD),
        ("powerup", CellType.POWERUP),
    ]

    total_needed = sum(counts.get(k, 0) for k, _ in placement_order)
    if total_needed > len(free):
        raise ValueError(
            f"Not enough free cells ({len(free)}) for required elements ({total_needed})"
        )

    for key, ct in placement_order:
        n = counts.get(key, 0)
        for _ in range(n):
            pos = free.pop()
            set_cell(grid, pos, ct)

    validate_map(grid, START_POS)
    return grid


def load_map_from_file(path: str | Path) -> tuple[Grid, dict]:
    """Load a map from a JSON or plain-text file.

    Returns the grid and a dict of metadata (start, initial_direction).
    Two formats are supported:

    1. JSON with explicit grid (list of strings):
        {
          "size": 12,
          "start": [1, 1],
          "initial_direction": "east",
          "grid": [".P..G......T", "............", ...]
        }

    2. JSON with cell list:
        {
          "size": 12,
          "start": [1, 1],
          "initial_direction": "east",
          "cells": [{"pos": [3, 4], "type": "pit"}, ...]
        }

    3. Plain text: 12 lines of 12 symbols (`.`, `P`, `d`, `D`, `T`, `O`, `U`).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Map file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    suffix = path.suffix.lower()

    if suffix == ".pl" or text.lstrip().startswith(":-") or "tile(" in text.split("\n", 1)[0]:
        return _load_prolog_map(text)

    if suffix == ".json" or text.startswith("{"):
        data = json.loads(text)
        size = int(data.get("size", GRID_SIZE))
        start = tuple(data.get("start", list(START_POS)))
        direction = Direction.parse(data.get("initial_direction", Direction.EAST.value))
        if "grid" in data:
            grid = _grid_from_strings(data["grid"], size)
        elif "cells" in data:
            grid = empty_grid(size)
            for entry in data["cells"]:
                pos = tuple(entry["pos"])
                ct = CellType(entry["type"])
                set_cell(grid, pos, ct)
        else:
            raise ValueError("JSON map must contain 'grid' or 'cells'")
        validate_map(grid, start)
        return grid, {"start": start, "initial_direction": direction, "size": size}

    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    grid = _grid_from_strings(lines, GRID_SIZE)
    validate_map(grid, START_POS)
    return grid, {"start": START_POS, "initial_direction": Direction.EAST, "size": GRID_SIZE}


def _load_prolog_map(text: str) -> tuple[Grid, dict]:
    """Parse a `tile(X, Y, 'Z').`-style map (the legacy reference format).

    The provided `.pl` maps use `tile(X, Y, Symbol)`, where X is the column
    from left to right and Y is the line from bottom to top. The project uses
    `(row, col)` with row 1 at the top, so `tile(1, 12, ...)` becomes `(1, 1)`.
    """
    size_match = re.search(r"map_size\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", text)
    size = int(size_match.group(1)) if size_match else GRID_SIZE

    grid = empty_grid(size)
    pattern = re.compile(r"tile\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*'([^']*)'\s*\)")
    for match in pattern.finditer(text):
        x, y, sym = int(match.group(1)), int(match.group(2)), match.group(3)
        row = size + 1 - y
        col = x
        cell = CellType.from_symbol(sym if sym else ".")
        set_cell(grid, (row, col), cell)

    legacy_start: Position = (1, 1)
    validate_map(grid, legacy_start, allow_start_items=True)
    return grid, {
        "start": legacy_start,
        "initial_direction": Direction.NORTH,
        "size": size,
    }


def _grid_from_strings(rows: Iterable[str], size: int) -> Grid:
    rows = list(rows)
    if len(rows) != size:
        raise ValueError(f"Map must have {size} rows, got {len(rows)}")
    grid = empty_grid(size)
    for r, line in enumerate(rows, start=1):
        if len(line) != size:
            raise ValueError(
                f"Row {r} must have exactly {size} symbols, got {len(line)}"
            )
        for c, sym in enumerate(line, start=1):
            try:
                grid[r - 1][c - 1] = CellType.from_symbol(sym)
            except ValueError as exc:
                raise ValueError(f"Invalid symbol at row {r}, col {c}: {sym!r}") from exc
    return grid


def validate_map(
    grid: Grid,
    start: Position = START_POS,
    *,
    allow_start_items: bool = False,
) -> None:
    """Validate shape and start-cell invariants shared by all map formats."""
    if not grid:
        raise ValueError("Map cannot be empty")
    size = len(grid)
    for i, row in enumerate(grid, start=1):
        if len(row) != size:
            raise ValueError(f"Map must be square; row {i} has {len(row)} cells")
    if not (1 <= start[0] <= size and 1 <= start[1] <= size):
        raise ValueError(f"Start position out of bounds: {start}")
    allowed_start_cells = {CellType.EMPTY}
    if allow_start_items:
        allowed_start_cells.update({CellType.GOLD, CellType.POWERUP})
    if get_cell(grid, start) not in allowed_start_cells:
        raise ValueError("Starting cell must be empty")


def save_map_to_file(grid: Grid, path: str | Path, *, start: Position = START_POS,
                     initial_direction: Direction = Direction.EAST) -> None:
    """Persist a grid as a human-readable JSON map."""
    path = Path(path)
    rows = ["".join(cell.symbol for cell in row) for row in grid]
    data = {
        "size": len(grid),
        "start": list(start),
        "initial_direction": initial_direction.value,
        "grid": rows,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def count_elements(grid: Grid) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in grid:
        for cell in row:
            counts[cell.value] = counts.get(cell.value, 0) + 1
    return counts
