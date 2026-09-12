# Pause-assisted Red Alert 2 test mode

This is an offline experiment for a disposable game-file copy and a separately
copied Wine prefix. It does not install anything into Steam or change the normal
launcher. Linux, Hyprland, `ip`, `unshare`, `nsenter`, `grim`, and a working local
Wine/Proton installation are required.

## Control contract

- Start the test bridge with `singleStep: true`; the client never toggles this
  setting in a running mission or uses the Escape menu to pause.
- `ReadValue(data.gameState)` reads stored state without releasing simulation.
- `GetGameState` deliberately releases one iteration of the upstream game-loop
  gate. This side effect is why the ordinary reader still rejects singleStep mode.
- Verify the pre-release frame, then wait for exactly the next frame. Never retry
  an uncertain release. Repeated reads must remain on that frame between actions.
- Submit a selection/move over a binary WebSocket connection, keep the connection
  open, release one frame, and collect the matching command result. Selection and
  arrival are independently verified from state, not inferred from an acknowledgment.
- Capture the entire chosen monitor, with matching simulation frames before and
  after capture. The game must fill that monitor and be focused. This brackets the
  capture; it does not establish a renderer-level pixel/frame synchronization fence.

The game remains paused while the model thinks or after a CLI command returns.
Ordinary manual UI interaction is not supported while the simulation gate is
closed. Music/video playback can have a separate clock. Camera following is not
implemented; a scripted camera can leave a selected unit outside the view.

### Additional controls and observation

`--actor ACTOR_ID --stop-actor` issues a stop and verifies three consecutive
unchanged positions with a Stop/Guard mission. The total budget is 120 frames;
units can finish their current cell movement before stopping. A timeout is not
reported as success. This was live-verified at frame 1138 and the position stayed
unchanged through frame 1258.

Observations now include owned-unit type names (from the initial type table),
infantry/building/etc. categories, current orders, destinations, deployment state,
credits, power, and production information where supplied by the bridge. Missing
information remains null. Every successful CLI operation also reports before/after
changes. An owned object disappearing is **not** called destruction; its cause is
unknown. No Tanya-specific actor lookup is used.

`--center` is an **experimental camera diagnostic**, not a verified camera fix.
It reads CenterView from the test copy's KeyboardMD.ini and rejects unsupported or
conflicting bindings. The configured keypad binding is 12; the proposed isolated
test binding is J (74). It sends through Hyprland, releases the key even on step
failure, and leaves simulation paused. Inspect the complete capture afterward:
`camera_key_sent` means delivery was acknowledged, not that the camera centered.
Do not substitute F: the game's own command descriptions define Follow as making
selected objects follow another object, not camera following.

The camera investigation also found that constructing a Hyprland dispatcher is
not executing it: runtime focus needs `hl.dispatch(hl.dsp.focus(...))` through
`hyprctl eval`. This is a runtime action, not a compositor configuration change.

Text-oriented virtual keyboards can assign temporary physical codes. The tested
`wtype` keypad attempt opened the Options menu and caused the frame guard to stop;
the menu was closed and the session recovered without restarting. Do not use that
method for game camera control. See [wtype source](https://github.com/atx/wtype/blob/master/main.c).

### Remaining implementation milestones

1. Verify camera centering and visible pointer behavior in a fresh isolated run;
   add automatic recentering only after positive live evidence.
2. Generalize selection to multiple owned actors and add verified deployment.
3. Add player-visible target evidence and combat outcomes; do not expose hidden
   enemies as actionable or treat disappearance as a kill.
4. Add production/placement commands and verify queue, resource, and object changes
   in a mission with a base. Current production support is observation only.
5. Add an objective/task planner and test several missions with different unit
   sets. Neither a mission-specific script nor passing unit tests proves general play.

## Preparing and launching

Obtain the external bridge described in [the investigation](ra2-bridge.md).
Keep it and all game assets outside this repository. The launcher expects the
tested Ares/CnCNet-Spawner/Phobos/Syringe combination and `gamemd-spawn.exe`.
It is not a universal launcher for every Red Alert installation.

After making the two disposable copies, create marker files named
`.rts-controller-lab` in the game copy and `.rts-controller-prefix` in its prefix.
Do not mark the original directories. In the copied `ra2yrcpp.json`, set:

```json
{"port":14521,"singleStep":true,"parseMapDataInterval":15,
 "allowedHostsRegex":"^127\\.0\\.0\\.1$","logFilename":"ra2yrcpp.log"}
```

The regex is not relied on for isolation. The namespace has only loopback and no
external network interface. Filesystem access is not sandboxed. Do not run another
controller or change bridge configuration during a test.

From the repository, install the optional dependency and start the lab:

```sh
python -m venv .venv
.venv/bin/pip install -e '.[ra2]'
.venv/bin/python -m rts_controller.lab \
  --game-dir /absolute/path/to/game-copy \
  --prefix /absolute/path/to/prefix-copy \
  --wine /absolute/path/to/wine
```

The launcher prints `namespace_pid`. Keep that terminal open. Wait for the mission
to load, place it fullscreen on the intended monitor, and obtain its game PID from
`hyprctl clients -j`. Replace the capitalized placeholders in the commands below.
All controller commands run in the same namespace. A normal-host invocation is refused.

```sh
nsenter -t NAMESPACE_PID --user --net --preserve-credentials \
  .venv/bin/python -m rts_controller.cli paused-ra2 \
  --game-pid GAME_PID --game-dir /absolute/path/to/game-copy \
  --output DP-1 --arm
```

That command only observes and captures; it does not release frames. Append
`--frames 5` to advance exactly five iterations and re-pause, or append
`--actor ACTOR_ID --move WORLD_X WORLD_Y` for a short movement. Read the current
owned actor ID from the observation. IDs are session-specific and not stable
across launches. The destination must be within 512 world units, and arrival is
within 96 world units to accommodate cell-based movement. Default total movement
budget is 120 frames; unreachable routes fail rather than trigger blind retries.

## Stop and recovery

Ctrl+C requests a stop at the next safe boundary. A global shortcut can invoke:

```sh
.venv/bin/python -m rts_controller.cli stop --stop-file /absolute/path/to/repo/runtime/STOP
```

Use the same stop-file path in the running CLI. The test machine has
Super+Shift+F12 bound to create this latch. Clearing it does not advance simulation:

```sh
.venv/bin/python -m rts_controller.cli clear-stop
```

An already released frame may finish. There is no continuous run to cancel;
existing unit orders remain in the game and would continue on future steps.
If a queued game command becomes uncertain, the controller terminates only its
identity-checked, marked test-game process before disconnecting. This can lose
unsaved test progress. No global process killing or automatic retry is used.
On an ordinary path failure, the game stays paused instead.

## Live evidence — 2026-09-12

- Separate game files and Wine prefix; only loopback present in test namespace.
  Port 14521 listened inside that namespace, not on the normal host network.
- Initial frame 0 advanced to 5, then remained at 5 over subsequent observations.
- Tanya selection verified at frame 6; first short move reached its tolerance at
  frame 19 (14 total frames from the pre-selection state).
- Further moves reached tolerance at frames 40 and 63. A different route exhausted
  its 120-frame budget at 183, without a crash or unverified retry.
- Three later 120-frame batches ended at 307, 427, and 547 (after a small keyboard
  camera experiment). The public CLI completed another move at frame 562.
- A stop-latched five-frame request remained at 562 and exited with status 130.
- Native full-monitor captures were 2560×1440. No image cropping/downscaling was
  performed by the controller. The viewer may resize images for display.
- 43 automated tests pass, including mocked transport and simulated stepping.
  These do not replace repeated live-launch and long-session testing.

Two timed repeated moves took 5.638 and 9.884 wall-clock seconds on this machine;
this intentionally conservative prototype is not human-speed play.
The earlier free-running crash has not been conclusively diagnosed or fixed.
The pause-assisted session avoided that failure, which is narrower evidence.
No attacks or fog-of-war targeting are enabled: trustworthy enemy visibility and
destruction events remain missing from the current integration.
