import argparse
import json
import time
import threading
import signal
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
    for name in ("stop", "clear-stop"):
        latch = commands.add_parser(name, help="Set or explicitly clear the operator stop latch")
        latch.add_argument("--stop-file", type=Path, default=Path("runtime/STOP"))
    paused = commands.add_parser("paused-ra2", help="Isolated, explicitly stepped test game")
    paused.add_argument("--port", type=int, default=14521)
    paused.add_argument("--game-pid", type=int, required=True)
    paused.add_argument("--game-dir", type=Path, required=True)
    paused.add_argument("--output", required=True)
    paused.add_argument("--image", type=Path, default=Path("runtime/paused.png"))
    paused.add_argument("--stop-file", type=Path, default=Path("runtime/STOP"))
    paused.add_argument("--arm", action="store_true")
    action = paused.add_mutually_exclusive_group()
    action.add_argument("--frames", type=int)
    action.add_argument("--move", nargs=2, type=int, metavar=("WORLD_X", "WORLD_Y"))
    paused.add_argument("--actor")
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
    elif args.command in {"stop", "clear-stop"}:
        if args.command == "stop":
            args.stop_file.parent.mkdir(parents=True, exist_ok=True)
            args.stop_file.touch()
        else:
            args.stop_file.unlink(missing_ok=True)
        print("Stop latched" if args.command == "stop" else "Stop cleared; no frames advanced")
    elif args.command == "paused-ra2":
        from .paused import PausedSession
        from .paused_move import move
        from .test_game import TestGame, require_private_network
        class OperatorStop(threading.Event):
            def is_set(self):
                return super().is_set() or args.stop_file.exists()
        stop = OperatorStop()
        previous = signal.signal(signal.SIGINT, lambda *_: stop.set())
        try:
            require_private_network()
            game = TestGame(args.game_pid, args.game_dir)
            session = PausedSession(args.port, armed=args.arm, stop=stop)
            if not game.fits_output(args.output): raise BridgeError("Test game must fill the chosen monitor and be focused")
            if args.move is not None:
                if args.actor is None: raise ValueError("Movement requires --actor")
                print(json.dumps(move(session, game, args.actor, tuple(args.move),
                      report=lambda e: print(json.dumps(e), flush=True))), flush=True)
            elif args.frames is not None:
                session.advance(args.frames, guard=game.focused)
            if not game.focused(): raise BridgeError("Focus changed before capture")
            print(json.dumps(session.capture(args.output, args.image)), flush=True)
            if not game.fits_output(args.output): raise BridgeError("Window mapping changed during capture")
            if stop.is_set(): parser.exit(130, "Stopped. No further simulation frames will be released.\n")
        except (BridgeError, ValueError, OSError) as error:
            parser.exit(1, str(error)+"\n")
        finally:
            signal.signal(signal.SIGINT, previous)
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
