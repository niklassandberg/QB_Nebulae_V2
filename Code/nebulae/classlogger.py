import faulthandler
import logging
import os
import subprocess
import sys
import threading

# Logs to stderr, which systemd puts in the journal. A "<N>" prefix sets the
# journal priority. Level: NEB_LOG_LEVEL, else log_level in configsettings.
STATS = 15  # status lines, between DEBUG and INFO
logging.addLevelName(STATS, "STATS")


def _level_name():
    from configsettings import configSettings  # circular import
    return os.environ.get("NEB_LOG_LEVEL") or configSettings.logLevel


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


# Prefix on every traceback line too; none on a terminal.
class JournalFormatter(logging.Formatter):
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


# Quiet mode keeps the journal in RAM: a crash must survive a power cut.
def _flush_journal():
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
            # stdout to the journal is block buffered: print() came minutes late.
            try:
                sys.stdout.reconfigure(line_buffering=True)
            except (AttributeError, ValueError):
                pass
            sys.excepthook = cls._excepthook
            threading.excepthook = cls._thread_excepthook
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
        cls._configure_root()
        logging.getLogger("Nebulae").critical(message, exc_info=True)
        _flush_journal()

    @classmethod
    def loggerSetup(cls, owner, level=None):
        cls._configure_root()
        log = logging.getLogger(owner.__class__.__name__)
        if level is not None:
            log.setLevel(level)
        return log
