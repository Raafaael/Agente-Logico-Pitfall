"""Bridge between Python and SWI-Prolog.

If a `swipl` executable is available on PATH, :class:`SwiPrologKB` spawns it
as a persistent subprocess and forwards `assertz`/`retract`/`call` via stdin.
Otherwise, the project falls back to :class:`pitfall.kb_python.PythonKB`.

Both backends expose the same surface used by :mod:`pitfall.agent`:
    - :meth:`reset`
    - :meth:`set_agent_pos(pos)`
    - :meth:`update_perception(pos, percepts)`
    - :meth:`mark_gold_taken(pos)`
    - :meth:`likely_safe(pos) -> bool`
    - :meth:`is_visited(pos) -> bool`
    - :meth:`is_known_gold(pos) -> bool`
    - :meth:`is_risky(pos) -> bool`
    - :meth:`safe_unvisited_frontier() -> list[Position]`
    - :meth:`decide() -> tuple[str, Optional[Position]]`
    - :meth:`snapshot() -> dict`
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Protocol

from .kb_python import PythonKB
from .types import GRID_SIZE, Position

logger = logging.getLogger(__name__)


KB_FILE = Path(__file__).with_name("knowledge_base.pl")
END_MARKER = "---END---"


class KnowledgeBase(Protocol):
    backend: str
    def reset(self) -> None: ...
    def set_agent_pos(self, pos: Position) -> None: ...
    def set_energy(self, energy: int) -> None: ...
    def update_perception(self, pos: Position, percepts: list[str]) -> None: ...
    def mark_gold_taken(self, pos: Position) -> None: ...
    def note_powerup_taken(self, pos: Position) -> None: ...
    def note_enemy_here(self, pos: Position) -> None: ...
    def likely_safe(self, pos: Position) -> bool: ...
    def walkable_for_path(self, pos: Position) -> bool: ...
    def is_visited(self, pos: Position) -> bool: ...
    def is_known_gold(self, pos: Position) -> bool: ...
    def is_risky(self, pos: Position) -> bool: ...
    def safe_unvisited_frontier(self) -> list[Position]: ...
    def decide(self) -> tuple[str, Optional[Position]]: ...
    def snapshot(self) -> dict: ...


class PrologUnavailable(RuntimeError):
    pass


class SwiPrologKB:
    """Persistent SWI-Prolog subprocess wrapped to look like ``PythonKB``."""

    backend = "swi-prolog"

    def __init__(self, kb_file: Path = KB_FILE, executable: str = "swipl") -> None:
        if shutil.which(executable) is None:
            raise PrologUnavailable(f"{executable!r} not found in PATH")
        if not kb_file.exists():
            raise FileNotFoundError(kb_file)

        self._proc = subprocess.Popen(
            [executable, "-q", "-f", str(kb_file)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )
        self.size = GRID_SIZE
        self.reset()

    # ---- low-level wire format ----

    def _send(self, term: str) -> str:
        if self._proc.poll() is not None:
            raise PrologUnavailable("swipl process has exited")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(term.rstrip(".") + ".\n")
        self._proc.stdin.flush()
        out: list[str] = []
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise PrologUnavailable("swipl pipe closed unexpectedly")
            line = line.rstrip("\n")
            if line == END_MARKER:
                break
            out.append(line)
        return "\n".join(out)

    def _do(self, goal: str) -> bool:
        reply = self._send(f"do({goal})")
        return reply.strip().endswith("OK")

    def _query(self, goal: str, template: str) -> list[str]:
        reply = self._send(f"query({goal}, {template})")
        m = re.search(r"SOLUTIONS:(.*)", reply, re.DOTALL)
        if not m:
            return []
        body = m.group(1).strip()
        if body == "[]":
            return []
        return _split_top_level(body)

    # ---- public KB API ----

    def reset(self) -> None:
        self._do("reset_kb")

    def set_exit(self, pos: Position) -> None:
        self._do(f"set_exit({_pos(pos)})")

    def set_agent_pos(self, pos: Position) -> None:
        self._do(f"set_agent_pos({_pos(pos)})")

    def set_energy(self, energy: int) -> None:
        self._do(f"set_energy({int(energy)})")

    def update_perception(self, pos: Position, percepts: list[str]) -> None:
        plist = "[" + ",".join(percepts) + "]"
        self._do(f"update_perception({_pos(pos)}, {plist})")

    def mark_gold_taken(self, pos: Position) -> None:
        self._do(f"mark_gold_taken({_pos(pos)})")
        self._do("inc_gold")

    def note_powerup_at(self, pos: Position) -> None:
        self._do(f"note_powerup_at({_pos(pos)})")

    def note_powerup_taken(self, pos: Position) -> None:
        self._do(f"note_powerup_taken({_pos(pos)})")

    def note_enemy_here(self, pos: Position) -> None:
        self._do(f"note_enemy_here({_pos(pos)})")

    def likely_safe(self, pos: Position) -> bool:
        return self._do(f"likely_safe({_pos(pos)})")

    def walkable_for_path(self, pos: Position) -> bool:
        return self._do(f"walkable_for_path({_pos(pos)})")

    def is_visited(self, pos: Position) -> bool:
        return self._do(f"visited({_pos(pos)})")

    def is_known_gold(self, pos: Position) -> bool:
        return self._do(f"gold_seen({_pos(pos)})")

    def is_risky(self, pos: Position) -> bool:
        return self._do(f"risky({_pos(pos)})")

    def safe_unvisited_frontier(self) -> list[Position]:
        sols = self._query("unvisited_safe_frontier(P)", "P")
        return [_parse_pos(s) for s in sols]

    def decide(self) -> tuple[str, Optional[Position]]:
        sols = self._query("decide(A)", "A")
        if not sols:
            return "sair", None
        head = sols[0]
        if head == "pegar":
            return "pegar", None
        if head == "sair":
            return "sair", None
        m = re.match(r"mover\((\d+)/(\d+)\)", head)
        if m:
            return "mover", (int(m.group(1)), int(m.group(2)))
        return "sair", None

    def snapshot(self) -> dict:
        return {
            "visited": [_parse_pos(p) for p in self._query("visited(P)", "P")],
            "safe": [_parse_pos(p) for p in self._query("likely_safe(P)", "P")],
            "risk_pit": [_parse_pos(p) for p in self._query("risk_pit(P)", "P")],
            "risk_enemy": [_parse_pos(p) for p in self._query("risk_enemy(P)", "P")],
            "risk_teleport": [_parse_pos(p) for p in self._query("risk_teleport(P)", "P")],
            "confirmed_pit": [
                _parse_pos(p) for p in self._query("confirmed_pit(P)", "P")
            ],
            "confirmed_enemy": [
                _parse_pos(p) for p in self._query("confirmed_enemy(P)", "P")
            ],
            "confirmed_teleport": [
                _parse_pos(p) for p in self._query("confirmed_teleport(P)", "P")
            ],
            "risky_frontier": [
                _parse_pos(p) for p in self._query("risky_frontier(P)", "P")
            ],
            "gold_seen": [_parse_pos(p) for p in self._query("gold_seen(P)", "P")],
            "powerup_seen": [_parse_pos(p) for p in self._query("powerup_seen(P)", "P")],
            "gold_carried": _parse_int(self._query("gold_carried(N)", "N")),
            "energy": _parse_int(self._query("agent_energy(N)", "N")),
        }

    def close(self) -> None:
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()


def _pos(p: Position) -> str:
    return f"{p[0]}/{p[1]}"


def _parse_pos(text: str) -> Position:
    text = text.strip()
    m = re.match(r"(\d+)\s*/\s*(\d+)", text)
    if not m:
        raise ValueError(f"Cannot parse position from {text!r}")
    return int(m.group(1)), int(m.group(2))


def _parse_int(sols: list[str]) -> int:
    if not sols:
        return 0
    try:
        return int(sols[0])
    except ValueError:
        return 0


def _split_top_level(body: str) -> list[str]:
    """Strip outer brackets and split a Prolog list at top-level commas."""
    body = body.strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in body:
        if ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [c for c in out if c]


def make_kb(prefer: str = "auto") -> KnowledgeBase:
    """Factory: try SWI-Prolog first (when ``prefer`` is auto/prolog), else Python.

    ``prefer`` values:
        - "auto"  -> try prolog, fall back to python
        - "prolog" -> require swipl, raise if unavailable
        - "python" -> always use the Python fallback
    """
    if prefer == "python":
        return PythonKB()
    if prefer == "prolog":
        return SwiPrologKB()
    try:
        return SwiPrologKB()
    except (PrologUnavailable, FileNotFoundError) as exc:
        logger.info("SWI-Prolog unavailable (%s); using Python KB fallback", exc)
        return PythonKB()
