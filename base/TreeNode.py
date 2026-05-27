class TreeNode:

    coord = None        #tupla com as coordenadas
    priority = None     #priority é o f_x para busca heuristica (f_x = g_x + h_x), h_x é a distância heuristica que falta ao destino
    value_gx = None     #g_x é a distância percorrida da origem até o nó atual
    children = []
    parent = None

    def __init__(self, coord, fx, gx = None):
        self.coord = coord
        if gx == None: # se nao for busca heuristica
            self.priority = fx
            self.value_gx = fx
        else:
            self.priority = fx
            self.value_gx = gx

    def get_coord(self):
        return self.coord
    
    def get_priority(self):
        return self.priority
    
    def get_value_gx(self):
        return self.value_gx

    def set_parent(self, value):
        self.parent = value
    
    def get_parent(self):
        return self.parent

    def add_child(self,value):
        self.children.append(value)

    def remove_child(self, value):
        self.children.remove(value)

    def __lt__(self, other):
        return self.priority < other.priority