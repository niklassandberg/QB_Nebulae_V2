// wavewriter.py: the record buffer as a 16-bit stereo 48 kHz WAV on the USB
// stick (neb_buffer_<n>.wav), n counted in buffer_cnt.txt.
#pragma once

#include <functional>
#include <optional>
#include <string>
#include <vector>

#include "classlogger.h"
#include "pyvalue.h"

namespace neb {

// fileloader.FileLoader as WaveWriter uses it.
class UsbStick {
public:
    virtual ~UsbStick() = default;
    virtual void mount() = 0;
    virtual void umount() = 0;
    virtual bool isUSBMounted() = 0;
};

struct DiskSpace {
    unsigned long long f_bsize = 0, f_bfree = 0;
};

class WaveWriter {
public:
    WaveWriter(UsbStick &usb, std::string fpath = "/home/alarm/QB_Nebulae_V2/Code/config/buffer_cnt.txt",
               std::string outpath = "/mnt/memory/");
    bool WriteStereoWaveFile(const std::vector<double> &datal, const std::vector<double> &datar,
                             const Value &length);

    std::string fpath, outpath;
    std::optional<long long> num_written;  // unset: buffer_cnt.txt had only blank lines
    std::string default_name = "neb_buffer_", extension = ".wav";
    int nchannels = 2, sampwidth = 2, framerate = 48000;
    std::function<DiskSpace(const std::string &)> statvfs;  // os.statvfs("/mnt/memory")

private:
    void writeCount();
    UsbStick &usb_;
    Logger log_{"WaveWriter"};
};

}  // namespace neb
