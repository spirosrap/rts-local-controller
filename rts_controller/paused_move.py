"""Owned-unit short moves, with each engine tick explicitly released."""
import math
from .ra2 import BridgeError
from .ra2_orders import Orders


def move(session, game, actor, destination, *, max_frames=120, report=lambda event: None):
    if not isinstance(actor, str) or not actor.isdecimal(): raise ValueError("Numeric actor ID required")
    if len(destination) != 2 or not all(type(v) is int and 0 <= v <= 65535 for v in destination):
        raise ValueError("Bounded world coordinates required")
    if type(max_frames) is not int or not 1 <= max_frames <= 120: raise ValueError("Frame budget 1..120 required")
    orders = Orders(session.port, timeout=1)
    state = session.stable()
    initial_frame = state["frame"]
    type_id = None

    def unit(snapshot):
        nonlocal type_id
        if snapshot["winner"] or snapshot["loser"] or not snapshot["single_human"]:
            raise BridgeError("Inactive or nonlocal mission")
        matches = [u for u in snapshot["own_objects"] if u["id"] == actor]
        if len(matches) != 1: raise BridgeError("Owned actor unavailable")
        u = matches[0]
        if u["health"] <= 0 or not u["on_map"] or u["in_limbo"]: raise BridgeError("Actor unavailable")
        if type_id is None: type_id = u["type_id"]
        if u["type_id"] != type_id: raise BridgeError("Actor identity changed")
        return u

    def position(u):
        p = u["coordinates"]
        if not isinstance(p, dict): raise BridgeError("Missing unit coordinates")
        point = (p.get("x", 0), p.get("y", 0))
        if not all(type(v) is int for v in point): raise BridgeError("Invalid unit coordinates")
        return point

    u = unit(state)
    if math.dist(position(u), destination) > 512: raise BridgeError("Move exceeds 512 world units")

    def command(name, fields):
        if session.stop.is_set(): raise BridgeError("Operator stop")
        if state["frame"]-initial_frame >= max_frames:
            raise BridgeError("Movement frame budget exhausted before command")
        if not game.focused(): raise BridgeError("Test game not focused")
        current = session.stable()
        current_unit = unit(current)
        if name == "MissionClicked" and not current_unit["selected"]:
            raise BridgeError("Selection changed before movement")
        if any(v["selected"] and v["id"] != actor for v in current["own_objects"]):
            raise BridgeError("Other units selected before command")
        try:
            orders.request(name, fields,
                           on_queued=lambda: session.advance(1, guard=game.focused),
                           on_uncertain=game.terminate_uncertain)
        except BaseException:
            session.failed = True
            raise
        result = session.stable()
        report({"event": name, "frame": result["frame"], "actor": actor})
        return result

    if any(v["selected"] and v["id"] != actor for v in state["own_objects"]):
        raise BridgeError("Other units selected")
    if not u["selected"]:
        state = command("UnitCommand", {"objectAddresses": [int(actor)], "action": "UNIT_ACTION_SELECT"})
    if not unit(state)["selected"]: raise BridgeError("Selection was not confirmed")
    if session.stop.is_set(): return {"status": "stopped", "frame": state["frame"]}
    state = command("MissionClicked", {"objectAddresses": [int(actor)], "event": "Mission_Move",
                    "coordinates": {"x": destination[0], "y": destination[1], "z": 0}})
    while True:
        u = unit(state)
        if not u["selected"]: raise BridgeError("Selection changed")
        distance = math.dist(position(u), destination)
        report({"event": "observe", "frame": state["frame"], "position": position(u), "distance": distance})
        if distance <= 96:
            return {"status": "arrived", "frame": state["frame"], "position": position(u),
                    "advanced_frames": state["frame"]-initial_frame}
        if session.stop.is_set(): return {"status": "stopped", "frame": state["frame"]}
        if state["frame"]-initial_frame >= max_frames:
            raise BridgeError("Movement frame budget exhausted; game remains paused")
        state = session.advance(1, guard=game.focused)
