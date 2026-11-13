#include "wavewriter.h"

#include <sys/stat.h>
#include <sys/statvfs.h>

#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>

#include "settings.h"
#include "textfile.h"

namespace neb {

namespace {
void le16(std::string &out, uint16_t v) {
    out += static_cast<char>(v & 0xff);
    out += static_cast<char>(v >> 8);
}

void le32(std::string &out, uint32_t v) {
    for (int k = 0; k < 4; ++k) out += static_cast<char>((v >> (8 * k)) & 0xff);
}

// numpy's astype('int16') of an in-range float: toward zero.
int16_t toInt16(double x) { return static_cast<int16_t>(static_cast<int32_t>(std::trunc(x))); }
}  // namespace

WaveWriter::WaveWriter(UsbStick &usb, std::string fpath_, std::string outpath_)
    : fpath(std::move(fpath_)), outpath(std::move(outpath_)), usb_(usb) {
    statvfs = [](const std::string &path) {
        struct statvfs st {};
        if (::statvfs(path.c_str(), &st) != 0) throw PyError(errno == ENOENT ? "FileNotFoundError" : "OSError", path);
        DiskSpace d;
        d.f_bsize = st.f_bsize;
        d.f_bfree = st.f_bfree;
        return d;
    };
    struct stat st;
    if (::stat(fpath.c_str(), &st) == 0 && S_ISREG(st.st_mode) && st.st_size > 0) {
        for (const std::string &line : textfile::lines(fpath)) {
            if (strip(line).empty()) continue;
            auto n = pyInt(line);
            if (!n) throw PyError("ValueError", "invalid literal for int()");
            num_written = *n;
        }
    } else {
        num_written = 0;
        writeCount();
    }
}

void WaveWriter::writeCount() {
    if (remountFs) std::system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw");
    std::ofstream f(fpath, std::ios::trunc);
    if (!f) throw PyError("FileNotFoundError", fpath);
    f << *num_written;
    f.close();
    if (remountFs) std::system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro");
}

bool WaveWriter::WriteStereoWaveFile(const std::vector<double> &datal, const std::vector<double> &datar,
                                     const Value &lengthValue) {
    bool success = false;
    // Csound's channel value is a float: a whole number of frames.
    long long length = toInt(lengthValue);
    usb_.mount();
    if (usb_.isUSBMounted()) {
        NLOG(log_, INFO, "USB Mounted, proceeding");
        if (!num_written) throw PyError("AttributeError", "'WaveWriter' object has no attribute 'num_written'");
        std::string filename = outpath + default_name + std::to_string(*num_written) + extension;
        const double maxamp = 32767.0;
        if (length > 0) {
            DiskSpace disk = statvfs("/mnt/memory");
            unsigned long long bytesToWrite = static_cast<unsigned long long>(length) * nchannels * sampwidth;
            unsigned long long bytesAvailable = disk.f_bsize * disk.f_bfree;
            NLOG(log_, INFO, "Calculated length: %lld", length);
            if (bytesToWrite < bytesAvailable) {
                // datal[idx:end] as numpy slices: never past the end.
                size_t nl = std::min<size_t>(datal.size(), length), nr = std::min<size_t>(datar.size(), length);
                std::FILE *out = nl == nr ? std::fopen(filename.c_str(), "wb") : nullptr;
                if (out) {
                    NLOG(log_, INFO, "Writing Audio File. . . ");
                    uint32_t dataBytes = static_cast<uint32_t>(nl * nchannels * sampwidth);
                    std::string header;
                    header += "RIFF";
                    le32(header, 36 + dataBytes);
                    header += "WAVEfmt ";
                    le32(header, 16);
                    le16(header, 1);  // PCM
                    le16(header, nchannels);
                    le32(header, framerate);
                    le32(header, framerate * nchannels * sampwidth);
                    le16(header, nchannels * sampwidth);
                    le16(header, sampwidth * 8);
                    header += "data";
                    le32(header, dataBytes);
                    std::string frames;
                    frames.reserve(dataBytes);
                    for (size_t i = 0; i < nl; ++i) {
                        le16(frames, static_cast<uint16_t>(toInt16(datal[i] * maxamp)));
                        le16(frames, static_cast<uint16_t>(toInt16(datar[i] * maxamp)));
                    }
                    bool ok = std::fwrite(header.data(), 1, header.size(), out) == header.size() &&
                              std::fwrite(frames.data(), 1, frames.size(), out) == frames.size();
                    ok = std::fclose(out) == 0 && ok;
                    if (ok) {
                        NLOG(log_, INFO, "Done.");
                        *num_written += 1;
                        try {
                            writeCount();
                            success = true;
                        } catch (const PyError &) {
                            NLOG(log_, ERROR, "Could not write file!");
                            std::remove(filename.c_str());
                        }
                    } else {
                        NLOG(log_, ERROR, "Could not write file!");
                        std::remove(filename.c_str());
                    }
                } else {
                    // A half-written file is copied in from the stick at the
                    // next boot and Csound crashes on it.
                    NLOG(log_, ERROR, "Could not write file!");
                    std::remove(filename.c_str());
                }
            } else {
                NLOG(log_, WARNING, "Not enough room to write file.");
            }
        } else {
            NLOG(log_, WARNING, "Buffer is empty. Nothing valuable to write.");
        }
    } else {
        NLOG(log_, WARNING, "No USB Present -- not storing buffer");
    }
    usb_.umount();
    return success;
}

}  // namespace neb
