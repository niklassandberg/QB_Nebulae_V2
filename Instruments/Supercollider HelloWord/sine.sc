
thisProcess.openUDPPort(3000);
~remote = NetAddr("127.0.0.1", 3001);

SynthDef(\sineSynth, { |freq = 440, amp = 0.1|
    var sig;
    sig = SinOsc.ar(freq) * amp;
    Out.ar(0, sig ! 2);
}).add;

Server.default.boot;
Server.default.waitForBoot {
    Server.default.sync;
	
	~remote = NetAddr("127.0.0.1", 57122);
	
	Server.default.sync;
    ~sine = Synth(\sineSynth);
	
	OSCdef(\pitchControl, { |msg, time, addr, recvPort|
        var newFreq = msg[1];
		newFreq.postln;
        ~synth.set(\freq, newFreq);
        //~remote.sendMsg("/ack", newFreq);
    }, '/neb/pitch');
	
};