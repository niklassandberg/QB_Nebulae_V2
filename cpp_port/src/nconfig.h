// nconfig.py: ./nebulae.opt read with Python's configparser rules (sections,
// "key = value" or "key: value", keys lowercased, # and ; comment lines,
// indented continuation lines, %(name)s interpolation).
#pragma once

#include <map>
#include <string>
#include <vector>

#include "pyvalue.h"

namespace neb {

class NConfig {
public:
    // PyError with configparser's exception names for a malformed file.
    explicit NConfig(const std::string &path = "./nebulae.opt");
    // The text value, or defvalue when missing or not interpolatable.
    Value getValue(const std::string &section, const std::string &var, const Value &defvalue) const;

private:
    bool lookup(const std::string &section, const std::string &key, std::string &out) const;
    bool interpolate(const std::string &section, const std::string &raw, std::string &out, int depth) const;

    std::map<std::string, std::string> defaults_;
    std::map<std::string, std::map<std::string, std::string>> sections_;
};

}  // namespace neb
