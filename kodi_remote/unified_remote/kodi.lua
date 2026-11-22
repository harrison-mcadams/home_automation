-- Kodi controls, shared by the Kodi remote and the Kodi tab of the Display Modes remote.
-- Include it with include("kodi.lua"). Layout ids it uses: kodi_status (label), kodi_typed (text).
-- Source: C:\Users\harri\Desktop\home_automation\kodi_remote\unified_remote\kodi.lua

local fs = libs.fs;
local keyboard = libs.keyboard;
local timer = libs.timer;
local win = libs.win;

local pythonw = "C:\\Users\\harri\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe";
local commands = "C:\\Users\\harri\\Desktop\\home_automation\\kodi_remote\\commands\\";
local typedFile = "C:\\Users\\harri\\Desktop\\home_automation\\kodi_remote\\logs\\typed.txt";
local modeFile = "C:\\Users\\harri\\DisplayModes\\logs\\current-mode.txt";

local function mode()
	local ok, text = pcall(function () return fs.read(modeFile); end);
	if ok and text and text ~= "" then return text; end
	return "Desk";
end

local function running()
	return win.window("kodi.exe") ~= 0;
end

local function status(text)
	pcall(function () layout.kodi_status.text = text; end);
end

local function refresh()
	local m = mode();
	local where = (m == "Couch") and "fullscreen on the TV" or "fullscreen on the Dell";
	if running() then
		status("Kodi: " .. m .. " mode, " .. where);
	else
		status("Kodi: not running. Tap Open Kodi to start it.");
	end
end

local function run(cmd)
	os.start(pythonw, commands .. cmd .. ".pyw");
end

-- Keys only reach Kodi when it has focus, so bring it forward first (and start it if needed).
local function key(k)
	if not running() then
		actions.kodi_launch();
		return;
	end
	win.switchtowait("kodi.exe");
	keyboard.stroke(k);
end

--@help Open Kodi fullscreen (TV in Couch mode, Dell in Desk mode)
actions.kodi_launch = function ()
	status(running() and "Kodi: bringing to front..." or "Kodi: starting...");
	run("launch");
	timer.timeout(refresh, 3000);
	timer.timeout(refresh, 12000);
end

--@help Kodi: up
actions.kodi_up = function () key("up"); end
--@help Kodi: down
actions.kodi_down = function () key("down"); end
--@help Kodi: left
actions.kodi_left = function () key("left"); end
--@help Kodi: right
actions.kodi_right = function () key("right"); end
--@help Kodi: select
actions.kodi_select = function () key("return"); end
--@help Kodi: back
actions.kodi_back = function () key("back"); end
--@help Kodi: home screen
actions.kodi_home = function () run("home"); end
--@help Kodi: context menu
actions.kodi_menu = function () key("c"); end
--@help Kodi: info
actions.kodi_info = function () key("i"); end
--@help Kodi: play or pause
actions.kodi_play_pause = function () key("space"); end
--@help Kodi: stop
actions.kodi_stop = function () key("x"); end
--@help Kodi: rewind
actions.kodi_rewind = function () key("r"); end
--@help Kodi: fast forward
actions.kodi_fast_forward = function () key("f"); end

--@help Volume up
actions.kodi_volume_up = function () keyboard.stroke("volume_up"); end
--@help Volume down
actions.kodi_volume_down = function () keyboard.stroke("volume_down"); end
--@help Mute
actions.kodi_volume_mute = function () keyboard.stroke("volume_mute"); end

--@help Kodi: toggle fullscreen and a window
actions.kodi_fullscreen = function () run("fullscreen"); end

-- Typing: open a search (or any text box) in Kodi so its on-screen keyboard shows, type on the
-- phone, then press Enter on the phone keyboard or the Send button.
local typed = "";

actions.kodi_text_changed = function (text)
	typed = text or "";
end

--@help Kodi: type the text box into Kodi's on-screen keyboard
actions.kodi_send_text = function ()
	if typed == "" then return; end
	fs.write(typedFile, typed);
	run("type");
	typed = "";
	pcall(function () layout.kodi_typed.text = ""; end);
end

actions.kodi_text_done = function (text)
	actions.kodi_text_changed(text);
	actions.kodi_send_text();
end

--@help Close Kodi
actions.kodi_quit = function ()
	run("quit");
	status("Kodi: closing...");
	timer.timeout(refresh, 4000);
end
