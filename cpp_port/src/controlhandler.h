// controlhandler.py: all ControlChannels of an instrument, the modes (normal,
// secondary controls, instr selector) and the Csound bank's main-loop pass.
#pragma once

#include <atomic>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "classlogger.h"
#include "control.h"
#include "inputs.h"
#include "nebio_api.h"
#include "settings.h"
#include "wavewriter.h"

namespace neb {

extern const std::vector<std::string> DIGITAL_CONTROLS;

constexpr int FREEZE_GATE_PIN = 4;
constexpr int RESET_GATE_PIN = 25;
constexpr int NEXT_GATE_PIN = 23;
constexpr int RECORD_GATE_PIN = 24;

// What production takes as it is and the tests replace.
struct HandlerEnv {
    std::string settingsDir = "/home/alarm/QB_Nebulae_V2/Code/config/";
    WaveWriter *writer = nullptr;  // the record buffer's WAV writer
    // Runs the WAV writing; empty: a thread of its own.
    std::function<void(const std::function<void()> &)> runWorker;
};

class ControlHandler {
public:
    // configData: the nebconfig block (key -> list of str), nullptr: none.
    ControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                   std::string instr = "a_granularlooper", std::string bank = "instr", HandlerEnv env = HandlerEnv());
    virtual ~ControlHandler();
    ControlHandler(const ControlHandler &) = delete;
    ControlHandler &operator=(const ControlHandler &) = delete;

    virtual bool isRaw(const std::string &) { return false; }
    int inputClipCount();

    void setValue(const std::string &name, const Value &value) { channel(name).setValue(value); }
    void setAltValue(const std::string &name, const Value &value) { altChannel(name).setValue(value); }
    Value getValue(const std::string &name) { return channel(name).getValue(); }
    Value getAltValue(const std::string &name) { return altChannel(name).getValue(); }
    Value getLEDValue(const std::string &name) { return channel(name).getLEDValue(); }
    Value getAltLEDValue(const std::string &name) { return altChannel(name).getLEDValue(); }
    Value getStaticVal(const std::string &name) { return channel(name).getStaticVal(); }
    Value getAltStaticVal(const std::string &name) { return altChannel(name).getStaticVal(); }
    Value getInstrValue(const std::string &name) { return instrChannel(name).getValue(); }
    void updateChannel(const std::string &name) { channel(name).update(); }
    void updateAltChannel(const std::string &name) { altChannel(name).update(); }

    long long getInstrSelIdx() const { return instr_sel_idx; }
    std::string getInstrSelBank() const { return instr_sel_bank; }
    long long getInstrSelOffset() const { return instr_sel_offset; }
    void setInstrSelIdx(long long idx) { instr_sel_idx = idx; }
    void setInstrSelBank(const std::string &bank) { instr_sel_bank = bank; }
    void setInstrSelOffset(long long offset) { instr_sel_offset = offset; }
    void setInstrSelNumFiles(long long numfiles) { instr_sel_numfiles = numfiles; }
    void setCurrentInstr(const std::string &name) { currentInstr = name; }
    const std::string &mode() const { return control_mode; }

    virtual void closeSockets() {}
    virtual void enterNormalMode();
    // Everything of the instrument, at every mode change and before a
    // restart: subclasses add theirs (pages, the engine's own values).
    virtual void saveInstrument();
    virtual void enterSecondaryMode();
    virtual void enterInstrSelMode();
    void resistNormalSettings();
    void resistSecondarySettings();
    void restoreAltToDefault();
    void setInputLevel(const Value &scalar);
    bool getEndOfLoopState() const { return eol_state; }
    void handleEndOfLoop();
    void handleRecordStatus();
    bool getEditFunctionFlag(const std::string &name) const;
    void clearEditFunctionFlag(const std::string &name);
    void setEditFunctionFlag(const std::string &name);
    void countUpdateAll();  // logged every 10 s at log level STATS
    void handleSourceHold();
    void updateInstrSelector();
    virtual void updateAll();
    void printAllControls();
    void printAllControlsVerbose();
    void writeBufferToAudioFile();

    ControlChannel &channel(const std::string &name);       // PyError KeyError
    ControlChannel &altChannel(const std::string &name);    // PyError KeyError
    ControlChannel &instrChannel(const std::string &name);  // PyError KeyError

    std::vector<ControlChannel *> channels, altchannels, instr_sel_controls;
    std::map<std::string, ControlChannel *> channeldict, altchanneldict, instrchanneldict;
    std::map<std::string, std::vector<std::string>> defaultConfig;
    std::map<std::string, bool> editFunctionFlag;

    std::string control_mode = "normal", prev_control_mode = "normal";
    std::string currentInstr, currentBank;
    long long now;  // ms, set by countUpdateAll()
    long long updateAllCount = 0, updateAllLogCount = 0, updateAllLogTime;
    Value in_ticks = I(23);
    Value static_file_idx = I(0);
    bool prep_mode_change = false;
    long long prep_mode_change_time;
    long long instr_sel_idx = 0, instr_sel_offset = 0, instr_sel_numfiles = 5;
    std::string instr_sel_bank = "instr";
    bool eol_state = false;
    std::atomic<bool> writing_buffer{false}, buffer_failure{false};

protected:
    void populateDefaultConfig();
    ControlChannel *own(std::unique_ptr<ControlChannel> chn);
    void startWriteThread();

    Logger log_{"ControlHandler"};
    Csound *csound_;
    Value numFiles_;
    const OrderedDict *configData_;
    HandlerEnv env_;
    ShiftRegister shiftReg_;
    SettingManager settings_;
    std::vector<std::unique_ptr<ControlChannel>> owned_;
    std::unique_ptr<ControlChannel> sourceStateCtrl_;
    std::unique_ptr<CommChannel> eol_comm_, size_status_comm_, record_status_comm_, buffer_size_comm_;
    std::thread writeThread_;
    std::atomic<bool> writeRunning_{false};
};

}  // namespace neb
