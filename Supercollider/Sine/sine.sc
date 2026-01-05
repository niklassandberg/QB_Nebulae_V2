s.boot;

NebInterface.init(s);

SynthDef(\sineSynth, { |freq = 440, amp = 0.1|
    var sig;
	sig = SinOsc.ar( NebPitch.kr(20,1800) ) * amp;
    Out.ar(0, sig ! 2);
}).add;

Server.default.boot;
Server.default.waitForBoot {
	Server.default.sync;
    ~sine = Synth(\sineSynth);
    NebInterface.ready(s);
};