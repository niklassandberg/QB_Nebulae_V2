// nebmixer.py: the WM8731's ALSA mixer: input gain ("Capture", 0-31) and the
// HiFi output switch.
#pragma once

#include <string>

#include "pyvalue.h"

namespace neb {

// The libasound mixer calls nebmixer makes. The real one (nebmixer_alsa.cpp)
// looks "Capture" up by a proper selem id, where the original passed the
// name's text as the id.
class Asound {
public:
    virtual ~Asound() = default;
    virtual int mixer_open(void **mixer, int mode) = 0;
    virtual int mixer_attach(void *mixer, const std::string &device) = 0;
    virtual int mixer_detach(void *mixer, const std::string &device) = 0;
    virtual int mixer_selem_register(void *mixer) = 0;
    virtual int mixer_load(void *mixer) = 0;
    virtual int mixer_close(void *mixer) = 0;
    virtual void *mixer_find_selem_name(void *mixer, const std::string &name) = 0;  // "Capture"
    virtual int selem_id_malloc(void **sid) = 0;
    virtual void selem_id_set_name(void *sid, const std::string &name) = 0;
    virtual void selem_id_set_index(void *sid, unsigned index) = 0;
    virtual void *mixer_find_selem(void *mixer, void *sid) = 0;
    virtual int selem_set_capture_volume(void *elem, int channel, long value) = 0;
    virtual int selem_set_playback_switch_all(void *elem, int value) = 0;
};

namespace nebmixer {

constexpr int LEFT = 0;
constexpr int RIGHT = 1;

void setAsound(Asound *lib);  // nullptr: libasound could not be loaded
bool init(const std::string &device = "hw:sndrpiproto", const std::string &capturecontrol = "Capture",
          const std::string &hifi_control_name = "Output Mixer HiFi");
bool remove(const std::string &device = "hw:sndrpiproto");
void enable();
void disable();
void inputLevel(const Value &volume);
void resetForTests();

}  // namespace nebmixer
}  // namespace neb
