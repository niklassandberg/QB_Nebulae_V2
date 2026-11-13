#include <chrono>
#include <random>
#include <thread>

#include "nebio_api.h"

namespace neb {

namespace {
class SystemClock : public Clock {
public:
    double time() override {
        using namespace std::chrono;
        return duration<double>(system_clock::now().time_since_epoch()).count();
    }
    void sleep(double s) override { std::this_thread::sleep_for(std::chrono::duration<double>(s)); }
};

class SystemRandom : public Random {
public:
    int randint(int a, int b) override { return std::uniform_int_distribution<int>(a, b)(gen_); }

private:
    std::mt19937 gen_{std::random_device{}()};
};

SystemClock systemClock;
SystemRandom systemRandom;
NebioC *g_nebio = nullptr;
Clock *g_clock = &systemClock;
Random *g_random = &systemRandom;
}  // namespace

NebioC &nebioC() {
    if (!g_nebio) throw PyError("RuntimeError", "setNebioC() not called");
    return *g_nebio;
}
Clock &clock() { return *g_clock; }
Random &random() { return *g_random; }
void setNebioC(NebioC *c) { g_nebio = c; }
void setClock(Clock *c) { g_clock = c ? c : &systemClock; }
void setRandom(Random *r) { g_random = r ? r : &systemRandom; }

}  // namespace neb
