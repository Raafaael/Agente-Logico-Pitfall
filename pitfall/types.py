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

ELEMENT_COUNTS = {
    "enemy_small": 2,
    "enemy_big": 2,
    "teleporter": 4,
    "pit": 8,
    "gold": 3,
    "powerup": 3,
}
GOLD_TARGET = ELEMENT_COUNTS["gold"]
LOW_ENERGY_RETURN = 60
CRITICAL_ENERGY_RETURN = 25


Position = Tuple[int, int]


class CellType(str, Enum):
    """Enumera os tipos de celula que podem aparecer no labirinto."""

    EMPTY = "empty"
    PIT = "pit"
    ENEMY_SMALL = "enemy_small"
    ENEMY_BIG = "enemy_big"
    TELEPORTER = "teleporter"
    GOLD = "gold"
    POWERUP = "powerup"

    @classmethod
    def from_symbol(cls, sym: str) -> "CellType":
        """Converte o simbolo de um arquivo de mapa para o tipo interno."""
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
        """Retorna o simbolo usado ao salvar ou exibir este tipo de celula."""
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
    """Representa as quatro orientacoes possiveis do agente."""

    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"

    @property
    def delta(self) -> Tuple[int, int]:
        """Informa o deslocamento cartesiano produzido ao andar nessa direcao."""
        return {
            Direction.NORTH: (0, 1),
            Direction.EAST: (1, 0),
            Direction.SOUTH: (0, -1),
            Direction.WEST: (-1, 0),
        }[self]

    def turn_right(self) -> "Direction":
        """Retorna a direcao obtida ao girar 90 graus para a direita."""
        order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
        return order[(order.index(self) + 1) % 4]

    def turn_left(self) -> "Direction":
        """Retorna a direcao obtida ao girar 90 graus para a esquerda."""
        order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
        return order[(order.index(self) - 1) % 4]

    @property
    def short(self) -> str:
        """Fornece a abreviacao usada nos renderizadores de status."""
        return {"north": "N", "east": "E", "south": "S", "west": "W"}[self.value]

    @property
    def pt(self) -> str:
        """Fornece o nome em portugues usado em mapas legados."""
        # Portuguese label, matching legacy/main.pl conventions.
        return {"north": "norte", "east": "leste",
                "south": "sul", "west": "oeste"}[self.value]

    @classmethod
    def from_delta(cls, delta: Tuple[int, int]) -> "Direction":
        """Converte um deslocamento ortogonal em uma direcao."""
        for d in cls:
            if d.delta == delta:
                return d
        raise ValueError(f"No direction for delta {delta!r}")

    @classmethod
    def parse(cls, raw: str) -> "Direction":
        """Interpreta nomes e abreviacoes de direcao vindos de entrada externa."""
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
    """Define as acoes concretas aceitas pelo ambiente."""

    WALK = "andar"
    TURN_LEFT = "virar_a_esquerda"
    TURN_RIGHT = "virar_a_direita"
    GRAB = "pegar"
    EXIT = "sair"


@dataclass
class Percept:
    """Agrupa os sinais que o agente percebe na sala atual."""

    steps: bool = False     # adjacente a inimigo (som de passos)
    breeze: bool = False    # adjacente a poco (brisa)
    flash: bool = False     # adjacente a teletransporte (flash)
    glow: bool = False      # ouro na sala atual (brilho)
    powerup: bool = False   # powerup na sala atual (reflexo)
    impact: bool = False    # andou contra a parede
    scream: bool = False    # emitted when an enemy damages the agent

    def as_list(self) -> list[str]:
        """Retorna somente os nomes das percepcoes ativas."""
        return [k for k, v in self.__dict__.items() if v]

    def __str__(self) -> str:
        """Formata as percepcoes para exibicao em logs e status."""
        active = self.as_list()
        return ",".join(active) if active else "nenhuma"


@dataclass
class StepResult:
    """Descreve todos os efeitos observaveis apos uma acao do agente."""

    percept: Percept
    score_delta: int
    energy_delta: int
    alive: bool
    escaped: bool
    teleported: bool = False
    teleported_from: list[Position] = field(default_factory=list)
    picked: str | None = None
    message: str = ""


def in_bounds(pos: Position, size: int = GRID_SIZE) -> bool:
    """Verifica se uma coordenada esta dentro dos limites do tabuleiro."""
    x, y = pos
    return 1 <= x <= size and 1 <= y <= size


def orthogonal_neighbors(pos: Position, size: int = GRID_SIZE) -> list[Position]:
    """Lista os vizinhos ortogonais validos de uma posicao."""
    x, y = pos
    out = []
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nx, ny = x + dx, y + dy
        if 1 <= nx <= size and 1 <= ny <= size:
            out.append((nx, ny))
    return out
