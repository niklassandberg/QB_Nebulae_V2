# nebmixer.py
import ctypes
import os

LEFT = 0
RIGHT = 1
_libasound = None
_mixer = None
_capturecontrol_handle = None
_enable = True

def _log_message(message):
    print("NebMixer Message: "+message+"\n")

def _log_error(message):
    print("NebMixer Error: "+message+"\n")

def _log_warning(message):
    print("NebMixer Warning: "+message+"\n")

def _init_lib_once():
    global _libasound
    if _libasound is None:
        _log_message("_init_lib_once")
        try:
            _libasound = ctypes.CDLL("libasound.so")
            # Define function signatures
            _libasound.snd_mixer_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
            _libasound.snd_mixer_open.restype = ctypes.c_int
            _libasound.snd_mixer_attach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            _libasound.snd_mixer_attach.restype = ctypes.c_int
            _libasound.snd_mixer_detach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            _libasound.snd_mixer_detach.restype = ctypes.c_int
            _libasound.snd_mixer_selem_register.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            _libasound.snd_mixer_selem_register.restype = ctypes.c_int
            _libasound.snd_mixer_load.argtypes = [ctypes.c_void_p]
            _libasound.snd_mixer_load.restype = ctypes.c_int
            _libasound.snd_mixer_close.argtypes = [ctypes.c_void_p]
            _libasound.snd_mixer_close.restype = ctypes.c_int
            _libasound.snd_mixer_find_selem.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            _libasound.snd_mixer_find_selem.restype = ctypes.c_void_p
            _libasound.snd_mixer_selem_set_capture_volume.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            _libasound.snd_mixer_selem_set_capture_volume.restype = ctypes.c_int
            _log_message("_init_lib_once end")
        except OSError:
            _log_error("_init_lib_once - OSError")
            return False
    return True

def init(device= b"hw:sndrpiproto", capturecontrol= b"Capture"):
    global _mixer, strcap, _capturecontrol_handle
    _log_message("initMixer")
    if _mixer is not None:
        return True

    if not _init_lib_once():
        return False

    _mixer = ctypes.c_void_p()  # Mixer handle

    device_bytes = device
    if isinstance(device, str):
        device_bytes = device.encode('utf-8')
    device_c = ctypes.c_char_p(device_bytes)

    _log_message("snd_mixer_open")
    if _libasound.snd_mixer_open(ctypes.byref(_mixer), 0) < 0:
        _log_error("Cannot open ALSA mixer")
        _mixer = None
        return False

    _log_message("snd_mixer_attach")
    if _libasound.snd_mixer_attach(_mixer, device_c) < 0:
        _log_error("Cannot attach mixer to device")
        _libasound.snd_mixer_close(_mixer)
        _mixer = None
        return False
    _log_message("snd_mixer_selem_register")
    if _libasound.snd_mixer_selem_register(_mixer, None, None) < 0:
        _log_error("Cannot register mixer element")
        remove()
        _mixer = None
        return False
    _log_message("snd_mixer_load")
    if _libasound.snd_mixer_load(_mixer) < 0:
        _log_error("Cannot load mixer elements")
        remove()
        _mixer = None
        return False
    _log_message("snd_mixer_find_selem")
    strcap = ctypes.create_string_buffer(capturecontrol)
    _capturecontrol_handle = _libasound.snd_mixer_find_selem(_mixer, strcap)
    if not _capturecontrol_handle:
        _log_error("Error: Capture '"+ strcap.value +"' control not found")
        remove()
        _mixer = None
        return False

    return True

def remove(device= b"hw:sndrpiproto"):
    global _mixer, _capturecontrol_handle
    _log_message("removeMixer")
    if _mixer is None:
        return True
    retval = True

    device_bytes = device
    if isinstance(device, str):
        device_bytes = device.encode('utf-8')
    device_c = ctypes.c_char_p(device_bytes)

    _log_message("snd_mixer_detach")
    if _libasound.snd_mixer_detach(_mixer, device_c) < 0:
        _log_error("snd_mixer_detach failed!!")
        retval = False
    _log_message("snd_mixer_close")
    if _libasound.snd_mixer_close(_mixer) < 0:
        _log_error("snd_mixer_close failed!!")
        retval = False
    _log_message("removeMixer exit")
    _capturecontrol_handle = None
    _mixer = None
    return retval

def _removeLib():
    global _libasound, _mixer
    _log_message("removeLib")
    if _libasound is None:
        return True
    remove()
    _log_message("LoadLibrary")
    try:
        if hasattr(_libasound, '_handle'):
            ctypes.cdll.LoadLibrary("libdl.so").dlclose(_libasound._handle)
        else:
            _log_warning("libasound dont have hamle, cannot unload!!!")
    except AttributeError:
        _log_warning("Could not explicitly dlclose libasound!!!")
    _libasound = None
    _log_message("removeLib exit")
    return True

def enable():
    global _enable
    _enable = True
    
def disable():
    global _enable
    _enable = False

def setInputLevel(volume):
    global _capturecontrol_handle, LEFT, RIGHT, _mixer, _capturecontrol

    if not _enable:
        return

    volume = max(0, min(31, int(volume)))  # Clamp volume between 0 and 31
    ctvol = ctypes.c_long(volume)

    if not init():
        return

    #todo: this chould not be nesesary, remove later!!
    if _capturecontrol_handle is None:
        _log_error("Capture control handle is None. Ensure initMixer was successful.")
        return

    try:
        global _libasound
        _libasound.snd_mixer_selem_set_capture_volume(_capturecontrol_handle, LEFT, ctvol)
        _libasound.snd_mixer_selem_set_capture_volume(_capturecontrol_handle, RIGHT, ctvol)
    except OSError:
        _log_error("snd_mixer_selem_set_capture_volume not working!!")