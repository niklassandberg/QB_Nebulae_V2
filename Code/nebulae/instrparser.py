# Instr File Parser
from classlogger import ClassLogger

class InstrParser(object):
    def __init__(self):
        self.configDict = dict() # Container for Config Data
        self.instrString = ""
        self.log = ClassLogger.loggerSetup(self)

    def parse(self, filename, path, ext='.instr'):
        self.clearConfigDict()
        withinConfigChunk = False
        configList = []
        orcString = ""
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
                    orcString += line
            self.configList = configList
            self.instrString = orcString
        self.populateDict()

    def populateDict(self):
        tempList = []
        for line in self.configList:
            strippedLine = line.rstrip()
            tempList = strippedLine.split(",")
            newKey = tempList[0]
            tempList.pop(0)
            self.configDict[newKey] = tempList

    def getInstrString(self):
        return self.instrString

    def configEntry(self, name):
        if name in self.configDict:
            return self.configDict.get(name)
        else:
            return None
    
    def clearConfigDict(self):
        self.configDict.clear()

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

    def printInstrString(self):
        self.log.debug("printing orchestra string")
        self.log.debug(self.instrString)
        self.log.debug("done printing orchestra string")
