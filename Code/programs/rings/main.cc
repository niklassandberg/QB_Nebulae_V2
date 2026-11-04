// miRings - Mutable Instruments Rings (Emilie Gillet, MIT, src/rings and
// src/stmlib) as a JACK program for the Nebulae's "programs" bank.
//
//   miRings --port 3020 [--name miRings] [--no-connect] [file.prog]
//
// Audio: two inputs and two outputs (Rings' ODD and EVEN outputs, to
// system:playback_1/2). "in" (system:capture_1) is the exciter, as Rings'
// IN jack. "fm_in" (system:capture_2) is audio-rate FM: Rings reads its
// pitch once per block, so the mean of each block's 24 samples (2 kHz)
// is added to the pitch, times /rings/fm_in semitones (0 = off). Rings
// computes 24 samples at a time at 48 kHz; the JACK period is cut into
// those blocks, which adds 24 samples (0.5 ms) of latency. Other sample
// rates are refused: Rings' tuning and filters are fixed to 48 kHz.
//
// Control: OSC on 127.0.0.1:<port>, one float per message. Which Nebulae
// control drives which address (and its range) is in the .prog file and
// done by nebulae.py, so this program has fixed addresses only:
//   /rings/note              tonic, MIDI note (60 = C4)
//   /rings/fm                frequency offset, semitones (-48..48)
//   /rings/fm_in             depth of the FM input: semitones at full
//                            scale (0..48, default 0 = off)
//   /rings/structure         0..1 (also selects the chord of the
//   /rings/brightness        0..1  sympathetic-string models)
//   /rings/damping           0..1
//   /rings/position          0..1
//   /rings/model             0..5 resonator models, 6..11 the string
//                            synth ("easter egg") with its fx 0..5
//   /rings/polyphony         1..4
//   /rings/strum             a rising edge (>= 0.5) strums once
//   /rings/internal_exciter  1: Rings excites itself (no input needed)
//   /rings/internal_strum    1: strums by itself on input onsets or
//                            note changes (as with no trigger cable)
//   /rings/level             output gain, 0..2 (default 1)
// The file argument (the .prog that started it) is not read here.

#include <jack/jack.h>
#include <lo/lo.h>

#include <atomic>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unistd.h>

#include "rings/dsp/part.h"
#include "rings/dsp/string_synth_part.h"
#include "rings/dsp/strummer.h"

using namespace rings;

namespace {

const int kNumResonatorModels = 6;   // RESONATOR_MODEL_MODAL .. STRING_AND_REVERB
const int kNumModels = kNumResonatorModels + FX_LAST;
const float kNoiseGateThreshold = 0.00003f;  // as rings.cc

// Values from OSC, read once per 24-sample block by the audio thread.
struct Controls {
  std::atomic<float> note{48.0f};
  std::atomic<float> fm{0.0f};
  std::atomic<float> fm_in{0.0f};
  std::atomic<float> structure{0.4f};
  std::atomic<float> brightness{0.5f};
  std::atomic<float> damping{0.5f};
  std::atomic<float> position{0.5f};
  std::atomic<float> level{1.0f};
  std::atomic<int> model{0};
  std::atomic<int> polyphony{1};
  std::atomic<bool> internal_exciter{true};
  std::atomic<bool> internal_strum{true};
  std::atomic<unsigned> strums{0};  // counts rising edges of /rings/strum
};

Controls controls;
float strum_value = 0.0f;  // last /rings/strum value (OSC thread only)

uint16_t reverb_buffer[32768];
Part part;
StringSynthPart string_synth;
Strummer strummer;

// Audio thread state
float in_block[kMaxBlockSize];
float fm_sum = 0.0f;  // sum of the FM input over the block being filled
float fm_mean = 0.0f;  // its mean over the last complete block
float out_block[kMaxBlockSize];
float aux_block[kMaxBlockSize];
size_t block_pos = 0;
float in_level = 0.0f;
int32_t chord = 0;
int model = -1;
int polyphony = -1;
unsigned strums_done = 0;

jack_client_t* client = nullptr;
jack_port_t* port_in = nullptr;
jack_port_t* port_fm_in = nullptr;
jack_port_t* port_out_l = nullptr;
jack_port_t* port_out_r = nullptr;
volatile sig_atomic_t quit = 0;

float clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

// Tiny values in the resonators' feedback would otherwise be computed as
// denormals, many times slower.
void flushDenormals() {
#if defined(__aarch64__)
  uint64_t fpcr;
  asm volatile("mrs %0, fpcr" : "=r"(fpcr));
  asm volatile("msr fpcr, %0" : : "r"(fpcr | (1ULL << 24)));
#elif defined(__arm__) && defined(__ARM_FP)
  uint32_t fpscr;
  asm volatile("vmrs %0, fpscr" : "=r"(fpscr));
  asm volatile("vmsr fpscr, %0" : : "r"(fpscr | (1U << 24)));
#endif
}

void processBlock() {
  int m = controls.model.load();
  int p = controls.polyphony.load();
  if (m != model) {
    model = m;
    if (m < kNumResonatorModels) {
      part.set_model(static_cast<ResonatorModel>(m));
    } else {
      string_synth.set_fx(static_cast<FxType>(m - kNumResonatorModels));
    }
  }
  if (p != polyphony) {
    polyphony = p;
    part.set_polyphony(p);
    string_synth.set_polyphony(p);
  }

  Patch patch;
  patch.structure = clampf(controls.structure.load(), 0.0f, 0.9995f);
  patch.brightness = clampf(controls.brightness.load(), 0.0f, 1.0f);
  patch.damping = clampf(controls.damping.load(), 0.0f, 1.0f);
  patch.position = clampf(controls.position.load(), 0.0f, 1.0f);

  PerformanceState state;
  state.tonic = controls.note.load();
  state.note = 0.0f;
  float fm_in = clampf(controls.fm_in.load(), 0.0f, 48.0f);
  state.fm = clampf(controls.fm.load() + fm_in * fm_mean, -48.0f, 48.0f);
  state.internal_exciter = controls.internal_exciter.load();
  state.internal_strum = controls.internal_strum.load();
  state.internal_note = false;  // the note always comes from Nebulae
  unsigned s = controls.strums.load();
  state.strum = s != strums_done;
  strums_done = s;

  // The chord follows structure with hysteresis (cv_scaler.cc).
  float c = patch.structure * static_cast<float>(kNumChords - 1);
  float hysteresis = c - chord > 0.0f ? -0.1f : +0.1f;
  chord = static_cast<int32_t>(c + hysteresis + 0.5f);
  if (chord < 0) chord = 0;
  if (chord > kNumChords - 1) chord = kNumChords - 1;
  state.chord = chord;

  if (model >= kNumResonatorModels) {
    strummer.Process(NULL, kMaxBlockSize, &state);
    string_synth.Process(state, patch, in_block, out_block, aux_block, kMaxBlockSize);
  } else {
    // Noise gate on the input (rings.cc)
    for (size_t i = 0; i < kMaxBlockSize; ++i) {
      float x = in_block[i];
      float error = x * x - in_level;
      in_level += error * (error > 0.0f ? 0.1f : 0.0001f);
      float gain = in_level <= kNoiseGateThreshold ? (1.0f / kNoiseGateThreshold) * in_level : 1.0f;
      in_block[i] = gain * x;
    }
    strummer.Process(in_block, kMaxBlockSize, &state);
    part.Process(state, patch, in_block, out_block, aux_block, kMaxBlockSize);
  }

  float level = clampf(controls.level.load(), 0.0f, 2.0f);
  for (size_t i = 0; i < kMaxBlockSize; ++i) {
    out_block[i] = clampf(out_block[i] * level, -1.0f, 1.0f);
    aux_block[i] = clampf(aux_block[i] * level, -1.0f, 1.0f);
  }
}

int onProcess(jack_nframes_t nframes, void*) {
  static thread_local bool flushed = false;
  if (!flushed) {
    flushDenormals();
    flushed = true;
  }
  const float* in = static_cast<const float*>(jack_port_get_buffer(port_in, nframes));
  const float* fm = static_cast<const float*>(jack_port_get_buffer(port_fm_in, nframes));
  float* out_l = static_cast<float*>(jack_port_get_buffer(port_out_l, nframes));
  float* out_r = static_cast<float*>(jack_port_get_buffer(port_out_r, nframes));
  // Each sample goes into the block and the block computed before comes out:
  // a constant delay of one block.
  for (jack_nframes_t i = 0; i < nframes; ++i) {
    in_block[block_pos] = in[i];
    fm_sum += fm[i];
    out_l[i] = out_block[block_pos];
    out_r[i] = aux_block[block_pos];
    if (++block_pos == kMaxBlockSize) {
      fm_mean = fm_sum * (1.0f / kMaxBlockSize);
      fm_sum = 0.0f;
      processBlock();
      block_pos = 0;
    }
  }
  return 0;
}

void onShutdown(void*) {
  std::fprintf(stderr, "miRings: jackd went away\n");
  quit = 1;
}

// One handler for every float address: user_data is the atomic it sets.
int onFloat(const char*, const char*, lo_arg** argv, int, lo_message, void* data) {
  static_cast<std::atomic<float>*>(data)->store(argv[0]->f);
  return 0;
}

int onModel(const char*, const char*, lo_arg** argv, int, lo_message, void*) {
  int m = static_cast<int>(std::lround(argv[0]->f));
  controls.model.store(m < 0 ? 0 : (m > kNumModels - 1 ? kNumModels - 1 : m));
  return 0;
}

int onPolyphony(const char*, const char*, lo_arg** argv, int, lo_message, void*) {
  int p = static_cast<int>(std::lround(argv[0]->f));
  controls.polyphony.store(p < 1 ? 1 : (p > kMaxPolyphony ? kMaxPolyphony : p));
  return 0;
}

int onBool(const char*, const char*, lo_arg** argv, int, lo_message, void* data) {
  static_cast<std::atomic<bool>*>(data)->store(argv[0]->f >= 0.5f);
  return 0;
}

int onStrum(const char*, const char*, lo_arg** argv, int, lo_message, void*) {
  float v = argv[0]->f;
  if (v >= 0.5f && strum_value < 0.5f) {
    controls.strums.fetch_add(1);
  }
  strum_value = v;
  return 0;
}

void onOscError(int num, const char* msg, const char* where) {
  std::fprintf(stderr, "miRings: OSC error %d: %s %s\n", num, msg, where ? where : "");
}

void onSignal(int) { quit = 1; }

void connect(const char* from, const char* to) {
  if (jack_connect(client, from, to) != 0) {
    std::fprintf(stderr, "miRings: could not connect %s -> %s\n", from, to);
  }
}

}  // namespace

int main(int argc, char** argv) {
  std::string port = "3020";
  std::string name = "miRings";
  bool autoconnect = true;
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--port") && i + 1 < argc) {
      port = argv[++i];
    } else if (!std::strcmp(argv[i], "--name") && i + 1 < argc) {
      name = argv[++i];
    } else if (!std::strcmp(argv[i], "--no-connect")) {
      autoconnect = false;
    }
  }

  std::signal(SIGTERM, onSignal);
  std::signal(SIGINT, onSignal);

  strummer.Init(0.01f, kSampleRate / kMaxBlockSize);
  part.Init(reverb_buffer);
  string_synth.Init(reverb_buffer);

  lo_server_thread osc = lo_server_thread_new(port.c_str(), onOscError);
  if (!osc) {
    std::fprintf(stderr, "miRings: cannot listen for OSC on port %s\n", port.c_str());
    return 1;
  }
  lo_server_thread_add_method(osc, "/rings/note", "f", onFloat, &controls.note);
  lo_server_thread_add_method(osc, "/rings/fm", "f", onFloat, &controls.fm);
  lo_server_thread_add_method(osc, "/rings/fm_in", "f", onFloat, &controls.fm_in);
  lo_server_thread_add_method(osc, "/rings/structure", "f", onFloat, &controls.structure);
  lo_server_thread_add_method(osc, "/rings/brightness", "f", onFloat, &controls.brightness);
  lo_server_thread_add_method(osc, "/rings/damping", "f", onFloat, &controls.damping);
  lo_server_thread_add_method(osc, "/rings/position", "f", onFloat, &controls.position);
  lo_server_thread_add_method(osc, "/rings/level", "f", onFloat, &controls.level);
  lo_server_thread_add_method(osc, "/rings/model", "f", onModel, nullptr);
  lo_server_thread_add_method(osc, "/rings/polyphony", "f", onPolyphony, nullptr);
  lo_server_thread_add_method(osc, "/rings/strum", "f", onStrum, nullptr);
  lo_server_thread_add_method(osc, "/rings/internal_exciter", "f", onBool, &controls.internal_exciter);
  lo_server_thread_add_method(osc, "/rings/internal_strum", "f", onBool, &controls.internal_strum);

  // nebulae.py starts the program as soon as the jackd process exists; the
  // server may need a moment more before it takes clients.
  jack_status_t status;
  for (int i = 0; i < 100 && !quit; ++i) {
    client = jack_client_open(name.c_str(), JackNoStartServer, &status);
    if (client) break;
    usleep(100000);
  }
  if (!client) {
    std::fprintf(stderr, "miRings: cannot connect to jackd (status 0x%x)\n", status);
    lo_server_thread_free(osc);
    return 1;
  }
  jack_nframes_t rate = jack_get_sample_rate(client);
  if (rate != static_cast<jack_nframes_t>(kSampleRate)) {
    std::fprintf(stderr, "miRings: jackd runs at %u Hz, Rings needs 48000 (set -r,48000 in the .prog)\n", rate);
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  port_in = jack_port_register(client, "in", JACK_DEFAULT_AUDIO_TYPE, JackPortIsInput, 0);
  port_fm_in = jack_port_register(client, "fm_in", JACK_DEFAULT_AUDIO_TYPE, JackPortIsInput, 0);
  port_out_l = jack_port_register(client, "out_l", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  port_out_r = jack_port_register(client, "out_r", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  if (!port_in || !port_fm_in || !port_out_l || !port_out_r) {
    std::fprintf(stderr, "miRings: cannot register JACK ports\n");
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  jack_set_process_callback(client, onProcess, nullptr);
  jack_on_shutdown(client, onShutdown, nullptr);

  lo_server_thread_start(osc);
  if (jack_activate(client) != 0) {
    std::fprintf(stderr, "miRings: cannot activate the JACK client\n");
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  if (autoconnect) {
    std::string self = jack_get_client_name(client);
    connect("system:capture_1", (self + ":in").c_str());
    connect("system:capture_2", (self + ":fm_in").c_str());
    connect((self + ":out_l").c_str(), "system:playback_1");
    connect((self + ":out_r").c_str(), "system:playback_2");
  }
  std::fprintf(stderr, "miRings: running (JACK %u Hz, period %u, OSC port %s)\n",
               rate, jack_get_buffer_size(client), port.c_str());

  while (!quit) {
    usleep(100000);
  }
  jack_client_close(client);
  lo_server_thread_stop(osc);
  lo_server_thread_free(osc);
  std::fprintf(stderr, "miRings: stopped\n");
  return 0;
}
