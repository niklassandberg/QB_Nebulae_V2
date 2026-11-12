// The Laboratory: a 2-minute stereo record buffer played as a loop, recorded
// and reset as the granular looper's (Programs/TheLaboratory/thelaboratory.prog).
// The sound is in looper.h.
//
//   thelaboratory --port 3023 [file.prog] [--no-connect]

#include <jack/jack.h>
#include <lo/lo.h>
#include <sys/mman.h>

#include <atomic>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <unistd.h>

#include "looper.h"

namespace {

// Levels from Nebulae (the .prog's osc: lines).
std::atomic<float> record{0.0f};     // record button, latching
std::atomic<float> fileHeld{0.0f};   // file button held (filestate)
std::atomic<float> start{0.0f};
std::atomic<float> speed{1.0f};      // -1..1
std::atomic<float> mix{1.0f};        // 0 = input, 1 = loop

// Rising edges of reset, counted in the OSC thread so a short trigger is
// never missed between two periods. With file held it clears the buffer.
std::atomic<unsigned> resets{0};
std::atomic<unsigned> clears{0};

std::unique_ptr<Looper> looper;
unsigned resetsDone = 0;   // audio thread only
unsigned clearsDone = 0;

jack_client_t* client = nullptr;
jack_port_t* in_port[2];
jack_port_t* out_port[2];
volatile sig_atomic_t quit = 0;

int process(jack_nframes_t nframes, void*) {
  Looper& l = *looper;
  unsigned c = clears.load();
  if (c != clearsDone) {
    clearsDone = c;
    l.clear();
  }
  l.setRecording(record.load() >= 0.5f);
  unsigned r = resets.load();
  if (r != resetsDone) {
    resetsDone = r;
    l.reset();
  }
  l.setStart(start.load());
  l.setSpeed(speed.load());
  float wet = mix.load();
  wet = wet < 0 ? 0 : (wet > 1 ? 1 : wet);

  const float* in[2];
  float* out[2];
  for (int ch = 0; ch < 2; ++ch) {
    in[ch] = static_cast<const float*>(jack_port_get_buffer(in_port[ch], nframes));
    out[ch] = static_cast<float*>(jack_port_get_buffer(out_port[ch], nframes));
  }
  for (jack_nframes_t i = 0; i < nframes; ++i) {
    float x[2] = {in[0][i], in[1][i]}, y[2];
    l.process(x, y);
    for (int ch = 0; ch < 2; ++ch) out[ch][i] = x[ch] * (1 - wet) + y[ch] * wet;
  }
  return 0;
}

int onLevel(const char*, const char*, lo_arg** argv, int, lo_message, void* data) {
  static_cast<std::atomic<float>*>(data)->store(argv[0]->f);
  return 0;
}

int onReset(const char*, const char*, lo_arg** argv, int, lo_message, void*) {
  static bool high = false;  // OSC thread only
  bool now = argv[0]->f >= 0.5f;
  if (now && !high) (fileHeld.load() >= 0.5f ? clears : resets).fetch_add(1);
  high = now;
  return 0;
}

void onShutdown(void*) { quit = 1; }
void onSignal(int) { quit = 1; }

}  // namespace

int main(int argc, char** argv) {
  std::string port = "3023";
  bool autoconnect = true;
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--port") && i + 1 < argc) port = argv[++i];
    if (!std::strcmp(argv[i], "--no-connect")) autoconnect = false;
  }
  std::signal(SIGTERM, onSignal);
  std::signal(SIGINT, onSignal);

  lo_server_thread osc = lo_server_thread_new(port.c_str(), nullptr);
  if (!osc) {
    std::fprintf(stderr, "thelaboratory: cannot listen for OSC on port %s\n", port.c_str());
    return 1;
  }
  lo_server_thread_add_method(osc, "/lab/record", "f", onLevel, &record);
  lo_server_thread_add_method(osc, "/lab/file_held", "f", onLevel, &fileHeld);
  lo_server_thread_add_method(osc, "/lab/start", "f", onLevel, &start);
  lo_server_thread_add_method(osc, "/lab/speed", "f", onLevel, &speed);
  lo_server_thread_add_method(osc, "/lab/mix", "f", onLevel, &mix);
  lo_server_thread_add_method(osc, "/lab/reset", "f", onReset, nullptr);

  // jackd may not take clients yet when the program starts.
  for (int i = 0; i < 100 && !quit && !client; ++i) {
    client = jack_client_open("thelaboratory", JackNoStartServer, nullptr);
    if (!client) usleep(100000);
  }
  if (!client) {
    std::fprintf(stderr, "thelaboratory: cannot connect to jackd\n");
    lo_server_thread_free(osc);
    return 1;
  }
  // The buffer at JACK's rate, allocated and locked before the audio starts:
  // no page faults in the real-time thread.
  jack_nframes_t rate = jack_get_sample_rate(client);
  looper = std::make_unique<Looper>(static_cast<double>(rate));
  if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0)
    std::fprintf(stderr, "thelaboratory: could not lock memory, the buffer may page\n");

  const char* in_names[2] = {"in_l", "in_r"};
  const char* out_names[2] = {"out_l", "out_r"};
  for (int ch = 0; ch < 2; ++ch) {
    in_port[ch] = jack_port_register(client, in_names[ch], JACK_DEFAULT_AUDIO_TYPE, JackPortIsInput, 0);
    out_port[ch] = jack_port_register(client, out_names[ch], JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  }
  jack_set_process_callback(client, process, nullptr);
  jack_on_shutdown(client, onShutdown, nullptr);
  lo_server_thread_start(osc);
  if (jack_activate(client) != 0) {
    std::fprintf(stderr, "thelaboratory: cannot activate the JACK client\n");
    jack_client_close(client);
    lo_server_thread_free(osc);
    return 1;
  }
  if (autoconnect) {
    std::string self = jack_get_client_name(client);
    for (int ch = 0; ch < 2; ++ch) {
      std::string capture = "system:capture_" + std::to_string(ch + 1);
      std::string playback = "system:playback_" + std::to_string(ch + 1);
      jack_connect(client, capture.c_str(), (self + ":" + in_names[ch]).c_str());
      jack_connect(client, (self + ":" + out_names[ch]).c_str(), playback.c_str());
    }
  }
  std::fprintf(stderr, "thelaboratory: running (JACK %u Hz, period %u, %.0f s buffer, OSC port %s)\n",
               rate, jack_get_buffer_size(client), Looper::kSeconds, port.c_str());

  while (!quit) usleep(100000);

  jack_client_close(client);
  lo_server_thread_stop(osc);
  lo_server_thread_free(osc);
  return 0;
}
