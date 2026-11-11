// audrey - AudreyTouch's sound engine (Infrasonic Audio / Synthux Academy,
// MIT; DaisySP MIT and LGPL) as a JACK program, without touch and MIDI.
//
//   audrey --port 3021 [--name audrey] [--no-connect] [file.prog]
//
// One input, two outputs, 48 kHz only.
//
// OSC on 127.0.0.1:<port>, one float per message, 0..1 through the knob curves:
//   /audrey/feedback     feedback gain, the main control (S30)
//   /audrey/input        input level (S31)
//   /audrey/reverb_mix   dry/wet (S32)
//   /audrey/reverb_size  reverb decay (S33)
//   /audrey/lpf          low pass in the loop (S34)
//   /audrey/hpf          high pass in the loop (S35)
//   /audrey/body         body (S37; 1 = top of the fader = shortest delay);
//                        with the LFO on: its rate and spread
//   /audrey/shape        envelope shape (P11 + S37)
//   /audrey/lfo          body LFO: 0 off, 1 fast (1-8 Hz), 2 slow (0.01-0.5 Hz)
//                        (the right switch)
//   /audrey/note         string pitch, MIDI note 16..88 (pads + S36 + octave)
//   /audrey/gate         >= 0.5: note on (as touching a pad), < 0.5: note off
//   /audrey/drone        1: the loop keeps ringing without a gate (P11 + P02)
//   /audrey/source       >= 0.5: the input is the left output (a feedback
//                        cable), < 0.5: the input jack (default)
//   /audrey/echo         >= 0.5: the echo on (not on the hardware)
//   /audrey/echo_tap     tap tempo: rising edges (>= 0.5); the time between
//                        two taps is the echo time (0.03..4.9 s)
//   /audrey/echo_feedback  echo feedback 0..kEchoMaxFeedback; above about 1 the
//                        repeats never die (soft-clipped, dub style)
//   /audrey/echo_cutoff  centre of the band-pass in the echo loop, Hz
//                        (kEchoMinCutoff..kEchoMaxCutoff, 800 at start)
//   /audrey/echo_volume  how much goes into the echo while it is on, 0..1
//                        (1 at start); the repeats follow it
//   /audrey/echo_wownflutter  wow and flutter on the echo, 0..1 (0 at start):
//                        higher is more unstable

#include <jack/jack.h>
#include <lo/lo.h>

#include <atomic>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <unistd.h>

#include "FeedbackSynthEngine.h"
#include "ParameterRegistry.h"
#include "DSPUtils.h"

using namespace infrasonic;
using namespace infrasonic::FeedbackSynth;

namespace {

const float kSampleRate = 48000.0f;
const size_t kBlockSize = 4;  // as FeedbackSynth_main.cpp
const float kOutputLevel = 1.0f;  // normalized, fixed at max
const float kEchoStartTime = 0.25f;  // seconds
const float kEchoMinTime = 0.03f;
const float kEchoMaxFeedback = 1.5f;
const float kEchoMaxTime = 4.9f;    // the echo holds 5 s; a longer gap starts a new tap
const float kEchoMinCutoff = 50.0f;
const float kEchoMaxCutoff = 12000.0f;

// Wow and flutter on the echo time, as on a worn tape machine: a slow wow, a
// fast flutter and a random drift. amount 0..1 (/audrey/echo_wownflutter):
// the depths grow with amount, the speeds wander more with amount.
const float kWowHz = 0.6f;
const float kFlutterHz = 7.0f;
const float kWowDepth = 0.006f;       // seconds at amount 1
const float kFlutterDepth = 0.0005f;
const float kDriftDepth = 0.004f;
const float kWowRateSpread = 0.6f;    // part of the rate it wanders at amount 1
const float kFlutterRateSpread = 0.3f;
const float kAmountLag = 0.05f;       // seconds: a turned encoder does not jump
const float kTwoPi = 6.2831853f;

uint32_t wow_rng = 0x9e3779b9u;

float wowNoise() {  // -1..1
  wow_rng ^= wow_rng << 13;
  wow_rng ^= wow_rng >> 17;
  wow_rng ^= wow_rng << 5;
  return (wow_rng >> 8) * (2.0f / 16777216.0f) - 1.0f;
}

// A slow random value -1..1: a new target every 0.2..1 s, slewed to it.
struct Wander {
  float value = 0.0f, target = 0.0f, left = 0.0f;
  float step(float dt, float lag) {
    left -= dt;
    if (left <= 0.0f) {
      target = wowNoise();
      left = 0.6f + 0.4f * wowNoise();
    }
    value += (target - value) * (dt / lag);
    return value;
  }
};

struct WowFlutter {
  float amount_target = 0.0f, amount = 0.0f;
  float wow_phase = 0.0f, flutter_phase = 0.0f;
  Wander wow_rate, flutter_rate, drift;

  // Seconds to add to the echo time for the next dt seconds.
  float next(float dt) {
    amount += (amount_target - amount) * (dt / kAmountLag);
    if (amount < 1e-4f) return 0.0f;
    float wow_hz = kWowHz * (1.0f + kWowRateSpread * amount * wow_rate.step(dt, 0.5f));
    float flutter_hz = kFlutterHz * (1.0f + kFlutterRateSpread * amount * flutter_rate.step(dt, 0.2f));
    wow_phase += wow_hz * dt;
    wow_phase -= std::floor(wow_phase);
    flutter_phase += flutter_hz * dt;
    flutter_phase -= std::floor(flutter_phase);
    float depth = amount;
    return depth * (kWowDepth * std::sin(kTwoPi * wow_phase)
                    + kFlutterDepth * std::sin(kTwoPi * flutter_phase)
                    + kDriftDepth * drift.step(dt, 0.3f));
  }
};

enum class Parameter : uint8_t {
  Frequency,
  FeedbackGain,
  FeedbackBody,
  FeedbackLPFCutoff,
  FeedbackHPFCutoff,
  ReverbMix,
  ReverbDecay,
  OutputVolume,
  InputVolume,
  EnvelopeShape,
  LFOFrequency,
  LFODistribution,
};

// Applied by the audio thread once per block when the counter changed.
struct Control {
  std::atomic<float> value;
  std::atomic<unsigned> sets{0};
  unsigned applied = 0;  // audio thread only
  explicit Control(float v) : value(v) {}
  bool take(float& v) {
    unsigned s = sets.load();
    if (s == applied) return false;
    applied = s;
    v = value.load();
    return true;
  }
};

// Defaults: AudreyTouch's registered initial values, as normalized knobs.
Control c_feedback{0.0f}, c_input{0.5f}, c_reverb_mix{0.0f},
    c_reverb_size{0.0f}, c_lpf{1.0f}, c_hpf{0.0f}, c_body{1.0f}, c_shape{0.0f},
    c_lfo{0.0f}, c_note{40.0f}, c_gate{0.0f}, c_drone{0.0f}, c_source{0.0f},
    c_echo{0.0f}, c_echo_tap{0.0f}, c_echo_feedback{0.5f}, c_echo_cutoff{800.0f},
    c_echo_volume{1.0f}, c_echo_wownflutter{0.0f};

Engine engine;
ParameterRegistry<Parameter> params;
daisysp::Limiter limiter[2];

// Audio thread state
float in_block[kBlockSize], out_l_block[kBlockSize], out_r_block[kBlockSize];
size_t block_pos = 0;
float body = 1.0f;  // last body value (knob orientation)
int lfo_mode = 0;
bool gate = false;
bool input_from_output = false;
bool echo_tap_high = false;
bool echo_on = false;
float echo_volume = 1.0f;
WowFlutter wow_flutter;
uint64_t samples_done = 0;
uint64_t last_tap = 0;  // in samples_done, 0 = none

jack_client_t* client = nullptr;
jack_port_t* port_in = nullptr;
jack_port_t* port_out_l = nullptr;
jack_port_t* port_out_r = nullptr;
volatile sig_atomic_t quit = 0;

void registerParams() {
  using namespace std::placeholders;
  // As Controls::registerParams() in FeedbackSynthControls.cpp
  params.Register(Parameter::Frequency, 40.0f, 16.0f, 88.0f,
                  std::bind(&Engine::SetStringPitch, &engine, _1), 0.2f);
  params.Register(Parameter::FeedbackGain, -60.0f, -60.0f, 12.0f,
                  std::bind(&Engine::SetFeedbackGain, &engine, _1));
  params.Register(Parameter::FeedbackBody, 0.001f, 0.001f, 0.1f,
                  std::bind(&Engine::SetFeedbackDelay, &engine, _1), 1.0f, daisysp::Mapping::EXP);
  params.Register(Parameter::FeedbackLPFCutoff, 18000.0f, 100.0f, 18000.0f,
                  std::bind(&Engine::SetFeedbackLPFCutoff, &engine, _1), 0.05f, daisysp::Mapping::LOG);
  params.Register(Parameter::FeedbackHPFCutoff, 250.0f, 10.0f, 4000.0f,
                  std::bind(&Engine::SetFeedbackHPFCutoff, &engine, _1), 0.05f, daisysp::Mapping::LOG);
  params.Register(Parameter::ReverbMix, 0.0f, 0.0f, 1.0f,
                  std::bind(&Engine::SetReverbMix, &engine, _1));
  params.Register(Parameter::ReverbDecay, 0.2f, 0.2f, 1.0f,
                  std::bind(&Engine::SetReverbFeedback, &engine, _1));
  params.Register(Parameter::OutputVolume, 0.5f, 0.0f, 1.0f,
                  std::bind(&Engine::SetOutputLevel, &engine, _1), 0.05f, daisysp::Mapping::EXP);
  params.Register(Parameter::InputVolume, 0.5f, 0.0f, 5.0f,
                  std::bind(&Engine::SetInputLevel, &engine, _1), 0.05f, daisysp::Mapping::EXP);
  params.Register(Parameter::EnvelopeShape, 0.0f, 0.0f, 1.0f,
                  std::bind(&Engine::SetShape, &engine, _1));
  params.Register(Parameter::LFOFrequency, 1.0f, 0.01f, 7.0f,
                  std::bind(&Engine::SetLFOFrequency, &engine, _1));
  params.Register(Parameter::LFODistribution, .5f, 0.f, 1.0f,
                  std::bind(&Engine::SetLFODistribution, &engine, _1));
}

// As Controls::processBodyValue(): value = the inverted fader.
void processBodyValue(float value) {
  if (lfo_mode == 1) {
    params.UpdateNormalized(Parameter::LFOFrequency, 1.f + ((1.f - value) * 7.f));
  } else if (lfo_mode == 2) {
    params.UpdateNormalized(Parameter::LFOFrequency, .01f + ((1.0f - value) * .5f));
  } else {
    params.UpdateNormalized(Parameter::FeedbackBody, value);
  }
  params.UpdateNormalized(Parameter::LFODistribution, value);
}

void applyControls() {
  float v;
  if (c_feedback.take(v)) params.UpdateNormalized(Parameter::FeedbackGain, v);
  if (c_input.take(v)) params.UpdateNormalized(Parameter::InputVolume, v);
  if (c_reverb_mix.take(v)) params.UpdateNormalized(Parameter::ReverbMix, v);
  if (c_reverb_size.take(v)) params.UpdateNormalized(Parameter::ReverbDecay, ftension(daisysp::fclamp(v, 0.f, 1.f), -3.0f));
  if (c_lpf.take(v)) params.UpdateNormalized(Parameter::FeedbackLPFCutoff, v);
  if (c_hpf.take(v)) params.UpdateNormalized(Parameter::FeedbackHPFCutoff, v);
  if (c_shape.take(v)) params.UpdateNormalized(Parameter::EnvelopeShape, v);
  if (c_note.take(v)) params.Update(Parameter::Frequency, v);
  bool body_changed = c_body.take(v);
  if (body_changed) body = daisysp::fclamp(v, 0.f, 1.f);
  if (c_lfo.take(v)) {
    int m = static_cast<int>(std::lround(v));
    lfo_mode = m < 0 ? 0 : (m > 2 ? 2 : m);
    engine.SetBodyLFOOn(lfo_mode != 0);
    body_changed = true;
  }
  if (body_changed) processBodyValue(1.0f - body);
  if (c_gate.take(v)) {
    bool g = v >= 0.5f;
    if (g && !gate) engine.NoteOn();
    if (!g && gate) engine.NoteOff();
    gate = g;
  }
  if (c_drone.take(v)) engine.DroneMode(v >= 0.5f);
  if (c_source.take(v)) input_from_output = v >= 0.5f;
  bool echo_changed = false;
  if (c_echo.take(v)) {
    echo_on = v >= 0.5f;
    echo_changed = true;
  }
  if (c_echo_volume.take(v)) {
    echo_volume = daisysp::fclamp(v, 0.f, 1.f);
    echo_changed = true;
  }
  if (echo_changed) engine.SetEchoDelaySendAmount(echo_on ? echo_volume : 0.0f);
  if (c_echo_feedback.take(v)) engine.SetEchoDelayFeedback(daisysp::fclamp(v, 0.f, kEchoMaxFeedback));
  if (c_echo_wownflutter.take(v)) wow_flutter.amount_target = daisysp::fclamp(v, 0.f, 1.f);
  if (c_echo_cutoff.take(v))
    engine.SetEchoDelayFilterFreq(daisysp::fclamp(v, kEchoMinCutoff, kEchoMaxCutoff));
  if (c_echo_tap.take(v)) {
    bool high = v >= 0.5f;
    if (high && !echo_tap_high) {
      float gap = last_tap ? (samples_done - last_tap) / kSampleRate : 0.0f;
      if (gap >= kEchoMinTime && gap <= kEchoMaxTime) engine.SetEchoDelayTime(gap);
      last_tap = samples_done;
    }
    echo_tap_high = high;
  }
}

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

// One block as FeedbackSynth_main.cpp's AudioCallback.
void processBlock() {
  applyControls();
  engine.SetEchoDelayTimeMod(wow_flutter.next(kBlockSize / kSampleRate));
  samples_done += kBlockSize;
  params.Process();
  for (size_t i = 0; i < kBlockSize; ++i) {
    engine.Process(in_block[i], out_l_block[i], out_r_block[i]);
  }
  limiter[0].ProcessBlock(out_l_block, kBlockSize, 0.7f);
  limiter[1].ProcessBlock(out_r_block, kBlockSize, 0.7f);
}

int onProcess(jack_nframes_t nframes, void*) {
  static thread_local bool flushed = false;
  if (!flushed) {
    flushDenormals();
    flushed = true;
  }
  const float* in = static_cast<const float*>(jack_port_get_buffer(port_in, nframes));
  float* out_l = static_cast<float*>(jack_port_get_buffer(port_out_l, nframes));
  float* out_r = static_cast<float*>(jack_port_get_buffer(port_out_r, nframes));
  // One block of delay.
  for (jack_nframes_t i = 0; i < nframes; ++i) {
    in_block[block_pos] = input_from_output ? out_l_block[block_pos] : in[i];
    out_l[i] = out_l_block[block_pos];
    out_r[i] = out_r_block[block_pos];
    if (++block_pos == kBlockSize) {
      processBlock();
      block_pos = 0;
    }
  }
  return 0;
}

void onShutdown(void*) {
  std::fprintf(stderr, "audrey: jackd went away\n");
  quit = 1;
}

int onFloat(const char*, const char*, lo_arg** argv, int, lo_message, void* data) {
  Control* c = static_cast<Control*>(data);
  c->value.store(argv[0]->f);
  c->sets.fetch_add(1);
  return 0;
}

void onOscError(int num, const char* msg, const char* where) {
  std::fprintf(stderr, "audrey: OSC error %d: %s %s\n", num, msg, where ? where : "");
}

void onSignal(int) { quit = 1; }

void connect(const char* from, const char* to) {
  if (jack_connect(client, from, to) != 0) {
    std::fprintf(stderr, "audrey: could not connect %s -> %s\n", from, to);
  }
}

}  // namespace

int main(int argc, char** argv) {
  std::string port = "3021";
  std::string name = "audrey";
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

  engine.Init(kSampleRate);
  params.Init(kSampleRate / kBlockSize);
  registerParams();
  params.UpdateNormalized(Parameter::OutputVolume, kOutputLevel);
  engine.SetEchoDelayTime(kEchoStartTime);
  for (auto& lim : limiter) lim.Init();
  for (Control* c : {&c_feedback, &c_input, &c_reverb_mix, &c_reverb_size, &c_lpf,
                     &c_hpf, &c_body, &c_shape, &c_lfo, &c_note, &c_echo_feedback,
                     &c_echo_cutoff, &c_echo_volume, &c_echo_wownflutter}) {
    c->sets.fetch_add(1);
  }

  lo_server_thread osc = lo_server_thread_new(port.c_str(), onOscError);
  if (!osc) {
    std::fprintf(stderr, "audrey: cannot listen for OSC on port %s\n", port.c_str());
    return 1;
  }
  struct { const char* path; Control* c; } addresses[] = {
      {"/audrey/feedback", &c_feedback}, {"/audrey/input", &c_input},
      {"/audrey/reverb_mix", &c_reverb_mix},
      {"/audrey/reverb_size", &c_reverb_size}, {"/audrey/lpf", &c_lpf},
      {"/audrey/hpf", &c_hpf}, {"/audrey/body", &c_body}, {"/audrey/shape", &c_shape},
      {"/audrey/lfo", &c_lfo}, {"/audrey/note", &c_note}, {"/audrey/gate", &c_gate},
      {"/audrey/drone", &c_drone}, {"/audrey/source", &c_source},
      {"/audrey/echo", &c_echo}, {"/audrey/echo_tap", &c_echo_tap},
      {"/audrey/echo_feedback", &c_echo_feedback}, {"/audrey/echo_cutoff", &c_echo_cutoff},
      {"/audrey/echo_volume", &c_echo_volume},
      {"/audrey/echo_wownflutter", &c_echo_wownflutter}};
  for (auto& a : addresses) {
    lo_server_thread_add_method(osc, a.path, "f", onFloat, a.c);
  }

  // jackd may not take clients yet when the program starts.
  jack_status_t status;
  for (int i = 0; i < 100 && !quit; ++i) {
    client = jack_client_open(name.c_str(), JackNoStartServer, &status);
    if (client) break;
    usleep(100000);
  }
  if (!client) {
    std::fprintf(stderr, "audrey: cannot connect to jackd (status 0x%x)\n", status);
    lo_server_thread_free(osc);
    return 1;
  }
  jack_nframes_t rate = jack_get_sample_rate(client);
  if (rate != static_cast<jack_nframes_t>(kSampleRate)) {
    std::fprintf(stderr, "audrey: jackd runs at %u Hz, audrey needs 48000 (set -r,48000 in the .prog)\n", rate);
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  port_in = jack_port_register(client, "in", JACK_DEFAULT_AUDIO_TYPE, JackPortIsInput, 0);
  port_out_l = jack_port_register(client, "out_l", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  port_out_r = jack_port_register(client, "out_r", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  if (!port_in || !port_out_l || !port_out_r) {
    std::fprintf(stderr, "audrey: cannot register JACK ports\n");
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  jack_set_process_callback(client, onProcess, nullptr);
  jack_on_shutdown(client, onShutdown, nullptr);

  lo_server_thread_start(osc);
  if (jack_activate(client) != 0) {
    std::fprintf(stderr, "audrey: cannot activate the JACK client\n");
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  if (autoconnect) {
    std::string self = jack_get_client_name(client);
    connect("system:capture_1", (self + ":in").c_str());
    connect((self + ":out_l").c_str(), "system:playback_1");
    connect((self + ":out_r").c_str(), "system:playback_2");
  }
  std::fprintf(stderr, "audrey: running (JACK %u Hz, period %u, OSC port %s)\n",
               rate, jack_get_buffer_size(client), port.c_str());

  while (!quit) {
    usleep(100000);
  }
  jack_client_close(client);
  lo_server_thread_stop(osc);
  lo_server_thread_free(osc);
  std::fprintf(stderr, "audrey: stopped\n");
  return 0;
}
