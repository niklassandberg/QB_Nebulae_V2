#include "settings.h"

#include <sys/stat.h>

#include <cstdlib>
#include <fstream>

#include "textfile.h"

namespace neb {

bool remountFs = false;

bool OrderedDict::has(const std::string &k) const {
    for (auto &kv : items_)
        if (kv.first == k) return true;
    return false;
}

const Value &OrderedDict::at(const std::string &k) const {
    for (auto &kv : items_)
        if (kv.first == k) return kv.second;
    throw PyError("KeyError", k);
}

void OrderedDict::set(const std::string &k, const Value &v) {
    for (auto &kv : items_)
        if (kv.first == k) {
            kv.second = v;
            return;
        }
    items_.emplace_back(k, v);
}

namespace {
std::string rstrip(const std::string &s) { return pyRstrip(s); }

// "key,value[,...]": key and the first value; IndexError without a comma.
std::pair<std::string, std::string> keyValue(const std::string &line) {
    std::string s = rstrip(line);
    size_t comma = s.find(',');
    if (comma == std::string::npos) throw PyError("IndexError", "list index out of range");
    size_t next = s.find(',', comma + 1);
    return {s.substr(0, comma), s.substr(comma + 1, next == std::string::npos ? std::string::npos : next - comma - 1)};
}

bool isFileWithData(const std::string &path) {
    struct stat st;
    return ::stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode) && st.st_size > 0;
}

// float(x), or x itself when it is not a number text.
Value floatOrSelf(const Value &item) {
    if (item.type == Value::Str) {
        auto f = pyFloat(item.s);
        return f ? F(*f) : item;
    }
    return F(toFloat(item));
}
}  // namespace

SettingManager::SettingManager(const OrderedDict *config) : configData(config) {}

void SettingManager::read() {
    std::vector<std::string> defaultList = textfile::lines(filepath + defaultsfilename);
    populateDefaultDict(defaultList, defaultDict);
    std::string fpath = filepath + filename;
    if (isFileWithData(fpath)) {
        NLOG(log_, INFO, "Found Previously saved settings");
        std::vector<std::string> settingList;
        for (auto &line : textfile::lines(fpath))
            if (!strip(line).empty()) settingList.push_back(line);
        populateDict(settingList, settingDict);
        // Settings added later are missing from an older file; without them
        // they would never be saved.
        for (auto &kv : defaultDict.items())
            if (!settingDict.has(kv.first)) settingDict.set(kv.first, kv.second);
    } else {
        NLOG(log_, INFO, "Could not locate previous settings.");
        populateDict(defaultList, settingDict);
    }
    mutableSettings = settingDict;
    haveMutable = true;
}

void SettingManager::write() {
    if (remountFs) std::system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw");
    std::ofstream f(filepath + filename, std::ios::binary | std::ios::trunc);
    if (!f) {
        NLOG(log_, ERROR, "Could not write .nebsettings file");
        return;
    }
    for (auto &line : lines) f << line;
    f.close();
    if (remountFs) std::system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro");
}

void SettingManager::update(const Value &now) {
    lastUpdate = now;
    lines.clear();
    for (auto &kv : settingDict.items()) {
        Value v = mutable_().at(kv.first);
        settingDict.set(kv.first, v);
        lines.push_back(kv.first + "," + pyStr(v) + "\n");
    }
}

Value SettingManager::getDefault(const std::string &key) const {
    if (!defaultDict.has(key)) return Value::none();
    Value out = floatOrSelf(defaultDict.at(key));
    return out.isNone() ? I(0) : out;
}

Value SettingManager::load(const std::string &key) const {
    if (!settingDict.has(key)) return Value::none();
    Value out = floatOrSelf(settingDict.at(key));
    if (out.isNone()) out = defaultDict.at(key);
    if (out.isNone()) out = I(0);
    NLOG(log_, DEBUG, "Loading %s value: %s", key.c_str(), pyStr(out).c_str());
    return out;
}

void SettingManager::populateDict(const std::vector<std::string> &list, OrderedDict &dict) {
    for (auto &line : list) {
        auto kv = keyValue(line);
        dict.set(kv.first, Value::str(kv.second));
    }
}

void SettingManager::populateDefaultDict(const std::vector<std::string> &list, OrderedDict &dict) {
    bool haveNewVal = false;  // new_val is one local for the whole loop
    Value new_val;
    for (auto &line : list) {
        std::string s = rstrip(line);
        size_t comma = s.find(',');
        std::string newKey = s.substr(0, comma);
        auto field = [&]() { return keyValue(line).second; };
        if (configData && configData->has(newKey) && newKey.find("_alt") != std::string::npos) {
            const Value &c = configData->at(newKey);
            if (c.type == Value::Str) {
                dict.set(newKey, c);
            } else {
                if (c.type != Value::List && c.type != Value::Str)
                    throw PyError("TypeError", "object is not subscriptable");
                if (c.list.empty()) throw PyError("IndexError", "list index out of range");
                const Value &first = c.list[0];
                auto f = first.type == Value::Str ? pyFloat(first.s) : std::optional<double>(toFloat(first));
                if (f) {
                    new_val = F(*f);
                    haveNewVal = true;
                    NLOG(log_, DEBUG, "setting %s to: %s", newKey.c_str(), pyStr(new_val).c_str());
                    dict.set(newKey, new_val);
                } else {
                    dict.set(newKey, Value::str(field()));
                    NLOG(log_, WARNING, "complex alt settings are not yet supported.");
                }
                if (!haveNewVal) throw PyError("UnboundLocalError", "new_val");
                if (new_val.isNone()) dict.set(newKey, Value::str(field()));
            }
        } else {
            dict.set(newKey, Value::str(field()));
        }
    }
}

}  // namespace neb
