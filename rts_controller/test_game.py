"""Identity-bound guard for disposable local test games, never global pkill."""
import json
import os
import signal
import subprocess
from pathlib import Path
from .ra2 import BridgeError


class TestGame:
    def __init__(self, pid, directory):
        if type(pid) is not int or pid <= 1: raise ValueError("Invalid game PID")
        self.pid = pid
        self.directory = Path(directory).resolve(strict=True)
        if not (self.directory / ".rts-controller-lab").is_file():
            raise BridgeError("Game directory is not marked as a disposable test copy")
        self.identity = self._identity()

    def _identity(self):
        proc = Path(f"/proc/{self.pid}")
        if (proc / "cwd").resolve(strict=True) != self.directory:
            raise BridgeError("Game PID does not belong to this test directory")
        args = (proc / "cmdline").read_bytes().split(b"\0")
        if not args or b"gamemd-spawn.exe" not in args[0].lower():
            raise BridgeError("Unexpected test executable")
        stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        return stat[19]  # process start time: proc stat field 22

    def valid(self):
        try: return self._identity() == self.identity
        except (OSError, BridgeError): return False

    def focused(self):
        if not self.valid(): return False
        try:
            w = json.loads(subprocess.check_output(["hyprctl", "activewindow", "-j"], timeout=.5))
            return w.get("pid") == self.pid and w.get("title") == "Red Alert 2"
        except (OSError, ValueError, subprocess.SubprocessError): return False

    def terminate_uncertain(self):
        if self.valid():
            # pidfd avoids delivering a signal to a recycled PID.
            fd = os.pidfd_open(self.pid)
            try:
                if self.valid(): signal.pidfd_send_signal(fd, signal.SIGTERM)
            finally: os.close(fd)

    def fits_output(self, output):
        if not self.focused(): return False
        try:
            monitors = json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"], timeout=.5))
            windows = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], timeout=.5))
            monitor = next(m for m in monitors if m["name"] == output)
            window = next(w for w in windows if w["pid"] == self.pid and w["title"] == "Red Alert 2")
            width, height = monitor["width"], monitor["height"]
            if monitor.get("transform", 0) % 2: width, height = height, width
            size = [width/monitor["scale"], height/monitor["scale"]]
            return (window["monitor"] == monitor["id"] and
                    window["at"] == [monitor["x"], monitor["y"]] and
                    all(abs(a-b) <= 2 for a, b in zip(window["size"], size)))
        except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
            return False


def require_private_network():
    links = json.loads(subprocess.check_output(["ip", "-j", "link", "show"], timeout=1))
    if {link.get("ifname") for link in links} != {"lo"}:
        raise BridgeError("Run the test game and controller in a loopback-only network namespace")
