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

from .types import GOLD_TARGET, GRID_SIZE, Position, orthogonal_neighbors


@dataclass
class PythonKB:
    size: int = GRID_SIZE
    visited: set[Position] = field(default_factory=set)
    confirmed_safe: set[Position] = field(default_factory=set)
    risk_pit: set[Position] = field(default_factory=set)
    risk_enemy: set[Position] = field(default_factory=set)
    risk_teleport: set[Position] = field(default_factory=set)
    confirmed_pit: set[Position] = field(default_factory=set)
    confirmed_enemy: set[Position] = field(default_factory=set)
    confirmed_teleport: set[Position] = field(default_factory=set)
    pit_clear: set[Position] = field(default_factory=set)
    enemy_clear: set[Position] = field(default_factory=set)
    tele_clear: set[Position] = field(default_factory=set)
    breeze_at: set[Position] = field(default_factory=set)
    steps_at: set[Position] = field(default_factory=set)
    flash_at: set[Position] = field(default_factory=set)
    gold_seen: set[Position] = field(default_factory=set)
    agent_pos: Position = (1, 1)
    exit_pos: Position = (1, 1)
    gold_carried: int = 0

    backend: str = "python"

    def reset(self) -> None:
        for s in (
            self.visited, self.confirmed_safe,
            self.risk_pit, self.risk_enemy, self.risk_teleport,
            self.confirmed_pit, self.confirmed_enemy, self.confirmed_teleport,
            self.pit_clear, self.enemy_clear, self.tele_clear,
            self.breeze_at, self.steps_at, self.flash_at,
            self.gold_seen,
        ):
            s.clear()
        self.agent_pos = self.exit_pos
        self.gold_carried = 0

    def set_exit(self, pos: Position) -> None:
        self.exit_pos = pos

    def set_agent_pos(self, pos: Position) -> None:
        self.agent_pos = pos

    def update_perception(self, pos: Position, percepts: list[str]) -> None:
        self.visited.add(pos)
        self.confirmed_safe.add(pos)
        for s in (self.risk_pit, self.risk_enemy, self.risk_teleport):
            s.discard(pos)
        # We're alive in `pos` so all hazard checks are cleared for it.
        self.pit_clear.add(pos)
        self.enemy_clear.add(pos)
        self.tele_clear.add(pos)

        neighbors = orthogonal_neighbors(pos, self.size)

        self._remember_signal(pos, "breeze" in percepts, self.breeze_at)
        self._remember_signal(pos, "steps" in percepts, self.steps_at)
        self._remember_signal(pos, "flash" in percepts, self.flash_at)

        self._apply_perception(neighbors,
                               present="breeze" in percepts,
                               clear_set=self.pit_clear,
                               risk_set=self.risk_pit,
                               confirmed_set=self.confirmed_pit)
        self._apply_perception(neighbors,
                               present="steps" in percepts,
                               clear_set=self.enemy_clear,
                               risk_set=self.risk_enemy,
                               confirmed_set=self.confirmed_enemy)
        self._apply_perception(neighbors,
                               present="flash" in percepts,
                               clear_set=self.tele_clear,
                               risk_set=self.risk_teleport,
                               confirmed_set=self.confirmed_teleport)

        if "glow" in percepts:
            self.gold_seen.add(pos)
        else:
            self.gold_seen.discard(pos)

        self._infer_confirmed_hazards()

    def _remember_signal(self, pos: Position, present: bool,
                         store: set[Position]) -> None:
        if present:
            store.add(pos)
        else:
            store.discard(pos)

    def _apply_perception(
        self,
        neighbors: list[Position],
        present: bool,
        clear_set: set[Position],
        risk_set: set[Position],
        confirmed_set: set[Position],
    ) -> None:
        if present:
            for n in neighbors:
                # Already deduced safe from a previous neighbor observation:
                # don't downgrade it back to risky.
                if (
                    n not in clear_set
                    and n not in self.confirmed_safe
                    and n not in self.visited
                ):
                    risk_set.add(n)
        else:
            # No hazard sensed -> all neighbors are positively cleared
            # for this hazard.
            for n in neighbors:
                clear_set.add(n)
                risk_set.discard(n)
                confirmed_set.discard(n)

    def _infer_confirmed_hazards(self) -> None:
        changed = True
        while changed:
            changed = False
            for sensed, clear, risk, confirmed in (
                (self.breeze_at, self.pit_clear, self.risk_pit, self.confirmed_pit),
                (self.steps_at, self.enemy_clear, self.risk_enemy, self.confirmed_enemy),
                (
                    self.flash_at,
                    self.tele_clear,
                    self.risk_teleport,
                    self.confirmed_teleport,
                ),
            ):
                for source in tuple(sensed):
                    candidates = [
                        n for n in orthogonal_neighbors(source, self.size)
                        if self._hazard_candidate(n, clear, confirmed)
                    ]
                    if len(candidates) == 1:
                        target = candidates[0]
                        if target not in confirmed:
                            confirmed.add(target)
                            risk.add(target)
                            clear.discard(target)
                            changed = True

    def _hazard_candidate(
        self,
        pos: Position,
        clear_set: set[Position],
        confirmed_set: set[Position],
    ) -> bool:
        if not self._valid(pos):
            return False
        if pos in clear_set or pos in self.visited or pos in self.confirmed_safe:
            return False
        if self._confirmed_any(pos) and pos not in confirmed_set:
            return False
        return True

    def mark_gold_taken(self, pos: Position) -> None:
        self.gold_seen.discard(pos)
        self.gold_carried += 1

    def likely_safe(self, pos: Position) -> bool:
        if self._confirmed_any(pos):
            return False
        if pos in self.confirmed_safe:
            return True
        if not self._valid(pos):
            return False
        return (
            pos in self.pit_clear
            and pos in self.enemy_clear
            and pos in self.tele_clear
        )

    def is_visited(self, pos: Position) -> bool:
        return pos in self.visited

    def is_known_gold(self, pos: Position) -> bool:
        return pos in self.gold_seen

    def is_risky(self, pos: Position) -> bool:
        if pos in self.confirmed_safe:
            return False
        return (
            pos in self.risk_pit
            or pos in self.risk_enemy
            or pos in self.risk_teleport
            or self._confirmed_any(pos)
        )

    def safe_unvisited_frontier(self) -> list[Position]:
        out = []
        for r in range(1, self.size + 1):
            for c in range(1, self.size + 1):
                p = (r, c)
                if self.likely_safe(p) and p not in self.visited:
                    out.append(p)
        return out

    def decide(self) -> tuple[str, Optional[Position]]:
        """Return (kind, target) where kind in {pegar, sair, mover}.

        Mirrors the Prolog rules in :file:`knowledge_base.pl`.
        """
        pos = self.agent_pos

        if pos in self.gold_seen:
            return "pegar", None

        if pos == self.exit_pos and self.gold_carried >= GOLD_TARGET:
            return "sair", None

        # Prefer reachable known gold over unknown frontiers.
        for g in self.gold_seen:
            if g != pos and self.likely_safe(g):
                return "mover", g

        frontier = self.safe_unvisited_frontier()
        if frontier:
            target = min(
                frontier,
                key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]),
            )
            return "mover", target

        risky = self.risky_frontier()
        if risky:
            target = min(
                risky,
                key=lambda p: (
                    self.risk_score(p),
                    abs(p[0] - pos[0]) + abs(p[1] - pos[1]),
                ),
            )
            return "mover", target

        if pos != self.exit_pos:
            return "mover", self.exit_pos

        return "sair", None

    def risky_frontier(self) -> list[Position]:
        out: set[Position] = set()
        for seen in self.visited | self.confirmed_safe:
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
        if pos in self.confirmed_enemy:
            score += 80
        if pos in self.confirmed_teleport:
            score += 260
        if pos in self.risk_enemy:
            score += 60 + 30 * self._source_count(pos, self.steps_at)
        if pos in self.risk_teleport:
            score += 180 + 60 * self._source_count(pos, self.flash_at)
        if pos in self.risk_pit:
            score += 900 + 120 * self._source_count(pos, self.breeze_at)
        if not self.is_risky(pos):
            score += 40
        return score

    def _source_count(self, pos: Position, sources: set[Position]) -> int:
        return sum(1 for source in sources if pos in orthogonal_neighbors(source, self.size))

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
        """Useful for debugging/rendering."""
        safe = [
            (r, c)
            for r in range(1, self.size + 1)
            for c in range(1, self.size + 1)
            if self.likely_safe((r, c))
        ]
        return {
            "visited": sorted(self.visited),
            "safe": sorted(safe),
            "risk_pit": sorted(self.risk_pit),
            "risk_enemy": sorted(self.risk_enemy),
            "risk_teleport": sorted(self.risk_teleport),
            "confirmed_pit": sorted(self.confirmed_pit),
            "confirmed_enemy": sorted(self.confirmed_enemy),
            "confirmed_teleport": sorted(self.confirmed_teleport),
            "risky_frontier": self.risky_frontier(),
            "gold_seen": sorted(self.gold_seen),
            "gold_carried": self.gold_carried,
        }
