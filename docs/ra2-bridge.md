# Red Alert 2 bridge investigation

## Interface

The candidate bridge is [shmocz/ra2yrcpp](https://github.com/shmocz/ra2yrcpp),
reviewed at commit `ee215f5a01f709c52b1fe4dd333d16cbe5d5f146` with its
`ra2yrproto` submodule at `0ad72455bcdcf5626d0e17c3311ea82556da2ad3`.
It is an external GPL-3.0 project; this repository does not vendor its code or DLL.

The reader implements its JSON HTTP protocol on loopback. A blocking command
returns a Response containing PollResults, then a typed CommandResult.
Protocol defaults can omit zero-valued success fields. Envelope and result types
are checked, errors stop observation, and responses have a size limit.

Run against an already configured bridge:

```sh
python -m rts_controller.cli observe-ra2 --samples 100 --interval 0.1
```

The read-only CLI sends only InspectConfiguration (without update) and
GetGameState. The configuration check rejects single-step mode because upstream
GetGameState can advance simulation in that mode. Do not concurrently change
bridge configuration while observing. The HTTP endpoint is fixed to 127.0.0.1.

## Evidence and limits

GameState exposes currentFrame, houses, objects, selection, coordinates, health,
limbo/on-map state, and victory/defeat flags. The reader reports only local-player
objects. It reports how long the game frame has remained unchanged rather than
pretending repeated snapshots are fresh simulation updates.

`onMap` is NOT line of sight. The schema does not expose a reliable per-object
enemy-visibility flag or explicit object-destroyed event. Object addresses can be
reused, so they are not proven stable lifetime IDs. These limitations prevent
general autonomous combat. `control_ready` remains false. A separate explicitly
armed, owned-unit short-move experiment is available, not a general action adapter.

## Experimental movement

Install the optional dependency in a virtual environment:

```sh
python -m venv .venv
.venv/bin/pip install '.[ra2]'
```

For an offline, network-isolated test only, obtain the current actor ID from the
reader and the game PID from Hyprland. Replace these placeholders:

```sh
.venv/bin/python -m rts_controller.cli move-ra2 \
  --actor ACTOR_ID --game-pid GAME_PID --destination WORLD_X WORLD_Y --arm
```

The destination must be within 512 world units of the actor (not screen pixels).
The adapter requires advancing frames, a single human player, no victory/defeat,
an owned available actor, and the exact focused game PID/title. This player-count
check alone does not prove an offline session; offline launch is an operator requirement.
It refuses to disturb other selected units. Selection must be observed before
movement, and arrival within 96 world units is required for completion.
There is no attack implementation and no automatic retry of uncertain orders.

Orders use binary WebSocket messages with JSON payloads, as required by upstream.
One connection stays open through acknowledgment and result polling. Result IDs
must match the submitted order. Empty polls are not success and do not resubmit.
HTTP remains suitable for observation, but its short-lived connection is unsuitable
for pending game-loop actions. Transport completion is not proof of gameplay success.

Ctrl+C stops further orders. Already issued game orders are NOT cancelled, and
there is not yet a physical emergency-stop binding. Transport calls use short
timeouts; this remains experimental, not a hard-real-time controller.

## Installation policy for experiments

Use an isolated copy of a locally owned game installation and an offline campaign.
Upstream says its modified spawner is incompatible with standard online CnCNet
games. Preserve the regular launcher and executables. Configure singleStep=false
and configure an independently verified firewall/network namespace that excludes
untrusted hosts. Upstream listens on all IPv4 interfaces. Its address-regex setting
must NOT be treated as a verified access-control boundary. Setting the client URL
to loopback does not restrict who can reach the server. Do not run the bridge on
an exposed host. A game-file copy alone is not process or network isolation.

Do not publish game assets, saves, machine-specific launch scripts, or DLLs here.
Compatibility with the installed Ares/Phobos/spawner combination must be tested;
successful protocol tests against a synthetic HTTP server do not establish live
game compatibility.

## Local validation (2026-09-12)

- 24 automated tests passed, covering synthetic HTTP, mocked WebSocket polling,
  correlation/errors, no command resubmission, explicit arming, owned-unit bounds,
  paused frames, focus loss, ended missions, single-step refusal, and frame aging.
- The original game had no listener on port 14521.
- A separate game-file copy and upstream release DLL were prepared outside this
  repo. It shared the existing Wine prefix; it was not a fully isolated environment.
- Native full-monitor capture remains separate from observation; no crop is used.
- Live bridge startup and read-only state succeeded. Short local samples measured
  approximately 14–30 ms for configuration plus state retrieval. This does not
  measure capture, planning, input, or verified arrival latency.
- HTTP selection returned an empty pending result. The replacement WebSocket
  command path is tested with mocks but has not completed a verified live move.
- A replay attempt exited; a later resume showed a fatal-error dialog and an
  access violation (C0000005). No system core or OOM evidence was found. Root cause
  is unresolved; bridge/runtime compatibility is not established.
- The instrumented process was stopped and port 14521 was verified no longer
  listening. No successful live movement or combat is claimed.

Release archive SHA-256 inspected locally:
`b42842856b0f41256ab7bb7cb4f17f77edcd520b778aff8feffbf2845d13aee9`.
DLL SHA-256:
`59b8d235a44398f20d290b44b60b92d7127fada1353cfe1d2bfd0a8b646a0b28`.
These record the downloaded artifact, not a reproducible-build verification.
