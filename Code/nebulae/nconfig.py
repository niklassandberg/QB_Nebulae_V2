import configparser
from classlogger import ClassLogger


class NConfig:

   def __init__(self):
       self.config = configparser.ConfigParser()
       self.config.read("./nebulae.opt")
       self.log = ClassLogger.loggerSetup(self)

   def getValue(self,section,var,defvalue):
      try:
        val = self.config.get(section,var)
        self.log.debug("config " + section + ":"+ var + "=" + str(val))
      except: 
        val = defvalue
      return val

