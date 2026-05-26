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
    DAMAGE_BIG,
    DAMAGE_SMALL,
    Direction,
    GOLD_TARGET,
    GRID_SIZE,
    INITIAL_ENERGY,
    Percept,
    Position,
    POWERUP_ENERGY_GAIN,
    START_POS,
    StepResult,
    in_bounds,
    orthogonal_neighbors,
)


@dataclass
class AgentState:
    """Guarda o estado local usado pelo agente durante o jogo.

    Esta estrutura concentra tudo o que o agente precisa acompanhar entre um
    turno e outro: posicao, orientacao, energia observada, score, fila de
    acoes pendentes e pequenas memorias auxiliares usadas para evitar riscos
    repetidos.
    """
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
    returning_to_exit: bool = False
    damaging_cells: dict[Position, int] = field(default_factory=dict)
    blocked_cells: set[Position] = field(default_factory=set)
    teleporter_cells: set[Position] = field(default_factory=set)
    unreachable_targets: set[Position] = field(default_factory=set)


class Agent:
    """Decide a proxima acao usando apenas o que a KB conhece.

    O agente nao consulta o mapa real do ambiente. Ele trabalha somente com as
    percepcoes recebidas, o estado interno que ja construiu e as inferencias da
    base de conhecimento. Isso deixa a solucao alinhada ao enunciado e ajuda a
    separar claramente exploracao, planejamento e simulacao do mundo.
    """

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        size: int = GRID_SIZE,
        kb_backend: str = "auto",
        start: Position = START_POS,
        initial_direction: Direction = Direction.EAST,
    ) -> None:
        """Prepara a KB, o estado inicial e os caches usados nas decisoes."""
        self.kb = kb or make_kb(kb_backend)
        self.size = size
        self.exit_pos = start
        self.state = AgentState(pos=start, direction=initial_direction)
        self._snapshot_cache: Optional[dict] = None
        self._safe_frontier_cache: Optional[list[Position]] = None
        self._safe_cells_cache: Optional[set[Position]] = None
        if hasattr(self.kb, "set_exit"):
            self.kb.set_exit(start)
        self.kb.reset()
        if hasattr(self.kb, "set_exit"):
            self.kb.set_exit(start)
        self.kb.set_agent_pos(start)

    def _invalidate_kb_cache(self) -> None:
        """Descarta snapshots calculados depois de qualquer mudanca na KB."""
        self._snapshot_cache = None
        self._safe_frontier_cache = None
        self._safe_cells_cache = None

    def _snapshot(self) -> dict:
        """Retorna uma visao cacheada do conhecimento atual do agente."""
        if self._snapshot_cache is None:
            self._snapshot_cache = self.kb.snapshot()
        return self._snapshot_cache

    def _safe_frontier(self) -> list[Position]:
        """Lista celulas seguras ainda nao visitadas, usando cache local."""
        if self._safe_frontier_cache is None:
            snapshot = self._snapshot()
            safe = set(map(tuple, snapshot.get("safe", [])))
            visited = set(map(tuple, snapshot.get("visited", [])))
            self._safe_frontier_cache = sorted(safe - visited)
        return self._safe_frontier_cache

    def _safe_cells(self) -> set[Position]:
        """Retorna o conjunto de celulas consideradas seguras pela KB."""
        if self._safe_cells_cache is None:
            self._safe_cells_cache = set(map(tuple, self._snapshot().get("safe", [])))
        return self._safe_cells_cache

    def _is_known_safe(self, pos: Position) -> bool:
        """Verifica se uma posicao ja esta no conjunto seguro conhecido."""
        return pos in self._safe_cells()

    @property
    def backend(self) -> str:
        """Informa qual backend de conhecimento esta em uso.

        Essa informacao aparece principalmente na interface e nos resultados
        finais, facilitando a comparacao entre Python e SWI-Prolog.
        """
        return getattr(self.kb, "backend", "unknown")

    @property
    def backend_label(self) -> str:
        """Label amigavel para mostrar quando Python esta atuando como fallback."""
        backend = self.backend
        fallback_from = getattr(self.kb, "fallback_from", None)
        if fallback_from:
            return f"{backend} (fallback de {fallback_from})"
        return backend

    @property
    def fallback_reason(self) -> str | None:
        """Motivo do fallback automatico, quando houver."""
        return getattr(self.kb, "fallback_reason", None)

    def observe(self, percept: Percept, pos: Position, direction: Direction,
                energy: int, score: int) -> None:
        """Atualiza o estado interno com a percepcao do turno.

        Aqui o agente sincroniza o que acabou de observar com sua KB e registra
        efeitos importantes, como dano recebido ao entrar em uma celula. Ao
        final, qualquer plano antigo e descartado para evitar que uma rota
        desatualizada conduza o agente a um risco recem-descoberto.
        """
        previous_pos = self.state.pos
        previous_energy = self.state.energy
        self.state.pos = pos
        self.state.direction = direction
        self.state.energy = energy
        self.state.score = score
        self.state.last_percept = percept
        if pos != previous_pos:
            self.state.unreachable_targets.clear()

        if hasattr(self.kb, "set_agent_state"):
            self.kb.set_agent_state(pos, energy)
        else:
            self.kb.set_agent_pos(pos)
            self.kb.set_agent_energy(energy)
        active = percept.as_list()
        self.kb.update_perception(pos, active)
        self._invalidate_kb_cache()
        self._release_safe_blocks()
        if (
            self.state.last_action == Action.WALK
            and energy < previous_energy
            and not percept.scream
        ):
            self.state.damaging_cells[pos] = max(
                self.state.damaging_cells.get(pos, 0),
                previous_energy - energy,
            )

        self.state.pending.clear()

    def notify_picked(self, kind: str) -> None:
        """Sincroniza a KB quando ouro ou powerup sao coletados.

        Essa etapa evita que a base de conhecimento continue perseguindo itens
        que ja sairam do mapa.
        """
        if kind == "gold":
            self.state.gold_carried += 1
            self.kb.mark_gold_taken(self.state.pos)
            self._invalidate_kb_cache()
        elif kind == "powerup":
            self.kb.mark_powerup_taken(self.state.pos)
            self._invalidate_kb_cache()

    def notify_step_result(self, action: Action, result: StepResult) -> None:
        """Aprende efeitos que so aparecem depois de executar uma acao.

        O principal caso e teletransporte: a percepcao `flash` avisa que ha um
        teletransporte adjacente, mas so o resultado da acao confirma qual
        celula causou o salto. Bloquear essa origem evita que o planejador
        reutilize a mesma casa e entre em ciclos aleatorios.
        """
        if action != Action.WALK or not result.teleported:
            return
        origins = result.teleported_from or [self._forward_pos()]
        for origin in origins:
            if in_bounds(origin, self.size):
                self.state.teleporter_cells.add(origin)
                self.state.blocked_cells.add(origin)
        self.state.pending.clear()
        self._invalidate_kb_cache()

    def _release_safe_blocks(self) -> None:
        """Remove bloqueios temporarios que a KB ja provou serem seguros."""
        releasable = {
            cell
            for cell in self.state.blocked_cells
            if cell not in self.state.teleporter_cells and self.kb.likely_safe(cell)
        }
        if releasable:
            self.state.blocked_cells -= releasable

    def decide_action(self) -> Action:
        """Calcula e registra a acao escolhida para o turno.

        O metodo publico e curto de proposito: ele delega a logica principal
        para `_decide()` e apenas registra a ultima acao escolhida.
        """
        action = self._decide()
        self.state.last_action = action
        return action

    def _decide(self) -> Action:
        """Organiza a prioridade entre coleta, retorno e exploracao.

        A ordem aqui foi pensada para ficar facil de explicar:
        1. consumir a fila de acoes ja planejadas;
        2. pegar item da celula atual sempre que houver;
        3. reagir a impacto ou situacoes especiais;
        4. voltar para a saida quando isso ja faz mais sentido;
        5. consultar a KB para seguir explorando.
        """
        if self.state.pending:
            return self.state.pending.popleft()
        if (self.state.last_percept is not None and self.state.last_percept.glow):
            return Action.GRAB
        if (self.state.last_percept is not None
                and self.state.last_percept.powerup
                and self.state.energy <= INITIAL_ENERGY - POWERUP_ENERGY_GAIN):
            return Action.GRAB
        if (self.state.last_percept is not None
                and self.state.last_percept.impact
                and self.state.last_action == Action.WALK):
            return Action.TURN_RIGHT
        if self.state.gold_carried >= GOLD_TARGET:
            self.state.returning_to_exit = True
        if self.state.returning_to_exit:
            if self.state.pos == self.exit_pos:
                if self.state.gold_carried >= GOLD_TARGET:
                    self.state.returning_to_exit = False
                    self.state.last_decision = ("sair", None)
                    return Action.EXIT
                late_corner = self._late_risky_corner_target()
                if late_corner is not None:
                    self.state.returning_to_exit = False
                    action = self._move_toward(late_corner)
                    if action is not None:
                        self.state.last_decision = ("canto_ultimo_ouro", late_corner)
                        return action
                detour = self._best_return_detour()
                if detour is not None:
                    action = self._move_toward(detour)
                    if action is not None:
                        self.state.last_decision = ("desvio_retorno", detour)
                        return action
                self.state.returning_to_exit = False
                self.state.blocked_cells = set(self.state.teleporter_cells)
            else:
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
                if self.state.gold_carried >= GOLD_TARGET:
                    self.state.last_decision = ("retornar_sem_rota", self.exit_pos)
                    return Action.TURN_RIGHT
                self.state.returning_to_exit = False
        if not self.state.returning_to_exit and self._should_return_for_energy():
            self.state.returning_to_exit = True
            self.state.last_decision = ("retornar_energia_critica", self.exit_pos)
            if self.state.pos == self.exit_pos:
                return Action.EXIT
            action = self._move_toward(self.exit_pos)
            if action is not None:
                return action
        late_corner = self._late_risky_corner_target()
        if late_corner is not None:
            action = self._move_toward(late_corner)
            if action is not None:
                self.state.last_decision = ("canto_ultimo_ouro", late_corner)
                return action
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
            gold_seen = set(map(tuple, self._snapshot().get("gold_seen", [])))
            if target not in gold_seen:
                self.state.unreachable_targets.add(target)
            alt = self._best_exploration_target(
                self._snapshot(),
                include_risky=True,
                banned=set(self.state.blocked_cells) | set(self.state.unreachable_targets),
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
            if self.state.gold_carried < GOLD_TARGET:
                action = self._safe_step_from_exit()
                if action is not None:
                    self.state.last_decision = ("retomar_exploracao", None)
                    return action
            return Action.TURN_RIGHT

        return Action.EXIT

    def _move_toward(self, target: Position) -> Optional[Action]:
        """Transforma uma meta em acoes de curto prazo.

        Primeiro o agente planeja um caminho. Em seguida, antes de executar,
        ele ainda faz uma ultima verificacao local para evitar avancar
        diretamente para uma celula que acabou de parecer arriscada.
        """
        actions = self._plan_path(target)
        if actions and actions[0] == Action.WALK and self.state.last_percept:
            forward = self._forward_pos()
            pursuing_late_risky_target = (
                forward == target
                and self.state.gold_carried >= GOLD_TARGET - 1
                and self.kb.is_risky(target)
            )
            if (
                target != self.exit_pos
                and self.state.last_percept.breeze
                and self.kb.is_risky(forward)
                and not pursuing_late_risky_target
            ):
                self.state.blocked_cells.add(forward)
                right = self._neighbor_in_direction(self.state.direction.turn_right())
                if in_bounds(right, self.size) and right not in self.state.blocked_cells:
                    return Action.TURN_RIGHT
                alt = self._best_exploration_target(
                    self._snapshot(),
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
        """Planeja um caminho seguro ate a meta.

        O planejamento principal evita celulas perigosas, bloqueadas ou
        marcadas como dano forte. Se isso falhar, a funcao ainda tenta uma
        segunda busca mais permissiva para nao travar o agente desnecessariamente.
        """
        def walkable(p: Position) -> bool:
            """Permite ao A* andar apenas por celulas aceitas pelo agente."""
            return self._is_walkable(p)

        path = astar(self.state.pos, goal, walkable, size=self.size)
        if path is None and goal == self.exit_pos and self.state.gold_carried >= GOLD_TARGET:
            path = astar(self.state.pos, goal, self._is_known_safe, size=self.size)
        if path is None and self.state.damaging_cells:
            path = astar(self.state.pos, goal, self._is_known_safe, size=self.size)
        if path is None:
            return []
        return path_to_actions(path, self.state.direction)

    def _should_return_for_energy(self) -> bool:
        """Decide retorno por energia sem tratar deslocamento como gasto.

        Como andar nao consome energia, a distancia ate a saida nao entra mais
        nesse calculo. Energia baixa aqui significa pouca margem para sobreviver
        a outro inimigo; se houver powerup seguro conhecido, o agente tenta
        recuperar energia em vez de desistir da exploracao.
        """
        if self.state.gold_carried <= 0:
            return False
        if self.state.energy > CRITICAL_ENERGY_RETURN:
            return False

        snapshot = self._snapshot()
        powerups = set(map(tuple, snapshot.get("powerup_seen", [])))
        safe_powerups = [
            p
            for p in powerups
            if self._is_known_safe(p)
            and p not in self.state.blocked_cells
            and p not in self.state.teleporter_cells
        ]
        return not safe_powerups

    def _choose_target(self, proposed: Position) -> Position:
        """Ajusta a meta da KB quando existe uma alternativa melhor.

        A KB escolhe uma meta plausivel, mas o agente ainda pode refinar essa
        escolha com heuristicas de custo, bloqueios temporarios e prioridades
        de coleta.
        """
        snapshot = self._snapshot()
        priority = set(map(tuple, snapshot.get("gold_seen", [])))
        if self.state.energy <= INITIAL_ENERGY // 2:
            priority |= set(map(tuple, snapshot.get("powerup_seen", [])))
        if proposed in priority:
            return proposed
        if proposed in self.state.unreachable_targets:
            return (
                self._best_exploration_target(
                    snapshot,
                    include_risky=True,
                    banned=set(self.state.blocked_cells) | set(self.state.unreachable_targets),
                )
                or proposed
            )
        if proposed in self.state.blocked_cells:
            return (
                self._best_exploration_target(
                    snapshot,
                    include_risky=True,
                    banned=set(self.state.blocked_cells) | set(self.state.unreachable_targets),
                )
                or proposed
            )
        if self._is_known_safe(proposed):
            if (
                self.state.gold_carried >= GOLD_TARGET - 1
                and self.state.energy > INITIAL_ENERGY // 8
            ):
                return self._late_gold_frontier() or proposed
            return proposed
        return self._best_exploration_target(snapshot, include_risky=True) or proposed

    def _late_gold_frontier(self) -> Optional[Position]:
        """Escolhe a fronteira segura mais barata no fim da exploracao.

        Quando o agente ja esta perto de completar a coleta, vale simplificar a
        decisao e priorizar caminhos curtos para terminar o mapa com menos
        desperdicio de movimentos.
        """
        best: Optional[Position] = None
        best_cost = float("inf")
        for cell in self._safe_frontier():
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

    def _late_risky_corner_target(self) -> Optional[Position]:
        """Prioriza cantos arriscados quando falta apenas um ouro.

        Alguns mapas escondem ouro em uma casa que continua suspeita por ficar
        ao lado de um poco. Depois de coletar dois ouros, essa regra evita que
        o agente gaste o fim do jogo circulando por riscos menos promissores.
        """
        if self.state.gold_carried < GOLD_TARGET - 1:
            return None
        snapshot = self._snapshot()
        if snapshot.get("gold_seen"):
            return None

        visited = set(map(tuple, snapshot.get("visited", [])))
        risky = set(map(tuple, snapshot.get("risky_frontier", [])))
        confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
        candidates = [
            cell
            for cell in risky
            if self._is_corner(cell)
            and cell not in visited
            and cell not in confirmed_pit
            and cell not in self.state.blocked_cells
            and cell not in self.state.unreachable_targets
        ]
        if not candidates:
            return None

        reachable: list[tuple[int, Position]] = []
        for cell in candidates:
            path = astar(self.state.pos, cell, self._is_walkable, size=self.size)
            if path is None:
                continue
            actions = path_to_actions(path, self.state.direction)
            if actions:
                reachable.append((len(actions), cell))
        if not reachable:
            return None
        return min(reachable)[1]

    def _best_exploration_target(
        self,
        snapshot: Optional[dict] = None,
        *,
        include_risky: bool = True,
        banned: Optional[set[Position]] = None,
    ) -> Optional[Position]:
        """Compara fronteiras por ganho de informacao, custo e risco.

        Esta e a heuristica mais rica do agente. Ela combina:
        - o quanto a celula pode revelar do mapa;
        - o custo para chegar ate ela;
        - a distancia em relacao a saida;
        - o risco estimado a partir da KB;
        - o efeito esperado sobre a energia restante.
        """
        snapshot = snapshot or self._snapshot()
        banned = banned or set()
        safe_frontier = set(map(tuple, self._safe_frontier()))
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
        candidates -= self.state.teleporter_cells
        candidates -= self.state.blocked_cells
        candidates -= banned
        candidates -= self.state.unreachable_targets

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
            energy_margin = self._energy_margin_after(cell, snapshot)

            score = info_gain * 16 + exit_distance - travel_cost * 3 - risk
            if cell in gold_seen:
                score += 2000
            if cell in powerup_seen:
                score += 160 + POWERUP_ENERGY_GAIN
            if (
                self.state.gold_carried >= GOLD_TARGET - 1
                and cell in risky_frontier
                and self._is_corner(cell)
            ):
                score += 1800
            if cell in safe_frontier:
                score += 30
            else:
                score += cell[1] * 0.1 + cell[0] * 0.05
            if energy_margin < 0 and self.state.gold_carried > 0:
                score += energy_margin * 12

            if score > best_score:
                best_score = score
                best = cell

        if best_score < -250 and not banned:
            return None
        return best

    def _risk_penalty(self, pos: Position, snapshot: dict) -> int:
        """Traduz os sinais da KB em uma penalidade numerica.

        O objetivo nao e modelar probabilidade exata, e sim transformar a
        intuicao de risco em um numero comparavel dentro da heuristica.
        """
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
        """Estimativa simples de quanto uma celula pode revelar.

        Quanto mais vizinhos desconhecidos ou pouco explicados a celula tiver,
        maior tende a ser o ganho de informacao ao visita-la.
        """
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
        """Calcula a distancia Manhattan ate a saida.

        Esse valor ajuda a evitar exploracoes que empurrem o agente para longe
        demais quando o retorno ja comeca a importar.
        """
        return abs(pos[0] - self.exit_pos[0]) + abs(pos[1] - self.exit_pos[1])

    def _is_corner(self, pos: Position) -> bool:
        """Indica se uma posicao fica em um canto do tabuleiro."""
        x, y = pos
        return x in (1, self.size) and y in (1, self.size)

    def _energy_margin_after(self, target: Position, snapshot: dict) -> int:
        """Estima a energia apos o evento provavel da celula alvo.

        Deslocamento nao entra nessa conta: energia so muda em inimigos e
        powerups. A estimativa serve apenas para evitar escolher um risco que
        possa matar o agente quando ele ja esta carregando ouro.
        """
        expected = self.state.energy
        powerup_seen = set(map(tuple, snapshot.get("powerup_seen", [])))
        if target in powerup_seen:
            expected = min(INITIAL_ENERGY, expected + POWERUP_ENERGY_GAIN)

        if target in set(map(tuple, snapshot.get("confirmed_pit", []))):
            return -1000
        if target in set(map(tuple, snapshot.get("risk_pit", []))):
            return min(expected, 0)
        if target in set(map(tuple, snapshot.get("confirmed_enemy", []))):
            return expected - DAMAGE_BIG
        if target in set(map(tuple, snapshot.get("risk_enemy", []))):
            return expected - DAMAGE_SMALL
        return expected

    def _is_walkable(self, pos: Position) -> bool:
        """Filtra celulas seguras e evita riscos repetidos.

        Mesmo que a KB considere uma celula tecnicamente acessivel, o agente
        pode recusá-la se ela tiver causado dano relevante ou se tiver sido
        bloqueada temporariamente por um contexto de risco recente.
        """
        damage = self.state.damaging_cells.get(pos, 0)
        if damage >= 40:
            return False
        if damage > 0 and self.state.energy <= damage + 30:
            return False
        if pos in self.state.teleporter_cells:
            return False
        if pos in self.state.blocked_cells:
            return False
        return self._is_known_safe(pos)

    def _forward_pos(self) -> Position:
        """Retorna a celula logo a frente do agente.

        Esse helper simplifica verificacoes locais antes do proximo WALK.
        """
        dr, dc = self.state.direction.delta
        return self.state.pos[0] + dr, self.state.pos[1] + dc

    def _neighbor_in_direction(self, direction: Direction) -> Position:
        """Retorna o vizinho ortogonal para uma direcao dada.

        E usado em pequenos ajustes taticos, como virar antes de entrar em uma
        celula recem-marcada como suspeita.
        """
        dr, dc = direction.delta
        return self.state.pos[0] + dr, self.state.pos[1] + dc

    def _best_return_detour(self) -> Optional[Position]:
        """Procura um pequeno desvio seguro durante o retorno.

        Em vez de voltar sempre em linha reta, o agente tenta aproveitar o
        caminho para visitar uma sala segura e ainda nao explorada, desde que
        isso nao comprometa a chegada na saida com folga suficiente.
        """
        from .planner import astar

        frontier = self._safe_frontier()
        if not frontier:
            return None

        def walkable(p: Position) -> bool:
            """Reusa a politica de caminhada atual para avaliar desvios."""
            return self._is_walkable(p)

        if self.state.energy <= CRITICAL_ENERGY_RETURN:
            return None

        best: Optional[Position] = None
        best_total = float("inf")

        for cell in frontier:
            path_there = self._plan_path(cell)
            if not path_there:
                continue
            steps_to_cell = len(path_there)

            path_home = astar(cell, self.exit_pos, walkable, size=self.size)
            if path_home is None:
                continue
            walks_home = max(0, len(path_home) - 1)
            direction_changes = sum(
                1 for i in range(1, len(path_home) - 1)
                if (path_home[i][0] - path_home[i-1][0], path_home[i][1] - path_home[i-1][1])
                != (path_home[i+1][0] - path_home[i][0], path_home[i+1][1] - path_home[i][1])
            ) if len(path_home) > 2 else 0
            est_return = walks_home + direction_changes + 2

            total = steps_to_cell + est_return
            if total < best_total:
                best_total = total
                best = cell

        return best

    def _safe_step_from_exit(self) -> Optional[Action]:
        """Sai do portal quando ainda falta ouro e a meta atual nao tem rota."""
        if self.state.pos != self.exit_pos:
            return None
        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if self._is_walkable(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None

    def _fallback_action(self, target: Position) -> Optional[Action]:
        """Usa um movimento direto quando o plano completo falha.

        Esse fallback cobre casos pequenos em que o A* nao montou um plano
        completo, mas ainda existe um vizinho imediato que leva ao alvo.
        """
        for nb in orthogonal_neighbors(self.state.pos, self.size):
            if nb == target and self._is_walkable(nb):
                actions = path_to_actions([self.state.pos, nb], self.state.direction)
                if actions:
                    self.state.pending.extend(actions[1:])
                    return actions[0]
        return None
