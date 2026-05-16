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

Decision policy adds three pragmatic layers on top of the logical core:
    1. If the next-best frontier is a likely pit and we are already
       carrying gold, retreat to the exit instead of gambling.
    2. If energy is low and a known powerup is reachable through safe
       cells, prefer the powerup over deeper exploration.
    3. Frontier ranking prefers cells with more unvisited neighbors
       (higher information gain) as a tie-breaker after risk.
"""
from __future__ import annotations

from collections import deque
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
    powerup_seen: set[Position] = field(default_factory=set)
    agent_pos: Position = (1, 1)
    exit_pos: Position = (1, 1)
    gold_carried: int = 0
    energy: int = 100

    backend: str = "python"

    def reset(self) -> None:
        for s in (
            self.visited, self.confirmed_safe,
            self.risk_pit, self.risk_enemy, self.risk_teleport,
            self.confirmed_pit, self.confirmed_enemy, self.confirmed_teleport,
            self.pit_clear, self.enemy_clear, self.tele_clear,
            self.breeze_at, self.steps_at, self.flash_at,
            self.gold_seen, self.powerup_seen,
        ):
            s.clear()
        self.agent_pos = self.exit_pos
        self.gold_carried = 0
        self.energy = 100

    def set_energy(self, energy: int) -> None:
        self.energy = energy

    def note_powerup_taken(self, pos: Position) -> None:
        self.powerup_seen.discard(pos)

    def set_exit(self, pos: Position) -> None:
        self.exit_pos = pos

    def set_agent_pos(self, pos: Position) -> None:
        self.agent_pos = pos

    def update_perception(self, pos: Position, percepts: list[str]) -> None:
        self.visited.add(pos)
        self.confirmed_safe.add(pos)
        for s in (self.risk_pit, self.risk_enemy, self.risk_teleport):
            s.discard(pos)
        # We're alive in `pos` so a pit is impossible here. We are also not
        # being yanked, so this cell cannot be a teleporter. (We may still
        # have stepped on an enemy and taken damage -- keep ``confirmed_enemy``
        # untouched so we can avoid the cell next time it is optional.)
        self.pit_clear.add(pos)
        self.enemy_clear.add(pos)
        self.tele_clear.add(pos)
        self.confirmed_pit.discard(pos)
        self.confirmed_teleport.discard(pos)

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

    def note_powerup_at(self, pos: Position) -> None:
        if pos in self.visited and pos not in self.powerup_seen:
            return
        self.powerup_seen.add(pos)

    def note_enemy_here(self, pos: Position) -> None:
        """Record that the agent took damage entering ``pos`` -- there is an
        enemy in this exact cell. The cell remains visited (we are standing
        in it), but it should no longer be picked as a transit-cell when a
        less-painful path exists."""
        self.confirmed_enemy.add(pos)
        self.enemy_clear.discard(pos)
        self.risk_enemy.discard(pos)

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

    def walkable_for_path(self, pos: Position) -> bool:
        """Looser than :meth:`likely_safe`: a visited cell can be retraversed
        even if it now turns out to host an enemy (we will take damage but the
        cell is not a one-way trap). Used when the agent has to come home
        through a known-hostile corridor."""
        if not self._valid(pos):
            return False
        if pos in self.visited:
            return True
        return self.likely_safe(pos)

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

        Mirrors the Prolog rules in :file:`knowledge_base.pl`, plus the
        pragmatic layers described in the module docstring.
        """
        pos = self.agent_pos

        if pos in self.gold_seen:
            return "pegar", None

        if pos in self.powerup_seen and self.energy <= 60:
            return "pegar", None

        if pos == self.exit_pos and self.gold_carried >= GOLD_TARGET:
            return "sair", None

        # 1) Already-known gold reachable through safe cells -> go grab it.
        gold_target = self._best_safe_target(self.gold_seen)
        if gold_target is not None:
            return "mover", gold_target

        # 2) Low energy + known reachable powerup -> stock up.
        if self.energy <= 50:
            pu_target = self._best_safe_target(self.powerup_seen)
            if pu_target is not None:
                return "mover", pu_target

        # 3) Expand the safe frontier (rank by path distance, then info gain).
        #    Cells with no likely_safe path from the agent are dropped: picking
        #    them would force the planner into a hostile retrace.
        frontier = [
            p for p in self.safe_unvisited_frontier()
            if self._safe_path_distance(p) != float("inf")
        ]
        if frontier:
            target = min(
                frontier,
                key=lambda p: (
                    self._safe_path_distance(p),
                    -self._info_gain(p),
                ),
            )
            return "mover", target

        # 4) Forced into the risky frontier: bail if it is too costly given
        #    the gold we already carry.
        risky = self.risky_frontier()
        if risky:
            best = min(
                risky,
                key=lambda p: (
                    self.risk_score(p),
                    -self._info_gain(p),
                    abs(p[0] - pos[0]) + abs(p[1] - pos[1]),
                ),
            )
            if self._should_retreat(best):
                if pos == self.exit_pos:
                    return "sair", None
                return "mover", self.exit_pos
            return "mover", best

        if pos != self.exit_pos:
            return "mover", self.exit_pos

        return "sair", None

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _best_safe_target(self, candidates: set[Position]) -> Optional[Position]:
        reachable: list[tuple[int, Position]] = []
        for cell in candidates:
            if cell == self.agent_pos:
                continue
            if not self.likely_safe(cell):
                continue
            dist = self._safe_path_distance(cell)
            if dist == float("inf"):
                continue
            reachable.append((dist, cell))
        if not reachable:
            return None
        reachable.sort()
        return reachable[0][1]

    def _info_gain(self, pos: Position) -> int:
        """How many unknown neighbors a candidate would let us probe."""
        return sum(
            1 for n in orthogonal_neighbors(pos, self.size)
            if n not in self.visited and n not in self.confirmed_safe
        )

    def _safe_path_distance(self, goal: Position) -> float:
        """BFS distance over known-safe cells; the goal itself is allowed
        even if it is only on the frontier (not yet visited)."""
        start = self.agent_pos
        if start == goal:
            return 0
        seen = {start}
        queue: deque[tuple[Position, int]] = deque([(start, 0)])
        while queue:
            cur, d = queue.popleft()
            for nb in orthogonal_neighbors(cur, self.size):
                if nb in seen:
                    continue
                if nb == goal:
                    return d + 1
                if not self.likely_safe(nb):
                    continue
                seen.add(nb)
                queue.append((nb, d + 1))
        return float("inf")

    def _should_retreat(self, candidate: Position) -> bool:
        """Decide whether stepping into ``candidate`` is worse than going home.

        Heuristic:
          - Confirmed pit -> always retreat (we'd die for sure).
          - Multiple breeze sources point at this cell -> a real pit is far
            more likely than a coincidence, retreat even before single-source
            inference fires.
          - Already carrying gold and best forward step is any pit/teleport
            risk -> the score in hand beats the gamble.
        Pure ``risk_enemy`` steps are kept on the table: damage is finite
        and survivable, and rejecting them paralyses exploration.
        """
        if not self._can_reach_exit():
            return False
        if candidate in self.confirmed_pit:
            return True
        if (
            candidate in self.risk_pit
            and self._source_count(candidate, self.breeze_at) >= 2
        ):
            return True
        if self.gold_carried > 0 and (
            candidate in self.risk_pit
            or candidate in self.confirmed_teleport
        ):
            return True
        return False

    def _can_reach_exit(self) -> bool:
        if self.agent_pos == self.exit_pos:
            return True
        if self._safe_path_distance(self.exit_pos) != float("inf"):
            return True
        # Relax to retraceable cells (visited but maybe hostile): an agent
        # who walked in can always crawl back.
        start = self.agent_pos
        seen = {start}
        queue: deque[Position] = deque([start])
        while queue:
            cur = queue.popleft()
            for nb in orthogonal_neighbors(cur, self.size):
                if nb in seen:
                    continue
                if nb == self.exit_pos:
                    return True
                if not self.walkable_for_path(nb):
                    continue
                seen.add(nb)
                queue.append(nb)
        return False

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
            "powerup_seen": sorted(self.powerup_seen),
            "gold_carried": self.gold_carried,
            "energy": self.energy,
        }
