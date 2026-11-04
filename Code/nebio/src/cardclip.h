// ALSA control "Input Clip Count" of the patched card driver
// (Resources/kernel/0003-rpi-proto-input-clip-count.patch).
#pragma once

#include <chrono>
#include <mutex>

namespace nebio {

class CardClip {
public:
    static CardClip &instance();

    // See nebio_card_clip_count.
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
