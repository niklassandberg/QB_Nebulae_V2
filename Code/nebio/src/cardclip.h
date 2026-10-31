// cardclip.h - the input clip counter of the codec card driver
// (Resources/kernel/0003-rpi-proto-input-clip-count.patch: ALSA control
// "Input Clip Count" on hw:sndrpiproto, left and right). The same for every
// engine (Csound, SuperCollider, Pure Data).
#pragma once

#include <chrono>
#include <mutex>

namespace nebio {

class CardClip {
public:
    static CardClip &instance();

    // Clipped samples of both channels so far, wraps from INT_MAX to 0: only
    // changes matter. -1 while the card has no counter (older driver, nebio
    // built without alsa-lib): then no clip is shown.
    int count();

private:
    CardClip() = default;
    bool open();
    void close();

    std::mutex mutex_;
    void *ctl_ = nullptr;    // snd_ctl_t
    void *value_ = nullptr;  // snd_ctl_elem_value_t
    std::chrono::steady_clock::time_point nextOpen_{};
    bool reported_ = false;  // found / not found is logged once
};

}  // namespace nebio
