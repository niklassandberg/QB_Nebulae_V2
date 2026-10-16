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
    // Reads all 8 channels in one ioctl. Returns false on error.
    bool readAll(uint16_t codes[8]);

private:
    int fd_ = -1;
    uint32_t speedHz_ = 1000000;
};

}  // namespace nebio
