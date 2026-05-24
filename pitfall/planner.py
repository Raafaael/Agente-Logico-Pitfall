"""A* path planning over the agent's known-safe cells."""
from __future__ import annotations

import heapq
from typing import Callable, Iterable, Optional

from .TreeNode import TreeNode
from .types import Action, Direction, GRID_SIZE, Position, orthogonal_neighbors


def manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(
    start: Position,
    goal: Position,
    is_walkable: Callable[[Position], bool],
    size: int = GRID_SIZE,
) -> Optional[list[Position]]:
    """Standard A* over a 12x12 grid with Manhattan heuristic.

    `is_walkable(pos)` is queried for any candidate cell except `start`. The
    `goal` itself is *not* required to be walkable — this lets the agent plan a
    path *toward* a frontier cell that has not yet been confirmed safe.
    """
    if start == goal:
        return [start]

    open_heap: list[tuple[int, int, TreeNode]] = []
    counter = 0
    start_node = TreeNode(start, g=0, h=manhattan(start, goal))
    heapq.heappush(open_heap, (start_node.f, counter, start_node))
    g_score: dict[Position, int] = {start: 0}

    while open_heap:
        _, _, node = heapq.heappop(open_heap)
        current = node.position
        if current == goal:
            return node.path()

        for nb in orthogonal_neighbors(current, size):
            if nb != goal and not is_walkable(nb):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nb, 10**9):
                g_score[nb] = tentative
                counter += 1
                child = TreeNode(
                    nb,
                    parent=node,
                    g=tentative,
                    h=manhattan(nb, goal),
                )
                heapq.heappush(
                    open_heap, (child.f, counter, child)
                )

    return None


def path_to_actions(
    path: Iterable[Position],
    initial_dir: Direction,
) -> list[Action]:
    """Convert a list of positions into a sequence of low-level actions.

    Generates the minimum number of left/right turns needed to align with each
    next step, followed by a WALK. The initial position must be the agent's
    current position.
    """
    path = list(path)
    if len(path) < 2:
        return []

    actions: list[Action] = []
    cur_dir = initial_dir
    for a, b in zip(path, path[1:]):
        delta = (b[0] - a[0], b[1] - a[1])
        target_dir = Direction.from_delta(delta)
        actions.extend(_align_actions(cur_dir, target_dir))
        actions.append(Action.WALK)
        cur_dir = target_dir
    return actions


def _align_actions(cur: Direction, target: Direction) -> list[Action]:
    if cur == target:
        return []
    order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
    delta = (order.index(target) - order.index(cur)) % 4
    if delta == 1:
        return [Action.TURN_RIGHT]
    if delta == 3:
        return [Action.TURN_LEFT]
    # 180-degree turn: prefer two right turns.
    return [Action.TURN_RIGHT, Action.TURN_RIGHT]
