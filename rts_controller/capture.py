"""Full output capture. Never crops or resizes the frame."""
import os
import struct
import subprocess
import time
from pathlib import Path


def capture(output: str, destination: Path):
    if not output or output.startswith("-"):
        raise ValueError("Expected an output name, e.g. DP-1")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial.png")
    start = time.monotonic()
    subprocess.run(["grim", "-c", "-o", output, str(temporary)],
                   check=True, timeout=5, capture_output=True)
    with temporary.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or len(header) != 24:
        raise ValueError("Capture did not produce a PNG")
    width, height = struct.unpack(">II", header[16:24])
    os.replace(temporary, destination)
    return {"width": width, "height": height,
            "capture_ms": round((time.monotonic()-start)*1000, 2),
            "path": str(destination)}
