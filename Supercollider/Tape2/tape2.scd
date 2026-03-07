s.waitForBoot {

    NebInterface.init(s);
    s.sync;
    buffert = Buffer.alloc(s, s.sampleRate * 10, 2); 
    s.sync;

    NebInterface.onBusChange(\reset, { |val|
        var fileHigh = NebInterface.busValue(\file) > 0.5;
		var resetHigh = val > 0.5;
        if( fileHigh && resetHigh ) {
            buffert.fill(0, b.numFrames * b.numChannels, 0);
            "Buffer cleared!!!!!!!!!!".postln;
        };
    });

    NebInterface.synthDef(\tape, {
        arg buf, t_trig = 0;
        var phase, input, inputFilter, oldSignal, mixedSignal, readPhase;
        var rate, cutoff;
        var readHeadMin, readHeadMax;

        // Kontroller
        var pitchVal = NebPitch.kr(0, 1);
        var rate = LinLin.kr(pitchVal, 0, 1, 0, 1);
        var rateScale = BufRateScale.kr(buf) * rate;
        
        //NebDensity.kr(256,  size - 256).varlag(0.0);
        
        var dry = NebBlend.kr(1, 0);
        var wet = NebBlend.kr(0, 1);
        var preLevel = NebOverlap.kr(0, 1);

        // -------------------------------

        var getTrapezoidVol = { |pos, size, xFade|
			var fadeIn = pos.abs / xFade;
			var fadeOut = (size - pos.abs) / xFade;
			fadeIn.min(fadeOut).clip(0.0, 1.0);
		};
		
		var getExitTrig = { |val, limit|
			var isOutNow = val.abs >= limit;
			var wasInBefore = Delay1.ar(val.abs) < limit;
			isOutNow * wasInBefore;
		};
		
		var feedback = LocalIn.ar(2);
		var feedbackTrig = feedback[0];
		var lastVol1 = feedback[1];
		
		var rate = 1;
		var sr = BufSampleRate.kr(buf);
		var frames = BufFrames.kr(buf);
		
		var start = NebStart.kr(0, BufFrames.kr(buf)).varlag(0.0);
		var size =  NebSize.kr(4096, BufFrames.kr(buf)-1).varlag(0.0); //YOU NEED TO HAVE SIZE THT FITS READHEAD!!!!
		var xFadeSamples = 1024;
		
		var limit = (size - xFadeSamples);
		
		var mouseTrig = HPZ1.kr(NebReset.kr(0, 1)) > 0.5;
		var mouseTrigP1 = Trig1.ar(mouseTrig * (lastVol1 < 0.9), SampleDur.ir);
		var mouseTrigP2 = Trig1.ar(mouseTrig * (lastVol1 > 0.1), SampleDur.ir);
		
		var p1 = Sweep.ar(feedbackTrig + mouseTrigP1, rate * sr);
		var trig2 = getExitTrig.value(p1, limit);
		
		var p2 = Sweep.ar(trig2 + mouseTrigP2, rate * sr);
		var trig = getExitTrig.value(p2, limit);
			
		var loop1 = ((start + p1) % size) % frames;
		var loop2 = ((start + p2) % size) % frames;
        
        var readHead = 256;
			
		var sig1 = BufRd.ar(buf.numChannels, buf, loop1, 1, 4);
		var sig2 = BufRd.ar(buf.numChannels, buf, loop2, 1, 4);
		
		var vol1 = getTrapezoidVol.value(p1, size, xFadeSamples);
		var vol2 = getTrapezoidVol.value(p2, size, xFadeSamples);
			
		var sig = (sig1 * vol1) + (sig2 * (1.0 - vol1));
		
		sig = AnalogTape.ar(sig, 0.1, 1.0, MouseY.kr(1.0, 2.0), 2, 2); 

        cutoff = (SampleRate.ir * 0.4 * rate.abs).clip(40, 18000);

        input = SoundIn.ar([0, 1]);
        inputFilter = input;//LPF.ar(input, cutoff);
        oldSignal = LPF.ar(oldSignal, cutoff);

        // 4. OVERDUB & SKRIV
        mixedSignal = (inputFilter) + (oldSignal * preLevel);
        BufWr.ar(Limiter.ar(mixedSignal, 0.98), buf, phase, loop: 1);

        // 5. MONITOR
        Out.ar(0, Limiter.ar((input * dry) + (oldSignal * wet), 0.98));
    }).add;

    s.sync;
    ~tape = Synth(\tape, [\buf, buffert]);
    NebInterface.ready(s);
};
