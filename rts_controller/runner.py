"""In-process adapter loop: no model/tool round trips per action."""
import threading
import time
from typing import Protocol
from .core import Controller, State


class Adapter(Protocol):
    def observe(self) -> State:
        """Return fresh verified state; bounded latency is required."""
        ...

    def execute(self, action: dict) -> None:
        """Recheck focus and geometry immediately before bounded input."""
        ...

    def release(self) -> None:
        """Release any held keys/buttons on every exit path."""
        ...


def run(controller: Controller, adapter: Adapter, stop: threading.Event,
        *, hz=10, report=lambda event: None):
    if not 1 <= hz <= 60:
        raise ValueError("hz must be between 1 and 60")
    try:
        while controller.phase not in {"done", "halted"}:
            started = time.monotonic()
            if stop.is_set():
                controller.halt("Emergency stop")
                break
            state = adapter.observe()
            action = controller.step(state, time.monotonic(), stopped=stop.is_set())
            if action:
                if stop.is_set():
                    controller.halt("Emergency stop")
                    break
                adapter.execute(action)
            report({"phase": controller.phase, "reason": controller.reason,
                    "action": action, "loop_ms": (time.monotonic()-started)*1000})
            if controller.phase not in {"done", "halted"}:
                stop.wait(max(0, 1/hz-(time.monotonic()-started)))
    except BaseException:
        controller.halt("Adapter or controller exception")
        raise
    finally:
        adapter.release()
    return controller.phase
