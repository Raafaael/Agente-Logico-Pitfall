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

from .types import (
    GOLD_TARGET,
    GRID_SIZE,
    INITIAL_ENERGY,
    POWERUP_ENERGY_GAIN,
    Position,
    orthogonal_neighbors,
)


@dataclass
class PythonKB:
    """Replica em Python a base de conhecimento usada no Prolog.

    O objetivo desta classe e manter o mesmo comportamento da KB declarativa
    mesmo quando o SWI-Prolog nao estiver disponivel. Assim, o projeto pode ser
    executado e testado em qualquer ambiente, preservando a mesma ideia de
    representacao: memoria parcial, certeza de seguranca, suspeitas de perigo e
    escolhas guiadas apenas por percepcoes.
    """

    size: int = GRID_SIZE

    memory: dict = field(default_factory=dict)          # pos -> frozenset de obs
    certeza: set = field(default_factory=set)
    visited: set[Position] = field(default_factory=set)

    breeze_at: set[Position] = field(default_factory=set)
    steps_at: set[Position] = field(default_factory=set)
    flash_at: set[Position] = field(default_factory=set)

    confirmed_pit: set[Position] = field(default_factory=set)
    confirmed_enemy: set[Position] = field(default_factory=set)
    confirmed_teleport: set[Position] = field(default_factory=set)

    gold_seen: set[Position] = field(default_factory=set)
    powerup_seen: set[Position] = field(default_factory=set)

    agent_pos: Position = (1, 1)
    agent_energy: int = INITIAL_ENERGY
    exit_pos: Position = (1, 1)
    gold_carried: int = 0

    backend: str = "python"
    fallback_from: str | None = None
    fallback_reason: str | None = None

    _energy_low: int = field(default=INITIAL_ENERGY // 2, init=False, repr=False)

    _PERCEPT_OBS: dict = field(
        default_factory=lambda: {"breeze": "brisa", "steps": "passos", "flash": "palmas"},
        init=False, repr=False,
    )

    def reset(self) -> None:
        """Limpa toda a memoria da base de conhecimento.

        Esse metodo devolve a KB ao estado inicial do jogo, apagando fatos
        observados, confirmacoes de perigo, itens conhecidos e estado do agente.
        """
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
        """Define a posicao de saida do mapa.

        A saida normalmente coincide com a posicao inicial, mas fica
        parametrizada para manter a KB desacoplada do carregamento de mapas.
        """
        self.exit_pos = pos

    def set_agent_pos(self, pos: Position) -> None:
        """Atualiza a posicao conhecida do agente.

        A KB usa essa informacao para decidir entre pegar, explorar, voltar ou
        sair do mapa.
        """
        self.agent_pos = pos

    def set_agent_energy(self, energy: int) -> None:
        """Atualiza a energia conhecida do agente.

        A energia influencia principalmente as regras de busca por powerup e de
        retorno mais conservador.
        """
        self.agent_energy = energy

    def set_agent_state(self, pos: Position, energy: int) -> None:
        """Atualiza posicao e energia em uma unica chamada."""
        self.agent_pos = pos
        self.agent_energy = energy

    def update_perception(self, pos: Position, percepts: list[str]) -> None:
        """Atualiza a memoria com base nas percepcoes atuais.

        A celula atual passa a ser tratada como visitada e segura. Em seguida,
        a KB propaga para os vizinhos os sinais de perigo observados e tenta
        deduzir novas certezas, como uma fonte unica de poco, inimigo ou
        teletransporte.
        """
        self.visited.add(pos)
        self.certeza.add(pos)
        self.memory[pos] = frozenset()
        self.confirmed_pit.discard(pos)
        self.confirmed_enemy.discard(pos)
        self.confirmed_teleport.discard(pos)

        self._remember_signal(pos, "breeze" in percepts, self.breeze_at)
        self._remember_signal(pos, "steps"  in percepts, self.steps_at)
        self._remember_signal(pos, "flash"  in percepts, self.flash_at)

        if "glow" in percepts:
            self.gold_seen.add(pos)
        else:
            self.gold_seen.discard(pos)

        if "powerup" in percepts:
            self.powerup_seen.add(pos)
        else:
            self.powerup_seen.discard(pos)

        hazard_obs = frozenset(
            obs for p, obs in self._PERCEPT_OBS.items() if p in percepts
        )

        for nb in orthogonal_neighbors(pos, self.size):
            if nb in self.certeza:
                continue
            if nb in self.memory:
                self.memory[nb] = self.memory[nb] & hazard_obs
            else:
                self.memory[nb] = hazard_obs

        self._infer_safe_from_empty()
        changed = True
        while changed:
            changed = self._infer_unique_source(self.breeze_at, "brisa",  self.confirmed_pit)
            changed |= self._infer_unique_source(self.steps_at,  "passos", self.confirmed_enemy)
            changed |= self._infer_unique_source(self.flash_at,  "palmas", self.confirmed_teleport)

    def _remember_signal(self, pos: Position, present: bool,
                         store: set[Position]) -> None:
        """Guarda ou remove um sinal percebido em uma celula.

        Esse helper centraliza a atualizacao dos conjuntos de brisa, passos e
        flash percebidos durante a exploracao.
        """
        if present:
            store.add(pos)
        else:
            store.discard(pos)

    def _infer_safe_from_empty(self) -> None:
        """Marca como segura uma celula sem sinais possiveis de perigo.

        Quando a intersecao de evidencias fica vazia, a KB conclui que aquela
        celula nao pode conter nenhum dos perigos modelados.
        """
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
        """Confirma um perigo quando resta apenas uma fonte possivel.

        Esse e o passo de inferencia mais forte da KB: se um sinal observado so
        pode vir de uma unica celula ainda incerta, essa celula passa a ser
        tratada como perigo confirmado.
        """
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
        """Remove o ouro conhecido de uma posicao coletada.

        Tambem atualiza o contador interno de ouros carregados, usado na regra
        de retorno e saida.
        """
        self.gold_seen.discard(pos)
        self.gold_carried += 1

    def mark_powerup_taken(self, pos: Position) -> None:
        """Remove o powerup conhecido de uma posicao coletada.

        Isso impede que a KB continue perseguindo um item que ja foi consumido.
        """
        self.powerup_seen.discard(pos)

    def likely_safe(self, pos: Position) -> bool:
        """Verifica se a celula e tratada como segura pela KB.

        Uma celula e segura quando ja foi confirmada como tal ou quando nao ha
        qualquer evidencia restante de poco, inimigo ou teletransporte nela.
        """
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
        """Indica se a celula ja foi visitada pelo agente."""
        return pos in self.visited

    def is_known_gold(self, pos: Position) -> bool:
        """Indica se a KB sabe que existe ouro nessa celula."""
        return pos in self.gold_seen

    def is_risky(self, pos: Position) -> bool:
        """Indica se a celula ainda tem risco relevante.

        Essa verificacao e usada para evitar movimentos que contradigam as
        suspeitas atuais da base de conhecimento.
        """
        if pos in self.certeza:
            return False
        if pos in self.confirmed_pit or pos in self.confirmed_enemy or pos in self.confirmed_teleport:
            return True
        obs = self.memory.get(pos, frozenset())
        return bool(obs & {"brisa", "passos", "palmas"})

    def safe_unvisited_frontier(self) -> list[Position]:
        """Lista as celulas seguras ainda nao visitadas.

        Essa fronteira e a principal materia-prima da exploracao prudente.
        """
        return [
            (r, c)
            for r in range(1, self.size + 1)
            for c in range(1, self.size + 1)
            if self.likely_safe((r, c)) and (r, c) not in self.visited
        ]

    def decide(self) -> tuple[str, Optional[Position]]:
        """Escolhe a proxima meta com base no estado conhecido.

        A ordem das regras tenta ser simples de explicar: primeiro coletar o
        que esta na celula atual, depois buscar objetivos claramente vantajosos
        e, por fim, explorar ou recuar quando nao houver opcao melhor.
        """
        pos = self.agent_pos
        if pos in self.gold_seen:
            return "pegar", None
        if (
            pos in self.powerup_seen
            and self.agent_energy <= INITIAL_ENERGY - POWERUP_ENERGY_GAIN
        ):
            return "pegar", None
        if pos == self.exit_pos and self.gold_carried >= GOLD_TARGET:
            return "sair", None
        for g in self.gold_seen:
            if g != pos and self.likely_safe(g):
                return "mover", g
        if self.agent_energy <= self._energy_low:
            reachable = [
                p for p in self.powerup_seen
                if p != pos and self.likely_safe(p)
            ]
            if reachable:
                target = min(reachable,
                             key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
                return "mover", target

        frontier = self.safe_unvisited_frontier()
        if frontier:
            target = min(frontier,
                         key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
            return "mover", target

        risky = self.risky_frontier()
        if risky:
            target = min(risky,
                         key=lambda p: (self.risk_score(p),
                                        abs(p[0]-pos[0]) + abs(p[1]-pos[1])))
            return "mover", target

        if pos != self.exit_pos:
            return "mover", self.exit_pos

        return "sair", None

    def risky_frontier(self) -> list[Position]:
        """Lista a fronteira desconhecida que ainda envolve risco.

        Essas celulas sao vizinhas da area conhecida, mas ainda carregam sinais
        suficientes para exigir cautela.
        """
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
        """Calcula um peso simples para comparar riscos.

        O valor nao precisa ser matematicamente perfeito; ele serve apenas como
        criterio de desempate para escolher o menor mal quando nao ha caminho
        claramente seguro.
        """
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
        """Conta quantos sinais observados apontam para a celula.

        Quanto mais fontes apontam para o mesmo lugar, maior tende a ser a
        suspeita associada a essa posicao.
        """
        return sum(1 for src in sources if pos in orthogonal_neighbors(src, self.size))

    def _confirmed_any(self, pos: Position) -> bool:
        """Indica se a celula ja foi confirmada como algum perigo.

        Esse helper existe principalmente para deixar outras verificacoes mais
        legiveis.
        """
        return (
            pos in self.confirmed_pit
            or pos in self.confirmed_enemy
            or pos in self.confirmed_teleport
        )

    def _valid(self, pos: Position) -> bool:
        """Valida se a posicao esta dentro do tabuleiro.

        A KB usa isso antes de qualquer inferencia que dependa de coordenadas.
        """
        r, c = pos
        return 1 <= r <= self.size and 1 <= c <= self.size

    def snapshot(self) -> dict:
        """Gera um resumo da KB para debug e interface.

        O snapshot e usado pela GUI e pela renderizacao textual para mostrar o
        que o agente sabe, suspeita ou confirmou ate o momento.
        """
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
