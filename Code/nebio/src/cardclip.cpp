#include "cardclip.h"

#include <climits>

#include "log.h"

#ifdef NEBIO_HAVE_ALSA
#include <alsa/asoundlib.h>
#endif

namespace nebio {

namespace {
constexpr const char *kCard = "hw:sndrpiproto";
constexpr const char *kControl = "Input Clip Count";
constexpr auto kRetry = std::chrono::seconds(1);  // the card is not there yet / older driver
}  // namespace

CardClip &CardClip::instance() {
    static CardClip c;
    return c;
}

#ifdef NEBIO_HAVE_ALSA

int CardClip::count() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!ctl_ && !open())
        return -1;
    auto *ctl = static_cast<snd_ctl_t *>(ctl_);
    auto *value = static_cast<snd_ctl_elem_value_t *>(value_);
    if (snd_ctl_elem_read(ctl, value) < 0) {
        close();
        return -1;
    }
    long long sum = static_cast<long long>(snd_ctl_elem_value_get_integer(value, 0))
                    + snd_ctl_elem_value_get_integer(value, 1);
    return static_cast<int>(sum & INT_MAX);
}

// At most once per kRetry: count() runs in every UI update.
bool CardClip::open() {
    auto now = std::chrono::steady_clock::now();
    if (now < nextOpen_)
        return false;
    nextOpen_ = now + kRetry;
    snd_ctl_t *ctl = nullptr;
    if (snd_ctl_open(&ctl, kCard, SND_CTL_NONBLOCK) < 0)
        return false;
    snd_ctl_elem_value_t *value = nullptr;
    snd_ctl_elem_value_malloc(&value);
    snd_ctl_elem_value_set_interface(value, SND_CTL_ELEM_IFACE_MIXER);
    snd_ctl_elem_value_set_name(value, kControl);
    if (snd_ctl_elem_read(ctl, value) < 0) {
        if (!reported_)
            logInfo("card driver has no \"%s\": no input clip warning", kControl);
        reported_ = true;
        snd_ctl_elem_value_free(value);
        snd_ctl_close(ctl);
        return false;
    }
    if (!reported_)
        logInfo("input clipping from the card driver (\"%s\")", kControl);
    reported_ = true;
    ctl_ = ctl;
    value_ = value;
    return true;
}

void CardClip::close() {
    if (value_)
        snd_ctl_elem_value_free(static_cast<snd_ctl_elem_value_t *>(value_));
    if (ctl_)
        snd_ctl_close(static_cast<snd_ctl_t *>(ctl_));
    value_ = nullptr;
    ctl_ = nullptr;
}

#else

int CardClip::count() { return -1; }
bool CardClip::open() { return false; }
void CardClip::close() {}

#endif

}  // namespace nebio
