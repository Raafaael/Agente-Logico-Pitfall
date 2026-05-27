################################################
import argparse
import heapq
import pathlib
import random
import sys
import time

from pyswip import Functor, Prolog, Query, Variable

from TreeNode import TreeNode


BASE_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
ASSETS_DIR = PROJECT_DIR / "assets"


def parse_args():
    parser = argparse.ArgumentParser(
        description="INF1771 Trabalho 2 - Agente logico Pitfall"
    )
    parser.add_argument(
        "--map",
        type=pathlib.Path,
        default=None,
        help="Arquivo .pl com fatos tile/3. Padrao: maps/mapa.pl.",
    )
    parser.add_argument(
        "--random-map",
        action="store_true",
        help="Gera um mapa aleatorio seguindo as quantidades do PDF.",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Desliga o autoplay para controle pelo teclado.",
    )
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--show-map", action="store_true")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa pelo terminal, sem abrir a janela grafica.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="Limite de acoes no modo headless.",
    )
    parser.add_argument("--trace", action="store_true")
    return parser.parse_known_args()[0]


args = parse_args()

elapsed_time = 0
auto_play_tempo = args.delay
auto_play = not args.manual
show_map = args.show_map

scale = 60
size_x = 12
size_y = 12
width = size_x * scale
height = size_y * scale

player_pos = (1, 1, "norte")
energia = 100
pontuacao = 0
ouros_coletados = 0

mapa = [
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
]

visitados = []
certezas = []

prolog = Prolog()
pl_file = str(BASE_DIR / "main.pl")
prolog.consult(pl_file)

last_action = ""
action_queue = []
blocked_cells = set()
unreachable_targets = set()
expected_walk_target = None
last_agent_cell = (1, 1)


def resolve_map_path(raw_path):
    if raw_path is not None:
        candidates = [
            raw_path,
            pathlib.Path.cwd() / raw_path,
            BASE_DIR / raw_path,
            PROJECT_DIR / raw_path,
        ]
    else:
        candidates = [
            BASE_DIR / "mapa.pl",
            PROJECT_DIR / "maps" / "mapa.pl",
        ]

    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Nao encontrei o arquivo de mapa .pl.")


def load_map_from_file():
    map_path = resolve_map_path(args.map)
    prolog.consult(str(map_path))
    print(f"[mapa] carregado: {map_path}")


def load_random_map():
    rng = random.Random(args.seed)
    elements = (
        ["P"] * 8
        + ["T"] * 4
        + ["D"] * 2
        + ["d"] * 2
        + ["O"] * 3
        + ["U"] * 3
    )
    positions = [(x, y) for x in range(1, 13) for y in range(1, 13) if (x, y) != (1, 1)]
    safe_first_step = rng.choice([(2, 1), (1, 2)])
    positions.remove(safe_first_step)
    rng.shuffle(positions)
    placement = dict(zip(positions, elements))

    list(prolog.query("retractall(tile(_,_,_))"))
    list(prolog.query("retractall(map_size(_,_))"))
    list(prolog.query("assertz(map_size(12,12))"))
    for y in range(1, 13):
        for x in range(1, 13):
            sym = placement.get((x, y), "")
            list(prolog.query(f"assertz(tile({x},{y},'{sym}'))"))
    print(f"[mapa] gerado aleatoriamente (seed={args.seed})")


if args.random_map:
    load_random_map()
else:
    load_map_from_file()

if args.seed is not None:
    list(prolog.query(f"set_random(seed({args.seed}))"))

list(prolog.query("reset_game"))


def atom(value):
    return str(value)


def alive():
    return player_pos[2] not in ("morto", "saiu")


def in_bounds(pos):
    x, y = pos
    return 1 <= x <= size_x and 1 <= y <= size_y


def neighbors(pos):
    x, y = pos
    out = []
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nb = (x + dx, y + dy)
        if in_bounds(nb):
            out.append(nb)
    return out


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def query_cells(predicate):
    cells = set()
    for sol in prolog.query(f"{predicate}(X,Y)"):
        cells.add((int(sol["X"]), int(sol["Y"])))
    return cells


def get_candidates():
    candidates = []
    for sol in prolog.query("meta_candidata(T,X,Y,C)"):
        candidates.append(
            (
                int(sol["C"]),
                atom(sol["T"]),
                int(sol["X"]),
                int(sol["Y"]),
            )
        )
    candidates.sort()
    return candidates


def current_memory():
    x, y = player_pos[0], player_pos[1]
    result = list(prolog.query(f"conteudo_memoria({x},{y},M)"))
    if not result:
        return []
    return [atom(value) for value in result[0]["M"]]


def escape_damage_action():
    if "passos" not in current_memory():
        return ""

    current = (player_pos[0], player_pos[1])
    safe_cells = query_cells("seguro")
    visited_cells = query_cells("visitado")
    confirmed_pits = query_cells("poco_confirmado")
    confirmed_enemies = query_cells("inimigo_confirmado")
    confirmed_teleports = query_cells("teleporte_confirmado")

    options = []
    for nb in neighbors(current):
        if nb in confirmed_pits or nb in confirmed_enemies or nb in confirmed_teleports:
            continue
        if nb in safe_cells:
            priority = 0
        elif nb in visited_cells:
            priority = 1
        else:
            priority = 2
        target_direction = direction_between(current, nb)
        turns = align_actions(player_pos[2], target_direction)
        options.append((priority, len(turns), manhattan(nb, (1, 1)), nb, turns))

    if not options:
        return ""

    _, _, _, target, turns = min(options)
    if not turns:
        return "andar"
    return turns[0]


def reconstruct_path(node):
    path = []
    while node is not None:
        path.append(node.get_coord())
        node = node.get_parent()
    path.reverse()
    return path


def astar(start, goal, walkable):
    if start == goal:
        return [start]

    counter = 0
    start_node = TreeNode(start, manhattan(start, goal), 0)
    open_heap = [(start_node.get_priority(), counter, start_node)]
    best_g = {start: 0}
    closed = set()

    while open_heap:
        _, _, node = heapq.heappop(open_heap)
        current = node.get_coord()
        if current in closed:
            continue
        if current == goal:
            return reconstruct_path(node)
        closed.add(current)

        for nb in neighbors(current):
            if nb != goal and not walkable(nb):
                continue
            if nb == goal and not walkable(nb):
                continue
            tentative_g = node.get_value_gx() + 1
            if tentative_g >= best_g.get(nb, 10**9):
                continue
            best_g[nb] = tentative_g
            fx = tentative_g + manhattan(nb, goal)
            child = TreeNode(nb, fx, tentative_g)
            child.set_parent(node)
            counter += 1
            heapq.heappush(open_heap, (child.get_priority(), counter, child))

    return None


def direction_between(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 1:
        return "leste"
    if dx == -1:
        return "oeste"
    if dy == 1:
        return "norte"
    if dy == -1:
        return "sul"
    raise ValueError(f"Passo invalido no caminho: {a} -> {b}")


def align_actions(current, target):
    if current == target:
        return []
    order = ["norte", "leste", "sul", "oeste"]
    delta = (order.index(target) - order.index(current)) % 4
    if delta == 1:
        return ["virar_direita"]
    if delta == 3:
        return ["virar_esquerda"]
    return ["virar_direita", "virar_direita"]


def path_to_actions(path, initial_direction):
    actions = []
    direction = initial_direction
    for a, b in zip(path, path[1:]):
        target_direction = direction_between(a, b)
        actions.extend(align_actions(direction, target_direction))
        actions.append("andar")
        direction = target_direction
    return actions


def plan_to(goal):
    current = (player_pos[0], player_pos[1])
    if current == goal:
        return []

    safe_cells = query_cells("seguro")
    visited_cells = query_cells("visitado")
    confirmed_pits = query_cells("poco_confirmado")
    confirmed_enemies = query_cells("inimigo_confirmado")
    confirmed_teleports = query_cells("teleporte_confirmado")
    safe_cells.add(current)
    visited_cells.add(current)

    def walkable(pos):
        if pos in confirmed_pits:
            return False
        if pos in confirmed_teleports:
            return False
        if pos in confirmed_enemies and pos != current and pos != goal:
            return False
        if pos in blocked_cells:
            return False
        if pos == goal:
            return True
        if pos in visited_cells:
            return True
        return pos in safe_cells

    path = astar(current, goal, walkable)
    if path is None:
        return []
    return path_to_actions(path, player_pos[2])


def decisao():
    global last_agent_cell

    if not alive():
        return ""

    escape_action = escape_damage_action()
    if escape_action:
        action_queue.clear()
        return escape_action

    current = (player_pos[0], player_pos[1])
    if current != last_agent_cell:
        unreachable_targets.clear()
        last_agent_cell = current

    if action_queue:
        return action_queue.pop(0)

    for _, tipo, x, y in get_candidates():
        if tipo in ("pegar", "sair"):
            return tipo
        if tipo != "mover":
            continue
        target = (x, y)
        if target in unreachable_targets or target in blocked_cells:
            continue
        actions = plan_to(target)
        if actions:
            action_queue.extend(actions)
            return action_queue.pop(0)
        unreachable_targets.add(target)

    home_actions = plan_to((1, 1))
    if home_actions:
        action_queue.extend(home_actions)
        return action_queue.pop(0)

    acoes = list(prolog.query("executa_acao(X)"))
    if not acoes:
        return ""
    fallback = atom(acoes[0]["X"])
    if fallback == "sair" and current != (1, 1):
        return "virar_direita"
    return fallback


def forward_position():
    x, y, direction = player_pos
    deltas = {
        "norte": (0, 1),
        "sul": (0, -1),
        "leste": (1, 0),
        "oeste": (-1, 0),
    }
    dx, dy = deltas.get(direction, (0, 0))
    return (x + dx, y + dy)


def exec_prolog(a):
    global last_action, expected_walk_target
    if a != "":
        expected_walk_target = forward_position() if a == "andar" else None
        list(prolog.query(a))
    last_action = a


def update_prolog():
    global player_pos, mapa, energia, pontuacao, visitados, show_map
    global ouros_coletados, expected_walk_target

    list(prolog.query("atualiza_obs, verifica_player"))

    x = Variable()
    y = Variable()
    visitado = Functor("visitado", 2)
    visitado_query = Query(visitado(x, y))
    visitados.clear()
    while visitado_query.nextSolution():
        visitados.append((x.value, y.value))
    visitado_query.closeQuery()

    x = Variable()
    y = Variable()
    certeza = Functor("certeza", 2)
    certeza_query = Query(certeza(x, y))
    certezas.clear()
    while certeza_query.nextSolution():
        certezas.append((x.value, y.value))
    certeza_query.closeQuery()

    if show_map:
        x = Variable()
        y = Variable()
        z = Variable()
        tile = Functor("tile", 3)
        tile_query = Query(tile(x, y, z))
        while tile_query.nextSolution():
            mapa[y.get_value() - 1][x.get_value() - 1] = str(z.value)
        tile_query.closeQuery()
    else:
        for yy in range(len(mapa)):
            for xx in range(len(mapa[yy])):
                mapa[yy][xx] = ""

        x = Variable()
        y = Variable()
        z = Variable()
        memory = Functor("memory", 3)
        memory_query = Query(memory(x, y, z))
        while memory_query.nextSolution():
            for s in z.value:
                if str(s) == "brisa":
                    mapa[y.get_value() - 1][x.get_value() - 1] += "P"
                elif str(s) == "flash":
                    mapa[y.get_value() - 1][x.get_value() - 1] += "T"
                elif str(s) == "passos":
                    mapa[y.get_value() - 1][x.get_value() - 1] += "D"
                elif str(s) == "reflexo":
                    mapa[y.get_value() - 1][x.get_value() - 1] += "U"
                elif str(s) == "brilho":
                    mapa[y.get_value() - 1][x.get_value() - 1] += "O"
        memory_query.closeQuery()

    x = Variable()
    y = Variable()
    z = Variable()
    posicao = Functor("posicao", 3)
    position_query = Query(posicao(x, y, z))
    position_query.nextSolution()
    player_pos = (x.value, y.value, str(z.value))
    position_query.closeQuery()

    x = Variable()
    energia_functor = Functor("energia", 1)
    energia_query = Query(energia_functor(x))
    energia_query.nextSolution()
    energia = x.value
    energia_query.closeQuery()

    x = Variable()
    pontuacao_functor = Functor("pontuacao", 1)
    pontuacao_query = Query(pontuacao_functor(x))
    pontuacao_query.nextSolution()
    pontuacao = x.value
    pontuacao_query.closeQuery()

    x = Variable()
    ouro_functor = Functor("ouros_coletados", 1)
    ouro_query = Query(ouro_functor(x))
    ouro_query.nextSolution()
    ouros_coletados = x.value
    ouro_query.closeQuery()

    if expected_walk_target is not None and in_bounds(expected_walk_target):
        current = (player_pos[0], player_pos[1])
        if alive() and current != expected_walk_target:
            blocked_cells.add(expected_walk_target)
            action_queue.clear()
        expected_walk_target = None

    if last_action == "andar":
        action_queue.clear()


def load_image(name):
    return pygame.image.load(str(ASSETS_DIR / name))


def load():
    global sys_font, clock, img_wall, img_grass, img_start, img_finish, img_path
    global img_gold, img_health, img_pit, img_bat, img_enemy1, img_enemy2, img_floor
    global bw_img_gold, bw_img_health, bw_img_pit, bw_img_bat, bw_img_enemy1, bw_img_enemy2, bw_img_floor
    global img_player_up, img_player_down, img_player_left, img_player_right, img_tomb

    sys_font = pygame.font.Font(pygame.font.get_default_font(), 20)
    clock = pygame.time.Clock()

    img_wall = load_image("wall.jpg")
    img_wall_size = (width / size_x, height / size_y)
    img_wall = pygame.transform.scale(img_wall, img_wall_size)

    img_player_up = load_image("player_up.png")
    img_player_up_size = (width / size_x, height / size_y)
    img_player_up = pygame.transform.scale(img_player_up, img_player_up_size)

    img_player_down = load_image("player_down.png")
    img_player_down_size = (width / size_x, height / size_y)
    img_player_down = pygame.transform.scale(img_player_down, img_player_down_size)

    img_player_left = load_image("player_left.png")
    img_player_left_size = (width / size_x, height / size_y)
    img_player_left = pygame.transform.scale(img_player_left, img_player_left_size)

    img_player_right = load_image("player_right.png")
    img_player_right_size = (width / size_x, height / size_y)
    img_player_right = pygame.transform.scale(img_player_right, img_player_right_size)

    img_tomb = load_image("tombstone.png")
    img_tomb_size = (width / size_x, height / size_y)
    img_tomb = pygame.transform.scale(img_tomb, img_tomb_size)

    img_grass = load_image("grass.jpg")
    img_grass_size = (width / size_x, height / size_y)
    img_grass = pygame.transform.scale(img_grass, img_grass_size)

    img_floor = load_image("floor.png")
    img_floor_size = (width / size_x, height / size_y)
    img_floor = pygame.transform.scale(img_floor, img_floor_size)

    img_gold = load_image("gold.png")
    img_gold_size = (width / size_x, height / size_y)
    img_gold = pygame.transform.scale(img_gold, img_gold_size)

    img_pit = load_image("pit.png")
    img_pit_size = (width / size_x, height / size_y)
    img_pit = pygame.transform.scale(img_pit, img_pit_size)

    img_enemy1 = load_image("enemy1.png")
    img_enemy1_size = (width / size_x, height / size_y)
    img_enemy1 = pygame.transform.scale(img_enemy1, img_enemy1_size)

    img_enemy2 = load_image("enemy2.png")
    img_enemy2_size = (width / size_x, height / size_y)
    img_enemy2 = pygame.transform.scale(img_enemy2, img_enemy2_size)

    img_bat = load_image("bat.png")
    img_bat_size = (width / size_x, height / size_y)
    img_bat = pygame.transform.scale(img_bat, img_bat_size)

    img_health = load_image("health.png")
    img_health_size = (width / size_x, height / size_y)
    img_health = pygame.transform.scale(img_health, img_health_size)

    bw_img_floor = load_image("bw_floor.png")
    bw_img_floor_size = (width / size_x, height / size_y)
    bw_img_floor = pygame.transform.scale(bw_img_floor, bw_img_floor_size)

    bw_img_gold = load_image("bw_gold.png")
    bw_img_gold_size = (width / size_x, height / size_y)
    bw_img_gold = pygame.transform.scale(bw_img_gold, bw_img_gold_size)

    bw_img_pit = load_image("bw_pit.png")
    bw_img_pit_size = (width / size_x, height / size_y)
    bw_img_pit = pygame.transform.scale(bw_img_pit, bw_img_pit_size)

    bw_img_enemy1 = load_image("bw_enemy1.png")
    bw_img_enemy1_size = (width / size_x, height / size_y)
    bw_img_enemy1 = pygame.transform.scale(bw_img_enemy1, bw_img_enemy1_size)

    bw_img_enemy2 = load_image("bw_enemy2.png")
    bw_img_enemy2_size = (width / size_x, height / size_y)
    bw_img_enemy2 = pygame.transform.scale(bw_img_enemy2, bw_img_enemy2_size)

    bw_img_bat = load_image("bw_bat.png")
    bw_img_bat_size = (width / size_x, height / size_y)
    bw_img_bat = pygame.transform.scale(bw_img_bat, bw_img_bat_size)

    bw_img_health = load_image("bw_health.png")
    bw_img_health_size = (width / size_x, height / size_y)
    bw_img_health = pygame.transform.scale(bw_img_health, bw_img_health_size)


def update(dt, screen):
    global elapsed_time

    elapsed_time += dt

    if (elapsed_time / 1000) > auto_play_tempo:
        if auto_play and alive():
            exec_prolog(decisao())
            update_prolog()

        elapsed_time = 0


def key_pressed(event):
    global show_map, auto_play
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_a:
            auto_play = not auto_play

        if not auto_play and alive():
            if event.key == pygame.K_LEFT:
                exec_prolog("virar_esquerda")
                update_prolog()

            elif event.key == pygame.K_RIGHT:
                exec_prolog("virar_direita")
                update_prolog()

            elif event.key == pygame.K_UP:
                exec_prolog("andar")
                update_prolog()

            elif event.key == pygame.K_SPACE:
                exec_prolog("pegar")
                update_prolog()

            elif event.key == pygame.K_s:
                exec_prolog("sair")
                update_prolog()

        if event.key == pygame.K_m:
            show_map = not show_map
            update_prolog()


def draw_screen(screen):
    screen.fill((0, 0, 0))

    y = 0
    for j in mapa:
        x = 0
        for i in j:
            if (x + 1, 12 - y) in visitados:
                screen.blit(img_floor, (x * img_floor.get_width(), y * img_floor.get_height()))
            else:
                screen.blit(
                    bw_img_floor,
                    (x * bw_img_floor.get_width(), y * bw_img_floor.get_height()),
                )

            if mapa[11 - y][x].find("P") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(img_pit, (x * img_pit.get_width(), y * img_pit.get_height()))
                else:
                    screen.blit(
                        bw_img_pit,
                        (x * bw_img_pit.get_width(), y * bw_img_pit.get_height()),
                    )

            if mapa[11 - y][x].find("T") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(img_bat, (x * img_bat.get_width(), y * img_bat.get_height()))
                else:
                    screen.blit(
                        bw_img_bat,
                        (x * bw_img_bat.get_width(), y * bw_img_bat.get_height()),
                    )

            if mapa[11 - y][x].find("D") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(
                        img_enemy1,
                        (x * img_enemy1.get_width(), y * img_enemy1.get_height()),
                    )
                else:
                    screen.blit(
                        bw_img_enemy1,
                        (x * bw_img_enemy1.get_width(), y * bw_img_enemy1.get_height()),
                    )

            if mapa[11 - y][x].find("d") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(
                        img_enemy2,
                        (x * img_enemy2.get_width(), y * img_enemy2.get_height()),
                    )
                else:
                    screen.blit(
                        bw_img_enemy2,
                        (x * bw_img_enemy2.get_width(), y * bw_img_enemy2.get_height()),
                    )

            if mapa[11 - y][x].find("U") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(
                        img_health,
                        (x * img_health.get_width(), y * img_health.get_height()),
                    )
                else:
                    screen.blit(
                        bw_img_health,
                        (x * bw_img_health.get_width(), y * bw_img_health.get_height()),
                    )

            if mapa[11 - y][x].find("O") > -1:
                if (x + 1, 12 - y) in certezas:
                    screen.blit(img_gold, (x * img_gold.get_width(), y * img_gold.get_height()))
                else:
                    screen.blit(
                        bw_img_gold,
                        (x * bw_img_gold.get_width(), y * bw_img_gold.get_height()),
                    )

            if x == player_pos[0] - 1 and y == 12 - player_pos[1]:
                if player_pos[2] == "norte":
                    screen.blit(
                        img_player_up,
                        (x * img_player_up.get_width(), y * img_player_up.get_height()),
                    )
                elif player_pos[2] == "sul":
                    screen.blit(
                        img_player_down,
                        (x * img_player_down.get_width(), y * img_player_down.get_height()),
                    )
                elif player_pos[2] == "leste":
                    screen.blit(
                        img_player_right,
                        (x * img_player_right.get_width(), y * img_player_right.get_height()),
                    )
                elif player_pos[2] == "oeste":
                    screen.blit(
                        img_player_left,
                        (x * img_player_left.get_width(), y * img_player_left.get_height()),
                    )
                elif player_pos[2] == "saiu":
                    screen.blit(
                        img_player_up,
                        (x * img_player_up.get_width(), y * img_player_up.get_height()),
                    )
                else:
                    screen.blit(
                        img_tomb,
                        (x * img_tomb.get_width(), y * img_tomb.get_height()),
                    )
            x += 1
        y += 1

    status = "saiu" if player_pos[2] == "saiu" else ("morto" if player_pos[2] == "morto" else "")
    t = sys_font.render("Pontuacao: " + str(pontuacao), False, (255, 255, 255))
    screen.blit(t, t.get_rect(top=height + 5, left=20))

    t = sys_font.render(last_action + (" " + status if status else ""), False, (255, 255, 255))
    screen.blit(t, t.get_rect(top=height + 5, left=width / 2 - 70))

    t = sys_font.render("E: " + str(energia) + "  O: " + str(ouros_coletados), False, (255, 255, 255))
    screen.blit(t, t.get_rect(top=height + 5, left=width - 160))


def main_loop(screen):
    global clock
    running = True

    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                break

            key_pressed(e)

        dt = clock.tick()
        update(dt, screen)
        draw_screen(screen)
        pygame.display.update()


def run_headless(max_steps):
    update_prolog()

    step = 0
    for step in range(1, max_steps + 1):
        if not alive():
            break
        acao = decisao()
        if acao == "":
            break
        if args.trace:
            print(
                f"{step:04d} antes pos={player_pos} "
                f"acao={acao} energia={energia} pontos={pontuacao} ouros={ouros_coletados}"
            )
        exec_prolog(acao)
        update_prolog()
        if args.trace:
            print(
                f"{step:04d} depois pos={player_pos} "
                f"energia={energia} pontos={pontuacao} ouros={ouros_coletados}"
            )
        if not alive():
            break
    else:
        step = max_steps

    status = player_pos[2]
    print(
        "resultado "
        f"status={status} "
        f"passos={step} "
        f"energia={energia} "
        f"pontuacao={pontuacao} "
        f"ouros={ouros_coletados} "
        f"pos=({player_pos[0]},{player_pos[1]})"
    )
    return 0 if status == "saiu" else 1


if args.headless:
    sys.exit(run_headless(args.max_steps))

import pygame

update_prolog()
pygame.init()
pygame.display.set_caption("INF1771 Trabalho 2 - Agente Logico")
screen = pygame.display.set_mode((width, height + 30))
load()

main_loop(screen)
pygame.quit()
