"""Environment: holds the ground-truth map and produces percepts.

The Agent must NEVER read attributes of this object that reveal the map. The
public surface for the agent is :py:meth:`Environment.step` (which returns a
:class:`StepResult` with only sensor information) and :py:attr:`Environment.size`.
"""
from __future__ import annotations

import random
from typing import Optional

from .map_loader import Grid, all_positions, get_cell, set_cell
from .types import (
    ACTION_COST,
    Action,
    CellType,
    DAMAGE_BIG,
    DAMAGE_SMALL,
    DEATH_PENALTY,
    Direction,
    GOLD_REWARD,
    INITIAL_ENERGY,
    PIT_PENALTY,
    POWERUP_ENERGY_GAIN,
    Percept,
    Position,
    START_POS,
    StepResult,
    WALK_ENERGY_COST,
    in_bounds,
    orthogonal_neighbors,
)


class Environment:
    """Ground-truth game world. Owns the grid and applies actions."""

    def __init__(
        self,
        grid: Grid,
        start: Position = START_POS,
        initial_direction: Direction = Direction.EAST,
        initial_energy: int = INITIAL_ENERGY,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._grid = [row[:] for row in grid]
        self.size = len(grid)
        self.start_pos: Position = start
        self.agent_pos: Position = start
        self.agent_dir: Direction = initial_direction
        self.energy: int = initial_energy
        self.score: int = 0
        self.steps: int = 0
        self.gold_collected: int = 0
        self.powerups_taken: int = 0
        self.alive: bool = True
        self.escaped: bool = False
        self._last_impact: bool = False
        self._last_scream: bool = False
        self._rng = rng or random.Random()
        if get_cell(self._grid, start) != CellType.EMPTY:
            raise ValueError("Starting cell must be EMPTY")

    @property
    def game_over(self) -> bool:
        return not self.alive or self.escaped

    def get_percept(self) -> Percept:
        """Compute the percepts the agent senses at its current position."""
        pos = self.agent_pos
        cell = get_cell(self._grid, pos)
        breeze = steps = flash = False
        for n in orthogonal_neighbors(pos, self.size):
            nc = get_cell(self._grid, n)
            if nc == CellType.PIT:
                breeze = True
            if nc in (CellType.ENEMY_SMALL, CellType.ENEMY_BIG):
                steps = True
            if nc == CellType.TELEPORTER:
                flash = True
        glow = cell == CellType.GOLD
        powerup = cell == CellType.POWERUP
        return Percept(
            steps=steps,
            breeze=breeze,
            flash=flash,
            glow=glow,
            powerup=powerup,
            impact=self._last_impact,
            scream=self._last_scream,
        )

    def step(self, action: Action) -> StepResult:
        """Apply an action, mutate state and return a result."""
        if self.game_over:
            return StepResult(
                percept=self.get_percept(),
                score_delta=0,
                energy_delta=0,
                alive=self.alive,
                escaped=self.escaped,
                message="game already over",
            )

        self._last_impact = False
        self._last_scream = False
        score_delta = ACTION_COST
        energy_delta = 0
        teleported = False
        picked: Optional[str] = None
        message = ""

        if action == Action.TURN_LEFT:
            self.agent_dir = self.agent_dir.turn_left()
            message = f"virou para esquerda -> {self.agent_dir.short}"

        elif action == Action.TURN_RIGHT:
            self.agent_dir = self.agent_dir.turn_right()
            message = f"virou para direita -> {self.agent_dir.short}"

        elif action == Action.WALK:
            energy_delta += WALK_ENERGY_COST
            dr, dc = self.agent_dir.delta
            target = (self.agent_pos[0] + dr, self.agent_pos[1] + dc)
            if not in_bounds(target, self.size):
                self._last_impact = True
                message = "impacto contra parede"
            else:
                self.agent_pos = target
                event = self._enter_cell(target)
                score_delta += event["score"]
                energy_delta += event["energy"]
                teleported = event["teleported"]
                picked = event["picked"]
                message = event["message"]

        elif action == Action.GRAB:
            cell = get_cell(self._grid, self.agent_pos)
            if cell == CellType.GOLD:
                set_cell(self._grid, self.agent_pos, CellType.EMPTY)
                self.gold_collected += 1
                score_delta += GOLD_REWARD
                picked = "gold"
                message = f"ouro coletado (#{self.gold_collected})"
            elif cell == CellType.POWERUP:
                set_cell(self._grid, self.agent_pos, CellType.EMPTY)
                self.powerups_taken += 1
                energy_delta += POWERUP_ENERGY_GAIN
                picked = "powerup"
                message = f"powerup: +{POWERUP_ENERGY_GAIN} energia"
            else:
                message = "nada para pegar"

        elif action == Action.EXIT:
            if self.agent_pos == self.start_pos:
                self.escaped = True
                message = "saiu do labirinto"
            else:
                message = "fora da saida; nada acontece"

        else:
            raise ValueError(f"Unknown action: {action!r}")

        self.score += score_delta
        self.energy += energy_delta
        self.steps += 1

        if self.energy <= 0 and self.alive and not self.escaped:
            self.alive = False
            self.score += DEATH_PENALTY
            score_delta += DEATH_PENALTY
            message += " | morreu por exaustao"

        return StepResult(
            percept=self.get_percept(),
            score_delta=score_delta,
            energy_delta=energy_delta,
            alive=self.alive,
            escaped=self.escaped,
            teleported=teleported,
            picked=picked,
            message=message,
        )

    def _enter_cell(self, pos: Position, depth: int = 0) -> dict:
        result = {
            "score": 0,
            "energy": 0,
            "teleported": False,
            "picked": None,
            "message": "",
        }
        cell = get_cell(self._grid, pos)

        if cell == CellType.PIT:
            self.alive = False
            result["score"] += PIT_PENALTY
            result["message"] = "caiu em poco/obstaculo"
            return result

        if cell == CellType.ENEMY_SMALL:
            result["energy"] -= DAMAGE_SMALL
            result["score"] -= DAMAGE_SMALL
            result["message"] = (
                f"atingido por inimigo pequeno (-{DAMAGE_SMALL} energia/score)"
            )
            return result

        if cell == CellType.ENEMY_BIG:
            result["energy"] -= DAMAGE_BIG
            result["score"] -= DAMAGE_BIG
            result["message"] = (
                f"atingido por inimigo grande (-{DAMAGE_BIG} energia/score)"
            )
            return result

        if cell == CellType.TELEPORTER:
            result["teleported"] = True
            if depth >= self.size * self.size:
                result["message"] = "teletransporte em cadeia interrompido"
                return result
            destinations = [p for p in all_positions(self.size) if p != self.agent_pos]
            new_pos = self._rng.choice(destinations)
            self.agent_pos = new_pos
            inner = self._enter_cell(new_pos, depth + 1)
            result["score"] += inner["score"]
            result["energy"] += inner["energy"]
            result["picked"] = inner["picked"]
            result["message"] = (
                f"teleportado para {new_pos}; {inner['message']}".strip("; ")
            )
            return result

        if cell == CellType.POWERUP:
            result["message"] = "sala com powerup"
            return result

        result["message"] = "sala vazia"
        return result

    def reveal_grid(self) -> Grid:
        """Returns a deep copy of the underlying grid (for rendering/debug only)."""
        return [row[:] for row in self._grid]
