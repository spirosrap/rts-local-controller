# RTS Local Controller

An experimental local controller for observable, verified RTS actions, initially
motivated by playing Red Alert 2 on Linux/Wayland.

**Status: pause-assisted selection and short movement verified in a live test.**
The controller reads state without advancing simulation, releases bounded game
frames, verifies movement, and leaves the game paused. Four short moves completed
in the first test session; an unsuccessful route stopped at its frame limit.
Full 2560×1440 monitor capture was checked against unchanged simulation frames.
This remains an experimental offline controller, not a campaign-playing bot or
human-speed player. Earlier free-running tests crashed; their root cause is not
proven fixed. The demo never controls your computer.

## Why

A screenshot → language-model decision → tool invocation loop is too slow for
reactive play. This project moves selection, execution, verification, timeouts,
and stopping into a local loop. A higher-level planner can supply objectives.

The complete monitor is captured at native resolution, without cropping or
resizing. Viewing frames and reading game state are separate concerns. A future
state adapter may use local full-frame vision or a documented game integration;
the candidate API and its limits are documented in [the bridge investigation](docs/ra2-bridge.md).

## Run

Python 3.11+; the core and tests use the standard library only.

```sh
python -m rts_controller.cli demo
python -m unittest discover -s tests -v
```

Read an already running, network-isolated game bridge:

```sh
python -m rts_controller.cli observe-ra2 --samples 10
```

The experimental live-order extra uses `websocket-client`. Start with the
[pause-assisted test guide](docs/pause-assisted.md). The older free-running path
is not the recommended test mode. See also
[bridge setup, restrictions, and historical test status](docs/ra2-bridge.md).
Do not expose the third-party bridge to a network or use it in online matches.

On a Wayland desktop supporting `grim`:

```sh
python -m rts_controller.cli capture --output DP-1
```

This saves the **entire output** to `runtime/frame.png` and reports its dimensions
and capture latency. Screenshots, runtime state, and game files are git-ignored.
Only one capture writer should use a given destination at a time.

## Controller contract

`Controller.step(state, monotonic_time)` returns at most one semantic action.
It first selects the actor, waits for a new observation confirming selection,
then issues the move or attack. Arrival confirms movement. An explicit destruction
event confirms an attack. A target disappearing into fog does **not** count.
An actor or target that becomes unavailable halts the order for replanning.

`runner.run` schedules the local adapter at a configurable rate (10 Hz default).
This is a scheduling target, not a measured perception/input speed guarantee.
An emergency-stop event is checked before observation and before execution.
Focus loss, stale observations, and timeouts halt commands. Adapters release
held input on exit. Blocking adapters must enforce their own short timeouts;
the stop cannot interrupt a blocked adapter call.

Adapter observations must provide stable unit IDs, world coordinates, trustworthy
selection/focus, explicit destruction events, a monotonically increasing sequence,
and a same-host monotonic capture timestamp. Camera movement must not alter world
coordinates. Input adapters must recheck the target game window and coordinate
mapping immediately before input. These are adapter requirements, not capabilities
of the current capture backend.

## Next milestones

1. Test repeated fresh launches and longer sessions; investigate the earlier crash.
2. Improve camera following, path failure reporting, and tick throughput.
3. Add a user-facing control panel and portable physical emergency-stop bindings.
4. Establish trustworthy enemy visibility, lifetime IDs, and destruction events
   before enabling attacks. Test camera movement and fog transitions.
5. Add target reacquisition, path failure recovery, and multi-unit behaviors.

No game binaries, maps, sprites, screenshots, credentials, or proprietary source
are included. Use an independently obtained copy of the game for future adapters.
