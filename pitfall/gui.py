"""Tkinter GUI for the Pitfall logical agent."""
from __future__ import annotations

import math
import random
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .agent import Agent
from .environment import Environment
from .map_loader import Grid, count_elements, generate_random_map, load_map_from_file
from .prolog_bridge import PrologUnavailable
from .types import Action, CellType, Direction, INITIAL_ENERGY, START_POS


CELL_SIZE = 48
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


@dataclass
class GuiConfig:
    map_path: Path | None = None
    seed: int | None = None
    kb_backend: str = "auto"
    reveal: bool = False
    max_steps: int = 400
    delay: float = 0.25


class PitfallGUI:
    """Visual runner that reuses the same Environment/Agent used by the CLI."""

    def __init__(self, config: GuiConfig) -> None:
        self.config = config
        self.map_path = config.map_path
        self.current_seed = config.seed
        if self.map_path is None and self.current_seed is None:
            self.current_seed = random.randrange(1, 1_000_000)

        self.root = tk.Tk()
        self.root.title("Agente Logico Pitfall - INF1771")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.reveal_var = tk.BooleanVar(value=config.reveal)
        self.backend_var = tk.StringVar(value=config.kb_backend)
        self.delay_var = tk.DoubleVar(value=max(config.delay, 0.05))
        self.status_vars: dict[str, tk.StringVar] = {}

        self.env: Environment | None = None
        self.agent: Agent | None = None
        self.turn = 0
        self.running = False
        self.after_id: str | None = None
        self.last_action = "-"
        self.last_message = "inicio"
        self.last_picked = "-"
        self.last_percepts = "nenhuma"
        self.last_energy_delta = 0
        self.last_score_delta = 0

        self.images: dict[str, tk.PhotoImage] = {}
        self._load_images()
        self._build_layout()
        self._bind_keys()
        self._new_game(reuse_source=True)

    def run(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        board_frame = ttk.Frame(outer)
        board_frame.grid(row=0, column=0, sticky="n")
        size_px = CELL_SIZE * 12
        self.canvas = tk.Canvas(
            board_frame,
            width=size_px,
            height=size_px,
            bg="#101612",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        side = ttk.Frame(outer, padding=(12, 0, 0, 0))
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)

        controls = ttk.LabelFrame(side, text="Controles", padding=8)
        controls.grid(row=0, column=0, sticky="ew")
        for i in range(2):
            controls.columnconfigure(i, weight=1)

        ttk.Button(controls, text="Passo", command=self._step_once).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=2
        )
        self.run_button = ttk.Button(controls, text="Executar", command=self._toggle_run)
        self.run_button.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)
        ttk.Button(controls, text="Reiniciar", command=self._reset_game).grid(
            row=1, column=0, sticky="ew", padx=(0, 4), pady=2
        )
        ttk.Button(controls, text="Novo mapa", command=self._new_random_game).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=2
        )
        ttk.Button(controls, text="Carregar mapa", command=self._choose_map).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=2
        )

        ttk.Checkbutton(
            controls,
            text="Revelar mapa real",
            variable=self.reveal_var,
            command=self._refresh,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 2))

        ttk.Label(controls, text="Backend KB").grid(row=4, column=0, sticky="w", pady=(6, 2))
        backend = ttk.Combobox(
            controls,
            textvariable=self.backend_var,
            values=("auto", "python", "prolog"),
            state="readonly",
            width=10,
        )
        backend.grid(row=4, column=1, sticky="ew", pady=(6, 2))
        backend.bind("<<ComboboxSelected>>", lambda _event: self._reset_game())

        ttk.Label(controls, text="Intervalo").grid(row=5, column=0, sticky="w", pady=(6, 2))
        ttk.Scale(
            controls,
            from_=0.05,
            to=1.0,
            variable=self.delay_var,
            orient="horizontal",
        ).grid(row=5, column=1, sticky="ew", pady=(6, 2))

        manual = ttk.LabelFrame(side, text="Manual", padding=8)
        manual.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for i in range(3):
            manual.columnconfigure(i, weight=1)
        ttk.Button(
            manual,
            text="Esquerda",
            command=lambda: self._manual_action(Action.TURN_LEFT),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(
            manual,
            text="Andar",
            command=lambda: self._manual_action(Action.WALK),
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(
            manual,
            text="Direita",
            command=lambda: self._manual_action(Action.TURN_RIGHT),
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0), pady=2)
        ttk.Button(
            manual,
            text="Pegar",
            command=lambda: self._manual_action(Action.GRAB),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(
            manual,
            text="Sair",
            command=lambda: self._manual_action(Action.EXIT),
        ).grid(row=1, column=2, sticky="ew", padx=(4, 0), pady=2)

        info = ttk.LabelFrame(side, text="Estado", padding=8)
        info.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        info.columnconfigure(1, weight=1)
        for row, key in enumerate(
            (
                "Fonte",
                "Seed",
                "Turno",
                "Posicao",
                "Direcao",
                "Energia",
                "Score",
                "Ouros",
                "Powerups",
                "Percepcoes",
                "Acao",
                "Delta E/S",
                "Evento",
                "Backend",
            )
        ):
            self.status_vars[key] = tk.StringVar(value="-")
            ttk.Label(info, text=f"{key}:").grid(row=row, column=0, sticky="w", pady=1)
            ttk.Label(info, textvariable=self.status_vars[key]).grid(
                row=row, column=1, sticky="ew", pady=1
            )

        legend = ttk.LabelFrame(side, text="Legenda", padding=8)
        legend.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            legend,
            justify="left",
            text=(
                "? desconhecido | o visitado | s seguro\n"
                "p poco | i inimigo | t teletransporte | ! combinado\n"
                "P/X/T = perigo confirmado pela KB"
            ),
        ).grid(row=0, column=0, sticky="w")

        log_frame = ttk.LabelFrame(side, text="Historico", padding=8)
        log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        side.rowconfigure(4, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, width=44, state="disabled", wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    def _load_images(self) -> None:
        names = {
            "floor": "floor.png",
            "unknown": "bw_floor.png",
            "pit": "pit.png",
            "enemy_small": "enemy1.png",
            "enemy_big": "enemy2.png",
            "teleporter": "bat.png",
            "gold": "gold.png",
            "powerup": "health.png",
            "player_north": "player_up.png",
            "player_east": "player_right.png",
            "player_south": "player_down.png",
            "player_west": "player_left.png",
            "dead": "tombstone.png",
        }
        for key, filename in names.items():
            path = ASSET_DIR / filename
            if path.exists():
                try:
                    raw = tk.PhotoImage(file=str(path))
                    self.images[key] = _resize_photo(raw, CELL_SIZE)
                except tk.TclError:
                    pass

    def _bind_keys(self) -> None:
        self.root.bind("<Up>", lambda _event: self._manual_action(Action.WALK))
        self.root.bind("<Left>", lambda _event: self._manual_action(Action.TURN_LEFT))
        self.root.bind("<Right>", lambda _event: self._manual_action(Action.TURN_RIGHT))
        self.root.bind("<space>", lambda _event: self._manual_action(Action.GRAB))
        self.root.bind("<Return>", lambda _event: self._step_once())

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------

    def _new_game(self, *, reuse_source: bool) -> None:
        self._stop()
        try:
            grid, start, direction, source_name = self._load_grid(reuse_source=reuse_source)
            env = Environment(
                grid,
                start=start,
                initial_direction=direction,
                initial_energy=INITIAL_ENERGY,
            )
            try:
                agent = Agent(
                    kb_backend=self.backend_var.get(),
                    start=start,
                    initial_direction=direction,
                )
            except (PrologUnavailable, FileNotFoundError) as exc:
                if self.backend_var.get() == "prolog":
                    self.backend_var.set("python")
                    agent = Agent(kb_backend="python", start=start, initial_direction=direction)
                    self._append_log(
                        f"SWI-Prolog indisponivel ({exc}); jogo iniciado com backend Python."
                    )
                else:
                    raise
        except Exception as exc:
            messagebox.showerror("Erro ao iniciar jogo", str(exc))
            return

        self.env = env
        self.agent = agent
        self.turn = 0
        self.last_action = "-"
        self.last_message = "inicio"
        self.last_picked = "-"
        self.last_percepts = str(env.get_percept())
        self.last_energy_delta = 0
        self.last_score_delta = 0
        self._append_log(f"Novo jogo: {source_name} | elementos={count_elements(grid)}")
        self._observe_current()
        self._refresh()

    def _load_grid(self, *, reuse_source: bool) -> tuple[Grid, tuple[int, int], Direction, str]:
        if self.map_path is not None and reuse_source:
            grid, meta = load_map_from_file(self.map_path)
            start = tuple(meta.get("start", START_POS))
            direction = meta.get("initial_direction", Direction.EAST)
            if isinstance(direction, str):
                direction = Direction.parse(direction)
            return grid, start, direction, self.map_path.name

        if self.current_seed is None:
            self.current_seed = random.randrange(1, 1_000_000)
        grid = generate_random_map(seed=self.current_seed)
        return grid, START_POS, Direction.EAST, "aleatorio"

    def _reset_game(self) -> None:
        self._new_game(reuse_source=True)

    def _new_random_game(self) -> None:
        self.map_path = None
        self.current_seed = random.randrange(1, 1_000_000)
        self._new_game(reuse_source=False)

    def _choose_map(self) -> None:
        path = filedialog.askopenfilename(
            title="Carregar mapa",
            filetypes=(
                ("Mapas", "*.json *.txt *.pl"),
                ("JSON", "*.json"),
                ("Prolog", "*.pl"),
                ("Texto", "*.txt"),
                ("Todos", "*.*"),
            ),
        )
        if not path:
            return
        self.map_path = Path(path)
        self._new_game(reuse_source=True)

    # ------------------------------------------------------------------
    # Game stepping
    # ------------------------------------------------------------------

    def _step_once(self) -> None:
        if self.env is None or self.agent is None:
            return
        if self.env.game_over or self.turn >= self.config.max_steps:
            self._stop()
            self._refresh()
            return

        self._observe_current()
        action = self.agent.decide_action()
        self._apply_action(action, source="agente")

    def _manual_action(self, action: Action) -> None:
        self._stop()
        if self.env is None or self.agent is None:
            return
        if self.env.game_over or self.turn >= self.config.max_steps:
            self._refresh()
            return
        self._observe_current()
        self._apply_action(action, source="manual")

    def _apply_action(self, action: Action, *, source: str) -> None:
        if self.env is None or self.agent is None:
            return
        result = self.env.step(action)
        self.turn += 1

        if result.picked:
            self.agent.notify_picked(result.picked)

        # Atualiza apenas a string de percepcao para display; o observe() completo
        # e' feito no inicio do proximo _step_once (igual ao CLI), evitando apagar
        # o pending mid-turno e mantendo o timing identico entre GUI e CLI.
        self.last_percepts = str(result.percept)

        self.last_action = action.value
        self.last_picked = result.picked or "-"
        self.last_message = result.message
        self.last_energy_delta = result.energy_delta
        self.last_score_delta = result.score_delta
        self._append_log(
            f"{self.turn:03d} | {source} | {action.value} | pos={self.env.agent_pos} "
            f"| energia={self.env.energy} ({result.energy_delta:+d}) "
            f"| score={self.env.score} ({result.score_delta:+d}) | {result.message}"
        )
        self._refresh()

        if self.env.game_over or self.turn >= self.config.max_steps:
            self._stop()

    def _observe_current(self) -> None:
        if self.env is None or self.agent is None:
            return
        percept = self.env.get_percept()
        self.last_percepts = str(percept)
        self.agent.observe(
            percept=percept,
            pos=self.env.agent_pos,
            direction=self.env.agent_dir,
            energy=self.env.energy,
            score=self.env.score,
        )

    def _toggle_run(self) -> None:
        if self.running:
            self._stop()
            return
        self.running = True
        self.run_button.configure(text="Pausar")
        self._run_next()

    def _run_next(self) -> None:
        if not self.running:
            return
        self._step_once()
        if self.running:
            delay_ms = int(max(self.delay_var.get(), 0.05) * 1000)
            self.after_id = self.root.after(delay_ms, self._run_next)

    def _stop(self) -> None:
        self.running = False
        if hasattr(self, "run_button"):
            self.run_button.configure(text="Executar")
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._draw_board()
        self._draw_status()

    def _draw_board(self) -> None:
        if self.env is None or self.agent is None:
            return
        self.canvas.delete("all")
        grid = self.env.reveal_grid()
        snapshot = self.agent.kb.snapshot()
        visited = set(map(tuple, snapshot.get("visited", [])))
        safe = set(map(tuple, snapshot.get("safe", [])))
        risk_pit = set(map(tuple, snapshot.get("risk_pit", [])))
        risk_enemy = set(map(tuple, snapshot.get("risk_enemy", [])))
        risk_tele = set(map(tuple, snapshot.get("risk_teleport", [])))
        confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
        confirmed_enemy = set(map(tuple, snapshot.get("confirmed_enemy", [])))
        confirmed_tele = set(map(tuple, snapshot.get("confirmed_teleport", [])))
        gold_seen = set(map(tuple, snapshot.get("gold_seen", [])))

        for r in range(1, len(grid) + 1):
            for c in range(1, len(grid) + 1):
                pos = (r, c)
                cell = grid[r - 1][c - 1]
                self._draw_cell(
                    pos,
                    cell,
                    visited,
                    safe,
                    risk_pit,
                    risk_enemy,
                    risk_tele,
                    confirmed_pit,
                    confirmed_enemy,
                    confirmed_tele,
                    gold_seen,
                )

        player_key = _player_image_key(self.env.agent_dir)
        if not self.env.alive:
            player_key = "dead"
        self._draw_image(player_key, self.env.agent_pos)
        self.canvas.create_rectangle(
            0,
            0,
            CELL_SIZE * len(grid),
            CELL_SIZE * len(grid),
            outline="#d6c07a",
            width=2,
        )

    def _draw_cell(
        self,
        pos: tuple[int, int],
        cell: CellType,
        visited: set[tuple[int, int]],
        safe: set[tuple[int, int]],
        risk_pit: set[tuple[int, int]],
        risk_enemy: set[tuple[int, int]],
        risk_tele: set[tuple[int, int]],
        confirmed_pit: set[tuple[int, int]],
        confirmed_enemy: set[tuple[int, int]],
        confirmed_tele: set[tuple[int, int]],
        gold_seen: set[tuple[int, int]],
    ) -> None:
        r, c = pos
        x0 = (c - 1) * CELL_SIZE
        y0 = (r - 1) * CELL_SIZE
        x1 = x0 + CELL_SIZE
        y1 = y0 + CELL_SIZE

        if self.reveal_var.get():
            self._draw_image(_cell_image_key(cell), pos)
        elif pos in visited:
            self._draw_image("floor", pos)
            self.canvas.create_text(x0 + 8, y0 + 8, text="o", fill="#eef2d0", anchor="nw")
        elif pos in confirmed_pit or pos in confirmed_enemy or pos in confirmed_tele:
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="#1e1212", outline="")
            label = "P"
            if pos in confirmed_enemy:
                label = "X"
            elif pos in confirmed_tele:
                label = "T"
            self.canvas.create_text(x0 + CELL_SIZE / 2, y0 + CELL_SIZE / 2,
                                    text=label, fill="#ff6961",
                                    font=("Segoe UI", 14, "bold"))
        elif pos in safe:
            self._draw_image("unknown", pos)
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="#203527", stipple="gray50")
            self.canvas.create_text(x0 + CELL_SIZE / 2, y0 + CELL_SIZE / 2,
                                    text="s", fill="#d9f5c4", font=("Segoe UI", 14, "bold"))
        else:
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="#101612", outline="")
            label = "?"
            color = "#6f806f"
            risks = []
            if pos in risk_pit:
                risks.append("p")
            if pos in risk_enemy:
                risks.append("i")
            if pos in risk_tele:
                risks.append("t")
            if risks:
                label = "!" if len(risks) > 1 else risks[0]
                color = "#ffb15c"
            self.canvas.create_text(x0 + CELL_SIZE / 2, y0 + CELL_SIZE / 2,
                                    text=label, fill=color, font=("Segoe UI", 13, "bold"))

        if pos in gold_seen and not self.reveal_var.get():
            self.canvas.create_text(x0 + CELL_SIZE - 8, y0 + 8, text="O",
                                    fill="#ffd761", anchor="ne",
                                    font=("Segoe UI", 13, "bold"))

        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#253128")

    def _draw_image(self, key: str, pos: tuple[int, int]) -> None:
        r, c = pos
        x = (c - 1) * CELL_SIZE
        y = (r - 1) * CELL_SIZE
        img = self.images.get(key)
        if img is None:
            fill = "#243024" if key in ("floor", "unknown") else "#5a4030"
            self.canvas.create_rectangle(x, y, x + CELL_SIZE, y + CELL_SIZE, fill=fill, outline="")
            return
        self.canvas.create_image(x, y, image=img, anchor="nw")

    def _draw_status(self) -> None:
        if self.env is None or self.agent is None:
            return
        source = self.map_path.name if self.map_path is not None else "aleatorio"
        values = {
            "Fonte": source,
            "Seed": str(self.current_seed) if self.map_path is None else "-",
            "Turno": f"{self.turn}/{self.config.max_steps}",
            "Posicao": str(self.env.agent_pos),
            "Direcao": self.env.agent_dir.pt,
            "Energia": str(self.env.energy),
            "Score": str(self.env.score),
            "Ouros": f"{self.env.gold_collected}/3",
            "Powerups": f"{self.env.powerups_taken}/3",
            "Percepcoes": self.last_percepts,
            "Acao": self.last_action,
            "Delta E/S": f"{self.last_energy_delta:+d} / {self.last_score_delta:+d}",
            "Evento": self._status_message(),
            "Backend": self.agent.backend,
        }
        for key, value in values.items():
            self.status_vars[key].set(value)

    def _status_message(self) -> str:
        if self.env is None:
            return self.last_message
        if self.env.escaped:
            return "saiu do labirinto"
        if not self.env.alive:
            return "morreu"
        if self.turn >= self.config.max_steps:
            return "limite de turnos"
        return self.last_message

    def _append_log(self, msg: str) -> None:
        if not hasattr(self, "log"):
            return
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()


def _resize_photo(photo: tk.PhotoImage, target: int) -> tk.PhotoImage:
    gcd_w = math.gcd(photo.width(), target)
    gcd_h = math.gcd(photo.height(), target)
    zoom_x = target // gcd_w
    zoom_y = target // gcd_h
    sub_x = photo.width() // gcd_w
    sub_y = photo.height() // gcd_h
    return photo.zoom(zoom_x, zoom_y).subsample(sub_x, sub_y)


def _cell_image_key(cell: CellType) -> str:
    return {
        CellType.EMPTY: "floor",
        CellType.PIT: "pit",
        CellType.ENEMY_SMALL: "enemy_small",
        CellType.ENEMY_BIG: "enemy_big",
        CellType.TELEPORTER: "teleporter",
        CellType.GOLD: "gold",
        CellType.POWERUP: "powerup",
    }[cell]


def _player_image_key(direction: Direction) -> str:
    return {
        Direction.NORTH: "player_north",
        Direction.EAST: "player_east",
        Direction.SOUTH: "player_south",
        Direction.WEST: "player_west",
    }[direction]


def launch_gui(
    *,
    map_path: Path | None = None,
    seed: int | None = None,
    kb_backend: str = "auto",
    reveal: bool = False,
    max_steps: int = 400,
    delay: float = 0.25,
) -> None:
    config = GuiConfig(
        map_path=map_path,
        seed=seed,
        kb_backend=kb_backend,
        reveal=reveal,
        max_steps=max_steps,
        delay=delay if delay > 0 else 0.25,
    )
    PitfallGUI(config).run()
