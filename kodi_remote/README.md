# kodi_remote

A Unified Remote remote called **Kodi** that opens Kodi on SpoonBox and drives it from the phone.

## Use it

Open the **Kodi** remote (or its home-screen shortcut). Opening it starts Kodi, or brings it to the
front if it is already running, and shows the remote:

| Row | Buttons |
| --- | --- |
| Top | Back, Home, context menu |
| Middle | D-pad: arrows, tap the centre to select |
| Playback | Rewind, play/pause, fast forward, stop |
| Volume | Windows volume down, mute, up, and Kodi's Info |
| Bottom | Fullscreen (toggles fullscreen and a window), Close Kodi |

The phone's volume keys also change the volume while the remote is open.

## Couch and Desk

Kodi follows the same mode as the Display Modes remote and puckstream
(`C:\Users\harri\DisplayModes\logs\current-mode.txt`):

- **Couch**: fullscreen on the TV.
- **Desk**: a window at 65% of the Dell, centred. **Fullscreen** makes it fullscreen.

Kodi is fitted to the mode when it starts, and again whenever the remote is opened after the mode
has changed. Otherwise a window you made fullscreen on purpose is left alone.

## How it works

- `unified_remote/`: the remote (layout and Lua). Arrows, select, back, play/pause and the rest are
  keystrokes sent to Kodi after bringing its window to the front, the same way Unified Remote's own
  Kodi Keyboard remote does it. Volume uses the Windows volume keys.
- `kodi_control.py`: starting Kodi, fullscreen/window, Home and Close. These go through Kodi's
  JSON-RPC on `localhost:9090`, which Kodi has on by default ("Allow remote control from
  applications on this system"). Its web server stays off.
- `commands/*.pyw`: one file per command, so the remote can start each with `pythonw`.

The only Kodi setting this changes is **Display mode** (fullscreen or windowed). Close Kodi puts it
back to fullscreen, Kodi's default, so starting Kodi any other way behaves as before.

Log: `logs/kodi_remote.log`.

## Setup

1. Copy `unified_remote/` to `C:\ProgramData\Unified Remote\Remotes\Custom\Kodi`, then click
   **Reload remotes** at http://localhost:9510/web.
2. On the phone, add a home-screen shortcut for the remote: long-press the home screen, choose
   **Widgets**, then **Unified Remote**, drag the remote shortcut out and pick **Kodi**.
