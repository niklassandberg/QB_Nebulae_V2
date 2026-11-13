#include "controlhandler.h"

#include "configsettings.h"
#include "digitaldata.h"
#include "nebio.h"
#include "nebmixer.h"

namespace neb {

const std::vector<std::string> DIGITAL_CONTROLS = {
    "reset", "freeze", "source", "record", "file", "filestate", "sourcegate",
    "reset_alt", "freeze_alt", "source_alt", "record_alt", "file_alt"};

namespace {

long long nowMs() { return static_cast<long long>(pyRound0(clock().time() * 1000)); }

// A nebconfig value: the list of str after its key.
std::vector<std::string> strings(const Value &v) {
    if (v.type != Value::List) throw PyError("TypeError", "not a list");
    std::vector<std::string> out;
    for (auto &x : v.list) out.push_back(pyStr(x));
    return out;
}

ControlChannel &find(const std::map<std::string, ControlChannel *> &dict, const std::string &name) {
    auto it = dict.find(name);
    if (it == dict.end()) throw PyError("KeyError", name);
    return *it->second;
}

}  // namespace

ControlHandler::ControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                               std::string instr, std::string bank, HandlerEnv env)
    : currentInstr(std::move(instr)), currentBank(std::move(bank)), csound_(csound), numFiles_(numberFiles),
      configData_(configData), env_(std::move(env)), settings_(configData) {
    nebio::inputs();
    auto rates = nebio::set_input_rates(I(configSettings().nebioScanHz()), I(configSettings().nebioDigitalHz()),
                                        I(configSettings().nebioAdcHz()));
    NLOG(log_, INFO, "nebio input rates (scan, digital, adc): (%d, %d, %d)", std::get<0>(rates),
         std::get<1>(rates), std::get<2>(rates));
    if (configSettings().nebioFastGpio())
        NLOG(log_, INFO, "nebio fast GPIO requested: %s",
             nebio::set_fast_gpio(true) ? "on" : "refused, using libgpiod");
    else
        NLOG(log_, INFO, "nebio fast GPIO: off (libgpiod)");
    if (nebio::set_gate_interrupts(configSettings().gateInterrupts(), configSettings().gateHoldoffMs()))
        NLOG(log_, INFO, "nebio gates: interrupts");
    else
        NLOG(log_, INFO, "nebio gates: polled, hold-off %.1f ms", configSettings().gateHoldoffMs());

    settings_.filepath = env_.settingsDir;
    settings_.read();
    now = nowMs();
    updateAllLogTime = now;
    prep_mode_change_time = now;

    populateDefaultConfig();
    std::optional<double> output_period;
    if (configData_ && configData_->has("output_period"))
        output_period = toFloat(configData_->at("output_period").list.at(0));

    std::map<std::string, std::vector<std::string>> digitalConfig;
    for (auto &ctrl : DIGITAL_CONTROLS) {
        if (configData_ && configData_->has(ctrl))
            digitalConfig[ctrl] = strings(configData_->at(ctrl));
        else
            digitalConfig[ctrl] = defaultConfig.at(ctrl);
    }

    auto make = [&](const std::string &name, const Value &init, const std::string &source, ControlOptions opt) {
        return own(std::make_unique<ControlChannel>(csound_, name, init, source, std::move(opt)));
    };
    auto analog = [&](const std::string &name, const std::string &source, int data_channel, int cvchn = -2,
                      Value maximum = I(1)) {
        ControlOptions opt;
        opt.data_channel = data_channel;
        opt.cvchn = cvchn;
        opt.maximum = std::move(maximum);
        return make(name, settings_.load(name), source, std::move(opt));
    };
    auto digital = [&](const std::string &name, const Value &init, int data_channel, int gate_pin, int button_pin,
                       std::optional<std::vector<std::string>> config, Value maximum = I(1)) {
        ControlOptions opt;
        opt.data_channel = data_channel;
        opt.sr = &shiftReg_;
        opt.gate_pin = gate_pin;
        opt.button_pin = button_pin;
        opt.config = std::move(config);
        opt.maximum = std::move(maximum);
        return make(name, init, "digital", std::move(opt));
    };
    auto load = [&](const std::string &name) { return settings_.load(name); };

    channels = {
        analog("speed", "hybrid", 1),
        analog("pitch", "hybrid", 4),
        analog("start", "analog", 0),
        analog("size", "analog", 6),
        analog("blend", "analog", 1, 3),
        analog("density", "analog", 2),
        analog("overlap", "analog", 7),
        analog("window", "analog", 5),
        digital("reset", I(0), BUTTON_SR_GATE_GPIO, RESET_GATE_PIN, PIN_RESET, digitalConfig["reset"]),
        digital("freeze", load("freeze"), BUTTON_SR_GATE_GPIO, FREEZE_GATE_PIN, PIN_FREEZE, digitalConfig["freeze"]),
        digital("record", load("record"), BUTTON_SR_GATE_GPIO, RECORD_GATE_PIN, PIN_RECORD, digitalConfig["record"]),
        digital("file", load("file"), BUTTON_SR_GATE_GPIO, NEXT_GATE_PIN, PIN_NEXT, digitalConfig["file"], numFiles_),
        digital("source", load("source"), BUTTON_GATE_SR, PIN_SOURCE_GATE, PIN_SOURCE, digitalConfig["source"]),
        digital("filestate", I(0), BUTTON_SR_GATE_GPIO, NEXT_GATE_PIN, PIN_NEXT, digitalConfig["filestate"]),
        digital("sourcegate", I(0), BUTTON_GATE_SR, PIN_SOURCE_GATE, PIN_SOURCE, digitalConfig["sourcegate"]),
    };
    altchannels = {
        analog("speed_alt", "hybrid", -1, -2, I(32)),
        analog("pitch_alt", "hybrid", -1),
        analog("start_alt", "analog", 0, -1),
        analog("size_alt", "analog", 6, -1),
        analog("blend_alt", "analog", 1, -1),
        analog("density_alt", "analog", 2, -1),
        analog("overlap_alt", "analog", 7, -1),
        analog("window_alt", "analog", 5, -1),
        digital("reset_alt", load("reset_alt"), BUTTON_SR_GATE_GPIO, RESET_GATE_PIN, PIN_RESET, digitalConfig["reset_alt"]),
        digital("freeze_alt", load("freeze_alt"), BUTTON_SR_GATE_GPIO, FREEZE_GATE_PIN, PIN_FREEZE, digitalConfig["freeze_alt"]),
        digital("source_alt", load("source_alt"), BUTTON_GATE_SR, PIN_SOURCE_GATE, PIN_SOURCE, digitalConfig["source_alt"]),
        digital("record_alt", load("record_alt"), BUTTON_SR_GATE_GPIO, RECORD_GATE_PIN, PIN_RECORD, digitalConfig["record_alt"]),
        digital("file_alt", load("file_alt"), BUTTON_SR_GATE_GPIO, NEXT_GATE_PIN, PIN_NEXT, digitalConfig["file_alt"], I(3)),
    };
    std::vector<std::string> triggered = {"triggered", "falling"};
    instr_sel_controls = {
        digital("record_instr", I(0), BUTTON_SR_GATE_NONE, -1, PIN_RECORD, triggered),
        digital("file_instr", I(0), BUTTON_SR_GATE_NONE, -1, PIN_NEXT, triggered),
        digital("source_instr", I(0), BUTTON_SR_GATE_NONE, -1, PIN_SOURCE, triggered),
        digital("reset_instr", I(0), BUTTON_SR_GATE_NONE, -1, PIN_RESET, triggered),
        digital("freeze_instr", I(0), BUTTON_SR_GATE_NONE, -1, PIN_FREEZE, triggered),
    };
    if (output_period) {
        std::vector<ControlChannel *> all(channels);
        all.insert(all.end(), altchannels.begin(), altchannels.end());
        for (auto *chn : all) {
            auto it = digitalConfig.find(chn->name);
            if (it != digitalConfig.end() && it->second.at(0) == "triggered") chn->setOutputPeriod(F(*output_period));
        }
    }

    for (auto *chn : channels) channeldict[chn->name] = chn;
    for (auto *chn : altchannels) altchanneldict[chn->name] = chn;
    for (auto *chn : instr_sel_controls) instrchanneldict[chn->name] = chn;
    for (auto *chn : channels)
        if (chn->source == "digital" && chn->name != "file" && chn->name != "filestate")
            editFunctionFlag[chn->name] = false;

    ControlOptions sourceState;
    sourceState.data_channel = BUTTON_SR_GATE_NONE;
    sourceState.sr = &shiftReg_;
    sourceState.button_pin = PIN_SOURCE;
    sourceState.config = std::vector<std::string>{"momentary", "rising"};
    sourceStateCtrl_ = std::make_unique<ControlChannel>(csound_, "source_state", I(0), "digital", sourceState);
    eol_comm_ = std::make_unique<CommChannel>(csound_, "eol");
    size_status_comm_ = std::make_unique<CommChannel>(csound_, "sizestatus");
    record_status_comm_ = std::make_unique<CommChannel>(csound_, "recordstatus");
    buffer_size_comm_ = std::make_unique<CommChannel>(csound_, "bufferlength");
    channel("filestate").setIgnoreGate(true);
    channel("sourcegate").setIgnoreHID(true);
}

ControlHandler::~ControlHandler() {
    if (writeThread_.joinable()) writeThread_.join();
}

ControlChannel *ControlHandler::own(std::unique_ptr<ControlChannel> chn) {
    owned_.push_back(std::move(chn));
    return owned_.back().get();
}

ControlChannel &ControlHandler::channel(const std::string &name) { return find(channeldict, name); }
ControlChannel &ControlHandler::altChannel(const std::string &name) { return find(altchanneldict, name); }
ControlChannel &ControlHandler::instrChannel(const std::string &name) { return find(instrchanneldict, name); }

int ControlHandler::inputClipCount() { return nebio::card_clip_count(); }

void ControlHandler::enterNormalMode() {
    NLOG(log_, INFO, "entering normal");
    for (auto *chn : channels) chn->muteCSound(false);
    if (control_mode == "secondary controls") resistSecondarySettings();
    saveInstrument();
    altChannel("source_alt").setValue(I(0));
    prev_control_mode = control_mode;
    control_mode = "normal";
}

void ControlHandler::saveInstrument() {
    settings_.update(I(now));
    settings_.write();
}

void ControlHandler::enterSecondaryMode() {
    if (control_mode == "normal" || control_mode == "puredata" || control_mode == "supercollider" ||
        control_mode == "programs") {
        NLOG(log_, INFO, "entering secondary");
        resistNormalSettings();
        prev_control_mode = control_mode;
        control_mode = "secondary controls";
    }
    for (auto *chn : channels) chn->setIgnoreHID(true);
    saveInstrument();
}

void ControlHandler::enterInstrSelMode() {
    if (control_mode == "normal" || control_mode == "puredata" || control_mode == "supercollider" ||
        control_mode == "programs") {
        NLOG(log_, INFO, "entering instr selector");
        control_mode = "instr selector";
    }
    saveInstrument();
    for (auto *chn : channels) chn->muteCSound(true);
}

void ControlHandler::resistNormalSettings() {
    for (size_t i = 0; i < 8; ++i) altchannels.at(i)->setModeChangeValue(channels.at(i)->getPotValue());
}

void ControlHandler::resistSecondarySettings() {
    for (size_t i = 0; i < 8; ++i) channels.at(i)->setModeChangeValue(channels.at(i)->getPotValue());
}

void ControlHandler::populateDefaultConfig() {
    bool normal = control_mode == "normal" || control_mode == "secondary controls";
    bool engine = control_mode == "puredata" || control_mode == "supercollider" || control_mode == "programs";
    if (!normal && !engine) return;
    defaultConfig["reset"] = {"triggered", "rising"};
    defaultConfig["freeze"] = {"latching", "rising"};
    defaultConfig["source"] = {"latching", "falling"};
    defaultConfig["file"] = {normal ? "incremental" : "latching", "falling"};
    defaultConfig["record"] = {"latching", "rising"};
    defaultConfig["filestate"] = {"momentary", "rising"};
    defaultConfig["reset_alt"] = {"triggered", "rising"};
    defaultConfig["freeze_alt"] = {"latching", "rising"};
    defaultConfig["source_alt"] = {"latching", "falling"};
    defaultConfig["file_alt"] = {"incremental", "falling"};
    defaultConfig["record_alt"] = {"latching", "falling"};
    defaultConfig["sourcegate"] = {"triggered", "rising"};
    defaultConfig["ksmps"] = {"128"};
    defaultConfig["sr"] = {"44100"};
}

void ControlHandler::restoreAltToDefault() {
    for (auto *chn : altchannels) {
        Value defaultVal = settings_.getDefault(chn->name);
        Value nowval = chn->getPotValue();
        chn->setValue(defaultVal);
        chn->setModeChangeValue(nowval);
    }
}

void ControlHandler::setInputLevel(const Value &scalar) {
    if (scalar != in_ticks) {
        in_ticks = scalar;
        nebmixer::inputLevel(scalar);
    }
}

void ControlHandler::handleEndOfLoop() {
    eol_comm_->update();
    size_status_comm_->update();
    if (size_status_comm_->getState() == I(0))
        nebio::set_eol(!(eol_comm_->getState().number() > 0));
    else
        nebio::set_eol(true);
}

void ControlHandler::handleRecordStatus() {
    record_status_comm_->update();
    if (record_status_comm_->fallingEdge()) {
        NLOG(log_, INFO, "Ending recording.");
        if (getAltValue("record_alt") == I(0)) {
            setValue("record", I(0));
            if (getValue("source") == I(1)) {
                setValue("pitch", F(0.6));
                setValue("speed", F(0.625));
            }
        }
    }
}

bool ControlHandler::getEditFunctionFlag(const std::string &name) const {
    auto it = editFunctionFlag.find(name);
    return it != editFunctionFlag.end() && it->second;
}

void ControlHandler::clearEditFunctionFlag(const std::string &name) {
    auto it = editFunctionFlag.find(name);
    if (it != editFunctionFlag.end()) it->second = false;
}

void ControlHandler::setEditFunctionFlag(const std::string &name) {
    auto it = editFunctionFlag.find(name);
    if (it != editFunctionFlag.end()) it->second = true;
}

void ControlHandler::countUpdateAll() {
    now = nowMs();
    ++updateAllCount;
    if (now - updateAllLogTime >= 10000) {
        if (Logger::rootLevel() <= STATS) {
            NLOG(log_, STATS, "updateAll: %.1f calls/s (total %lld)",
                 (updateAllCount - updateAllLogCount) * 1000.0 / static_cast<double>(now - updateAllLogTime),
                 updateAllCount);
            NLOG(log_, STATS, "nebio: %s", nebio::stats().c_str());
        }
        updateAllLogCount = updateAllCount;
        updateAllLogTime = now;
    }
}

void ControlHandler::handleSourceHold() {
    sourceStateCtrl_->update();
    Value value = sourceStateCtrl_->getValue(), prev = sourceStateCtrl_->getPrevValue();
    if (value == I(1) && prev == I(0)) {
        prep_mode_change = true;
        prep_mode_change_time = now;
    } else if (value == I(0)) {
        if (prev == I(1)) {
            prep_mode_change = false;
            if (control_mode == "secondary controls") enterNormalMode();
        }
    }
    if (prep_mode_change && now - prep_mode_change_time > 175) {
        enterSecondaryMode();
        prep_mode_change = false;
        channel("source").setIgnoreNextButton();
    }
}

void ControlHandler::updateInstrSelector() {
    for (size_t idx = 0; idx < instr_sel_controls.size(); ++idx) {
        ControlChannel *chn = instr_sel_controls[idx];
        chn->update();
        if (chn->getValue() == I(1)) {
            long long sel_idx = static_cast<long long>(idx) + instr_sel_offset;
            if (sel_idx < instr_sel_numfiles) instr_sel_idx = sel_idx;
        }
    }
}

void ControlHandler::updateAll() {
    countUpdateAll();
    shiftReg_.update();
    handleSourceHold();
    handleEndOfLoop();
    handleRecordStatus();

    if (control_mode == "secondary controls") {
        for (auto *chn : channels) chn->update();
        for (auto *chn : altchannels) {
            chn->update();
            settings_.save(chn->name, chn->getValue());
        }
        if (currentInstr == "a_granularlooper")
            channel("file").digital()->setIncOrder(static_cast<int>(toInt(getAltValue("file_alt"))));
        setInputLevel(getAltValue("speed_alt"));
    } else if (control_mode == "instr selector") {
        updateInstrSelector();
    } else {
        Value filestate = channel("filestate").getValue();
        bool file_edit = filestate == I(1) || filestate == Value::boolean(true);
        Value source_state = getValue("source");
        bool granular = currentInstr == "a_granularlooper";
        channel("source").setIgnoreGate(getAltValue("freeze_alt") == I(1) && granular);

        for (auto *chn : channels) {
            const std::string &name = chn->name;
            if (name != "sourcegate") chn->setIgnoreHID(false);
            chn->update();
            if (granular && name == "file") {
                if (source_state == I(1))
                    chn->setValue(static_file_idx);
                else
                    static_file_idx = chn->getValue();
            }
            if (name == "filestate") continue;
            settings_.save(name, chn->source == "hybrid" ? chn->getStaticVal() : chn->getValue());
            if (file_edit && chn->source == "digital" && name != "file") {
                if (chn->hasChanged() && chn->getTrigSource() == "button") {
                    if (name == "reset") {
                        setEditFunctionFlag(name);
                    } else if (name == "source") {
                        setEditFunctionFlag(name);
                        channel(name).setIgnoreNextButton();
                    } else if (name == "freeze") {
                        setEditFunctionFlag(name);
                        channel(name).setIgnoreNextButton();
                        channel(name).setValue(sub(I(1), channel(name).getValue()));
                        startWriteThread();
                    }
                    NLOG(log_, INFO, "channel: %s has changed.", name.c_str());
                    channel("file").setIgnoreNextButton();
                }
            }
        }
    }
}

void ControlHandler::startWriteThread() {
    if (writeRunning_) {
        NLOG(log_, INFO, "Write thread still running.");
        return;
    }
    NLOG(log_, INFO, "Write Thread Starting!");
    if (writeThread_.joinable()) writeThread_.join();
    writeRunning_ = true;
    if (env_.runWorker) {
        env_.runWorker([this] { writeBufferToAudioFile(); });
        writeRunning_ = false;
        return;
    }
    writeThread_ = std::thread([this] {
        try {
            writeBufferToAudioFile();
        } catch (const std::exception &e) {
            NLOG(log_, ERROR, "Writing the buffer failed: %s", e.what());
        }
        writeRunning_ = false;
    });
}

void ControlHandler::printAllControls() {
    std::string line = "############################\nPrimary Channels:";
    for (size_t i = 0; i < channels.size(); ++i) {
        if (i % 4 == 0) line += "\n";
        line += channels[i]->name + ": " + pyStr(channels[i]->getValue()) + "\t";
    }
    line += "\nSecondary Channels:";
    for (size_t i = 0; i < altchannels.size(); ++i) {
        if (i % 4 == 0) line += "\n";
        line += altchannels[i]->name + ": " + pyStr(altchannels[i]->getValue()) + "\t";
    }
    line += "\n############################\n\nComm Channels:krecordstatus: " +
            pyStr(record_status_comm_->getState()) + "\n\n############################\n";
    NLOG(log_, INFO, "%s", line.c_str());
}

void ControlHandler::printAllControlsVerbose() {
    std::string line = "############################\nPrimary Channel Pots:";
    for (size_t i = 0; i < channels.size(); ++i) {
        if (i % 4 == 0) line += "\n";
        line += channels[i]->name + ": " + pyStr(channels[i]->getPotValue()) + "\t";
    }
    line += "\nPrimary Channel CVs:";
    for (size_t i = 0; i < channels.size(); ++i) {
        if (i % 4 == 0) line += "\n";
        line += channels[i]->name + ": " + pyStr(channels[i]->getCVValue()) + "\t";
    }
    line += "\nSecondary Channels:";
    for (size_t i = 0; i < altchannels.size(); ++i) {
        if (i % 4 == 0) line += "\n";
        line += altchannels[i]->name + ": " + pyStr(altchannels[i]->getValue()) + "\t";
    }
    line += "\n############################\n";
    NLOG(log_, INFO, "%s", line.c_str());
}

void ControlHandler::writeBufferToAudioFile() {
    bool success = false;
    if (csound_) {
        NLOG(log_, INFO, "Started Writing Buffer");
        writing_buffer = true;
        buffer_size_comm_->update();
        Value length = buffer_size_comm_->getState();
        if (length.number() > 0) {
            NLOG(log_, INFO, "%s", pyStr(length).c_str());
            NLOG(log_, INFO, "Getting tables from Csound");
            std::vector<double> left = csound_->table(200), right = csound_->table(201);
            NLOG(log_, INFO, "Jumping to WaveWriter");
            if (!env_.writer) throw PyError("AttributeError", "no WaveWriter");
            success = env_.writer->WriteStereoWaveFile(left, right, length);
            NLOG(log_, INFO, "Finished Writing Buffer");
        } else {
            NLOG(log_, INFO, "Buffer is currently empty");
        }
        writing_buffer = false;
    }
    if (!success) buffer_failure = true;
}

}  // namespace neb
