#include "nebmixer.h"

#include <algorithm>

namespace neb::nebmixer {

namespace {
Asound *lib = nullptr;
bool haveMixer = false;  // _mixer is not None
void *mixer = nullptr;
void *capture = nullptr;
void *hifi = nullptr;
bool enabled = true;
}  // namespace

void setAsound(Asound *l) { lib = l; }

bool init(const std::string &device, const std::string &capturecontrol, const std::string &hifi_control_name) {
    if (haveMixer) return true;
    if (!lib) return false;
    haveMixer = true;
    mixer = nullptr;
    if (lib->mixer_open(&mixer, 0) < 0) {
        haveMixer = false;
        return false;
    }
    if (lib->mixer_attach(mixer, device) < 0) {
        lib->mixer_close(mixer);
        haveMixer = false;
        return false;
    }
    if (lib->mixer_selem_register(mixer) < 0 || lib->mixer_load(mixer) < 0) {
        remove();
        return false;
    }
    capture = lib->mixer_find_selem_name(mixer, capturecontrol);
    if (!capture) {
        remove();
        return false;
    }
    void *sid = nullptr;
    lib->selem_id_malloc(&sid);
    lib->selem_id_set_name(sid, hifi_control_name);
    lib->selem_id_set_index(sid, 0);
    hifi = lib->mixer_find_selem(mixer, sid);  // missing: no output switch
    return true;
}

bool remove(const std::string &device) {
    if (!haveMixer) return true;
    lib->mixer_detach(mixer, device);
    lib->mixer_close(mixer);
    capture = hifi = nullptr;
    mixer = nullptr;
    haveMixer = false;
    return true;
}

void enable() {
    enabled = true;
    if (!lib || !hifi) return;
    lib->selem_set_playback_switch_all(hifi, 1);
}

void disable() {
    enabled = false;
    if (!lib || !hifi) return;
    lib->selem_set_playback_switch_all(hifi, 0);
}

void inputLevel(const Value &volume) {
    if (!enabled) return;
    if (!init()) return;
    if (!capture) return;
    long v = static_cast<long>(std::max<long long>(0, std::min<long long>(31, toInt(volume))));
    lib->selem_set_capture_volume(capture, LEFT, v);
    lib->selem_set_capture_volume(capture, RIGHT, v);
}

void resetForTests() {
    haveMixer = false;
    mixer = capture = hifi = nullptr;
    enabled = true;
}

}  // namespace neb::nebmixer
