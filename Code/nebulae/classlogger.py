import logging
import threading

class ClassLogger:
    _configured = False
    _lock = threading.Lock()

    @classmethod
    def _configure_root(cls):
        with cls._lock:
            if cls._configured:
                return
            root = logging.getLogger()
            root.setLevel(logging.DEBUG)
            fh = logging.FileHandler("/tmp/nebulae_logging.log")
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s %(name)s %(levelname)s: %(message)s"
            )
            fh.setFormatter(formatter)
            root.addHandler(fh)
            cls._configured = True

            logging.getLogger("Adafruit_I2C").propagate = False
            logging.getLogger("Adafruit_I2C").setLevel(logging.CRITICAL)

    @classmethod
    def loggerSetup(cls, owner):
        """
        owner = usually `self`
        """
        cls._configure_root()
        return logging.getLogger(owner.__class__.__name__)
