// Shim: the Daisy's SDRAM pool is ordinary memory on the Pi.
#pragma once
#include <utility>

namespace infrasonic {

class SDRAM {
 public:
  template <typename T, class... Args>
  static T* allocate(Args&&... args) {
    return new T(std::forward<Args>(args)...);
  }
};

}  // namespace infrasonic
