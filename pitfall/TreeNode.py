"""Small search-tree node used by the grid planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import Position


@dataclass(slots=True)
class TreeNode:
    """Representa um no da arvore de busca usada pelo planejador.

    Cada no guarda a posicao atual, uma referencia para o no pai e os custos
    usados pelo algoritmo A*. Isso permite reconstruir o caminho completo ao
    final da busca sem misturar essa responsabilidade com a funcao principal
    do planejador.
    """

    position: Position
    parent: Optional["TreeNode"] = None
    g: int = 0
    h: int = 0

    @property
    def f(self) -> int:
        """Retorna o custo total estimado do no.

        No A*, esse valor e a soma entre:
        - `g`: custo real ja percorrido ate o no atual;
        - `h`: heuristica que estima o custo restante ate o objetivo.
        """
        return self.g + self.h

    def path(self) -> list[Position]:
        """Reconstrui o caminho da raiz ate este no.

        O percurso e montado voltando pelos ponteiros `parent` ate a origem.
        Ao final, a lista e invertida para ficar na ordem natural de execucao:
        inicio, passos intermediarios e destino.
        """
        node: Optional[TreeNode] = self
        out: list[Position] = []
        while node is not None:
            out.append(node.position)
            node = node.parent
        out.reverse()
        return out
