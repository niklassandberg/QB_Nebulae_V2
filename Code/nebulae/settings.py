import os
from multiprocessing import Process
from functools import partial
import neb_globals
from classlogger import ClassLogger

class SettingManager(object):
    def __init__(self, config):
        self.settingDict = dict() # Container for Config Data
        self.defaultDict = dict()
        self.configData = config
        self.filename = "nebsettings.txt"
        self.defaultsfilename = "defaultnebsettings.txt"
        self.filepath = "/home/alarm/QB_Nebulae_V2/Code/config/"
        self.lastUpdate = 0
        self.lines = []
        self.writeProcess = None
        self.log = ClassLogger.loggerSetup(self)

    def read(self):
        settingList = []
        defaultList = []
        fpath = self.filepath + self.defaultsfilename
        #print("Searching: \"" + fpath + "\" for settings.")
        #print("Is file: " + str(os.path.isfile(fpath)))
        #print("Size: " + str(os.path.getsize(fpath)))
        with open(fpath, 'r') as myfile:
            for line in myfile:
                defaultList.append(line)
        self.populateDefaultDict(defaultList,self.defaultDict)
        #self.mutableSettings = self.settingDict.copy()
        fpath = self.filepath + self.filename
        #print("Searching: \"" + fpath + "\" for settings.")
        #print("Is file: " + str(os.path.isfile(fpath)))
        #print("Size: " + str(os.path.getsize(fpath)))
        if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
            self.log.info("Found Previously saved settings")
            with open(self.filepath + self.filename, 'r') as myfile:
                for line in myfile:
                    if line.strip():
                        settingList.append(line)
            self.populateDict(settingList, self.settingDict)
            #self.mutableSettings = self.settingDict.copy()
        else:
            self.log.info("Could not locate previous settings.")
            self.populateDict(defaultList, self.settingDict)
        self.mutableSettings = self.settingDict.copy()

    def write(self): 
        try:
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh rw")
            with open(self.filepath + self.filename, 'w') as myfile:
                for line in self.lines:
                    myfile.write(line)
            if neb_globals.remount_fs is True:
                os.system("sh /home/alarm/QB_Nebulae_V2/Code/scripts/mountfs.sh ro")
        except:
            self.log.error("Could not write .nebsettings file")

    #TODO: maybe use??
    def offloadWrite(self):
        if self.writeProcess is not None:
            if not self.writeProcess.is_alive():
                #try:
                #self.writeProcess.terminate()
                self.writeProcess.join()
                self.writeProcess = Process(target=self.write, args=())
                self.writeProcess.start()
                #except:
                    #print 'Could not restart offload_write sub-process.'
                    #print 'Likely OSError: [ErrNo 12] Cannot allocate memory'
        else:
            #try:
            self.writeProcess = Process(target=self.offloadWrite, args=())
            self.writeProcess.start()
            #except:
            #    print 'Could not start offload_write sub-process.'
            #    print 'Likely OSError: [ErrNo 12] Cannot allocate memory'

    def update(self, now):
        self.lastUpdate = now
        self.lines = []
        for item in self.settingDict.keys():
            self.settingDict[item] = self.mutableSettings[item]
            line = str(item) + "," + str(self.settingDict[item]) + "\n"
            self.lines.append(line)

    def getDefault(self, key):            
        if key in self.defaultDict: 
            item = self.defaultDict[key]
            try:
                out = float(item)
            except ValueError:
                out = item
            if out is None:
                out = 0
            return out

    def load(self,key):
        if key in self.settingDict:
            try:
                out = float(self.settingDict[key]) 
            except ValueError:
                out = self.settingDict[key]
            if out is None:
                out = self.defaultDict[key]
            if out is None:
                out = 0
            self.log.debug("Loading " + key + " value: " + str(out))
            return out

    def getLastUpdate(self):
        return self.lastUpdate

    def populateDict(self, settingslist, settingsdict):
        tempList = []
        for line in settingslist:
            strippedLine = line.rstrip()
            tempList = strippedLine.split(",")
            newKey = tempList[0]
            tempList.pop(0)
            settingsdict[newKey] = tempList[0]

    def populateDefaultDict(self, settingslist, settingsdict):
        tempList = []
        for line in settingslist:
            strippedLine = line.rstrip()
            tempList = strippedLine.split(",")
            newKey = tempList[0]
            tempList.pop(0)
            if self.configData is not None:
                if newKey in self.configData and '_alt' in newKey:
                    if isinstance(self.configData[newKey], str):
                        self.log.debug('setting ' + newKey + ' to: ' + str(self.configData[newKey]))
                        settingsdict[newKey] = self.configData[newKey]
                    else:
                        try:
                            new_val = float(self.configData[newKey][0])
                            self.log.debug('setting ' + newKey + ' to: ' + str(new_val))
                            settingsdict[newKey] = new_val
                        except ValueError:
                            settingsdict[newKey] = tempList[0]
                            self.log.warning('complex alt settings are not yet supported.')
                        if new_val == None:
                            settingsdict[newKey] = tempList[0]
                else:
                    settingsdict[newKey] = tempList[0]
            else:
                settingsdict[newKey] = tempList[0]

    def hasSetting(self, key):
        if key in self.settingDict:
            return True
        else:
            return False

    def save(self, key, value):
        self.mutableSettings[key] = value

    def printSettings(self):
        self.log.debug("Printing Settings Now")
        for item in self.settingDict.keys():
            self.log.debug(str(item) + "," + str(self.settingDict[item]))
        self.log.debug("Done Printing Settings")
        self.log.debug("Printing Defaults Now")
        for item in self.defaultDict.keys():
            self.log.debug(str(item) + "," + str(self.defaultDict[item]))
        self.log.debug("Done Printing Default")

