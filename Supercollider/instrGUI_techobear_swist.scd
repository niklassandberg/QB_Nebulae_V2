var initAudioPath = "C:/Users/niksan/Desktop/wavetable_kasta";
var initScdFilePath = "C:/Users/niksan/Documents/QB_Nebulae_V2/Supercollider/Wave Tables/wave_tables.scd";

var guiAddr = NetAddr("127.0.0.1", 3010); // NebInterface OSC receiver

// Define the discrete pitch values (in Hz)
var pitchValues = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0];
// Snap mode flag
var pitchPressed = false;

var width = 600, height = 650; // Increased height for new UI elements
var filePathBox, audioPathBox;
var statusLamp, statusAudioPathLamp;

var startKnob, densityKnob, blendKnob, speedKnob, pitchKnob, sizeKnob, overlapKnob, windowKnob;

var buttonFile, buttonReset;

var upperText;
var background_color = Color.new255(0, 0, 40);


s.quit; // Stäng av servern om den redan körs
s.options.inDevice = "MME : MOTU Analog 1-2 (MOTU Audio Wav";
s.options.outDevice = "MME : MOTU Phones 1-2 (MOTU Audio Wav";


// INTERFACE INIT
NebInterface.audioPath = initAudioPath;
NebInterface.init(s);

Window.closeAll;
w = Window.new("NEBULAE V2", Rect(0, 0, width, height), false).alwaysOnTop_(true).background_(background_color).front;

upperText = StaticText.new(w, Rect(width/2-50, 20, 100, 20));
upperText.stringColor_(Color.white).string_("Nebulae SC").font_(Font("Yuppy TC", 18));

// KNOBS
startKnob = Knob.new(w, Rect(60, 100, 80, 80)).color_([Color.white, background_color, background_color]);
densityKnob = Knob.new(w, Rect(60, 250, 80, 80)).color_([Color.white, background_color, background_color]);
blendKnob = Knob.new(w, Rect(150, 380, 80, 80)).color_([Color.white, background_color, background_color]);
speedKnob = Knob.new(w, Rect(width/2-60, 90, 120, 120)).color_([Color.white, background_color, background_color]);
pitchKnob = Knob.new(w, Rect(width/2-60, 230, 120, 120)).color_([Color.white, background_color, background_color]);
sizeKnob = Knob.new(w, Rect(width-140, 100, 80, 80)).color_([Color.white, background_color, background_color]);
overlapKnob = Knob.new(w, Rect(width-140, 250, 80, 80)).color_([Color.white, background_color, background_color]);
windowKnob = Knob.new(w, Rect(width-230, 380, 80, 80)).color_([Color.white, background_color, background_color]);

// STATIC TEXTS
StaticText.new(w, Rect(width/3.3, 100, 100, 100)).stringColor_(Color.white).string_("speed").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/3.3, 240, 100, 100)).stringColor_(Color.white).string_("pitch").font_(Font("Yuppy TC", 20));
StaticText.new(w, Rect(width/7.5, 30, 200, 100)).stringColor_(Color.white).string_("start").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/1.25, 30, 200, 100)).stringColor_(Color.white).string_("size").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/1.28, 180, 200, 100)).stringColor_(Color.white).string_("overlap").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/8.25, 180, 200, 100)).stringColor_(Color.white).string_("density").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/3.6, 310, 200, 100)).stringColor_(Color.white).string_("blend").font_(Font("Yuppy TC", 18));
StaticText.new(w, Rect(width/1.6, 310, 200, 100)).stringColor_(Color.white).string_("window").font_(Font("Yuppy TC", 18));

// --- SYNK Help function ---
~syncGuiToNeb = {
    "Syncing GUI knobs to Nebulae...".postln;
    guiAddr.sendMsg("/neb/start", startKnob.value);
    guiAddr.sendMsg("/neb/density", densityKnob.value);
    guiAddr.sendMsg("/neb/blend", blendKnob.value);
    guiAddr.sendMsg("/neb/speed", speedKnob.value);
    guiAddr.sendMsg("/neb/pitch", pitchKnob.value);
    guiAddr.sendMsg("/neb/size", sizeKnob.value);
    guiAddr.sendMsg("/neb/overlap", overlapKnob.value);
    guiAddr.sendMsg("/neb/window", windowKnob.value);
    guiAddr.sendMsg("/neb/file", buttonFile.value);
    guiAddr.sendMsg("/neb/reset", buttonReset.value);
};

// HELPERS
~bindKnob = { |knob, oscName|
    knob.action_ { |k|
        guiAddr.sendMsg("/neb/" ++ oscName.asString, k.value);
    };
};

pitchKnob.action_ { |k|
    var val = k.value;
    if (pitchPressed) {
		var diffs = pitchValues.collect { |p| (p - val).abs };
		var idx = diffs.indexOf(diffs.minItem);
		val = pitchValues[idx];
		k.value = val;
    };
    ("pitch value: %".format(val)).postln;
    guiAddr.sendMsg("/neb/pitch", val);
};

~bindKnob.(startKnob, \start);
~bindKnob.(densityKnob, \density);
~bindKnob.(blendKnob, \blend);
~bindKnob.(speedKnob, \speed);
~bindKnob.(sizeKnob, \size);
~bindKnob.(overlapKnob, \overlap);
~bindKnob.(windowKnob, \window);

// FILE PATH UI
StaticText.new(w, Rect(50, 475, 200, 20))
    .string_("SC file path:")
    .stringColor_(Color.gray).font_(Font("Arial", 10));

filePathBox = TextField.new(w, Rect(50, 500, 500, 30))
    .string_(initScdFilePath)
    .font_(Font("Arial", 12))
    .background_(Color.black)
    .stringColor_(Color.white);

statusLamp = UserView.new(w, Rect(15, 505, 20, 20));
statusLamp.drawFunc = { |v|
    Pen.fillColor = v.getProperty(\color) ?? { Color.red };
    Pen.fillOval(v.bounds.moveTo(0,0));
};
statusLamp.setProperty(\color, Color.red);

// AUDIO PATH UI
StaticText.new(w, Rect(50, 545, 200, 20))
    .string_("Audio directory path:")
    .stringColor_(Color.gray).font_(Font("Arial", 10));

audioPathBox = TextField.new(w, Rect(50, 570, 500, 30))
    .string_(initAudioPath)
    .font_(Font("Arial", 12))
    .background_(Color.black)
    .stringColor_(Color.white);

statusAudioPathLamp = UserView.new(w, Rect(15, 575, 20, 20));
statusAudioPathLamp.drawFunc = { |v|
    Pen.fillColor = v.getProperty(\color) ?? { Color.red };
    Pen.fillOval(v.bounds.moveTo(0,0));
};
statusAudioPathLamp.setProperty(\color, Color.red);

// ACTIONS
filePathBox.action_({ |field|
    var path = field.string.replace("\\", "/");
    {
        statusLamp.setProperty(\color, Color.red); // Reset to red while loading
        statusLamp.refresh;
    }.defer;
    guiAddr.sendMsg("/neb/loadScFile", path);
    ("Sent OSC /neb/loadScFile " ++ path).postln;
});

audioPathBox.action_({ |field|
    var path = field.string.replace("\\", "/");
    if (File.exists(path)) {
        NebInterface.audioPath = path;
        {
            statusAudioPathLamp.setProperty(\color, Color.green);
            statusAudioPathLamp.refresh;
        }.defer;
        ("NebInterface.audioPath set to: " ++ path).postln;
    } {
        {
            statusAudioPathLamp.setProperty(\color, Color.red);
            statusAudioPathLamp.refresh;
        }.defer;
        ("ERROR: Directory does not exist: " ++ path).warn;
    };
});


buttonFile = Button.new(w, Rect(50, 420, 40, 40))
		.states_([
			["", Color.black, Color.white],
			["", Color.black, Color.gray]
		])
		.action_({ |btn|
			guiAddr.sendMsg("/neb/file", btn.value);
			("Sent OSC /neb/file: " ++ btn.value).postln;
		});

	buttonReset = Button.new(w, Rect(width-90, 420, 40, 40))
		.states_([
			["", Color.black, Color.white],
			["", Color.black, Color.gray]
		])
		.action_({ |btn|
			guiAddr.sendMsg("/neb/reset", btn.value);
			("Sent OSC /neb/reset: " ++ btn.value).postln;
		});

	StaticText.new(w, Rect(45, 400, 50, 20))
		.string_("file")
		.stringColor_(Color.white)
		.font_(Font("Yuppy TC", 14))
		.align_(\center);

	StaticText.new(w, Rect(width-95, 400, 50, 20))
		.string_("reset")
		.stringColor_(Color.white)
		.font_(Font("Yuppy TC", 14))
		.align_(\center);


// INITIAL STATE FOR AUDIO LAMP
if(NebInterface.audioPath.notNil && File.exists(NebInterface.audioPath)) {
    statusAudioPathLamp.setProperty(\color, Color.green);
};

// KEYBOARD HANDLING
~pLastDown = 0;
~debounceMS = 50;

w.view.keyDownAction_ { |view, char, mods|
    if (char.asString == "P") {
        var now = thisThread.clock.seconds * 1000;
        if ((now - ~pLastDown) > ~debounceMS) {
            pitchPressed = pitchPressed.not;
            ~pLastDown = now;
            "P pressed = true".postln;
        };
    };
	if (char.asString == "p") {
        var now = thisThread.clock.seconds * 1000;
        if ((now - ~pLastDown) > ~debounceMS) {
			var val = 0.6;
			pitchKnob.value = val;
			guiAddr.sendMsg("/neb/pitch", val);
            pitchPressed = false;
            ~pLastDown = now;
            "Double p pressed = true".postln;
        };
    };
};

~setupTestGUI = {
    "Setup OSC Receiver for GUI".postln;
	thisProcess.openUDPPort(3011);
    OSCdef(\instrup, { |msg|
        {
			~syncGuiToNeb.value;
            "GUI is up!".postln;
            statusLamp.setProperty(\color, Color.green);
            statusLamp.refresh;
        }.defer;
        {
			Window.allWindows.do { |win|
				if (win.view.children.any { |v| v.isKindOf(ScopeView) }) { win.close; }
			};
			FreqScope.new; s.scope;
        }.defer;
    }, '/sc/up');
};

NebInterface.onReset = ~setupTestGUI;
~setupTestGUI.value;

audioPathBox.doAction;
filePathBox.doAction;

w.onClose_({ Window.closeAll; s.freeAll; });


s.freeAll();




guiAddr.sendMsg("/neb/file", 1.0);
guiAddr.sendMsg("/neb/reset", 1.0);
//Vänta
guiAddr.sendMsg("/neb/file", 0.0);
guiAddr.sendMsg("/neb/reset", 0.0);