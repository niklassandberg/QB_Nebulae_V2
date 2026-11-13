// controlhandlerEncoders.py: base for the SuperCollider and programs banks:
// encoder sources, button modes, encoder pages and hold layers per instrument.
#pragma once

#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "controlhandler.h"
#include "encoderpages.h"
#include "nebconfig.h"

namespace neb {

extern const std::vector<std::string> ENCODERS;            // speed, pitch
extern const std::vector<std::string> CV_ASSIGN_BUTTONS;   // file, reset
extern const std::vector<std::string> HOLD_EDGE_MODES;     // a hold: the button reacts on release
int holdPin(const std::string &button);                    // HOLD_PINS; PyError KeyError

class EncoderControlHandler : public ControlHandler {
public:
    EncoderControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                          std::string instr = "a_granularlooper", std::string bank = "instr",
                          HandlerEnv env = HandlerEnv());

    virtual void setConfig(const NebConfig &config, const std::string &pages_path);
    void setButtonConfig(const NebConfig &config);
    void setPages(const NebConfig &config, const std::string &pages_path);
    // Saved and sent: the encoder pages, and the hold layers as "<layer>:<encoder>".
    EncoderMap allPages() const;
    std::set<std::string> holdFirstButtons() const;  // the buttons that start a layer
    std::set<std::string> holdButtons() const;
    // A second button's own press is held back; its gate still works.
    bool buttonBlocked(const std::string &name) const { return hold_blocked.count(name) > 0; }
    void saveInstrument() override;
    void savePages();
    // What the encoder turns now: the held button's layer, else its pages (nullptr: none).
    EncoderPages *encoderPages(const std::string &encoder) const;
    void pageStep(const std::string &encoder, const Value &steps);
    void pageJump(const std::string &encoder, const Value &steps);
    void nextPage(const std::string &encoder);
    EncoderPages &touchedPages(const std::string &encoder);
    void setCvOn(const std::string &encoder, bool on);
    bool cvAssignActive() const { return cv_assign; }
    void updateCvAssign();
    void updateHolds();
    void logHold(const std::string &layer);
    bool sendsControl(const std::string &name) const;
    Value encoderCV(const std::string &encoder);  // hybrid = encoder + CV
    void sendPages(bool full = false);
    virtual void sendControl(const std::string &name, const Value &value) = 0;
    virtual void sendPath(const std::string &path, double value) = 0;

    // encoders[name][source]: a paged encoder keeps its hybrid channel for the CV.
    std::map<std::string, std::map<std::string, ControlChannel *>> encoders;
    EncoderMap pages;                                    // encoder -> its pages, in block order
    std::vector<std::pair<std::string, EncoderMap>> holds;  // layer -> {encoder: pages}
    std::map<std::string, long long> hold_since;         // button -> ms it went down, while down
    std::optional<std::string> hold_active;              // the layer the encoders show
    bool hold_used = false;                              // an encoder changed the layer: no press
    std::set<std::string> hold_blocked;                  // second buttons of a layer: no press until released
    std::unique_ptr<PageState> pageState;
    std::map<std::string, double> page_sent;
    bool cv_assign = false;

protected:
    EncoderPages *makePages(const std::string &encoder, const PageList &specs, std::optional<std::string> cv_target,
                            std::optional<Colour> hold);
    const EncoderMap *holdLayer(const std::string &layer) const;

private:
    std::vector<std::unique_ptr<Page>> ownedPages_;
    std::vector<std::unique_ptr<EncoderPages>> ownedEncoderPages_;
};

}  // namespace neb
