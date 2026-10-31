Server.local.options.memSize = 256 * 1024 * 2;    // 256MB — plenty of headroom
Server.local.options.bindAddress = "0.0.0.0";
Server.local.options.maxLogins = 4;
Server.local.options.blockSize = 64;
Server.local.options.numInputBusChannels = 2;
Server.local.options.numOutputBusChannels = 2;

Server.internal.options.memSize = 256 * 1024 * 2;
Server.internal.options.bindAddress = "0.0.0.0";
Server.internal.options.maxLogins = 4;
Server.internal.options.blockSize = 128;
Server.internal.options.numInputBusChannels = 2;
Server.internal.options.numOutputBusChannels = 2;

s = Server.default;

NebInterface.init(s);

// scsynth early: when the boot instrument is SuperCollider and bootinstr.txt
// has its JACK settings ("jack,64-3-48000"), startup.sh starts that jackd as
// soon as the card is there. Boot the server on it now instead of when
// Nebulae loads the patch (~1 s sooner sound); the patch's s.waitForBoot then
// finds it running. NebInterface.earlyBoot holds a patch Nebulae sends
// meanwhile until the boot is confirmed (a second boot from the patch killed
// the first one and, with it, jackd). jackd is ready for clients when its
// "system" client exists (/dev/shm is empty at every boot). Not ready within
// 15 s, or another bank: nothing, the patch boots the server as before.
fork {
	var cfg = "/home/alarm/QB_Nebulae_V2/Code/config/bootinstr.txt";
	var lines = if(File.exists(cfg)) { File.readAllString(cfg).split($\n) } { [] };
	var sc = lines.any { |l| l == "bank,supercollider" };
	var jack = lines.any { |l| l.beginsWith("jack,") };
	var ready = { File.exists("/dev/shm/jack_sem.0_default_system")
		and: { "pgrep -x jackd > /dev/null".systemCmd == 0 } };
	var tries = 0;
	if(sc and: jack) {
		while { ready.value.not and: { tries < 150 } } { 0.1.wait; tries = tries + 1 };
		if(ready.value and: { s.serverRunning.not and: { s.serverBooting.not } }) {
			"Nebulae: jackd is up, booting scsynth early".postln;
			NebInterface.earlyBoot = true;
			s.waitForBoot({ NebInterface.earlyBoot = false }, onFailure: { NebInterface.earlyBoot = false });
		}
	}
};
