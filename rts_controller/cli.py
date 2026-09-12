import argparse
import json
import time
import threading
from pathlib import Path
from .capture import capture
from .core import Controller, Order, State, Unit
from .ra2 import Reader, BridgeError


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
    observe = commands.add_parser("observe-ra2", help="Read local ra2yrcpp; never send game orders")
    observe.add_argument("--port", type=int, default=14521)
    observe.add_argument("--samples", type=int, default=1)
    observe.add_argument("--interval", type=float, default=.1)
    move = commands.add_parser("move-ra2", help="Armed, owned-unit short movement test")
    move.add_argument("--port", type=int, default=14521)
    move.add_argument("--actor", required=True)
    move.add_argument("--game-pid", type=int, required=True)
    move.add_argument("--destination", nargs=2, type=int, required=True)
    move.add_argument("--arm", action="store_true")
    cap = commands.add_parser("capture", help="Capture the complete monitor at native resolution")
    cap.add_argument("--output", required=True)
    cap.add_argument("--destination", type=Path, default=Path("runtime/frame.png"))
    args = parser.parse_args()
    if args.command == "demo": demo()
    elif args.command == "move-ra2":
        from .ra2_move import MoveAdapter
        from .runner import run
        stop = threading.Event()
        try:
            destination = tuple(args.destination)
            adapter = MoveAdapter(Reader(args.port), args.actor, args.game_pid, destination, armed=args.arm)
            controller = Controller(Order(args.actor, "move", destination=destination), tolerance=96)
            phase = run(controller, adapter, stop, report=lambda e: print(json.dumps(e), flush=True))
            if phase != "done": parser.exit(1, controller.reason+"\n")
        except KeyboardInterrupt:
            stop.set()
            parser.exit(130, "Stopped issuing commands; already issued orders remain active.\n")
        except (BridgeError, ValueError) as error:
            parser.exit(1, str(error)+"\n")
    elif args.command == "observe-ra2":
        if not 1 <= args.samples <= 10000 or not .02 <= args.interval <= 10:
            parser.error("samples must be 1..10000 and interval .02..10 seconds")
        reader = Reader(args.port)
        try:
            for i in range(args.samples):
                start = time.monotonic()
                print(json.dumps(reader.observe()), flush=True)
                if i+1 < args.samples:
                    time.sleep(max(0, args.interval-(time.monotonic()-start)))
        except BridgeError as error:
            parser.exit(1, str(error) + "\n")
    else: print(json.dumps(capture(args.output, args.destination)))


if __name__ == "__main__": main()
