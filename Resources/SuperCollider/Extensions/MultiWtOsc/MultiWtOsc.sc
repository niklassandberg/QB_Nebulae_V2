MultiWtOsc {
	*ar { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
		bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
		numOscs = 1, detune = 1, interpolation = 2, hardSync = 0, phaseMod = 0|

		var out = this.arOscs(freq, wtPos, squeeze, wtOffset,
			bufnum, wtSize, numTables, ratio,
			numOscs, detune, interpolation, hardSync, phaseMod
		);
		^out.asArray.sum
	}

	*arOscs { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
		bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
		numOscs = 1, detune = 1, interpolation = 2, hardSync = 0, phaseMod = 0|
		^this.makeOscArray(
			freq * Array.fill(numOscs, { detune ** Rand(-1, 1) }),
			wtPos, squeeze, wtOffset,
			bufnum, wtSize, numTables, ratio,
			numOscs, interpolation, hardSync, phaseMod
		)
	}

	// this isn't right though -- the window should follow sync source frequency
	// *arOscsSoftSync { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
	// 	bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
	// 	numOscs = 1, detune = 1, interpolation = 2, hardSync = 0, phaseMod = 0|
	// 	var detunes = Array.fill(numOscs, { detune ** Rand(-1, 1) });
	// 	var freqs = freq * detunes;
	// 	^this.makeOscArray(
	// 		freqs, wtPos, squeeze, wtOffset,
	// 		bufnum, wtSize, numTables, ratio,
	// 		numOscs, interpolation, hardSync, phaseMod
	// 	) * LFTri.ar(freqs)
	// }

	// you should pass in the exact frequencies that you want (including detune)
	*makeOscArray { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
		bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
		numOscs = 1, interpolation = 2, hardSync = 0, phaseMod = 0|

		var log = log(ratio);
		var baseFreq = SampleRate.ir / wtSize;
		// logarithm (base ratio) of freq / baseFreq
		// I'm also going to use an ugly workaround
		// to stick a conditional into a 'var' block
		// this must be ar before rounding!
		// else kr --> ar interpolation will accidentally
		// offset the buffer read position
		var mapIndex = {
			var index = ((log(freq) - log(baseFreq)) / log).clip(0, numTables - 1.001);
			if(index.rate == \control) {
				K2A.ar(index);
			} {
				index
			}
		}.value;

		// current SC releases don't have 'ramp' in K2A
		// so apply a workaround in that case
		var zeroOrderHold = { |ugen|
			if(ugen.rate == \control) {
				if(Meta_K2A.findMethod(\ar).argNames.includes('ramp')) {
					K2A.ar(ugen, 0)
				} {
					Duty.ar(SampleDur.ir, 0, ugen)
				}
			} {
				ugen
			}
		};

		var evenMap = zeroOrderHold.(mapIndex.round(2) * wtSize);
		var oddMap = zeroOrderHold.(((mapIndex + 1).round(2) - 1) * wtSize);
		var mapXfade = mapIndex.fold(0, 1);

		var rowSize = wtSize * numTables;
		var lagPos = if(#[audio, control].includes(wtPos.rate)) {
			Lag.perform(wtPos.methodSelectorForRate, wtPos, 0.1)
		} {
			wtPos
		};
		var evenWt = zeroOrderHold.(lagPos.round(2) * rowSize);
		var oddWt = zeroOrderHold.(((lagPos + 1).round(2) - 1) * rowSize);
		var wtXfade = lagPos.fold(0, 1) * 2 - 1;
		// var wtXfade = SinOsc.perform(lagPos.methodSelectorForRate,
		// 	0,
		// 	// this should be -cos(lagPos * pi)
		// 	// but SinOsc lookup table may be faster than 'cos' operator
		// 	lagPos.fold(0, 1) * pi - 0.5pi
		// );

		var normphase = Phasor.ar(hardSync, SampleDur.ir * freq, 0, 1);
		// credit: Paul Miller of TXModular
		var phaseDist = (((normphase + phaseMod % 1.0) * 2 - 1) ** (2 ** squeeze)) * 0.5 + 0.5;
		var phase = (phaseDist + zeroOrderHold.(wtOffset)) % 1.0 * wtSize;

		var evenPhase = phase + evenMap;  // eliminate a duplicate '+'
		var evenSig = LinXFade2.ar(
			BufRd.ar(1, bufnum, evenPhase + evenWt, interpolation: interpolation),
			BufRd.ar(1, bufnum, evenPhase + oddWt, interpolation: interpolation),
			wtXfade
		);
		var oddPhase = phase + oddMap;
		var oddSig = LinXFade2.ar(
			BufRd.ar(1, bufnum, oddPhase + evenWt, interpolation: interpolation),
			BufRd.ar(1, bufnum, oddPhase + oddWt, interpolation: interpolation),
			wtXfade
		);

		^LinXFade2.ar(evenSig, oddSig, mapXfade * 2 - 1).unbubble
	}
}