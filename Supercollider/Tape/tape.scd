s.waitForBoot {
	NebInterface.init(s);
    
    //TODO: add to scsynth startup (5 minutes)
    s.sync;
    b = Buffer.alloc(s, s.sampleRate * 5, 2); 
    s.sync;

	NebInterface.synthDef(\tape, {
        arg buf, t_trig = 0;
        var phase, input, oldSignal, mixedSignal, readPhase, writePhase;
        var rate, rateScale, readHeadLimit = 256;
        var relativePhase;
        var filterOldSignal, filterInput;

        var readHead = NebDensity.kr(BufFrames.kr(buf), readHeadLimit ).varlag(0.4);

        var start = NebStart.kr(0, BufFrames.kr(buf) ).varlag(0.4);
        var size = NebSize.kr(SampleRate.ir, BufFrames.kr(buf)).varlag(0.4);
        var dry = NebBlend.kr(1,0);
        var wet = NebBlend.kr(0,1);

        var pitchVal = NebPitch.kr(0, 1);
        var preLevel = NebOverlap.kr(0, 1); //TODO: free param
        rate = LinLin.kr(pitchVal, 0, 1, 0, 1);
        rateScale = BufRateScale.kr(buf) * rate;

        // NebSize (antar att det är din andra variabel) ger oss längden (0 till 1) 
        // multiplicerat med bufferns totala längd

        // 2. PHASOR: Låt den bara gå från 0 till size
        // Den här rör sig nu i den hastighet du valt (rate)
        relativePhase = Phasor.ar(t_trig, rateScale, 0, size, 0);

        // 3. ADDERA START: Flytta fönstret till rätt ställe på bandet
        // Vi använder modulo % för att se till att vi inte kraschar om 
        // start + relativePhase går utanför bufferns slut
        phase = (start + relativePhase) % BufFrames.kr(buf);

        // 2. INPUT (Din röst - filtreras för att undvika aliasing i buffern)
        input = SoundIn.ar([0, 1]);
        filterInput = LPF.ar(input, (SampleRate.ir * 0.4 * rate.abs).clip(20, 20000));

        // 3. LÄS FRÅN BANDET (Med säkerhetsavstånd för interpolation)
        // Vi läser 128 samples BAKOM för att låta Cubic-algoritmen jobba ifred.
        readPhase = (phase - readHead) % BufFrames.kr(buf);
        oldSignal = BufRd.ar(2, buf, readPhase, loop: 1, interpolation: 4);

        // 4. OVERDUB-LOGIK
        // Vi blandar input med det vi nyss läste och skriver det till NUET (phase)
        mixedSignal = Limiter.ar((filterInput*dry) + (oldSignal * preLevel), 0.95);
        BufWr.ar(mixedSignal, buf, phase, loop: 1);

        // 5. UTGÅNG (Monitorering)
        // För noll latens på din röst: Mixa INPUT direkt med det vi hör från bandet.
        // Detta gör att din röst alltid är ren, medan "ekot" från bandet följer pitchen.
		
		filterOldSignal = LPF.ar(oldSignal, (SampleRate.ir * 0.4 * rate.abs).clip(20, 20000));
        Out.ar(0, Limiter.ar((input*dry) + (filterOldSignal*wet), 0.95));
    }).add;
    s.sync;
    ~tape = Synth(\tape, [\buf, b ]);
    NebInterface.ready(s);
};