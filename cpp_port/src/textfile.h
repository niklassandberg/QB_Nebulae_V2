// textfile.py: text files a person can edit are UTF-8, with or without a
// BOM; \r\n and \r line ends read as \n. Any other encoding:
// fatal::badFile().
#pragma once

#include <string>
#include <vector>

namespace neb {
namespace textfile {

std::string decode(const std::string &data, const std::string &path);
// PyError FileNotFoundError, PermissionError, IsADirectoryError or OSError.
std::string read(const std::string &path);
// As iterating a file in text mode: every line ends with "\n" but the last.
std::vector<std::string> lines(const std::string &path);

// The PyError types that are OSError subclasses in Python.
bool isOSError(const std::string &type);

}  // namespace textfile
}  // namespace neb
