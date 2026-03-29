s.waitForBoot {

    NebInterface.init(s);
    s.sync;

    NebInterface.synthDef(\micouds, {

        var pos = NebStart.kr(0, 1).varlag(0.2);
        var dens =NebDensity.kr(0,1);
        var drywet = NebBlend.kr(0, 1);

        //var spread = NebSpeed.kr(0, 1);

        var nebSpeed = (NebSpeed.kr(0, 1)*8 - 4)*(-1);

        var pit = LinExp.kr(NebPitch.kr(0, 1).varlag(0.1), 0, 1, 0.125, 4.0);

        var size = NebOverlap.kr(0, 1);
        var nebSize = NebSize.kr(0, 1).varlag(0.2); //apperantly rvb == spread
        var tex = NebWindow.kr(0, 1);
        var freeze = NebFreeze.kr(0, 1);
        var record = (freeze < 0.5) * NebRecord.kr(0,1);

        var trig = NebReset.kr(0, 1);

        var fb = 0.0;
        var rvb = 0.0;

        //var mode = NebSource.kr(0, 1);

        //var modeChoosen = (mode<0.5)*0 + (mode>=0.5)*3;

        var input = SoundIn.ar([0, 1]);

        var out = MiClouds.ar(
            input, pit: pit, pos: pos, size: size, dens: dens, tex: tex, drywet: drywet, in_gain: 1.0,
                    spread: 1.0, rvb: rvb, fb: fb, freeze: freeze, mode: 3, trig: trig, speed: ((record<0.5)*nebSpeed), ssize: ((record<0.5)*size), record: record
        );

        Out.ar(0, Limiter.ar(out*8, 1.0, 0.01));
    }).add;

    s.sync;
    ~clouds = Synth(\micouds);
    NebInterface.ready(s);
};

