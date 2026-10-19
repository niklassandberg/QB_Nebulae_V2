
// Wavetable synth. The wt_*.wav files in the audio folder (mono, frames of
// 2048 samples, e.g. 256 x 2048 as from Serum) are prepared once without
// aliasing (NebPatch.loadWavetables) and kept in a cache until a file changes.
//   pitch   frequency, blend sets the range (low 16-65 Hz .. high 523-2093 Hz)
//   speed   position inside the wavetable file
//   window  scans across the files
s.waitForBoot {
    var neb = NebInterface.init(s);
    var wtSize = 2048, numMaps = 16, ratio = 2.sqrt;  // as loadWavetables' defaults
    var bufs = neb.loadWavetables("^wt_.*wav$", wtSize, numMaps, ratio, true);
    if (bufs.isEmpty) {
        "wave_tables: no wt_*.wav in %".format(NebInterface.audioPath).warn;
    } {
        {
            var pitchVal = NebPitch.kr(0, 1);
            var offset = NebBlend.kr(0, 1);
            var base = LinExp.kr(offset, 0, 1, 16.3515, 65.406);
            var top  = LinExp.kr(offset, 0, 1, 523.251, 2093.004);
            var freq = LinExp.kr(pitchVal, 0, 1, base, top);

            var sigs = bufs.collect { |b|
                var last = NebPatch.wavetablePositions(b, wtSize, numMaps) - 1.001;
                MultiWtOsc.ar(
                    freq,
                    NebSpeed.kr(0, last),
                    0, 0,
                    bufnum: b, numTables: numMaps, wtSize: wtSize, ratio: ratio,
                    numOscs: 1, detune: 1.0,
                    interpolation: 4,  // cubic, cleaner than linear (2)
                    mapOffset: 1       // map 0 is unfiltered, see loadWavetables
                )
            };
            var wtScan = NebWindow.kr(0, bufs.size - 1);
            SelectX.ar(wtScan, sigs) ! 2 * 0.1
        }.play;
    };
    NebInterface.ready(s);
};
