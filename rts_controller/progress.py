"""Mission-independent changes from two owned-state observations.

Disappearance is deliberately not called destruction. Units may enter transports,
change ownership, or be replaced. There is no mission-specific actor lookup.
"""
from .ra2 import BridgeError


def changes(before, after):
    if after["frame"] < before["frame"]:
        raise BridgeError("Cannot compare different/reset sessions")
    old = {u["id"]: u for u in before["own_objects"]}
    new = {u["id"]: u for u in after["own_objects"]}
    events = []
    for actor in sorted(new.keys() - old.keys()):
        events.append({"kind": "owned_object_appeared", "actor": actor})
    for actor in sorted(old.keys() - new.keys()):
        events.append({"kind": "owned_object_missing", "actor": actor,
                       "cause": "unknown"})
    for actor in sorted(old.keys() & new.keys()):
        a, b = old[actor], new[actor]
        if a["type_id"] != b["type_id"]:
            events.append({"kind": "identity_changed", "actor": actor})
            continue
        for field in ("health", "coordinates", "selected", "mission", "deployed"):
            if a.get(field) != b.get(field):
                events.append({"kind": field+"_changed", "actor": actor,
                               "before": a.get(field), "after": b.get(field)})
    for field in ("economy", "production", "winner", "loser"):
        if before.get(field) != after.get(field):
            events.append({"kind": field+"_changed", "before": before.get(field),
                           "after": after.get(field)})
    return {"from_frame": before["frame"], "to_frame": after["frame"], "events": events}
