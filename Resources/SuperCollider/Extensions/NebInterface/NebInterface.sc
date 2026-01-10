NebInterface {
    classvar buses;   // plain classvar
    classvar params;  // declare, but don't assign here!

    classvar initialized = false;


    *init { |s|
       
        //if (initialized) {
        //    "NebInterface already initialized".warn;
        //    ^this
        //};

        this.softReset(s);
		
        if(buses.notNil) { buses.values.do { |b| b.free }; buses.clear };
        buses  = Dictionary.new;
		
		//OSCdef.all.do(_.free);   // free OSC callbacks

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

        thisProcess.openUDPPort(3010);
        ~remote = NetAddr("127.0.0.1", 3011);

        params.do { |name|
            this.addBus(name, "/neb/%".format(name));
        };

        OSCdef.new(\loadScFile, { |msg|
			msg[1].load;
        }, '/neb/loadScFile');
    }

    *addBus { |name, path, def = 0.0|
        var b = Bus.control(Server.default, 1);
        b.set(def);
        buses[name] = b;
        OSCdef(name, { |msg| b.set(msg[1]) }, path);
    }

    *bus { |name| ^buses[name] }
    
    *ready { |s|
        SystemClock.sched(2.0, { ~remote.sendMsg("/sc/up", 0); nil; });
        ~remote.sendMsg("/sc/up", 0);
    }

    *softReset { |s|
        CmdPeriod.run;           // stop all Routines/Patterns
		s.freeAll;               // stop all synths
		s.freeAllBuffers;        // free buffers
		//currentEnvironment.clear; //find a better GC for this

        "Soft reset complete".postln;
    }
}

NebPitch : UGen {
    *kr { |min = 20, max = 2000|
        ^In.kr(NebInterface.bus(\pitch)).linlin(0, 1, min, max)
    }
}

NebSpeed : UGen {
    *kr { |min = 0.0, max = 2.0|
        ^In.kr(NebInterface.bus(\speed)).linlin(0, 1, min, max)
    }
}

NebStart : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\start)).linlin(0, 1, min, max)
    }
}

NebSize : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\size)).linlin(0, 1, min, max)
    }
}

NebBlend : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\blend)).linlin(0, 1, min, max)
    }
}

NebDensity : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\density)).linlin(0, 1, min, max)
    }
}

NebOverlap : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\overlap)).linlin(0, 1, min, max)
    }
}

NebWindow : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\window)).linlin(0, 1, min, max)
    }
}

NebReset : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\reset)).linlin(0, 1, min, max)
    }
}

NebFreeze : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\freeze)).linlin(0, 1, min, max)
    }
}

NebRecord : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\record)).linlin(0, 1, min, max)
    }
}

NebFile : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\file)).linlin(0, 1, min, max)
    }
}

NebSource : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\source)).linlin(0, 1, min, max)
    }
}

NebFilestate : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\filestate)).linlin(0, 1, min, max)
    }
}

NebSourcegate : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\sourcegate)).linlin(0, 1, min, max)
    }
}

// ---------- ALT versions ----------

NebSpeed_alt : UGen {
    *kr { |min = 0.0, max = 2.0|
        ^In.kr(NebInterface.bus(\speed_alt)).linlin(0, 1, min, max)
    }
}

NebPitch_alt : UGen {
    *kr { |min = 20, max = 2000|
        ^In.kr(NebInterface.bus(\pitch_alt)).linlin(0, 1, min, max)
    }
}

NebStart_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\start_alt)).linlin(0, 1, min, max)
    }
}

NebSize_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\size_alt)).linlin(0, 1, min, max)
    }
}

NebBlend_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\blend_alt)).linlin(0, 1, min, max)
    }
}

NebDensity_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\density_alt)).linlin(0, 1, min, max)
    }
}

NebOverlap_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\overlap_alt)).linlin(0, 1, min, max)
    }
}

NebWindow_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\window_alt)).linlin(0, 1, min, max)
    }
}

NebReset_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\reset_alt)).linlin(0, 1, min, max)
    }
}

NebFreeze_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\freeze_alt)).linlin(0, 1, min, max)
    }
}

NebSource_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\source_alt)).linlin(0, 1, min, max)
    }
}

NebRecord_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\record_alt)).linlin(0, 1, min, max)
    }
}

NebFile_alt : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\file_alt)).linlin(0, 1, min, max)
    }
}

NebRecord_instr : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\record_instr)).linlin(0, 1, min, max)
    }
}

NebFile_instr : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\file_instr)).linlin(0, 1, min, max)
    }
}

NebSource_instr : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\source_instr)).linlin(0, 1, min, max)
    }
}

NebReset_instr : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\reset_instr)).linlin(0, 1, min, max)
    }
}

NebFreeze_instr : UGen {
    *kr { |min = 0.0, max = 1.0|
        ^In.kr(NebInterface.bus(\freeze_instr)).linlin(0, 1, min, max)
    }
}
