"""Core enums, dataclasses and constants used across the project."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


GRID_SIZE = 12
START_POS: "Position" = (1, 1)
INITIAL_ENERGY = 100

ACTION_COST = -1
GOLD_REWARD = 1000
PIT_PENALTY = -1000
DEATH_PENALTY = -1000
POWERUP_ENERGY_GAIN = 20

DAMAGE_SMALL = 20
DAMAGE_BIG = 50

# Used by the random map generator, not by the agent or knowledge bases.
DEFAULT_MAP_COUNTS = {
    "enemy_small": 2,
    "enemy_big": 2,
    "teleporter": 4,
    "pit": 8,
    "gold": 3,
    "powerup": 3,
}
REQUIRED_GOLD = 3
LOW_ENERGY_RETURN = 60
CRITICAL_ENERGY_RETURN = 25


Position = Tuple[int, int]


class CellType(str, Enum):
    EMPTY = "empty"
    PIT = "pit"
    ENEMY_SMALL = "enemy_small"
    ENEMY_BIG = "enemy_big"
    TELEPORTER = "teleporter"
    GOLD = "gold"
    POWERUP = "powerup"

    @classmethod
    def from_symbol(cls, sym: str) -> "CellType":
        # Primary symbols match the teacher's reference (legacy/main.pl):
        # P=pit, d=small enemy, D=big enemy, T=teleporter, O=gold, U=powerup.
        # Aliases (e/E/G/+) are accepted to keep older test fixtures compatible.
        mapping = {
            ".": cls.EMPTY, "S": cls.EMPTY, " ": cls.EMPTY, "": cls.EMPTY,
            "P": cls.PIT,
            "d": cls.ENEMY_SMALL, "e": cls.ENEMY_SMALL,
            "D": cls.ENEMY_BIG,   "E": cls.ENEMY_BIG,
            "T": cls.TELEPORTER,
            "O": cls.GOLD,        "G": cls.GOLD,
            "U": cls.POWERUP,     "+": cls.POWERUP,
        }
        if sym not in mapping:
            raise ValueError(f"Unknown cell symbol: {sym!r}")
        return mapping[sym]

    @property
    def symbol(self) -> str:
        return {
            CellType.EMPTY: ".",
            CellType.PIT: "P",
            CellType.ENEMY_SMALL: "d",
            CellType.ENEMY_BIG: "D",
            CellType.TELEPORTER: "T",
            CellType.GOLD: "O",
            CellType.POWERUP: "U",
        }[self]


class Direction(str, Enum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"

    @property
    def delta(self) -> Tuple[int, int]:
        return {
            Direction.NORTH: (-1, 0),
            Direction.EAST: (0, 1),
            Direction.SOUTH: (1, 0),
            Direction.WEST: (0, -1),
        }[self]

    def turn_right(self) -> "Direction":
        order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
        return order[(order.index(self) + 1) % 4]

    def turn_left(self) -> "Direction":
        order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
        return order[(order.index(self) - 1) % 4]

    @property
    def short(self) -> str:
        return {"north": "N", "east": "E", "south": "S", "west": "W"}[self.value]

    @property
    def pt(self) -> str:
        # Portuguese label, matching legacy/main.pl conventions.
        return {"north": "norte", "east": "leste",
                "south": "sul", "west": "oeste"}[self.value]

    @classmethod
    def from_delta(cls, delta: Tuple[int, int]) -> "Direction":
        for d in cls:
            if d.delta == delta:
                return d
        raise ValueError(f"No direction for delta {delta!r}")

    @classmethod
    def parse(cls, raw: str) -> "Direction":
        raw = raw.strip().lower()
        aliases = {
            "n": cls.NORTH, "north": cls.NORTH, "norte": cls.NORTH,
            "e": cls.EAST,  "east":  cls.EAST,  "leste": cls.EAST,
            "s": cls.SOUTH, "south": cls.SOUTH, "sul":   cls.SOUTH,
            "w": cls.WEST,  "west":  cls.WEST,  "oeste": cls.WEST,
        }
        if raw in aliases:
            return aliases[raw]
        return cls(raw)


class Action(str, Enum):
    WALK = "andar"
    TURN_LEFT = "virar_a_esquerda"
    TURN_RIGHT = "virar_a_direita"
    GRAB = "pegar"
    EXIT = "sair"


@dataclass
class Percept:
    steps: bool = False     # adjacente a inimigo (som de passos)
    breeze: bool = False    # adjacente a poco (brisa)
    flash: bool = False     # adjacente a teletransporte (flash)
    glow: bool = False      # ouro na sala atual (brilho)
    impact: bool = False    # andou contra a parede
    scream: bool = False    # reserved for future enemy-combat extensions

    def as_list(self) -> list[str]:
        return [k for k, v in self.__dict__.items() if v]

    def __str__(self) -> str:
        active = self.as_list()
        return ",".join(active) if active else "nenhuma"


@dataclass
class StepResult:
    percept: Percept
    score_delta: int
    energy_delta: int
    alive: bool
    escaped: bool
    teleported: bool = False
    picked: str | None = None
    message: str = ""


def in_bounds(pos: Position, size: int = GRID_SIZE) -> bool:
    r, c = pos
    return 1 <= r <= size and 1 <= c <= size


def orthogonal_neighbors(pos: Position, size: int = GRID_SIZE) -> list[Position]:
    r, c = pos
    out = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 1 <= nr <= size and 1 <= nc <= size:
            out.append((nr, nc))
    return out
