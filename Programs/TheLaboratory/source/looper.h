// The Laboratory's record buffer and its playhead, without JACK (tested on
// its own). Stereo, kSeconds at the JACK rate.
//
// - record on: a new take from the beginning of the buffer, heard live while
//   it records. Past kSeconds it records on circularly, overwriting the
//   oldest: the take is then the last kSeconds.
// - record off: the take ends there; the loop plays from start.
// - The loop runs from start (0..1 of the take) to the end of the take.
// - reset: the playhead jumps to start. clear: the take is gone (one still
//   recording starts again from the beginning).
// - speed -1..1: 1 = normal speed forward, -1 = normal speed backward.
// No clicks: a jump cross-fades from the old position, and the playhead
// fades out over the last kFadeSeconds before the loop's edge.
#pragma once

#include <cmath>
#include <cstddef>
#include <vector>

class Looper {
 public:
  static constexpr double kSeconds = 120.0;
  static constexpr double kFadeSeconds = 0.005;
  static constexpr double kMinLoopSeconds = 0.01;

  explicit Looper(double sampleRate)
      : size_(static_cast<size_t>(kSeconds * sampleRate)),
        fade_(static_cast<int>(kFadeSeconds * sampleRate)),
        minLoop_(kMinLoopSeconds * sampleRate) {
    for (auto& ch : buf_) ch.assign(size_, 0.0f);  // touched now, not in the audio thread
  }

  size_t length() const { return len_; }
  size_t capacity() const { return size_; }
  bool recording() const { return recording_; }
  double position() const { return pos_; }

  void setRecording(bool on) {
    if (on == recording_) return;
    recording_ = on;
    if (on) {
      clearTake();
    } else {
      pos_ = loopStart();
      fadeLeft_ = 0;
    }
  }

  void clear() {
    clearTake();
    pos_ = 0.0;
    fadeLeft_ = 0;
  }

  void reset() {
    if (!recording_ && len_ > 0) jump(loopStart());
  }

  void setStart(float start) { start_ = start < 0 ? 0 : (start > 1 ? 1 : start); }

  // Exactly +-1 near the ends, as the granular looper does.
  void setSpeed(float speed) {
    if (std::fabs(std::fabs(speed) - 1.0f) <= 0.025f) speed = speed > 0 ? 1.0f : -1.0f;
    speed_ = speed < -1 ? -1 : (speed > 1 ? 1 : speed);
  }

  // One stereo sample in, the wet signal out.
  void process(const float in[2], float out[2]) {
    if (recording_) {
      write(in);
      out[0] = in[0];
      out[1] = in[1];
      return;
    }
    if (len_ == 0) {
      out[0] = out[1] = 0.0f;
      return;
    }
    float a[2];
    read(pos_, a);
    float g = edgeGain();
    a[0] *= g;
    a[1] *= g;
    if (fadeLeft_ > 0) {
      float b[2];
      read(fadePos_, b);
      float old = static_cast<float>(fadeLeft_) / fade_;  // 1 -> 0
      a[0] = a[0] * (1 - old) + b[0] * old;
      a[1] = a[1] * (1 - old) + b[1] * old;
      fadePos_ += speed_;
      --fadeLeft_;
    }
    out[0] = a[0];
    out[1] = a[1];
    advance();
  }

 private:
  void clearTake() {
    len_ = 0;
    write_ = 0;
    oldest_ = 0;
  }

  void write(const float in[2]) {
    buf_[0][write_] = in[0];
    buf_[1][write_] = in[1];
    write_ = (write_ + 1) % size_;
    if (len_ < size_)
      ++len_;
    else
      oldest_ = write_;  // circular: the oldest sample is the next one written
  }

  double loopStart() const {
    double hi = static_cast<double>(len_);
    double lo = start_ * hi;
    if (hi - lo < minLoop_) lo = hi > minLoop_ ? hi - minLoop_ : 0.0;
    return lo;
  }

  // 1 in the loop, down to 0 on the last sample before the edge the playhead
  // runs towards.
  float edgeGain() const {
    double toEdge = (speed_ >= 0 ? static_cast<double>(len_) - pos_ : pos_ - loopStart()) - 1;
    return toEdge >= fade_ ? 1.0f : static_cast<float>(toEdge < 0 ? 0 : toEdge / fade_);
  }

  // Linear interpolation; outside the take is silence.
  void read(double rel, float out[2]) const {
    if (rel < 0 || rel >= static_cast<double>(len_)) {
      out[0] = out[1] = 0.0f;
      return;
    }
    size_t i = static_cast<size_t>(rel);
    float frac = static_cast<float>(rel - static_cast<double>(i));
    size_t p0 = (oldest_ + i) % size_;
    size_t p1 = i + 1 < len_ ? (oldest_ + i + 1) % size_ : p0;
    for (int c = 0; c < 2; ++c) out[c] = buf_[c][p0] + (buf_[c][p1] - buf_[c][p0]) * frac;
  }

  void jump(double to) {
    fadePos_ = pos_;
    fadeLeft_ = fade_;
    pos_ = to;
  }

  void advance() {
    pos_ += speed_;
    double lo = loopStart();
    double hi = static_cast<double>(len_);
    if (speed_ >= 0) {
      if (pos_ >= hi) jump(lo + (pos_ - hi));
      else if (pos_ < lo) jump(lo);  // start turned past the playhead
    } else {
      if (pos_ < lo) jump(hi - (lo - pos_));
      else if (pos_ >= hi) jump(hi - 1);
    }
  }

  std::vector<float> buf_[2];
  size_t size_;
  int fade_;
  double minLoop_;
  size_t len_ = 0;     // samples in the take
  size_t write_ = 0;   // next sample written
  size_t oldest_ = 0;  // where the take begins (moves once it records circularly)
  bool recording_ = false;
  double pos_ = 0.0;   // playhead, samples from the take's beginning
  double fadePos_ = 0.0;
  int fadeLeft_ = 0;
  float start_ = 0.0f;
  float speed_ = 1.0f;
};
