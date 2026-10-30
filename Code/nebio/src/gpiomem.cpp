#include "gpiomem.h"

#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <fstream>
#include <iterator>

#include "log.h"

namespace nebio {

namespace {

// SoC from the device tree "compatible" list (NUL separated strings).
// Returns a description for supported SoCs, "" otherwise.
std::string supportedBoard(std::string &found) {
    std::ifstream f("/proc/device-tree/compatible", std::ios::binary);
    std::string all((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    for (char &c : all)
        if (c == '\0') c = ' ';
    found = all;
    struct Soc {
        const char *compatible;
        const char *board;
    };
    // Same GPIO register layout on all of these.
    static const Soc kSupported[] = {
        {"brcm,bcm2711", "BCM2711 (Pi 4)"},
        {"brcm,bcm2837", "BCM2837 (Pi 3)"},
        {"brcm,bcm2710", "BCM2837 (Pi 3)"},
        {"brcm,bcm2836", "BCM2836 (Pi 2)"},
        {"brcm,bcm2709", "BCM2836 (Pi 2)"},
        {"brcm,bcm2835", "BCM2835 (Pi 1/Zero)"},
        {"brcm,bcm2708", "BCM2835 (Pi 1/Zero)"},
    };
    if (all.find("brcm,bcm2712") != std::string::npos) return "";  // Pi 5: RP1, different layout
    for (const Soc &s : kSupported)
        if (all.find(s.compatible) != std::string::npos) return s.board;
    return "";
}

}  // namespace

GpioMem &GpioMem::instance() {
    static GpioMem *mem = new GpioMem();  // never destroyed, see GpioChip
    return *mem;
}

bool GpioMem::open() {
    if (regs_) return true;
    std::string compatible;
    board_ = supportedBoard(compatible);
    if (board_.empty()) {
        logError("fast GPIO not supported on this board (compatible: %s)", compatible.c_str());
        return false;
    }
    int fd = ::open("/dev/gpiomem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (fd < 0) {
        logError("could not open /dev/gpiomem");
        return false;
    }
    void *p = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    ::close(fd);
    if (p == MAP_FAILED) {
        logError("could not map /dev/gpiomem");
        return false;
    }
    regs_ = static_cast<volatile uint32_t *>(p);
    logInfo("fast GPIO available on %s", board_.c_str());
    return true;
}

int GpioMem::function(unsigned pin) const {
    if (!regs_ || pin > 53) return -1;
    return static_cast<int>((regs_[kFsel0 + pin / 10] >> ((pin % 10) * 3)) & 7);
}

void GpioMem::write(uint32_t setMask, uint32_t clearMask) {
    if (!regs_) return;
    if (((setMask | clearMask) & ~writable_) != 0 && !warned_) {
        warned_ = true;
        logError("fast GPIO: write to pins outside the allowed mask ignored (0x%08x)",
                 static_cast<unsigned>((setMask | clearMask) & ~writable_));
    }
    setMask &= writable_;
    clearMask &= writable_;
    if (setMask) regs_[kSet0] = setMask;
    if (clearMask) regs_[kClr0] = clearMask;
    __sync_synchronize();  // the write reaches the pin before any later read
}

}  // namespace nebio
