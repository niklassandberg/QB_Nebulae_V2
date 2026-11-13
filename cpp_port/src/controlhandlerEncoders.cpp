#include "controlhandlerEncoders.h"

#include <algorithm>

#include "digitaldata.h"

namespace neb {

const std::vector<std::string> ENCODERS = {"speed", "pitch"};
const std::vector<std::string> CV_ASSIGN_BUTTONS = {"file", "reset"};
const std::vector<std::string> HOLD_EDGE_MODES = {"latching", "triggered", "incremental"};

namespace {

// HOLD_PINS, in this order: Python iterates a set here, an order that
// changes with the hash seed (only matters when two buttons go down in one pass).
const std::vector<std::pair<std::string, int>> HOLD_PINS = {
    {"record", PIN_RECORD}, {"file", PIN_NEXT}, {"reset", PIN_RESET}, {"freeze", PIN_FREEZE}, {"source", PIN_SOURCE}};

bool contains(const std::vector<std::string> &list, const std::string &x) {
    return std::find(list.begin(), list.end(), x) != list.end();
}

std::string firstButton(const std::string &layer) { return layer.substr(0, layer.find('+')); }

EncoderPages *lookup(const EncoderMap &map, const std::string &key) {
    for (auto &kv : map)
        if (kv.first == key) return kv.second;
    return nullptr;
}

}  // namespace

int holdPin(const std::string &button) {
    for (auto &kv : HOLD_PINS)
        if (kv.first == button) return kv.second;
    throw PyError("KeyError", button);
}

EncoderControlHandler::EncoderControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                                             std::string instr, std::string bank, HandlerEnv env)
    : ControlHandler(csound, numberFiles, configData, std::move(instr), std::move(bank), std::move(env)) {
    for (auto &name : ENCODERS) encoders[name]["hybrid"] = &channel(name);
}

void EncoderControlHandler::setConfig(const NebConfig &config, const std::string &pages_path) {
    for (auto &name : ENCODERS) {
        std::string source = config.encoderType(name);
        if (!encoders[name].count(source) && source != "pages") {
            NLOG(log_, ERROR, "%s,%s: not in this bank, hybrid", name.c_str(), source.c_str());
            source = "hybrid";
        }
        ControlChannel *now_ = encoders[name].at(source == "pages" ? "hybrid" : source);
        ControlChannel *old = &channel(name);
        if (now_ != old) {
            // Same index: resistNormalSettings() pairs channels[i] with altchannels[i].
            *std::find(channels.begin(), channels.end(), old) = now_;
            channeldict[name] = now_;
        }
        NLOG(log_, INFO, "%s: %s", name.c_str(), source.c_str());
    }
    setPages(config, pages_path);
    setButtonConfig(config);
}

void EncoderControlHandler::setButtonConfig(const NebConfig &nebConfig) {
    double output_period = nebConfig.outputPeriod();
    std::set<std::string> first = holdFirstButtons();
    for (auto &ctrl : DIGITAL_CONTROLS) {
        ControlChannel *chn = nullptr;
        if (channeldict.count(ctrl))
            chn = channeldict.at(ctrl);
        else if (altchanneldict.count(ctrl))
            chn = altchanneldict.at(ctrl);
        const std::vector<std::string> *config = nebConfig.entry(ctrl);
        if ((!config || config->empty()) && defaultConfig.count(ctrl)) config = &defaultConfig.at(ctrl);
        if (!chn || !config || config->size() < 2) continue;
        const std::string &mode = (*config)[0];
        std::string edge = (*config)[1];
        if (first.count(ctrl)) {
            if (contains(HOLD_EDGE_MODES, mode))
                edge = "falling";
            else
                NLOG(log_, WARNING, "%s,%s: also on while held for its hold: layer", ctrl.c_str(), mode.c_str());
        }
        chn->setMode(mode, edge);
        chn->setOutputPeriod(mode == "triggered" ? F(output_period) : I(DEFAULT_OUTPUT_PERIOD));
    }
}

EncoderPages *EncoderControlHandler::makePages(const std::string &encoder, const PageList &specs,
                                               std::optional<std::string> cv_target, std::optional<Colour> hold) {
    std::vector<Page *> list;
    for (auto &p : specs) {
        ownedPages_.push_back(std::make_unique<Page>(p.name, p.path, F(p.lo), F(p.hi), p.curve, F(p.value), F(p.step)));
        list.push_back(ownedPages_.back().get());
    }
    ownedEncoderPages_.push_back(std::make_unique<EncoderPages>(encoder, list, std::move(cv_target), hold));
    return ownedEncoderPages_.back().get();
}

void EncoderControlHandler::setPages(const NebConfig &config, const std::string &pages_path) {
    savePages();  // the previous instrument's
    auto [entries, errors] = config.encoderPages();
    for (auto &error : errors) NLOG(log_, ERROR, "nebconfig: %s", error.c_str());
    auto targets = config.cvTargets();
    std::vector<std::unique_ptr<Page>> oldPages;
    std::vector<std::unique_ptr<EncoderPages>> oldEncoderPages;
    oldPages.swap(ownedPages_);
    oldEncoderPages.swap(ownedEncoderPages_);
    pages.clear();
    for (auto &[name, specs] : entries) {
        if (config.encoderType(name) != "pages") continue;
        std::optional<std::string> target;
        for (auto &t : targets)
            if (t.first == name) target = t.second;
        pages.emplace_back(name, makePages(name, specs, target, std::nullopt));
    }
    auto [layers, holdErrors] = config.holdPages();
    for (auto &error : holdErrors) NLOG(log_, ERROR, "nebconfig: %s", error.c_str());
    holds.clear();
    for (auto &[layer, encoderSpecs] : layers) {
        Colour colour = layer.find('+') != std::string::npos ? HOLD2_COLOUR : HOLD_COLOUR;
        EncoderMap map;
        for (auto &[name, specs] : encoderSpecs) map.emplace_back(name, makePages(name, specs, std::nullopt, colour));
        holds.emplace_back(layer, map);
    }
    hold_since.clear();
    hold_active.reset();
    hold_used = false;
    hold_blocked.clear();
    pageState = std::make_unique<PageState>(pages_path);
    pageState->load(allPages());
    page_sent.clear();
    cv_assign = false;
}

EncoderMap EncoderControlHandler::allPages() const {
    EncoderMap out = pages;
    for (auto &[layer, map] : holds)
        for (auto &[name, p] : map) out.emplace_back(layer + ":" + name, p);
    return out;
}

std::set<std::string> EncoderControlHandler::holdFirstButtons() const {
    std::set<std::string> out;
    for (auto &kv : holds) out.insert(firstButton(kv.first));
    return out;
}

std::set<std::string> EncoderControlHandler::holdButtons() const {
    std::set<std::string> out;
    for (auto &kv : holds) {
        const std::string &layer = kv.first;
        size_t plus = layer.find('+');
        out.insert(layer.substr(0, plus));
        if (plus != std::string::npos) out.insert(layer.substr(plus + 1));
    }
    return out;
}

void EncoderControlHandler::saveInstrument() {
    ControlHandler::saveInstrument();
    savePages();
}

void EncoderControlHandler::savePages() {
    if (pageState && !pageState->dirty_time.isNone()) pageState->save(allPages());
}

const EncoderMap *EncoderControlHandler::holdLayer(const std::string &layer) const {
    for (auto &kv : holds)
        if (kv.first == layer) return &kv.second;
    return nullptr;
}

EncoderPages *EncoderControlHandler::encoderPages(const std::string &encoder) const {
    if (hold_active) {
        if (const EncoderMap *layer = holdLayer(*hold_active))
            if (EncoderPages *p = lookup(*layer, encoder)) return p;
    }
    return lookup(pages, encoder);
}

void EncoderControlHandler::pageStep(const std::string &encoder, const Value &steps) {
    touchedPages(encoder).step(steps);
    pageState->changed(I(now));
}

void EncoderControlHandler::pageJump(const std::string &encoder, const Value &steps) {
    touchedPages(encoder).move(mul(F(PAGE_JUMP), steps));
    pageState->changed(I(now));
}

void EncoderControlHandler::nextPage(const std::string &encoder) { touchedPages(encoder).nextPage(); }

EncoderPages &EncoderControlHandler::touchedPages(const std::string &encoder) {
    EncoderPages *p = encoderPages(encoder);
    if (!p) throw PyError("AttributeError", "'NoneType' object has no attribute 'hold'");
    if (p->hold) hold_used = true;
    return *p;
}

void EncoderControlHandler::setCvOn(const std::string &encoder, bool on) {
    EncoderPages *p = lookup(pages, encoder);
    if (!p) throw PyError("KeyError", encoder);
    p->setCandidate(on);
}

void EncoderControlHandler::updateCvAssign() {
    bool held_next = shiftReg_.state(PIN_NEXT);
    bool held_reset = shiftReg_.state(PIN_RESET);
    if (held_next && held_reset && !cv_assign && !pages.empty()) {
        cv_assign = true;
        hold_active.reset();
        for (auto &kv : pages) kv.second->startChoosing();
        for (auto &name : CV_ASSIGN_BUTTONS) {
            channel(name).setIgnoreNextButton();
            sendControl(name, I(0));
        }
    } else if (cv_assign && !held_next && !held_reset) {
        cv_assign = false;
        bool changed = false;
        for (auto &kv : pages) changed = kv.second->commitCandidate() || changed;
        if (changed) {
            pageState->changed(I(now));
            std::string targets;
            for (auto &[e, p] : pages)
                targets += (targets.empty() ? "" : ", ") + e + " -> " + p->cv_target.value_or("none");
            NLOG(log_, INFO, "CV targets: %s", targets.c_str());
        }
    }
}

// While the button is down the encoders show and change its layer. Its
// release is a press only when short (HOLD_MS) and no encoder was used.
// A second button pressed during the hold (a "record+file" layer) switches
// to that layer until it is released; its own press is dropped, its gate
// still works. Releasing the first button ends both.
// Runs before the channels read the buttons, so those presses are dropped.
// Not while choosing CV targets (file + reset).
void EncoderControlHandler::updateHolds() {
    std::set<std::string> first = holdFirstButtons(), buttons = holdButtons();
    for (auto &[button, pin] : HOLD_PINS) {
        if (!buttons.count(button)) continue;
        if (shiftReg_.state(pin)) {
            if (hold_since.count(button)) continue;
            hold_since[button] = now;
            if (cv_assign) continue;
            if (!hold_active) {
                if (first.count(button)) {
                    hold_active = button;
                    hold_used = false;
                }
            } else if (hold_active->find('+') == std::string::npos) {
                std::string layer = *hold_active + "+" + button;
                if (holdLayer(layer)) {
                    hold_active = layer;
                    hold_used = true;
                    hold_blocked.insert(button);
                }
            }
            continue;
        }
        std::optional<long long> since;
        auto it = hold_since.find(button);
        if (it != hold_since.end()) {
            since = it->second;
            hold_since.erase(it);
        }
        std::string suffix = "+" + button;
        if (hold_blocked.count(button)) {
            hold_blocked.erase(button);
            channel(button).setIgnoreNextButton();
            if (hold_active && hold_active->size() >= suffix.size() &&
                hold_active->compare(hold_active->size() - suffix.size(), suffix.size(), suffix) == 0) {
                logHold(*hold_active);
                hold_active = firstButton(*hold_active);
            }
        } else if (hold_active && firstButton(*hold_active) == button) {
            logHold(*hold_active);
            hold_active.reset();
            bool held = !since || now - *since >= HOLD_MS;
            if (hold_used || held) channel(button).setIgnoreNextButton();
        }
    }
}

void EncoderControlHandler::logHold(const std::string &layer) {
    // Built even when not logged: page() of a layer without pages raises, as in Python.
    std::string shown;
    if (const EncoderMap *map = holdLayer(layer))
        for (auto &[e, p] : *map) shown += (shown.empty() ? "" : ", ") + e + " " + p->page().name;
    NLOG(log_, INFO, "hold %s: %s", layer.c_str(), shown.c_str());
}

bool EncoderControlHandler::sendsControl(const std::string &name) const {
    if (lookup(pages, name)) return false;
    return !(cv_assign && contains(CV_ASSIGN_BUTTONS, name));
}

Value EncoderControlHandler::encoderCV(const std::string &encoder) {
    ControlChannel &chn = channel(encoder);
    return sub(chn.getValue(), chn.getStaticVal());
}

void EncoderControlHandler::sendPages(bool full) {
    for (auto &[key, p] : allPages()) {
        Value cv = p->hold ? F(0.0) : encoderCV(key);
        for (auto &[path, out] : p->outputs(cv)) {
            auto it = page_sent.find(path);
            if (full || it == page_sent.end() || it->second != out) {
                sendPath(path, out);
                page_sent[path] = out;
            }
        }
    }
    if (pageState) pageState->saveIfDue(I(now), allPages());
}

}  // namespace neb
