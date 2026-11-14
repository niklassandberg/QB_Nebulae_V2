# Nebulae sends to Pd as OSC on UDP port 3000. A patch written for the old TCP
# link ([netreceive 3000]) gets a converted copy next to it:
#   [netreceive -u -b 3000] -> [oscparse] -> [list trim] -> what it fed before
# ("/start 0.5" arrives as "start 0.5", as before). The original is never
# changed, and no other network object is touched.
import os
import re

import neb_globals
import textfile
from classlogger import ClassLogger

class PdConvert(object):
    pass


_log = ClassLogger.loggerSetup(PdConvert())

PORT = 3000
OBJECTS = ("#X obj", "#X msg", "#X text", "#X floatatom", "#X symbolatom", "#X listbox", "#X restore")
_END = re.compile(r"(?<!\\);[ \t]*\r?\n")
_NETRECEIVE = re.compile(r"#X obj (-?\d+) (-?\d+) netreceive( .*)?$")


def _norm(s):
    return " ".join(s.split())


# The TCP link: [netreceive 3000] or [netreceive 3000 0]; "-u" or a
# protocol 1 is UDP, "-b" binary.
def _isTcp(args):
    return args in (["3000"], ["3000", "0"])


def _isOsc(args):
    flags = [a for a in args if a.startswith("-")]
    rest = [a for a in args if not a.startswith("-")]
    return "-u" in flags and "-b" in flags and rest[:1] == ["3000"]


def _statements(text):
    parts, pos = [], 0  # [statement, its terminator]
    for m in _END.finditer(text):
        parts.append([text[pos:m.start()], m.group(0)])
        pos = m.end()
    if text[pos:].strip():
        parts.append([text[pos:], ""])
    return parts


# The patch text for OSC, None when it needs nothing, or a ValueError saying
# why it cannot be converted.
def convert(text):
    nl = "\r\n" if "\r\n" in text else "\n"
    parts = _statements(text)
    canvas_of, canvases, stack = [], [], []
    tcp, osc = [], 0
    for stmt, _ in parts:
        t = _norm(stmt)
        if t.startswith("#N canvas"):
            canvases.append({"objects": 0, "last_obj": None, "close": None})
            stack.append(len(canvases) - 1)
            canvas_of.append(stack[-1])
            continue
        if t.startswith("#X restore") and len(stack) > 1:
            canvases[stack[-1]]["close"] = len(canvas_of)
            stack.pop()
        if not stack:
            raise ValueError("not a Pd patch")
        c = stack[-1]
        canvas_of.append(c)
        if t.startswith(OBJECTS):
            m = _NETRECEIVE.match(re.sub(r", f \d+$", "", t))
            if m:
                args = (m.group(3) or "").split()
                if _isTcp(args):
                    tcp.append((c, canvases[c]["objects"], len(canvas_of) - 1))
                elif _isOsc(args):
                    osc += 1
            canvases[c]["objects"] += 1
            canvases[c]["last_obj"] = len(canvas_of) - 1
    if not tcp:
        return None
    if len(tcp) > 1 or osc:
        raise ValueError("more than one [netreceive %d]" % PORT)
    k, nr, nr_index = tcp[0]
    c = canvases[k]
    links = []
    for i, (stmt, _) in enumerate(parts):
        m = re.match(r"#X connect (\d+) (\d+) (\d+) (\d+)$", _norm(stmt))
        if canvas_of[i] != k or not m:
            continue
        src, outlet, dst = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if dst == nr:
            raise ValueError("something is connected into [netreceive %d]" % PORT)
        if src == nr:
            if outlet != 0:
                raise ValueError("[netreceive %d]'s connection outlet is used (TCP only)" % PORT)
            links.append(i)
    oscparse, trim = c["objects"], c["objects"] + 1
    term = ";" + nl
    stmt = parts[nr_index][0]
    parts[nr_index][0] = re.sub(r"netreceive 3000( 0)?(?=\s|,|$)", "netreceive -u -b 3000", stmt, count=1)
    x, y = (int(v) for v in _NETRECEIVE.match(_norm(stmt)).group(1, 2))
    moved = []
    for i in links:
        m = re.match(r"#X connect \d+ 0 (\d+) (\d+)$", _norm(parts[i][0]))
        moved.append(["#X connect %d 0 %s %s" % (trim, m.group(1), m.group(2)), term])
        parts[i] = None
    new_links = [["#X connect %d 0 %d 0" % (nr, oscparse), term],
                 ["#X connect %d 0 %d 0" % (oscparse, trim), term]] + moved
    close = c["close"] if c["close"] is not None else len(parts)
    if close == len(parts) and parts[-1] is not None and not parts[-1][1]:
        parts[-1][1] = term  # a last statement without its ";"
    parts[close:close] = new_links
    parts[c["last_obj"] + 1:c["last_obj"] + 1] = [["#X obj %d %d oscparse" % (x, y + 25), term],
                                                    ["#X obj %d %d list trim" % (x, y + 50), term]]
    return "".join(s + t for s, t in (p for p in parts if p is not None))


def copyPath(path):
    folder, name = os.path.split(path)
    return os.path.join(folder, "." + name[:-3] + ".osc.pd")


# The patch Pd should open: the original, or its OSC copy (written when
# missing or older). In the same folder, as the patch's samples and
# abstractions are found relative to it.
def forNebulae(path):
    copy = copyPath(path)
    try:
        if os.path.getmtime(copy) >= os.path.getmtime(path):
            return copy
    except OSError:
        pass
    try:
        converted = convert(textfile.read(path))
    except ValueError as e:
        _log.warning("%s: cannot use it over OSC (%s): it gets no values", os.path.basename(path), e)
        return path
    if converted is None:
        return path
    if neb_globals.remount_fs is True:
        os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
    try:
        with open(copy, "w", encoding="utf-8") as f:
            f.write(converted)
    finally:
        if neb_globals.remount_fs is True:
            os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
    _log.info("%s: old TCP patch, using an OSC copy", os.path.basename(path))
    return copy
