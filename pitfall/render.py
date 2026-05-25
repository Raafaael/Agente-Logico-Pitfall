"""Terminal renderer for the agent + environment."""
from __future__ import annotations

from .map_loader import Grid, get_cell
from .types import CellType, Direction, GRID_SIZE, Position


_DIR_GLYPH = {
    Direction.NORTH: "^",
    Direction.EAST: ">",
    Direction.SOUTH: "v",
    Direction.WEST: "<",
}

_CELL_GLYPH = {
    CellType.EMPTY: ".",
    CellType.PIT: "P",
    CellType.ENEMY_SMALL: "e",
    CellType.ENEMY_BIG: "E",
    CellType.TELEPORTER: "T",
    CellType.GOLD: "G",
    CellType.POWERUP: "+",
}


def render_world(grid: Grid, agent_pos: Position, agent_dir: Direction,
                 reveal: bool = False, kb_snapshot: dict | None = None) -> str:
    size = len(grid)
    lines: list[str] = []
    header = "    " + " ".join(f"{x:>2}" for x in range(1, size + 1))
    lines.append(header)
    lines.append("   +" + "---" * size + "+")
    snapshot = kb_snapshot or {}
    visited = set(map(tuple, snapshot.get("visited", [])))
    safe = set(map(tuple, snapshot.get("safe", [])))
    risk_pit = set(map(tuple, snapshot.get("risk_pit", [])))
    risk_enemy = set(map(tuple, snapshot.get("risk_enemy", [])))
    risk_tele = set(map(tuple, snapshot.get("risk_teleport", [])))
    confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
    confirmed_enemy = set(map(tuple, snapshot.get("confirmed_enemy", [])))
    confirmed_tele = set(map(tuple, snapshot.get("confirmed_teleport", [])))
    for y in range(size, 0, -1):
        cells: list[str] = []
        for x in range(1, size + 1):
            pos = (x, y)
            if pos == agent_pos:
                glyph = _DIR_GLYPH[agent_dir]
            elif reveal:
                glyph = _CELL_GLYPH[get_cell(grid, pos)]
            elif pos in visited or pos in safe:
                glyph = _glyph_for_known(grid, pos) if reveal else _knowledge_glyph(
                    pos, visited, safe, risk_pit, risk_enemy, risk_tele,
                    confirmed_pit, confirmed_enemy, confirmed_tele
                )
            else:
                glyph = _knowledge_glyph(
                    pos, visited, safe, risk_pit, risk_enemy, risk_tele,
                    confirmed_pit, confirmed_enemy, confirmed_tele
                )
            cells.append(f" {glyph} ")
        lines.append(f"{y:>2} |" + "".join(cells) + "|")
    lines.append("   +" + "---" * size + "+")
    return "\n".join(lines)


def _glyph_for_known(grid: Grid, pos: Position) -> str:
    return _CELL_GLYPH[get_cell(grid, pos)]


def _knowledge_glyph(pos, visited, safe, risk_pit, risk_enemy, risk_tele,
                     confirmed_pit, confirmed_enemy, confirmed_tele) -> str:
    if pos in visited:
        return "o"
    if pos in confirmed_pit:
        return "P"
    if pos in confirmed_enemy:
        return "X"
    if pos in confirmed_tele:
        return "T"
    if pos in safe:
        return "s"
    risks = []
    if pos in risk_pit:
        risks.append("p")
    if pos in risk_enemy:
        risks.append("x")
    if pos in risk_tele:
        risks.append("t")
    if risks:
        return "!" if len(risks) > 1 else risks[0]
    return "?"


def render_status(turn: int, agent_state, last_action: str, picked: str | None,
                  last_message: str) -> str:
    p = agent_state.last_percept
    return (
        f"turno={turn:>3} | pos={agent_state.pos} dir={agent_state.direction.short} "
        f"| energia={agent_state.energy} score={agent_state.score} "
        f"| acao={last_action} | percep=({p}) "
        f"| pega={picked or '-'} | {last_message}"
    )


LEGEND = (
    "Legenda do mapa (modo agente):\n"
    "  > < ^ v  agente (orientacao)\n"
    "  o        sala visitada\n"
    "  s        sala segura nao visitada\n"
    "  p/x/t    suspeita de poco / inimigo / teletransporte\n"
    "  !        multiplas suspeitas combinadas\n"
    "  P/X/T    perigo confirmado pela base de conhecimento\n"
    "  ?        sala desconhecida\n"
    "Modo --reveal mostra o mapa real:\n"
    "  P poco | e inimigo dano20 | E inimigo dano50 | T teletransporte\n"
    "  G ouro | + powerup | . vazio"
)
