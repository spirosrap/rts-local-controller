"""Opt-in simulation stepping using ra2yrcpp's documented storage reader.

ReadValue never advances simulation; GetGameState deliberately releases one
iteration in singleStep mode. A step is never retried after an uncertain result.
"""
import http.client
import json
import time
import threading
from pathlib import Path
from .ra2 import Reader, BridgeError, PREFIX, LIMIT, unpack
from .capture import capture


class PausedSession:
    def __init__(self, port=14521, *, armed=False, stop=None):
        if not armed:
            raise ValueError("Pause-assisted control requires explicit arming")
        self.reader = Reader(port)
        self.port = port
        self.stop = stop if stop is not None else threading.Event()
        self.failed = False
        self.last_frame = None
        self.object_types = None

    def request(self, name, fields=None):
        allowed = {"InspectConfiguration": [{}],
                   "ReadValue": [{"data": {"gameState": {}}}, {"data": {"initialGameState": {}}}],
                   "GetGameState": [{}]}
        if name not in allowed or (fields or {}) not in allowed[name]:
            raise BridgeError("Unsupported paused-session request")
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=.7)
        try:
            c.request("POST", "/", json.dumps({"commandType": "CLIENT_COMMAND", "blocking": True,
                      "command": {"@type": PREFIX+"ra2yrproto.commands."+name, **(fields or {})}}),
                      {"Content-Type": "application/json"})
            r = c.getresponse()
            if r.status != 200: raise BridgeError("Bridge HTTP error")
            raw = r.read(LIMIT+1)
            if len(raw) > LIMIT: raise BridgeError("Bridge response too large")
            return unpack(json.loads(raw), name)
        except (OSError, ValueError, http.client.HTTPException) as error:
            self.failed = True
            raise BridgeError("Paused bridge transport failed; no retry") from error
        finally:
            c.close()

    def observe(self):
        start = time.monotonic()
        if self.failed: raise BridgeError("Session halted after an uncertain operation")
        config = self.request("InspectConfiguration").get("config", {})
        if config.get("singleStep") is not True:
            self.failed = True
            raise BridgeError("singleStep must already be enabled in the test copy")
        state = self.request("ReadValue", {"data": {"gameState": {}}}).get("data", {}).get("gameState")
        if self.object_types is None:
            initial = self.request("ReadValue", {"data": {"initialGameState": {}}})
            self.object_types = initial.get("data", {}).get("initialGameState", {}).get("objectTypes", [])
        if isinstance(state, dict) and not state.get("objectTypes"):
            state["objectTypes"] = self.object_types
        snapshot = self.reader.summarize(state, start)
        if self.last_frame is not None and snapshot["frame"] < self.last_frame:
            self.failed = True
            raise BridgeError("Session frame reset")
        self.last_frame = snapshot["frame"]
        snapshot["observed_at"] = time.monotonic()
        snapshot["mode"] = "single_step"
        return snapshot

    def stable(self):
        first = self.observe()
        time.sleep(.05)
        second = self.observe()
        if first["frame"] != second["frame"]:
            self.failed = True
            raise BridgeError("Simulation moved without a requested step")
        return second

    def advance(self, frames=1, *, guard=lambda: True):
        if type(frames) is not int or not 1 <= frames <= 120:
            raise ValueError("Step budget must be 1..120 frames")
        state = self.stable()
        for _ in range(frames):
            if self.stop.is_set(): break
            if not guard(): raise BridgeError("Focus or operator guard failed")
            if state["winner"] or state["loser"] or not state["single_human"]:
                raise BridgeError("An active single-human test mission is required")
            before = state["frame"]
            # Exactly one release; never repeat this on timeout.
            try:
                released = self.request("GetGameState").get("state", {})
                if released.get("currentFrame", 0) != before:
                    raise BridgeError("Frame changed before release; another controller may be active")
                deadline = time.monotonic()+1
                while True:
                    state = self.observe()
                    if state["frame"] != before: break
                    if time.monotonic() >= deadline:
                        raise BridgeError("No frame advancement; outcome uncertain")
                    time.sleep(.005)
                if state["frame"] != before+1:
                    raise BridgeError("Unexpected frame increment")
            except BaseException:
                self.failed = True
                raise
        return self.stable()

    def capture(self, output, destination):
        before = self.stable()
        frame = capture(output, Path(destination).resolve())
        after = self.observe()
        if before["frame"] != after["frame"]:
            self.failed = True
            raise BridgeError("Frame changed during capture; image/state pairing rejected")
        return {"state": after, "image": frame, "simulation_frame": after["frame"]}
