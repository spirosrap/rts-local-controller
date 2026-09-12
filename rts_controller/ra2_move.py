"""Explicitly armed, owned-unit selection and short-move experiment only."""
import json
import math
import subprocess
import time
from .core import State, Unit
from .ra2 import Reader, BridgeError
from .ra2_orders import Orders


class MoveAdapter:
    def __init__(self, reader: Reader, actor: str, game_pid: int, destination, *, armed=False):
        if not armed:
            raise ValueError("Live input requires explicit arming")
        if game_pid <= 0 or not actor.isdecimal():
            raise ValueError("Expected game PID and numeric actor ID")
        if len(destination) != 2 or not all(type(v) is int and 0 <= v <= 65535 for v in destination):
            raise ValueError("Expected bounded integer world coordinates")
        self.reader, self.actor, self.pid = reader, actor, game_pid
        self.destination = tuple(destination)
        self.origin = None
        self.orders = Orders(reader.port)

    def focused(self):
        result = subprocess.run(["hyprctl", "activewindow", "-j"], check=True,
                                capture_output=True, text=True, timeout=.3)
        window = json.loads(result.stdout)
        return window.get("pid") == self.pid and window.get("title") == "Red Alert 2"

    def observe(self):
        snapshot = self.reader.observe()
        if self.origin is None:
            # A first snapshot alone cannot prove that simulation is running.
            time.sleep(.1)
            following = self.reader.observe()
            if following["frame"] <= snapshot["frame"]:
                raise BridgeError("Simulation is paused or not advancing; no input sent")
            snapshot = following
        if snapshot.get("single_human") is not True or snapshot.get("winner") or snapshot.get("loser"):
            raise BridgeError("An active single-human offline test is required")
        units = {}
        selected = []
        for obj in snapshot["own_objects"]:
            coord = obj["coordinates"]
            if not isinstance(coord, dict): continue
            x, y = coord.get("x", 0), coord.get("y", 0)
            if not all(type(v) is int for v in (x, y)):
                raise BridgeError("Invalid unit coordinates")
            available = obj["on_map"] and not obj["in_limbo"]
            units[obj["id"]] = Unit(obj["id"], x, y, obj["health"] > 0, available)
            if obj["selected"]: selected.append(obj["id"])
        unit = units.get(self.actor)
        if unit is None or not unit.alive or not unit.visible:
            raise BridgeError("Owned actor unavailable")
        if self.origin is None:
            self.origin = unit.x, unit.y
            if math.dist(self.origin, self.destination) > 512:
                raise BridgeError("Experiment limited to a 512-world-unit move")
        return State(snapshot["frame"], snapshot["observed_at"], self.focused(),
                     selected[0] if selected == [self.actor] else None, units)

    def execute(self, action):
        if action.get("actor") != self.actor or action.get("kind") not in {"select", "move"}:
            raise BridgeError("Only the armed actor's selection and move are allowed")
        current = self.observe()
        if not current.focused or time.monotonic()-current.captured_at > .5:
            raise BridgeError("Focus lost or observation stale before input")
        if action["kind"] == "select":
            # Refuse to disturb any other owned units' selection.
            snapshot = self.reader.observe()
            others = [int(o["id"]) for o in snapshot["own_objects"]
                      if o["selected"] and o["id"] != self.actor]
            if others:
                raise BridgeError("Other units selected; refusing to change their selection")
            if not self.focused(): raise BridgeError("Focus lost before selection")
            self.orders.request("UnitCommand", {"objectAddresses": [int(self.actor)],
                                                 "action": "UNIT_ACTION_SELECT"})
        else:
            if current.selected != self.actor or tuple(action["destination"]) != self.destination:
                raise BridgeError("Selection or armed destination mismatch")
            if not self.focused(): raise BridgeError("Focus lost before move")
            self.orders.request("MissionClicked", {"objectAddresses": [int(self.actor)],
                "event": "Mission_Move", "coordinates": {
                    "x": self.destination[0], "y": self.destination[1], "z": 0}})

    def release(self):
        # Semantic API commands hold no keys/buttons. An issued move remains
        # active when the controller stops; no automatic game-stop order is sent.
        self.orders.close()
