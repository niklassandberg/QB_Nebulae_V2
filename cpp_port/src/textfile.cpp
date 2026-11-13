#include "textfile.h"

#include <fcntl.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>

#include "fatal.h"
#include "pyvalue.h"

namespace neb {
namespace textfile {

namespace {
const std::string BOM = "\xef\xbb\xbf";

// Length of the UTF-8 sequence at data[i], 0 when it is not valid: the same
// bytes Python's strict decoder rejects (overlong forms, surrogates, > U+10FFFF).
size_t utf8Length(const std::string &data, size_t i) {
    auto at = [&](size_t k) { return static_cast<unsigned char>(data[k]); };
    unsigned char c = at(i);
    if (c < 0x80) return 1;
    size_t n;
    unsigned char lo = 0x80, hi = 0xBF;
    if (c >= 0xC2 && c <= 0xDF) {
        n = 2;
    } else if (c >= 0xE0 && c <= 0xEF) {
        n = 3;
        if (c == 0xE0) lo = 0xA0;
        if (c == 0xED) hi = 0x9F;
    } else if (c >= 0xF0 && c <= 0xF4) {
        n = 4;
        if (c == 0xF0) lo = 0x90;
        if (c == 0xF4) hi = 0x8F;
    } else {
        return 0;
    }
    if (i + n > data.size()) {
        // Python reports a truncated sequence at its first byte as well.
        return 0;
    }
    if (at(i + 1) < lo || at(i + 1) > hi) return 0;
    for (size_t k = 2; k < n; ++k)
        if (at(i + k) < 0x80 || at(i + k) > 0xBF) return 0;
    return n;
}

PyError osError(int err, const std::string &path) {
    const char *type = err == ENOENT ? "FileNotFoundError"
                       : (err == EACCES || err == EPERM) ? "PermissionError"
                       : err == EISDIR ? "IsADirectoryError"
                                       : "OSError";
    return PyError(type, path + ": " + std::strerror(err));
}
}  // namespace

std::string decode(const std::string &data, const std::string &path) {
    size_t skip = data.compare(0, BOM.size(), BOM) == 0 ? BOM.size() : 0;
    for (size_t i = skip; i < data.size();) {
        size_t n = utf8Length(data, i);
        if (n == 0) fatal::badFile(path, i);
        i += n;
    }
    std::string text;
    text.reserve(data.size() - skip);
    for (size_t i = skip; i < data.size(); ++i) {
        if (data[i] == '\r') {
            text += '\n';
            if (i + 1 < data.size() && data[i + 1] == '\n') ++i;
        } else {
            text += data[i];
        }
    }
    return text;
}

std::string read(const std::string &path) {
    int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0) throw osError(errno, path);
    std::string data;
    char buf[65536];
    while (true) {
        ssize_t n = ::read(fd, buf, sizeof buf);
        if (n < 0) {
            int err = errno;
            ::close(fd);
            throw osError(err, path);
        }
        if (n == 0) break;
        data.append(buf, static_cast<size_t>(n));
    }
    ::close(fd);
    return decode(data, path);
}

std::vector<std::string> lines(const std::string &path) {
    std::string text = read(path);
    std::vector<std::string> out;
    size_t start = 0;
    while (start < text.size()) {
        size_t nl = text.find('\n', start);
        if (nl == std::string::npos) {
            out.push_back(text.substr(start));
            break;
        }
        out.push_back(text.substr(start, nl - start + 1));
        start = nl + 1;
    }
    return out;
}

bool isOSError(const std::string &type) {
    return type == "OSError" || type == "FileNotFoundError" || type == "PermissionError" ||
           type == "IsADirectoryError" || type == "BadTextFile";
}

}  // namespace textfile
}  // namespace neb
