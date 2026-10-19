/*
nebconfigbegin
speed,rawencoder
record,momentary,rising
reset,triggered,rising
freeze,latching,rising
nebconfigend
*/

/* CHOMPI style sampler (after Chase Bliss CHOMPI, TAPE firmware).

   record   hold to record (the CHOMPI key), release to stop. It records what
            the sampler plays (after the effects) + the input into a second
            buffer; on release that recording becomes the played sample.
            The first time nothing plays, so it is just the input; each next
            recording layers the input onto what is playing (bounce).
   reset    play the sample (a key press), button or gate
   freeze   looping on/off (sample looping toggle)
   pitch    chromatic transposition, 1V/oct (0.6 = original pitch)
   start    sample start point          size     sample end point
   density  attack                      overlap  release
   window   multi-mode filter: low-pass < neutral (middle) < high-pass
   blend    input monitor (dry) <-> sampler (wet)

   speed (rawencoder): press and release to step through three pages.
   The two speed LEDs show the page (colour) and its value (crossfade):
   at the minimum only the left LED (neg) glows, at the maximum only the
   right LED (pos), in between both, the brighter towards the value.
     page 1  speed / direction  -2x .. 2x   white, green at exactly 1x
     page 2  reverb amount       0 .. 1     left cyan (dry) -> right blue (wet)
     page 3  tape: saturation    0 .. 1     left yellow (clean) -> right red (driven)
             + wow & flutter
   All three values are NebInterface settings: saved for the patch and back
   the next time it is loaded. The page always starts at page 1.
   Holding speed for 1.5 s still opens the instr selector; a press of 1 s or
   longer doesn't change the page.
*/
s.waitForBoot {
	// The speed pages: name, default, min, max.
	var pages = [
		[\speed,  1.0, -2, 2],
		[\reverb, 0.0,  0, 1],
		[\tape,   0.0,  0, 1]
	];
	var step = 0.02, page = 0, pressTime;
	var neb, bufs, playIdx = 0, fxBus, wetBus, recSynth, voice, fx, showLeds;
	var ledBright = 0.4;
	var white = [4095, 4095, 4095], green = [0, 4095, 0];
	var cyan = [0, 2600, 4095], blue = [0, 0, 4095];
	var yellow = [4095, 3000, 0], red = [4095, 0, 0];

	neb = NebInterface.init(s);
	NebInterface.initSettings(pages.collect { |p| p[0..1] });  // name, default

	// Two CHOMPI buffers, 20 s stereo each: one is played, the other recorded
	// into. They swap places when a recording is done.
	bufs   = { neb.addStereoAudioBuffer(20.0) } ! 2;
	fxBus  = Bus.audio(s, 2);  // voice -> effects
	wetBus = Bus.audio(s, 2);  // what the sampler plays, after the effects -> recorder
	s.sync;

	// Hold record: what is played + the input, from the start of buf. On
	// release the recorded length (frames) goes to sclang (/chompi/recorded).
	NebInterface.synthDef(\chompiRec, { |buf, wet|
		var in, rec, recTrig, frames;
		in      = SoundIn.ar([0, 1]) + In.ar(wet, 2);
		rec     = NebRecord.kr(0, 1) > 0.5;
		recTrig = Trig1.kr(rec, 0.001);
		RecordBuf.ar(in, buf, 0, 1, 0, rec, 0, recTrig);
		frames  = Sweep.kr(recTrig, SampleRate.ir * rec).min(BufFrames.kr(buf));
		SendReply.kr(HPZ1.kr(rec) < 0, '/chompi/recorded', frames);  // released
	}).add;

	// One sample voice: start/end window, speed/direction (page 1) times the
	// chromatic pitch, attack/release envelope, one-shot or looping.
	// t_new: a new recording was swapped in, play it from the start.
	NebInterface.synthDef(\chompiVoice, { |out, buf, len = 0, t_new = 0|
		var startF, endF, segLen, semis, rate, trig, phase, sig;
		var loopOn, t, dur, gate, att, rel, env, declick;

		len    = len.max(64);
		startF = (NebStart.kr(0, 1) * len).min(len - 64);
		endF   = (NebSize.kr(0, 1) * len).max(startF + 64).min(len);
		segLen = endF - startF;

		semis = ((NebPitch.kr(0, 1) - 0.6) * 60).round(1);  // 0.2 per octave = 1V/oct
		rate  = NebSetting.kr(\speed).lag(0.05) * semis.midiratio * BufRateScale.kr(buf);

		trig  = (Trig1.kr(NebReset.kr(0, 1) > 0.5, 0.001) + t_new) > 0;
		phase = Phasor.ar(trig, rate, startF, endF, Select.kr(rate < 0, [startF, endF - 1]));
		sig   = BufRd.ar(2, buf, phase, loop: 1, interpolation: 4);

		// One-shot: the gate is open for one pass through the window.
		loopOn = NebFreeze.kr(0, 1) > 0.5;
		t      = Sweep.kr(trig, 1);
		dur    = segLen / (SampleRate.ir * rate.abs.max(0.01));
		gate   = loopOn.max(t < dur);

		att = NebDensity.kr(0, 1).linexp(0, 1, 0.002, 2);
		rel = NebOverlap.kr(0, 1).linexp(0, 1, 0.01, 4);
		env = EnvGen.kr(Env.asr(att, 1, rel), gate);
		declick = EnvGen.kr(Env([0, 1], [0.005]), trig + Impulse.kr(0));

		Out.ar(out, sig * env * declick);
	}).add;

	// Tape (page 3), multi-mode filter (window), reverb (page 2), blend.
	NebInterface.synthDef(\chompiFx, { |in, wet|
		var sig, dry, tape, rev, window, wow, flutter, blend;
		sig  = In.ar(in, 2);
		tape = NebSetting.kr(\tape).lag(0.05);
		rev  = NebSetting.kr(\reverb).lag(0.05);

		// Wow & flutter: a slowly wandering and a fast wobbling tape delay.
		wow     = LFNoise2.kr(0.6, 0.0035 * tape);
		flutter = SinOsc.kr(6.5, 0, 0.0004 * tape);
		sig = DelayC.ar(sig, 0.02, 0.006 + wow + flutter);
		// Saturation: from subtle warmth to blown out, losing the top end.
		sig = (sig * (1 + (tape * 15))).tanh / (1 + tape);
		sig = LPF.ar(sig, tape.linexp(0, 1, 18000, 5000));

		window = NebWindow.kr(0, 1);
		sig = RLPF.ar(sig, window.linexp(0, 0.45, 120, 20000), 0.7);
		sig = RHPF.ar(sig, window.linexp(0.55, 1, 20, 5000), 0.7);

		sig = FreeVerb2.ar(sig[0], sig[1], rev, 0.6 + (rev * 0.35), 0.4);

		Out.ar(wet, sig);  // to the recorder

		blend = NebBlend.kr(0, 1);
		dry = SoundIn.ar([0, 1]);
		Out.ar(0, Limiter.ar((dry * (1 - blend)) + (sig * blend), 0.95));
	}).add;
	s.sync;

	// Order: voice -> effects -> recorder (it reads the effects' output).
	voice = Synth(\chompiVoice,
		[\out, fxBus, \buf, bufs[playIdx]]);
	fx = Synth.after(voice, \chompiFx, [\in, fxBus, \wet, wetBus]);
	recSynth = Synth.after(fx, \chompiRec, [\buf, bufs[1 - playIdx], \wet, wetBus]);

	// Recording done: it becomes the played sample, the old one the next
	// recording buffer. A tap shorter than 64 frames is ignored.
	OSCdef(\chompiRecorded, { |msg|
		var frames = msg[3];
		if (frames >= 64) {
			playIdx = 1 - playIdx;
			voice.set(\buf, bufs[playIdx], \len, frames, \t_new, 1);
			recSynth.set(\buf, bufs[1 - playIdx]);
		};
	}, '/chompi/recorded');

	// Speed LEDs: the colour shows the page, the crossfade its value
	// (0 = only the left/neg LED, 1 = only the right/pos LED).
	showLeds = {
		var name = pages[page][0], v = NebInterface.setting(name), amount, pos, neg;
		var lit = { |colour, bright| colour * bright.clip(0, 1) * ledBright };
		amount = v.linlin(pages[page][2], pages[page][3], 0, 1);
		switch (page,
			0, {
				var colour = if ((v - 1).abs < 0.001) { green } { white };
				pos = lit.(colour, amount);
				neg = lit.(colour, 1 - amount);
			},
			1, { pos = lit.(blue, amount); neg = lit.(cyan, 1 - amount) },
			2, { pos = lit.(red, amount);  neg = lit.(yellow, 1 - amount) }
		);
		NebInterface.led(\speed_pos, pos[0], pos[1], pos[2]);
		NebInterface.led(\speed_neg, neg[0], neg[1], neg[2]);
	};

	NebInterface.rawEncoder(\speed,
		onStep: { |n|
			var name = pages[page][0], min = pages[page][2], max = pages[page][3];
			NebInterface.setSetting(name,
				(NebInterface.setting(name) + (n * step)).round(step).clip(min, max));
			showLeds.value;
		},
		onClick: { |state|
			if (state == 1) {
				pressTime = Main.elapsedTime;
			} {
				if (pressTime.notNil and: { (Main.elapsedTime - pressTime) < 1.0 }) {
					page = (page + 1) % pages.size;
					showLeds.value;
				};
				pressTime = nil;
			};
		});
	showLeds.value;

	NebInterface.ready(s);
};
