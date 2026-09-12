"""Center the camera on selected owned objects; never use the unit Follow order."""
import configparser
import subprocess
from .ra2 import BridgeError


def center_key(directory):
    config = configparser.ConfigParser()
    if not config.read(directory / "KeyboardMD.ini"):
        raise BridgeError("Missing game keyboard configuration")
    values = [section["CenterView"] for section in config.values() if "CenterView" in section]
    supported = {"12": "KP_Begin", "74": "j"}
    if len(values) != 1 or values[0] not in supported:
        raise BridgeError("Unsupported CenterView binding; expected VK_CLEAR (12) or J (74)")
    for section in config.values():
        if any(name.lower() != "centerview" and value == values[0]
               for name, value in section.items()):
            raise BridgeError("CenterView binding conflicts with another command")
    return supported[values[0]]


def send_key(key, state):
    if key not in {"KP_Begin", "j"} or state not in {"down", "up"}:
        raise ValueError("Only the validated camera key is allowed")
    expression = (f'hl.dispatch(hl.dsp.send_key_state({{mods="",key="{key}",'
                  f'state="{state}"' + '}))')
    result = subprocess.run(["hyprctl", "eval", expression], capture_output=True,
                            text=True, timeout=2, check=True)
    if result.stdout.strip() != "ok":
        raise BridgeError("Camera key delivery was not acknowledged")


def center(session, game, output, *, key_sender=send_key):
    key = center_key(game.directory)
    if session.stop.is_set(): raise BridgeError("Operator stop")
    if not game.fits_output(output): raise BridgeError("Game mapping/focus changed")
    state = session.stable()
    selected = [u for u in state["own_objects"] if u["selected"] and
                u["health"] > 0 and u["on_map"] and not u["in_limbo"]]
    if not selected: raise BridgeError("No selected owned objects to center")
    if not state["single_human"] or state["winner"] or state["loser"]:
        raise BridgeError("Inactive or nonlocal mission")
    try:
        key_sender(key, "down")
        session.advance(3, guard=lambda: game.fits_output(output))
    finally:
        # Always release, including when focus is lost or stepping fails.
        key_sender(key, "up")
    after = session.advance(1, guard=lambda: game.fits_output(output))
    return {"status": "camera_key_sent", "frame": after["frame"],
            "actors": [u["id"] for u in selected],
            "verification": "Inspect full-screen capture; acknowledgment is not camera proof"}
