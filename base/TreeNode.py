"""No auxiliar usado pela busca A* em ``gmap.py``.

O enunciado pede que a interface, o controle geral e o A* fiquem em Python,
enquanto a representacao de conhecimento e a tomada de decisao ficam em Prolog.
Esta classe pertence justamente a parte do A*: ela guarda uma casa do mapa, o
custo acumulado para chegar nela e uma referencia ao no anterior. Com isso, ao
encontrar o destino, o programa consegue reconstruir o caminho completo.
"""


class TreeNode:
    """Representa uma casa visitada pela busca heuristica.

    A busca A* trabalha com dois valores principais:

    - ``g(x)``: custo real ja percorrido desde a origem ate este no.
    - ``f(x)``: prioridade do no na fila, calculada como ``g(x) + h(x)``.

    No projeto, ``h(x)`` e a distancia Manhattan ate o alvo. Assim, o agente
    prefere caminhos curtos, mas ainda respeita as restricoes de seguranca que
    vieram da base de conhecimento em Prolog.
    """

    coord = None        # tupla (X, Y) com as coordenadas da casa no mapa
    priority = None     # valor f(x): prioridade usada pela fila do A*
    value_gx = None     # valor g(x): distancia ja percorrida desde a origem
    children = []
    parent = None

    def __init__(self, coord, fx, gx=None):
        """Cria um no de busca.

        ``coord`` e a posicao da casa. ``fx`` e a prioridade usada na fila. O
        parametro ``gx`` e opcional para manter compatibilidade com buscas que
        usam apenas um custo simples; no A* de ``gmap.py`` ele representa o custo
        real acumulado ate esta casa.
        """
        self.coord = coord
        if gx is None:
            self.priority = fx
            self.value_gx = fx
        else:
            self.priority = fx
            self.value_gx = gx

    def get_coord(self):
        """Retorna a coordenada ``(X, Y)`` associada ao no."""
        return self.coord

    def get_priority(self):
        """Retorna a prioridade ``f(x)`` usada pelo heap do A*."""
        return self.priority

    def get_value_gx(self):
        """Retorna o custo acumulado ``g(x)`` ate este no."""
        return self.value_gx

    def set_parent(self, value):
        """Define o no anterior no caminho encontrado pela busca."""
        self.parent = value

    def get_parent(self):
        """Retorna o no anterior usado para reconstruir o caminho."""
        return self.parent

    def add_child(self, value):
        """Adiciona um filho a lista auxiliar de filhos."""
        self.children.append(value)

    def remove_child(self, value):
        """Remove um filho da lista auxiliar de filhos."""
        self.children.remove(value)

    def __lt__(self, other):
        """Permite comparar nos pela prioridade dentro de filas ordenadas."""
        return self.priority < other.priority
