import configparser
import textfile
from classlogger import ClassLogger


class NConfig:

   def __init__(self):
       self.config = configparser.ConfigParser()
       try:
           text = textfile.read("./nebulae.opt")
       except OSError:
           text = ""  # configparser.read() skips a file it cannot open
       self.config.read_string(text, "./nebulae.opt")
       self.log = ClassLogger.loggerSetup(self)

   def getValue(self,section,var,defvalue):
      try:
        val = self.config.get(section,var)
        self.log.debug("config " + section + ":"+ var + "=" + str(val))
      except:
        val = defvalue
      return val
