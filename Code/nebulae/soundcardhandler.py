import ctypes

class SoundcardHandler:
    
    def __init__(self, device=b"default"):
        self.LEFT = 0
        self.RIGHT = 1

        self.device = device
        self.libasound = ctypes.CDLL("libasound.so")
        self.mixer = ctypes.c_void_p()  # Mixer handle
        
        # Define function signatures
        self.libasound.snd_mixer_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
        self.libasound.snd_mixer_open.restype = ctypes.c_int
        self.libasound.snd_mixer_attach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.libasound.snd_mixer_attach.restype = ctypes.c_int
        self.libasound.snd_mixer_selem_register.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.libasound.snd_mixer_selem_register.restype = ctypes.c_int
        self.libasound.snd_mixer_load.argtypes = [ctypes.c_void_p]
        self.libasound.snd_mixer_load.restype = ctypes.c_int
        self.libasound.snd_mixer_find_selem.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.libasound.snd_mixer_find_selem.restype = ctypes.c_void_p
        self.libasound.snd_mixer_selem_set_capture_volume.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        self.libasound.snd_mixer_selem_set_capture_volume.restype = ctypes.c_int

        self.strcap = None
        self.capturecontrol = None

    def initcapture(self):
        # Open ALSA mixer
        if self.libasound.snd_mixer_open(ctypes.byref(self.mixer), 0) < 0:
            print "Error: Cannot open ALSA mixer"
        if self.libasound.snd_mixer_attach(self.mixer, self.device) < 0:
            print "Error: Cannot attach mixer to device"
        if self.libasound.snd_mixer_selem_register(self.mixer, None, None) < 0:
            print "Error: Cannot register mixer element"
        if self.libasound.snd_mixer_load(self.mixer) < 0:
            print "Error: Cannot load mixer elements"

        # Find the capture control once and store it
        self.strcap = ctypes.create_string_buffer(b"Capture")  # Store control name buffer
        self.capturecontrol = self.libasound.snd_mixer_find_selem(self.mixer, self.strcap)
        if not self.capturecontrol:
            self.capturecontrol = None
            print "Error: Capture control not found"

    def init(self):
        self.initcapture()

    def setInputLevel(self, volume):

        volume = int(volume)
        
        if volume < 0:
            volume = 0
        if volume > 31:
            volume = 31
        
        ctvol = ctypes.c_long(volume)
        
        if self.capturecontrol is None:
            self.initcapture()

        self.libasound.snd_mixer_selem_set_capture_volume(self.capturecontrol, self.LEFT, ctvol)
        self.libasound.snd_mixer_selem_set_capture_volume(self.capturecontrol, self.RIGHT, ctvol)

    def __del__(self):
        """ Destructor """
        if self.mixer:
            self.libasound.snd_mixer_open(ctypes.byref(self.mixer), 0)  # Close mixer