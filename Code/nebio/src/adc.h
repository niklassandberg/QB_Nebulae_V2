// adc.h - MCP3208 over spidev. Same command bytes as MCP3208.py.
#pragma once

#include <cstdint>
#include <string>

namespace nebio {

class Mcp3208 {
public:
    ~Mcp3208();
    bool open(const std::string &device, uint32_t speedHz);
    void close();
    bool ok() const { return fd_ >= 0; }
    // Channels to read (bit n = channel n). Unread channels keep the value
    // codes[] already holds. Default: all 8.
    void setChannelMask(uint8_t mask) { mask_ = mask; }
    // Reads the masked channels in one ioctl. Returns false on error.
    bool readAll(uint16_t codes[8]);

private:
    int fd_ = -1;
    uint32_t speedHz_ = 1000000;
    uint8_t mask_ = 0xFF;
};

}  // namespace nebio
