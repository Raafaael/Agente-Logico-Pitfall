"""CLI entry point for the Pitfall logical agent."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from pitfall.agent import Agent
from pitfall.environment import Environment
from pitfall.map_loader import (
    count_elements,
    empty_grid,
    generate_random_map,
    load_map_from_file,
    save_map_to_file,
)
from pitfall.render import LEGEND, render_status, render_world
from pitfall.types import Action, Direction, INITIAL_ENERGY, START_POS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pitfall logical agent (INF1771 - PUC-Rio).",
    )
    p.add_argument("--map", type=Path, help="Carregar mapa JSON/texto.")
    p.add_argument("--seed", type=int, default=None,
                   help="Seed para geracao aleatoria do mapa.")
    p.add_argument("--save-map", type=Path,
                   help="Salva o mapa gerado em arquivo JSON antes de jogar.")
    p.add_argument("--max-steps", type=int, default=800,
                   help="Limite de turnos (default: 800).")
    p.add_argument("--kb", choices=["auto", "prolog", "python"], default="auto",
                   help="Backend da base de conhecimento.")
    p.add_argument("--reveal", action="store_true",
                   help="Mostra o mapa real durante a execucao (debug).")
    p.add_argument("--render-every", type=int, default=1,
                   help="Renderizar a cada N turnos (0 = somente final).")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Pausa em segundos entre turnos (default: 0).")
    p.add_argument("--gui", action="store_true",
                   help="Abre a interface grafica Tkinter.")
    p.add_argument("--quiet", action="store_true", help="Reduz verbosidade.")
    p.add_argument("--verbose", action="store_true", help="Logs em DEBUG.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.gui:
        from pitfall.gui import launch_gui

        launch_gui(
            map_path=args.map,
            seed=args.seed,
            kb_backend=args.kb,
            reveal=args.reveal,
            max_steps=args.max_steps,
            delay=args.delay,
        )
        return 0

    if args.map:
        grid, meta = load_map_from_file(args.map)
        start = tuple(meta.get("start", START_POS))
        direction = meta.get("initial_direction", Direction.EAST)
        if isinstance(direction, str):
            direction = Direction.parse(direction)
        if not args.quiet:
            print(f"[mapa] carregado de {args.map}")
    else:
        grid = generate_random_map(seed=args.seed)
        start = START_POS
        direction = Direction.EAST
        if not args.quiet:
            print(f"[mapa] gerado aleatoriamente (seed={args.seed})")

    if args.save_map:
        save_map_to_file(grid, args.save_map, start=start, initial_direction=direction)
        if not args.quiet:
            print(f"[mapa] salvo em {args.save_map}")

    if not args.quiet:
        print("[mapa] elementos:", count_elements(grid))

    env = Environment(grid, start=start, initial_direction=direction,
                      initial_energy=INITIAL_ENERGY)
    agent = Agent(kb_backend=args.kb, start=start, initial_direction=direction)
    if not args.quiet:
        print(f"[kb] backend={agent.backend}")
        print(LEGEND)
        print()

    return run_loop(env, agent, args)


def run_loop(env: Environment, agent: Agent, args) -> int:
    last_action_str = "-"
    last_picked: str | None = None
    last_msg = "inicio"
    for turn in range(1, args.max_steps + 1):
        percept = env.get_percept()
        agent.observe(
            percept=percept,
            pos=env.agent_pos,
            direction=env.agent_dir,
            energy=env.energy,
            score=env.score,
        )

        if args.render_every and turn % args.render_every == 0 and not args.quiet:
            display_grid = env.reveal_grid() if args.reveal else empty_grid(env.size)
            print(render_world(display_grid, env.agent_pos, env.agent_dir,
                               reveal=args.reveal,
                               kb_snapshot=agent.kb.snapshot()))
            print(render_status(turn, agent.state, last_action_str, last_picked, last_msg))
            print()

        if env.game_over:
            break

        action = agent.decide_action()
        result = env.step(action)
        last_action_str = action.value
        last_picked = result.picked
        last_msg = result.message

        if result.picked:
            agent.notify_picked(result.picked)

        if args.delay > 0:
            time.sleep(args.delay)

    print_final(env, agent, args)
    return 0 if env.escaped or env.alive else 1


def print_final(env: Environment, agent: Agent, args) -> None:
    if not args.quiet:
        print()
    print("=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    if env.escaped:
        print(f"status: SAIU PELO PORTAL {list(env.start_pos)}")
    elif not env.alive:
        print("status: MORREU")
    else:
        print("status: limite de turnos alcancado")
    print(f"score final  : {env.score}")
    print(f"energia      : {env.energy}")
    print(f"ouros        : {env.gold_collected}/3")
    print(f"powerups     : {env.powerups_taken}/3")
    print(f"acoes feitas : {env.steps}")
    print(f"backend kb   : {agent.backend}")


if __name__ == "__main__":
    sys.exit(main())
