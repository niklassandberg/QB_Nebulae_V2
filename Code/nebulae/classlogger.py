import logging
import threading
from logging.handlers import RotatingFileHandler

class ClassLogger:
    _configured = False
    _lock = threading.Lock()

    @classmethod
    def _configure_root(cls,level):
        with cls._lock:
            if cls._configured:
                return
            root = logging.getLogger()
            
            root.setLevel(level)
            fh = RotatingFileHandler(
                "/tmp/nebulae_logging.log",
                maxBytes=1 * 1024 * 1024,  # 1 MB
                backupCount=5
            )
            fh.setLevel(logging.DEBUG)
            #formatter = logging.Formatter(
            #    "%(asctime)s %(name)s %(levelname)s: %(message)s"
            #)

            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d]: %(message)s"
            )

            fh.setFormatter(formatter)
            root.addHandler(fh)
            cls._configured = True

            logging.getLogger("Adafruit_I2C").propagate = False
            logging.getLogger("Adafruit_I2C").setLevel(logging.CRITICAL)

    @classmethod
    def loggerSetup(cls, owner,level=logging.DEBUG):
        """
        owner = usually `self`
        """
        cls._configure_root(level)
        return logging.getLogger(owner.__class__.__name__)
