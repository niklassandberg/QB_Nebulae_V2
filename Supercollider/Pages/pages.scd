/*
nebconfigbegin
page:speed:detune,/neb/page/detune,0,24
page:speed:drive,/neb/page/drive,1,20,exp
page:pitch:note,/neb/page/note,24,84,lin,0.5
page:pitch:cutoff,/neb/page/cutoff,100,12000,exp,0.6
cv:pitch,note
cv:speed,none
nebconfigend
*/

/* Encoder pages in a .scd: a template (the same pages as in a program's .prog).

   speed  page 1 detune  0..24 semitones, the second oscillator
          page 2 drive (red)  1..20
   pitch  page 1 note  C1..C6, pitch CV here (1V/oct)
          page 2 cutoff (red)  100..12000 Hz
   blend  volume

   Click speed or pitch = next page, turn = value; the LEDs show the value as
   pitch does, and the LED that stays dark there shows the page's colour, dim,
   pulsing (page 1 none, 2 red, 3 blue, ...). Python saves them as pages.pages.
   Where the pitch/speed CV goes: hold file + reset, click pitch or speed,
   release. A SynthDef reads a page with NebPage.kr(\name), already scaled.
*/
s.waitForBoot {
	NebInterface.init(s);
	NebInterface.synthDef(\pagesSynth, {
		var note = NebPage.kr(\note).lag(0.02);
		var freq = note.midicps;
		var sig = Saw.ar([freq, freq * NebPage.kr(\detune).midiratio]).sum * 0.3;
		sig = (sig * NebPage.kr(\drive)).tanh;
		sig = RLPF.ar(sig, NebPage.kr(\cutoff).lag(0.05).clip(20, 18000), 0.3);
		Out.ar(0, (sig * NebBlend.kr(0, 1) * 0.5) ! 2);
	}).add;
	s.sync;
	Synth(\pagesSynth);
	NebInterface.ready(s);
};
