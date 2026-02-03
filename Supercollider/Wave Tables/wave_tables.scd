
s.waitForBoot {
    NebInterface.initAndLoadAudio(s, "^wt_.*wav$", true,
    { |bufs|
        {
            var wtSize   = 2048;
            var numTables = 256;
            var pitchVal = NebPitch.kr(0, 1);
            var offset = NebBlend.kr(0, 1);
            var base = LinExp.kr(offset, 0, 1, 16.3515, 65.406);
            var top  = LinExp.kr(offset, 0, 1, 523.251, 2093.004);
            var freq = LinExp.kr(pitchVal, 0, 1, base, top);

            var sigs = bufs.collect { |b|
                MultiWtOsc.ar(
                    freq,
                    NebSpeed.kr(0, numTables),
                    0, 0,
                    bufnum: b, numTables: 1, wtSize: 2048, ratio: 2,
                    numOscs: 1, detune: 1.0
                )
            };
            var wtScan = NebWindow.kr(0, bufs.size - 1);
            SelectX.ar(wtScan, sigs) ! 2 * 0.1
        }.play;
        NebInterface.ready(s);
    });
};
