#include "adc.h"

#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <cstring>

#include "log.h"

namespace nebio {

Mcp3208::~Mcp3208() { close(); }

bool Mcp3208::open(const std::string &device, uint32_t speedHz) {
    close();
    fd_ = ::open(device.c_str(), O_RDWR);
    if (fd_ < 0) {
        logError("could not open %s", device.c_str());
        return false;
    }
    uint8_t mode = SPI_MODE_0;
    uint8_t bits = 8;
    speedHz_ = speedHz;
    if (ioctl(fd_, SPI_IOC_WR_MODE, &mode) < 0 || ioctl(fd_, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(fd_, SPI_IOC_WR_MAX_SPEED_HZ, &speedHz_) < 0) {
        logError("could not configure %s", device.c_str());
        close();
        return false;
    }
    return true;
}

void Mcp3208::close() {
    if (fd_ >= 0) ::close(fd_);
    fd_ = -1;
}

bool Mcp3208::readAll(uint16_t codes[8]) {
    if (fd_ < 0) return false;
    uint8_t tx[8][3];
    uint8_t rx[8][3];
    spi_ioc_transfer xfer[8];
    int chans[8];
    int n = 0;
    for (int ch = 0; ch < 8; ++ch)
        if (mask_ & (1u << ch)) chans[n++] = ch;
    if (n == 0) return true;
    std::memset(xfer, 0, sizeof(xfer));
    std::memset(rx, 0, sizeof(rx));
    for (int i = 0; i < n; ++i) {
        int ch = chans[i];
        // Start bit + single-ended, channel split over two bytes (see MCP3208.py).
        tx[i][0] = 0b110 | (ch > 3 ? 1 : 0);
        tx[i][1] = static_cast<uint8_t>((ch & 3) << 6);
        tx[i][2] = 0;
        xfer[i].tx_buf = reinterpret_cast<unsigned long>(tx[i]);
        xfer[i].rx_buf = reinterpret_cast<unsigned long>(rx[i]);
        xfer[i].len = 3;
        xfer[i].speed_hz = speedHz_;
        xfer[i].bits_per_word = 8;
        xfer[i].cs_change = i < n - 1 ? 1 : 0;  // release CS between conversions
    }
    // SPI_IOC_MESSAGE(n) needs a compile-time n in C++; same request number:
    const unsigned long request = _IOC(_IOC_WRITE, SPI_IOC_MAGIC, 0, SPI_MSGSIZE(n));
    if (ioctl(fd_, request, xfer) < 0) return false;
    for (int i = 0; i < n; ++i) codes[chans[i]] = ((rx[i][1] << 8) | rx[i][2]) & 0xFFF;
    return true;
}

}  // namespace nebio
