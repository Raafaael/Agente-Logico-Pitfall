"""Logical agent: percept -> KB update -> decision -> action queue."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .planner import astar, path_to_actions
from .prolog_bridge import KnowledgeBase, make_kb
from .types import (
    Action,
    CRITICAL_ENERGY_RETURN,
    Direction,
    GOLD_TARGET,
    GRID_SIZE,
    LOW_ENERGY_RETURN,
    Percept,
    Position,
    START_POS,
)


@dataclass
class AgentState:
    pos: Position = START_POS
    direction: Direction = Direction.EAST
    energy: int = 100
    score: int = 0
    gold_carried: int = 0
    last_percept: Optional[Percept] = None
    last_action: Optional[Action] = None
    last_decision: Optional[tuple[str, Optional[Position]]] = None
    last_message: str = ""
    pending: deque[Action] = field(default_factory=deque)


class Agent:
    """Picks the next action using only its own knowledge base.

    Importantly, the agent never reads the environment's grid: it only sees
    percepts and the position/direction values it tracks itself. The latter
    are first-class outputs of the agent's actions, so they do not leak the
    map.
    """

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        size: int = GRID_SIZE,
        kb_backend: str = "auto",
        start: Position = START_POS,
        initial_direction: Direction = Direction.EAST,
    ) -> None:
        self.kb = kb or make_kb(kb_backend)
        self.size = size
        self.exit_pos = start
        self.state = AgentState(pos=start, direction=initial_direction)
        if hasattr(self.kb, "set_exit"):
            self.kb.set_exit(start)
        self.kb.reset()
        if hasattr(self.kb, "set_exit"):
            self.kb.set_exit(start)
        self.kb.set_agent_pos(start)

    @property
    def backend(self) -> str:
        return getattr(self.kb, "backend", "unknown")

    def planned_path(self) -> list[Position]:
        """Return the cells of the agent's currently committed plan, if any.

        The path always starts at the agent's current position. Useful to
        render the A* trace on top of the GUI board.
        """
        target = self._current_target()
        if target is None or target == self.state.pos:
            return []

        def safe(p: Position) -> bool:
            return self.kb.likely_safe(p)

        path = astar(self.state.pos, target, safe, size=self.size)
        if path is None and hasattr(self.kb, "walkable_for_path"):
            def retrace(p: Position) -> bool:
                return self.kb.walkable_for_path(p)

            path = astar(self.state.pos, target, retrace, size=self.size)
        return list(path) if path else []

    def _current_target(self) -> Optional[Position]:
        decision = self.state.last_decision
        if decision is None:
            return None
        kind, target = decision
        if kind == "mover":
            return target
        return None

    def observe(self, percept: Percept, pos: Position, direction: Direction,
                energy: int, score: int) -> None:
        prev_pos = self.state.pos
        prev_energy = self.state.energy
        moved = prev_pos != pos
        damage_taken = self.state.last_action == Action.WALK and energy < prev_energy

        self.state.pos = pos
        self.state.direction = direction
        self.state.energy = energy
        self.state.score = score
        self.state.last_percept = percept

        self.kb.set_agent_pos(pos)
        if hasattr(self.kb, "set_energy"):
            self.kb.set_energy(energy)
        active = percept.as_list()
        self.kb.update_perception(pos, active)

        if damage_taken and moved and hasattr(self.kb, "note_enemy_here"):
            # We walked into ``pos`` and our energy dropped -- the cell hosts
            # an enemy. Pits would have killed us and teleporters would have
            # relocated us, so the only remaining explanation is an enemy.
            self.kb.note_enemy_here(pos)

        # Always replan from scratch each turn: a stale path queue could
        # send the agent into a cell we just learned to be risky.
        self.state.pending.clear()

    def notify_picked(self, kind: str) -> None:
        if kind == "gold":
            self.state.gold_carried += 1
            self.kb.mark_gold_taken(self.state.pos)
        elif kind == "powerup" and hasattr(self.kb, "note_powerup_taken"):
            self.kb.note_powerup_taken(self.state.pos)

    def decide_action(self) -> Action:
        action = self._choose_action()
        self.state.last_action = action
        return action

    def _choose_action(self) -> Action:
        if self.state.pending:
            return self.state.pending.popleft()

        should_return = (
            self.state.gold_carried >= GOLD_TARGET
            or (self.state.gold_carried > 0 and self.state.energy <= LOW_ENERGY_RETURN)
            or self.state.energy <= CRITICAL_ENERGY_RETURN
        )
        if should_return:
            if self.state.pos == self.exit_pos:
                self.state.last_decision = ("sair", None)
                return Action.EXIT
            action = self._move_toward(self.exit_pos)
            if action is not None:
                self.state.last_decision = ("mover", self.exit_pos)
                return action

        kind, target = self.kb.decide()
        self.state.last_decision = (kind, target)

        if kind == "pegar":
            return Action.GRAB
        if kind == "sair":
            return Action.EXIT
        if kind == "mover" and target is not None:
            action = self._move_toward(target)
            return action if action is not None else Action.EXIT

        return Action.EXIT

    def _move_toward(self, target: Position) -> Optional[Action]:
        retreat = target == self.exit_pos
        actions = self._plan_path(target, allow_hostile_retrace=retreat)
        if not actions:
            if target == self.state.pos:
                return Action.EXIT
            fallback = self._fallback_action(target)
            if fallback is not None:
                return fallback
            return None
        self.state.pending.extend(actions)
        return self.state.pending.popleft()

    def _plan_path(self, goal: Position, allow_hostile_retrace: bool = False) -> list[Action]:
        def safe(p: Position) -> bool:
            return self.kb.likely_safe(p)

        path = astar(self.state.pos, goal, safe, size=self.size)
        if path is None and allow_hostile_retrace and hasattr(self.kb, "walkable_for_path"):
            # No strictly-safe corridor home: retrace through visited cells
            # even if they now host known enemies. Reserved for retreats so
            # we never trade damage for mere exploration.
            def retrace(p: Position) -> bool:
                return self.kb.walkable_for_path(p)

            path = astar(self.state.pos, goal, retrace, size=self.size)
        if path is None:
            return []
        return path_to_actions(path, self.state.direction)

    def _fallback_action(self, target: Position) -> Optional[Action]:
        from .types import orthogonal_neighbors

        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if nb == target and self.kb.likely_safe(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None
