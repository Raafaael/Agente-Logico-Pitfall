"""Logical agent: percept -> KB update -> decision -> action queue."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .planner import astar, path_to_actions, plan_actions
from .prolog_bridge import KnowledgeBase, make_kb
from .types import (
    Action,
    CRITICAL_ENERGY_RETURN,
    DAMAGE_BIG,
    Direction,
    GRID_SIZE,
    LOW_ENERGY_RETURN,
    Percept,
    Position,
    START_POS,
    in_bounds,
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
        if hasattr(self.kb, "set_agent_dir"):
            self.kb.set_agent_dir(initial_direction)

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
        prev_dir = self.state.direction
        prev_energy = self.state.energy
        expected_walk: Position | None = None
        if self.state.last_action == Action.WALK:
            dr, dc = prev_dir.delta
            candidate = (prev_pos[0] + dr, prev_pos[1] + dc)
            if in_bounds(candidate, self.size):
                expected_walk = candidate
        damage_taken = self.state.last_action == Action.WALK and energy < prev_energy
        damage_amount = prev_energy - energy if damage_taken else 0
        teleported = (
            self.state.last_action == Action.WALK
            and expected_walk is not None
            and pos != expected_walk
        )

        self.state.pos = pos
        self.state.direction = direction
        self.state.energy = energy
        self.state.score = score
        self.state.last_percept = percept

        self.kb.set_agent_pos(pos)
        if hasattr(self.kb, "set_agent_dir"):
            self.kb.set_agent_dir(direction)
        if hasattr(self.kb, "set_energy"):
            self.kb.set_energy(energy)
        active = percept.as_list()
        self.kb.update_perception(pos, active)

        if teleported and hasattr(self.kb, "note_teleporter_here"):
            # We tried to step into expected_walk but woke up elsewhere. The
            # only rule that changes position like that is the bat/teleporter.
            self.kb.note_teleporter_here(expected_walk)

        if damage_taken and hasattr(self.kb, "note_enemy_here"):
            # We walked into ``pos`` and our energy dropped -- the cell hosts
            # an enemy. If this happened after a teleport, ``pos`` is the
            # destination cell that hurt us.
            self.kb.note_enemy_here(pos, damage_amount)

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

        kind, target = self.kb.decide()
        self.state.last_decision = (kind, target)

        if self._should_force_energy_retreat(kind, target):
            if self.state.pos == self.exit_pos:
                self.state.last_decision = ("sair", None)
                return Action.EXIT
            action = self._move_toward(self.exit_pos)
            if action is not None:
                self.state.last_decision = ("mover", self.exit_pos)
                return action

        if kind == "pegar":
            return Action.GRAB
        if kind == "sair":
            if self.state.pos == self.exit_pos:
                return Action.EXIT
            fallback = self._last_resort_risk_action() or self._survival_action()
            if fallback is not None:
                return fallback
            return Action.TURN_RIGHT
        if kind == "mover" and target is not None:
            action = self._move_toward(target)
            if action is not None:
                return action
            if self.state.pos != self.exit_pos:
                self.state.last_decision = ("mover", self.exit_pos)
                action = self._move_toward(self.exit_pos)
                if action is not None:
                    return action
                fallback = self._last_resort_risk_action() or self._survival_action()
                if fallback is not None:
                    return fallback
            if self.state.pos == self.exit_pos:
                return Action.EXIT
            return Action.TURN_RIGHT

        if self.state.pos == self.exit_pos:
            return Action.EXIT
        return Action.TURN_RIGHT

    def _should_force_energy_retreat(
        self,
        kind: str,
        target: Optional[Position],
    ) -> bool:
        """Keep low-energy caution from blocking proven-safe progress."""
        if kind != "mover" or target is None or target == self.exit_pos:
            return False
        if self.kb.likely_safe(target):
            return False
        if self.state.energy <= CRITICAL_ENERGY_RETURN:
            return True
        return (
            self.state.gold_carried > 0
            and self.state.energy <= LOW_ENERGY_RETURN
        )

    def _move_toward(self, target: Position) -> Optional[Action]:
        retreat = target == self.exit_pos
        actions = self._plan_path(target, allow_hostile_retrace=False)
        if not actions and (retreat or self._can_use_hostile_retrace(target)):
            actions = self._plan_path(target, allow_hostile_retrace=True)
        if not actions:
            if target == self.state.pos:
                if self.state.pos == self.exit_pos:
                    return Action.EXIT
                return None
            fallback = self._fallback_action(target)
            if fallback is not None:
                return fallback
            return None
        self.state.pending.extend(actions)
        return self.state.pending.popleft()

    def _plan_path(self, goal: Position, allow_hostile_retrace: bool = False) -> list[Action]:
        def safe(p: Position) -> bool:
            return self.kb.likely_safe(p)

        actions = plan_actions(
            self.state.pos,
            goal,
            self.state.direction,
            safe,
            size=self.size,
        )
        if (
            actions is None
            and allow_hostile_retrace
            and hasattr(self.kb, "walkable_for_path")
        ):
            # No strictly-safe corridor home: retrace through visited cells
            # even if they now host known enemies. Reserved for retreats so
            # we never trade damage for mere exploration.
            def retrace(p: Position) -> bool:
                return self.kb.walkable_for_path(p)

            actions = plan_actions(
                self.state.pos,
                goal,
                self.state.direction,
                retrace,
                size=self.size,
                entry_cost=self._entry_cost_for_retrace(),
            )
        if actions is None:
            return []
        return actions

    def _fallback_action(self, target: Position) -> Optional[Action]:
        from .types import orthogonal_neighbors

        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if nb == target and self.kb.likely_safe(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None

    def _survival_action(self) -> Optional[Action]:
        """Move to an unvisited safe neighbor when no full route exists."""
        from .types import orthogonal_neighbors

        candidates: list[tuple[int, int, Position, list[Action]]] = []
        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if not self.kb.likely_safe(nb) or self.kb.is_visited(nb):
                continue
            actions = path_to_actions([self.state.pos, nb], self.state.direction)
            if actions:
                candidates.append((0, len(actions), nb, actions))

        if not candidates:
            return None
        candidates.sort()
        actions = candidates[0][3]
        self.state.pending.extend(actions[1:])
        return actions[0]

    def _last_resort_risk_action(self) -> Optional[Action]:
        """Try a reachable enemy frontier when safe planning is exhausted."""
        if not hasattr(self.kb, "walkable_for_path"):
            return None

        snapshot = self.kb.snapshot()
        risk_enemy = set(map(tuple, snapshot.get("risk_enemy", [])))
        risk_pit = set(map(tuple, snapshot.get("risk_pit", [])))
        risk_tele = set(map(tuple, snapshot.get("risk_teleport", [])))
        confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
        confirmed_tele = set(map(tuple, snapshot.get("confirmed_teleport", [])))
        confirmed_enemy = set(map(tuple, snapshot.get("confirmed_enemy", [])))
        enemy_damage = {
            tuple(pos): int(damage)
            for pos, damage in snapshot.get("enemy_damage", [])
        }

        def retrace(p: Position) -> bool:
            return self.kb.walkable_for_path(p)

        base_entry_cost = self._entry_cost_for_retrace()
        candidates: list[tuple[int, Position, list[Action]]] = []
        for raw in snapshot.get("risky_frontier", []):
            target = tuple(raw)
            if target in risk_pit or target in risk_tele:
                continue
            if target in confirmed_pit or target in confirmed_tele:
                continue
            if target not in risk_enemy and target not in confirmed_enemy:
                continue
            known_damage = enemy_damage.get(target)
            if known_damage is not None and self.state.energy <= known_damage:
                continue

            def entry_cost(pos: Position, *, target=target) -> Optional[int]:
                if pos == target and pos in confirmed_enemy and pos not in enemy_damage:
                    return 0
                return base_entry_cost(pos)

            actions = plan_actions(
                self.state.pos,
                target,
                self.state.direction,
                retrace,
                size=self.size,
                entry_cost=entry_cost,
            )
            if actions:
                penalty = enemy_damage.get(target, DAMAGE_BIG)
                candidates.append((len(actions) + penalty, target, actions))

        if not candidates:
            return None
        candidates.sort()
        actions = candidates[0][2]
        self.state.pending.extend(actions[1:])
        return actions[0]

    def _can_use_hostile_retrace(self, target: Position) -> bool:
        """Allow exploration through already-visited enemy cells when needed.

        A confirmed enemy hurts, but it is not a one-way trap like a pit or a
        teleporter. On harder maps this lets the agent leave an isolated pocket
        instead of burning score on impossible plans.
        """
        if self.state.energy <= LOW_ENERGY_RETURN:
            return False

        snapshot = self.kb.snapshot()
        target = tuple(target)
        confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
        confirmed_tele = set(map(tuple, snapshot.get("confirmed_teleport", [])))
        risk_pit = set(map(tuple, snapshot.get("risk_pit", [])))
        risk_tele = set(map(tuple, snapshot.get("risk_teleport", [])))

        if target in confirmed_pit or target in confirmed_tele:
            return False
        if self.state.gold_carried > 0 and (target in risk_pit or target in risk_tele):
            return False
        return True

    def _entry_cost_for_retrace(self):
        snapshot = self.kb.snapshot()
        confirmed_enemy = set(map(tuple, snapshot.get("confirmed_enemy", [])))
        enemy_damage = {
            tuple(pos): int(damage)
            for pos, damage in snapshot.get("enemy_damage", [])
        }

        def cost(pos: Position) -> Optional[int]:
            if pos not in confirmed_enemy:
                return 0
            damage = enemy_damage.get(pos, DAMAGE_BIG)
            if self.state.energy <= damage:
                return None
            return damage

        return cost
