NebInterface {
    classvar buses;
	classvar synthDefs;
    //classvar params;
	classvar remote;
	classvar server;
	classvar <>onReset;

    classvar initialized = false;
	
	classvar <>audioPath = nil;
	
	classvar <>storedBuffers;
	classvar busCallbacks;
	classvar busValues;

	
    *init { |s|
		var params;
        if (initialized) {
            "NebInterface already initialized".warn;
			if (thisThread.isKindOf(Routine)) {
				this.prSoftReset(s);
			} {
				"Not inside of a Routine, nothing will happens by design.".warn;
				^this;
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
		initialized = true;

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
			file.load;
        }, '/neb/loadScFile');
		
		OSCdef.new(\quit_n, { |msg|
            var code = "{ s.waitForBoot { NebInterface.init(s); s.quit; NebInterface.storedBuffers.clear; } }";
			var func = code.compile.value;
			func.value;
        }, '/neb/quit');

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
    
    *ready { |s|
        SystemClock.sched(2.0, { remote.sendMsg("/sc/up", 0); nil; });
		storedBuffers = IdentityDictionary.new;
        remote.sendMsg("/sc/up", 0);
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
			if (fname.findRegexp(regex).notNil) {
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
NebFreeze        : UGenValueRange { *busKey { ^\freeze } }
NebRecord        : UGenValueRange { *busKey { ^\record } }
NebSource        : UGenValueRange { *busKey { ^\source } }
NebFilestate     : UGenValueRange { *busKey { ^\filestate } }
NebSourcegate    : UGenValueRange { *busKey { ^\sourcegate } }

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
