// From ddwWavetableSynth (https://github.com/jamshark70/ddwWavetableSynth), GPL v3.
// Nebulae change in makeOscArray: with interpolation 2 (linear, the default)
// the read position wraps inside each table. Upstream, BufRd interpolates
// the last sample of a table (index wtSize - 1 .. wtSize) with the first
// sample of the next table in the buffer: a small jump every cycle, which
// aliases. The whole sample index and the fraction are also kept apart, so
// a large buffer offset (position x numTables x wtSize) loses no precision.
// Nebulae: mapOffset (default 0 = upstream) is added to the map index. With
// tables from NebPatch.loadWavetables (fudgeFactor 0) pass mapOffset 1: map 0
// is then the unfiltered table and every map is used only up to the pitch
// where it would start to alias, so nothing is cut that doesn't need to be.
MultiWtOsc {
	*ar { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
		bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
		numOscs = 1, detune = 1, interpolation = 2, hardSync = 0, phaseMod = 0, mapOffset = 0|

		var out = this.arOscs(freq, wtPos, squeeze, wtOffset,
			bufnum, wtSize, numTables, ratio,
			numOscs, detune, interpolation, hardSync, phaseMod, mapOffset
		);
		^out.asArray.sum
	}

	*arOscs { |freq = 440, wtPos = 0, squeeze = 0, wtOffset = 0,
		bufnum = 0, wtSize = 2048, numTables = 8, ratio = 2,
		numOscs = 1, detune = 1, interpolation = 2, hardSync = 0, phaseMod = 0, mapOffset = 0|
		^this.makeOscArray(
			freq * Array.fill(numOscs, { detune ** Rand(-1, 1) }),
			wtPos, squeeze, wtOffset,
			bufnum, wtSize, numTables, ratio,
			numOscs, interpolation, hardSync, phaseMod, mapOffset
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
		numOscs = 1, interpolation = 2, hardSync = 0, phaseMod = 0, mapOffset = 0|

		var log = log(ratio);
		var baseFreq = SampleRate.ir / wtSize;
		// logarithm (base ratio) of freq / baseFreq
		// I'm also going to use an ugly workaround
		// to stick a conditional into a 'var' block
		// this must be ar before rounding!
		// else kr --> ar interpolation will accidentally
		// offset the buffer read position
		var mapIndex = {
			// Nebulae: + mapOffset, see top.
			var index = ((log(freq) - log(baseFreq)) / log + mapOffset).clip(0, numTables - 1.001);
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

		// Nebulae: linear (2) or cubic (4) interpolation that wraps inside the
		// table (see top). Cubic is the same 4-point one as BufRd's.
		var i0 = phase.floor, frac = phase - i0, i1 = (i0 + 1) % wtSize;
		var read = { |table|
			var a, b, m, c;
			case
			{ interpolation == 2 } {
				a = BufRd.ar(1, bufnum, table + i0, interpolation: 1);
				b = BufRd.ar(1, bufnum, table + i1, interpolation: 1);
				a + ((b - a) * frac)
			}
			{ interpolation == 4 } {
				m = BufRd.ar(1, bufnum, table + ((i0 - 1) % wtSize), interpolation: 1);
				a = BufRd.ar(1, bufnum, table + i0, interpolation: 1);
				b = BufRd.ar(1, bufnum, table + i1, interpolation: 1);
				c = BufRd.ar(1, bufnum, table + ((i0 + 2) % wtSize), interpolation: 1);
				((((0.5 * (c - m)) + (1.5 * (a - b))) * frac
					+ (m - (2.5 * a) + (2 * b) - (0.5 * c))) * frac
					+ (0.5 * (b - m))) * frac + a
			}
			{ BufRd.ar(1, bufnum, table + phase, interpolation: interpolation) }
		};

		var evenSig = LinXFade2.ar(
			read.(evenMap + evenWt),
			read.(evenMap + oddWt),
			wtXfade
		);
		var oddSig = LinXFade2.ar(
			read.(oddMap + evenWt),
			read.(oddMap + oddWt),
			wtXfade
		);

		^LinXFade2.ar(evenSig, oddSig, mapXfade * 2 - 1).unbubble
	}
}