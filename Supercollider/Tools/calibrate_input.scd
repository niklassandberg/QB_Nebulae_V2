/*
nebconfigbegin
speed,rawencoder
nebconfigend
*/

/* Input clip calibration.

   Finds where the audio input clips before the codec's input gain (the
   speed knob in secondary controls), so the clip warning can also catch it
   when the gain is turned down.

   How to use:
   1. Put this file in sc/ on the USB stick (e.g. as 9_calibrate_input.scd)
      and load it like any SuperCollider patch.
   2. Feed a SINE or TRIANGLE wave into the audio input, as loud as it gets
      (e.g. a modular oscillator at full level). Not a square wave: it has
      flat tops by nature and hides the clipping.
   3. Don't touch secondary controls while it runs (that sets the gain too).
   4. It steps the gain through 0..31 (about 40 s). The speed LEDs show the
      progress in blue and turn green when it is done.
   5. The result is in /home/alarm/input_calibration.csv and in
      /tmp/sclang.log. Afterwards the gain is set back to what it was.

   Per gain step it records 0.5 s and measures:
     peak       highest sample (1.0 = full scale, the ADC clips)
     plateau    share of the time within 1 % of the peak: a sine is about
                9 %, a clipped sine much more (flat tops)
     rms        average level

   For testing on a PC (no amixer, no codec): set ~calibInput to a function
   that returns the input signal (it gets the gain step), ~calibSetGain to a
   function that takes the gain step, and ~calibCsv to the CSV path, before
   loading.
*/
s.waitForBoot {
	var neb = NebInterface.init(s);
	var device = "hw:sndrpiproto", control = "Capture";
	var csvPath = ~calibCsv ? "/home/alarm/input_calibration.csv";
	var recSeconds = 0.5, settleSeconds = 0.3;
	var getGain, setGain, input, gainBus, buf, tmp, rows, startGain, showProgress;

	// The codec's capture volume, raw steps 0..31 (as nebmixer.inputLevel).
	getGain = {
		var out = "amixer -D % sget %".format(device, control).unixCmdGetStdOut;
		var m = out.findRegexp("Capture ([0-9]+) \\[");
		if (m.size >= 2) { m[1][1].asInteger } { nil }
	};
	setGain = ~calibSetGain ? { |step|
		"amixer -q -D % sset % %".format(device, control, step).systemCmd;
	};
	input = ~calibInput ? { SoundIn.ar([0, 1]) };

	showProgress = { |fraction, done = false|
		var c = if (done) { [0, 4095, 0] } { [0, 0, 4095] };
		NebInterface.led(\speed_pos, *(c * if (done) { 1 } { fraction }));
		NebInterface.led(\speed_neg, *(c * if (done) { 1 } { 1 - fraction }));
	};

	NebInterface.ready(s);   // answer Nebulae's handshake at once; the measuring takes a while

	startGain = if (~calibSetGain.isNil) { getGain.value } { nil };
	"calibrate_input: gain before: %".format(startGain).postln;
	buf = Buffer.alloc(s, (s.sampleRate * recSeconds).asInteger, 2);
	tmp = PathName.tmp +/+ "calibrate_input.wav";
	s.sync;

	rows = (0..31).collect { |step|
		var data, peak, plateau, rms;
		showProgress.(step / 31);
		setGain.(step);
		settleSeconds.wait;
		{
			var sig = input.value(step);
			if (sig.size == 0) { sig = sig ! 2 };   // the buffer is stereo, RecordBuf needs 2 channels
			RecordBuf.ar(sig, buf, loop: 0, doneAction: 2);
			nil
		}.play;
		(recSeconds + 0.1).wait;
		buf.write(tmp, "wav", "float");
		s.sync;
		SoundFile.use(tmp, { |f|
			data = FloatArray.newClear(f.numFrames * f.numChannels);
			f.readData(data);
		});
		data = data.abs;
		peak = data.maxItem;
		plateau = if (peak > 0) { data.count { |x| x >= (peak * 0.99) } / data.size } { 0 };
		rms = (data.squared.sum / data.size).sqrt;
		"calibrate_input: step % (% dB gain)  peak % (% dBFS)  plateau % percent  rms % dBFS".format(
			step, ((step - 23) * 1.5).round(0.1), peak.round(0.0001), peak.ampdb.round(0.1),
			(plateau * 100).round(0.1), rms.ampdb.round(0.1)).postln;
		[step, (step - 23) * 1.5, peak, peak.ampdb, plateau * 100, rms.ampdb]
	};

	if (startGain.notNil) { setGain.(startGain) };
	File.use(csvPath, "w", { |f|
		f.write("step,gain_db,peak,peak_dbfs,plateau_percent,rms_dbfs\n");
		rows.do { |r| f.write(r.collect { |v| v.round(0.0001) }.join(",") ++ "\n") };
	});
	"calibrate_input: done, written to %".format(csvPath).postln;
	showProgress.(1, true);
};
