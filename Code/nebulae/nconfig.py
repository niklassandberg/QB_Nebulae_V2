import configparser


class NConfig:

   def __init__(self):
       self.config = configparser.ConfigParser()
       self.config.read("./nebulae.opt")

   def getValue(self,section,var,defvalue):
      try:
        val = self.config.get(section,var)
        print("config " + section + ":"+ var + "=" + str(val))
      except: 
        val = defvalue
      return val

