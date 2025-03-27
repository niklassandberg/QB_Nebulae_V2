import ctypes

class SoundcardHandler:
    _instance = None  # Singleton instance

    #simple Singleton impl. 
    # It could also avoid raise condition for creation of SoundcardHandler
    # but we dont need it right now

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SoundcardHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self, device=b"hw:sndrpiproto", capturecontrol=b"Capture"):

        self.LEFT = 0
        self.RIGHT = 1
        self.device = device
        
        self.libasound = None
        self.mixer = None
        self.strcap = None
        self.device = device
        self.capturecontrol = capturecontrol

        self._log_init("SoundcardHandler")

    def initLib(self):
        
        self._log_message("initLib")

        if self.libasound is not None:
            return True
        try:
            self.libasound = ctypes.CDLL("libasound.so")
        except OSError:
            self._log_error("initLib - OSError")
            return False  # Failed to reload the library
        
        # Define function signatures
        self.libasound.snd_mixer_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
        self.libasound.snd_mixer_open.restype = ctypes.c_int
        self.libasound.snd_mixer_attach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.libasound.snd_mixer_attach.restype = ctypes.c_int

        self.libasound.snd_mixer_detach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.libasound.snd_mixer_detach.restype = ctypes.c_int

        self.libasound.snd_mixer_selem_register.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.libasound.snd_mixer_selem_register.restype = ctypes.c_int
        self.libasound.snd_mixer_load.argtypes = [ctypes.c_void_p]
        self.libasound.snd_mixer_load.restype = ctypes.c_int
        self.libasound.snd_mixer_close.argtypes = [ctypes.c_void_p]
        self.libasound.snd_mixer_close.restype = ctypes.c_int
        self.libasound.snd_mixer_find_selem.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.libasound.snd_mixer_find_selem.restype = ctypes.c_void_p
        self.libasound.snd_mixer_selem_set_capture_volume.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        self.libasound.snd_mixer_selem_set_capture_volume.restype = ctypes.c_int

        self._log_message("initLib end")
        #new
        """
        self.libasound.snd_mixer_selem_id_alloca.argtypes = [ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
        self.libasound.snd_mixer_selem_id_alloca.restype = None  # This function does not return a value
        self.libasound.snd_mixer_selem_id_set_index.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint]
        self.libasound.snd_mixer_selem_id_set_index.restype = None  # This function does not return a value
        self.libasound.snd_mixer_selem_id_set_name.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p]
        self.libasound.snd_mixer_selem_id_set_name.restype = None  # This function does not return a value
        """

        return True

    def initMixer(self):

        if self.mixer is not None:
            return True
        
        if self.initLib() == False:
            return False
        
        self.mixer = ctypes.c_void_p()  # Mixer handle
        
        self.device_bytes = self.device
        if isinstance(self.device, str):
            self.device_bytes = self.device.encode('utf-8')
        self.device_c = ctypes.c_char_p(self.device_bytes)
        
        if self.libasound.snd_mixer_open(ctypes.byref(self.mixer), 0) < 0:
            self._log_error("Cannot open ALSA mixer")
            self.mixer = None
            return False

        if self.libasound.snd_mixer_attach(self.mixer, self.device_c) < 0:
            self._log_error("Cannot attach mixer to device")
            self.libasound.snd_mixer_close(self.mixer)
            self.mixer = None
            return False
        if self.libasound.snd_mixer_selem_register(self.mixer, None, None) < 0:
            self._log_error("Cannot register mixer element")
            self.removeMixer()
            self.mixer = None
            return False
        if self.libasound.snd_mixer_load(self.mixer) < 0:
            self._log_error("Cannot load mixer elements")
            self.removeMixer()
            self.mixer = None
            return False

        self.strcap = ctypes.create_string_buffer(self.capturecontrol)
        self.capturecontrol = self.libasound.snd_mixer_find_selem(self.mixer, self.strcap)
        if not self.capturecontrol:
            self._log_error("Error: Capture '"+ self.strcap.value +"' control not found")
            self.removeMixer()
            self.mixer = None
            return False
        
        return True

    def removeMixer(self):
        self._log_message("removeMixer")
        if self.mixer is None:
            return True
        retval = True
        self._log_message("removeMixer 2")
        if self.libasound.snd_mixer_detach(self.mixer, self.device) < 0:
            self._log_error("snd_mixer_detach failed!!")
            retval = False
        elif self.libasound.snd_mixer_close(self.mixer) < 0:
            self._log_error("snd_mixer_close failed!!")
            retval = False
        else:
            self._log_message("snd_mixer_close IS working!!")
        self._log_message("removeMixer 4")
        self.mixer = None
        return retval

    def removeLib(self):
        
        self._log_message("removeLib")
            
        if self.libasound is None:
            return True
        self.removeMixer()

        self._log_message("removeLib 2")
        
        ctypes.cdll.LoadLibrary("libdl.so").dlclose(self.libasound._handle)
        del self.libasound
        
        self._log_message("removeLib 3")

        self.libasound = None  # Ensure this is cleared
        self.mixer = None
        
        return True

    def setInputLevel(self, volume):
        volume = max(0, min(31, int(volume)))  # Clamp volume between 0 and 31
        ctvol = ctypes.c_long(volume)
        
        if self.initMixer() == False:
            self.removeLib()
            return
        
        try:
            self.libasound.snd_mixer_selem_set_capture_volume(self.capturecontrol, self.LEFT, ctvol)
            self.libasound.snd_mixer_selem_set_capture_volume(self.capturecontrol, self.RIGHT, ctvol)
        except OSError:
            self._log_error("snd_mixer_selem_set_capture_volume not working!!")
        
    def _log_message(self, message):
        with open('/tmp/soundcardHandler.txt', 'a') as f:
            f.write("Message: "+ message + "\n")

    def _log_error(self, message):
        with open('/tmp/soundcardHandler.txt', 'a') as f:
            f.write("Error: "+ message + "\n")

    def _log_warning(self, message):
        with open('/tmp/soundcardHandler.txt', 'a') as f:
            f.write("Warning: "+ message + "\n")

    def _log_init(self, message):
        with open('/tmp/soundcardHandler.txt', 'a') as f:
            f.write("Init: "+ message + "\n")