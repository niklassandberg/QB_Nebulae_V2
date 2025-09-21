s.boot;
NebulaeInterface.init(s);

s.waitForBoot {

        var path = "/home/alarm/audio/";
        var regex = "^wt_.*wav$";   // example regexp

    var wtSize   = 2048;
    var numTables = 256;
    var loaded   = 0;

        var paths = List[];
        var buffers;

    var playSynth = { |bufs|
        {
            var sigs = bufs.collect { |b|
                MultiWtOsc.ar(
                                        NebPitch.kr(20, 1800),
                                        NebSpeed.kr(0, numTables),
                                        0, 0,
                                        bufnum: b, numTables: 1, wtSize: 2048, ratio: 2,
                                        numOscs: 1, detune: 1.0
                                )
            };

            var wtScan = NebBlend.kr(0, bufs.size - 1);

                        SelectX.ar(wtScan, sigs) ! 2 * 0.1
                        //Mix.new(sigs) ! 2 * 0.1
        }.play;
    };


        PathName(path)
        .filesDo { |pathname|
                if(pathname.extension == "wav"
                ){
                        var fname = pathname.fullPath.split($/).last;
                        if (fname.findRegexp(regex).notNil) {
                                paths add: pathname.fullPath
                        }
                }
        };

    buffers  = Array.newClear(paths.size);

    paths.do { |path, i|
        Buffer.read(s, path, action: { |buf|
            "Loaded: %".format(buf).postln;
            buffers[i] = buf;
            loaded = loaded + 1;

            // When all are ready, start synth
            if (loaded == paths.size) {
                playSynth.(buffers);
            }
        });
    };
};
