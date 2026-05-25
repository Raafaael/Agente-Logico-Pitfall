"""Tkinter GUI for the Pitfall logical agent."""
from __future__ import annotations

import math
import random
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from .agent import Agent
from .environment import Environment
from .map_loader import generate_random_map, load_map_from_file
from .types import Direction, INITIAL_ENERGY, START_POS


CELL_SIZE = 48
STATUS_HEIGHT = 32
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


@dataclass
class GuiConfig:
    map_path: Path | None = None
    seed: int | None = None
    kb_backend: str = "auto"
    min_score: int = -500
    max_steps: int = 400
    delay: float = 0.25


class PitfallGUI:
    """Minimal viewer from base_projeto: board + score/energy bar."""

    def __init__(self, config: GuiConfig) -> None:
        self.config = config
        self.map_path = config.map_path
        self.current_seed = config.seed
        if self.map_path is None and self.current_seed is None:
            self.current_seed = random.randrange(1, 1_000_000)

        self.root = tk.Tk()
        self.root.title("INF1771 Trabalho 2 - Agente Logico")
        self.root.configure(bg="#000000")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.env: Environment | None = None
        self.agent: Agent | None = None
        self.after_id: str | None = None
        self.turn = 0

        self.images: dict[str, tk.PhotoImage] = {}
        self._load_images()
        self._build_layout()
        self._bind_keys()
        self._new_game()
        self._schedule_step()

    def run(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        size_px = CELL_SIZE * 12
        self.canvas = tk.Canvas(
            self.root,
            width=size_px,
            height=size_px,
            bg="#000000",
            highlightthickness=0,
        )
        self.canvas.pack(side="top")

        status = tk.Frame(self.root, bg="#000000", height=STATUS_HEIGHT)
        status.pack(side="bottom", fill="x")
        self.score_var = tk.StringVar(value="Pontuacao: 0")
        self.energy_var = tk.StringVar(value="Energia: 100")
        tk.Label(
            status,
            textvariable=self.score_var,
            bg="#000000",
            fg="#ffffff",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).pack(side="left", padx=12, pady=4)
        tk.Label(
            status,
            textvariable=self.energy_var,
            bg="#000000",
            fg="#ffffff",
            font=("Segoe UI", 14, "bold"),
            anchor="e",
        ).pack(side="right", padx=12, pady=4)

    def _load_images(self) -> None:
        names = {
            "floor": "floor.png",
            "floor_inferred": "bw_floor.png",
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
        self.root.bind("<space>", lambda _event: self._toggle_pause())
        self.root.bind("<Return>", lambda _event: self._step_once())
        self.root.bind("r", lambda _event: self._reset_game())
        self.root.bind("R", lambda _event: self._reset_game())

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------

    def _new_game(self) -> None:
        try:
            if self.map_path is not None:
                grid, meta = load_map_from_file(self.map_path)
                start = tuple(meta.get("start", START_POS))
                direction = meta.get("initial_direction", Direction.EAST)
                if isinstance(direction, str):
                    direction = Direction.parse(direction)
            else:
                if self.current_seed is None:
                    self.current_seed = random.randrange(1, 1_000_000)
                grid = generate_random_map(seed=self.current_seed)
                start = START_POS
                direction = Direction.EAST

            env = Environment(
                grid,
                start=start,
                initial_direction=direction,
                initial_energy=INITIAL_ENERGY,
                rng=(
                    random.Random(self.current_seed)
                    if self.current_seed is not None
                    else None
                ),
            )
            try:
                agent = Agent(
                    kb_backend=self.config.kb_backend,
                    start=start,
                    initial_direction=direction,
                )
            except Exception as exc:
                if self.config.kb_backend == "prolog":
                    messagebox.showwarning(
                        "SWI-Prolog indisponivel",
                        f"Nao foi possivel iniciar o Prolog:\n{exc}\n\nUsando Python.",
                    )
                    agent = Agent(
                        kb_backend="python",
                        start=start,
                        initial_direction=direction,
                    )
                else:
                    raise
        except Exception as exc:
            messagebox.showerror("Erro ao iniciar jogo", str(exc))
            return

        self.env = env
        self.agent = agent
        self.turn = 0
        self._observe_current()
        self._refresh()

    def _reset_game(self) -> None:
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        self._new_game()
        self._schedule_step()

    # ------------------------------------------------------------------
    # Game stepping
    # ------------------------------------------------------------------

    def _schedule_step(self) -> None:
        if self.env is None or self.env.game_over:
            return
        if self.turn >= self.config.max_steps:
            return
        delay_ms = int(max(self.config.delay, 0.05) * 1000)
        self.after_id = self.root.after(delay_ms, self._auto_step)

    def _auto_step(self) -> None:
        self._step_once()
        self._schedule_step()

    def _toggle_pause(self) -> None:
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        else:
            self._schedule_step()

    def _step_once(self) -> None:
        if self.env is None or self.agent is None:
            return
        if (
            self.env.game_over
            or self.env.score <= self.config.min_score
            or self.turn >= self.config.max_steps
        ):
            return
        self._observe_current()
        action = self.agent.decide_action()
        result = self.env.step(action)
        self.turn += 1
        self.agent.notify_step_result(action, result)
        if result.picked:
            self.agent.notify_picked(result.picked)
        if self.env.alive and not self.env.escaped:
            self._observe_current()
        self._refresh()

    def _observe_current(self) -> None:
        if self.env is None or self.agent is None:
            return
        percept = self.env.get_percept()
        self.agent.observe(
            percept=percept,
            pos=self.env.agent_pos,
            direction=self.env.agent_dir,
            energy=self.env.energy,
            score=self.env.score,
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._draw_board()
        if self.env is not None:
            self.score_var.set(f"Pontuacao: {self.env.score}")
            self.energy_var.set(f"Energia: {self.env.energy}")

    def _draw_board(self) -> None:
        if self.env is None or self.agent is None:
            return
        self.canvas.delete("all")
        grid = self.env.reveal_grid()
        size = len(grid)

        self.canvas.create_rectangle(
            0, 0, size * CELL_SIZE, size * CELL_SIZE,
            fill="#000000", outline="",
        )

        snapshot = self.agent.kb.snapshot()
        visited = set(map(tuple, snapshot.get("visited", [])))
        safe = set(map(tuple, snapshot.get("safe", [])))
        confirmed_pit = set(map(tuple, snapshot.get("confirmed_pit", [])))
        confirmed_enemy = set(map(tuple, snapshot.get("confirmed_enemy", [])))
        confirmed_tele = set(map(tuple, snapshot.get("confirmed_teleport", [])))
        gold_seen = set(map(tuple, snapshot.get("gold_seen", [])))
        powerup_seen = set(map(tuple, snapshot.get("powerup_seen", [])))
        enemy_damage = dict(snapshot.get("enemy_damage", []))

        for r in range(1, size + 1):
            for c in range(1, size + 1):
                pos = (r, c)
                is_known = (
                    pos in visited
                    or pos in safe
                    or pos in confirmed_pit
                    or pos in confirmed_enemy
                    or pos in confirmed_tele
                )
                if not is_known:
                    continue

                base = "floor" if pos in visited else "floor_inferred"
                self._draw_image(base, pos)

                if pos in confirmed_pit:
                    self._draw_image("pit", pos)
                elif pos in confirmed_enemy:
                    damage = enemy_damage.get(pos)
                    enemy_key = (
                        "enemy_big" if damage is not None and damage >= 50
                        else "enemy_small"
                    )
                    self._draw_image(enemy_key, pos)
                elif pos in confirmed_tele:
                    self._draw_image("teleporter", pos)
                elif pos in gold_seen:
                    self._draw_image("gold", pos)
                elif pos in powerup_seen:
                    self._draw_image("powerup", pos)

        player_key = _player_image_key(self.env.agent_dir)
        if not self.env.alive:
            player_key = "dead"
        self._draw_image(player_key, self.env.agent_pos)

    def _draw_image(self, key: str, pos: tuple[int, int]) -> None:
        r, c = pos
        x = (c - 1) * CELL_SIZE
        y = (r - 1) * CELL_SIZE
        img = self.images.get(key)
        if img is None:
            fill = "#243024" if key == "floor" else "#5a4030"
            self.canvas.create_rectangle(
                x, y, x + CELL_SIZE, y + CELL_SIZE, fill=fill, outline=""
            )
            return
        self.canvas.create_image(x, y, image=img, anchor="nw")

    def _on_close(self) -> None:
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
        if self.agent is not None and hasattr(self.agent.kb, "close"):
            self.agent.kb.close()
        self.root.destroy()


def _resize_photo(photo: tk.PhotoImage, target: int) -> tk.PhotoImage:
    gcd_w = math.gcd(photo.width(), target)
    gcd_h = math.gcd(photo.height(), target)
    zoom_x = target // gcd_w
    zoom_y = target // gcd_h
    sub_x = photo.width() // gcd_w
    sub_y = photo.height() // gcd_h
    return photo.zoom(zoom_x, zoom_y).subsample(sub_x, sub_y)


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
    min_score: int = -500,
    delay: float = 0.25,
) -> None:
    _ = reveal
    config = GuiConfig(
        map_path=map_path,
        seed=seed,
        kb_backend=kb_backend,
        min_score=min_score,
        max_steps=max_steps,
        delay=delay if delay > 0 else 0.25,
    )
    PitfallGUI(config).run()
