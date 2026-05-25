"""A* path planning over the agent's known-safe cells."""
from __future__ import annotations

import heapq
from typing import Callable, Iterable, Optional

from .TreeNode import TreeNode
from .types import Action, Direction, GRID_SIZE, Position, orthogonal_neighbors


def manhattan(a: Position, b: Position) -> int:
    """Calcula a distancia Manhattan entre duas posicoes.

    Essa heuristica considera apenas movimentos ortogonais, que sao exatamente
    os movimentos permitidos no tabuleiro. Por isso ela funciona bem como
    estimativa para o A*: e simples, barata de calcular e nunca superestima o
    custo minimo real entre duas celulas.
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(
    start: Position,
    goal: Position,
    is_walkable: Callable[[Position], bool],
    size: int = GRID_SIZE,
) -> Optional[list[Position]]:
    """Busca um caminho entre duas posicoes usando A*.

    A funcao recebe uma posicao inicial, uma meta e um predicado `is_walkable`
    que informa se uma celula pode ser usada no planejamento. O retorno e uma
    lista de posicoes, incluindo origem e destino, ou `None` quando nao existe
    caminho viavel.

    O objetivo do codigo aqui e manter o planejador separado da logica do
    agente: ele apenas calcula trajetos, sem decidir se vale a pena correr um
    risco ou se e melhor voltar para a saida.
    """
    if start == goal:
        return [start]

    open_heap: list[tuple[int, int, TreeNode]] = []
    counter = 0
    start_node = TreeNode(start, g=0, h=manhattan(start, goal))
    heapq.heappush(open_heap, (start_node.f, counter, start_node))
    g_score: dict[Position, int] = {start: 0}

    while open_heap:
        _, _, node = heapq.heappop(open_heap)
        current = node.position
        if current == goal:
            return node.path()

        for nb in orthogonal_neighbors(current, size):
            if nb != goal and not is_walkable(nb):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nb, 10**9):
                g_score[nb] = tentative
                counter += 1
                child = TreeNode(
                    nb,
                    parent=node,
                    g=tentative,
                    h=manhattan(nb, goal),
                )
                heapq.heappush(
                    open_heap, (child.f, counter, child)
                )

    return None


def path_to_actions(
    path: Iterable[Position],
    initial_dir: Direction,
) -> list[Action]:
    """Converte um caminho em acoes de giro e movimento.

    O agente nao executa "teletransportes" de uma celula para outra: ele
    precisa alinhar a orientacao e depois andar. Por isso, esta funcao traduz
    um caminho geometrico em uma sequencia concreta de acoes de baixo nivel
    que o ambiente entende.
    """
    path = list(path)
    if len(path) < 2:
        return []

    actions: list[Action] = []
    cur_dir = initial_dir
    for a, b in zip(path, path[1:]):
        delta = (b[0] - a[0], b[1] - a[1])
        target_dir = Direction.from_delta(delta)
        actions.extend(_align_actions(cur_dir, target_dir))
        actions.append(Action.WALK)
        cur_dir = target_dir
    return actions


def _align_actions(cur: Direction, target: Direction) -> list[Action]:
    """Gera os giros necessarios para alinhar a orientacao.

    Sempre que possivel, a funcao escolhe a menor quantidade de giros. No caso
    de meia-volta, ela usa duas rotacoes para a direita por simplicidade e
    previsibilidade no comportamento do agente.
    """
    if cur == target:
        return []
    order = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
    delta = (order.index(target) - order.index(cur)) % 4
    if delta == 1:
        return [Action.TURN_RIGHT]
    if delta == 3:
        return [Action.TURN_LEFT]
    return [Action.TURN_LEFT, Action.TURN_LEFT]
