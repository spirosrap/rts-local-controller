# RTS Local Controller

An experimental local controller for observable, verified RTS actions, initially
motivated by playing Red Alert 2 on Linux/Wayland.

**Status: tested foundation, not yet a working Red Alert 2 bot.** There is no live
game-state reader, unit detector, or OS input adapter in this release. It does
not claim human-speed play. The simulation never controls your computer.

## Why

A screenshot → language-model decision → tool invocation loop is too slow for
reactive play. This project moves selection, execution, verification, timeouts,
and stopping into a local loop. A higher-level planner can supply objectives.

The complete monitor is captured at native resolution, without cropping or
resizing. Viewing frames and reading game state are separate concerns. A future
state adapter may use local full-frame vision or a documented game integration;
neither has been implemented yet.

## Run

Python 3.11+; the core and tests use the standard library only.

```sh
python -m rts_controller.cli demo
python -m unittest discover -s tests -v
```

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

1. Investigate an RA2/CnCNet game-state interface and its redistribution terms.
2. Implement a read-only adapter; compare its positions, selection, and events
   against full-screen recordings across camera movement and fog transitions.
3. Add bounded input, focus validation, runtime monitor mapping, and a physical
   emergency-stop binding. Avoid fixed desktop coordinates.
4. Test single-unit selection and movement, then one ship attack, with local
   action/observation logs and measured end-to-end latency.
5. Add target reacquisition, path failure recovery, and multi-unit behaviors.

No game binaries, maps, sprites, screenshots, credentials, or proprietary source
are included. Use an independently obtained copy of the game for future adapters.
