import argparse
import json
import time
from pathlib import Path
from .capture import capture
from .core import Controller, Order, State, Unit


def demo():
    """Deterministic simulated adapter; never sends OS input."""
    c = Controller(Order("tanya", "attack", target="ship"))
    selected = None
    attacked = False
    for sequence in range(5):
        now = time.monotonic()
        state = State(sequence, now, True, selected,
                      {"tanya": Unit("tanya", 0, 0), "ship": Unit("ship", 5, 5)},
                      frozenset({"ship"}) if attacked else frozenset())
        action = c.step(state, now)
        print(json.dumps({"sequence": sequence, "phase": c.phase, "action": action}))
        if action and action["kind"] == "select": selected = "tanya"
        if action and action["kind"] == "attack": attacked = True
        if c.phase == "done": break


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Simulated selection/attack/verification; no input")
    cap = commands.add_parser("capture", help="Capture the complete monitor at native resolution")
    cap.add_argument("--output", required=True)
    cap.add_argument("--destination", type=Path, default=Path("runtime/frame.png"))
    args = parser.parse_args()
    if args.command == "demo": demo()
    else: print(json.dumps(capture(args.output, args.destination)))


if __name__ == "__main__": main()
