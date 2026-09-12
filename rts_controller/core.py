"""Pure decision logic: no screenshots, OS input, or hidden global state."""
from dataclasses import dataclass
from math import hypot, isfinite


@dataclass(frozen=True)
class Unit:
    id: str
    x: float
    y: float
    alive: bool = True
    visible: bool = True


@dataclass(frozen=True)
class State:
    sequence: int
    captured_at: float  # monotonic seconds, same host as controller
    focused: bool
    selected: str | None
    units: dict[str, Unit]
    destroyed: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Order:
    actor: str
    kind: str
    target: str | None = None
    destination: tuple[float, float] | None = None

    def __post_init__(self):
        if self.kind not in {"move", "attack"}:
            raise ValueError("Only move and attack orders are supported")
        if self.kind == "attack" and not self.target:
            raise ValueError("Attack requires a target ID")
        if self.kind == "move" and (self.destination is None or
                len(self.destination) != 2 or
                not all(isfinite(v) for v in self.destination)):
            raise ValueError("Move requires a finite (x, y) destination")


class Controller:
    """An order completes only on positive evidence, never disappearance.

    Failed/uncertain actions are not automatically retried. A timeout requires
    an explicit new order. Fresh observations are required for every decision.
    """
    def __init__(self, order: Order, *, timeout=15.0, max_age=.5, tolerance=3.0):
        self.order = order
        self.timeout, self.max_age, self.tolerance = timeout, max_age, tolerance
        self.started = None
        self.last_sequence = -1
        self.phase = "new"
        self.reason = ""

    def step(self, state: State, now: float, *, stopped=False):
        if self.phase in {"done", "halted"}:
            return None
        if self.started is None:
            self.started = now
        if stopped:
            return self.halt("Emergency stop")
        if now - self.started > self.timeout:
            return self.halt("Order timed out; no unverified retry")
        age = now - state.captured_at
        if not isfinite(age) or age < 0 or age > self.max_age:
            return self.halt("Stale or invalid observation timestamp")
        if not state.focused:
            return self.halt("Game focus lost")
        if state.sequence <= self.last_sequence:
            return None
        self.last_sequence = state.sequence
        actor = state.units.get(self.order.actor)
        if actor is None or not actor.visible or not actor.alive:
            return self.halt("Actor unavailable")
        if self.order.kind == "attack" and self.order.target in state.destroyed:
            self.phase = "done"
            return None
        if self.order.kind == "move" and hypot(
                actor.x-self.order.destination[0], actor.y-self.order.destination[1]
        ) <= self.tolerance:
            self.phase = "done"
            return None
        if self.order.kind == "attack":
            target = state.units.get(self.order.target)
            if target is None or not target.visible:
                return self.halt("Target lost; disappearance is not destruction")
        if self.phase == "new":
            self.phase = "selecting"
            return {"kind": "select", "actor": actor.id}
        if self.phase == "selecting" and state.selected == actor.id:
            self.phase = "executing"
            return {"kind": self.order.kind, "actor": actor.id,
                    "target": self.order.target, "destination": self.order.destination}
        if self.phase == "executing" and state.selected != actor.id:
            return self.halt("Selection changed")
        return None

    def halt(self, reason):
        self.phase, self.reason = "halted", reason
        return None
