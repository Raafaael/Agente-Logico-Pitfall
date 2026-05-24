"""Small search-tree node used by the grid planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import Position


@dataclass(slots=True)
class TreeNode:
    """Node for A*/best-first searches over grid positions."""

    position: Position
    parent: Optional["TreeNode"] = None
    g: int = 0
    h: int = 0

    @property
    def f(self) -> int:
        return self.g + self.h

    def path(self) -> list[Position]:
        node: Optional[TreeNode] = self
        out: list[Position] = []
        while node is not None:
            out.append(node.position)
            node = node.parent
        out.reverse()
        return out