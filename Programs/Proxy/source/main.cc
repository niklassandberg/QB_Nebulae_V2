// proxy - the smallest Nebulae program: a template for C/C++ programs of the
// "programs" bank (as Supercollider/Proxy/proxy.sc is for the SC bank).
//
// It passes the two audio inputs to the two outputs, times one value it gets
// over OSC. Copy this folder, rename it, and put your sound in process().
//
//   proxy --port 3022 [file.prog]
//
// What every program needs (Programs/README.md):
//   - nebulae.py starts it with --port <oscport of the .prog> and the .prog's
//     path, and stops it with SIGTERM;
//   - it connects itself to jackd (which may need a moment) and its ports to
//     system:capture_* / system:playback_*;
//   - it listens for OSC floats on 127.0.0.1:<port>. Which knob sends which
//     path is written in the .prog (osc: lines), not here.

#include <jack/jack.h>
#include <lo/lo.h>

#include <atomic>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <string>
#include <unistd.h>

namespace {

std::atomic<float> level{1.0f};  // /proxy/level, 0..1 (proxy.prog: blend)

jack_client_t* client = nullptr;
jack_port_t* in_port[2];
jack_port_t* out_port[2];
volatile sig_atomic_t quit = 0;

// The sound: called by jackd for every period (nframes samples per channel).
int process(jack_nframes_t nframes, void*) {
  float gain = level.load();
  for (int c = 0; c < 2; ++c) {
    const float* in = static_cast<const float*>(jack_port_get_buffer(in_port[c], nframes));
    float* out = static_cast<float*>(jack_port_get_buffer(out_port[c], nframes));
    for (jack_nframes_t i = 0; i < nframes; ++i) {
      out[i] = in[i] * gain;
    }
  }
  return 0;
}

// One OSC float -> the atomic given as user data.
int onFloat(const char*, const char*, lo_arg** argv, int, lo_message, void* data) {
  static_cast<std::atomic<float>*>(data)->store(argv[0]->f);
  return 0;
}

void onShutdown(void*) { quit = 1; }
void onSignal(int) { quit = 1; }

}  // namespace

int main(int argc, char** argv) {
  std::string port = "3022";
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--port") && i + 1 < argc) port = argv[++i];
  }
  std::signal(SIGTERM, onSignal);
  std::signal(SIGINT, onSignal);

  // OSC: one method per path
  lo_server_thread osc = lo_server_thread_new(port.c_str(), nullptr);
  if (!osc) {
    std::fprintf(stderr, "proxy: cannot listen for OSC on port %s\n", port.c_str());
    return 1;
  }
  lo_server_thread_add_method(osc, "/proxy/level", "f", onFloat, &level);
  lo_server_thread_start(osc);

  // JACK: jackd runs, but may not take clients yet
  for (int i = 0; i < 100 && !quit && !client; ++i) {
    client = jack_client_open("proxy", JackNoStartServer, nullptr);
    if (!client) usleep(100000);
  }
  if (!client) {
    std::fprintf(stderr, "proxy: cannot connect to jackd\n");
    lo_server_thread_free(osc);
    return 1;
  }
  const char* in_names[2] = {"in_l", "in_r"};
  const char* out_names[2] = {"out_l", "out_r"};
  for (int c = 0; c < 2; ++c) {
    in_port[c] = jack_port_register(client, in_names[c], JACK_DEFAULT_AUDIO_TYPE, JackPortIsInput, 0);
    out_port[c] = jack_port_register(client, out_names[c], JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
  }
  jack_set_process_callback(client, process, nullptr);
  jack_on_shutdown(client, onShutdown, nullptr);
  jack_activate(client);

  // Connect to the Nebulae's inputs and outputs
  std::string self = jack_get_client_name(client);
  for (int c = 0; c < 2; ++c) {
    std::string capture = "system:capture_" + std::to_string(c + 1);
    std::string playback = "system:playback_" + std::to_string(c + 1);
    jack_connect(client, capture.c_str(), (self + ":" + in_names[c]).c_str());
    jack_connect(client, (self + ":" + out_names[c]).c_str(), playback.c_str());
  }
  std::fprintf(stderr, "proxy: running (OSC port %s)\n", port.c_str());

  while (!quit) usleep(100000);

  jack_client_close(client);
  lo_server_thread_stop(osc);
  lo_server_thread_free(osc);
  return 0;
}
