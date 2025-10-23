s.boot;
NebInterface.init(s);

s.waitForBoot {
	{
		var sig = SoundIn.ar([0, 1]);
		Out.ar(0, sig);
	}.play;
};