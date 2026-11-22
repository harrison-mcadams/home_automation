# kodi_remote

A Unified Remote remote called **Kodi** that opens Kodi on SpoonBox and drives it from the phone.

## Use it

The same controls are also the **Kodi** tab of the Display Modes remote. Opening that tab starts
Kodi. Both remotes `include("kodi.lua")`, so copy `unified_remote/kodi.lua` into each installed
remote folder after changing it.

Open the **Kodi** remote (or its home-screen shortcut). Opening it starts Kodi, or brings it to the
front if it is already running, and shows the remote:

| Row | Buttons |
| --- | --- |
| Text box | Type, then press Enter on the phone keyboard or **Send** |
| Top | Back, Home, context menu |
| Middle | D-pad: arrows, tap the centre to select |
| Playback | Rewind, play/pause, fast forward, stop |
| Volume | Windows volume down, mute, up, and Kodi's Info |
| Bottom | Fullscreen (toggles fullscreen and a window), Close Kodi |

The phone's volume keys also change the volume while the remote is open.

## Couch and Desk

Kodi follows the same mode as the Display Modes remote and puckstream
(`C:\Users\harri\DisplayModes\logs\current-mode.txt`):

Kodi always opens fullscreen, on the main screen of the current mode:

- **Couch**: the TV.
- **Desk**: the Dell.

Every time the remote is opened, Kodi is put back to fullscreen. If the mode changed while Kodi was
open, it moves to the new mode's screen. **Fullscreen** on the remote toggles to a 65% window and
back.

Switching to **Couch** also starts Kodi fullscreen on the TV: `C:\Users\harri\DisplayModes\settings.json`
has `commands\couch.pyw` in Couch's `Launch` list (as `{"Path": pythonw, "Args": couch.pyw}`, which
Set-DisplayMode.ps1 supports since 2026-11-22). From there Yatse can drive it.

## Yatse

Kodi's web server is on for Yatse at port 8081 (8080 is SABnzbd), user `kodi`; the password is in
`logs/yatse-login.txt` (not committed). Change Kodi's network settings only while Kodi is closed, by
editing `userdata/guisettings.xml`: changing them over JSON-RPC while it runs crashed Kodi 21.3.

## Typing

Open search in Kodi and type in the remote's text box (or Yatse's keyboard), then press Enter or
**Send**. Text goes into whatever text box has focus: the search bar, or Kodi's on-screen keyboard
(confirmed with OK).

Arctic Fuse 2 normally opens search with the A to Z letters focused, where typed text is ignored.
`skin.arctic.fuse.2/1080i/Includes_Search.xml` (in Kodi's addons folder) is edited so search opens
with the search bar (control 9099) focused instead: `defaultcontrol` and the first `SetFocus` in
`Search_Window_Def`, both marked `SpoonBox`. A skin update undoes this; redo it and restart Kodi.

## How it works

- `unified_remote/`: the remote (layout and Lua). Arrows, select, back, play/pause and the rest are
  keystrokes sent to Kodi after bringing its window to the front, the same way Unified Remote's own
  Kodi Keyboard remote does it. Volume uses the Windows volume keys.
- `kodi_control.py`: starting Kodi, fullscreen/window, Home, typing (`Input.SendText`) and Close. These go through Kodi's
  JSON-RPC on `localhost:9090`, which Kodi has on by default ("Allow remote control from
  applications on this system").
- `commands/*.pyw`: one file per command, so the remote can start each with `pythonw`.

The only Kodi setting this changes is **Display mode** (fullscreen or windowed). Close Kodi puts it
back to fullscreen, Kodi's default, so starting Kodi any other way behaves as before.

Log: `logs/kodi_remote.log`.

## Setup

1. Copy `unified_remote/` to `C:\ProgramData\Unified Remote\Remotes\Custom\Kodi`, then click
   **Reload remotes** at http://localhost:9510/web.
2. On the phone, add a home-screen shortcut for the remote: long-press the home screen, choose
   **Widgets**, then **Unified Remote**, drag the remote shortcut out and pick **Kodi**.
