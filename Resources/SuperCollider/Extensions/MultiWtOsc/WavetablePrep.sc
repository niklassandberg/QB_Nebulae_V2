// 2022 hjh H. James Harkins
// From ddwWavetableSynth (https://github.com/jamshark70/ddwWavetableSynth,
// commit a78801b), GPL v3, like MultiWtOsc.sc next to it.
// Only the parts without GUI are kept: the image reading (Image, Color),
// WavetablePrepGui and SoundFileStream are left out, so it runs headless.
// Added: readSync, the same as read but in the calling Routine, and in
// decimate: a map whose top bin is the whole table is not filtered (only DC
// is removed), so with fudgeFactor 0 map 0 keeps every harmonic.

WavetablePrep {
	classvar <>filters;

	var <>path;
	var <>wtSize = 2048;
	var <>numMaps = 8;
	var <>ratio = 2;
	var <>fudgeFactor = 0.5;
	var <>filter = \tenPctSlope;
	// 2d array of Signals
	// outer dimension is wt-position entries
	// inner dimension is mipmaps
	var <>tables;

	*initClass {
		filters = (
			brickwall: { |fft, topBin|
				var r = fft.real.copy, i = fft.imag.copy;
				topBin = topBin.asInteger + 1;
				r[topBin .. r.size - topBin] = 0.0;
				i[topBin .. r.size - topBin] = 0.0;
				r[0] = 0.0; i[0] = 0.0;  // also kill DC
				Complex(r, i)
			},
			tenPctSlope: { |fft, topBin|
				var r = fft.real.copy, i = fft.imag.copy;
				var half = (topBin * 0.05).asInteger;
				var step;
				// number of items = topBin * 0.1
				// total line should slide over -1 / (topBin * 0.1)
				// = -10 / topBin
				topBin = topBin.asInteger;
				step = max(-1, -10.0 / topBin);  // x < -1 is wrong, will amplify partials
				((topBin * 0.9).asInteger .. topBin).do { |bin, j|
					var mul = 1.0 + (step * j);
					j = (j - half + topBin);  // centered around topBin
					r[j] = r[j] * mul;
					i[j] = i[j] * mul;
					if(j > 0) {
						r[r.size - j] = r[r.size - j] * mul;
						i[r.size - j] = i[r.size - j] * mul;
					};
				};
				topBin = topBin + half + 1;
				r[topBin .. r.size - topBin] = 0.0;
				i[topBin .. r.size - topBin] = 0.0;
				r[0] = 0.0; i[0] = 0.0;  // also kill DC
				Complex(r, i)
			}
		)
	}

	*new { |path, wtSize = 2048, numMaps = 8, ratio = 2, filter|
		^super.newCopyArgs(path, wtSize, numMaps, ratio, 0.5, filter)
	}

	*read { |path, wtSize = 2048, numMaps = 8, ratio = 2, filter,
		action, pause = 0|
		^this.new(path, wtSize, numMaps, ratio, filter)
		.read(action, pause)
	}

	*readFromProcessedFile { |path, wtSize = 2048, numMaps = 8, ratio = 2,
		startFrame = 0, numFrames = -1|
		^this.new("", wtSize, numMaps, ratio)
		.readFromProcessedFile(path, startFrame, numFrames)
	}

	read { |action, pause = 0|
		var file = SoundFile.openRead(path);
		if(file.isNil) {
			action.value(Error("File open failed"))
		} {
			this.readStream(file, action, pause);
		};
	}

	readStream { |file, action, pause = 0|
		var block;
		{
			tables = Array.new(file.numFrames div: wtSize);
			protect {
				while {
					block = Signal.newClear(wtSize);
					file.readData(block);
					block.size == wtSize
				} {
					tables = tables.add(this.decimate(block));
					if(pause > 0) { pause.wait };
				};
			} { |exception|
				file.close;
				action.value(exception, this);
			};
		}.fork(AppClock);
	}

	// Nebulae: as read, but in the calling Routine (yields after every
	// position, so sclang still answers OSC meanwhile). Mono files only.
	readSync {
		var file = SoundFile.openRead(path), block, cos = Signal.fftCosTable(wtSize);
		if(file.isNil) { Error("WavetablePrep: could not open %".format(path)).throw };
		if(file.numChannels != 1) {
			file.close;
			Error("WavetablePrep: % has % channels, a wavetable file must be mono".format(path, file.numChannels)).throw;
		};
		tables = Array.new(file.numFrames div: wtSize);
		protect {
			while {
				block = Signal.newClear(wtSize);
				file.readData(block);
				block.size == wtSize
			} {
				tables = tables.add(this.decimate(block, cos));
				0.wait;
			};
		} { file.close };
	}

	decimate { |timeDomainTable, cos(Signal.fftCosTable(wtSize))|
		var fft = timeDomainTable.fft(Signal.newClear(wtSize), cos);
		var func = filters[filter] ?? { filters[\tenPctSlope] };
		^Array.fill(numMaps, { |i|
			var topBin = timeDomainTable.size * 0.5 / (ratio ** (i + fudgeFactor));
			var new;
			if(topBin >= (timeDomainTable.size * 0.5)) {
				new = Complex(fft.real.copy.put(0, 0.0), fft.imag.copy.put(0, 0.0));  // Nebulae: all of it, no DC
			} {
				new = func.(fft, topBin);
			};
			new.real.ifft(new.imag, cos).real.normalize
		});
	}

	blendAt { |wtPos = 0, freq = 1, sr = 44100|
		var pos, pos1, lowmap, himap;
		// log_base_ratio
		var baseFreq = sr / wtSize;
		var map = (log(freq / baseFreq) / log(ratio)).clip(0, numMaps - 1.001);
		var map1 = floor(map + 1);
		if(tables.size == 1) {
			^blend(tables[0][map.floor], tables[0][map1], map.frac)
		} {
			pos = wtPos.clip(0, tables.size - 1.001);
			pos1 = floor(pos + 1);
			lowmap = blend(tables[pos.floor][map.floor], tables[pos1][map.floor], pos.frac);
			himap = blend(tables[pos.floor][map1], tables[pos1][map1], pos.frac);
			^blend(lowmap, himap, map.frac)
		}
	}

	readFromProcessedFile { |path, startFrame = 0, numFrames = -1|
		var file = SoundFile.openRead(path);
		if(file.notNil) {
			file.seek(startFrame, 0);
			this.readProcessedStream(file, numFrames);
		} {
			Error("Could not open '%' for reading".format(path.basename)).throw;
		}
	}

	readProcessedStream { |file, numFrames = -1|
		var chunk;
		if(numFrames < 0) {
			numFrames = file.numFrames;
		};
		tables = Array.new;
		protect {
			while {
				numFrames >= wtSize and: {
					chunk = Signal.newClear(wtSize);
					file.readData(chunk);
					chunk.size == wtSize
				}
			} {
				tables = tables.add(chunk);
				numFrames = numFrames - wtSize;
			};
		} { file.close };
		tables = tables.clump(numMaps);
	}

	write { |outPath|
		var file = SoundFile.openWrite(outPath,
			"WAV", "float", 1, 44100
		);
		if(file.isNil) {
			Error("Could not open file '%' for writing".format(outPath.basename)).throw;
		};
		protect {
			this.writeStream(file)
		} { file.close };
	}

	writeStream { |file|
		tables.do { |row|  // row = one wtpos
			row.do { |wt|
				file.writeData(wt)
			}
		}
	}
}
