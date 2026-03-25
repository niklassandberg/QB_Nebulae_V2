s.waitForBoot {

    NebInterface.init(s);
    s.sync;

    NebInterface.synthDef(\micouds, {

        // Kontroller
        var pos = NebStart.kr(0, 1).varlag(0.2);
        var dens =NebDensity.kr(0,1);
        var drywet = NebBlend.kr(0, 1);
        var drywetNew = (drywet>0.5) + (drywet<=0.5)*drywet;

        //var spread = NebSpeed.kr(0, 1);
        var nebSpeedRaw = NebSpeed.kr(-1, 1);
        var nebSpeedSign = nebSpeedRaw.sign;
        var nebSpeedAbs = nebSpeedRaw.abs;
        var nebSpeed = (LinExp.kr(nebSpeedAbs, 0, 1, 1, 5)-1) * nebSpeedSign * (-1);


        var pit = LinLin.kr( NebPitch.kr(0, 1).varlag(0.2), 0, 1, -48, 48);

        var size = NebOverlap.kr(0.001, 1);
        var nebSize = NebSize.kr(0, 1).varlag(0.2); //apperantly rvb == spread
        var tex = NebWindow.kr(0, 1);

        var freeze = NebFreeze.kr(0, 1);
        var trig = NebReset.kr(0, 1);

        var fb = 0.0;
        var rvb = 0.0;

        //var mode = NebSource.kr(0, 1);

        //var modeChoosen = (mode<0.5)*0 + (mode>=0.5)*3;

        var input = SoundIn.ar(0);

        var bufDur = (700 * 1024 / 48000)*(1/4); // ~14.9 seconds
        var totalpos = ((Integrator.kr( nebSpeed * ControlDur.ir / bufDur ).wrap(0, nebSize)+pos).wrap(0, 1) * (freeze>0.5)) + (pos * (freeze<0.5));

        var out = MiClouds.ar(
            input, pit: pit, pos: totalpos, size: size, dens: dens, tex: tex, drywet: drywetNew, in_gain: 1.0,
                    spread: 1.0, rvb: rvb, fb: fb, freeze: freeze, mode: 3, trig: trig
        );

        Out.ar(0, Limiter.ar(out*8, 1.0, 0.01));
    }).add;

    s.sync;
    ~clouds = Synth(\micouds);
    NebInterface.ready(s);
};
