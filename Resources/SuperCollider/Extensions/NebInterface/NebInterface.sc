NebInterface {
    classvar buses;
	classvar synthDefs;
    //classvar params;
	classvar remote;
	classvar server;
	classvar <>onReset;

    classvar initialized = false;
	
	classvar <>audioPath = nil;
	// Processed wavetables (NebPatch.loadWavetables). Not in audioPath: that is
	// emptied on every USB load, and not in QB_Nebulae_V2: replaced by updates.
	classvar <>wavetableCachePath = "/home/alarm/cache/wavetables/";
	
	classvar <>storedBuffers;
	classvar busCallbacks;
	classvar busValues;

	// Values the patch saves itself (see *stateAt / *statePut), one file per patch.
	classvar <>statePath = "/home/alarm/QB_Nebulae_V2/Code/config/sc/";
	classvar <>saveDelay = 1.0;  // seconds after the last change before writing
	classvar currentPatch;       // name of the loaded .scd, nil when not loaded by Nebulae
	classvar state;
	classvar stateDirty = false;
	classvar saveTask;
	// Settings (see *initSettings): name -> value, name -> bus.
	classvar settings;
	classvar settingBuses;
	// Layout of the .scstate file. Version 0 (no \version key) was the state dictionary alone.
	classvar stateVersion = 1;
	// The NebPatch init gave back; +1 on every init, so an older NebPatch knows it's stale.
	classvar patch;
	classvar <generation = 0;

	/* Returns a NebPatch: the only way to get buffers (see NebPatch below).
	   s.waitForBoot {
	       var neb = NebInterface.init(s);
	       var rec = neb.addStereoAudioBuffer(20.0, true);
	       ...
	   };
	*/
    *init { |s|
		var params;
        if (initialized) {
            "NebInterface already initialized".warn;
			if (thisThread.isKindOf(Routine)) {
				this.prSoftReset(s);
			} {
				"Not inside of a Routine, nothing will happens by design.".warn;
				^patch;
			};
            //^this
        } {
			thisProcess.openUDPPort(3010);
            remote = NetAddr("127.0.0.1", 3011);
			onReset = {};
			storedBuffers = IdentityDictionary.new;
			busCallbacks = IdentityDictionary.new;
			busValues = IdentityDictionary.new;
			if (audioPath.isNil) {
				audioPath = "/home/alarm/audio/";
			};
        };
		
		server = s;
		synthDefs = [];
		buses = Dictionary.new;
		settingBuses = IdentityDictionary.new;
		initialized = true;
		generation = generation + 1;
		patch = NebPatch(s, generation);
		this.prReadState;

        // assign the array here instead
        params = [
            \speed, \pitch, \start, \size, \blend,
            \density, \overlap, \window, \reset, \freeze,
            \record, \file, \source, \filestate, \sourcegate,
            \speed_alt, \pitch_alt, \start_alt, \size_alt, \blend_alt,
            \density_alt, \overlap_alt, \window_alt, \reset_alt, \freeze_alt,
            \source_alt, \record_alt, \file_alt,
            \record_instr, \file_instr, \source_instr,
            \reset_instr, \freeze_instr
        ];

        params.do { |name|
            this.addBus(name, "/neb/%".format(name));
        };

        OSCdef.new(\loadScFile, { |msg|
            var file = msg[1].asString;
            OSCdef(\hasBeenLoaded).free; // remove previous handshake listener before loading new file
			this.prSaveState; // the old patch's values, before its clocks are cleared
			currentPatch = PathName(file).fileNameWithoutExtension;
			file.load;
        }, '/neb/loadScFile');
		
		OSCdef.new(\quit_n, { |msg|
            var code = "{ s.waitForBoot { NebInterface.init(s); s.quit; NebInterface.storedBuffers.clear; } }";
			var func = code.compile.value;
			this.prSaveState;
			func.value;
        }, '/neb/quit');

		^patch
    }

	*onBusChange { |name, action|
		busCallbacks[name] = action;
	}

    *addBus { |name, path, def = 0.0|
        var b = Bus.control(server, 1);
        b.set(def);
        buses[name] = b;
        OSCdef(name, { |msg| 
			var val = msg[1];
			b.set(val);
			busValues[name] = val;
			busCallbacks[name].value(val);
		}, path);
    }

	/* TODO: remove, will not be used.
	*addSynthReceiver { |symbol, action|
		OSCdef(symbol, { |msg| 
			action.value(msg[3]); 
		}, "/scsynth/" ++ symbol); // Ändrat + till ++
	}
	*/

    *bus { |name| ^buses[name] }
	*busValue { |name| ^busValues[name] ? 0.0 }

	/* Saved values of the patch: any key, any archivable SC object. They are
	   read in NebInterface.init and written by sclang itself (writeArchive)
	   saveDelay seconds after the last change, and at once when the next patch
	   is loaded or on /neb/quit. File: statePath ++ <patch> ++ ".scstate"
	   (not next to the .scd: /home/alarm/sc/ is erased on every USB load).

	   ~cutoff = NebInterface.stateAt(\cutoff, 1000);
	   NebInterface.statePut(\cutoff, ~cutoff);
	*/
	*stateAt { |key, default| ^state[key] ? default }

	*statePut { |key, value|
		state[key] = value;
		this.prStateChanged;
	}

	/* Settings: named numbers of the patch, each with its own control bus,
	   saved like the state (same file, same timing). Call it after
	   NebInterface.init and before the SynthDefs that read them.
	   Each entry: [name, default].

	   NebInterface.initSettings([
	       [\speed,  1.0],
	       [\reverb, 0.0],
	       [\tape,   0.0]
	   ]);

	   A saved value is used only if it is a number. Otherwise (first time, a
	   new setting, a value from another version of the patch) the default is
	   used. Saved settings that aren't declared any more are dropped.
	   Ranges are the patch's own business: NebInterface doesn't clip.

	   In a SynthDef:  NebSetting.kr(\speed)
	   From sclang:    NebInterface.setSetting(\speed, v)
	                   NebInterface.setting(\speed)
	*/
	*initSettings { |list|
		var saved = settings ? IdentityDictionary.new;
		settingBuses.do(_.free);
		settings = IdentityDictionary.new;
		settingBuses = IdentityDictionary.new;
		list.do { |entry|
			var name = entry[0].asSymbol, value = saved[name];
			if (value.isNumber.not) { value = entry[1] };
			settings[name] = value;
			settingBuses[name] = Bus.control(server, 1).set(value);
		};
	}

	*setting { |name| ^settings[name] }

	*settingBus { |name|
		var bus = settingBuses[name];
		if (bus.isNil) { Error("NebInterface: setting % not declared in initSettings".format(name)).throw };
		^bus
	}

	*setSetting { |name, value|
		if (settingBuses[name].isNil) { "NebInterface: setting % not declared in initSettings".format(name).warn; ^nil };
		settings[name] = value;
		settingBuses[name].set(value);
		this.prStateChanged;
		^value
	}

	*prStateChanged {
		stateDirty = true;
		saveTask.stop;
		saveTask = Routine { saveDelay.wait; this.prSaveState }.play(SystemClock);
	}

	*prReadState {
		var path, data;
		state = IdentityDictionary.new;
		settings = IdentityDictionary.new;
		stateDirty = false;
		if (currentPatch.isNil) { ^this };
		path = statePath ++ currentPatch ++ ".scstate";
		if (File.exists(path).not) { ^this };
		try {
			data = Object.readArchive(path);
		} { |err|
			"NebInterface: could not read %: %".format(path, err.errorString).warn;
		};
		if (data.isKindOf(IdentityDictionary).not) { ^this };
		case
		{ data[\version] == stateVersion } {
			state = data[\state] ? IdentityDictionary.new;
			settings = data[\settings] ? IdentityDictionary.new;
		}
		{ data[\version].isNil } {
			// Version 0: the state alone. Its numbers can become settings.
			state = data;
			settings = data.copy;
		}
		{ "NebInterface: % has unknown version %, using defaults".format(path, data[\version]).warn };
	}

	*prSaveState {
		var path;
		if (saveTask.notNil and: { thisThread !== saveTask }) { saveTask.stop };
		saveTask = nil;
		if (stateDirty.not or: { currentPatch.isNil }) { ^this };
		path = statePath ++ currentPatch ++ ".scstate";
		try {
			File.mkdir(statePath);
			IdentityDictionary[
				\version -> stateVersion,
				\state -> state,
				\settings -> settings
			].writeArchive(path);
			stateDirty = false;
		} { |err|
			"NebInterface: could not save %: %".format(path, err.errorString).warn;
		};
	}

	/* rawencoder: the .scd declares "speed,rawencoder" and/or "pitch,rawencoder"
	   in its nebconfig block. nebio then sends the encoder's steps and clicks
	   here, and the patch does everything else itself: value, buses, saving
	   (stateAt / statePut) and the encoder's two LEDs (led).
	   onStep gets the steps: -1 or 1 (-n / n if turned faster than nebio scans).
	   onClick gets 1 when pressed, 0 when released.
	   No steps arrive in secondary controls or the instr selector; a click
	   held when that happens still gets its 0.
	   Call it after NebInterface.init (init frees all OSCdefs).

	   NebInterface.rawEncoder(\pitch,
	       onStep:  { |steps| ... },
	       onClick: { |state| ... });
	*/
	*rawEncoder { |name, onStep, onClick|
		OSCdef(("rawenc_" ++ name).asSymbol, { |msg|
			onStep.value(msg[1]);
		}, "/neb/enc/%".format(name).asSymbol);
		if (onClick.notNil) { this.encoderClick(name, onClick) };
	}

	/* Press/release of the speed or pitch encoder, raw or not: nebio sends it
	   for both encoders in a SuperCollider patch (not in secondary controls or
	   the instr selector). For a hybrid encoder Python still does its own
	   thing with the click too (speed jumps between 0.625 and 0.375, pitch
	   goes back to 0.6).
	   func gets 1 when pressed, 0 when released.
	   Call it after NebInterface.init (init frees all OSCdefs).

	   NebInterface.encoderClick(\pitch, { |state| ... });
	*/
	*encoderClick { |name, func|
		OSCdef(("encclick_" ++ name).asSymbol, { |msg|
			func.value(msg[1]);
		}, "/neb/enc/%/click".format(name).asSymbol);
	}

	/* Colour of an encoder LED owned by the patch (rawencoder):
	   \speed_pos, \speed_neg, \pitch_pos or \pitch_neg, r g b 0-4095. */
	*led { |name, r, g, b|
		remote.sendMsg("/sc/led/%".format(name), r.asInteger, g.asInteger, b.asInteger);
	}
    
    *ready { |s|
		storedBuffers = IdentityDictionary.new;
        OSCdef.new(\hasBeenLoaded, { |msg|
            remote.sendMsg("/sc/up", 0);
        }, '/neb/hasbeenloaded');
    }
	
    *synthDef { |name, defFunc|
        synthDefs.add(name);
        ^SynthDef(name, defFunc);
    }

    *prSoftReset { |s|
	
		var savedBuffers;
	
		CmdPeriod.run;
		s.freeAll;
		
		//s.freeAllBuffers;
		//Just free that should be freed.
		savedBuffers = storedBuffers.values.as(Set);
		Buffer.cachedBuffersDo(s, { |buf|
			if (savedBuffers.includes(buf).not) {
				buf.free; 
			}
		});
		savedBuffers.clear;

		busCallbacks.clear;
		
		synthDefs.do { |name|
			s.sendMsg("/d_free", name);
		};
		
		// Clocks
		TempoClock.default.clear;
		SystemClock.clear;
		AppClock.clear;

		// OSC / MIDI
		if(buses.notNil) { buses.values.do { |b| b.free }; buses.clear };
		if(settingBuses.notNil) { settingBuses.do(_.free); settingBuses.clear };
		OSCdef.all.do(_.free);   // free OSC callbacks
		MIDIdef.freeAll;
		
		//This can just be done at runtime, gives error othervice if compiled
		//O.SCFunc._a.ll.do(_.free)
		
		//Dont do this, scsynth should be running.
		//s.quit;
		//s.boot;
			
		s.reset;
		s.sync; //s.reset; needs to been runned on server.
		s.sendMsg("/g_new", 1, 0, 0); //add default group, probably removed.
		s.sync;
		
		onReset.value;
		"Soft reset complete".postln;
    }
	
	*loadBuffers { | path, regex, storeBuff = false, callback |
	
		var paths = List.new;
		var loaded = 0;
		var buffers;

		PathName(path).filesDo { |pathname|
			var fname = pathname.fileName;
			if (regex.matchRegexp(fname)) {
				paths.add([fname.asSymbol, pathname.fullPath]);
			};
		};

		buffers = Array.newClear(paths.size);

		paths.do { |pair, i|
			
			var fname = pair[0].asSymbol;
			var fullPath = pair[1];
			
			if (storedBuffers.includesKey(fname)) {
				buffers[i] = storedBuffers[fname];
				loaded = loaded + 1;
				
				if (loaded == paths.size) {
					callback.(buffers);
				};
			} {
				Buffer.read(server, fullPath, action: { |buf|
					buffers[i] = buf;

					if (storeBuff) {
						storedBuffers[fname] = buf;
					};

					loaded = loaded + 1;
					if (loaded == paths.size) {
						callback.(buffers);
					};
				});
			};
		};
	}
	
	/*
		Example usage localy:
			s.waitForBoot {
				NebInterface.audioPath = "C:/Users/niksan/Desktop/wavetable_kasta";
				NebInterface.initAndLoadAudio(s, "^wt_.*wav$", true,
					{ |buffers|
					"All buffers loaded: %".format(buffers).postln;
					//doneFunc.(buffers);
				});
			};
	*/
	*initAndLoadAudio { | s, regex, storeBuff = false, callback |
		NebInterface.init(s);
		
		NebInterface.audioPath.postln;
		NebInterface.loadBuffers(NebInterface.audioPath, regex, storeBuff, callback);
	}
}

/* What NebInterface.init gives back: buffers can only be made through it,
   so they always come after init. When init runs again (next patch, or the
   patch calls it twice), the old NebPatch is stale and throws: the buffers
   it made are freed by that init (except stored ones).

   Each method waits until scsynth is done and returns the buffer(s), so it
   must run inside a Routine (s.waitForBoot is one).

   s.waitForBoot {
       var neb    = NebInterface.init(s);
       var rec    = neb.addStereoAudioBuffer(20.0, true);
       var tables = neb.loadAudio("^wt_.*wav$", true);
       ...
       NebInterface.ready(s);
   };

   storeBuff: kept in NebInterface.storedBuffers, so the next patch can get
   the same buffer back (with its content) instead of a new one.
*/
NebPatch {
	var <server, generation;

	*new { |server, generation| ^super.newCopyArgs(server, generation) }

	isValid { ^generation == NebInterface.generation }

	/* An empty buffer of seconds length, e.g. to record into. A stored
	   buffer with the same name, length and number of channels is reused;
	   one of another size is freed and a new one allocated. */
	addAudioBuffer { |seconds, numChannels = 1, storeBuff = false, name = \audioBuffer|
		var frames, buf;
		this.prCheck;
		frames = (server.sampleRate * seconds).asInteger;
		buf = NebInterface.storedBuffers[name];
		if (buf.notNil and: { buf.numFrames != frames or: { buf.numChannels != numChannels } }) {
			buf.free;
			NebInterface.storedBuffers.removeAt(name);
			buf = nil;
		};
		if (buf.isNil) {
			buf = Buffer.alloc(server, frames, numChannels);
			if (storeBuff) { NebInterface.storedBuffers[name] = buf };
			server.sync;
		};
		^buf
	}

	addStereoAudioBuffer { |seconds, storeBuff = false, name = \stereoBuffer|
		^this.addAudioBuffer(seconds, 2, storeBuff, name)
	}

	/* The files in path (default NebInterface.audioPath) whose names match
	   regex, as an Array of Buffers. Stored ones are reused by file name. */
	loadAudio { |regex, storeBuff = false, path|
		var buffers = List.new;
		this.prCheck;
		PathName(path ? NebInterface.audioPath).filesDo { |pathname|
			var fname = pathname.fileName.asSymbol;
			var buf;
			if (regex.matchRegexp(pathname.fileName)) {
				buf = NebInterface.storedBuffers[fname];
				if (buf.isNil) {
					buf = Buffer.read(server, pathname.fullPath);
					if (storeBuff) { NebInterface.storedBuffers[fname] = buf };
				};
				buffers.add(buf);
			};
		};
		server.sync;
		^buffers.asArray
	}

	/* Wavetable files (mono, frames of wtSize samples, e.g. 256 x 2048 as from
	   Serum) prepared for MultiWtOsc (WavetablePrep): every frame gets numMaps
	   band-limited copies, each step of ratio lower, so MultiWtOsc can play
	   each pitch without aliasing. Returns an Array of Buffers, like loadAudio.

	   Map 0 is the unfiltered table (fudgeFactor 0): nothing is cut where it
	   wouldn't alias. Pass MultiWtOsc the same numMaps and ratio (numTables,
	   ratio) and mapOffset: 1, so each map is used only up to the pitch where
	   it would start to alias. interpolation: 4 (cubic) is cleaner than 2.

	   The defaults (ratio sqrt 2, 16 maps) were the best measured at 48 kHz,
	   65 Hz .. 2 kHz: aliasing -64 .. -84 dB, harmonics up to 17 .. 23 kHz.
	   Upstream's ratio 2, 8 maps, fudgeFactor 0.5 aliases up to -41 dB.
	   Memory: positions x numMaps x wtSize x 4 bytes (34 MB for 256 x 2048).

	   Preparing takes a while, so the result is saved in
	   NebInterface.wavetableCachePath and reused as long as the audio file is
	   unchanged (same md5, or size + time on a PC). A changed file is prepared
	   again and its old cache file deleted.

	   var tables = neb.loadWavetables("^wt_.*wav$", storeBuff: true);
	   MultiWtOsc.ar(freq, pos, bufnum: tables[0], wtSize: 2048, numTables: 16, ratio: 2.sqrt,
	       interpolation: 4, mapOffset: 1)
	   pos: 0 .. NebPatch.wavetablePositions(tables[0], 2048, 16) - 1
	*/
	loadWavetables { |regex, wtSize = 2048, numMaps = 16, ratio = 1.4142135623731, storeBuff = false, path, fudgeFactor = 0|
		var buffers = List.new, cacheDir = NebInterface.wavetableCachePath;
		this.prCheck;
		File.mkdir(cacheDir);
		PathName(path ? NebInterface.audioPath).filesDo { |pathname|
			var src = pathname.fullPath, base, cacheFile, key, buf;
			if (regex.matchRegexp(pathname.fileName)) {
				base = pathname.fileNameWithoutExtension;
				cacheFile = cacheDir ++ "%_%_%x%r%f%.wav".format(base, this.prFileKey(src), wtSize, numMaps,
					ratio.round(0.001), fudgeFactor.round(0.001));
				key = PathName(cacheFile).fileName.asSymbol;
				buf = NebInterface.storedBuffers[key];
				if (buf.isNil) {
					if (this.prCacheValid(src, cacheFile, wtSize, numMaps).not) {
						this.prPrepareWavetable(src, cacheFile, base, wtSize, numMaps, ratio, fudgeFactor);
					};
					buf = Buffer.read(server, cacheFile);
					if (storeBuff) { NebInterface.storedBuffers[key] = buf };
				};
				buffers.add(buf);
			};
		};
		server.sync;
		^buffers.asArray
	}

	// Number of wavetable positions in a buffer from loadWavetables.
	*wavetablePositions { |buf, wtSize = 2048, numMaps = 16|
		^buf.numFrames div: (wtSize * numMaps)
	}

	// Same content -> same key. md5 on Linux; size and time elsewhere.
	prFileKey { |file|
		var md5;
		if (thisProcess.platform.name == \linux) {
			md5 = ("md5sum " ++ file.shellQuote).unixCmdGetStdOut.split($ )[0];
			if (md5.size == 32) { ^md5 };
		};
		^"%-%".format(File.fileSize(file), File.mtime(file))
	}

	// A cache file cut short (power off while writing) is made again.
	prCacheValid { |src, cacheFile, wtSize, numMaps|
		var srcFile, cache, ok;
		if (File.exists(cacheFile).not) { ^false };
		srcFile = SoundFile.openRead(src);
		cache = SoundFile.openRead(cacheFile);
		ok = srcFile.notNil and: { cache.notNil } and: {
			cache.numFrames == ((srcFile.numFrames div: wtSize) * numMaps * wtSize)
		};
		srcFile !? { srcFile.close };
		cache !? { cache.close };
		^ok
	}

	prPrepareWavetable { |src, cacheFile, base, wtSize, numMaps, ratio, fudgeFactor|
		var prep = WavetablePrep(src, wtSize, numMaps, ratio).fudgeFactor_(fudgeFactor), t = Main.elapsedTime;
		"NebPatch: preparing wavetable % ...".format(PathName(src).fileName).postln;
		prep.readSync;
		// Older cache files of this audio file (it was changed).
		(NebInterface.wavetableCachePath ++ base ++ "_*.wav").pathMatch.do { |old|
			if (old != cacheFile) { File.delete(old) };
		};
		prep.write(cacheFile);
		"NebPatch: % positions done in % s".format(prep.tables.size, (Main.elapsedTime - t).round(0.1)).postln;
	}

	prCheck {
		if (this.isValid.not) {
			Error("NebPatch: NebInterface.init was called again, use the NebPatch it returned").throw;
		};
		if (thisThread.isKindOf(Routine).not) {
			Error("NebPatch: call it inside a Routine (e.g. s.waitForBoot)").throw;
		};
	}
}

// -----------------------------
// Base generic class
// -----------------------------
UGenValueRange : UGen {
    
	*mapFunc { |val, srclo, srchi, min, max|
        ^val.linlin(srclo, srchi, min, max)
    }

    *kr { |srclo = 0, srchi = 1, min = nil, max = nil|
        var val;
		
		if(min.notNil and: max.isNil) {
			Error("NebInterface: tre number arguments not valid, 2 or 4 is").throw;
		};
		
		if(min.isNil or: max.isNil) {
			min = srclo;
			max = srchi;
			srclo = 0;
			srchi = 1;
		};
		
        val = In.kr(NebInterface.bus(this.busKey));
        ^this.mapFunc(val, srclo, srchi, min, max)
    }
}

// A setting declared with NebInterface.initSettings: NebSetting.kr(\reverb)
NebSetting {
	*kr { |name| ^In.kr(NebInterface.settingBus(name)) }
}

NebPitch         : UGenValueRange { *busKey { ^\pitch } }
NebSpeed         : UGenValueRange { *busKey { ^\speed } }
NebStart         : UGenValueRange { *busKey { ^\start } }
NebSize          : UGenValueRange { *busKey { ^\size } }
NebBlend         : UGenValueRange { *busKey { ^\blend } }
NebDensity       : UGenValueRange { *busKey { ^\density } }
NebOverlap       : UGenValueRange { *busKey { ^\overlap } }
NebWindow        : UGenValueRange { *busKey { ^\window } }
NebFile          : UGenValueRange { *busKey { ^\file } }
NebReset : UGenValueRange {

    *busKey { ^\reset } 
    
	/*
    *mapFunc { |val, srclo, srchi, min, max| 
        var fileSig = NebFile.kr(0, 1);
		var resetValue = val.linlin(srclo, srchi, min, max);
		var isHigh = fileSig > 0.5 && resetValue > 0.5;
        var trigger = Trig1.kr( HPZ1.kr(isHigh) > 0, 0.1);
        SendReply.kr(trigger, '/scsynth/zeroBuffer');
        ^resetValue
    }
	*/

}
NebRecord        : UGenValueRange { *busKey { ^\record } }
NebFilestate     : UGenValueRange { *busKey { ^\filestate } }
NebSource        : UGenValueRange { *busKey { ^\source } }
NebSourcegate    : UGenValueRange { *busKey { ^\sourcegate } }
NebFreeze        : UGenValueRange { *busKey { ^\freeze } }

NebSpeed_alt     : UGenValueRange { *busKey { ^\speed_alt } }
NebPitch_alt     : UGenValueRange { *busKey { ^\pitch_alt } }
NebStart_alt     : UGenValueRange { *busKey { ^\start_alt } }
NebSize_alt      : UGenValueRange { *busKey { ^\size_alt } }
NebBlend_alt     : UGenValueRange { *busKey { ^\blend_alt } }
NebDensity_alt   : UGenValueRange { *busKey { ^\density_alt } }
NebOverlap_alt   : UGenValueRange { *busKey { ^\overlap_alt } }
NebWindow_alt    : UGenValueRange { *busKey { ^\window_alt } }
NebReset_alt     : UGenValueRange { *busKey { ^\reset_alt } }
NebFreeze_alt    : UGenValueRange { *busKey { ^\freeze_alt } }
NebSource_alt    : UGenValueRange { *busKey { ^\source_alt } }
NebRecord_alt    : UGenValueRange { *busKey { ^\record_alt } }
NebFile_alt      : UGenValueRange { *busKey { ^\file_alt } }

NebRecord_instr  : UGenValueRange { *busKey { ^\record_instr } }
NebFile_instr    : UGenValueRange { *busKey { ^\file_instr } }
NebSource_instr  : UGenValueRange { *busKey { ^\source_instr } }
NebReset_instr   : UGenValueRange { *busKey { ^\reset_instr } }
NebFreeze_instr  : UGenValueRange { *busKey { ^\freeze_instr } }
