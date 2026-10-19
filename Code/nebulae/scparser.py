# SuperCollider .scd File Parser
from classlogger import ClassLogger

# Reads the nebconfig block of a .scd, the same way InstrParser does for .instr.
# In a .scd the block sits inside a /* */ comment, so sclang never sees it:
#   /*
#   nebconfigbegin
#   ksmps,64
#   speed,rawencoder
#   nebconfigend
#   */
class ScParser(object):
    def __init__(self):
        self.configDict = dict() # Container for Config Data
        self.configList = []
        self.scString = ""
        self.log = ClassLogger.loggerSetup(self)

    def parse(self, filename, path, ext='.scd'):
        self.clearConfigDict()
        withinConfigChunk = False
        configList = []
        scString = ""
        with open(path + filename + ext, 'r') as myfile:
            for line in myfile:
                if line.startswith("nebconfigbegin"):
                    withinConfigChunk = True
                if withinConfigChunk is True:
                    if line.startswith("nebconfigend"):
                        withinConfigChunk = False
                    elif not line.startswith("nebconfigbegin"):
                        configList.append(line)
                else:
                    scString += line
            self.configList = configList
            self.scString = scString
        self.populateDict()

    def populateDict(self):
        tempList = []
        for line in self.configList:
            strippedLine = line.rstrip()
            if not strippedLine:
                continue
            tempList = strippedLine.split(",")
            newKey = tempList[0]
            tempList.pop(0)
            self.configDict[newKey] = tempList

    def getScString(self):
        return self.scString

    # Type of an encoder (speed/pitch): "rawencoder" if the .scd declares it, else "hybrid".
    def getType(self, name):
        entry = self.configEntry(name)
        if entry and entry[0].strip().lower() == "rawencoder":
            return "rawencoder"
        return "hybrid"

    def configEntry(self, name):
        if name in self.configDict:
            return self.configDict.get(name)
        else:
            return None

    def clearConfigDict(self):
        self.configDict.clear()

    # Same as InstrParser: not parsed yet, so always empty.
    def getHoldWithTriggCombos(self):
        return self.holdWithTriggList if hasattr(self, 'holdWithTriggList') else []

    def getConfigDict(self):
        return self.configDict

    def getOutputPeriod(self):
        ksmps = int(self.configDict.get("ksmps", ["128"])[0])
        sr = int(self.configDict.get("sr", ["48000"])[0])
        block_ms = (ksmps / float(sr)) * 1000.0
        return max(100.0, block_ms * 75)

    def printConfigList(self):
        self.log.debug("Printing Config Chunk Now")
        for configItem in self.configList:
            self.log.debug(configItem)
        self.log.debug("Done printing config chunk")

    def printScString(self):
        self.log.debug("printing sc string")
        self.log.debug(self.scString)
        self.log.debug("done printing sc string")
