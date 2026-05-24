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
    INITIAL_ENERGY,
    Percept,
    Position,
    POWERUP_ENERGY_GAIN,
    START_POS,
    in_bounds,
    orthogonal_neighbors,
)


@dataclass
class AgentState:
    pos: Position = START_POS
    direction: Direction = Direction.EAST
    energy: int = INITIAL_ENERGY
    score: int = 0
    gold_carried: int = 0
    last_percept: Optional[Percept] = None
    last_action: Optional[Action] = None
    last_decision: Optional[tuple[str, Optional[Position]]] = None
    last_message: str = ""
    pending: deque[Action] = field(default_factory=deque)
    returning_to_exit: bool = False  # True: comprometido com retorno ate a saida
    damaging_cells: dict[Position, int] = field(default_factory=dict)
    blocked_cells: set[Position] = field(default_factory=set)


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
        previous_energy = self.state.energy
        self.state.pos = pos
        self.state.direction = direction
        self.state.energy = energy
        self.state.score = score
        self.state.last_percept = percept

        self.kb.set_agent_pos(pos)
        self.kb.set_agent_energy(energy)
        active = percept.as_list()
        self.kb.update_perception(pos, active)
        if (
            self.state.last_action == Action.WALK
            and energy < previous_energy
            and not percept.scream
        ):
            self.state.damaging_cells[pos] = max(
                self.state.damaging_cells.get(pos, 0),
                previous_energy - energy,
            )

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

        # Pegar ouro/powerup imediatamente se o agente estiver na célula.
        # Tem prioridade sobre qualquer modo (inclusive returning_to_exit) para
        # garantir que o agente nunca passe por ouro/powerup sem pegar.
        if (self.state.last_percept is not None
                and (self.state.last_percept.glow or self.state.last_percept.powerup)):
            return Action.GRAB

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
        # Durante o retorno verifica desvios viaveis para aproveitar energia
        # restante (celulas seguras nao visitadas no caminho de volta).
        # ----------------------------------------------------------------
        if self.state.returning_to_exit:
            if self.state.pos == self.exit_pos:
                if self.state.gold_carried >= GOLD_TARGET:
                    self.state.returning_to_exit = False
                    self.state.last_decision = ("sair", None)
                    return Action.EXIT
                # Ouro parcial: tentar desvio acessivel antes de sair
                detour = self._best_return_detour()
                if detour is not None:
                    # Permanece em modo retorno — desvio no caminho de volta
                    action = self._move_toward(detour)
                    if action is not None:
                        self.state.last_decision = ("desvio_retorno", detour)
                        return action
                # Sem desvio viavel na saida: sair imediatamente para preservar
                # a pontuacao atual. _enough_energy_to_return() e' trivialmente
                # True aqui (pos==exit_pos), entao nunca deve ser consultado.
                self.state.last_decision = ("sair_energia", None)
                return Action.EXIT
            else:
                # Fora da saida: verificar desvio antes de ir diretamente
                if self.state.gold_carried < GOLD_TARGET:
                    detour = self._best_return_detour()
                    if detour is not None:
                        action = self._move_toward(detour)
                        if action is not None:
                            self.state.last_decision = ("desvio_retorno", detour)
                            return action
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
            target = self._choose_target(target)
            action = self._move_toward(target)
            if action is not None:
                return action
            alt = self._best_exploration_target(
                self.kb.snapshot(),
                include_risky=True,
                banned=set(self.state.blocked_cells),
            )
            if alt is not None and alt != target:
                action = self._move_toward(alt)
                if action is not None:
                    self.state.last_decision = ("alternativa", alt)
                    return action
            if self.state.pos != self.exit_pos:
                action = self._move_toward(self.exit_pos)
                if action is not None:
                    self.state.last_decision = ("retornar_sem_rota", self.exit_pos)
                    return action
            return Action.TURN_RIGHT

        return Action.EXIT

    def _move_toward(self, target: Position) -> Optional[Action]:
        actions = self._plan_path(target)
        if actions and actions[0] == Action.WALK and self.state.last_percept:
            forward = self._forward_pos()
            if self.state.last_percept.breeze and self.kb.is_risky(forward):
                self.state.blocked_cells.add(forward)
                right = self._neighbor_in_direction(self.state.direction.turn_right())
                if in_bounds(right, self.size) and right not in self.state.blocked_cells:
                    return Action.TURN_RIGHT
                alt = self._best_exploration_target(
                    self.kb.snapshot(),
                    include_risky=True,
                    banned=set(self.state.blocked_cells),
                )
                if alt is not None and alt != target:
                    target = alt
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
            return self._is_walkable(p)

        path = astar(self.state.pos, goal, walkable, size=self.size)
        if path is None and self.state.damaging_cells:
            path = astar(self.state.pos, goal, self.kb.likely_safe, size=self.size)
        if path is None:
            return []
        return path_to_actions(path, self.state.direction)

    def _enough_energy_to_return(self) -> bool:
        """True se ha energia para pelo menos 1 passo de exploracao E o retorno completo.

        Buffer de +6: aciona retorno quando energy <= sth + 6.
        - +5 absorve saltos bruscos do A* (pode crescer ate +3 por passo)
        - +1 extra garante que ao chegar na saida sobra energia para desvios
          de 1 passo (custo ~5) via _best_return_detour.
        Com energia menor que buffer+1 ao chegar seria possivel fazer o desvio
        mas nao garantido; o +1 elimina esse risco.
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
        return self.state.energy > steps_home + 1

    def _choose_target(self, proposed: Position) -> Position:
        snapshot = self.kb.snapshot()
        priority = set(map(tuple, snapshot.get("gold_seen", [])))
        if self.state.energy <= INITIAL_ENERGY // 2:
            priority |= set(map(tuple, snapshot.get("powerup_seen", [])))
        if proposed in priority:
            return proposed
        if proposed in self.state.blocked_cells:
            return (
                self._best_exploration_target(
                    snapshot,
                    include_risky=True,
                    banned=set(self.state.blocked_cells),
                )
                or proposed
            )
        if self.kb.likely_safe(proposed):
            if (
                self.state.gold_carried >= GOLD_TARGET - 1
                and self.state.energy > INITIAL_ENERGY // 8
            ):
                return self._late_gold_frontier() or proposed
            # Trust KB's nearest-first proposal: systematic BFS coverage avoids
            # info_gain bias that deprioritises corner/border cells (e.g. (1,1)).
            return proposed
        return self._best_exploration_target(snapshot, include_risky=True) or proposed

    def _late_gold_frontier(self) -> Optional[Position]:
        best: Optional[Position] = None
        best_cost = float("inf")
        for cell in self.kb.safe_unvisited_frontier():
            path = astar(self.state.pos, cell, self._is_walkable, size=self.size)
            if path is None:
                continue
            actions = path_to_actions(path, self.state.direction)
            if not actions:
                continue
            cost = len(actions)
            if cost < best_cost:
                best_cost = cost
                best = cell
        return best

    def _best_exploration_target(
        self,
        snapshot: Optional[dict] = None,
        *,
        include_risky: bool = True,
        banned: Optional[set[Position]] = None,
    ) -> Optional[Position]:
        snapshot = snapshot or self.kb.snapshot()
        banned = banned or set()
        safe_frontier = set(map(tuple, self.kb.safe_unvisited_frontier()))
        risky_frontier = (
            set(map(tuple, snapshot.get("risky_frontier", []))) if include_risky else set()
        )
        gold_seen = set(map(tuple, snapshot.get("gold_seen", [])))
        powerup_seen = set(map(tuple, snapshot.get("powerup_seen", [])))

        candidates = safe_frontier | risky_frontier
        if self.state.energy <= INITIAL_ENERGY // 2:
            candidates |= powerup_seen
        candidates |= gold_seen
        candidates.discard(self.state.pos)
        candidates -= banned

        best: Optional[Position] = None
        best_score = float("-inf")

        for cell in candidates:
            path = astar(self.state.pos, cell, self._is_walkable, size=self.size)
            if path is None:
                continue
            actions = path_to_actions(path, self.state.direction)
            if not actions:
                continue

            risk = self._risk_penalty(cell, snapshot)
            if risk >= 10_000:
                continue

            travel_cost = len(actions)
            info_gain = self._information_gain(cell, snapshot)
            exit_distance = self._distance_from_exit(cell)
            energy_margin = self._energy_margin_after(cell, travel_cost)

            # Base: information gain weighted strongly, travel penalised.
            # exit_distance kept small (1x) — avoid biasing too far from exit.
            score = info_gain * 16 + exit_distance - travel_cost * 3 - risk
            if cell in gold_seen:
                score += 2000
            if cell in powerup_seen:
                score += 160 + POWERUP_ENERGY_GAIN
            if cell in safe_frontier:
                score += 30
            else:
                score += cell[1] * 0.1 + cell[0] * 0.05
            if energy_margin < 0 and self.state.gold_carried > 0:
                score += energy_margin * 12

            if score > best_score:
                best_score = score
                best = cell

        # Negative utility means the only candidates are probably bad risks.
        if best_score < -250 and not banned:
            return None
        return best

    def _risk_penalty(self, pos: Position, snapshot: dict) -> int:
        if pos in set(map(tuple, snapshot.get("confirmed_pit", []))):
            return 10_000
        penalty = 0
        if pos in set(map(tuple, snapshot.get("risk_pit", []))):
            penalty += 850
        if pos in set(map(tuple, snapshot.get("risk_enemy", []))):
            penalty += 70
        if pos in set(map(tuple, snapshot.get("risk_teleport", []))):
            penalty += 110
        if pos in set(map(tuple, snapshot.get("confirmed_enemy", []))):
            penalty += 160
        if pos in set(map(tuple, snapshot.get("confirmed_teleport", []))):
            penalty += 320
        return penalty

    def _information_gain(self, pos: Position, snapshot: dict) -> int:
        visited = set(map(tuple, snapshot.get("visited", [])))
        safe = set(map(tuple, snapshot.get("safe", [])))
        gain = 0
        for nb in orthogonal_neighbors(pos, self.size):
            if nb not in visited:
                gain += 1
            if nb not in visited and nb not in safe:
                gain += 2
        return gain

    def _distance_from_exit(self, pos: Position) -> int:
        return abs(pos[0] - self.exit_pos[0]) + abs(pos[1] - self.exit_pos[1])

    def _energy_margin_after(self, target: Position, travel_cost: int) -> int:
        from .planner import path_to_actions
        path_home = astar(target, self.exit_pos, self._is_walkable, size=self.size)
        if path_home is None:
            home_cost = self._distance_from_exit(target) * 2 + 5
        else:
            # Estimate turns: count direction changes in the A* path + 2 buffer
            home_walks = max(0, len(path_home) - 1)
            direction_changes = sum(
                1 for i in range(1, len(path_home) - 1)
                if (path_home[i][0] - path_home[i-1][0], path_home[i][1] - path_home[i-1][1])
                != (path_home[i+1][0] - path_home[i][0], path_home[i+1][1] - path_home[i][1])
            ) if len(path_home) > 2 else 0
            home_cost = home_walks + direction_changes + 2
        return self.state.energy - travel_cost - home_cost

    def _is_walkable(self, pos: Position) -> bool:
        damage = self.state.damaging_cells.get(pos, 0)
        if damage >= 40:
            return False
        if damage > 0 and self.state.energy <= damage + 30:
            return False
        if pos in self.state.blocked_cells:
            return False
        return self.kb.likely_safe(pos)

    def _forward_pos(self) -> Position:
        dr, dc = self.state.direction.delta
        return self.state.pos[0] + dr, self.state.pos[1] + dc

    def _neighbor_in_direction(self, direction: Direction) -> Position:
        dr, dc = direction.delta
        return self.state.pos[0] + dr, self.state.pos[1] + dc

    def _best_return_detour(self) -> Optional[Position]:
        """Encontra a celula segura nao visitada mais proxima que pode ser visitada
        enquanto retorna, sem comprometer a chegada na saida com energia >= 1.

        Estimativa conservadora do retorno: walks_home * 2 + 1
        (pior caso: 1 giro por caminhada + 1 alinhamento inicial).
        Condicao: energy > steps_to_cell + est_return  (chega na saida com >= 1 de energia).
        """
        from .planner import astar

        frontier = self.kb.safe_unvisited_frontier()
        if not frontier:
            return None

        def walkable(p: Position) -> bool:
            return self._is_walkable(p)

        best: Optional[Position] = None
        best_total = self.state.energy  # so aceita se total < energy (strict)

        for cell in frontier:
            path_there = self._plan_path(cell)
            if not path_there:
                continue
            steps_to_cell = len(path_there)

            path_home = astar(cell, self.exit_pos, walkable, size=self.size)
            if path_home is None:
                continue
            walks_home = max(0, len(path_home) - 1)
            # Estimate: walks + direction changes in path + 2 buffer
            direction_changes = sum(
                1 for i in range(1, len(path_home) - 1)
                if (path_home[i][0] - path_home[i-1][0], path_home[i][1] - path_home[i-1][1])
                != (path_home[i+1][0] - path_home[i][0], path_home[i+1][1] - path_home[i][1])
            ) if len(path_home) > 2 else 0
            est_return = walks_home + direction_changes + 2

            total = steps_to_cell + est_return
            # Acessivel se sobra pelo menos 1 de energia ao chegar na saida
            if self.state.energy > total and total < best_total:
                best_total = total
                best = cell

        return best

    def _fallback_action(self, target: Position) -> Optional[Action]:
        from .types import orthogonal_neighbors

        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if nb == target and self._is_walkable(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None
