/*
nebconfigbegin
ksmps,64
-B,2048
-b,512
sr,48000
freeze,latching,rising
reset,triggered,rising
source,latching,falling
file,incremental,falling
record,triggered,rising
nebconfigend
*/

s.waitForBoot {

    NebInterface.init(s);
    s.sync;

    NebInterface.onBusChange(\record, { |val|
        if( val > 0.5 ) {
            "GOT RECORD ON".postln;
            ~clouds.set(\record_sc, 0);
            AppClock.sched( s.options.blockSize / s.sampleRate, {
                "SET RECORD OFF".postln;
                ~clouds.set(\record_sc, 1);
                nil;
            });
        };
    });

    NebInterface.synthDef(\micouds, {

        var pos = NebStart.kr(0, 1).varlag(0.2);
        var dens = NebDensity.kr(0,1);
        var drywet = NebBlend.kr(0, 1);
        var nebSpeed = (NebSpeed.kr(0, 1)*8 - 4)*(-1);
        var pit = LinExp.kr(NebPitch.kr(0, 1).varlag(0.1), 0, 1, 0.125, 4.0);
        var size = NebOverlap.kr(0, 1);
        var nebSize = NebSize.kr(0, 1).varlag(0.2);
        var tex = NebWindow.kr(0, 1);
        var freeze = NebFreeze.kr(0, 1);
        var record = NebRecord.kr(0,1);
        var record_mode = NebRecord_alt.kr(0,1);
        var trig = NebFile.kr(0, 1);
        var phase_reset = NebReset.kr(0, 1);
        var record_reset = NebFilestate.kr(0, 1);

        var input = SoundIn.ar([0, 1]);

        var out = MiClouds.ar(
            input, pit: pit, pos: pos, size: size, dens: dens, tex: tex, drywet: drywet, in_gain: 2.0,
            spread: 1.0, rvb: 0.0, fb: 0.0, freeze: freeze, mode: 3, trig: trig,
            speed: nebSpeed, ssize: nebSize, record: record, record_reset: record_reset, phasor_reset: phase_reset, record_mode: record_mode
        );

        //Out.ar(0, Limiter.ar(fb_output, 1.0, 0.01));
        Out.ar(0, out);
    }).add;

    s.sync;
    ~clouds = Synth(\micouds);
    NebInterface.ready(s);
};
