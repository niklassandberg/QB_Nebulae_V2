s.waitForBoot {

    NebInterface.init(s);
    s.sync;
    b = Buffer.alloc(s, s.sampleRate * 10, 2); 
    s.sync;

    NebInterface.onBusChange(\reset, { |val|
        var fileHigh = NebInterface.busValue(\file) > 0.5;
		var resetHigh = val > 0.5;
        if( fileHigh && resetHigh ) {
            b.fill(0, b.numFrames * b.numChannels, 0);
            "Buffer cleared!!!!!!!!!!".postln;
        };
    });

    NebInterface.synthDef(\tape, {
        arg buf, t_trig = 0;
        var phase, input, inputFilter, oldSignal, mixedSignal, readPhase;
        var rate, rateScale, size, start, dry, wet, preLevel, readHead, cutoff;
        var readHeadMin, readHeadMax;

        // Kontroller
        var pitchVal = NebPitch.kr(0, 1);
        rate = LinLin.kr(pitchVal, 0, 1, 0, 1);
        rateScale = BufRateScale.kr(buf) * rate;
        
        start = NebStart.kr(0, BufFrames.kr(buf)).varlag(0.0);
        //I dont want start+size to warp around the buffer two times. Small increments are better ofr the brain.
        size = NebSize.kr(1024, BufFrames.kr(buf)-1).varlag(0.0); //YOU NEED TO HAVE SIZE THT FITS READHEAD!!!!
        
        readHead = NebDensity.kr(256,  size - 256).varlag(0.0);
        

        //TODO: WE NEED PROBABLY TO HAVE SILENCE WHEN CHANGING.... WHY THE FUCK DO WE NEED SO BIG READHEAD!!!!!!!!!
        
        dry = NebBlend.kr(1, 0);
        wet = NebBlend.kr(0, 1);
        preLevel = NebOverlap.kr(0, 1);

        // 1. FHASES

        //phase = (Phasor.ar(t_trig, rateScale, 0, size, 0) + start ) % BufFrames.kr(buf);
        //phase = phase + ( (phase < start) * start );

        phase = ( Phasor.ar(t_trig, rateScale, start, start + size, start) ) % BufFrames.kr(buf);
        readPhase = ( phase - readHead ) % BufFrames.kr(buf);
        
        // 2. MANUELL OVERSAMPLING (4-tap Cubic Interpolation)
        // Vi läser på fyra pyttesmå förskjutna ställen och mixar dem.
        // Detta tar bort "trappstegen" som skapar det fula digitala gruset.
        
        oldSignal = (
            BufRd.ar(2, buf, readPhase, loop: 1, interpolation: 4) +
            BufRd.ar(2, buf, readPhase + 0.25, loop: 1, interpolation: 4) +
            BufRd.ar(2, buf, readPhase + 0.5, loop: 1, interpolation: 4) +
            BufRd.ar(2, buf, readPhase + 0.75, loop: 1, interpolation: 4)
        ) * 0.25;

        // 3. DUBBLA FILTER (För "Tape"-karaktär)
        cutoff = (SampleRate.ir * 0.4 * rate.abs).clip(40, 18000);
        
        input = SoundIn.ar([0, 1]);
        inputFilter = LPF.ar(input, cutoff);
        oldSignal = LPF.ar(oldSignal, cutoff);

        // 4. OVERDUB & SKRIV
        mixedSignal = (inputFilter) + (oldSignal * preLevel);
        BufWr.ar(Limiter.ar(mixedSignal, 0.98), buf, phase, loop: 1);

        // 5. MONITOR
        Out.ar(0, Limiter.ar((input * dry) + (oldSignal * wet), 0.98));
    }).add;

    s.sync;
    ~tape = Synth(\tape, [\buf, b]);
    NebInterface.ready(s);
};
