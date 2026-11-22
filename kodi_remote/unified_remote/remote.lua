-- Kodi remote. The controls live in kodi.lua, which the Display Modes remote's Kodi tab uses too.
include("kodi.lua");

-- Opening the remote (or coming back to it) starts Kodi or brings it to the front.
events.focus = function ()
	actions.kodi_launch();
end
