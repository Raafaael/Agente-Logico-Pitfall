"""Pure-Python implementation of the Prolog knowledge base.

Mirrors the rules in :file:`knowledge_base.pl` so the project remains
runnable when SWI-Prolog is not available locally. Both implementations
expose the same :class:`KnowledgeBase` Protocol -- see
:mod:`pitfall.prolog_bridge` for the wiring.

Inference model (classic wumpus-world):
    A cell is `likely_safe` only if we have positively ruled out every
    hazard for it -- either by visiting it, or by observing a neighbor
    that did NOT sense the corresponding hazard. Cells we have no
    evidence about remain "unknown" and are NOT considered safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .types import GOLD_TARGET, GRID_SIZE, INITIAL_ENERGY, Position, orthogonal_neighbors


@dataclass
class PythonKB:
    """Implementacao Python do modelo memory/certeza (espelho de knowledge_base.pl).

    memory[pos] = conjunto de sinais de perigo que pos PODERIA estar emitindo.
    Atualizado por intersecao a cada vizinho visitado. memory[pos] = set() => segura.
    certeza = conjunto de posicoes confirmadas (visitadas ou deduzidas seguras).
    """

    size: int = GRID_SIZE

    # Modelo memory/certeza (equivalente ao Prolog)
    memory: dict = field(default_factory=dict)          # pos -> frozenset de obs
    certeza: set = field(default_factory=set)
    visited: set[Position] = field(default_factory=set)

    # Sinais de perigo registrados em celulas visitadas (para inferencia)
    breeze_at: set[Position] = field(default_factory=set)
    steps_at: set[Position] = field(default_factory=set)
    flash_at: set[Position] = field(default_factory=set)

    # Perigos confirmados por unicidade
    confirmed_pit: set[Position] = field(default_factory=set)
    confirmed_enemy: set[Position] = field(default_factory=set)
    confirmed_teleport: set[Position] = field(default_factory=set)

    # Percepcoes locais
    gold_seen: set[Position] = field(default_factory=set)
    powerup_seen: set[Position] = field(default_factory=set)

    agent_pos: Position = (1, 1)
    agent_energy: int = INITIAL_ENERGY
    exit_pos: Position = (1, 1)
    gold_carried: int = 0

    backend: str = "python"

    # Limiar de energia para buscar/pegar powerup (energy_low_threshold em Prolog)
    _energy_low: int = field(default=INITIAL_ENERGY // 2, init=False, repr=False)

    # Mapeamento: nome do percepto -> observacao de perigo
    _PERCEPT_OBS: dict = field(
        default_factory=lambda: {"breeze": "brisa", "steps": "passos", "flash": "palmas"},
        init=False, repr=False,
    )

    def reset(self) -> None:
        self.memory.clear()
        self.certeza.clear()
        self.visited.clear()
        self.breeze_at.clear()
        self.steps_at.clear()
        self.flash_at.clear()
        self.confirmed_pit.clear()
        self.confirmed_enemy.clear()
        self.confirmed_teleport.clear()
        self.gold_seen.clear()
        self.powerup_seen.clear()
        self.agent_pos = self.exit_pos
        self.agent_energy = INITIAL_ENERGY
        self.gold_carried = 0

    def set_exit(self, pos: Position) -> None:
        self.exit_pos = pos

    def set_agent_pos(self, pos: Position) -> None:
        self.agent_pos = pos

    def set_agent_energy(self, energy: int) -> None:
        self.agent_energy = energy

    def update_perception(self, pos: Position, percepts: list[str]) -> None:
        # Celula atual: visitada, com certeza, memory = {} (segura)
        self.visited.add(pos)
        self.certeza.add(pos)
        self.memory[pos] = frozenset()
        self.confirmed_pit.discard(pos)
        self.confirmed_enemy.discard(pos)
        self.confirmed_teleport.discard(pos)

        # Registrar sinais de perigo percebidos (para inferencia de fonte unica)
        self._remember_signal(pos, "breeze" in percepts, self.breeze_at)
        self._remember_signal(pos, "steps"  in percepts, self.steps_at)
        self._remember_signal(pos, "flash"  in percepts, self.flash_at)

        # Percepcoes locais: ouro e powerup na celula atual
        if "glow" in percepts:
            self.gold_seen.add(pos)
        else:
            self.gold_seen.discard(pos)

        if "powerup" in percepts:
            self.powerup_seen.add(pos)
        else:
            self.powerup_seen.discard(pos)

        # Construir vetor de sinais de perigo para vizinhos
        hazard_obs = frozenset(
            obs for p, obs in self._PERCEPT_OBS.items() if p in percepts
        )

        # Atualizar memoria dos vizinhos por intersecao (modelo main.pl)
        for nb in orthogonal_neighbors(pos, self.size):
            if nb in self.certeza:
                continue
            if nb in self.memory:
                self.memory[nb] = self.memory[nb] & hazard_obs
            else:
                self.memory[nb] = hazard_obs

        # Inferencia: celulas com memoria vazia sao seguras; fonte unica de perigo
        self._infer_safe_from_empty()
        changed = True
        while changed:
            changed = self._infer_unique_source(self.breeze_at, "brisa",  self.confirmed_pit)
            changed |= self._infer_unique_source(self.steps_at,  "passos", self.confirmed_enemy)
            changed |= self._infer_unique_source(self.flash_at,  "palmas", self.confirmed_teleport)

    def _remember_signal(self, pos: Position, present: bool,
                         store: set[Position]) -> None:
        if present:
            store.add(pos)
        else:
            store.discard(pos)

    def _infer_safe_from_empty(self) -> None:
        for pos, obs in list(self.memory.items()):
            if len(obs) == 0 and pos not in self.certeza:
                self.certeza.add(pos)
                self.confirmed_pit.discard(pos)
                self.confirmed_enemy.discard(pos)
                self.confirmed_teleport.discard(pos)

    def _infer_unique_source(
        self,
        sensed_set: set[Position],
        hazard_obs: str,
        confirmed_set: set[Position],
    ) -> bool:
        changed = False
        for source in tuple(sensed_set):
            cands = [
                n for n in orthogonal_neighbors(source, self.size)
                if n not in self.certeza
                and n not in self.visited
                and (hazard_obs in self.memory.get(n, {hazard_obs}))
            ]
            if len(cands) == 1:
                target = cands[0]
                if target not in confirmed_set:
                    confirmed_set.add(target)
                    changed = True
        return changed

    def mark_gold_taken(self, pos: Position) -> None:
        self.gold_seen.discard(pos)
        self.gold_carried += 1

    def mark_powerup_taken(self, pos: Position) -> None:
        self.powerup_seen.discard(pos)

    def likely_safe(self, pos: Position) -> bool:
        if not self._valid(pos):
            return False
        if pos in self.confirmed_pit:
            return False
        if pos in self.certeza:
            return True
        obs = self.memory.get(pos)
        if obs is None:
            return False
        return not (obs & {"brisa", "passos", "palmas"})

    def is_visited(self, pos: Position) -> bool:
        return pos in self.visited

    def is_known_gold(self, pos: Position) -> bool:
        return pos in self.gold_seen

    def is_risky(self, pos: Position) -> bool:
        if pos in self.certeza:
            return False
        if pos in self.confirmed_pit or pos in self.confirmed_enemy or pos in self.confirmed_teleport:
            return True
        obs = self.memory.get(pos, frozenset())
        return bool(obs & {"brisa", "passos", "palmas"})

    def safe_unvisited_frontier(self) -> list[Position]:
        return [
            (r, c)
            for r in range(1, self.size + 1)
            for c in range(1, self.size + 1)
            if self.likely_safe((r, c)) and (r, c) not in self.visited
        ]

    def decide(self) -> tuple[str, Optional[Position]]:
        """Espelho das regras decide/1 de knowledge_base.pl.

        O agente nunca retorna com ouro parcial por energia baixa (fiel ao main.pl).
        O retorno forcado fica por conta de agent.py (CRITICAL_ENERGY_RETURN=25).

        Prioridade:
          1. pegar ouro no local
          2. pegar powerup no local quando energia baixa
          3. sair com todos os ouros na saida
          4. mover para ouro seguro conhecido
          5. mover para powerup mais proximo quando energia baixa (energia_baixa)
          6. explorar fronteira segura
          7. arriscar fronteira de menor risco
          8. voltar para saida (fallback — sem mais o que explorar)
        """
        pos = self.agent_pos

        # 1. Ouro no local
        if pos in self.gold_seen:
            return "pegar", None

        # 2. Powerup no local: pegar sempre que encontrado.
        if pos in self.powerup_seen:
            return "pegar", None

        # 3. Saida com todos os ouros
        if pos == self.exit_pos and self.gold_carried >= GOLD_TARGET:
            return "sair", None

        # 4. Ouro seguro conhecido
        for g in self.gold_seen:
            if g != pos and self.likely_safe(g):
                return "mover", g

        # 5. energia_baixa: buscar powerup mais proximo
        if self.agent_energy <= self._energy_low:
            reachable = [
                p for p in self.powerup_seen
                if p != pos and self.likely_safe(p)
            ]
            if reachable:
                target = min(reachable,
                             key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
                return "mover", target

        # 6. Explorar fronteira segura
        frontier = self.safe_unvisited_frontier()
        if frontier:
            target = min(frontier,
                         key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
            return "mover", target

        # 7. Arriscar fronteira de menor risco
        risky = self.risky_frontier()
        if risky:
            target = min(risky,
                         key=lambda p: (self.risk_score(p),
                                        abs(p[0]-pos[0]) + abs(p[1]-pos[1])))
            return "mover", target

        # 8. Fallback: voltar para saida (sem mais o que explorar)
        if pos != self.exit_pos:
            return "mover", self.exit_pos

        return "sair", None

    def risky_frontier(self) -> list[Position]:
        out: set[Position] = set()
        for seen in self.visited | self.certeza:
            for nb in orthogonal_neighbors(seen, self.size):
                if nb in self.visited or self.likely_safe(nb):
                    continue
                if nb in self.confirmed_pit:
                    continue
                out.add(nb)
        return sorted(out)

    def risk_score(self, pos: Position) -> int:
        if pos in self.confirmed_pit:
            return 10_000
        score = 10
        obs = self.memory.get(pos, frozenset())
        if pos in self.confirmed_enemy:
            score += 80
        if pos in self.confirmed_teleport:
            score += 260
        if "passos" in obs:
            score += 60 + 30 * self._source_count(pos, self.steps_at)
        if "palmas" in obs:
            score += 180 + 60 * self._source_count(pos, self.flash_at)
        if "brisa" in obs:
            score += 900 + 120 * self._source_count(pos, self.breeze_at)
        if not self.is_risky(pos):
            score += 40
        return score

    def _source_count(self, pos: Position, sources: set[Position]) -> int:
        return sum(1 for src in sources if pos in orthogonal_neighbors(src, self.size))

    def _confirmed_any(self, pos: Position) -> bool:
        return (
            pos in self.confirmed_pit
            or pos in self.confirmed_enemy
            or pos in self.confirmed_teleport
        )

    def _valid(self, pos: Position) -> bool:
        r, c = pos
        return 1 <= r <= self.size and 1 <= c <= self.size

    def snapshot(self) -> dict:
        safe = [
            (r, c)
            for r in range(1, self.size + 1)
            for c in range(1, self.size + 1)
            if self.likely_safe((r, c))
        ]
        risk_pit = [
            p for p, obs in self.memory.items()
            if p not in self.certeza and "brisa" in obs
        ]
        risk_enemy = [
            p for p, obs in self.memory.items()
            if p not in self.certeza and "passos" in obs
        ]
        risk_tele = [
            p for p, obs in self.memory.items()
            if p not in self.certeza and "palmas" in obs
        ]
        return {
            "visited": sorted(self.visited),
            "safe": sorted(safe),
            "risk_pit": sorted(risk_pit),
            "risk_enemy": sorted(risk_enemy),
            "risk_teleport": sorted(risk_tele),
            "confirmed_pit": sorted(self.confirmed_pit),
            "confirmed_enemy": sorted(self.confirmed_enemy),
            "confirmed_teleport": sorted(self.confirmed_teleport),
            "risky_frontier": self.risky_frontier(),
            "gold_seen": sorted(self.gold_seen),
            "powerup_seen": sorted(self.powerup_seen),
            "gold_carried": self.gold_carried,
        }
