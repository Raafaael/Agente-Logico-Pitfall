"""A* path planning over the agent's known-safe cells."""
from __future__ import annotations

import heapq
from typing import Callable, Iterable, Optional

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

    open_heap: list[tuple[int, int, Position]] = []
    counter = 0
    heapq.heappush(open_heap, (manhattan(start, goal), counter, start))
    came_from: dict[Position, Position] = {}
    g_score: dict[Position, int] = {start: 0}

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            return _reconstruct(came_from, current)

        for nb in orthogonal_neighbors(current, size):
            if nb != goal and not is_walkable(nb):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nb, 10**9):
                came_from[nb] = current
                g_score[nb] = tentative
                counter += 1
                heapq.heappush(
                    open_heap, (tentative + manhattan(nb, goal), counter, nb)
                )

    return None


def _reconstruct(came_from: dict[Position, Position], end: Position) -> list[Position]:
    path = [end]
    while end in came_from:
        end = came_from[end]
        path.append(end)
    path.reverse()
    return path


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


def plan_actions(
    start: Position,
    goal: Position,
    initial_dir: Direction,
    is_walkable: Callable[[Position], bool],
    size: int = GRID_SIZE,
    entry_cost: Callable[[Position], Optional[int]] | None = None,
) -> Optional[list[Action]]:
    """Plan the cheapest low-level action sequence.

    Unlike :func:`astar`, this searches over ``(position, direction)`` states,
    so turns are counted in the path cost. ``entry_cost`` can add an extra
    penalty, or return ``None`` to forbid entering a cell.
    """
    if start == goal:
        return []

    start_state = (start, initial_dir)
    open_heap: list[tuple[int, int, int, tuple[Position, Direction]]] = []
    counter = 0
    heapq.heappush(open_heap, (manhattan(start, goal), 0, counter, start_state))
    came_from: dict[
        tuple[Position, Direction],
        tuple[tuple[Position, Direction], Action],
    ] = {}
    best: dict[tuple[Position, Direction], int] = {start_state: 0}

    while open_heap:
        _, cost, _, state = heapq.heappop(open_heap)
        pos, direction = state
        if cost != best.get(state):
            continue
        if pos == goal:
            return _reconstruct_actions(came_from, state)

        for action, next_state, step_cost in _action_successors(
            pos, direction, goal, is_walkable, size, entry_cost
        ):
            new_cost = cost + step_cost
            if new_cost >= best.get(next_state, 10**9):
                continue
            best[next_state] = new_cost
            came_from[next_state] = (state, action)
            counter += 1
            heuristic = manhattan(next_state[0], goal)
            heapq.heappush(
                open_heap,
                (new_cost + heuristic, new_cost, counter, next_state),
            )

    return None


def plan_action_cost(
    start: Position,
    goal: Position,
    initial_dir: Direction,
    is_walkable: Callable[[Position], bool],
    size: int = GRID_SIZE,
) -> float:
    actions = plan_actions(start, goal, initial_dir, is_walkable, size=size)
    if actions is None:
        return float("inf")
    return len(actions)


def _action_successors(
    pos: Position,
    direction: Direction,
    goal: Position,
    is_walkable: Callable[[Position], bool],
    size: int,
    entry_cost: Callable[[Position], Optional[int]] | None,
):
    left = direction.turn_left()
    yield Action.TURN_LEFT, (pos, left), 1
    right = direction.turn_right()
    yield Action.TURN_RIGHT, (pos, right), 1

    dr, dc = direction.delta
    nb = (pos[0] + dr, pos[1] + dc)
    if not (1 <= nb[0] <= size and 1 <= nb[1] <= size):
        return
    if nb != goal and not is_walkable(nb):
        return
    extra = entry_cost(nb) if entry_cost is not None else 0
    if extra is None:
        return
    yield Action.WALK, (nb, direction), 1 + extra


def _reconstruct_actions(
    came_from: dict[tuple[Position, Direction], tuple[tuple[Position, Direction], Action]],
    end: tuple[Position, Direction],
) -> list[Action]:
    actions: list[Action] = []
    while end in came_from:
        end, action = came_from[end]
        actions.append(action)
    actions.reverse()
    return actions
