// NEBULAE V2 - instrument tester GUI
//
// Keys (window focused):
//   P (shift+p) = toggle pitch quantize (snaps pitch to pitchValues)
//   p           = reset pitch to pitchDefault
//
// Status lamps:  red = missing/error,  yellow = loading,  green = ok

// Default paths are built per platform. The .scd is found relative to this file
// (repo layout: Code/instr_tester/ -> ../../Supercollider/...), audio under the user's home.
// Edit these or use the Browse... buttons.
var thisDir = thisProcess.nowExecutingPath !? { |p| p.dirname };
var initAudioPath = Platform.userHomeDir +/+ "Desktop" +/+ "wavetable_kasta";
var initScdFilePath = (thisDir ?? { Platform.userHomeDir }) +/+ ".." +/+ ".." +/+ "Supercollider" +/+ "Wave Tables" +/+ "wave_tables.scd";

var guiAddr = NetAddr("127.0.0.1", 3010);

var pitchValues = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0];
var pitchDefault = 0.6;
var pitchQuantize = false;
var keyLastDown = 0, debounceSec = 0.05;

var width = 700, height = 660;
var bgColor, labelFont, smallFont, fieldFont, buttonFont;

var knobSpecs, knobs, knobLabels;
var filePathBox, audioPathBox, statusLamp, statusAudioPathLamp;
var quitScsynthButton, thisWin;

var makeLamp, setLamp, makePathRow, browse, normalizePath;
var loadScFile, setAudioPath, updateLabel, setPitch, setupTestGUI;

// Synth handshake (same as ControlHandler.synthIsUpStatus in controlhandler.py)
var pingInterval = 0.5, maxPings = 50;
var pingRoutine, synthIsUp = false, awaitingSynth = false;
var startPinging, waitForSynth;

bgColor = Color.new255(0, 0, 40);
// Font.defaultSansFace resolves to a sans font that exists on the current OS.
labelFont = Font(if (Font.availableFonts.includesEqual("Yuppy TC")) { "Yuppy TC" } { Font.defaultSansFace }, 16);
smallFont = Font(Font.defaultSansFace, 10);
fieldFont = Font(Font.defaultSansFace, 12);
buttonFont = Font(Font.defaultSansFace, 12, true);

// [name (also OSC address /neb/<name>), bounds]
knobSpecs = [
	[\start,   Rect(60, 100, 80, 80)],
	[\density, Rect(60, 250, 80, 80)],
	[\blend,   Rect(150, 395, 80, 80)],
	[\speed,   Rect(width/2 - 60, 90, 120, 120)],
	[\pitch,   Rect(width/2 - 60, 240, 120, 120)],
	[\size,    Rect(width - 240, 100, 80, 80)],
	[\overlap, Rect(width - 240, 250, 80, 80)],
	[\window,  Rect(width - 330, 395, 80, 80)]
];
knobs = IdentityDictionary.new;
knobLabels = IdentityDictionary.new;

NebInterface.audioPath = initAudioPath;
NebInterface.init(s);

Window.closeAll;
thisWin = Window.new("NEBULAE V2", Rect(0, 0, width, height), false)
	.alwaysOnTop_(true)
	.background_(bgColor)
	.front;
w = thisWin;

StaticText(w, Rect(0, 20, width, 24))
	.align_(\center)
	.stringColor_(Color.white)
	.string_("Nebulae SC")
	.font_(Font(labelFont.name, 18));

// ---------------------------------------------------------------- HELPERS

// Expands "~", e.g. "~/audio" works on macOS/Linux.
// Backslashes are only path separators on Windows; elsewhere they are legal filename chars.
normalizePath = { |path|
	path = path.asString.standardizePath;
	if (thisProcess.platform.name == \windows) { path = path.replace("\\", "/") };
	path
};

makeLamp = { |rect, color|
	var lamp = UserView(w, rect);
	lamp.drawFunc = { |v|
		Pen.fillColor = v.getProperty(\color) ?? { Color.red };
		Pen.fillOval(v.bounds.moveTo(0, 0).insetBy(1, 1));
	};
	lamp.setProperty(\color, color ? Color.red);
	lamp
};

setLamp = { |lamp, color|
	{
		if (lamp.notClosed) {
			lamp.setProperty(\color, color);
			lamp.refresh;
		};
	}.defer;
};

// Opens a native file/directory dialog. fileMode: 1 = existing file, 2 = directory.
browse = { |fileMode, currentPath, onOk|
	var start = normalizePath.(currentPath);
	start = if (PathName(start).isFolder) { start } { PathName(start).pathOnly };
	// Temporarily drop alwaysOnTop so the dialog isn't hidden behind the window.
	w.alwaysOnTop = false;
	FileDialog(
		{ |path| w.alwaysOnTop = true; onOk.(normalizePath.(path)) },
		{ w.alwaysOnTop = true },
		fileMode, 0, true, start
	);
};

// Label + lamp + text field + "Browse..." button. Returns [lamp, field].
makePathRow = { |top, title, initPath, fileMode, onChange|
	var lamp, field;
	StaticText(w, Rect(50, top, 300, 20))
		.string_(title)
		.stringColor_(Color.gray)
		.font_(smallFont);
	lamp = makeLamp.(Rect(15, top + 28, 20, 20));
	field = TextField(w, Rect(50, top + 22, 470, 30))
		.string_(initPath)
		.font_(fieldFont)
		.background_(Color.black)
		.stringColor_(Color.white)
		.action_({ |f| onChange.(f.string) });
	Button(w, Rect(530, top + 22, 80, 30))
		.states_([["Browse...", Color.white, Color.gray(0.3)]])
		.font_(buttonFont)
		.action_({ browse.(fileMode, field.string, onChange) });
	[lamp, field]
};

updateLabel = { |name|
	var str = "% %".format(name, knobs[name].value.round(0.01));
	if (name == \pitch and: { pitchQuantize }) { str = str ++ " [Q]" };
	knobLabels[name].string = str;
};

setPitch = { |val|
	if (pitchQuantize) {
		val = pitchValues.minItem { |p| (p - val).abs };
	};
	knobs[\pitch].value = val;
	updateLabel.(\pitch);
	guiAddr.sendMsg("/neb/pitch", val);
	("pitch value: %".format(val)).postln;
};

loadScFile = { |path|
	path = normalizePath.(path);
	filePathBox.string = path;
	if (File.exists(path)) {
		// The .scd's NebInterface.init does a soft reset that frees all OSCdefs and then
		// calls onReset; make sure it's ours (another GUI script may have replaced it).
		NebInterface.onReset = setupTestGUI;
		setLamp.(statusLamp, Color.yellow);
		guiAddr.sendMsg("/neb/loadScFile", path);
		("Sent OSC /neb/loadScFile " ++ path).postln;
		waitForSynth.value;
	} {
		setLamp.(statusLamp, Color.red);
		("ERROR: SC file does not exist: " ++ path).warn;
	};
};

setAudioPath = { |path|
	path = normalizePath.(path);
	audioPathBox.string = path;
	if (PathName(path).isFolder) {
		NebInterface.audioPath = path;
		setLamp.(statusAudioPathLamp, Color.green);
		("NebInterface.audioPath set to: " ++ path).postln;
	} {
		setLamp.(statusAudioPathLamp, Color.red);
		("ERROR: Directory does not exist: " ++ path).warn;
	};
};

// ---------------------------------------------------------------- KNOBS

knobSpecs.do { |spec|
	var name = spec[0], rect = spec[1];
	knobs[name] = Knob(w, rect).color_([Color.white, bgColor, bgColor]);
	knobLabels[name] = StaticText(w, Rect(rect.left - 20, rect.top - 24, rect.width + 40, 20))
		.align_(\center)
		.stringColor_(Color.white)
		.font_(labelFont);
	knobs[name].action_({ |k|
		guiAddr.sendMsg("/neb/" ++ name, k.value);
		updateLabel.(name);
	});
	updateLabel.(name);
};

knobs[\pitch].action_({ |k| setPitch.(k.value) });

// ---------------------------------------------------------------- QUIT

quitScsynthButton = Button(w, Rect(width - 110, 120, 80, 40))
	.states_([["QUIT", Color.white, Color.red(0.6)]])
	.font_(buttonFont)
	.action_({
		pingRoutine.stop;
		awaitingSynth = false;
		synthIsUp = false;
		guiAddr.sendMsg("/neb/quit", 1);
		setLamp.(statusLamp, Color.red);
	});

// ---------------------------------------------------------------- PATHS

#statusLamp, filePathBox = makePathRow.(490, "SC file (.scd):", initScdFilePath, 1, loadScFile);
#statusAudioPathLamp, audioPathBox = makePathRow.(560, "Audio directory:", initAudioPath, 2, setAudioPath);

Button(w, Rect(620, 512, 60, 30))
	.states_([["Reload", Color.white, Color.gray(0.3)]])
	.font_(buttonFont)
	.action_({ loadScFile.(filePathBox.string) });

// ---------------------------------------------------------------- KEYBOARD

w.view.keyDownAction_({ |view, char|
	var now = Main.elapsedTime;
	if ((now - keyLastDown) > debounceSec) {
		case
		{ char == $P } {
			pitchQuantize = pitchQuantize.not;
			keyLastDown = now;
			("pitch quantize: " ++ pitchQuantize).postln;
			if (pitchQuantize) { setPitch.(knobs[\pitch].value) } { updateLabel.(\pitch) };
		}
		{ char == $p } {
			pitchQuantize = false;
			keyLastDown = now;
			setPitch.(pitchDefault);
		};
	};
});

// ---------------------------------------------------------------- OSC FROM SC

// After /neb/loadScFile, ping /neb/hasbeenloaded every pingInterval seconds until the
// loaded .scd has called NebInterface.ready and answers with /sc/up (max maxPings pings).
startPinging = {
	pingRoutine.stop;
	
	if (awaitingSynth) {
	pingRoutine = Routine({
		var retries = 0;
		pingInterval.wait;
		while { synthIsUp.not and: { retries < maxPings } } {
			retries = retries + 1;
			"synth is not up yet, pinging SC... (%/%)".format(retries, maxPings).postln;
			guiAddr.sendMsg("/neb/hasbeenloaded", 0);
			pingInterval.wait;
		};
		if (synthIsUp.not) {
			awaitingSynth = false;
			"Synth did not respond after % pings, giving up!".format(maxPings).warn;
			setLamp.(statusLamp, Color.red);
		};
	}).play(AppClock);
	};
};

waitForSynth = {
	synthIsUp = false;
	awaitingSynth = true;
};

setupTestGUI = {
	"Setup OSC Receiver for GUI".postln;
	
	"Waiting for synth handshake...".postln;
	startPinging.value;
	
	thisProcess.openUDPPort(3011);
	OSCdef(\instrup, { |msg|
		// Several pings may be in flight; only react to the first /sc/up.
		if (synthIsUp.not) {
			synthIsUp = true;
			awaitingSynth = false;
			pingRoutine.stop;
			"Synth is up!".postln;
			setLamp.(statusLamp, Color.green);
			// Open the scopes once and keep them. Closing them here would /n_free scope synths
			// the reset's /g_freeAll already removed -> "FAILURE IN SERVER /n_free Node not found".
			{
				if (FreqScope.scopeOpen != true) {
					~nebFreqScope = FreqScope.new;
				} {
					// The soft reset's /g_freeAll killed the scope synth, and its AppClock.clear
					// cancels Server.initTree before ServerTree would restart it. doOnServerTree
					// drops the dead synth (no /n_free) and starts a new one, like stop/start.
					~nebFreqScope !? { |fs| fs.scope.doOnServerTree };
				};
				s.scope; // reuses the existing Stethoscope window if it is open
			}.defer;
		};
	}, '/sc/up');
	// NebInterface's soft reset runs CmdPeriod.run, and TempoClock.cmdPeriod clears the
	// queue of EVERY clock (even permanent ones), so the ping loop is dead by now.
	// onReset is called after the clocks are cleared, so restarting it here survives.
	if (awaitingSynth) {
		"Restarting synth handshake after soft reset".postln;
		startPinging.value;
	};
};

NebInterface.onReset = setupTestGUI;
setupTestGUI.value;

setAudioPath.(initAudioPath);
loadScFile.(initScdFilePath);

thisWin.onClose_({
	// This window's own ping loop, always safe to stop.
	
	NebInterface.onReset = {};
	pingRoutine.stop;
	// Qt runs onClose asynchronously. When the script is re-run, the old window's
	// onClose fires after the new GUI is set up, so only clean up if this window
	// is still the current one — otherwise we'd wipe the new GUI's onReset/OSCdef.
	if (w === thisWin) {
		OSCdef(\instrup).free;
		//NebInterface.onReset = {};
		Window.closeAll;
		s.freeAll;
	};
});
