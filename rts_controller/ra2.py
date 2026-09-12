"""Read-only ra2yrcpp JSON-over-HTTP client, based on its public protocol.

No game DLLs or upstream source are redistributed. No arbitrary command entry
point is exposed. In single-step mode GetGameState advances simulation, so we
refuse to observe unless InspectConfiguration confirms it is disabled.
"""
import http.client
import json
import time

PREFIX = "type.googleapis.com/"
LIMIT = 16 * 1024 * 1024


class BridgeError(RuntimeError):
    pass


def unpack(response, expected):
    try:
        if response.get("code", "OK") not in ("OK", 0):
            raise BridgeError("Bridge returned an error")
        body = response["body"]
        if body["@type"] != PREFIX + "ra2yrproto.PollResults":
            raise BridgeError("Unexpected response envelope")
        results = body["result"]["results"]
        if len(results) != 1:
            raise BridgeError("Expected exactly one command result")
        result = results[0]
        if result.get("resultCode", "OK") not in ("OK", 0):
            raise BridgeError("Observation command failed")
        payload = result["result"]
        if payload["@type"] != PREFIX + "ra2yrproto.commands." + expected:
            raise BridgeError("Unexpected result type")
        return payload
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise BridgeError("Malformed bridge response") from error


class Reader:
    def __init__(self, port=14521, timeout=.4):
        if not 1 <= port <= 65535 or not 0 < timeout <= 5:
            raise ValueError("Invalid port or timeout")
        self.port, self.timeout = port, timeout
        self.frame = None
        self.frame_seen_at = None

    def _read(self, name):
        if name not in {"InspectConfiguration", "GetGameState"}:
            raise BridgeError("Read-only command allowlist")
        return self._request(name, {})

    def _request(self, name, fields):
        if name not in {"InspectConfiguration", "GetGameState"} or fields:
            raise BridgeError("Reader only permits unmodified observation commands")
        command = {"commandType": "CLIENT_COMMAND", "blocking": True,
                   "command": {"@type": PREFIX + "ra2yrproto.commands." + name, **fields}}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            conn.request("POST", "/", json.dumps(command), {"Content-Type": "application/json"})
            response = conn.getresponse()
            if response.status != 200:
                raise BridgeError(f"HTTP status {response.status}")
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise BridgeError("Response exceeds size limit")
            return unpack(json.loads(raw), name)
        except (OSError, http.client.HTTPException, ValueError) as error:
            raise BridgeError(f"Bridge observation failed: {error}") from error
        finally:
            conn.close()

    def observe(self):
        start = time.monotonic()
        config = self._read("InspectConfiguration").get("config")
        if not isinstance(config, dict):
            raise BridgeError("Missing bridge configuration")
        if config.get("singleStep", False) is not False:
            raise BridgeError("Single-step mode would advance the game; observation refused")
        payload = self._read("GetGameState")
        state = payload.get("state")
        if not isinstance(state, dict) or state.get("stage") not in ("STAGE_INGAME", 2):
            raise BridgeError("No active in-game observation")
        frame = state.get("currentFrame", 0)
        if type(frame) is not int or frame < 0:
            raise BridgeError("Invalid game frame")
        now = time.monotonic()
        if self.frame is not None and frame < self.frame:
            raise BridgeError("Game frame reset; create a new reader for the new session")
        if frame != self.frame:
            self.frame_seen_at = now
        self.frame = frame
        players = [h for h in state.get("houses", []) if h.get("currentPlayer") is True]
        if len(players) != 1 or not players[0].get("self"):
            raise BridgeError("Cannot identify local player")
        player = players[0]
        # Enemy visibility is not exposed by this protocol. Do not claim that
        # onMap means visible, or expose hidden enemies as actionable targets.
        own = [o for o in state.get("objects", []) if o.get("pointerHouse") == player["self"]]
        units = [{"id": str(o.get("pointerSelf")), "health": o.get("health", 0),
                  "coordinates": o.get("coordinates"), "selected": o.get("selected", False),
                  "on_map": o.get("onMap", False), "in_limbo": o.get("inLimbo", False),
                  "type_id": str(o.get("pointerTechnotypeclass"))} for o in own]
        return {"frame": frame, "observed_at": self.frame_seen_at,
                "frame_unchanged_ms": round((now-self.frame_seen_at)*1000, 2),
                "request_ms": round((now-start)*1000, 2), "own_objects": units,
                "winner": player.get("isWinner", False), "loser": player.get("isLoser", False),
                "single_human": player.get("isHumanPlayer") is True and
                    sum(h.get("isHumanPlayer") is True for h in state.get("houses", [])) == 1,
                "enemy_visibility": "unavailable", "destruction_events": "unavailable",
                "control_ready": False}
