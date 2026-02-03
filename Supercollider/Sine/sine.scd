s.waitForBoot {
	NebInterface.init(s);
	NebInterface.synthDef(\sineSynth, {
        var sig, pitchVal, offset, amp, base, top, freq;
        
        pitchVal = NebPitch.kr(0, 1);
        offset   = NebBlend.kr(0, 1);
        amp = NebWindow.kr(0, 1);
        
        base = LinExp.kr(offset, 0, 1, 32.703, 65.406);
        top  = LinExp.kr(offset, 0, 1, 1046.502, 2093.004);

        freq = LinExp.kr(pitchVal, 0, 1, base, top);

        sig = SinOsc.ar(freq) * amp;
        Out.ar(0, sig ! 2);
    }).add;
    s.sync;
    ~sine = Synth(\sineSynth);
    NebInterface.ready(s);
};