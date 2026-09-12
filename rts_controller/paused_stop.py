"""Stop an explicitly chosen owned actor and verify its motion settles."""
from .ra2 import BridgeError
from .ra2_orders import Orders


def stop_actor(session, game, actor, max_frames=120):
    if not isinstance(actor, str) or not actor.isdecimal(): raise ValueError("Numeric actor ID required")
    if type(max_frames) is not int or not 4 <= max_frames <= 120:
        raise ValueError("Frame budget must be 4..120")
    initial = session.stable()
    initial_frame = initial["frame"]
    identity = None

    def unit(state):
        nonlocal identity
        if not state["single_human"] or state["winner"] or state["loser"]:
            raise BridgeError("Inactive or nonlocal mission")
        matches = [u for u in state["own_objects"] if u["id"] == actor]
        if len(matches) != 1: raise BridgeError("Owned actor unavailable")
        u = matches[0]
        if u["health"] <= 0 or not u["on_map"] or u["in_limbo"]:
            raise BridgeError("Actor unavailable")
        if identity is None: identity = u["type_id"]
        if identity != u["type_id"]: raise BridgeError("Actor identity changed")
        return u

    initial_unit = unit(initial)
    position = initial_unit["coordinates"]
    if not isinstance(position, dict) or not all(type(position.get(k)) is int for k in ("x", "y")):
        raise BridgeError("Missing position")
    if session.stop.is_set(): raise BridgeError("Operator stop")
    if not game.focused(): raise BridgeError("Game not focused")
    try:
        Orders(session.port, timeout=1).request(
            "MissionClicked", {"objectAddresses": [int(actor)], "event": "Mission_Stop",
                               "coordinates": position},
            on_queued=lambda: session.advance(1, guard=game.focused),
            on_uncertain=game.terminate_uncertain)
    except BaseException:
        session.failed = True
        raise
    state = session.stable()
    previous = None
    settled = 0
    while state["frame"] - initial_frame < max_frames:
        u = unit(state)
        position = u["coordinates"]
        if not isinstance(position, dict): raise BridgeError("Missing position")
        # Stop commonly settles into Guard. Never equate an acknowledgment with success.
        if position == previous and u.get("mission") in ("Mission_Stop", "Mission_Guard", 13, 5):
            settled += 1
        else: settled = 0
        if settled >= 3:
            return {"status": "stop_verified", "actor": actor, "frame": state["frame"]}
        if session.stop.is_set(): return {"status": "stopped", "frame": state["frame"]}
        previous = position
        state = session.advance(1, guard=game.focused)
    raise BridgeError("Stop was not verified within the frame budget; game remains paused")
