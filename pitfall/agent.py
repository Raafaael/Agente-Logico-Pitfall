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

    def observe(self, percept: Percept, pos: Position, direction: Direction,
                energy: int, score: int) -> None:
        self.state.pos = pos
        self.state.direction = direction
        self.state.energy = energy
        self.state.score = score
        self.state.last_percept = percept

        self.kb.set_agent_pos(pos)
        self.kb.set_agent_energy(energy)
        active = percept.as_list()
        self.kb.update_perception(pos, active)

        # Always replan from scratch each turn: a stale path queue could
        # send the agent into a cell we just learned to be risky.
        self.state.pending.clear()

    def notify_picked(self, kind: str) -> None:
        if kind == "gold":
            self.state.gold_carried += 1
            self.kb.mark_gold_taken(self.state.pos)
        elif kind == "powerup":
            self.kb.mark_powerup_taken(self.state.pos)

    def decide_action(self) -> Action:
        if self.state.pending:
            return self.state.pending.popleft()

        # Retornar ao inicio quando: todos os ouros coletados, OU energia critica.
        # Energia baixa (mas nao critica) e' gerenciada pela KB via energia_baixa:
        # a KB busca powerups proximos antes de decidir retornar.
        should_return = (
            self.state.gold_carried >= GOLD_TARGET
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
        actions = self._plan_path(target)
        if not actions:
            if target == self.state.pos:
                return Action.EXIT
            fallback = self._fallback_action(target)
            if fallback is not None:
                return fallback
            return None
        self.state.pending.extend(actions)
        return self.state.pending.popleft()

    def _plan_path(self, goal: Position) -> list[Action]:
        def walkable(p: Position) -> bool:
            return self.kb.likely_safe(p)

        path = astar(self.state.pos, goal, walkable, size=self.size)
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
