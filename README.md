# tvmirror

`tvmirror` casts a Linux desktop to a TV or Android TV over Miracast (Wi-Fi
Direct). It wraps
[FluxCast](https://github.com/IlyaP358/fluxcast) with the workarounds that
actually matter on Hyprland and other Wayland compositors.

## What it adds

- Picks the capture backend per compositor. Hyprland must use `portal`; a
  default `x11grab` path captures the XWayland root window, which is pure
  black on a native Wayland session.
- Runs FluxCast `--doctor` first and refuses to start on a hard failure.
- Verifies the capture path is not black before pushing video.
- Stores the last-used TV sink so you do not rescan every time.
- Supports per-sink flags and `--auto-fix` retry profiles.

## Modes

```text
tvmirror                         interactive TUI
tvmirror run                     connect to the chosen peer
tvmirror run --peer <MAC>        skip scanning
tvmirror run --last              reuse the most recently used sink
tvmirror run --auto-fix          retry after early failure and remember flags
tvmirror run --encoder auto      use VAAPI/NVENC/x264 when available
tvmirror doctor                  capability report; --fresh bypasses cache
tvmirror scan                    list visible Miracast sinks
tvmirror test                    send a test pattern
tvmirror list                    show saved peers
tvmirror save <MAC> [name]       remember a peer
tvmirror profile                 show per-sink flag profiles
tvmirror profile-set <MAC> -- ... pin flags for one sink
tvmirror profile-forget <MAC>    drop a sink profile
tvmirror display                 create/remove a Hyprland virtual display
tvmirror backend                 print the capture backend for this compositor
```

Sink profiles are stored in `~/.config/tvmirror/profiles.json`. Hand-written
rules match a sink by name regex:

```json
{
  "by_name": [
    { "match": "^MyTV", "flags": ["--wfd-go-intent", "15"] }
  ]
}
```

## Requirements

- Linux with a FluxCast installation reachable on `PATH` and `fluxcast`
  itself configured.
- Python 3.10 or newer.
- Hyprland (or another compositor); capture uses the portal backend where
  required.
- GStreamer plugins needed by FluxCast for H.264 capture and RTP.

## Installation

```sh
install -m 0755 bin/tvmirror ~/.local/bin/tvmirror
mkdir -p ~/.config/tvmirror
printf '{}\n' > ~/.config/tvmirror/peers.json
printf '{}\n' > ~/.config/tvmirror/profiles.json
```

FluxCast remains an external dependency. See the FluxCast repository for its
own setup, encoding and firewall requirements.

## Configuration

Runtime configuration lives under:

- `~/.config/tvmirror/peers.json`
- `~/.config/tvmirror/profiles.json`
- `~/.config/tvmirror/fix.json`
- `~/.cache/tvmirror/doctor.json`

For tests and isolated runs, the wrapper respects:

- `TVMIRROR_CONFIG`
- `TVMIRROR_CACHE`

Do not commit files from those directories to a repository. They may contain TV
identifiers and local capability information.

The optional upstream-flag test uses:

- `FLUXCAST_SRC` (path to the FluxCast `src/main.py` file)

## Development

Run the local test suite with:

```sh
pytest
```

The tests are pure logic and do not require a TV, GPU, or FluxCast runtime.

## Security notes

- Do not publish `peers.json`, `profiles.json`, `fix.json`, or doctor caches.
- The included `setup-sudo.sh` script in the FluxCast fork grants D-Bus
  properties access to a whole group. Review it before running.
- This wrapper calls FluxCast as a subprocess; treat FluxCast and its
  dependencies as part of your trust boundary.

## License

MIT. FluxCast itself is licensed under GPL-3.0; see upstream for its terms.
