# tvmirror


tvmirror — cast your Linux desktop to a TV/Android TV over Miracast (WFD).

Wraps FluxCast (https://github.com/IlyaP358/fluxcast) with the lessons that
actually cost time on Hyprland:

  * Chooses the CAPTURE BACKEND per compositor. Hyprland must use `portal`;
    anything that defaults to `x11grab` captures the XWayland root window,
    which is pure BLACK on a native Wayland session (measured: 9KB, luma 0).
    Symptom is a black TV with a live cursor, because the cursor arrives as
    HID input events rather than video.
  * Runs FluxCast's --doctor first and refuses to start on a hard failure.
  * Verifies the capture path is NOT black before pushing video to the TV.
  * Remembers the TV peer so you don't rescan every time.

Modes:
  tvmirror                 interactive TUI (peer picker + status)
  tvmirror run             connect to the chosen peer
    --peer <MAC>           skip the wrapper scan and connect to this sink
    --last                 reuse the most recently used sink
    --auto-fix             if the session dies early, retry with known sink workarounds
                           and remember whichever flags finally worked (per sink)
    --encoder auto|vaapi|nvenc|x264   hardware H.264 (needs a FluxCast with --wfd-encoder)
  tvmirror doctor          show the full capability report (--fresh bypasses the cache)
  tvmirror scan            list visible Miracast sinks
  tvmirror test            send the test pattern (proves transport works)
  tvmirror list            show saved peers
  tvmirror save <MAC> [name]  remember a peer
  tvmirror profile                    show per-sink flag profiles
  tvmirror profile-set <MAC> -- <fluxcast flags>   pin flags for one sink
  tvmirror profile-forget <MAC>       drop a sink profile
  tvmirror display         create/remove a Hyprland virtual display
  tvmirror backend         print the capture backend for this compositor

Sink profiles live in ~/.config/tvmirror/profiles.json. Hand-written rules match a
sink by name regex: {"by_name": [{"match": "^MyTV", "flags": ["--wfd-go-intent","15"]}]}

--auto-fix only helps when the session DIES. A sink that connects and stays black
needs a manual flag (e.g. `-- --wfd-aosp-pmt-pid`); pin it with profile-set.

