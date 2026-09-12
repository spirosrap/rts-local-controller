"""Launch a marked game copy in a private network namespace (Linux only).

This is network isolation, not a filesystem sandbox. Supply a separately copied
Wine prefix. No binaries, configuration, or original game files are modified.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from .test_game import require_private_network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--wine", type=Path, required=True)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    game = args.game_dir.resolve(strict=True)
    prefix = args.prefix.resolve(strict=True)
    wine = args.wine.resolve(strict=True)
    if not (game / ".rts-controller-lab").is_file():
        parser.error("Use a marked disposable game copy")
    if not (prefix / ".rts-controller-prefix").is_file():
        parser.error("Use a marked separately copied Wine prefix")
    config = json.loads((game / "ra2yrcpp.json").read_text())
    if config.get("singleStep") is not True:
        parser.error("Test copy must have singleStep=true before launch")
    if not args.inside:
        command = ["unshare", "--user", "--map-root-user", "--net", sys.executable,
                   "-m", "rts_controller.lab", "--inside", "--game-dir", str(game),
                   "--prefix", str(prefix), "--wine", str(wine)]
        os.execvp(command[0], command)
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    require_private_network()
    print(json.dumps({"namespace_pid": os.getpid(), "game_dir": str(game),
                      "network": "loopback-only", "mode": "single-step"}), flush=True)
    environment = dict(os.environ, WINEPREFIX=str(prefix))
    command = [str(wine), "Syringe.exe", "-SPAWN", "-i=Ares.dll", "-i=CnCNet-Spawner.dll",
               "-i=Phobos.dll", "-i=libra2yrcpp.dll", "gamemd-spawn.exe",
               "--args=-SPAWN -LOG -CD -Include -Inheritance -RA2ModeSaveID=0x8d113b94"]
    result = subprocess.run(command, cwd=game, env=environment)
    raise SystemExit(result.returncode)


if __name__ == "__main__": main()
