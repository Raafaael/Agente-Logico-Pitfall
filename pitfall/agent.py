"""Logical agent: percept -> KB update -> decision -> action queue."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .planner import astar, path_to_actions
from .prolog_bridge import KnowledgeBase, make_kb
from .types import (
    Action,
    Direction,
    GOLD_TARGET,
    GRID_SIZE,
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
    returning_to_exit: bool = False  # True: comprometido com retorno ate a saida


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
        action = self._decide()
        self.state.last_action = action
        return action

    def _decide(self) -> Action:
        if self.state.pending:
            return self.state.pending.popleft()

        # Guard: se o ultimo WALK bateu em parede, girar para replanjar
        # (o planejador A* nunca deveria gerar isso, mas cobre casos extremos)
        if (self.state.last_percept is not None
                and self.state.last_percept.impact
                and self.state.last_action == Action.WALK):
            return Action.TURN_RIGHT

        # Ativar retorno quando coletou todos os ouros
        if self.state.gold_carried >= GOLD_TARGET:
            self.state.returning_to_exit = True

        # ----------------------------------------------------------------
        # Modo retorno: uma vez comprometido, segue ate a saida sem oscilar.
        # ----------------------------------------------------------------
        if self.state.returning_to_exit:
            if self.state.pos == self.exit_pos:
                if self.state.gold_carried >= GOLD_TARGET:
                    self.state.returning_to_exit = False
                    self.state.last_decision = ("sair", None)
                    return Action.EXIT
                # Ouro parcial na saida: retoma exploracao so se tiver energia
                if self.state.energy > self._MIN_ENERGY_REEXPLORE:
                    self.state.returning_to_exit = False
                    # cai no fluxo normal abaixo
                else:
                    self.state.last_decision = ("sair_energia", None)
                    return Action.EXIT
            else:
                action = self._move_toward(self.exit_pos)
                if action is not None:
                    self.state.last_decision = ("retornar", self.exit_pos)
                    return action
                self.state.returning_to_exit = False  # sem caminho, tenta KB

        # ----------------------------------------------------------------
        # Verificacao proativa: ativa retorno antes de nao ter energia suficiente.
        # Flag permanece True ate chegar na saida (sem oscilacao).
        # ----------------------------------------------------------------
        if not self.state.returning_to_exit and not self._enough_energy_to_return():
            self.state.returning_to_exit = True
            self.state.last_decision = ("retornar_energia", self.exit_pos)
            if self.state.pos == self.exit_pos:
                return Action.EXIT
            action = self._move_toward(self.exit_pos)
            if action is not None:
                return action

        # ----------------------------------------------------------------
        # Decisao normal via KB
        # ----------------------------------------------------------------
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

    # Energia minima na saida para valer a pena retomar exploracao.
    _MIN_ENERGY_REEXPLORE: int = 20

    def _enough_energy_to_return(self) -> bool:
        """True se ha energia para pelo menos 1 passo de exploracao E o retorno completo.

        Usa o caminho real via A*. Margem de 5 passos absorve desvios de rota.
        Ao chegar na saida, retorna True (agent.pos == exit_pos e' tratado antes).
        """
        if self.state.pos == self.exit_pos:
            return True
        path = self._plan_path(self.exit_pos)
        if path:
            steps_home = len(path)
        else:
            r1, c1 = self.state.pos
            r2, c2 = self.exit_pos
            steps_home = (abs(r1 - r2) + abs(c1 - c2)) * 2 + 5
        # energy > steps_home + 5 garante 1 passo de exploracao (+1) e
        # chega na saida com energia >= 1 apos o retorno (+4 de folga)
        return self.state.energy > steps_home + 5

    def _fallback_action(self, target: Position) -> Optional[Action]:
        from .types import orthogonal_neighbors

        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if nb == target and self.kb.likely_safe(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None
