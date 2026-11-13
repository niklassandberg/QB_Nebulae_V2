#include "nconfig.h"

#include <cctype>
#include <sstream>

#include "textfile.h"

namespace neb {

namespace {
std::string lower(std::string s) {
    for (auto &c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

std::string rstrip(const std::string &s) { return pyRstrip(s); }

size_t indentOf(const std::string &s) { return pyIndent(s); }
}  // namespace

NConfig::NConfig(const std::string &path) {
    std::string text;
    try {
        text = textfile::read(path);
    } catch (const PyError &e) {
        if (!textfile::isOSError(e.type)) throw;
        return;  // configparser.read() skips a file it cannot open
    }
    std::istringstream f(text);
    std::string line;
    std::map<std::string, std::string> *cur = nullptr;
    std::string curKey;
    size_t curIndent = 0;
    bool inValue = false;
    std::vector<std::string> pendingEmpty;
    while (std::getline(f, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::string stripped = strip(line);
        bool comment = !stripped.empty() && (stripped[0] == '#' || stripped[0] == ';');
        if (stripped.empty() || comment) {
            if (stripped.empty() && inValue) pendingEmpty.push_back("");
            if (comment) continue;
            continue;
        }
        size_t indent = indentOf(line);
        if (inValue && cur && indent > curIndent) {
            std::string &v = (*cur)[curKey];
            for (auto &e : pendingEmpty) v += "\n" + e;
            pendingEmpty.clear();
            v += "\n" + stripped;
            continue;
        }
        pendingEmpty.clear();
        inValue = false;
        if (stripped.front() == '[' && rstrip(line).back() == ']' && indent == 0) {
            std::string name = stripped.substr(1, stripped.size() - 2);
            if (name == "DEFAULT") {
                cur = &defaults_;
            } else {
                if (sections_.count(name)) throw PyError("DuplicateSectionError", name);
                cur = &sections_[name];
            }
            continue;
        }
        if (!cur) throw PyError("MissingSectionHeaderError", line);
        size_t sep = stripped.find_first_of("=:");
        if (sep == std::string::npos || sep == 0) throw PyError("ParsingError", line);
        std::string key = lower(rstrip(stripped.substr(0, sep)));
        std::string value = strip(stripped.substr(sep + 1));
        if (cur->count(key)) throw PyError("DuplicateOptionError", key);
        (*cur)[key] = value;
        curKey = key;
        curIndent = indent;
        inValue = true;
    }
}

bool NConfig::lookup(const std::string &section, const std::string &key, std::string &out) const {
    auto s = sections_.find(section);
    if (s != sections_.end()) {
        auto k = s->second.find(key);
        if (k != s->second.end()) {
            out = k->second;
            return true;
        }
    }
    auto d = defaults_.find(key);
    if (d == defaults_.end()) return false;
    out = d->second;
    return true;
}

bool NConfig::interpolate(const std::string &section, const std::string &raw, std::string &out, int depth) const {
    if (depth > 10) return false;  // InterpolationDepthError
    out.clear();
    for (size_t i = 0; i < raw.size(); ++i) {
        if (raw[i] != '%') {
            out += raw[i];
            continue;
        }
        if (i + 1 < raw.size() && raw[i + 1] == '%') {
            out += '%';
            ++i;
            continue;
        }
        if (i + 1 < raw.size() && raw[i + 1] == '(') {
            size_t close = raw.find(")s", i + 2);
            if (close == std::string::npos) return false;
            std::string name = lower(raw.substr(i + 2, close - i - 2));
            std::string ref, expanded;
            if (!lookup(section, name, ref)) return false;
            if (!interpolate(section, ref, expanded, depth + 1)) return false;
            out += expanded;
            i = close + 1;
            continue;
        }
        return false;  // InterpolationSyntaxError
    }
    return true;
}

Value NConfig::getValue(const std::string &section, const std::string &var, const Value &defvalue) const {
    if (section != "DEFAULT" && !sections_.count(section)) return defvalue;  // NoSectionError
    std::string raw, value;
    if (!lookup(section, lower(var), raw)) return defvalue;
    if (!interpolate(section, raw, value, 1)) return defvalue;
    return Value::str(value);
}

}  // namespace neb
