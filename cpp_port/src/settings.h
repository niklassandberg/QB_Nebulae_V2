// settings.py: the instrument's saved control values (nebsettings.txt, one
// "key,value" per line) over its defaults (defaultnebsettings.txt).
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "classlogger.h"
#include "pyvalue.h"

namespace neb {

// A dict: insertion order, an update keeps the key's place.
class OrderedDict {
public:
    bool has(const std::string &k) const;
    const Value &at(const std::string &k) const;  // PyError KeyError
    void set(const std::string &k, const Value &v);
    const std::vector<std::pair<std::string, Value>> &items() const { return items_; }

private:
    std::vector<std::pair<std::string, Value>> items_;
};

extern bool remountFs;  // neb_globals.remount_fs

class SettingManager {
public:
    explicit SettingManager(const OrderedDict *config);  // nullptr: None
    void read();
    void write();
    void update(const Value &now);
    Value getDefault(const std::string &key) const;  // None when not a default
    Value load(const std::string &key) const;        // None when not a setting
    Value getLastUpdate() const { return lastUpdate; }
    bool hasSetting(const std::string &key) const { return settingDict.has(key); }
    void save(const std::string &key, const Value &value) { mutable_().set(key, value); }
    void populateDict(const std::vector<std::string> &lines, OrderedDict &dict);
    void populateDefaultDict(const std::vector<std::string> &lines, OrderedDict &dict);

    OrderedDict settingDict, defaultDict, mutableSettings;
    bool haveMutable = false;  // mutableSettings exists once read() got that far
    OrderedDict &mutable_() {
        if (!haveMutable) throw PyError("AttributeError", "'SettingManager' object has no attribute 'mutableSettings'");
        return mutableSettings;
    }
    const OrderedDict *configData;
    std::string filename = "nebsettings.txt";
    std::string defaultsfilename = "defaultnebsettings.txt";
    std::string filepath = "/home/alarm/QB_Nebulae_V2/Code/config/";
    Value lastUpdate = I(0);
    std::vector<std::string> lines;

private:
    Logger log_{"SettingManager"};
};

}  // namespace neb
