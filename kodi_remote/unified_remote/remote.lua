local fs = libs.fs;
local keyboard = libs.keyboard;
local timer = libs.timer;
local win = libs.win;

-- kodi_remote (C:\Users\harri\Desktop\home_automation\kodi_remote)
local pythonw = "C:\\Users\\harri\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe";
local commands = "C:\\Users\\harri\\Desktop\\home_automation\\kodi_remote\\commands\\";
local modeFile = "C:\\Users\\harri\\DisplayModes\\logs\\current-mode.txt";

local function mode()
	local ok, text = pcall(function () return fs.read(modeFile); end);
	if ok and text and text ~= "" then return text; end
	return "Desk";
end

local function running()
	return win.window("kodi.exe") ~= 0;
end

local function refresh()
	local m = mode();
	local where = (m == "Couch") and "fullscreen on the TV" or "window on the Dell";
	if running() then
		layout.status.text = "Kodi: " .. m .. " mode, " .. where;
	else
		layout.status.text = "Kodi: not running. Tap the arrows or Select to start it.";
	end
end

local function run(cmd)
	os.start(pythonw, commands .. cmd .. ".pyw");
end

-- Keys only reach Kodi when it has focus, so bring it forward first (and start it if needed).
local function key(k)
	if not running() then
		actions.launch();
		return;
	end
	win.switchtowait("kodi.exe");
	keyboard.stroke(k);
end

-- Opening the remote (or coming back to it) starts Kodi or brings it to the front.
events.focus = function ()
	actions.launch();
end

--@help Start Kodi (fullscreen in Couch mode, a window in Desk mode) and bring it to the front
actions.launch = function ()
	layout.status.text = running() and "Kodi: bringing to front..." or "Kodi: starting...";
	run("launch");
	timer.timeout(refresh, 3000);
	timer.timeout(refresh, 12000);
end

--@help Navigate up
actions.up = function () key("up"); end
--@help Navigate down
actions.down = function () key("down"); end
--@help Navigate left
actions.left = function () key("left"); end
--@help Navigate right
actions.right = function () key("right"); end
--@help Select
actions.select = function () key("return"); end
--@help Back
actions.back = function () key("back"); end
--@help Home screen
actions.home = function () run("home"); end
--@help Context menu
actions.menu = function () key("c"); end
--@help Info
actions.info = function () key("i"); end
--@help Play or pause
actions.play_pause = function () key("space"); end
--@help Stop
actions.stop = function () key("x"); end
--@help Rewind
actions.rewind = function () key("r"); end
--@help Fast forward
actions.fast_forward = function () key("f"); end

--@help System volume up
actions.volume_up = function () keyboard.stroke("volume_up"); end
--@help System volume down
actions.volume_down = function () keyboard.stroke("volume_down"); end
--@help Mute
actions.volume_mute = function () keyboard.stroke("volume_mute"); end

--@help Toggle Kodi between fullscreen and a window
actions.fullscreen = function ()
	run("fullscreen");
end

--@help Close Kodi
actions.quit = function ()
	run("quit");
	layout.status.text = "Kodi: closing...";
	timer.timeout(refresh, 4000);
end
