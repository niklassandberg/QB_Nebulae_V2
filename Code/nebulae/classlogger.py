import faulthandler
import logging
import os
import subprocess
import sys
import threading

# All of Nebulae's log lines go to stderr. nebulae.service starts nebulae.py,
# so systemd puts them in the journal, together with nebio, Csound, Pd, jack
# and sclang: one timeline, "journalctl -b" (all), "journalctl -u nebulae".
# Where the journal keeps them is journald's setting, not this code's:
# /etc/systemd/journald.conf.d/nebulae.conf (SD card, max 50 MB, oldest
# removed first; Storage=volatile = RAM only, Storage=none = off), and Quiet
# mode keeps it in RAM (quiet.sh). No files, no rotation here.
#
# Each line starts with a syslog priority "<N>". The journal stores it as the
# line's level and removes it: "journalctl -u nebulae -p err" = errors only.
# Which levels are written at all: Code/config/log_level (one word: DEBUG,
# INFO, WARNING, ERROR or CRITICAL; no file = INFO), or NEB_LOG_LEVEL in the
# environment, which wins.

LEVEL_FILE = "/home/alarm/QB_Nebulae_V2/Code/config/log_level"


def _level_name():
    name = os.environ.get("NEB_LOG_LEVEL")
    if name:
        return name
    try:
        with open(LEVEL_FILE) as f:
            words = f.read().split()
        return words[0] if words else "INFO"
    except OSError:
        return "INFO"


def _priority(levelno):
    if levelno >= logging.CRITICAL:
        return 2
    if levelno >= logging.ERROR:
        return 3
    if levelno >= logging.WARNING:
        return 4
    if levelno >= logging.INFO:
        return 6
    return 7


class JournalFormatter(logging.Formatter):
    # Every line gets the prefix, also the lines of a traceback, so a crash
    # is one block of the same level in the journal. Not on a terminal
    # (nebulae.py started by hand), where it would show.
    def __init__(self, fmt):
        super().__init__(fmt)
        try:
            self.journal = not sys.stderr.isatty()
        except (AttributeError, ValueError):
            self.journal = True

    def format(self, record):
        text = super().format(record)
        if not self.journal:
            return text
        prefix = "<%d>" % _priority(record.levelno)
        return "\n".join(prefix + line for line in text.splitlines())


def _flush_journal():
    # A crash stays in the journal across a power cut: in Quiet mode the
    # journal is in RAM (journalctl --relinquish-var), this writes it to the
    # SD card. Nebulae has stopped playing anyway.
    try:
        subprocess.run(["journalctl", "--flush"], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


class ClassLogger:
    _configured = False
    _lock = threading.Lock()

    @classmethod
    def _configure_root(cls):
        with cls._lock:
            if cls._configured:
                return
            level = logging.getLevelName(_level_name().upper())
            if not isinstance(level, int):
                level = logging.INFO
            root = logging.getLogger()
            root.setLevel(level)
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(JournalFormatter(
                "%(levelname)s [%(filename)s:%(lineno)d]: %(message)s"))
            root.addHandler(handler)
            # print() output too: stdout to the journal is block buffered, so
            # it came minutes late and out of order with the log lines.
            try:
                sys.stdout.reconfigure(line_buffering=True)
            except (AttributeError, ValueError):
                pass
            sys.excepthook = cls._excepthook
            threading.excepthook = cls._thread_excepthook
            # Hard crashes inside C code (Csound, nebio via ctypes): where it
            # died, written straight to stderr.
            faulthandler.enable(file=sys.stderr)
            cls._configured = True

            logging.getLogger("Adafruit_I2C").propagate = False
            logging.getLogger("Adafruit_I2C").setLevel(logging.CRITICAL)

    @staticmethod
    def _excepthook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        logging.getLogger("Nebulae").critical("Nebulae crashed", exc_info=(kind, value, tb))
        _flush_journal()

    @staticmethod
    def _thread_excepthook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        name = args.thread.name if args.thread is not None else "?"
        logging.getLogger("Nebulae").critical(
            "Thread %s crashed", name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        _flush_journal()

    @classmethod
    def logCrash(cls, message):
        """For an except block that ends Nebulae: CRITICAL with traceback."""
        cls._configure_root()
        logging.getLogger("Nebulae").critical(message, exc_info=True)
        _flush_journal()

    @classmethod
    def loggerSetup(cls, owner, level=None):
        """
        owner = usually `self`; level = optional own level for this class
        """
        cls._configure_root()
        log = logging.getLogger(owner.__class__.__name__)
        if level is not None:
            log.setLevel(level)
        return log
